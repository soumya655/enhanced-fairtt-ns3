# Simulation and Experiment Parameters

This document specifies the parameter sets for the Stage 1 baseline dumbbell topology simulations.

## Topologies and Links

The dumbbell network consists of 6 nodes:
- Sender A (`10.1.1.1`) and Sender B (`10.1.2.1`)
- Router 1 (`10.1.1.2`, `10.1.2.2`, `10.2.1.1`)
- Router 2 (`10.2.1.2`, `10.3.1.1`, `10.3.2.1`)
- Receiver A (`10.3.1.2`) and Receiver B (`10.3.2.2`)

```
Sender A (n0) ----- [Access Link A] -----\
                                          Router 1 (n2) === [Bottleneck Link] === Router 2 (n3) ----- [Access Link A] -----> Receiver A (n4)
Sender B (n1) ----- [Access Link B] -----/                                                      \----- [Access Link B] -----> Receiver B (n5)
```

## Parameter Matrix

| Parameter | CLI Flag | Default Value | Experiment A (Equal RTT) | Experiment B (Different RTT) | Description |
|:---|:---|:---|:---|:---|:---|
| Bottleneck Bandwidth | `--bottleneckBw` | `10Mbps` | `10Mbps` | `10Mbps` | Shared bottleneck data rate |
| Bottleneck Delay | `--bottleneckDelay` | `10ms` | `10ms` | `10ms` | One-way propagation delay of bottleneck |
| Access Link Bandwidth | `--accessBw` | `100Mbps` | `100Mbps` | `100Mbps` | Non-bottleneck edge link data rate |
| Flow A Access Delay | `--accessDelayA` | `5ms` | `5ms` | `5ms` | One-way edge delay for Flow A (both sides) |
| Flow B Access Delay | `--accessDelayB` | `5ms` | `5ms` | `35ms` | One-way edge delay for Flow B (both sides) |
| Bottleneck Queue Disc | `--queueDisc` | `FifoQueueDisc` | `FifoQueueDisc` | `FifoQueueDisc` | Queuing discipline on bottleneck interface |
| Bottleneck Queue Size | `--queueSize` | `100p` | `100p` | `100p` | Maximum queue size (e.g., packets) |
| Congestion Control | `--tcpTypeId` | `TcpCubic` | `TcpCubic` | `TcpCubic` | Configurable: `TcpCubic`, `TcpLinuxReno`, `TcpBbr` |
| Total Simulation Time | `--simTime` | `30s` | `30s` | `30s` | Duration of simulation run |
| Flow A Start / Stop | `--flowAStart`, `--flowAStop` | `1.0s` / `29.0s` | `1.0s` / `29.0s` | `1.0s` / `29.0s` | Application active window for Flow A |
| Flow B Start / Stop | `--flowBStart`, `--flowBStop` | `1.0s` / `29.0s` | `1.0s` / `29.0s` | `1.0s` / `29.0s` | Application active window for Flow B |
| Sampling Interval | `--samplingInterval`| `0.2s` | `0.2s` | `0.2s` | Frequency of throughput and queue logging |
| Output Directory | `--outDir` | `results` | `results/equal-rtt` | `results/different-rtt` | Destination directory for CSV traces |
| Random Seed | `--seed` | `1` | `1` | `1` | NS-3 RngSeedManager seed value |

## Expected End-to-End RTTs

### Experiment A (Equal RTT):
- One-way propagation delay: $\text{accessDelayA} + \text{bottleneckDelay} + \text{accessDelayA} = 5 + 10 + 5 = 20\text{ ms}$.
- Round-Trip Time (base $RTT$ without queuing): $2 \times 20\text{ ms} = 40\text{ ms}$.
- Flow A and Flow B have identical theoretical minimum RTT ($40\text{ ms}$).

### Experiment B (Different RTT):
- Flow A: One-way $5 + 10 + 5 = 20\text{ ms} \implies RTT_A \approx 40\text{ ms}$.
- Flow B: One-way $35 + 10 + 35 = 80\text{ ms} \implies RTT_B \approx 160\text{ ms}$.
- Theoretical RTT ratio is $4:1$.
