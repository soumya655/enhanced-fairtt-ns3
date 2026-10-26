/*
 * Copyright (c) 2018 NITK Surathkal
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Authors: Vivek Jain <jain.vivek.anand@gmail.com>
 *          Viyom Mittal <viyommittal@gmail.com>
 *          Mohit P. Tahiliani <tahiliani@nitk.edu.in>
 */

#include "tcp-bbr-fairtt.h"

#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <deque>
#include <map>
#include <set>

namespace ns3
{

// Simulation-local registry of active TcpBbrFairtt instances. This provides the
// cross-flow RTT information required by the paper's fairness-threshold equation.
struct FairRttFlowState
{
    Time minRtt{Time::Max()};
    double weightedMinRttSeconds{0.0};
    uint32_t windowBytes{0};
};
static std::map<const TcpBbrFairtt*, FairRttFlowState> g_fairttFlows;


NS_LOG_COMPONENT_DEFINE("TcpBbrFairtt");
NS_OBJECT_ENSURE_REGISTERED(TcpBbrFairtt);

const double TcpBbrFairtt::PACING_GAIN_CYCLE[] = {5.0 / 4, 3.0 / 4, 1, 1, 1, 1, 1, 1};

TypeId
TcpBbrFairtt::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::TcpBbrFairtt")
            .SetParent<TcpCongestionOps>()
            .AddConstructor<TcpBbrFairtt>()
            .SetGroupName("Internet")
            .AddAttribute("Stream",
                          "Random number stream (default is set to 4 to align with Linux results)",
                          UintegerValue(4),
                          MakeUintegerAccessor(&TcpBbrFairtt::SetStream),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("HighGain",
                          "Value of high gain",
                          DoubleValue(2.89),
                          MakeDoubleAccessor(&TcpBbrFairtt::m_highGain),
                          MakeDoubleChecker<double>())
            .AddAttribute("FairRttBeta",
                          "FaiRTT smoothing factor (paper uses 0.8; exposed for experiments)",
                          DoubleValue(0.8),
                          MakeDoubleAccessor(&TcpBbrFairtt::m_fairRttBeta),
                          MakeDoubleChecker<double>(0.0, 1.0))
            .AddAttribute("FairRttGamma",
                          "FaiRTT BDP discount factor (paper uses 0.99)",
                          DoubleValue(0.99),
                          MakeDoubleAccessor(&TcpBbrFairtt::m_fairRttGamma),
                          MakeDoubleChecker<double>(0.0, 1.0))
            .AddAttribute("BwWindowLength",
                          "Length of bandwidth windowed filter",
                          UintegerValue(10),
                          MakeUintegerAccessor(&TcpBbrFairtt::m_bandwidthWindowLength),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RttWindowLength",
                          "Length of RTT windowed filter",
                          TimeValue(Seconds(10)),
                          MakeTimeAccessor(&TcpBbrFairtt::m_minRttFilterLen),
                          MakeTimeChecker())
            .AddAttribute("ProbeRttDuration",
                          "Time to be spent in PROBE_RTT phase",
                          TimeValue(MilliSeconds(200)),
                          MakeTimeAccessor(&TcpBbrFairtt::m_probeRttDuration),
                          MakeTimeChecker())
            .AddAttribute("ExtraAckedRttWindowLength",
                          "Window length of extra acked window",
                          UintegerValue(5),
                          MakeUintegerAccessor(&TcpBbrFairtt::m_extraAckedWinRttLength),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute(
                "AckEpochAckedResetThresh",
                "Max allowed val for m_ackEpochAcked, after which sampling epoch is reset",
                UintegerValue(1 << 12),
                MakeUintegerAccessor(&TcpBbrFairtt::m_ackEpochAckedResetThresh),
                MakeUintegerChecker<uint32_t>())
            .AddTraceSource("MinRtt",
                            "Estimated two-way round-trip propagation delay of the path, estimated "
                            "from the windowed minimum recent round-trip delay sample",
                            MakeTraceSourceAccessor(&TcpBbrFairtt::m_minRtt),
                            "ns3::TracedValueCallback::Time")
            .AddTraceSource("PacingGain",
                            "The dynamic pacing gain factor",
                            MakeTraceSourceAccessor(&TcpBbrFairtt::m_pacingGain),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("CwndGain",
                            "The dynamic congestion window gain factor",
                            MakeTraceSourceAccessor(&TcpBbrFairtt::m_cWndGain),
                            "ns3::TracedValueCallback::Double");
    return tid;
}

TcpBbrFairtt::TcpBbrFairtt()
    : TcpCongestionOps()
{
    NS_LOG_FUNCTION(this);
    m_uv = CreateObject<UniformRandomVariable>();
    g_fairttFlows[this] = FairRttFlowState{};
}

TcpBbrFairtt::TcpBbrFairtt(const TcpBbrFairtt& sock)
    : TcpCongestionOps(sock),
      m_bandwidthWindowLength(sock.m_bandwidthWindowLength),
      m_pacingGain(sock.m_pacingGain),
      m_cWndGain(sock.m_cWndGain),
      m_highGain(sock.m_highGain),
      m_isPipeFilled(sock.m_isPipeFilled),
      m_minPipeCwnd(sock.m_minPipeCwnd),
      m_roundCount(sock.m_roundCount),
      m_roundStart(sock.m_roundStart),
      m_nextRoundDelivered(sock.m_nextRoundDelivered),
      m_probeRttDuration(sock.m_probeRttDuration),
      m_probeRtPropStamp(sock.m_probeRtPropStamp),
      m_probeRttDoneStamp(sock.m_probeRttDoneStamp),
      m_probeRttRoundDone(sock.m_probeRttRoundDone),
      m_packetConservation(sock.m_packetConservation),
      m_priorCwnd(sock.m_priorCwnd),
      m_idleRestart(sock.m_idleRestart),
      m_targetCWnd(sock.m_targetCWnd),
      m_fullBandwidth(sock.m_fullBandwidth),
      m_fullBandwidthCount(sock.m_fullBandwidthCount),
      m_minRtt(Time::Max()),
      m_sendQuantum(sock.m_sendQuantum),
      m_cycleStamp(sock.m_cycleStamp),
      m_cycleIndex(sock.m_cycleIndex),
      m_minRttExpired(sock.m_minRttExpired),
      m_minRttFilterLen(sock.m_minRttFilterLen),
      m_minRttStamp(sock.m_minRttStamp),
      m_isInitialized(sock.m_isInitialized),
      m_uv(sock.m_uv),
      m_delivered(sock.m_delivered),
      m_extraAckedGain(sock.m_extraAckedGain),
      m_extraAckedWinRtt(sock.m_extraAckedWinRtt),
      m_extraAckedWinRttLength(sock.m_extraAckedWinRttLength),
      m_ackEpochAckedResetThresh(sock.m_ackEpochAckedResetThresh),
      m_extraAckedIdx(sock.m_extraAckedIdx),
      m_ackEpochTime(sock.m_ackEpochTime),
      m_ackEpochAcked(sock.m_ackEpochAcked),
      m_hasSeenRtt(sock.m_hasSeenRtt),
      m_fairRttBeta(sock.m_fairRttBeta),
      m_fairRttGamma(sock.m_fairRttGamma)
{
    NS_LOG_FUNCTION(this);
    g_fairttFlows[this].minRtt = m_minRtt;
}

TcpBbrFairtt::~TcpBbrFairtt()
{
    g_fairttFlows.erase(this);
}

void
TcpBbrFairtt::SetRateOps(Ptr<TcpRateOps> rateOps)
{
    m_rateOps = rateOps;
}

const char* const TcpBbrFairtt::BbrModeName[BBR_PROBE_RTT + 1] = {
    "BBR_STARTUP",
    "BBR_DRAIN",
    "BBR_PROBE_BW",
    "BBR_PROBE_RTT",
};

void
TcpBbrFairtt::SetStream(uint32_t stream)
{
    NS_LOG_FUNCTION(this << stream);
    m_uv->SetStream(stream);
}

void
TcpBbrFairtt::InitRoundCounting()
{
    NS_LOG_FUNCTION(this);
    m_nextRoundDelivered = 0;
    m_roundStart = false;
    m_roundCount = 0;
}

void
TcpBbrFairtt::InitFullPipe()
{
    NS_LOG_FUNCTION(this);
    m_isPipeFilled = false;
    m_fullBandwidth = 0;
    m_fullBandwidthCount = 0;
}

void
TcpBbrFairtt::InitPacingRate(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);

    if (!tcb->m_pacing)
    {
        NS_LOG_WARN("BBR must use pacing");
        tcb->m_pacing = true;
    }

    Time rtt;
    if (tcb->m_minRtt != Time::Max())
    {
        rtt = MilliSeconds(std::max<long int>(tcb->m_minRtt.GetMilliSeconds(), 1));
        m_hasSeenRtt = true;
    }
    else
    {
        rtt = MilliSeconds(1);
    }

    DataRate nominalBandwidth(tcb->m_cWnd * 8 / rtt.GetSeconds());
    tcb->m_pacingRate = DataRate(m_pacingGain * nominalBandwidth.GetBitRate());
    m_maxBwFilter = MaxBandwidthFilter_t(m_bandwidthWindowLength,
                                         DataRate(tcb->m_cWnd * 8 / rtt.GetSeconds()),
                                         0);
}

void
TcpBbrFairtt::EnterStartup()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_STARTUP);
    m_pacingGain = m_highGain;
    m_cWndGain = m_highGain;
}

