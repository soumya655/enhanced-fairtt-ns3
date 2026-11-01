FaiRTT variant for the supplied ns-3 TcpBbr implementation
==========================================================

Integration
-----------
The active controller is installed in ~/ns-3-dev/src/internet/model/ as
tcp-bbr-fairtt.cc/.h, with CMake and TypeId registration in the NS-3 checkout.
The source and header in this directory are synchronized reference copies.
The original tcp-bbr.cc/.h remain separate and unchanged by the FaiRTT logic.

Select the controller in a simulation with:
  --tcpTypeId=TcpBbrFairtt

The project runner selects it with:
  TCP_TYPE=TcpBbrFairtt ./experiments/all_experiments.sh

Algorithm implemented
---------------------
The implementation retains the existing NS-3 BBR model and applies the
paper's Algorithm 1 condition only in BBR_PROBE_BW:

  if lastRTT > alpha:
      adjustedBDP = BDP * (minRTT * gamma) / lastRTT
  else:
      adjustedBDP = BDP
  InFlight target = adjustedBDP * cwnd_gain

Here BDP is calculated as BtlBw * RTprop in bytes (bit-rate times seconds,
divided by eight), using the controller's existing max-bandwidth filter and
RTprop minimum. Existing BBR send-quanta and cycle terms are retained.

The fixed values are beta=0.8 and gamma=0.99. For each newly measured positive
RTT, the controller updates its 10-second BBR RTprop minimum and Eq. 6
cumulative history. The first valid sample initializes WminRTT; each later
sample uses:

  WminRTT_t = beta * (sum of prior minRTT samples / prior sample count)
              + (1-beta) * minRTT_t

History is cumulative from flow start until the connection ends. The latest
per-flow WminRTT estimates are kept for active flows in an RTT fairness group.
Alpha is the arithmetic mean of the exact-distinct estimates in that group.
The `RttFairnessGroup` attribute defaults to 0; set the same value for FaiRTT
flows sharing a bottleneck and distinct values for independent bottlenecks.

Research caveat and assumptions
-------------------------------
This is not a paper-faithful reproduction. Printed Eq. 5 and Eq. 7 do not
provide a dimensionally consistent threshold: Eq. 7 defines W_t using byte
windows, while Eq. 5 combines RTT terms and alpha is compared against an RTT.
The sample domain/indexing is also unclear. The exact-distinct per-flow
WminRTT arithmetic mean used here is an explicit, user-approved interpretation
to make the comparison meaningful; it is not claimed to be the paper's Eq. 5.
Eq. 6's initial condition is also assumed: the first valid RTT initializes
WminRTT, then cumulative prior minRTT observations are used without resets.

Other deliberate differences: the existing NS-3 BBR clone's gain schedule,
10-second RTprop expiry, 200-ms PROBE_RTT duration, and in-flight additive
terms are retained. The paper describes a different BBR model and its own
parameterization. Beta and gamma are fixed; the project's former square-root
RTT heuristic and proposed adaptive beta/gamma formulas are not used.

Build and validation
--------------------
From ~/ns-3-dev:
  ./ns3 build
  ./test.py -s tcp-bbr-test -n --verbose

From the project directory, reproduce baseline then FaiRTT experiments:
  ./experiments/all_experiments.sh
  TCP_TYPE=TcpBbrFairtt ./experiments/all_experiments.sh
  TCP_TYPE=TcpBbrEnhancedFairtt ./experiments/all_experiments.sh

The runner writes raw traces, calculated metrics, logs, per-controller plots,
and comparison plots under results/. Verify each run's `tcpTypeId` metadata
and log before interpreting its results. Do not treat this implementation as
validated against the paper until the alpha and model discrepancies are
resolved from an authoritative clarification.

Enhanced FaiRTT
---------------
`tcp-bbr-enhanced-fairtt.cc/.h` define `ns3::TcpBbrEnhancedFairtt` as a
separate controller. The original `TcpBbr` and `TcpBbrFairtt` source files are
not modified by this implementation. The Enhanced controller is integrated
into the active NS-3 checkout's `src/internet/CMakeLists.txt`.

Relative to FaiRTT, the new controller makes beta and gamma adaptive, adds the
group-relative RTT excess term to gamma, replaces the abrupt reduction with a
time-based exponential smoother, saturates the BDP/in-flight target arithmetic,
and exposes the applied smoother through `BdpReduction`. The inherited BBR
state machine and the original FaiRTT source remain unchanged.

Select it with:
  --tcpTypeId=TcpBbrEnhancedFairtt

It retains the existing alpha threshold interpretation and adapts parameters
from `r = max(1, smoothedRTT / minRTT)`, falling back to 1 if either RTT is
unavailable or invalid:

  beta(r)    = max(0.2, 0.8 / (1 + 0.005 * (r - 1)))
  e          = max(0, lastRTT / alpha - 1)
  gamma(r,e) = max(0.40, 0.99 - 0.02 * (r - 1) - 0.10 * e)

