# Enhanced FaiRTT in NS-3: Experiment Plan & Research Roadmap

## 1. Experimental Methodology (Stage 1 Baseline)

### 1.1 Network Architecture
The simulation implements an archetypal dumbbell bottleneck topology configured with 6 nodes:
- **Senders:** Sender A ($n_0$), Sender B ($n_1$)
- **Routers:** Router 1 ($n_2$), Router 2 ($n_3$)
- **Receivers:** Receiver A ($n_4$), Receiver B ($n_5$)

```
[Sender A: 10.1.1.1] ---\ (100 Mbps, 5ms)
                         ---> [Router 1: 10.2.1.1] === (10 Mbps, 10ms, Fifo 100p) ===> [Router 2: 10.2.1.2] ---\ (100 Mbps, 5ms)
[Sender B: 10.1.2.1] ---/ (100 Mbps, Delay_B)                                                                  \---> [Receiver A: 10.3.1.2]
                                                                                                                \---> [Receiver B: 10.3.2.2]
```

### 1.2 Congestion Control Algorithm Used in Stage 1
- **Algorithm Active in Baseline:** `ns3::TcpCubic` (default Linux TCP congestion control, also supported: `ns3::TcpLinuxReno`, `ns3::TcpBbr`).
- **Rationale:** Establishing a benchmark with TCP Cubic provides a rigorous, verified standard for RTT fairness before modifying BBR internals in Stage 2. Loss-based congestion control algorithms like Cubic are known to exhibit the well-documented $RTT^{-0.75}$ to $RTT^{-1}$ throughput penalty.
- **Trace Hooks:** Directly tap into `ns3::TcpSocketBase::RTT`, `CongestionWindow`, and `ns3::QueueDisc::PacketsInQueue`.

---

## 2. Benchmark Experiments

### Experiment A: Homogeneous / Equal RTT Baseline
- **Goal:** Verify that when both competing flows possess identical propagation delays, the bottleneck capacity is allocated fairly.
- **Parameters:**
  - Flow A access delay: $5\text{ ms}$ (one-way edge) $\implies \text{Base } RTT \approx 40\text{ ms}$
  - Flow B access delay: $5\text{ ms}$ (one-way edge) $\implies \text{Base } RTT \approx 40\text{ ms}$
  - Bottleneck delay: $10\text{ ms}$ (one-way)
  - Bottleneck capacity: $10\text{ Mbps}$
- **Expected Outcome:** High Jain's Fairness Index ($J \approx 0.95 - 1.0$) with symmetric throughput sharing ($~4.8\text{ Mbps}$ each).

### Experiment B: Heterogeneous / Different RTT Benchmark
- **Goal:** Quantify the throughput disparity and fairness degradation when one flow experiences a substantially longer RTT.
- **Parameters:**
  - Flow A access delay: $5\text{ ms} \implies \text{Base } RTT_A \approx 40\text{ ms}$
  - Flow B access delay: $35\text{ ms} \implies \text{Base } RTT_B \approx 160\text{ ms}$
  - Delay ratio: $RTT_B / RTT_A = 4.0$
- **Expected Outcome:** Severe throughput imbalance favoring Flow A ($RTT \approx 40\text{ ms}$), with Flow B starved or receiving a significantly lower share, driving Jain's Fairness Index down.

---

## 3. Mathematical Metrics

1. **Instantaneous Throughput:**
   $$T_i(t) = \frac{\Delta \text{RxBytes}_i(t) \times 8}{\Delta t \times 10^6} \quad (\text{Mbps})$$

2. **Aggregate Bottleneck Throughput:**
   $$T_{\text{agg}}(t) = T_A(t) + T_B(t)$$

3. **Jain's Fairness Index:**
   $$J(t) = \frac{\left(\sum_{i=1}^n T_i(t)\right)^2}{n \sum_{i=1}^n T_i(t)^2} = \frac{(T_A(t) + T_B(t))^2}{2(T_A(t)^2 + T_B(t)^2)}$$
   - $J = 1.0$: Ideal equal sharing.
   - $J = 0.5$: Severe unfairness (one flow dominates completely).

---

## 4. Stage 2 Research & Implementation Roadmap

Once the Stage 1 baseline is verified:
1. **Instrument BBR:** Run identical experiments under `TcpBbr` to isolate the exact RTT-unfairness mechanism described in the FaiRTT paper.
2. **Implement FaiRTT Core:** Extend `ns3::TcpBbr` to implement BDP dynamic compensation.
3. **Enhancement 1 (EWMA Smoothed RTT):** Replace raw/noisy $RTprop$ min-filter with an EWMA-smoothed estimator during steady-state probing.
4. **Enhancement 2 (Adaptive $\beta, \gamma$):** Formulate load-aware adaptation for tuning factors.
5. **Enhancement 3 (Bounded Nonlinear BDP Adjustment):** Implement a mathematically justified, saturating nonlinear adjustment function:
   $$f(RTT) = \frac{1}{1 + \alpha (RTT / RTT_{\min})^\gamma}$$
   preventing unbounded inflation while preserving throughput and fairness.