void
TcpBbrFairtt::HandleRestartFromIdle(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    if (tcb->m_bytesInFlight.Get() == 0U && rs.m_isAppLimited)
    {
        m_idleRestart = true;
        if (m_state == BbrMode_t::BBR_PROBE_BW)
        {
            SetPacingRate(tcb, 1);
        }
    }
}

void
TcpBbrFairtt::SetPacingRate(Ptr<TcpSocketState> tcb, double gain)
{
    NS_LOG_FUNCTION(this << tcb << gain);
    DataRate rate(gain * m_maxBwFilter.GetBest().GetBitRate());
    rate *= (1.f - m_pacingMargin);
    rate = std::min(rate, tcb->m_maxPacingRate);

    if (!m_hasSeenRtt && tcb->m_minRtt != Time::Max())
    {
        InitPacingRate(tcb);
    }

    if (m_isPipeFilled || rate > tcb->m_pacingRate)
    {
        tcb->m_pacingRate = rate;
        NS_LOG_DEBUG("Pacing rate updated. New value: " << tcb->m_pacingRate);
    }
}

uint32_t
TcpBbrFairtt::InFlight(Ptr<TcpSocketState> tcb, double gain)
{
    NS_LOG_FUNCTION(this << tcb << gain);
    if (m_minRtt == Time::Max())
    {
        return tcb->m_initialCWnd * tcb->m_segmentSize;
    }
    double quanta = 3 * m_sendQuantum;
    double estimatedBdp = m_maxBwFilter.GetBest() * m_minRtt / 8.0;

    // FaiRTT Algorithm 1, applied only in PROBE_BW.
    // Paper equations (5)-(7) define Wt=min(receive-window, send-window),
    // Wf_count as the number of distinct minRTT values, and alpha from the
    // weighted RTT values. We preserve those definitions explicitly here.
    if (m_state == BbrMode_t::BBR_PROBE_BW && tcb->m_lastRtt.Get().IsPositive())
    {
        const uint32_t windowBytes = std::min(tcb->m_rWnd, tcb->m_cWnd.Get());
        auto& ownState = g_fairttFlows[this];
        ownState.minRtt = m_minRtt;
        ownState.windowBytes = std::max<uint32_t>(windowBytes, 1);

        std::set<int64_t> uniqueMinRttNs;
        uint32_t flowCount = 0;
        double weightedRttSumSeconds = 0.0;
        for (const auto& entry : g_fairttFlows)
        {
            const auto& flow = entry.second;
            if (flow.minRtt != Time::Max() && flow.minRtt.IsPositive())
            {
                ++flowCount;
                uniqueMinRttNs.insert(flow.minRtt.GetNanoSeconds());
                // Equation (5): sum W_minRTT_j / W_t. The source paper's
                // equations use window size in this denominator; clamp to 1
                // to avoid division by zero before TCP windows are established.
                weightedRttSumSeconds += flow.weightedMinRttSeconds /
                                         std::max<uint32_t>(flow.windowBytes, 1);
            }
        }

        if (flowCount > 0 && !uniqueMinRttNs.empty())
        {
            // W_f_count is the count of distinct minimum RTT values (Eq. 5).
            const double alphaSeconds =
                static_cast<double>(uniqueMinRttNs.size()) * weightedRttSumSeconds;
            const double lastRttSeconds = tcb->m_lastRtt.Get().GetSeconds();
            if (lastRttSeconds > alphaSeconds)
            {
                // Equation (8) / Algorithm 1: discounted BDP for RTTs above alpha.
                const double scale = (m_minRtt.GetSeconds() * m_fairRttGamma) /
                                     lastRttSeconds;
                estimatedBdp *= std::clamp(scale, 0.0, 1.0);
            }
        }
    }

    if (m_state == BbrMode_t::BBR_PROBE_BW && m_cycleIndex == 0)
    {
        return (gain * estimatedBdp) + quanta + (2 * tcb->m_segmentSize);
    }
    return (gain * estimatedBdp) + quanta;
}