Beta is also capped at 1 to keep the cumulative-history update a convex
combination. Gamma is bounded above by 0.99. The implementation uses
compile-time parameter assertions, finite-value checks, positive RTT guards,
and bounded outputs.

The raw reduction target remains `gamma(r,e) * minRTT / lastRTT` when
`lastRTT > alpha`, otherwise 1. The group-relative excess term responds more
strongly when a flow's RTT is above the group threshold. The target is clamped
to [0.05, 1]. To avoid abrupt
changes, the applied factor follows continuous-time exponential smoothing:

  q(t + dt) = q(t) + (1 - exp(-dt / tau)) * (q_target - q(t))
  tau = 0.01 seconds

This solution is the exact first-order response of
`dq/dt = (q_target - q)/tau` for a constant target over an interval. Its
interpolation coefficient lies in [0,1], so the factor remains between its
prior value and the bounded target. The adjusted BDP is checked for
finiteness/non-negativity, and the final in-flight target is bounded to a
positive uint32 range. The `BdpReduction` trace source exposes the smoothed
factor.

The runner defaults to `RNG_SEED=1` and `RNG_RUN=1`; use identical values and
simulation arguments for all controller selections. For a paired comparison
without overwriting earlier project results, set `RESULTS_DIR` and `PLOTS_DIR`
to separate output paths for each run. After all runs, use:
  python3 scripts/compare_controllers.py --bbr <bbr-results> \
    --fairtt <fairtt-results> --enhanced <enhanced-results> --outdir <comparison-dir>

The metrics include both time-averaged and overall Jain fairness, aggregate
and per-flow throughput, and congestion-window variability. The window trace
is a proxy for the in-flight target, not a direct observation of bytes in
flight or the controller's estimated BDP.

## TcpBbrEnhancedFairttV2

V2 is a separate NS-3 TypeId; the baseline BBR, FaiRTT, and Enhanced FaiRTT
classes are unchanged. Its source/header are
`tcp-bbr-enhanced-fairtt-v2.cc` and `tcp-bbr-enhanced-fairtt-v2.h`.

Select it with:
  TCP_TYPE=TcpBbrEnhancedFairttV2 \
    RESULTS_DIR=<separate-results-dir> ./experiments/all_experiments.sh

V2 measures active path disparity from the distinct smoothed minimum RTTs:

  e = clamp((maxPathMinRTT - minPathMinRTT) / maxPathMinRTT, 0, 1)
  beta(e) = clamp(0.8 - 0.4*e, 0.2, 0.8)
  q = max(0, lastRTT/minRTT - 1)
  gamma(e,q) = clamp(0.99 - 0.25*e - 0.10*q, 0.55, 0.99)
  flowExcess = clamp((flowMinRTT - minPathMinRTT) /
                     (maxPathMinRTT - minPathMinRTT), 0, 1)
  response = e / (e + 0.15)
  strength = 0.70 + (1 - 0.70)*response*flowExcess
  target = 1 - strength*(1 - clamp(gamma*minRTT/lastRTT, 0.05, 1))
  S(t+dt) = exp(-dt/0.05)*S(t) + (1-exp(-dt/0.05))*target

The target is used in PROBE_BW only for positive current RTT above the group
mean minimum RTT. The 0.70 reduction floor retains queue-responsive behavior
for equal propagation RTTs; the normalized spread and flow's position in that
spread strengthen reductions for long-path flows. `MaxInflightBytes` defaults
to 524288 (512 KiB) and bounds BDP-derived in-flight/window targets. The
fairness floor, transition scale, smoothing time, and cap can be overridden
through the runner's `V2_FAIRNESS_FLOOR_STRENGTH`,
`V2_FAIRNESS_TRANSITION`, `V2_BDP_SMOOTHING_TIME_MS`, and
`V2_MAX_INFLIGHT_BYTES` settings.

V2 also exposes `BdpReduction`, `FairnessError`, and `ReductionStrength`
trace sources. The current experiment output records RTT and congestion
window; the congestion-window trace is only a stability proxy and not a
direct byte-level BDP measurement. V2's selected comparison, multi-seed
summary, and tuning log are stored separately under
`results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/`.

The in-flight cap also bounds the value returned by V2's `GetSsThresh`.
This is necessary because NS-3's fast-recovery exit assigns `m_ssThresh`
directly to `m_cWnd`, bypassing the controller's ordinary congestion-window
update. Capping the threshold stopped the UINT32-sized recovery-exit spike
without changing `TcpSocketBase` or the original BBR/FaiRTT controllers.
Three paired seeds improved different-RTT long-lived fairness over Enhanced
FaiRTT; equal-RTT and elephant/mice results were near baseline or slightly
lower. See the README's V2 comparison table and the CSV report for per-seed
values and sample variability; this is not evidence of generalization to
other topologies.
