# Enhanced FaiRTT in NS-3 — Controller Comparison

[![NS-3 Version](https://img.shields.io/badge/NS--3-3--dev-blue.svg)](https://www.nsnam.org/)
[![License](https://img.shields.io/badge/License-GPLv2-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/FaiRTT-Variant%20Integrated-blue.svg)]()

## 1. Project Background

This project is an NS-3 implementation and research extension based on the paper:
> **“FaiRTT: An Empirical Approach for Enhanced RTT Fairness and Bottleneck Throughput in BBR”**  
> *IEEE International Conference on Communications (ICC) Workshops, 2024.*

### The Problem
Google's BBR (*Bottleneck Bandwidth and Round-trip propagation time*) estimates bottleneck bandwidth ($BtlBw$) and minimum round-trip time ($RTprop$) to modulate packet injection. However, when flows with different propagation delays share a bottleneck, BBR exhibits severe **RTT unfairness**: flows with longer RTTs maintain higher in-flight queues and enter probe states less frequently, or shorter RTT flows aggressively dominate the bottleneck depending on buffer sizing.

### Implemented FaiRTT Variant
The separate `TcpBbrFairtt` controller applies the paper's PROBE_BW BDP
adjustment with fixed $\beta=0.8$ and $\gamma=0.99$. It uses a cumulative
Eq. 6 RTT history and a documented, dimensionally consistent interpretation
of the paper's ambiguous alpha threshold. This is an assumed variant, not a
paper-faithful reproduction. Adaptive beta/gamma and alternative nonlinear
adjustments are not implemented.

`TcpBbrEnhancedFairtt` is an additional, separate controller. It retains the
FaiRTT threshold calculation while adapting beta/gamma to the smoothed-to-minimum
RTT ratio and exponentially smoothing a bounded BDP reduction. The baseline
BBR and FaiRTT implementations remain separate.

---

## 2. Dumbbell Topology & Controller Benchmarks

The project provides a reproducible dumbbell simulation in NS-3 for baseline
TCP behavior, metric tracing, and cross-flow fairness comparisons.

### Network Architecture

The dumbbell topology consists of 6 nodes:
- **Senders:** Sender A (`10.1.1.1`), Sender B (`10.1.2.1`)
- **Routers:** Router 1 (`10.2.1.1`), Router 2 (`10.2.1.2`)
- **Receivers:** Receiver A (`10.3.1.2`), Receiver B (`10.3.2.2`)

```
Sender A (n0) ----- [100 Mbps, 5ms] -----\
                                          Router 1 (n2) === [10 Mbps, 10ms, FIFO 100p] ===> Router 2 (n3) ----- [100 Mbps, 5ms] -----> Receiver A (n4)
Sender B (n1) ----- [100 Mbps, DelayB] --/                                                                \----- [100 Mbps, DelayB] --> Receiver B (n5)
```

- **Flow A:** Sender A $\to$ Receiver A (Port `50001`)
- **Flow B:** Sender B $\to$ Receiver B (Port `50002`)
- **Shared Bottleneck:** Router 1 $\to$ Router 2 (10 Mbps, 10 ms delay, 100 packets FIFO queue).
- **Congestion Control:** `ns3::TcpBbr` by default in the experiment runner;
  configurable to `ns3::TcpBbrFairtt`, `ns3::TcpBbrEnhancedFairtt`, and other
  registered TCP controllers.

---

## 3. Repository Structure

```
enhanced-fairtt-ns3/
├── README.md                          # Project documentation and reproduction guide
├── .gitignore                         # Build and trace exclusion rules
├── scratch/
│   └── dumbbell-baseline.cc           # NS-3 C++ simulation source code
├── configs/
│   └── experiment-parameters.md       # Detailed parameter specification
├── experiments/
│   ├── run_experiments.sh             # Master execution script (runs both experiments & plots)
│   ├── equal-rtt/
│   │   └── run.sh                     # Experiment A runner (Equal RTT)
│   └── different-rtt/
│       └── run.sh                     # Experiment B runner (Different RTT)
├── scripts/
│   ├── calculate_fairness.py          # Jain's fairness calculation utility
│   └── plot_results.py                # Publication-quality plotting utility
├── results/
│   ├── raw/                           # CSV traces (throughput, RTT, cwnd, queue occupancy)
│   │   ├── equal-rtt/
│   │   └── different-rtt/
│   ├── metrics/                       # Summary JSON metrics
│   │   ├── equal-rtt/
│   │   └── different-rtt/
│   └── plots/                         # Generated high-resolution PNG charts
└── docs/
    ├── project-overview.md            # Research motivation and architectural plan
    └── experiment-plan.md             # Benchmark plan and Stage 2 roadmap
```

---

## 4. Quickstart & Reproduction

The experiment runner uses the unchanged `TcpBbr` baseline by default and stores
each controller's results separately under `results/<controller>/`. It creates
per-controller graphs under `results/plots/<controller>/`. After both algorithms
have been run, it also writes direct comparisons under
`results/plots/controller-comparison/`. The separate `TcpBbrFairtt` controller
implements the paper's PROBE_BW BDP adjustment using the explicitly documented
interpretation of its ambiguous alpha equation below. It is not an exact
reproduction of the paper. To select it explicitly:

```bash
TCP_TYPE=TcpBbrFairtt ./experiments/all_experiments.sh
```

Run all three controllers with identical explicit seeds and distinct result
directories, then generate the four-scenario comparison tables and plots:

```bash
RNG_SEED=1 RNG_RUN=1 TCP_TYPE=TcpBbr RESULTS_DIR=results/paired/TcpBbr \
  PLOTS_DIR=results/paired/plots ./experiments/all_experiments.sh
RNG_SEED=1 RNG_RUN=1 TCP_TYPE=TcpBbrFairtt RESULTS_DIR=results/paired/TcpBbrFairtt \
  PLOTS_DIR=results/paired/plots ./experiments/all_experiments.sh
RNG_SEED=1 RNG_RUN=1 TCP_TYPE=TcpBbrEnhancedFairtt \
  RESULTS_DIR=results/paired/TcpBbrEnhancedFairtt PLOTS_DIR=results/paired/plots \
  ./experiments/all_experiments.sh
python3 scripts/compare_controllers.py \
  --bbr results/paired/TcpBbr \
  --fairtt results/paired/TcpBbrFairtt \
  --enhanced results/paired/TcpBbrEnhancedFairtt \
  --outdir results/paired/plots/controller-comparison
```

The fixed-parameter `TcpBbrFairtt` controller uses `beta = 0.8` and
`gamma = 0.99` (not adaptive parameters). On each newly measured positive RTT sample, it updates the BBR
RTprop minimum and Eq. 6's cumulative history estimate. The first valid sample
initializes the estimate; later samples use
`WminRTT_t = 0.8 * (sum of prior minRTT samples / prior sample count) + 0.2 * minRTT_t`.
For each configured fairness group, alpha is the arithmetic mean of the exact-
distinct current per-flow `WminRTT` estimates. In PROBE_BW, if the latest RTT
sample exceeds alpha, the estimated BDP is multiplied by
`(minRTT * gamma) / lastRTT` before the existing BBR congestion-window gain is
applied.

This alpha definition is an explicit, user-approved interpretation—not the
paper's printed Eq. 5. Eq. 5's `W_t` is connected to a byte-valued window by
Eq. 7, while alpha is compared with an RTT; the printed units and summation
domain therefore do not define a consistent implementation. Eq. 6 history is
cumulative from the first RTT sample until the connection ends. The controller
also deliberately retains this NS-3 checkout's BBR gains, 10-second RTT filter,
and BBR-specific in-flight additive terms. The paper describes a different BBR
model and parameterization, so results must be described as this
paper-informed interpretation, not a validated paper reproduction. See
`Fairtt-implementation/README-fairtt-setup.txt` for the precise assumptions.
`RttFairnessGroup` defaults to 0; assign the same group to FaiRTT flows sharing
a bottleneck and different group IDs to unrelated bottlenecks.

### Enhanced FaiRTT equations and bounds

Compared with `TcpBbrFairtt`, the new controller keeps the inherited BBR
state machine and group-threshold calculation but changes the FaiRTT controls:
fixed beta becomes adaptive beta; fixed gamma becomes the RTT- and
group-excess-dependent gamma below; the immediate BDP multiplier becomes a
bounded exponential transition; and BDP/in-flight arithmetic is checked and
saturated before conversion to NS-3's uint32 window types. It also exposes a
`BdpReduction` trace source. No changes were made to the original BBR or
FaiRTT controller sources.

For `r = max(1, smoothedRTT / minRTT)` (using `r = 1` if either RTT is
unavailable), Enhanced FaiRTT uses:

```text
beta(r)  = max(0.2, 0.8 / (1 + 0.005 * (r - 1)))
e        = max(0, lastRTT / alpha - 1)
gamma(r,e) = max(0.40, 0.99 - 0.02 * (r - 1) - 0.10 * e)
```

Beta is additionally capped at 1, and gamma at 0.99. The group-relative excess
`e` makes gamma more responsive to a flow whose RTT exceeds the group threshold.
The reduction target `q_target = gamma(r,e) * minRTT / lastRTT` is used only when `lastRTT > alpha`;
otherwise it is 1. It is bounded to [0.05, 1]. The applied reduction follows
the exact first-order exponential response
`q(t+dt) = q(t) + (1 - exp(-dt / 0.01s)) * (q_target - q(t))`.
The coefficient is bounded in [0,1], giving a continuous transition toward a
fixed target without overshoot. Non-finite/negative intermediate BDP values
are rejected, and the final in-flight target is clamped to a positive
`uint32_t` range. The `BdpReduction` trace source reports the applied factor.

### Prerequisites
- NS-3 installation (tested on NS-3 `3-dev` / 3.41+)
- Python 3 with `matplotlib` and `numpy` (available in virtual environments or system Python)

### Step 1: Clone or Navigate to the Workspace
```bash
cd /home/soumyadeep/Documents/CN-PROJECT/enhanced-fairtt-ns3
```

### Step 2: Run All Experiments & Generate Plots
Execute the actual runner (it invokes the plotter when simulations complete):
```bash
./experiments/all_experiments.sh
```

Or run individual experiments directly:

#### Experiment A: Equal RTT (Flow A ~40ms, Flow B ~40ms)
```bash
./experiments/equal-rtt/run.sh
```

#### Experiment B: Different RTT (Flow A ~40ms, Flow B ~160ms)
```bash
./experiments/different-rtt/run.sh
```

---

## 5. Paired Simulation Results

All three controllers used the same six-node topology, traffic, 30-second
duration, seed/run (1/1), and active analysis window (2–29 seconds). The
baseline and fixed FaiRTT outputs are under `results/paired-evaluation/`;
the final Enhanced FaiRTT run is under `results/paired-evaluation-final/`.

| Scenario | Controller | Aggregate Mbps | Time-averaged Jain | Overall Jain |
|:---|:---|---:|---:|---:|
| Equal RTT, two flows | `TcpBbr` | 9.4954 | 0.9998 | 1.0000 |
| Equal RTT, two flows | `TcpBbrFairtt` | 9.4954 | 0.9991 | 0.9994 |
| Equal RTT, two flows | `TcpBbrEnhancedFairtt` | 9.4959 | 0.9997 | 1.0000 |
| Different RTT, two flows | `TcpBbr` | 9.3703 | 0.6618 | 0.6560 |
| Different RTT, two flows | `TcpBbrFairtt` | 9.3575 | 0.8030 | 0.8947 |
| Different RTT, two flows | `TcpBbrEnhancedFairtt` | 9.3924 | 0.8776 | 0.9222 |
| Equal RTT, elephant/mice | `TcpBbr` | 9.4788 | 0.9473 | 0.3714 |
| Equal RTT, elephant/mice | `TcpBbrFairtt` | 9.4762 | 0.9619 | 0.4320 |
| Equal RTT, elephant/mice | `TcpBbrEnhancedFairtt` | 9.4724 | 0.9583 | 0.4124 |
| Different RTT, elephant/mice | `TcpBbr` | 9.4792 | 0.9025 | 0.2875 |
| Different RTT, elephant/mice | `TcpBbrFairtt` | 9.4797 | 0.9026 | 0.2875 |
| Different RTT, elephant/mice | `TcpBbrEnhancedFairtt` | 9.4792 | 0.8989 | 0.2834 |

Compared with FaiRTT, Enhanced FaiRTT increased different-RTT long-lived
time-averaged fairness by 0.0746 and overall Jain fairness by 0.0275, while
raising aggregate throughput by 0.0349 Mbps. Mean Flow A / Flow B throughput
was 3.3325 / 6.0599 Mbps, versus 3.0736 / 6.2839 Mbps for FaiRTT. Equal-RTT
long-lived results were effectively preserved. However, the two elephant/mice
scenarios regressed slightly in fairness: time-averaged Jain changed by
-0.0036 (equal RTT) and -0.0037 (different RTT); their aggregate throughput
changed by -0.0038 and -0.0005 Mbps, respectively. Overall, the tuning
improved the target long-lived different-RTT case but did not eliminate
regressions in every traffic mix.

The overall Jain value for elephant/mice is computed from each flow's mean
rate over its sampled active rows; time-averaged fairness includes flows
present at each timestamp. These values are not directly comparable to a
fixed set of continuously active flows. The results are one paired seed, not
a general performance guarantee.

### Tuning record

The proposed starting values were tested first. Each row used the same
different-RTT long-lived scenario and measurement window:

| Trial | Parameter change | Time-averaged Jain | Overall Jain | Aggregate Mbps |
|:---|:---|---:|---:|---:|
| Initial | Proposed beta/gamma, 200 ms smoothing | 0.7073 | 0.7405 | 9.2970 |
| 2 | `gamma_min=0.80`, `k_gamma=0.05`, `tau=30 ms` | 0.7742 | 0.8063 | 9.3758 |
| 3 | `gamma_min=0.65`, `k_gamma=0.15`, `tau=15 ms` | 0.8072 | 0.8346 | 9.3903 |
| 4 | `gamma_min=0.50`, `k_gamma=0.20`, `k_beta=0.02` | 0.8371 | 0.8799 | 9.4065 |
| 5 | `gamma_min=0.40`, `k_gamma=0.25`, `k_beta=0.005` | 0.8500 | 0.9097 | 9.3916 |
| Final | Group-relative RTT excess term in gamma | 0.8776 | 0.9222 | 9.3924 |

The ratio-only gamma trials could penalize a queue-heavy short-RTT flow more
than a long-propagation flow. The final gamma therefore also responds to
`max(0, lastRTT / alpha - 1)`. It improved the different-RTT long-lived case
and restored equal-RTT results, but the elephant/mice regressions remain.

Congestion-window stability uses the recorded `cwnd.csv` traces resampled at
0.2-second intervals. In the different-RTT long-lived case, Flow B's
congestion-window coefficient of variation was 11.5379 for FaiRTT and 0.4225
for Enhanced FaiRTT; mean absolute relative step was 78.1647 versus 0.5832.
This window is an in-flight-target proxy, not a direct BDP or bytes-in-flight
measurement; the unusually large FaiRTT transient is visible in the raw
trace.

Raw traces, run summaries, and per-controller metrics include the selected
`tcpTypeId`. The comparison output includes overall and time-averaged Jain
indices, aggregate/per-flow throughput, fixed-interval congestion-window
stability, and plots.

---

## 6. Generated Visualizations

Per-controller throughput/fairness, queue, and RTT graphs for BBR and FaiRTT
are under `results/paired-evaluation/plots/`; Enhanced FaiRTT's are under
`results/paired-evaluation-final/plots/TcpBbrEnhancedFairtt/`. The three-way
comparison is under
`results/paired-evaluation-final/plots/controller-comparison/`:
- `controller-metrics-comparison.png` compares both Jain metrics and
  aggregate throughput across all four scenarios.
- `*-per-flow-throughput.png` and `*-cwnd-stability.png` show per-scenario
  throughput and congestion-window traces.
- `controller-comparison.csv` and `.json` contain the full metric table;
  `per-flow-throughput.csv` and `cwnd-stability.csv` provide normalized
  long-form data.

---

## 7. Limitations and Further Validation

- Repeat the comparisons across multiple random seeds and bottleneck/buffer
  configurations; the table reports one paired seed.
- The alpha threshold is an explicit assumption because the paper's printed
  Eq. 5/Eq. 7 do not define dimensionally consistent units and a clear sample
  domain. The current controller must not be presented as a paper-faithful
  reproduction.
- This variant preserves the existing NS-3 BBR clone's gain schedule,
  10-second RTprop expiry, 200-ms PROBE_RTT duration, and in-flight additive
  terms; these differ from the paper's described BBR model/parameterization.
- The final adaptive gamma includes an empirical group-relative RTT term.
  Validate its parameters across other topologies/seeds before drawing general
  conclusions about fairness or throughput.

## 8. Enhanced FaiRTT V2

`TcpBbrEnhancedFairttV2` is a separate controller and leaves BBR, FaiRTT, and
the current Enhanced FaiRTT implementation selectable as independent
baselines. Its source/header are
[`tcp-bbr-enhanced-fairtt-v2.cc`](./Fairtt-implementation/tcp-bbr-enhanced-fairtt-v2.cc)
and
[`tcp-bbr-enhanced-fairtt-v2.h`](./Fairtt-implementation/tcp-bbr-enhanced-fairtt-v2.h).

V2 computes its normalized fairness error from active controllers' distinct,
smoothed minimum-RTT observations:

```text
e = clamp((maxPathMinRTT - minPathMinRTT) / maxPathMinRTT, 0, 1)
beta(e) = clamp(0.8 - 0.4*e, 0.2, 0.8)
q = max(0, lastRTT/minRTT - 1)
gamma(e,q) = clamp(0.99 - 0.25*e - 0.10*q, 0.55, 0.99)
flowExcess = clamp((flowMinRTT - minPathMinRTT) /
                   (maxPathMinRTT - minPathMinRTT), 0, 1)
response = e / (e + 0.15)
strength = 0.70 + (1 - 0.70)*response*flowExcess
raw = clamp(gamma*minRTT/lastRTT, 0.05, 1)
target = 1 - strength*(1 - raw)
S_t = exp(-dt/0.05)*S_(t-1) + (1-exp(-dt/0.05))*target
```

The target is applied in PROBE_BW only when the current RTT is positive and
above the group's mean distinct smoothed minimum RTT; otherwise its target is
1 (no reduction). Missing/non-positive RTT samples produce a neutral fairness
error, and all reduction and in-flight targets are bounded.

The `0.70` floor retains some queue-responsive behavior when propagation RTTs
are equal (useful when finite mice arrive alongside an elephant); the
normalized path-RTT error and each flow's relative RTT position increase the
reduction for persistently longer paths. Queue inflation remains an explicit
gamma input rather than being mistaken for path disparity. The exponential
response has a 50 ms time constant. `MaxInflightBytes` defaults to 512 KiB,
which is about 2.6 times the 10 Mbps, 160 ms path BDP in this experiment; it
bounds BDP-derived in-flight/window targets and prevents UINT32 saturation
from producing multi-million-packet congestion windows. The cap also applies
to V2's `GetSsThresh`: NS-3 assigns the slow-start threshold directly to the
congestion window on fast-recovery exit, bypassing normal controller window
updates. The floor,
transition scale, smoothing time, and cap are TypeId attributes and exposed
through the experiment runner.

Initial V2 trials exposed a congestion-window spike even after limiting
BDP-derived targets and normal controller updates. NS-3's fast-recovery exit
assigns `m_ssThresh` directly to `m_cWnd`; V2's inherited threshold could
still be `UINT32_MAX`. V2 now caps the threshold returned by `GetSsThresh` as
well. No socket-base, BBR, FaiRTT, or Enhanced FaiRTT source was changed for
this fix. In the selected runs, the largest V2 congestion-window sample in
the different-RTT long-lived scenario was 362.1 packets (512 KiB divided by
the configured segment size), rather than the previous multi-million-packet
spike. `FairnessError` reports group RTT disparity even on samples where the
reduction condition is inactive.

### Three-seed comparison

The table gives mean metrics for seeds/runs 1/1, 2/2, and 3/3. V2 deltas are
relative to Enhanced FaiRTT. The one-seed original baseline artifacts for
seed 1 predate explicit seed metadata; their runner defaults were seed/run
1/1. All seed-2 and seed-3 controller runs record and verify their explicit
seed/run values. Three seeds are useful evidence but are not enough to claim
generalization.

| Scenario | Enhanced time Jain / overall Jain / Mbps | V2 time Jain / overall Jain / Mbps | V2 delta time Jain / overall Jain / Mbps |
|:---|---:|---:|---:|
| Equal RTT, long-lived | 0.999167 / 0.999733 / 9.496167 | 0.998000 / 0.999833 / 9.498000 | -0.001167 / +0.000100 / +0.001833 |
| Different RTT, long-lived | 0.867233 / 0.910900 / 9.395533 | 0.887433 / 0.949300 / 9.431133 | +0.020200 / +0.038400 / +0.035600 |
| Equal RTT, elephant/mice | 0.959433 / 0.417467 / 9.526500 | 0.958300 / 0.411467 / 9.505633 | -0.001133 / -0.006000 / -0.020867 |
| Different RTT, elephant/mice | 0.901367 / 0.286133 / 9.479500 | 0.900133 / 0.284767 / 9.479067 | -0.001233 / -0.001366 / -0.000433 |

The different-RTT long-lived fairness and throughput gains were positive in
all three paired seed comparisons. V2's mean Flow B congestion-window
coefficient of variation in that scenario was 0.4310, essentially the same
as Enhanced FaiRTT's 0.4306; its mean absolute relative step was lower
(0.4468 versus 0.5818). Equal-RTT long-lived flows remained nearly fair.
Elephant/mice differences were small and mixed: V2 is slightly lower on
fairness on average, while seed-level variation—especially equal-RTT
elephant/mice overall fairness and aggregate throughput—is large enough that
the three-seed result is inconclusive rather than a reliable regression or
improvement. The congestion-window trace is an in-flight proxy, not a direct
measurement of bytes in flight or estimated BDP.

The complete four-controller tables, per-flow results, sample standard
deviations, congestion-window stability results, and tuning log are in
[`results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/`](./results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/).
This includes
[`seed-aggregate-comparison.csv`](./results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/seed-aggregate-comparison.csv),
[`seed-aggregate-per-flow.csv`](./results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/seed-aggregate-per-flow.csv),
[`seed-aggregate-cwnd-stability.csv`](./results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/seed-aggregate-cwnd-stability.csv),
[`v2-experiment-log.csv`](./results/paired-evaluation-v2-final/recoverycap-ssthresh/paired-reports/v2-experiment-log.csv),
and the corresponding PNG plots. A seed-1 detailed comparison is also saved
under `paired-reports/seed1/`.

The earlier floor-0.35 and capped floor-0.70 experiments are retained as
tuning trials, not selected results. An attempted seed-2 batch that passed
only NS-3 global seed options was invalid because the topology overwrote them
with its own defaults; it is excluded from all multi-seed summaries.
V2 exposes `BdpReduction`, `FairnessError`, and `ReductionStrength` trace
sources; the saved congestion-window time series remains an in-flight proxy,
not a direct byte-level BDP trace. The V2 runs use the same four topologies,
traffic, duration, and analysis window as the earlier comparison; the runner
passes `RNG_SEED`/`RNG_RUN` to the topology's actual `--seed`/`--run` options.