void
TcpBbrFairtt::AdvanceCyclePhase()
{
    NS_LOG_FUNCTION(this);
    m_cycleStamp = Simulator::Now();
    m_cycleIndex = (m_cycleIndex + 1) % GAIN_CYCLE_LENGTH;
    m_pacingGain = PACING_GAIN_CYCLE[m_cycleIndex];
}

bool
TcpBbrFairtt::IsNextCyclePhase(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    bool isFullLength = (Simulator::Now() - m_cycleStamp) > m_minRtt;
    if (m_pacingGain == 1)
    {
        return isFullLength;
    }
    else if (m_pacingGain > 1)
    {
        return isFullLength &&
               (rs.m_bytesLoss > 0 || rs.m_priorInFlight >= InFlight(tcb, m_pacingGain));
    }
    else
    {
        return isFullLength || rs.m_priorInFlight <= InFlight(tcb, 1);
    }
}

void
TcpBbrFairtt::CheckCyclePhase(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    if (m_state == BbrMode_t::BBR_PROBE_BW && IsNextCyclePhase(tcb, rs))
    {
        AdvanceCyclePhase();
    }
}

void
TcpBbrFairtt::CheckFullPipe(const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << rs);
    if (m_isPipeFilled || !m_roundStart || rs.m_isAppLimited)
    {
        return;
    }

    /* Check if Bottleneck bandwidth is still growing*/
    if (m_maxBwFilter.GetBest().GetBitRate() >= m_fullBandwidth.GetBitRate() * 1.25)
    {
        m_fullBandwidth = m_maxBwFilter.GetBest();
        m_fullBandwidthCount = 0;
        return;
    }

    m_fullBandwidthCount++;
    if (m_fullBandwidthCount >= 3)
    {
        NS_LOG_DEBUG("Pipe filled");
        m_isPipeFilled = true;
    }
}

