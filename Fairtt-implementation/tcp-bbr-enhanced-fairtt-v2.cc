/*
 * Copyright (c) 2018 NITK Surathkal
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Authors: Vivek Jain <jain.vivek.anand@gmail.com>
 *          Viyom Mittal <viyommittal@gmail.com>
 *          Mohit P. Tahiliani <tahiliani@nitk.edu.in>
 */

#include "tcp-bbr-enhanced-fairtt-v2.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>

#include "ns3/log.h"
#include "ns3/simulator.h"

namespace ns3
{

namespace
{

constexpr double V2_RTT_BETA0 = 0.8;
constexpr double V2_RTT_BETA_MIN = 0.2;
constexpr double V2_RTT_K_BETA = 0.4;
constexpr double V2_RTT_GAMMA0 = 0.99;
constexpr double V2_RTT_GAMMA_MIN = 0.40;
constexpr double V2_RTT_K_GAMMA = 0.45;
constexpr double V2_RTT_K_QUEUE_GAMMA = 0.10;
constexpr double MIN_BDP_REDUCTION = 0.05;

static_assert(V2_RTT_BETA_MIN > 0.0 && V2_RTT_BETA_MIN <= V2_RTT_BETA0 &&
                  V2_RTT_BETA0 <= 1.0,
              "Adaptive beta parameters must define a valid convex weight");
static_assert(V2_RTT_GAMMA_MIN > 0.0 && V2_RTT_GAMMA_MIN <= V2_RTT_GAMMA0 &&
                  V2_RTT_GAMMA0 <= 1.0,
              "Adaptive gamma parameters must define a positive reduction");
static_assert(V2_RTT_K_BETA >= 0.0 && V2_RTT_K_GAMMA >= 0.0 &&
                  V2_RTT_K_QUEUE_GAMMA >= 0.0 &&
                  MIN_BDP_REDUCTION > 0.0 && MIN_BDP_REDUCTION <= 1.0,
              "Adaptive coefficients and smoothing bounds must be non-negative and finite");

double
CalculateAdaptiveBeta(double fairnessError)
{
    const double beta = V2_RTT_BETA0 - V2_RTT_K_BETA * fairnessError;
    return std::clamp(beta, V2_RTT_BETA_MIN, V2_RTT_BETA0);
}

double
CalculateAdaptiveGamma(double fairnessError, double queueExcess)
{
    const double gamma = V2_RTT_GAMMA0 - V2_RTT_K_GAMMA * fairnessError -
                         V2_RTT_K_QUEUE_GAMMA * queueExcess;
    return std::clamp(gamma, V2_RTT_GAMMA_MIN, V2_RTT_GAMMA0);
}

struct FairRttFlowSample
{
    uint32_t group;
    Time smoothedMinRtt;
};

struct FairRttGroupStats
{
    Time minRtt{Time::Max()};
    Time maxRtt{Seconds(0)};
    Time meanRtt{Seconds(0)};
};

std::map<const TcpBbrEnhancedFairttV2*, FairRttFlowSample> g_fairRttFlowSamples;

void
UpdateFairRttFlowSample(const TcpBbrEnhancedFairttV2* controller, uint32_t group, Time smoothedMinRtt)
{
    g_fairRttFlowSamples[controller] = {group, smoothedMinRtt};
}

void
RemoveFairRttFlowSample(const TcpBbrEnhancedFairttV2* controller)
{
    g_fairRttFlowSamples.erase(controller);
}

bool
CalculateFairRttGroupStats(uint32_t group, FairRttGroupStats& stats)
{
    std::set<Time> uniqueRtts;
    for (const auto& [controller, sample] : g_fairRttFlowSamples)
    {
        if (sample.group == group && sample.smoothedMinRtt.IsPositive())
        {
            uniqueRtts.insert(sample.smoothedMinRtt);
        }
    }

    if (uniqueRtts.empty())
    {
        return false;
    }

    long double sumSeconds = 0.0L;
    for (const Time& rtt : uniqueRtts)
    {
        sumSeconds += rtt.GetSeconds();
    }
    stats.minRtt = *uniqueRtts.begin();
    stats.maxRtt = *uniqueRtts.rbegin();
    stats.meanRtt = Seconds(static_cast<double>(sumSeconds / uniqueRtts.size()));
    return true;
}

double
CalculateFairnessError(const FairRttGroupStats& stats)
{
    if (!stats.minRtt.IsPositive() || !stats.maxRtt.IsPositive())
    {
        return 0.0;
    }
    const double maximum = stats.maxRtt.GetSeconds();
    const double error = (maximum - stats.minRtt.GetSeconds()) / maximum;
    return std::isfinite(error) ? std::clamp(error, 0.0, 1.0) : 0.0;
}

double
CalculateFlowRttExcess(Time flowMinRtt, const FairRttGroupStats& stats)
{
    const double spread = stats.maxRtt.GetSeconds() - stats.minRtt.GetSeconds();
    if (!flowMinRtt.IsPositive() || spread <= 0.0 || !std::isfinite(spread))
    {
        return 0.0;
    }
    const double excess =
        (flowMinRtt.GetSeconds() - stats.minRtt.GetSeconds()) / spread;
    return std::isfinite(excess) ? std::clamp(excess, 0.0, 1.0) : 0.0;
}

} // namespace

NS_LOG_COMPONENT_DEFINE("TcpBbrEnhancedFairttV2");
NS_OBJECT_ENSURE_REGISTERED(TcpBbrEnhancedFairttV2);

const double TcpBbrEnhancedFairttV2::PACING_GAIN_CYCLE[] = {5.0 / 4, 3.0 / 4, 1, 1, 1, 1, 1, 1};

TypeId
TcpBbrEnhancedFairttV2::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::TcpBbrEnhancedFairttV2")
            .SetParent<TcpCongestionOps>()
            .AddConstructor<TcpBbrEnhancedFairttV2>()
            .SetGroupName("Internet")
            .AddAttribute("Stream",
                          "Random number stream (default is set to 4 to align with Linux results)",
                          UintegerValue(4),
                          MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::SetStream),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("HighGain",
                          "Value of high gain",
                          DoubleValue(2.89),
                          MakeDoubleAccessor(&TcpBbrEnhancedFairttV2::m_highGain),
                          MakeDoubleChecker<double>())
            .AddAttribute("BwWindowLength",
                          "Length of bandwidth windowed filter",
                          UintegerValue(10),
                          MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::m_bandwidthWindowLength),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("RttWindowLength",
                          "Length of RTT windowed filter",
                          TimeValue(Seconds(10)),
                          MakeTimeAccessor(&TcpBbrEnhancedFairttV2::m_minRttFilterLen),
                          MakeTimeChecker())
            .AddAttribute("RttFairnessGroup",
                          "Identifier for FaiRTT flows that share a bottleneck and contribute to "
                          "the cross-flow RTT fairness threshold",
                          UintegerValue(0),
                          MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::m_rttFairnessGroup),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("FairnessFloorStrength",
                          "Minimum queue-responsive reduction strength when path RTTs are equal",
                          DoubleValue(0.70),
                          MakeDoubleAccessor(&TcpBbrEnhancedFairttV2::m_fairnessFloorStrength),
                          MakeDoubleChecker<double>(0.0, 1.0))
            .AddAttribute("FairnessTransition",
                          "Normalized RTT-gap scale controlling how quickly reduction strength "
                          "approaches its high-disparity value",
                          DoubleValue(0.15),
                          MakeDoubleAccessor(&TcpBbrEnhancedFairttV2::m_fairnessTransition),
                          MakeDoubleChecker<double>(0.01, 1.0))
            .AddAttribute("BdpSmoothingTime",
                          "Exponential response time for bounded BDP reduction transitions",
                          TimeValue(MilliSeconds(50)),
                          MakeTimeAccessor(&TcpBbrEnhancedFairttV2::m_bdpSmoothingTime),
                          MakeTimeChecker(MilliSeconds(1)))
            .AddAttribute("MaxInflightBytes",
                          "Upper bound for V2 BDP-derived in-flight and congestion-window targets",
                          UintegerValue(512 * 1024),
                          MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::m_maxInflightBytes),
                          MakeUintegerChecker<uint32_t>(1))
            .AddAttribute("ProbeRttDuration",
                          "Time to be spent in PROBE_RTT phase",
                          TimeValue(MilliSeconds(200)),
                          MakeTimeAccessor(&TcpBbrEnhancedFairttV2::m_probeRttDuration),
                          MakeTimeChecker())
            .AddAttribute("ExtraAckedRttWindowLength",
                          "Window length of extra acked window",
                          UintegerValue(5),
                          MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::m_extraAckedWinRttLength),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute(
                "AckEpochAckedResetThresh",
                "Max allowed val for m_ackEpochAcked, after which sampling epoch is reset",
                UintegerValue(1 << 12),
                MakeUintegerAccessor(&TcpBbrEnhancedFairttV2::m_ackEpochAckedResetThresh),
                MakeUintegerChecker<uint32_t>())
            .AddTraceSource("MinRtt",
                            "Estimated two-way round-trip propagation delay of the path, estimated "
                            "from the windowed minimum recent round-trip delay sample",
                            MakeTraceSourceAccessor(&TcpBbrEnhancedFairttV2::m_minRtt),
                            "ns3::TracedValueCallback::Time")
            .AddTraceSource("PacingGain",
                            "The dynamic pacing gain factor",
                            MakeTraceSourceAccessor(&TcpBbrEnhancedFairttV2::m_pacingGain),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("CwndGain",
                            "The dynamic congestion window gain factor",
                            MakeTraceSourceAccessor(&TcpBbrEnhancedFairttV2::m_cWndGain),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("BdpReduction",
                            "Smoothed bounded BDP reduction factor used in PROBE_BW",
                            MakeTraceSourceAccessor(&TcpBbrEnhancedFairttV2::m_bdpReduction),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("FairnessError",
                            "Normalized spread of active flows' smoothed minimum RTTs",
                            MakeTraceSourceAccessor(&TcpBbrEnhancedFairttV2::m_fairnessError),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("ReductionStrength",
                            "Effective per-flow weight applied to the BDP reduction target",
                            MakeTraceSourceAccessor(
                                &TcpBbrEnhancedFairttV2::m_effectiveReductionStrength),
                            "ns3::TracedValueCallback::Double");
    return tid;
}

TcpBbrEnhancedFairttV2::TcpBbrEnhancedFairttV2()
    : TcpCongestionOps()
{
    NS_LOG_FUNCTION(this);
    m_uv = CreateObject<UniformRandomVariable>();
}

TcpBbrEnhancedFairttV2::TcpBbrEnhancedFairttV2(const TcpBbrEnhancedFairttV2& sock)
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
      m_rttFairnessGroup(sock.m_rttFairnessGroup),
      m_fairnessFloorStrength(sock.m_fairnessFloorStrength),
      m_fairnessTransition(sock.m_fairnessTransition),
      m_bdpSmoothingTime(sock.m_bdpSmoothingTime),
      m_maxInflightBytes(sock.m_maxInflightBytes),
      m_bdpReduction(sock.m_bdpReduction),
      m_fairnessError(sock.m_fairnessError),
      m_effectiveReductionStrength(sock.m_effectiveReductionStrength),
      m_lastBdpSmoothingUpdate(sock.m_lastBdpSmoothingUpdate),
      m_hasBdpSmoothingUpdate(sock.m_hasBdpSmoothingUpdate),
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
      m_hasSeenRtt(sock.m_hasSeenRtt)
{
    NS_LOG_FUNCTION(this);
}

void
TcpBbrEnhancedFairttV2::SetRateOps(Ptr<TcpRateOps> rateOps)
{
    m_rateOps = rateOps;
}

const char* const TcpBbrEnhancedFairttV2::BbrModeName[BBR_PROBE_RTT + 1] = {
    "BBR_STARTUP",
    "BBR_DRAIN",
    "BBR_PROBE_BW",
    "BBR_PROBE_RTT",
};

void
TcpBbrEnhancedFairttV2::SetStream(uint32_t stream)
{
    NS_LOG_FUNCTION(this << stream);
    m_uv->SetStream(stream);
}

void
TcpBbrEnhancedFairttV2::InitRoundCounting()
{
    NS_LOG_FUNCTION(this);
    m_nextRoundDelivered = 0;
    m_roundStart = false;
    m_roundCount = 0;
}

void
TcpBbrEnhancedFairttV2::InitFullPipe()
{
    NS_LOG_FUNCTION(this);
    m_isPipeFilled = false;
    m_fullBandwidth = 0;
    m_fullBandwidthCount = 0;
}

void
TcpBbrEnhancedFairttV2::InitPacingRate(Ptr<TcpSocketState> tcb)
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
TcpBbrEnhancedFairttV2::EnterStartup()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_STARTUP);
    m_pacingGain = m_highGain;
    m_cWndGain = m_highGain;
}

void
TcpBbrEnhancedFairttV2::HandleRestartFromIdle(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::SetPacingRate(Ptr<TcpSocketState> tcb, double gain)
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
TcpBbrEnhancedFairttV2::InFlight(Ptr<TcpSocketState> tcb, double gain)
{
    NS_LOG_FUNCTION(this << tcb << gain);
    if (m_minRtt == Time::Max())
    {
        const double initialInFlight =
            static_cast<double>(tcb->m_initialCWnd) * tcb->m_segmentSize;
        return static_cast<uint32_t>(
            std::clamp(initialInFlight, 1.0, static_cast<double>(m_maxInflightBytes)));
    }
    double quanta = 3.0 * m_sendQuantum;
    const Time minRtt = m_minRtt.Get();
    double estimatedBdp = m_maxBwFilter.GetBest() * minRtt / 8.0;
    if (!std::isfinite(estimatedBdp) || estimatedBdp < 0.0)
    {
        estimatedBdp = 0.0;
    }
    double targetReduction = 1.0;
    double fairnessError = 0.0;
    double reductionStrength = 0.0;
    if (m_state == BbrMode_t::BBR_PROBE_BW && minRtt.IsPositive())
    {
        FairRttGroupStats groupStats;
        const Time lastRtt = tcb->m_lastRtt.Get();
        const bool hasGroupStats =
            CalculateFairRttGroupStats(m_rttFairnessGroup, groupStats);
        if (hasGroupStats)
        {
            fairnessError = CalculateFairnessError(groupStats);
        }
        if (lastRtt.IsPositive() &&
            hasGroupStats &&
            lastRtt > groupStats.meanRtt)
        {
            const double flowRttExcess = CalculateFlowRttExcess(minRtt, groupStats);
            const double disparityResponse =
                fairnessError / (fairnessError + m_fairnessTransition);
            const double baseStrength =
                (1.0 - disparityResponse) * m_fairnessFloorStrength;
            reductionStrength = baseStrength + disparityResponse * flowRttExcess;
            reductionStrength = std::clamp(reductionStrength, 0.0, 1.0);
            const double queueExcess =
                std::max(0.0, lastRtt.GetSeconds() / minRtt.GetSeconds() - 1.0);
            const double gamma = CalculateAdaptiveGamma(fairnessError, queueExcess);
            const double rawReduction =
                gamma * minRtt.GetSeconds() / lastRtt.GetSeconds();
            if (std::isfinite(rawReduction))
            {
                const double boundedReduction =
                    std::clamp(rawReduction, MIN_BDP_REDUCTION, 1.0);
                targetReduction = 1.0 - reductionStrength * (1.0 - boundedReduction);
            }
        }
    }
    m_fairnessError = fairnessError;
    m_effectiveReductionStrength = reductionStrength;

    const Time now = Simulator::Now();
    if (!m_hasBdpSmoothingUpdate)
    {
        m_lastBdpSmoothingUpdate = now;
        m_hasBdpSmoothingUpdate = true;
    }
    else
    {
        const double elapsed = std::max(0.0, (now - m_lastBdpSmoothingUpdate).GetSeconds());
        const double smoothingTime = m_bdpSmoothingTime.GetSeconds();
        const double alpha =
            -std::expm1(-elapsed / smoothingTime);
        const double currentReduction = m_bdpReduction.Get();
        const double nextReduction =
            currentReduction + alpha * (targetReduction - currentReduction);
        m_bdpReduction = std::clamp(nextReduction, MIN_BDP_REDUCTION, 1.0);
        m_lastBdpSmoothingUpdate = now;
    }
    const double maxInFlight = static_cast<double>(m_maxInflightBytes);
    estimatedBdp =
        std::clamp(estimatedBdp * m_bdpReduction.Get(), 1.0, maxInFlight);

    if (m_state == BbrMode_t::BBR_PROBE_BW && m_cycleIndex == 0)
    {
        const double inFlight =
            (gain * estimatedBdp) + quanta + (2.0 * tcb->m_segmentSize);
        return static_cast<uint32_t>(
            std::clamp(std::isfinite(inFlight) ? inFlight : 1.0,
                       1.0,
                       maxInFlight));
    }
    const double inFlight = (gain * estimatedBdp) + quanta;
    return static_cast<uint32_t>(
        std::clamp(std::isfinite(inFlight) ? inFlight : 1.0,
                   1.0,
                   maxInFlight));
}

void
TcpBbrEnhancedFairttV2::AdvanceCyclePhase()
{
    NS_LOG_FUNCTION(this);
    m_cycleStamp = Simulator::Now();
    m_cycleIndex = (m_cycleIndex + 1) % GAIN_CYCLE_LENGTH;
    m_pacingGain = PACING_GAIN_CYCLE[m_cycleIndex];
}

bool
TcpBbrEnhancedFairttV2::IsNextCyclePhase(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::CheckCyclePhase(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    if (m_state == BbrMode_t::BBR_PROBE_BW && IsNextCyclePhase(tcb, rs))
    {
        AdvanceCyclePhase();
    }
}

void
TcpBbrEnhancedFairttV2::CheckFullPipe(const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::EnterDrain()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_DRAIN);
    m_pacingGain = 1.0 / m_highGain;
    m_cWndGain = m_highGain;
}

void
TcpBbrEnhancedFairttV2::EnterProbeBW()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_PROBE_BW);
    m_pacingGain = 1;
    m_cWndGain = 2;
    m_cycleIndex = GAIN_CYCLE_LENGTH - 1 - (int)m_uv->GetValue(0, 6);
    AdvanceCyclePhase();
}

