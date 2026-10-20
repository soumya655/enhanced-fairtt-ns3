# Enhanced FaiRTT in NS-3: Project Overview

## 1. Context and Motivation

Congestion control algorithms like Google's BBR (Bottleneck Bandwidth and Round-trip propagation time) estimate two fundamental physical parameters of a network path:
- **Bottleneck Bandwidth ($BtlBw$):** Max bandwidth observed over a moving time window.
- **Minimum Round-Trip Time ($RTprop$):** Minimum RTT observed over a moving time window.

Using these two values, BBR calculates the **Bandwidth-Delay Product (BDP)**:
$$\text{BDP} = BtlBw \times RTprop$$

However, when multiple flows with disparate round-trip times (RTTs) share a common bottleneck, standard BBR exhibits severe **RTT unfairness**:
- Long-RTT flows maintain larger in-flight queues and enter probe states less frequently.
- Depending on bottleneck buffer depth, either long-RTT flows dominate the queue and starve short-RTT flows, or short-RTT flows respond faster and consume an unfair share of bandwidth.

The research paper **"FaiRTT: An Empirical Approach for Enhanced RTT Fairness and Bottleneck Throughput in BBR" (IEEE ICC Workshops, 2024)** addresses this challenge by introducing an empirical BDP adjustment mechanism based on an inverse relationship with flow RTT.

Our proposed extension explores:
1. **Smoothed RTT estimation using EWMA** to prevent noisy transient spikes from skewing the fairness adjustment.
2. **Adaptive fairness-related parameters ($\beta$ and $\gamma$)** to tune responsiveness dynamically under varying network loads.
3. **An alternative bounded nonlinear BDP adjustment function** with justified mathematical properties (ensuring bounded adjustment, stability, and controlled sensitivity).

---

## 2. Stage 1 Objective

Before modifying the congestion control engine, Stage 1 establishes a **clean, modular, and fully reproducible baseline simulation framework** in NS-3.

### Core Goals:
- Build an accurate dumbbell topology (Sender A/B, Routers R1/R2, Receiver A/B).
- Guarantee simultaneous competing TCP flows through a single shared bottleneck.
- Make all networking and simulation parameters fully configurable via command-line arguments.
- Instrument fine-grained metric collection:
  - Time-series per-flow throughput
  - Aggregate bottleneck throughput
  - Jain's Fairness Index over time
  - End-to-end RTT traces
  - Bottleneck queue occupancy
- Establish two reproducible benchmark experiments:
  - **Experiment A:** Equal RTT baseline ($\approx 40\text{ ms}$).
  - **Experiment B:** Heterogeneous RTT benchmark ($\text{Flow A} \approx 40\text{ ms}$ vs $\text{Flow B} \approx 160\text{ ms}$, 1:4 ratio).
- Implement post-processing and visualization pipelines in Python.
- Prepare a clean, version-controlled project repository ready for Stage 2 (BBR and FaiRTT implementation).