void
TcpBbrFairtt::EnterDrain()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_DRAIN);
    m_pacingGain = 1.0 / m_highGain;
    m_cWndGain = m_highGain;
}

void
TcpBbrFairtt::EnterProbeBW()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_PROBE_BW);
    m_pacingGain = 1;
    m_cWndGain = 2;
    m_cycleIndex = GAIN_CYCLE_LENGTH - 1 - (int)m_uv->GetValue(0, 6);
    AdvanceCyclePhase();
}

void
TcpBbrFairtt::CheckDrain(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    if (m_state == BbrMode_t::BBR_STARTUP && m_isPipeFilled)
    {
        EnterDrain();
        tcb->m_ssThresh = InFlight(tcb, 1);
    }

    if (m_state == BbrMode_t::BBR_DRAIN && tcb->m_bytesInFlight <= InFlight(tcb, 1))
    {
        EnterProbeBW();
    }
}

void
TcpBbrFairtt::UpdateRTprop(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    m_minRttExpired = Simulator::Now() > (m_minRttStamp + m_minRttFilterLen);
    if (tcb->m_lastRtt.Get().IsPositive() && (tcb->m_lastRtt <= m_minRtt || m_minRttExpired))
    {
        m_minRtt = tcb->m_lastRtt;
        m_minRttStamp = Simulator::Now();
        m_fairRttMinRttHistory.emplace_back(Simulator::Now(), m_minRtt);
        while (!m_fairRttMinRttHistory.empty() &&
               Simulator::Now() - m_fairRttMinRttHistory.front().first > m_minRttFilterLen)
        {
            m_fairRttMinRttHistory.pop_front();
        }
        double historySumSeconds = 0.0;
        for (const auto& sample : m_fairRttMinRttHistory)
        {
            historySumSeconds += sample.second.GetSeconds();
        }
        const double averageHistorySeconds =
            historySumSeconds / std::max<uint32_t>(
                std::min(tcb->m_rWnd, tcb->m_cWnd.Get()), 1);
        auto& flow = g_fairttFlows[this];
        flow.minRtt = m_minRtt;
        flow.windowBytes = std::max<uint32_t>(std::min(tcb->m_rWnd, tcb->m_cWnd.Get()), 1);
        // Equation (6): W_minRTT_t = beta * historical average + (1-beta) * minRTT_t.
        flow.weightedMinRttSeconds = m_fairRttBeta * averageHistorySeconds +
                                     (1.0 - m_fairRttBeta) * m_minRtt.GetSeconds();
    }
}