void
TcpBbrEnhancedFairttV2::CheckDrain(Ptr<TcpSocketState> tcb)
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
TcpBbrEnhancedFairttV2::UpdateRTprop(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    m_minRttExpired = Simulator::Now() > (m_minRttStamp + m_minRttFilterLen);
    if (tcb->m_lastRtt.Get().IsPositive() && (tcb->m_lastRtt <= m_minRtt || m_minRttExpired))
    {
        m_minRtt = tcb->m_lastRtt;
        m_minRttStamp = Simulator::Now();
    }

    if (m_hasNewFairnessRttSample && m_minRtt.Get().IsPositive())
    {
        const long double currentMinRtt = m_minRtt.Get().GetSeconds();
        long double priorAverageSeconds = 0.0L;
        if (m_fairRttHistoryCount == 0)
        {
            m_smoothedMinRtt = m_minRtt;
        }
        else
        {
            priorAverageSeconds = m_fairRttHistorySumSeconds / m_fairRttHistoryCount;
            FairRttGroupStats groupStats;
            const double fairnessError =
                CalculateFairRttGroupStats(m_rttFairnessGroup, groupStats)
                    ? CalculateFairnessError(groupStats)
                    : 0.0;
            const double beta = CalculateAdaptiveBeta(fairnessError);
            m_smoothedMinRtt = Seconds(static_cast<double>(
                beta * priorAverageSeconds + (1.0 - beta) * currentMinRtt));
        }
        m_fairRttHistorySumSeconds += currentMinRtt;
        ++m_fairRttHistoryCount;
        UpdateFairRttFlowSample(this, m_rttFairnessGroup, m_smoothedMinRtt);
        NS_LOG_DEBUG("FaiRTT Eq. 6 minRTT=" << m_minRtt.Get()
                                            << " priorMeanSeconds=" << priorAverageSeconds
                                            << " WminRTT=" << m_smoothedMinRtt
                                            << " samples=" << m_fairRttHistoryCount);
        m_hasNewFairnessRttSample = false;
    }
}

