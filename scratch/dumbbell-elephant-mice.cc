/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/**
 * Enhanced FaiRTT in NS-3: Stage 1 Dumbbell Baseline Simulation
 *
 * Topology:
 *
 *   Sender A (n0) --- [Access A] ---\
 *                                    Router 1 (n2) === [Bottleneck] === Router 2 (n3) --- [Access A] ---> Receiver A (n4)
 *   Sender B (n1) --- [Access B] ---/                                                 \--- [Access B] ---> Receiver B (n5)
 *
 * Flow A: Sender A (n0) -> Receiver A (n4)
 * Flow B: Sender B (n1) -> Receiver B (n5)
 * Both flows traverse the shared bottleneck link between Router 1 and Router 2.
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

using namespace ns3;

namespace fs = std::filesystem;

// Global trace output streams
static std::ofstream g_throughputStream;
static std::ofstream g_queueStream;
static std::ofstream g_rttStream;
static std::ofstream g_cwndStream;
static std::ofstream g_v2ControlStream;

// Tracking state for periodic throughput calculation
static uint64_t g_lastRxBytesA = 0;
static uint64_t g_lastRxBytesB = 0;
static Time g_lastSampleTime = Seconds(0);

// Ptrs to sink applications
static Ptr<PacketSink> g_sinkA;
static Ptr<PacketSink> g_sinkB;
static Ptr<QueueDisc> g_bottleneckQueue;

// Additional finite mice flows for the optional elephant-mice workload.
struct MiceFlowRecord
{
    uint16_t port;
    double startTime;
    double stopTime;
    uint64_t maxBytes;
    Ptr<PacketSink> sink;
    uint64_t lastRxBytes = 0;
    bool completed = false;
};
static std::vector<MiceFlowRecord> g_miceFlows;
static std::ofstream g_miceStream;
static bool g_enableElephantMice = false;

/**
 * Calculate Jain's Fairness Index between two values:
 * J = (T_A + T_B)^2 / (2 * (T_A^2 + T_B^2))
 */
static double
CalculateJainsIndex(double throughputA, double throughputB)
{
    double sum = throughputA + throughputB;
    if (sum <= 0.0)
    {
        return 1.0; // Both flows zero: trivially fair
    }
    double sumSq = (throughputA * throughputA) + (throughputB * throughputB);
    if (sumSq <= 0.0)
    {
        return 1.0;
    }
    return (sum * sum) / (2.0 * sumSq);
}

/**
 * Periodic sampler for throughput, Jain's fairness index, and queue occupancy.
 */
static void
SampleMetrics(Time interval)
{
    Time now = Simulator::Now();
    double timeSec = now.GetSeconds();
    double dtSec = (now - g_lastSampleTime).GetSeconds();

    if (dtSec > 0.0)
    {
        uint64_t curRxBytesA = g_sinkA ? g_sinkA->GetTotalRx() : 0;
        uint64_t curRxBytesB = g_sinkB ? g_sinkB->GetTotalRx() : 0;

        uint64_t dBytesA = (curRxBytesA >= g_lastRxBytesA) ? (curRxBytesA - g_lastRxBytesA) : 0;
        uint64_t dBytesB = (curRxBytesB >= g_lastRxBytesB) ? (curRxBytesB - g_lastRxBytesB) : 0;

        double mbpsA = (dBytesA * 8.0) / (dtSec * 1e6);
        double mbpsB = (dBytesB * 8.0) / (dtSec * 1e6);
        double aggregateMbps = mbpsA + mbpsB;
        double jainIndex = CalculateJainsIndex(mbpsA, mbpsB);

        g_throughputStream << std::fixed << std::setprecision(4)
                           << timeSec << ","
                           << mbpsA << ","
                           << mbpsB << ","
                           << aggregateMbps << ","
                           << jainIndex << "\n";

        // In elephant-mice mode, write a separate per-flow time series.
        // Flow A is the elephant; Flow B is unused for data in this mode.
        if (g_enableElephantMice && g_miceStream.is_open())
        {
            g_miceStream << std::fixed << std::setprecision(4)
                         << timeSec << ",elephant,"
                         << ((curRxBytesA >= g_lastRxBytesA) ?
                             ((curRxBytesA - g_lastRxBytesA) * 8.0 / (dtSec * 1e6)) : 0.0)
                         << "," << curRxBytesA << "\n";
            for (auto &mice : g_miceFlows)
            {
                if (!mice.completed && timeSec >= mice.startTime && timeSec <= mice.stopTime)
                {
                    uint64_t current = mice.sink ? mice.sink->GetTotalRx() : 0;
                    uint64_t delta = current >= mice.lastRxBytes ? current - mice.lastRxBytes : 0;
                    double mbps = (delta * 8.0) / (dtSec * 1e6);
                    g_miceStream << std::fixed << std::setprecision(4)
                                 << timeSec << ",mice_" << mice.port << ","
                                 << mbps << "," << current << "\n";
                    mice.lastRxBytes = current;
                    mice.completed = current >= mice.maxBytes;
                }
            }
        }

        g_lastRxBytesA = curRxBytesA;
        g_lastRxBytesB = curRxBytesB;
        g_lastSampleTime = now;
    }

    if (g_bottleneckQueue)
    {
        uint32_t qPackets = g_bottleneckQueue->GetNPackets();
        uint32_t qBytes = g_bottleneckQueue->GetNBytes();
        g_queueStream << std::fixed << std::setprecision(4)
                      << timeSec << ","
                      << qPackets << ","
                      << qBytes << "\n";
    }

    Simulator::Schedule(interval, &SampleMetrics, interval);
}

