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

// Tracking state for periodic throughput calculation
static uint64_t g_lastRxBytesA = 0;
static uint64_t g_lastRxBytesB = 0;
static Time g_lastSampleTime = Seconds(0);

// Pointers to sink applications
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
};

static std::vector<MiceFlowRecord> g_miceFlows;
static std::ofstream g_miceStream;
static bool g_enableElephantMice = false;

/**
 * Jain's Fairness Index for two flows.
 */
static double
CalculateJainsIndex(double throughputA, double throughputB)
{
    double sum = throughputA + throughputB;

    if (sum <= 0.0)
    {
        return 1.0;
    }

    double sumSq =
        (throughputA * throughputA) +
        (throughputB * throughputB);

    if (sumSq <= 0.0)
    {
        return 1.0;
    }

    return (sum * sum) / (2.0 * sumSq);
}

/**
 * Jain's Fairness Index for any number of flows.
 */
static double
CalculateJainsIndex(const std::vector<double>& throughputs)
{
    if (throughputs.empty())
    {
        return 1.0;
    }

    double sum = 0.0;
    double sumSq = 0.0;

    for (double throughput : throughputs)
    {
        sum += throughput;
        sumSq += throughput * throughput;
    }

    if (sumSq <= 0.0)
    {
        return 1.0;
    }

    return (sum * sum) /
           (throughputs.size() * sumSq);
}

/**
 * Periodic sampler for throughput, Jain's fairness index,
 * queue occupancy, and individual elephant/mice throughput.
 */
static void
SampleMetrics(Time interval)
{
    Time now = Simulator::Now();
    double timeSec = now.GetSeconds();
    double dtSec = (now - g_lastSampleTime).GetSeconds();

    if (dtSec > 0.0)
    {
        uint64_t curRxBytesA =
            g_sinkA ? g_sinkA->GetTotalRx() : 0;

        uint64_t curRxBytesB =
            g_sinkB ? g_sinkB->GetTotalRx() : 0;

        uint64_t dBytesA =
            (curRxBytesA >= g_lastRxBytesA)
                ? curRxBytesA - g_lastRxBytesA
                : 0;

        uint64_t dBytesB =
            (curRxBytesB >= g_lastRxBytesB)
                ? curRxBytesB - g_lastRxBytesB
                : 0;

        double mbpsA =
            (dBytesA * 8.0) / (dtSec * 1e6);

        double mbpsB =
            (dBytesB * 8.0) / (dtSec * 1e6);

        double aggregateMbps = mbpsA + mbpsB;
        double jainIndex =
            CalculateJainsIndex(mbpsA, mbpsB);

        g_throughputStream
            << std::fixed << std::setprecision(4)
            << timeSec << ","
            << mbpsA << ","
            << mbpsB << ","
            << aggregateMbps << ","
            << jainIndex << "\n";

        // In elephant-mice mode, record each flow separately.
        if (g_enableElephantMice && g_miceStream.is_open())
        {
            g_miceStream
                << std::fixed << std::setprecision(4)
                << timeSec << ",elephant,"
                << (dBytesA * 8.0 / (dtSec * 1e6))
                << "," << curRxBytesA << "\n";

            for (auto& mice : g_miceFlows)
            {
                uint64_t current =
                    mice.sink ? mice.sink->GetTotalRx() : 0;

                uint64_t delta =
                    current >= mice.lastRxBytes
                        ? current - mice.lastRxBytes
                        : 0;

                double mbps =
                    (delta * 8.0) / (dtSec * 1e6);

                g_miceStream
                    << std::fixed << std::setprecision(4)
                    << timeSec << ",mice_" << mice.port << ","
                    << mbps << ","
                    << current << "\n";

                mice.lastRxBytes = current;
            }
        }

        g_lastRxBytesA = curRxBytesA;
        g_lastRxBytesB = curRxBytesB;
        g_lastSampleTime = now;
    }

    if (g_bottleneckQueue)
    {
        uint32_t qPackets =
            g_bottleneckQueue->GetNPackets();

        uint32_t qBytes =
            g_bottleneckQueue->GetNBytes();

        g_queueStream
            << std::fixed << std::setprecision(4)
            << timeSec << ","
            << qPackets << ","
            << qBytes << "\n";
    }

    Simulator::Schedule(
        interval, &SampleMetrics, interval);
}

/**
 * Trace RTT updates for a flow.
 */