void
TcpBbrFairtt::EnterProbeRTT()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_PROBE_RTT);
    m_pacingGain = 1;
    m_cWndGain = 1;
}

void
TcpBbrFairtt::SaveCwnd(Ptr<const TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    if (tcb->m_congState != TcpSocketState::CA_RECOVERY && m_state != BbrMode_t::BBR_PROBE_RTT)
    {
        m_priorCwnd = tcb->m_cWnd;
    }
    else
    {
        m_priorCwnd = std::max(m_priorCwnd, tcb->m_cWnd.Get());
    }
}

void
TcpBbrFairtt::RestoreCwnd(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    tcb->m_cWnd = std::max(m_priorCwnd, tcb->m_cWnd.Get());
}

void
TcpBbrFairtt::ExitProbeRTT()
{
    NS_LOG_FUNCTION(this);
    if (m_isPipeFilled)
    {
        EnterProbeBW();
    }
    else
    {
        EnterStartup();
    }
}

void
TcpBbrFairtt::HandleProbeRTT(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);

    m_rateOps->SetAppLimited(tcb->m_bytesInFlight.Get());

    if (m_probeRttDoneStamp.IsZero() && tcb->m_bytesInFlight <= m_minPipeCwnd)
    {
        m_probeRttDoneStamp = Simulator::Now() + m_probeRttDuration;
        m_probeRttRoundDone = false;
        m_nextRoundDelivered = m_delivered;
    }
    else if (!m_probeRttDoneStamp.IsZero())
    {
        if (m_roundStart)
        {
            m_probeRttRoundDone = true;
        }
        if (m_probeRttRoundDone && Simulator::Now() > m_probeRttDoneStamp)
        {
            m_minRttStamp = Simulator::Now();
            RestoreCwnd(tcb);
            ExitProbeRTT();
        }
    }
}

