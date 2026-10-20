# Enhanced FaiRTT in NS-3 — Stage 1 Baseline

[![NS-3 Version](https://img.shields.io/badge/NS--3-3--dev-blue.svg)](https://www.nsnam.org/)
[![License](https://img.shields.io/badge/License-GPLv2-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Stage-1%20Baseline%20Validated-success.svg)]()

## 1. Project Background

This project is an NS-3 implementation and research extension based on the paper:
> **“FaiRTT: An Empirical Approach for Enhanced RTT Fairness and Bottleneck Throughput in BBR”**  
> *IEEE International Conference on Communications (ICC) Workshops, 2024.*

### The Problem
Google's BBR (*Bottleneck Bandwidth and Round-trip propagation time*) estimates bottleneck bandwidth ($BtlBw$) and minimum round-trip time ($RTprop$) to modulate packet injection. However, when flows with different propagation delays share a bottleneck, BBR exhibits severe **RTT unfairness**: flows with longer RTTs maintain higher in-flight queues and enter probe states less frequently, or shorter RTT flows aggressively dominate the bottleneck depending on buffer sizing.

### Proposed Research Enhancements
Our extension to FaiRTT investigates:
1. **Smoothed RTT Estimation using EWMA:** Mitigating noisy transient RTT fluctuations in the BDP adjustment.
2. **Adaptive Fairness Parameters ($\beta$ and $\gamma$):** Dynamically adjusting tuning factors according to real-time network load and queuing conditions.
3. **Alternative Bounded Nonlinear BDP Adjustment Function:** Replacing heuristic linear-inverse adjustments with a mathematically justified, saturating nonlinear function ensuring bounded adaptation and stability.

---

## 2. Stage 1: Dumbbell Topology & Baseline Benchmarks

Before modifying BBR internals in Stage 2, Stage 1 builds a modular, reproducible dumbbell simulation in NS-3 to validate baseline TCP behavior, metric tracing, and cross-flow fairness.

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
- **Initial Congestion Control:** `ns3::TcpCubic` (configurable to `ns3::TcpLinuxReno` or `ns3::TcpBbr`).

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

### Prerequisites
- NS-3 installation (tested on NS-3 `3-dev` / 3.41+)
- Python 3 with `matplotlib` and `numpy` (available in virtual environments or system Python)

### Step 1: Clone or Navigate to the Workspace
```bash
cd /home/soumyadeep/Documents/CN-PROJECT/enhanced-fairtt-ns3
```

### Step 2: Run All Experiments & Generate Plots
Execute the master runner:
```bash
./experiments/run_experiments.sh
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

## 5. Experimental Results (Stage 1 Actual Simulation Data)

All data presented below is measured directly from NS-3 simulation runs.

### Summary Comparison Table

| Metric | Experiment A (Equal RTT: 40ms vs 40ms) | Experiment B (Different RTT: 40ms vs 160ms) | Impact of RTT Heterogeneity |
|:---|:---:|:---:|:---:|
| **Flow A Delay / Base RTT** | $5\text{ ms} \implies 40\text{ ms}$ | $5\text{ ms} \implies 40\text{ ms}$ | Identical base path |
| **Flow B Delay / Base RTT** | $5\text{ ms} \implies 40\text{ ms}$ | $35\text{ ms} \implies 160\text{ ms}$ | $4\times$ longer RTT |
| **Flow A Mean Throughput** | **$5.4568\text{ Mbps}$** | **$6.6774\text{ Mbps}$** | $+22.4\%$ throughput capture |
| **Flow B Mean Throughput** | **$4.2554\text{ Mbps}$** | **$2.9582\text{ Mbps}$** | $-30.5\%$ starvation effect |
| **Aggregate Bottleneck Throughput** | **$9.7122\text{ Mbps}$** ($97.1\%$ link utilization) | **$9.6356\text{ Mbps}$** ($96.4\%$ link utilization) | Bottleneck fully utilized in both |
| **Throughput Ratio ($T_A / T_B$)** | **$1.282$** (Near-equal) | **$2.257$** (Over $2:1$ advantage) | Unfairness amplified |
| **Time-Averaged Jain's Index** | **$0.9490$** | **$0.8163$** | Dropped by $0.1327$ |
| **Overall Jain's Fairness Index** | **$0.9849$** | **$0.8703$** | Severe fairness degradation |

---

## 6. Generated Visualizations

Plots are saved to `results/plots/`:
1. `equal_rtt_throughput_fairness.png` — Throughput and instantaneous fairness for Experiment A.
2. `equal_rtt_queue_occupancy.png` — Bottleneck queue depth for Experiment A.
3. `equal_rtt_rtt.png` — Measured RTT dynamics for Experiment A.
4. `different_rtt_throughput_fairness.png` — Throughput and instantaneous fairness for Experiment B.
5. `different_rtt_queue_occupancy.png` — Bottleneck queue depth for Experiment B.
6. `different_rtt_rtt.png` — Measured RTT dynamics for Experiment B (verifying ~40ms vs ~160ms).
7. `comparison_equal_vs_different_rtt.png` — Side-by-side comparison across experiments.

---

## 7. Next Steps: Stage 2 Implementation

1. Benchmark native `TcpBbr` in the established dumbbell testbed.
2. Develop the `TcpFaiRtt` model in NS-3 `src/internet/model/`.
3. Integrate EWMA RTT smoothing.
4. Implement adaptive $\beta, \gamma$ tuning.
5. Evaluate the proposed bounded nonlinear BDP adjustment function against standard BBR and original FaiRTT.