void
TcpBbrEnhancedFairttV2::EnterProbeRTT()
{
    NS_LOG_FUNCTION(this);
    SetBbrState(BbrMode_t::BBR_PROBE_RTT);
    m_pacingGain = 1;
    m_cWndGain = 1;
}

void
TcpBbrEnhancedFairttV2::SaveCwnd(Ptr<const TcpSocketState> tcb)
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
TcpBbrEnhancedFairttV2::RestoreCwnd(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    tcb->m_cWnd = std::max(m_priorCwnd, tcb->m_cWnd.Get());
}

void
TcpBbrEnhancedFairttV2::ExitProbeRTT()
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
TcpBbrEnhancedFairttV2::HandleProbeRTT(Ptr<TcpSocketState> tcb)
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
TcpBbrEnhancedFairttV2::CheckProbeRTT(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::SetSendQuantum(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    m_sendQuantum = 1 * tcb->m_segmentSize;
}

void
TcpBbrEnhancedFairttV2::UpdateTargetCwnd(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    const uint64_t targetCwnd = static_cast<uint64_t>(InFlight(tcb, m_cWndGain)) +
                                AckAggregationCwnd();
    m_targetCWnd = static_cast<uint32_t>(
        std::min(targetCwnd, static_cast<uint64_t>(m_maxInflightBytes)));
}

void
TcpBbrEnhancedFairttV2::RttSample(Ptr<TcpSocketState> tcb, const Time& rtt)
{
    NS_LOG_FUNCTION(this << tcb << rtt);
    if (rtt.IsPositive())
    {
        m_hasNewFairnessRttSample = true;
    }
}

void
TcpBbrEnhancedFairttV2::ConnectionClosed(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    RemoveFairRttFlowSample(this);
    m_hasNewFairnessRttSample = false;
}

uint32_t
TcpBbrEnhancedFairttV2::AckAggregationCwnd()
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
TcpBbrEnhancedFairttV2::UpdateAckAggregation(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::ModulateCwndForRecovery(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    const uint64_t maxCwnd = m_maxInflightBytes;
    if (rs.m_bytesLoss > 0)
    {
        const uint64_t reduced =
            tcb->m_cWnd.Get() > rs.m_bytesLoss ? tcb->m_cWnd.Get() - rs.m_bytesLoss : 0;
        const uint64_t minimum =
            std::min<uint64_t>(tcb->m_segmentSize, maxCwnd);
        tcb->m_cWnd = static_cast<uint32_t>(
            std::min(std::max(reduced, minimum), maxCwnd));
    }

    if (m_packetConservation)
    {
        const uint64_t conservedWindow =
            static_cast<uint64_t>(tcb->m_bytesInFlight.Get()) + rs.m_ackedSacked;
        tcb->m_cWnd = static_cast<uint32_t>(
            std::min(std::max<uint64_t>(tcb->m_cWnd.Get(), conservedWindow), maxCwnd));
        return true;
    }
    return false;
}

void
TcpBbrEnhancedFairttV2::ModulateCwndForProbeRTT(Ptr<TcpSocketState> tcb)
{
    NS_LOG_FUNCTION(this << tcb);
    if (m_state == BbrMode_t::BBR_PROBE_RTT)
    {
        tcb->m_cWnd = std::min(tcb->m_cWnd.Get(), m_minPipeCwnd);
    }
}

void
TcpBbrEnhancedFairttV2::SetCwnd(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    const uint64_t maxCwnd = m_maxInflightBytes;
    const uint32_t minimumCwnd =
        static_cast<uint32_t>(std::min<uint64_t>(m_minPipeCwnd, maxCwnd));

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
        const uint64_t increased =
            static_cast<uint64_t>(tcb->m_cWnd.Get()) + rs.m_ackedSacked;
        tcb->m_cWnd =
            static_cast<uint32_t>(std::min(increased, static_cast<uint64_t>(m_targetCWnd)));
    }
    else if (tcb->m_cWnd < m_targetCWnd || m_delivered < tcb->m_initialCWnd * tcb->m_segmentSize)
    {
        const uint64_t increased =
            static_cast<uint64_t>(tcb->m_cWnd.Get()) + rs.m_ackedSacked;
        tcb->m_cWnd = static_cast<uint32_t>(std::min(increased, maxCwnd));
    }
    tcb->m_cWnd = std::min(std::max(tcb->m_cWnd.Get(), minimumCwnd),
                           static_cast<uint32_t>(maxCwnd));
    NS_LOG_DEBUG("Congestion window updated. New value:" << tcb->m_cWnd);

done:
    ModulateCwndForProbeRTT(tcb);
}

void
TcpBbrEnhancedFairttV2::UpdateRound(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::UpdateBottleneckBandwidth(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::UpdateModelAndState(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
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
TcpBbrEnhancedFairttV2::UpdateControlParameters(Ptr<TcpSocketState> tcb, const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    SetPacingRate(tcb, m_pacingGain);
    SetSendQuantum(tcb);
    SetCwnd(tcb, rs);
}

void
TcpBbrEnhancedFairttV2::SetBbrState(BbrMode_t mode)
{
    NS_LOG_FUNCTION(this << mode);
    NS_LOG_DEBUG(Simulator::Now() << " Changing from " << BbrModeName[m_state] << " to "
                                  << BbrModeName[mode]);
    m_state = mode;
}

uint32_t
TcpBbrEnhancedFairttV2::GetBbrState()
{
    NS_LOG_FUNCTION(this);
    return m_state;
}

double
TcpBbrEnhancedFairttV2::GetCwndGain()
{
    NS_LOG_FUNCTION(this);
    return m_cWndGain;
}

double
TcpBbrEnhancedFairttV2::GetPacingGain()
{
    NS_LOG_FUNCTION(this);
    return m_pacingGain;
}

std::string
TcpBbrEnhancedFairttV2::GetName() const
{
    return "TcpBbrEnhancedFairttV2";
}

bool
TcpBbrEnhancedFairttV2::HasCongControl() const
{
    NS_LOG_FUNCTION(this);
    return true;
}

void
TcpBbrEnhancedFairttV2::CongControl(Ptr<TcpSocketState> tcb,
                    const TcpRateOps::TcpRateConnection& rc,
                    const TcpRateOps::TcpRateSample& rs)
{
    NS_LOG_FUNCTION(this << tcb << rs);
    m_delivered = rc.m_delivered;
    UpdateModelAndState(tcb, rs);
    UpdateControlParameters(tcb, rs);
}

void
TcpBbrEnhancedFairttV2::CongestionStateSet(Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCongState_t newState)
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
TcpBbrEnhancedFairttV2::CwndEvent(Ptr<TcpSocketState> tcb, const TcpSocketState::TcpCAEvent_t event)
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
TcpBbrEnhancedFairttV2::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t bytesInFlight)
{
    NS_LOG_FUNCTION(this << tcb << bytesInFlight);
    SaveCwnd(tcb);
    uint32_t safeThresh = (m_priorCwnd > 0) ? m_priorCwnd : bytesInFlight;
    if (tcb->m_ssThresh.Get() < safeThresh && tcb->m_ssThresh.Get() > 0)
    {
        safeThresh = tcb->m_ssThresh.Get();
    }
    safeThresh = std::min(safeThresh, m_maxInflightBytes);
    return std::max(safeThresh, tcb->m_segmentSize);
}

Ptr<TcpCongestionOps>
TcpBbrEnhancedFairttV2::Fork()
{
    return CopyObject<TcpBbrEnhancedFairttV2>(this);
}

} // namespace ns3