void
TcpBbrFairtt::CheckProbeRTT(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb);
    if (m_state != BbrMode_t::BBR_PROBE_RTT && m_minRttExpired && !m_idleRestart)
    {
        EnterProbeRTT();
        SaveCwnd(tcb);
        m_probeRttDoneStamp = Seconds(0);
    }

    if (m_state == BbrMode_t::BBR_PROBE_RTT)
    {
        HandleProbeRTT(tcb);
    }

    if (rs.m_delivered)
    {
        m_idleRestart = false;
    }
}

void
TcpBbrFairtt::SetSendQuantum(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    m_sendQuantum = 1 * tcb->m_segmentSize;
}

void
TcpBbrFairtt::UpdateTargetCwnd(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    m_targetCWnd = InFlight(tcb, m_cWndGain) + AckAggregationCwnd();
}

uint32_t
TcpBbrFairtt::AckAggregationCwnd()
{
    NS_LOG_FUNCTION(this);
    uint32_t maxAggrBytes; // MaxBW * 0.1 secs
    uint32_t aggrCwndBytes = 0;

    if (m_extraAckedGain && m_isPipeFilled)
    {
        maxAggrBytes = m_maxBwFilter.GetBest().GetBitRate() / (10 * 8);
        aggrCwndBytes = m_extraAckedGain * std::max(m_extraAcked[0], m_extraAcked[1]);
        aggrCwndBytes = std::min(aggrCwndBytes, maxAggrBytes);
    }
    return aggrCwndBytes;
}

void
TcpBbrFairtt::UpdateAckAggregation(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    uint32_t expectedAcked;
    uint32_t extraAck;
    uint32_t epochProp;

    if (!m_extraAckedGain || rs.m_ackedSacked <= 0 || rs.m_delivered < 0)
    {
        return;
    }

    if (m_roundStart)
    {
        m_extraAckedWinRtt = std::min<uint32_t>(31, m_extraAckedWinRtt + 1);
        if (m_extraAckedWinRtt >= m_extraAckedWinRttLength)
        {
            m_extraAckedWinRtt = 0;
            m_extraAckedIdx = m_extraAckedIdx ? 0 : 1;
            m_extraAcked[m_extraAckedIdx] = 0;
        }
    }

    epochProp = Simulator::Now().GetSeconds() - m_ackEpochTime.GetSeconds();
    expectedAcked = m_maxBwFilter.GetBest().GetBitRate() * epochProp / 8;

    if (m_ackEpochAcked <= expectedAcked ||
        (m_ackEpochAcked + rs.m_ackedSacked >= m_ackEpochAckedResetThresh))
    {
        m_ackEpochAcked = 0;
        m_ackEpochTime = Simulator::Now();
        expectedAcked = 0;
    }

    m_ackEpochAcked = m_ackEpochAcked + rs.m_ackedSacked;
    extraAck = m_ackEpochAcked - expectedAcked;
    extraAck = std::min(extraAck, tcb->m_cWnd.Get());

    if (extraAck > m_extraAcked[m_extraAckedIdx])
    {
        m_extraAcked[m_extraAckedIdx] = extraAck;
    }
}

bool
TcpBbrFairtt::ModulateCwndForRecovery(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    if (rs.m_bytesLoss > 0)
    {
        tcb->m_cWnd =
            std::max((int)tcb->m_cWnd.Get() - (int)rs.m_bytesLoss, (int)tcb->m_segmentSize);
    }

    if (m_packetConservation)
    {
        tcb->m_cWnd = std::max(tcb->m_cWnd.Get(), tcb->m_bytesInFlight.Get() + rs.m_ackedSacked);
        return true;
    }
    return false;
}

