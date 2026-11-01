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
import json
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

        # Only flows with a sample at a timestamp are included. Inactive mice
        # have no rows, so taking the intersection would discard all samples.
        if flow_rates_by_time:
            sample_times = sorted({
                sample_time
                for rate_map in flow_rates_by_time.values()
                for sample_time in rate_map
            })
            if sample_times:
                aggregate = [
                    sum(rate_map[t] for rate_map in flow_rates_by_time.values() if t in rate_map)
                    for t in sample_times
                ]
                ax1.plot(sample_times, aggregate, color="#2ca02c",
                         linestyle="--", linewidth=1.8, label="Aggregate reported throughput")

            # Compute fairness among flows that reported a sample at each time.
            fairness_times, fairness_values = [], []
            for t in sample_times:
                values = [
                    rate_map[t]
                    for rate_map in flow_rates_by_time.values()
                    if t in rate_map
                ]
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

def plot_controller_comparison(bbr_dir, fairtt_dir, output_dir):
    """Compare BBR and FaiRTT metrics and time series for equal/different RTT."""
    scenarios = {
        "Equal RTT": "equal-rtt",
        "Different RTT": "different-rtt",
    }
    metrics_by_scenario = {}
    for label, scenario in scenarios.items():
        metrics_by_controller = {}
        for controller, root in (("TcpBbr", bbr_dir), ("TcpBbrFairtt", fairtt_dir)):
            metrics_path = os.path.join(root, "metrics", scenario, "metrics.json")
            if not os.path.isfile(metrics_path):
                raise FileNotFoundError(
                    f"Missing {controller} metrics for {scenario}: {metrics_path}"
                )
            with open(metrics_path, encoding="utf-8") as metrics_file:
                metrics_by_controller[controller] = json.load(metrics_file)
        metrics_by_scenario[label] = metrics_by_controller

    os.makedirs(output_dir, exist_ok=True)
    labels = list(scenarios)
    controller_names = ("TcpBbr", "TcpBbrFairtt")
    x_positions = list(range(len(labels)))
    width = 0.34

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for index, controller in enumerate(controller_names):
        offset = (index - 0.5) * width
        fairness = [
            metrics_by_scenario[label][controller]["overall_jains_index"]
            for label in labels
        ]
        aggregate = [
            metrics_by_scenario[label][controller]["aggregate_mean_mbps"]
            for label in labels
        ]
        axes[0].bar(
            [position + offset for position in x_positions],
            fairness,
            width,
            label=controller,
        )
        axes[1].bar(
            [position + offset for position in x_positions],
            aggregate,
            width,
            label=controller,
        )

    axes[0].set_title("Overall Jain's Fairness Index")
    axes[0].set_ylabel("Jain's index")
    axes[0].set_ylim(0, 1.05)
    axes[1].set_title("Mean Aggregate Throughput")
    axes[1].set_ylabel("Throughput (Mbps)")
    axes[1].axhline(10.0, color="#d62728", linestyle=":", label="Bottleneck capacity")
    for ax in axes:
        ax.set_xticks(x_positions, labels)
        ax.grid(axis="y")
        ax.legend()
    fig.suptitle("TcpBbr vs TcpBbrFairtt")
    fig.tight_layout()
    metrics_plot = os.path.join(output_dir, "tcpbbr_vs_tcpbbrfairtt_metrics.png")
    fig.savefig(metrics_plot, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated controller metrics comparison: {metrics_plot}")

    scenario = "different-rtt"
    fig, (throughput_ax, fairness_ax) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )
    for controller, root, style in (
        ("TcpBbr", bbr_dir, "-"),
        ("TcpBbrFairtt", fairtt_dir, "--"),
    ):
        throughput_path = os.path.join(root, "raw", scenario, "throughput.csv")
        rows = read_csv(throughput_path)
        if not rows:
            raise ValueError(f"Missing or empty throughput trace: {throughput_path}")
        times = [float(row["time"]) for row in rows]
        throughput_ax.plot(
            times,
            [float(row["flowA_mbps"]) for row in rows],
            linestyle=style,
            label=f"{controller} Flow A (short RTT)",
        )
        throughput_ax.plot(
            times,
            [float(row["flowB_mbps"]) for row in rows],
            linestyle=style,
            label=f"{controller} Flow B (long RTT)",
        )
        fairness_ax.plot(
            times,
            [float(row["fairness_index"]) for row in rows],
            linestyle=style,
            label=controller,
        )

    throughput_ax.axhline(10.0, color="#d62728", linestyle=":", label="Bottleneck capacity")
    throughput_ax.set_ylabel("Throughput (Mbps)")
    throughput_ax.set_title("Different-RTT Throughput")
    throughput_ax.grid(True)
    throughput_ax.legend()
    fairness_ax.axhline(1.0, color="#7f7f7f", linestyle=":")
    fairness_ax.set_xlabel("Time (seconds)")
    fairness_ax.set_ylabel("Jain's index")
    fairness_ax.set_ylim(-0.05, 1.05)
    fairness_ax.grid(True)
    fairness_ax.legend()
    fig.tight_layout()
    trace_plot = os.path.join(output_dir, "tcpbbr_vs_tcpbbrfairtt_different_rtt.png")
    fig.savefig(trace_plot, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated controller time-series comparison: {trace_plot}")

    comparison = {}
    for label, by_controller in metrics_by_scenario.items():
        comparison[label] = by_controller
    comparison_path = os.path.join(output_dir, "tcpbbr_vs_tcpbbrfairtt_metrics.json")
    with open(comparison_path, "w", encoding="utf-8") as comparison_file:
        json.dump(comparison, comparison_file, indent=2)
    print(f"[PLOT] Saved controller comparison metrics: {comparison_path}")

def main():
    parser = argparse.ArgumentParser(description="Plot simulation results.")
    parser.add_argument("--equal-rtt", help="Path to equal-rtt result directory (throughput.csv)")
    parser.add_argument("--diff-rtt", help="Path to different-rtt OR elephant/mice result directory")
    parser.add_argument("--elephant-mice-equal", help="Path to equal-RTT elephant/mice results")
    parser.add_argument("--elephant-mice-diff", help="Path to different-RTT elephant/mice results")
    parser.add_argument("--compare-bbr", help="TcpBbr result root containing raw/ and metrics/")
    parser.add_argument("--compare-fairtt", help="TcpBbrFairtt result root containing raw/ and metrics/")
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

    if args.elephant_mice_equal:
        plot_experiment_results(
            args.elephant_mice_equal,
            exp_title="Elephant/Mice (Equal RTT)",
            output_prefix=os.path.join(args.outdir, "elephant_mice_equal_rtt")
        )

    if args.elephant_mice_diff:
        plot_experiment_results(
            args.elephant_mice_diff,
            exp_title="Elephant/Mice (Different RTT)",
            output_prefix=os.path.join(args.outdir, "elephant_mice_different_rtt")
        )

    if args.equal_rtt and args.diff_rtt:
        cmp_path = os.path.join(args.outdir, "comparison_equal_vs_different_rtt.png")
        plot_cross_comparison(args.equal_rtt, args.diff_rtt, cmp_path)

    if args.compare_bbr and args.compare_fairtt:
        plot_controller_comparison(args.compare_bbr, args.compare_fairtt, args.outdir)

if __name__ == "__main__":
    main()