/**
 * Trace RTT updates for a flow.
 */
static void
RttTracer(std::string flowName, Time oldVal, Time newVal)
{
    g_rttStream << std::fixed << std::setprecision(4)
                << Simulator::Now().GetSeconds() << ","
                << flowName << ","
                << newVal.GetMilliSeconds() << "\n";
}

/**
 * Trace Congestion Window updates for a flow.
 */
static void
CwndTracer(std::string flowName, uint32_t oldVal, uint32_t newVal)
{
    g_cwndStream << std::fixed << std::setprecision(4)
                 << Simulator::Now().GetSeconds() << ","
                 << flowName << ","
                 << (newVal / 1448.0) << "\n";
}

/**
 * Trace V2's smoothed BDP reduction and fairness response values.
 */
static void
V2ControlTracer(std::string flowName,
                std::string traceName,
                double oldVal,
                double newVal)
{
    g_v2ControlStream << std::fixed << std::setprecision(8)
                      << Simulator::Now().GetSeconds() << ","
                      << flowName << ","
                      << traceName << ","
                      << oldVal << ","
                      << newVal << "\n";
}

/**
 * Hook trace sources to a sender node's TCP sockets.
 */
static void
ConnectSocketTraces(uint32_t nodeId, std::string flowName)
{
    std::string pathPrefix = "/NodeList/" + std::to_string(nodeId) + "/$ns3::TcpL4Protocol/SocketList/*/";
    Config::ConnectWithoutContext(
        pathPrefix + "RTT",
        MakeBoundCallback(&RttTracer, flowName)
    );
    Config::ConnectWithoutContext(
        pathPrefix + "CongestionWindow",
        MakeBoundCallback(&CwndTracer, flowName)
    );
}

/**
 * Hook V2 controller traces on a sender node's already-created TCP sockets.
 */
static void
ConnectV2ControllerTraces(uint32_t nodeId, uint32_t socketIndex, std::string flowName)
{
    const std::string pathPrefix =
        "/NodeList/" + std::to_string(nodeId) +
        "/$ns3::TcpL4Protocol/SocketList/" + std::to_string(socketIndex) +
        "/CongestionOps/"
        "$ns3::TcpBbrEnhancedFairttV2/";
    Config::ConnectWithoutContext(
        pathPrefix + "BdpReduction",
        MakeBoundCallback(&V2ControlTracer, flowName, "BdpReduction"));
    Config::ConnectWithoutContext(
        pathPrefix + "FairnessError",
        MakeBoundCallback(&V2ControlTracer, flowName, "FairnessError"));
    Config::ConnectWithoutContext(
        pathPrefix + "ReductionStrength",
        MakeBoundCallback(&V2ControlTracer, flowName, "ReductionStrength"));
}

