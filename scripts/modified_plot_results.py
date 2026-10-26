#!/usr/bin/env python3
"""
plot_results.py
Enhanced FaiRTT in NS-3 — Stage 1 Plotting Utility

Generates publication-quality charts for:
1. Per-flow and aggregate throughput vs. time
2. Jain's fairness index vs. time
3. Bottleneck queue occupancy vs. time
4. Measured RTT vs. time
5. Cross-experiment comparison (Equal RTT vs Different RTT)
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg") # Non-interactive backend
import matplotlib.pyplot as plt

# Styling configuration
plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "grid.alpha": 0.4,
    "grid.linestyle": "--"
})

def read_csv(filepath):
    if not os.path.exists(filepath):
        return None
    rows = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def plot_experiment_results(exp_dir, exp_title="Experiment Results", output_prefix=None):
    if output_prefix is None:
        output_prefix = os.path.join(exp_dir, "plot")

    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)

    # 1. Throughput & Fairness
    # Legacy two-flow output: throughput.csv
    tp_file = os.path.join(exp_dir, "throughput.csv")
    tp_rows = read_csv(tp_file)

    # Elephant/mice output is long-form:
    # time,flow,throughput_mbps,cumulative_rx_bytes
    em_file = os.path.join(exp_dir, "elephant_mice_throughput.csv")
    em_rows = read_csv(em_file)

    if em_rows:
        # Group each flow's samples without assuming a fixed number of mice.
        flows = {}
        for row in em_rows:
            flow_name = row.get("flow", "").strip()
            if not flow_name:
                continue
            flows.setdefault(flow_name, []).append({
                "time": float(row["time"]),
                "throughput_mbps": float(row["throughput_mbps"]),
                "cumulative_rx_bytes": float(row.get("cumulative_rx_bytes", 0) or 0),
            })

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(11, 7), sharex=True,
            gridspec_kw={"height_ratios": [2, 1]}
        )
        flow_rates_by_time = {}
        for flow_name, samples in sorted(flows.items()):
            samples.sort(key=lambda item: item["time"])
            tx = [s["time"] for s in samples]
            rates = [s["throughput_mbps"] for s in samples]
            flow_rates_by_time[flow_name] = dict(zip(tx, rates))
            ax1.plot(tx, rates, linewidth=1.5, label=f"{flow_name} throughput")

        # Sum per-flow rates only at timestamps shared by all active flow samples.
        # This is a visual aggregate of reported rates, not a link-capacity proof
        # if the source rows use different averaging windows.
        if flow_rates_by_time:
            shared_times = sorted(set.intersection(
                *(set(rate_map.keys()) for rate_map in flow_rates_by_time.values())
            )) if len(flow_rates_by_time) > 1 else sorted(next(iter(flow_rates_by_time.values())).keys())
            if shared_times:
                aggregate = [
                    sum(rate_map[t] for rate_map in flow_rates_by_time.values())
                    for t in shared_times
                ]
                ax1.plot(shared_times, aggregate, color="#2ca02c",
                         linestyle="--", linewidth=1.8, label="Aggregate reported throughput")

            # Compute Jain's index across flows at each timestamp where every flow
            # has a sample. A mouse that has not started yet is not silently treated
            # as an active zero-throughput flow.
            fairness_times, fairness_values = [], []
            for t in shared_times:
                values = [rate_map[t] for rate_map in flow_rates_by_time.values()]
                denom = len(values) * sum(v * v for v in values)
                fairness = (sum(values) ** 2 / denom) if denom > 0 else 1.0
                fairness_times.append(t)
                fairness_values.append(fairness)
            if fairness_times:
                ax2.plot(fairness_times, fairness_values,
                         label="Jain's Fairness Index (sampled flows)",
                         color="#9467bd", linewidth=1.8)

        ax1.axhline(y=10.0, color="#d62728", linestyle=":",
                    label="Bottleneck Capacity (10 Mbps)", alpha=0.8)
        ax1.set_ylabel("Throughput (Mbps)")
        ax1.set_title(f"{exp_title}: Elephant/Mice Throughput and Fairness vs. Time")
        ax1.legend(loc="upper right", framealpha=0.9)
        ax1.grid(True)
        ax1.set_ylim(bottom=0)
        ax2.axhline(y=1.0, color="#7f7f7f", linestyle=":", alpha=0.7)
        ax2.set_xlabel("Time (seconds)")
        ax2.set_ylabel("Jain's Index")
        ax2.set_ylim(-0.05, 1.05)
        ax2.legend(loc="lower right", framealpha=0.9)
        ax2.grid(True)
        plt.tight_layout()
        tp_out = f"{output_prefix}_throughput_fairness.png"
        plt.savefig(tp_out, dpi=300)
        plt.close()
        print(f"[PLOT] Generated elephant/mice plot: {tp_out}")

    elif tp_rows:
        # Standard equal-RTT / different-RTT experiment.
        time = [float(r["time"]) for r in tp_rows]
        flowA = [float(r["flowA_mbps"]) for r in tp_rows]
        flowB = [float(r["flowB_mbps"]) for r in tp_rows]
        agg = [float(r["aggregate_mbps"]) for r in tp_rows]
        fairness = [float(r["fairness_index"]) for r in tp_rows]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(time, flowA, label="Flow A Throughput", color="#1f77b4", linewidth=2.0)
        ax1.plot(time, flowB, label="Flow B Throughput", color="#ff7f0e", linewidth=2.0)
        ax1.plot(time, agg, label="Aggregate Throughput", color="#2ca02c", linestyle="--", linewidth=1.8)
        ax1.axhline(y=10.0, color="#d62728", linestyle=":", label="Bottleneck Capacity (10 Mbps)", alpha=0.8)
        ax1.set_ylabel("Throughput (Mbps)")
        ax1.set_title(f"{exp_title}: Throughput and Fairness vs. Time")
        ax1.legend(loc="upper right", framealpha=0.9)
        ax1.grid(True)
        ax1.set_ylim(bottom=0)

        ax2.plot(time, fairness, label="Jain's Fairness Index", color="#9467bd", linewidth=2.0)
        ax2.axhline(y=1.0, color="#7f7f7f", linestyle=":", alpha=0.7)
        ax2.set_xlabel("Time (seconds)")
        ax2.set_ylabel("Jain's Index")
        ax2.set_ylim(-0.05, 1.05)
        ax2.legend(loc="lower right", framealpha=0.9)
        ax2.grid(True)

        plt.tight_layout()
        tp_out = f"{output_prefix}_throughput_fairness.png"
        plt.savefig(tp_out, dpi=300)
        plt.close()
        print(f"[PLOT] Generated: {tp_out}")

    # 2. Queue Occupancy
    q_file = os.path.join(exp_dir, "queue_occupancy.csv")
    q_rows = read_csv(q_file)
    if q_rows:
        time = [float(r["time"]) for r in q_rows]
        q_packets = [float(r["queue_packets"]) for r in q_rows]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(time, q_packets, color="#d62728", linewidth=1.8, label="Bottleneck Queue (packets)")
        ax.axhline(y=100.0, color="black", linestyle="--", alpha=0.7, label="Max Queue Limit (100 packets)")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Queue Depth (packets)")
        ax.set_title(f"{exp_title}: Bottleneck Queue Occupancy")
        ax.legend(loc="upper right")
        ax.grid(True)
        ax.set_ylim(bottom=0)

        plt.tight_layout()
        q_out = f"{output_prefix}_queue_occupancy.png"
        plt.savefig(q_out, dpi=300)
        plt.close()
        print(f"[PLOT] Generated: {q_out}")

    # 3. RTT
    rtt_file = os.path.join(exp_dir, "rtt.csv")
    rtt_rows = read_csv(rtt_file)
    if rtt_rows:
        time_a, rtt_a = [], []
        time_b, rtt_b = [], []
        for r in rtt_rows:
            if r["flow"] == "FlowA":
                time_a.append(float(r["time"]))
                rtt_a.append(float(r["rtt_ms"]))
            elif r["flow"] == "FlowB":
                time_b.append(float(r["time"]))
                rtt_b.append(float(r["rtt_ms"]))

        fig, ax = plt.subplots(figsize=(10, 4.5))
        if time_a:
            ax.plot(time_a, rtt_a, label="Flow A Measured RTT", color="#1f77b4", linewidth=1.5, alpha=0.85)
        if time_b:
            ax.plot(time_b, rtt_b, label="Flow B Measured RTT", color="#ff7f0e", linewidth=1.5, alpha=0.85)
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Measured RTT (ms)")
        ax.set_title(f"{exp_title}: Measured Round-Trip Time")
        ax.legend(loc="best")
        ax.grid(True)
        ax.set_ylim(bottom=0)

        plt.tight_layout()
        rtt_out = f"{output_prefix}_rtt.png"
        plt.savefig(rtt_out, dpi=300)
        plt.close()
        print(f"[PLOT] Generated: {rtt_out}")

def plot_cross_comparison(equal_rtt_dir, diff_rtt_dir, output_path):
    rows_eq = read_csv(os.path.join(equal_rtt_dir, "throughput.csv"))
    rows_diff = read_csv(os.path.join(diff_rtt_dir, "throughput.csv"))

    if not rows_eq or not rows_diff:
        print("[WARN] Cannot generate comparison plot: missing throughput.csv in one of the directories.")
        return

    t_eq = [float(r["time"]) for r in rows_eq]
    fa_eq = [float(r["flowA_mbps"]) for r in rows_eq]
    fb_eq = [float(r["flowB_mbps"]) for r in rows_eq]
    j_eq = [float(r["fairness_index"]) for r in rows_eq]

    t_diff = [float(r["time"]) for r in rows_diff]
    fa_diff = [float(r["flowA_mbps"]) for r in rows_diff]
    fb_diff = [float(r["flowB_mbps"]) for r in rows_diff]
    j_diff = [float(r["fairness_index"]) for r in rows_diff]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex="col", sharey="row")

    # Column 0: Equal RTT
    axes[0, 0].plot(t_eq, fa_eq, label="Flow A (RTT ~ 40ms)", color="#1f77b4", linewidth=1.8)
    axes[0, 0].plot(t_eq, fb_eq, label="Flow B (RTT ~ 40ms)", color="#ff7f0e", linewidth=1.8)
    axes[0, 0].axhline(y=10.0, color="#d62728", linestyle=":", label="Capacity (10 Mbps)", alpha=0.7)
    axes[0, 0].set_title("Experiment A: Equal RTT (40ms vs 40ms)")
    axes[0, 0].set_ylabel("Throughput (Mbps)")
    axes[0, 0].legend(loc="upper right", framealpha=0.9)
    axes[0, 0].grid(True)
    axes[0, 0].set_ylim(0, 11)

    axes[1, 0].plot(t_eq, j_eq, label="Jain's Index", color="#9467bd", linewidth=1.8)
    axes[1, 0].axhline(y=1.0, color="gray", linestyle=":", alpha=0.7)
    axes[1, 0].set_xlabel("Time (seconds)")
    axes[1, 0].set_ylabel("Jain's Fairness Index")
    axes[1, 0].set_ylim(0, 1.05)
    axes[1, 0].legend(loc="lower right")
    axes[1, 0].grid(True)

    # Column 1: Different RTT
    axes[0, 1].plot(t_diff, fa_diff, label="Flow A (RTT ~ 40ms)", color="#1f77b4", linewidth=1.8)
    axes[0, 1].plot(t_diff, fb_diff, label="Flow B (RTT ~ 160ms)", color="#e377c2", linewidth=1.8)
    axes[0, 1].axhline(y=10.0, color="#d62728", linestyle=":", label="Capacity (10 Mbps)", alpha=0.7)
    axes[0, 1].set_title("Experiment B: Different RTT (40ms vs 160ms)")
    axes[0, 1].legend(loc="upper right", framealpha=0.9)
    axes[0, 1].grid(True)
    axes[0, 1].set_ylim(0, 11)

    axes[1, 1].plot(t_diff, j_diff, label="Jain's Index", color="#9467bd", linewidth=1.8)
    axes[1, 1].axhline(y=1.0, color="gray", linestyle=":", alpha=0.7)
    axes[1, 1].set_xlabel("Time (seconds)")
    axes[1, 1].set_ylim(0, 1.05)
    axes[1, 1].legend(loc="lower right")
    axes[1, 1].grid(True)

    plt.suptitle("Comparison: Equal RTT vs Heterogeneous RTT Bottleneck Competition", fontsize=15, y=0.98)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"[PLOT] Generated Cross-Comparison: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Plot simulation results.")
    parser.add_argument("--equal-rtt", help="Path to equal-rtt result directory (throughput.csv)")
    parser.add_argument("--diff-rtt", help="Path to different-rtt OR elephant/mice result directory")
    parser.add_argument("--outdir", default="results/plots", help="Output directory for plots")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.equal_rtt:
        plot_experiment_results(
            args.equal_rtt,
            exp_title="Experiment A (Equal RTT)",
            output_prefix=os.path.join(args.outdir, "equal_rtt")
        )

    if args.diff_rtt:
        plot_experiment_results(
            args.diff_rtt,
            exp_title="Experiment B (Different RTT)",
            output_prefix=os.path.join(args.outdir, "different_rtt")
        )

    if args.equal_rtt and args.diff_rtt:
        cmp_path = os.path.join(args.outdir, "comparison_equal_vs_different_rtt.png")
        plot_cross_comparison(args.equal_rtt, args.diff_rtt, cmp_path)

if __name__ == "__main__":
    main()