void
TcpBbrFairtt::ModulateCwndForProbeRTT(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    if (m_state == BbrMode_t::BBR_PROBE_RTT)
    {
        tcb->m_cWnd = std::min(tcb->m_cWnd.Get(), m_minPipeCwnd);
    }
}

void
TcpBbrFairtt::SetCwnd(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);

    if (!rs.m_ackedSacked)
    {
        goto done;
    }

    if (tcb->m_congState == TcpSocketState::CA_RECOVERY)
    {
        if (ModulateCwndForRecovery(tcb, rs))
        {
            goto done;
        }
    }

    UpdateTargetCwnd(tcb);

    if (m_isPipeFilled)
    {
        tcb->m_cWnd = std::min(tcb->m_cWnd.Get() + (uint32_t)rs.m_ackedSacked, m_targetCWnd);
    }
    else if (tcb->m_cWnd < m_targetCWnd || m_delivered < tcb->m_initialCWnd * tcb->m_segmentSize)
    {
        tcb->m_cWnd = tcb->m_cWnd.Get() + rs.m_ackedSacked;
    }
    tcb->m_cWnd = std::max(tcb->m_cWnd.Get(), m_minPipeCwnd);
    NS_LOG_DEBUG("Congestion window updated. New value:" << tcb->m_cWnd);

done:
    ModulateCwndForProbeRTT(tcb);
}

void
TcpBbrFairtt::UpdateRound(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    if (rs.m_priorDelivered >= m_nextRoundDelivered)
    {
        m_nextRoundDelivered = m_delivered;
        m_roundCount++;
        m_roundStart = true;
        m_packetConservation = false;
    }
    else
    {
        m_roundStart = false;
    }
}

void
TcpBbrFairtt::UpdateBottleneckBandwidth(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);

    if (rs.m_delivered < 0 || rs.m_interval.IsZero())
    {
        return;
    }

    UpdateRound(tcb, rs);

    if (rs.m_deliveryRate >= m_maxBwFilter.GetBest() || !rs.m_isAppLimited)
    {
        m_maxBwFilter.Update(rs.m_deliveryRate, m_roundCount);
    }
}

void
TcpBbrFairtt::UpdateModelAndState(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    UpdateBottleneckBandwidth(tcb, rs);
    UpdateAckAggregation(tcb, rs);
    CheckCyclePhase(tcb, rs);
    CheckFullPipe(rs);
    CheckDrain(tcb);
    UpdateRTprop(tcb);
    CheckProbeRTT(tcb, rs);
}

void
TcpBbrFairtt::UpdateControlParameters(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    SetPacingRate(tcb, m_pacingGain);
    SetSendQuantum(tcb);
    SetCwnd(tcb, rs);
}

void
TcpBbrFairtt::SetBbrState(BbrMode_t mode)
{
    NS_LOG_FUNCTION(this << mode);
    NS_LOG_DEBUG(Simulator::Now() << " Changing from " << BbrModeName[m_state] << " to "
                                  << BbrModeName[mode]);
    m_state = mode;
}

uint32_t
TcpBbrFairtt::GetBbrState()
{
    NS_LOG_FUNCTION(this);
    return m_state;
}

double
TcpBbrFairtt::GetCwndGain()
{
    NS_LOG_FUNCTION(this);
    return m_cWndGain;
}

double
TcpBbrFairtt::GetPacingGain()
{
    NS_LOG_FUNCTION(this);
    return m_pacingGain;
}

std::string
TcpBbrFairtt::GetName() const
{
    return "TcpBbrFairtt";
}

bool
TcpBbrFairtt::HasCongControl() const
{
    NS_LOG_FUNCTION(this);
    return true;
}