static void
RttTracer(std::string flowName, Time oldVal, Time newVal)
{
    g_rttStream
        << std::fixed << std::setprecision(4)
        << Simulator::Now().GetSeconds() << ","
        << flowName << ","
        << newVal.GetMilliSeconds() << "\n";
}

/**
 * Trace congestion-window updates for a flow.
 */
static void
CwndTracer(std::string flowName,
           uint32_t oldVal,
           uint32_t newVal)
{
    g_cwndStream
        << std::fixed << std::setprecision(4)
        << Simulator::Now().GetSeconds() << ","
        << flowName << ","
        << (newVal / 1448.0) << "\n";
}

/**
 * Hook trace sources to a sender node's TCP sockets.
 */
static void
ConnectSocketTraces(uint32_t nodeId, std::string flowName)
{
    std::string pathPrefix =
        "/NodeList/" + std::to_string(nodeId) +
        "/$ns3::TcpL4Protocol/SocketList/*/";

    Config::ConnectWithoutContext(
        pathPrefix + "RTT",
        MakeBoundCallback(&RttTracer, flowName));

    Config::ConnectWithoutContext(
        pathPrefix + "CongestionWindow",
        MakeBoundCallback(&CwndTracer, flowName));
}

int
main(int argc, char* argv[])
{
    // Simulation parameters
    std::string bottleneckBw = "10Mbps";
    std::string bottleneckDelay = "10ms";
    std::string accessBw = "100Mbps";
    std::string accessDelayA = "5ms";
    std::string accessDelayB = "5ms";
    std::string queueDisc = "FifoQueueDisc";
    std::string queueSize = "100p";
    std::string tcpTypeId = "TcpCubic";

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

    cmd.AddValue("bottleneckBw", "Bottleneck link bandwidth",
                 bottleneckBw);
    cmd.AddValue("bottleneckDelay", "Bottleneck link propagation delay",
                 bottleneckDelay);
    cmd.AddValue("accessBw", "Access link bandwidth", accessBw);
    cmd.AddValue("accessDelayA",
                 "Flow A access link delay (sender and receiver)",
                 accessDelayA);
    cmd.AddValue("accessDelayB",
                 "Flow B access link delay (sender and receiver)",
                 accessDelayB);
    cmd.AddValue("queueDisc",
                 "Bottleneck queue discipline",
                 queueDisc);
    cmd.AddValue("queueSize",
                 "Bottleneck queue size",
                 queueSize);
    cmd.AddValue("tcpTypeId",
                 "TCP congestion control algorithm",
                 tcpTypeId);
    cmd.AddValue("simTime", "Total simulation time", simTime);
    cmd.AddValue("flowAStart", "Flow A start time", flowAStart);
    cmd.AddValue("flowAStop", "Flow A stop time", flowAStop);
    cmd.AddValue("flowBStart", "Flow B start time", flowBStart);
    cmd.AddValue("flowBStop", "Flow B stop time", flowBStop);
    cmd.AddValue("samplingInterval",
                 "Metric sampling interval",
                 samplingInterval);
    cmd.AddValue("outDir", "Output directory", outDir);
    cmd.AddValue("seed", "Random seed", seed);
    cmd.AddValue("run", "Random run number", run);
    cmd.AddValue("enablePcap", "Enable PCAP generation", enablePcap);
    cmd.AddValue("enableElephantMice",
                 "Enable one elephant and five staggered mice flows",
                 enableElephantMice);

    cmd.Parse(argc, argv);

    g_enableElephantMice = enableElephantMice;

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(run);

    fs::create_directories(outDir);

    // Configure TCP attributes
    Config::SetDefault(
        "ns3::TcpL4Protocol::SocketType",
        StringValue("ns3::" + tcpTypeId));

    Config::SetDefault(
        "ns3::TcpSocket::SegmentSize",
        UintegerValue(1448));

    Config::SetDefault(
        "ns3::TcpSocket::SndBufSize",
        UintegerValue(4194304));

    Config::SetDefault(
        "ns3::TcpSocket::RcvBufSize",
        UintegerValue(6291456));

    Config::SetDefault(
        "ns3::TcpSocket::InitialCwnd",
        UintegerValue(10));

    Config::SetDefault(
        "ns3::TcpSocket::DelAckCount",
        UintegerValue(2));

    // Queue sizing
    Config::SetDefault(
        "ns3::DropTailQueue<Packet>::MaxSize",
        QueueSizeValue(QueueSize("1p")));

    Config::SetDefault(
        "ns3::" + queueDisc + "::MaxSize",
        QueueSizeValue(QueueSize(queueSize)));

    // 1. Create nodes
    NodeContainer senders;
    senders.Create(2);

    NodeContainer routers;
    routers.Create(2);

    NodeContainer receivers;
    receivers.Create(2);

    NodeContainer allNodes =
        NodeContainer(senders, routers, receivers);

    // 2. Configure point-to-point links
    PointToPointHelper bottleneckLink;
    bottleneckLink.SetDeviceAttribute(
        "DataRate", StringValue(bottleneckBw));
    bottleneckLink.SetChannelAttribute(
        "Delay", StringValue(bottleneckDelay));

    PointToPointHelper accessLinkA;
    accessLinkA.SetDeviceAttribute(
        "DataRate", StringValue(accessBw));
    accessLinkA.SetChannelAttribute(
        "Delay", StringValue(accessDelayA));

    PointToPointHelper accessLinkB;
    accessLinkB.SetDeviceAttribute(
        "DataRate", StringValue(accessBw));
    accessLinkB.SetChannelAttribute(
        "Delay", StringValue(accessDelayB));

    NetDeviceContainer devSenderA_R1 =
        accessLinkA.Install(senders.Get(0), routers.Get(0));

    NetDeviceContainer devSenderB_R1 =
        accessLinkB.Install(senders.Get(1), routers.Get(0));

    NetDeviceContainer devR1_R2 =
        bottleneckLink.Install(routers.Get(0), routers.Get(1));

    NetDeviceContainer devR2_ReceiverA =
        accessLinkA.Install(routers.Get(1), receivers.Get(0));

    NetDeviceContainer devR2_ReceiverB =
        accessLinkB.Install(routers.Get(1), receivers.Get(1));

    // 3. Install Internet stack
    InternetStackHelper internet;
    internet.Install(allNodes);

    // 4. Configure traffic control on the bottleneck
    TrafficControlHelper tch;
    tch.SetRootQueueDisc("ns3::" + queueDisc);

    QueueDiscContainer qdCont =
        tch.Install(devR1_R2.Get(0));

    g_bottleneckQueue = qdCont.Get(0);

    // 5. Assign IP addresses
    Ipv4AddressHelper ipv4;

    ipv4.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifSenderA_R1 =
        ipv4.Assign(devSenderA_R1);

    ipv4.SetBase("10.1.2.0", "255.255.255.0");
    Ipv4InterfaceContainer ifSenderB_R1 =
        ipv4.Assign(devSenderB_R1);

    ipv4.SetBase("10.2.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR1_R2 =
        ipv4.Assign(devR1_R2);

    ipv4.SetBase("10.3.1.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR2_ReceiverA =
        ipv4.Assign(devR2_ReceiverA);

    ipv4.SetBase("10.3.2.0", "255.255.255.0");
    Ipv4InterfaceContainer ifR2_ReceiverB =
        ipv4.Assign(devR2_ReceiverB);

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // 6. Install applications
    uint16_t portA = 50001;
    uint16_t portB = 50002;

    // Flow A sink
    PacketSinkHelper sinkHelperA(
        "ns3::TcpSocketFactory",
        InetSocketAddress(Ipv4Address::GetAny(), portA));

    ApplicationContainer sinkAppA =
        sinkHelperA.Install(receivers.Get(0));

    sinkAppA.Start(Seconds(0.0));
    sinkAppA.Stop(Seconds(simTime));

    g_sinkA =
        DynamicCast<PacketSink>(sinkAppA.Get(0));

    // Legacy Flow B sink remains available for baseline mode.
    PacketSinkHelper sinkHelperB(
        "ns3::TcpSocketFactory",
        InetSocketAddress(Ipv4Address::GetAny(), portB));

    ApplicationContainer sinkAppB =
        sinkHelperB.Install(receivers.Get(1));

    sinkAppB.Start(Seconds(0.0));
    sinkAppB.Stop(Seconds(simTime));

    g_sinkB =
        DynamicCast<PacketSink>(sinkAppB.Get(0));

    // Flow A: continuous elephant
    Address sinkAddressA(
        InetSocketAddress(ifR2_ReceiverA.GetAddress(1), portA));

    BulkSendHelper sourceA(
        "ns3::TcpSocketFactory", sinkAddressA);

    sourceA.SetAttribute("MaxBytes", UintegerValue(0));

    ApplicationContainer sourceAppA =
        sourceA.Install(senders.Get(0));

    sourceAppA.Start(Seconds(flowAStart));
    sourceAppA.Stop(Seconds(flowAStop));

    // Flow B remains unchanged in baseline mode.
    // In elephant-mice mode, it is replaced by finite mice transfers.
    if (!enableElephantMice)
    {
        Address sinkAddressB(
            InetSocketAddress(ifR2_ReceiverB.GetAddress(1), portB));

        BulkSendHelper sourceB(
            "ns3::TcpSocketFactory", sinkAddressB);

        sourceB.SetAttribute("MaxBytes", UintegerValue(0));

        ApplicationContainer sourceAppB =
            sourceB.Install(senders.Get(1));

        sourceAppB.Start(Seconds(flowBStart));
        sourceAppB.Stop(Seconds(flowBStop));
    }
    else
    {
        const double miceStarts[] =
            {4.0, 8.0, 12.0, 16.0, 20.0};

        const uint64_t miceBytes[] =
            {50 * 1024, 100 * 1024, 75 * 1024,
             150 * 1024, 100 * 1024};

        for (uint32_t i = 0; i < 5; ++i)
        {
            uint16_t micePort =
                static_cast<uint16_t>(50100 + i);

            PacketSinkHelper miceSinkHelper(
                "ns3::TcpSocketFactory",
                InetSocketAddress(
                    Ipv4Address::GetAny(), micePort));

            ApplicationContainer miceSinkApp =
                miceSinkHelper.Install(receivers.Get(1));

            miceSinkApp.Start(Seconds(0.0));
            miceSinkApp.Stop(Seconds(simTime));

            Address miceAddress(
                InetSocketAddress(
                    ifR2_ReceiverB.GetAddress(1), micePort));

            BulkSendHelper miceSource(
                "ns3::TcpSocketFactory", miceAddress);

            miceSource.SetAttribute(
                "MaxBytes", UintegerValue(miceBytes[i]));

            ApplicationContainer miceSourceApp =
                miceSource.Install(senders.Get(1));

            miceSourceApp.Start(Seconds(miceStarts[i]));
            miceSourceApp.Stop(Seconds(flowBStop));

            MiceFlowRecord record;
            record.port = micePort;
            record.startTime = miceStarts[i];
            record.stopTime = flowBStop;
            record.maxBytes = miceBytes[i];
            record.sink =
                DynamicCast<PacketSink>(miceSinkApp.Get(0));

            g_miceFlows.push_back(record);
        }
    }

    // Hook socket traces after applications start.
    Simulator::Schedule(
        Seconds(flowAStart) + MilliSeconds(10),
        &ConnectSocketTraces, 0, "FlowA");

    // Do not attempt to hook a nonexistent legacy Flow B sender
    // in elephant-mice mode.
    if (!enableElephantMice)
    {
        Simulator::Schedule(
            Seconds(flowBStart) + MilliSeconds(10),
            &ConnectSocketTraces, 1, "FlowB");
    }

    // Optional PCAP tracing
    if (enablePcap)
    {
        fs::create_directories(outDir + "/pcap");
        bottleneckLink.EnablePcap(
            outDir + "/pcap/bottleneck", devR1_R2, true);
    }

    // 7. Open output files and write headers
    g_throughputStream.open(outDir + "/throughput.csv");
    g_throughputStream
        << "time,flowA_mbps,flowB_mbps,aggregate_mbps,fairness_index\n";

    g_queueStream.open(outDir + "/queue_occupancy.csv");
    g_queueStream << "time,queue_packets,queue_bytes\n";

    g_rttStream.open(outDir + "/rtt.csv");
    g_rttStream << "time,flow,rtt_ms\n";

    g_cwndStream.open(outDir + "/cwnd.csv");
    g_cwndStream << "time,flow,cwnd_packets\n";

    // FIX: Open the per-flow elephant/mice CSV before sampling begins.
    if (enableElephantMice)
    {
        g_miceStream.open(
            outDir + "/elephant_mice_throughput.csv");

        g_miceStream
            << "time,flow,throughput_mbps,cumulative_rx_bytes\n";
    }

    // 8. Schedule periodic metric sampling
    Time interval = Seconds(samplingInterval);

    Simulator::Schedule(
        interval, &SampleMetrics, interval);

    // 9. Install FlowMonitor for end-of-run statistics
    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> flowmon =
        flowmonHelper.InstallAll();

    // 10. Run simulation
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    // 11. Process FlowMonitor statistics
    flowmon->CheckForLostPackets();

    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(
            flowmonHelper.GetClassifier());

    std::map<FlowId, FlowMonitor::FlowStats> stats =
        flowmon->GetFlowStats();

    // Use application bytes received at the sinks.
    double totalFlowABytes =
        g_sinkA
            ? static_cast<double>(g_sinkA->GetTotalRx())
            : 0.0;

    double totalFlowBBytes =
        g_sinkB
            ? static_cast<double>(g_sinkB->GetTotalRx())
            : 0.0;

    double flowADuration =
        (simTime > flowAStart)
            ? simTime - flowAStart
            : 1.0;

    double flowBDuration =
        (simTime > flowBStart)
            ? simTime - flowBStart
            : 1.0;

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
        Ipv4FlowClassifier::FiveTuple t =
            classifier->FindFlow(entry.first);

        if (t.destinationPort == portA)
        {
            lostA += entry.second.lostPackets;
            txPacketsA += entry.second.txPackets;
            rxPacketsA += entry.second.rxPackets;

            if (entry.second.rxPackets > 0)
            {
                meanDelayA_ms =
                    entry.second.delaySum.GetMilliSeconds() /
                    entry.second.rxPackets;
            }
        }
        else if (t.destinationPort == portB)
        {
            lostB += entry.second.lostPackets;
            txPacketsB += entry.second.txPackets;
            rxPacketsB += entry.second.rxPackets;

            if (entry.second.rxPackets > 0)
            {
                meanDelayB_ms =
                    entry.second.delaySum.GetMilliSeconds() /
                    entry.second.rxPackets;
            }
        }
    }

    double avgThroughputA =
        (totalFlowABytes * 8.0) /
        (flowADuration * 1e6);

    double avgThroughputB =
        (totalFlowBBytes * 8.0) /
        (flowBDuration * 1e6);

    double avgAggregate =
        avgThroughputA + avgThroughputB;

    double overallJainIndex =
        CalculateJainsIndex(
            avgThroughputA, avgThroughputB);

    // In elephant-mice mode, calculate aggregate throughput and
    // Jain's index for all six flows over the same time window.
    if (enableElephantMice)
    {
        std::vector<double> elephantMiceThroughputs;

        elephantMiceThroughputs.push_back(avgThroughputA);

        avgAggregate = avgThroughputA;

        for (const auto& mice : g_miceFlows)
        {
            double rxBytes =
                mice.sink
                    ? static_cast<double>(
                          mice.sink->GetTotalRx())
                    : 0.0;

            // Use the same common window as the elephant.
            double miceAvgMbps =
                (rxBytes * 8.0) /
                (flowADuration * 1e6);

            elephantMiceThroughputs.push_back(
                miceAvgMbps);

            avgAggregate += miceAvgMbps;
        }

        overallJainIndex =
            CalculateJainsIndex(
                elephantMiceThroughputs);
    }

    // Save summary text report
    std::ofstream summaryStream(
        outDir + "/summary.txt");

    summaryStream
        << "========================================================\n"
        << "Enhanced FaiRTT - Stage 1 Dumbbell Baseline Simulation\n"
        << "========================================================\n"
        << "Congestion Control: " << tcpTypeId << "\n"
        << "Traffic Scenario: "
        << (enableElephantMice
                ? "one elephant + five staggered mice"
                : "original two long-lived flows")
        << "\n"
        << "Bottleneck: " << bottleneckBw
        << ", " << bottleneckDelay << "\n"
        << "Access Link: " << accessBw << "\n"
        << "Flow A Delay: " << accessDelayA
        << " (Base RTT approx)\n"
        << "Flow B Delay: " << accessDelayB
        << " (Base RTT approx)\n"
        << "Queue Disc: " << queueDisc
        << " (" << queueSize << ")\n"
        << "Simulation Time: " << simTime << " s\n"
        << "--------------------------------------------------------\n"
        << "Flow A (Port " << portA << "):\n"
        << "  Rx Bytes:       " << totalFlowABytes << " bytes\n"
        << "  Avg Throughput: "
        << std::fixed << std::setprecision(3)
        << avgThroughputA << " Mbps\n"
        << "  Tx / Rx Pkts:   "
        << txPacketsA << " / " << rxPacketsA << "\n"
        << "  Lost Packets:   " << lostA << "\n"
        << "  Mean Delay:     " << meanDelayA_ms << " ms\n"
        << (enableElephantMice
                ? "Flow B (disabled; mice use separate ports):\n"
                : "Flow B (Port " +
                      std::to_string(portB) + "):\n")
        << "  Rx Bytes:       " << totalFlowBBytes << " bytes\n"
        << "  Avg Throughput: " << avgThroughputB << " Mbps\n"
        << "  Tx / Rx Pkts:   "
        << txPacketsB << " / " << rxPacketsB << "\n"
        << "  Lost Packets:   " << lostB << "\n"
        << "  Mean Delay:     " << meanDelayB_ms << " ms\n"
        << "--------------------------------------------------------\n";

    if (enableElephantMice)
    {
        summaryStream
            << "Elephant + Mice Flow Results (application bytes received):\n";

        summaryStream
            << "  Elephant (Flow A): "
            << totalFlowABytes << " bytes; "
            << avgThroughputA
            << " Mbps average over the common measurement window\n";

        for (const auto& mice : g_miceFlows)
        {
            uint64_t rxBytes =
                mice.sink
                    ? mice.sink->GetTotalRx()
                    : 0;

            double activeDuration =
                std::max(0.001, simTime - mice.startTime);

            double avgMbps =
                (rxBytes * 8.0) /
                (activeDuration * 1e6);

            summaryStream
                << "  Mice port " << mice.port
                << ": " << rxBytes
                << " bytes received; "
                << avgMbps
                << " Mbps average from arrival to simulation end; "
                << "configured size " << mice.maxBytes
                << " bytes; arrival "
                << mice.startTime << " s\n";
        }

        summaryStream
            << "  Per-sample throughput is in "
            << "elephant_mice_throughput.csv\n"
            << "  Aggregate throughput uses elephant + all mice "
            << "over the common window from "
            << flowAStart << " s to " << simTime << " s.\n"
            << "  Jain's index uses the elephant and all five mice "
            << "averaged over that same common window.\n";
    }

    summaryStream
        << (enableElephantMice
                ? "Aggregate Throughput (elephant + five mice): "
                : "Aggregate Throughput (Flow A + Flow B): ")
        << avgAggregate << " Mbps\n"
        << (enableElephantMice
                ? "Overall Jain's Fairness Index (six flows, common window): "
                : "Overall Jain's Fairness Index (Flow A and Flow B): ")
        << std::setprecision(4)
        << overallJainIndex << "\n"
        << "========================================================\n";

    summaryStream.close();

    // Save summary JSON
    std::ofstream jsonStream(
        outDir + "/summary.json");

    jsonStream
        << "{\n"
        << "  \"tcpTypeId\": \"" << tcpTypeId << "\",\n"
        << "  \"trafficScenario\": \""
        << (enableElephantMice
                ? "elephant_mice"
                : "two_long_lived_flows")
        << "\",\n"
        << "  \"bottleneckBw\": \"" << bottleneckBw << "\",\n"
        << "  \"bottleneckDelay\": \"" << bottleneckDelay << "\",\n"
        << "  \"accessDelayA\": \"" << accessDelayA << "\",\n"
        << "  \"accessDelayB\": \"" << accessDelayB << "\",\n"
        << "  \"flowA_avg_mbps\": " << avgThroughputA << ",\n"
        << "  \"flowB_avg_mbps\": " << avgThroughputB << ",\n"
        << "  \"aggregate_mbps\": " << avgAggregate << ",\n"
        << "  \"jains_fairness_index\": "
        << overallJainIndex << ",\n"
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

    if (g_miceStream.is_open())
    {
        g_miceStream.close();
    }

    Simulator::Destroy();

    std::cout
        << "[DONE] Simulation complete. Results written to: "
        << outDir << std::endl;

    std::cout
        << "  Flow A Throughput: "
        << avgThroughputA << " Mbps" << std::endl;

    std::cout
        << "  Flow B Throughput: "
        << avgThroughputB << " Mbps" << std::endl;

    std::cout
        << "  Aggregate Throughput: "
        << avgAggregate << " Mbps" << std::endl;

    std::cout
        << "  Jain's Fairness Index: "
        << overallJainIndex << std::endl;

    return 0;
}