int
main(int argc, char* argv[])
{
    // Simulation parameters with sensible defaults
    std::string bottleneckBw = "10Mbps";
    std::string bottleneckDelay = "10ms";
    std::string accessBw = "100Mbps";
    std::string accessDelayA = "5ms";
    std::string accessDelayB = "5ms";
    std::string queueDisc = "FifoQueueDisc";
    std::string queueSize = "100p";
    std::string tcpTypeId = "TcpCubic";
    double v2FairnessFloorStrength = 0.70;
    double v2FairnessTransition = 0.15;
    double v2BdpSmoothingTimeMs = 50.0;
    uint32_t v2MaxInflightBytes = 512 * 1024;

    double simTime = 30.0;
    double flowAStart = 1.0;
    double flowAStop = 29.0;
    double flowBStart = 1.0;
    double flowBStop = 29.0;
    double samplingInterval = 0.2;

    std::string outDir = "results";
    uint32_t seed = 1;
    uint32_t run = 1;
    bool enablePcap = false;
    bool enableElephantMice = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("bottleneckBw", "Bottleneck link bandwidth", bottleneckBw);
    cmd.AddValue("bottleneckDelay", "Bottleneck link propagation delay", bottleneckDelay);
    cmd.AddValue("accessBw", "Access link bandwidth", accessBw);
    cmd.AddValue("accessDelayA", "Flow A access link delay (both sender and receiver sides)", accessDelayA);
    cmd.AddValue("accessDelayB", "Flow B access link delay (both sender and receiver sides)", accessDelayB);
    cmd.AddValue("queueDisc", "Queue discipline on bottleneck (FifoQueueDisc, CoDelQueueDisc, RedQueueDisc)", queueDisc);
    cmd.AddValue("queueSize", "Bottleneck queue size (e.g. 100p, 500p, 100000B)", queueSize);
    cmd.AddValue("tcpTypeId", "TCP Congestion Control algorithm (TcpCubic, TcpLinuxReno, TcpBbr, TcpBbrFairtt, TcpBbrEnhancedFairtt, TcpBbrEnhancedFairttV2)", tcpTypeId);
    cmd.AddValue("v2FairnessFloorStrength", "V2 minimum queue-responsive BDP reduction strength", v2FairnessFloorStrength);
    cmd.AddValue("v2FairnessTransition", "V2 normalized RTT-gap transition scale", v2FairnessTransition);
    cmd.AddValue("v2BdpSmoothingTimeMs", "V2 exponential BDP reduction smoothing time in milliseconds", v2BdpSmoothingTimeMs);
    cmd.AddValue("v2MaxInflightBytes", "V2 maximum in-flight and congestion-window target in bytes", v2MaxInflightBytes);
    cmd.AddValue("simTime", "Total simulation time in seconds", simTime);
    cmd.AddValue("flowAStart", "Start time for Flow A in seconds", flowAStart);
    cmd.AddValue("flowAStop", "Stop time for Flow A in seconds", flowAStop);
    cmd.AddValue("flowBStart", "Start time for Flow B in seconds", flowBStart);
    cmd.AddValue("flowBStop", "Stop time for Flow B in seconds", flowBStop);
    cmd.AddValue("samplingInterval", "Interval for periodic metric sampling in seconds", samplingInterval);
    cmd.AddValue("outDir", "Output directory for CSV files and metrics", outDir);
    cmd.AddValue("seed", "Random seed", seed);
    cmd.AddValue("run", "Random run number", run);
    cmd.AddValue("enablePcap", "Enable PCAP generation", enablePcap);
    cmd.AddValue("enableElephantMice", "Add one long-lived elephant plus five staggered finite mice flows; keeps the original baseline available when false", enableElephantMice);
    cmd.Parse(argc, argv);
    g_enableElephantMice = enableElephantMice;

    // Apply random seed and run
    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(run);

    // Ensure output directories exist
    fs::create_directories(outDir);

    // Configure TCP global attributes
    Config::SetDefault("ns3::TcpL4Protocol::SocketType", StringValue("ns3::" + tcpTypeId));
    Config::SetDefault("ns3::TcpBbrEnhancedFairttV2::FairnessFloorStrength",
                       DoubleValue(v2FairnessFloorStrength));
    Config::SetDefault("ns3::TcpBbrEnhancedFairttV2::FairnessTransition",
                       DoubleValue(v2FairnessTransition));
    Config::SetDefault("ns3::TcpBbrEnhancedFairttV2::BdpSmoothingTime",
                       TimeValue(MilliSeconds(v2BdpSmoothingTimeMs)));
    Config::SetDefault("ns3::TcpBbrEnhancedFairttV2::MaxInflightBytes",
                       UintegerValue(v2MaxInflightBytes));
    Config::SetDefault("ns3::TcpSocket::SegmentSize", UintegerValue(1448));
    Config::SetDefault("ns3::TcpSocket::SndBufSize", UintegerValue(4194304)); // 4MB Linux default
    Config::SetDefault("ns3::TcpSocket::RcvBufSize", UintegerValue(6291456)); // 6MB Linux default
    Config::SetDefault("ns3::TcpSocket::InitialCwnd", UintegerValue(10));
    Config::SetDefault("ns3::TcpSocket::DelAckCount", UintegerValue(2));

    // Queue sizing
    Config::SetDefault("ns3::DropTailQueue<Packet>::MaxSize", QueueSizeValue(QueueSize("1p")));
    Config::SetDefault("ns3::" + queueDisc + "::MaxSize", QueueSizeValue(QueueSize(queueSize)));

    // 1. Create Nodes
    // Node index mapping:
    // 0: Sender A, 1: Sender B, 2: Router 1, 3: Router 2, 4: Receiver A, 5: Receiver B
    NodeContainer senders;
    senders.Create(2); // 0: Sender A, 1: Sender B

    NodeContainer routers;
    routers.Create(2); // 0: Router 1 (n2), 1: Router 2 (n3)

    NodeContainer receivers;
    receivers.Create(2); // 0: Receiver A (n4), 1: Receiver B (n5)

    NodeContainer allNodes = NodeContainer(senders, routers, receivers);

    // 2. Configure Point-to-Point Links
    PointToPointHelper bottleneckLink;
    bottleneckLink.SetDeviceAttribute("DataRate", StringValue(bottleneckBw));
    bottleneckLink.SetChannelAttribute("Delay", StringValue(bottleneckDelay));

    PointToPointHelper accessLinkA;
    accessLinkA.SetDeviceAttribute("DataRate", StringValue(accessBw));
    accessLinkA.SetChannelAttribute("Delay", StringValue(accessDelayA));

    PointToPointHelper accessLinkB;
    accessLinkB.SetDeviceAttribute("DataRate", StringValue(accessBw));
    accessLinkB.SetChannelAttribute("Delay", StringValue(accessDelayB));

    // Install NetDevices
    NetDeviceContainer devSenderA_R1 = accessLinkA.Install(senders.Get(0), routers.Get(0));
    NetDeviceContainer devSenderB_R1 = accessLinkB.Install(senders.Get(1), routers.Get(0));
    NetDeviceContainer devR1_R2       = bottleneckLink.Install(routers.Get(0), routers.Get(1));
    NetDeviceContainer devR2_ReceiverA = accessLinkA.Install(routers.Get(1), receivers.Get(0));
    NetDeviceContainer devR2_ReceiverB = accessLinkB.Install(routers.Get(1), receivers.Get(1));

    // 3. Install Internet Stack
    InternetStackHelper internet;
    internet.Install(allNodes);

    // 4. Configure Traffic Control on Bottleneck (Router 1 -> Router 2)
    TrafficControlHelper tch;
    tch.SetRootQueueDisc("ns3::" + queueDisc);
    QueueDiscContainer qdCont = tch.Install(devR1_R2.Get(0));
    g_bottleneckQueue = qdCont.Get(0);

    // 5. Assign IP Addresses
    Ipv4AddressHelper ipv4;

    ipv4.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifSenderA_R1 = ipv4.Assign(devSenderA_R1);

    ipv4.SetBase("10.1.2.0", "255.255.255.0");
    Ipv4InterfaceContainer ifSenderB_R1 = ipv4.Assign(devSenderB_R1);

    ipv4.SetBase("10.2.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR1_R2 = ipv4.Assign(devR1_R2);

    ipv4.SetBase("10.3.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR2_ReceiverA = ipv4.Assign(devR2_ReceiverA);

    ipv4.SetBase("10.3.2.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR2_ReceiverB = ipv4.Assign(devR2_ReceiverB);

    // Global static routing
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // 6. Install Applications
    uint16_t portA = 50001;
    uint16_t portB = 50002;

    // Sinks on receivers
    PacketSinkHelper sinkHelperA("ns3::TcpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), portA));
    ApplicationContainer sinkAppA = sinkHelperA.Install(receivers.Get(0));
    sinkAppA.Start(Seconds(0.0));
    sinkAppA.Stop(Seconds(simTime));
    g_sinkA = DynamicCast<PacketSink>(sinkAppA.Get(0));

    PacketSinkHelper sinkHelperB("ns3::TcpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), portB));
    ApplicationContainer sinkAppB = sinkHelperB.Install(receivers.Get(1));
    sinkAppB.Start(Seconds(0.0));
    sinkAppB.Stop(Seconds(simTime));
    g_sinkB = DynamicCast<PacketSink>(sinkAppB.Get(0));

    // BulkSend application on Sender A -> Receiver A
    Address sinkAddressA(InetSocketAddress(ifR2_ReceiverA.GetAddress(1), portA));
    BulkSendHelper sourceA("ns3::TcpSocketFactory", sinkAddressA);
    sourceA.SetAttribute("MaxBytes", UintegerValue(0)); // Continuous greedy transmission
    ApplicationContainer sourceAppA = sourceA.Install(senders.Get(0));
    sourceAppA.Start(Seconds(flowAStart));
    sourceAppA.Stop(Seconds(flowAStop));

    // Existing Flow B remains unchanged in baseline mode. In elephant-mice
    // mode, Flow A is the elephant and Flow B is replaced by five finite mice
    // transfers with staggered arrivals, so new mice arrive while the elephant
    // is still active.
    if (!enableElephantMice)
    {
        Address sinkAddressB(InetSocketAddress(ifR2_ReceiverB.GetAddress(1), portB));
        BulkSendHelper sourceB("ns3::TcpSocketFactory", sinkAddressB);
        sourceB.SetAttribute("MaxBytes", UintegerValue(0)); // Existing continuous Flow B
        ApplicationContainer sourceAppB = sourceB.Install(senders.Get(1));
        sourceAppB.Start(Seconds(flowBStart));
        sourceAppB.Stop(Seconds(flowBStop));
    }
    else
    {
        // Mice start at 4, 8, 12, 16, and 20 seconds; each has a finite
        // transfer size. They share the same bottleneck with the elephant.
        const double miceStarts[] = {4.0, 8.0, 12.0, 16.0, 20.0};
        const uint64_t miceBytes[] = {50 * 1024, 100 * 1024, 75 * 1024,
                                      150 * 1024, 100 * 1024};
        for (uint32_t i = 0; i < 5; ++i)
        {
            uint16_t micePort = static_cast<uint16_t>(50100 + i);
            PacketSinkHelper miceSinkHelper(
                "ns3::TcpSocketFactory",
                InetSocketAddress(Ipv4Address::GetAny(), micePort));
            ApplicationContainer miceSinkApp = miceSinkHelper.Install(receivers.Get(1));
            miceSinkApp.Start(Seconds(0.0));
            miceSinkApp.Stop(Seconds(simTime));

            Address miceAddress(InetSocketAddress(ifR2_ReceiverB.GetAddress(1), micePort));
            BulkSendHelper miceSource("ns3::TcpSocketFactory", miceAddress);
            miceSource.SetAttribute("MaxBytes", UintegerValue(miceBytes[i]));
            ApplicationContainer miceSourceApp = miceSource.Install(senders.Get(1));
            miceSourceApp.Start(Seconds(miceStarts[i]));
            miceSourceApp.Stop(Seconds(flowBStop));

            MiceFlowRecord record;
            record.port = micePort;
            record.startTime = miceStarts[i];
            record.stopTime = flowBStop;
            record.maxBytes = miceBytes[i];
            record.sink = DynamicCast<PacketSink>(miceSinkApp.Get(0));
            g_miceFlows.push_back(record);
        }
    }

    // Hook socket traces after applications start

Simulator::Schedule(Seconds(flowAStart) + MilliSeconds(10),
                    &ConnectSocketTraces, 0, "FlowA");

if (!enableElephantMice)
{
    Simulator::Schedule(Seconds(flowBStart) + MilliSeconds(10),
                        &ConnectSocketTraces, 1, "FlowB");
}

if (tcpTypeId == "TcpBbrEnhancedFairttV2")
{
    Simulator::Schedule(Seconds(flowAStart) + MilliSeconds(10),
                        &ConnectV2ControllerTraces, 0, 0, "FlowA");
    if (!enableElephantMice)
    {
        Simulator::Schedule(Seconds(flowBStart) + MilliSeconds(10),
                            &ConnectV2ControllerTraces, 1, 0, "FlowB");
    }
    else
    {
        const double miceStarts[] = {4.0, 8.0, 12.0, 16.0, 20.0};
        for (uint32_t i = 0; i < 5; ++i)
        {
            Simulator::Schedule(
                Seconds(miceStarts[i]) + MilliSeconds(10),
                &ConnectV2ControllerTraces,
                1,
                i,
                "mice_" + std::to_string(50100 + i));
        }
    }
}


    // Optional PCAP tracing
    if (enablePcap)
    {
        fs::create_directories(outDir + "/pcap");
        bottleneckLink.EnablePcap(outDir + "/pcap/bottleneck", devR1_R2, true);
    }

    // 7. Open Output Files and Write Headers
    g_throughputStream.open(outDir + "/throughput.csv");
    g_throughputStream << "time,flowA_mbps,flowB_mbps,aggregate_mbps,fairness_index\n";

    if (enableElephantMice)
    {
        g_miceStream.open(outDir + "/elephant_mice_throughput.csv");
        g_miceStream << "time,flow,throughput_mbps,cumulative_rx_bytes\n";
    }

    g_queueStream.open(outDir + "/queue_occupancy.csv");
    g_queueStream << "time,queue_packets,queue_bytes\n";

    g_rttStream.open(outDir + "/rtt.csv");
    g_rttStream << "time,flow,rtt_ms\n";

    g_cwndStream.open(outDir + "/cwnd.csv");
    g_cwndStream << "time,flow,cwnd_packets\n";

    if (tcpTypeId == "TcpBbrEnhancedFairttV2")
    {
        g_v2ControlStream.open(outDir + "/v2_controller.csv");
        g_v2ControlStream << "time,flow,trace,old_value,new_value\n";
    }

    // 8. Schedule Periodic Metric Sampler
    Time interval = Seconds(samplingInterval);
    Simulator::Schedule(interval, &SampleMetrics, interval);

    // 9. Install FlowMonitor for End-of-Run Stats
    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> flowmon = flowmonHelper.InstallAll();

    // 10. Run Simulation
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    // 11. Process FlowMonitor Statistics
    flowmon->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier = DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());
    std::map<FlowId, FlowMonitor::FlowStats> stats = flowmon->GetFlowStats();

    // Use application bytes received at the sinks for throughput calculations.
    // The sinks remain active until simTime, so include the drain period after
    // the sender applications stop. FlowMonitor rxBytes is IP-layer bytes and
    // should not be mixed with PacketSink application-layer byte counts.
    double totalFlowABytes = g_sinkA ? static_cast<double>(g_sinkA->GetTotalRx()) : 0.0;
    double totalFlowBBytes = g_sinkB ? static_cast<double>(g_sinkB->GetTotalRx()) : 0.0;
    double flowADuration = (simTime > flowAStart) ? (simTime - flowAStart) : 1.0;
    double flowBDuration = (simTime > flowBStart) ? (simTime - flowBStart) : 1.0;
    uint32_t lostA = 0;
    uint32_t lostB = 0;
    uint32_t txPacketsA = 0;
    uint32_t txPacketsB = 0;
    uint32_t rxPacketsA = 0;
    uint32_t rxPacketsB = 0;
    double meanDelayA_ms = 0.0;
    double meanDelayB_ms = 0.0;

    for (const auto& entry : stats)
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(entry.first);
        // Identify forward flows by destination port
        if (t.destinationPort == portA)
        {
            lostA += entry.second.lostPackets;
            txPacketsA += entry.second.txPackets;
            rxPacketsA += entry.second.rxPackets;
            if (entry.second.rxPackets > 0)
            {
                meanDelayA_ms = (entry.second.delaySum.GetMilliSeconds() / entry.second.rxPackets);
            }
        }
        else if (t.destinationPort == portB)
        {
            lostB += entry.second.lostPackets;
            txPacketsB += entry.second.txPackets;
            rxPacketsB += entry.second.rxPackets;
            if (entry.second.rxPackets > 0)
            {
                meanDelayB_ms = (entry.second.delaySum.GetMilliSeconds() / entry.second.rxPackets);
            }
        }
    }

    double avgThroughputA = (totalFlowABytes * 8.0) / (flowADuration * 1e6);
    double avgThroughputB = (totalFlowBBytes * 8.0) / (flowBDuration * 1e6);
    double avgAggregate = avgThroughputA + avgThroughputB;
    double overallJainIndex = CalculateJainsIndex(avgThroughputA, avgThroughputB);

    // Save summary text report
    std::ofstream summaryStream(outDir + "/summary.txt");
    summaryStream << "========================================================\n"
                  << "Enhanced FaiRTT - Stage 1 Dumbbell Baseline Simulation\n"
                  << "========================================================\n"
                  << "Congestion Control: " << tcpTypeId << "\n"
                  << "Traffic Scenario: " << (enableElephantMice ? "one elephant + five staggered mice" : "original two long-lived flows") << "\n"
                  << "Bottleneck: " << bottleneckBw << ", " << bottleneckDelay << "\n"
                  << "Access Link: " << accessBw << "\n"
                  << "Flow A Delay: " << accessDelayA << " (Base RTT approx)\n"
                  << "Flow B Delay: " << accessDelayB << " (Base RTT approx)\n"
                  << "Queue Disc: " << queueDisc << " (" << queueSize << ")\n"
                  << "Simulation Time: " << simTime << " s\n"
                  << "RNG Seed / Run: " << seed << " / " << run << "\n"
                  << "V2 Fairness Settings: floor=" << v2FairnessFloorStrength
                  << ", transition=" << v2FairnessTransition
                  << ", smoothing=" << v2BdpSmoothingTimeMs << " ms"
                  << ", max inflight=" << v2MaxInflightBytes << " bytes\n"
                  << "--------------------------------------------------------\n"
                  << "Flow A (Port " << portA << "):\n"
                  << "  Rx Bytes:       " << totalFlowABytes << " bytes\n"
                  << "  Avg Throughput: " << std::fixed << std::setprecision(3) << avgThroughputA << " Mbps\n"
                  << "  Tx / Rx Pkts:   " << txPacketsA << " / " << rxPacketsA << "\n"
                  << "  Lost Packets:   " << lostA << "\n"
                  << "  Mean Delay:     " << meanDelayA_ms << " ms\n"
                  << (enableElephantMice ? "Flow B (disabled; mice use separate ports):\n" : "Flow B (Port " + std::to_string(portB) + "):\n")
                  << "  Rx Bytes:       " << totalFlowBBytes << " bytes\n"
                  << "  Avg Throughput: " << std::fixed << std::setprecision(3) << avgThroughputB << " Mbps\n"
                  << "  Tx / Rx Pkts:   " << txPacketsB << " / " << rxPacketsB << "\n"
                  << "  Lost Packets:   " << lostB << "\n"
                  << "  Mean Delay:     " << meanDelayB_ms << " ms\n"
                  << "--------------------------------------------------------\n";
    if (enableElephantMice)
    {
        summaryStream << "Elephant + Mice Flow Results (application bytes received):\n";
        summaryStream << "  Elephant (Flow A): " << totalFlowABytes << " bytes; "
                      << avgThroughputA << " Mbps average from elephant start to simulation end\n";
        for (const auto &mice : g_miceFlows)
        {
            uint64_t rxBytes = mice.sink ? mice.sink->GetTotalRx() : 0;
            double activeDuration = std::max(0.001, simTime - mice.startTime);
            double avgMbps = (rxBytes * 8.0) / (activeDuration * 1e6);
            summaryStream << "  Mice port " << mice.port << ": " << rxBytes
                          << " bytes received; " << avgMbps
                          << " Mbps average from arrival to simulation end; configured size "
                          << mice.maxBytes << " bytes; arrival " << mice.startTime << " s\n";
        }
        summaryStream << "  Per-sample throughput is in elephant_mice_throughput.csv\n";
    }
    summaryStream << "Aggregate Throughput (Flow A + legacy Flow B counters): " << avgAggregate << " Mbps\n"
                  << "Overall Jain's Fairness Index (legacy A/B counters): " << std::setprecision(4) << overallJainIndex << "\n"
                  << "========================================================\n";
    summaryStream.close();

    // Save summary json
    std::ofstream jsonStream(outDir + "/summary.json");
    jsonStream << "{\n"
               << "  \"tcpTypeId\": \"" << tcpTypeId << "\",\n"
               << "  \"trafficScenario\": \"" << (enableElephantMice ? "elephant_mice" : "two_long_lived_flows") << "\",\n"
               << "  \"bottleneckBw\": \"" << bottleneckBw << "\",\n"
               << "  \"bottleneckDelay\": \"" << bottleneckDelay << "\",\n"
               << "  \"accessDelayA\": \"" << accessDelayA << "\",\n"
               << "  \"accessDelayB\": \"" << accessDelayB << "\",\n"
               << "  \"rngSeed\": " << seed << ",\n"
               << "  \"rngRun\": " << run << ",\n"
               << "  \"v2FairnessFloorStrength\": " << v2FairnessFloorStrength << ",\n"
               << "  \"v2FairnessTransition\": " << v2FairnessTransition << ",\n"
               << "  \"v2BdpSmoothingTimeMs\": " << v2BdpSmoothingTimeMs << ",\n"
               << "  \"v2MaxInflightBytes\": " << v2MaxInflightBytes << ",\n"
               << "  \"flowA_avg_mbps\": " << avgThroughputA << ",\n"
               << "  \"flowB_avg_mbps\": " << avgThroughputB << ",\n"
               << "  \"aggregate_mbps\": " << avgAggregate << ",\n"
               << "  \"jains_fairness_index\": " << overallJainIndex << ",\n"
               << "  \"flowA_rx_bytes\": " << totalFlowABytes << ",\n"
               << "  \"flowB_rx_bytes\": " << totalFlowBBytes << ",\n"
               << "  \"flowA_lost_packets\": " << lostA << ",\n"
               << "  \"flowB_lost_packets\": " << lostB << ",\n"
               << "  \"flowA_mean_delay_ms\": " << meanDelayA_ms << ",\n"
               << "  \"flowB_mean_delay_ms\": " << meanDelayB_ms << "\n"
               << "}\n";
    jsonStream.close();

    // Close all streams and clean up
    g_throughputStream.close();
    g_queueStream.close();
    g_rttStream.close();
    g_cwndStream.close();
    if (g_miceStream.is_open()) g_miceStream.close();

    Simulator::Destroy();

    std::cout << "[DONE] Simulation complete. Results written to: " << outDir << std::endl;
    std::cout << "  Flow A Throughput: " << avgThroughputA << " Mbps" << std::endl;
    std::cout << "  Flow B Throughput: " << avgThroughputB << " Mbps" << std::endl;
    std::cout << "  Aggregate Throughput: " << avgAggregate << " Mbps" << std::endl;
    std::cout << "  Jain's Fairness Index: " << overallJainIndex << std::endl;

    return 0;
}