void
TcpBbrFairtt::CongControl(Ptr<TcpSocketState> tcb,
                    const TcpRateOps::TcpRateConnection& rc,
                    const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    m_delivered = rc.m_delivered;
    UpdateModelAndState(tcb, rs);
    UpdateControlParameters(tcb, rs);
}

void
TcpBbrFairtt::CongestionStateSet(Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCongState_t newState)
{
    NS_LOG_FUNCTION(this << tcb << newState);
    if (newState == TcpSocketState::CA_OPEN && !m_isInitialized)
    {
        NS_LOG_DEBUG("CongestionStateSet triggered to CA_OPEN :: " << newState);
        m_minRtt = tcb->m_srtt.Get() != Time::Max() ? tcb->m_srtt.Get() : Time::Max();
        m_minRttStamp = Simulator::Now();
        m_priorCwnd = tcb->m_cWnd;
        tcb->m_ssThresh = tcb->m_initialSsThresh;
        m_targetCWnd = tcb->m_cWnd;
        m_minPipeCwnd = 4 * tcb->m_segmentSize;
        m_sendQuantum = 1 * tcb->m_segmentSize;

        InitRoundCounting();
        InitFullPipe();
        EnterStartup();
        InitPacingRate(tcb);
        m_ackEpochTime = Simulator::Now();
        m_extraAckedWinRtt = 0;
        m_extraAckedIdx = 0;
        m_ackEpochAcked = 0;
        m_extraAcked[0] = 0;
        m_extraAcked[1] = 0;
        m_isInitialized = true;
    }
    else if (newState == TcpSocketState::CA_LOSS)
    {
        NS_LOG_DEBUG("CongestionStateSet triggered to CA_LOSS :: " << newState);
        SaveCwnd(tcb);
        m_roundStart = true;
    }
    else if (newState == TcpSocketState::CA_RECOVERY)
    {
        NS_LOG_DEBUG("CongestionStateSet triggered to CA_RECOVERY :: " << newState);
        SaveCwnd(tcb);
        tcb->m_cWnd =
            tcb->m_bytesInFlight.Get() + std::max(tcb->m_lastAckedSackedBytes, tcb->m_segmentSize);
        m_packetConservation = true;
    }
}

void
TcpBbrFairtt::CwndEvent(Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCAEvent_t event)
{
    NS_LOG_FUNCTION(this << tcb << event);
    if (event == TcpSocketState::CA_EVENT_COMPLETE_CWR)
    {
        NS_LOG_DEBUG("CwndEvent triggered to CA_EVENT_COMPLETE_CWR :: " << event);
        m_packetConservation = false;
        RestoreCwnd(tcb);
    }
    else if (event == TcpSocketState::CA_EVENT_TX_START &&
             m_rateOps->GetConnectionRate().m_appLimited)
    {
        NS_LOG_DEBUG("CwndEvent triggered to CA_EVENT_TX_START :: " << event);
        m_idleRestart = true;
        m_ackEpochTime = Simulator::Now();
        m_ackEpochAcked = 0;
        if (m_state == BbrMode_t::BBR_PROBE_BW)
        {
            SetPacingRate(tcb, 1);
        }
        else if (m_state == BbrMode_t::BBR_PROBE_RTT)
        {
            if (m_probeRttRoundDone && Simulator::Now() > m_probeRttDoneStamp)
            {
                m_minRttStamp = Simulator::Now();
                RestoreCwnd(tcb);
                ExitProbeRTT();
            }
        }
    }
}

uint32_t
TcpBbrFairtt::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t bytesInFlight)
{
    NS_LOG_FUNCTION(this << tcb << bytesInFlight);
    SaveCwnd(tcb);
    return tcb->m_ssThresh;
}

Ptr<TcpCongestionOps>
TcpBbrFairtt::Fork()
{
    return CopyObject<TcpBbrFairtt>(this);
}

} // namespace ns3
