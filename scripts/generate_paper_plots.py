#!/usr/bin/env python3
"""
generate_paper_plots.py
Generates the publication-quality figures matching the IEEE ICC 2024 paper:
- Fig. 3(a): Throughput vs. Time (Flow A / Flow B / Aggregate) across all controllers
- Fig. 4(a): Jain's Fairness Index vs. Time across all controllers
- Fig. 5: Bottleneck Link Utilization (%) vs. Time across all controllers
- Comprehensive Paper Dashboard: Multi-panel comparative evaluation
"""

import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Consistent styling matching IEEE publication standards
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "grid.alpha": 0.35,
    "grid.linestyle": "--"
})

CONTROLLERS = [
    ("TcpBbr", "BBR", "#1f77b4", "-"),
    ("TcpBbrFairtt", "FaiRTT", "#ff7f0e", "--"),
    ("TcpBbrEnhancedFairtt", "Enhanced FaiRTT (v1)", "#2ca02c", "-."),
    ("TcpBbrEnhancedFairttV2", "Enhanced FaiRTT (V2)", "#d62728", "-")
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
OUT_DIR = os.path.join(RESULTS_DIR, "plots", "paper-comparison")
os.makedirs(OUT_DIR, exist_ok=True)

def load_scenario_throughput(scenario):
    data = {}
    for ctrl_id, ctrl_label, color, style in CONTROLLERS:
        path = os.path.join(RESULTS_DIR, ctrl_id, "raw", scenario, "throughput.csv")
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            t, fa, fb, agg, fair = [], [], [], [], []
            for row in reader:
                t.append(float(row["time"]))
                fa.append(float(row["flowA_mbps"]))
                fb.append(float(row["flowB_mbps"]))
                agg.append(float(row["aggregate_mbps"]))
                fair.append(float(row["fairness_index"]))
            data[ctrl_id] = {
                "label": ctrl_label,
                "color": color,
                "style": style,
                "time": np.array(t),
                "flowA": np.array(fa),
                "flowB": np.array(fb),
                "aggregate": np.array(agg),
                "fairness": np.array(fair),
                "utilization": np.array(agg) / 10.0 * 100.0  # 10 Mbps bottleneck
            }
    return data

def plot_paper_fig3a(data, scenario="different-rtt", outname="fig3a_paper_throughput_comparison.png"):
    """Fig. 3(a): Throughput vs. Time Comparison for Elephant vs. Mice / Flow A vs Flow B."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    # Upper panel: Short-RTT Flow (Flow A) & Long-RTT Flow (Flow B)
    for ctrl_id, d in data.items():
        linewidth = 2.0 if "V2" in ctrl_id else 1.5
        ax1.plot(d["time"], d["flowA"], label=f"{d['label']} (Short RTT 40ms)",
                 color=d["color"], linestyle=d["style"], linewidth=linewidth)
        ax2.plot(d["time"], d["flowB"], label=f"{d['label']} (Long RTT 160ms)",
                 color=d["color"], linestyle=d["style"], linewidth=linewidth)

    ax1.set_ylabel("Throughput (Mbps)")
    ax1.set_title("Fig. 3(a) Replica: Flow Throughput vs. Time (Short RTT Flow A ~ 40ms)")
    ax1.grid(True)
    ax1.set_ylim(0, 10)
    ax1.axhline(5.0, color="gray", linestyle=":", label="Fair Share (5.0 Mbps)")
    ax1.legend(loc="upper right", framealpha=0.9, ncol=2)

    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Throughput (Mbps)")
    ax2.set_title("Flow Throughput vs. Time (Long RTT Flow B ~ 160ms)")
    ax2.grid(True)
    ax2.set_ylim(0, 10)
    ax2.axhline(5.0, color="gray", linestyle=":", label="Fair Share (5.0 Mbps)")
    ax2.legend(loc="upper right", framealpha=0.9, ncol=2)

    plt.tight_layout()
    outpath = os.path.join(OUT_DIR, outname)
    plt.savefig(outpath, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {outpath}")

def plot_paper_fig4a(data, scenario="different-rtt", outname="fig4a_paper_fairness_index_comparison.png"):
    """Fig. 4(a): Jain's Fairness Index vs. Time Comparison."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for ctrl_id, d in data.items():
        linewidth = 2.4 if "V2" in ctrl_id else 1.6
        ax.plot(d["time"], d["fairness"], label=f"{d['label']} (Mean: {np.mean(d['fairness'][d['time']>=2.0]):.3f})",
                 color=d["color"], linestyle=d["style"], linewidth=linewidth)

    ax.axhline(1.0, color="black", linestyle=":", alpha=0.6, label="Ideal Fairness (1.0)")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Jain's Fairness Index")
    ax.set_title("Fig. 4(a) Replica: Jain's Fairness Index vs. Time (Different RTT: 40ms vs 160ms)")
    ax.set_ylim(0.4, 1.05)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    outpath = os.path.join(OUT_DIR, outname)
    plt.savefig(outpath, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {outpath}")

def plot_paper_fig5(data, scenario="different-rtt", outname="fig5_paper_link_utilization.png"):
    """Fig. 5: Bottleneck Link Bandwidth Utilization (%) vs. Time."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for ctrl_id, d in data.items():
        linewidth = 2.2 if "V2" in ctrl_id else 1.5
        mean_util = np.mean(d["utilization"][d["time"] >= 2.0])
        ax.plot(d["time"], d["utilization"], label=f"{d['label']} (Mean: {mean_util:.2f}%)",
                 color=d["color"], linestyle=d["style"], linewidth=linewidth)

    ax.axhline(100.0, color="gray", linestyle=":", label="100% Link Capacity (10 Mbps)")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Bottleneck Link Utilization (%)")
    ax.set_title("Fig. 5 Replica: Bottleneck Bandwidth Utilization vs. Time")
    ax.set_ylim(85, 102)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    outpath = os.path.join(OUT_DIR, outname)
    plt.savefig(outpath, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {outpath}")

def plot_paper_summary_dashboard(data, scenario="different-rtt", outname="paper_summary_dashboard.png"):
    """Three-panel comprehensive IEEE evaluation dashboard: Throughput, Fairness, Link Utilization."""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

    # Panel 1: Throughput (Aggregate and Flow A)
    for ctrl_id, d in data.items():
        lw = 2.0 if "V2" in ctrl_id else 1.4
        ax1.plot(d["time"], d["flowA"], label=f"{d['label']} Flow A",
                 color=d["color"], linestyle=d["style"], linewidth=lw)
    ax1.axhline(5.0, color="gray", linestyle=":", label="Fair Share (5 Mbps)")
    ax1.set_ylabel("Throughput (Mbps)")
    ax1.set_title("Panel A: Flow A (Short RTT 40ms) Throughput vs. Time")
    ax1.grid(True)
    ax1.set_ylim(0, 8)
    ax1.legend(loc="upper right", framealpha=0.9, ncol=2)

    # Panel 2: Fairness Index
    for ctrl_id, d in data.items():
        lw = 2.0 if "V2" in ctrl_id else 1.4
        ax2.plot(d["time"], d["fairness"], label=d["label"],
                 color=d["color"], linestyle=d["style"], linewidth=lw)
    ax2.axhline(1.0, color="gray", linestyle=":")
    ax2.set_ylabel("Jain's Index")
    ax2.set_title("Panel B: Jain's Fairness Index vs. Time")
    ax2.grid(True)
    ax2.set_ylim(0.4, 1.05)
    ax2.legend(loc="lower right", framealpha=0.9, ncol=2)

    # Panel 3: Link Utilization
    for ctrl_id, d in data.items():
        lw = 2.0 if "V2" in ctrl_id else 1.4
        ax3.plot(d["time"], d["utilization"], label=d["label"],
                 color=d["color"], linestyle=d["style"], linewidth=lw)
    ax3.set_xlabel("Time (seconds)")
    ax3.set_ylabel("Utilization (%)")
    ax3.set_title("Panel C: Bottleneck Link Utilization (%) vs. Time")
    ax3.grid(True)
    ax3.set_ylim(85, 102)
    ax3.legend(loc="lower right", framealpha=0.9, ncol=2)

    plt.tight_layout()
    outpath = os.path.join(OUT_DIR, outname)
    plt.savefig(outpath, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {outpath}")

def plot_queue_and_rtt(scenario="different-rtt", outname="paper_queue_and_rtt_comparison.png"):
    """Bottleneck queue occupancy and measured RTT comparison."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    for ctrl_id, ctrl_label, color, style in CONTROLLERS:
        q_path = os.path.join(RESULTS_DIR, ctrl_id, "raw", scenario, "queue_occupancy.csv")
        if os.path.exists(q_path):
            with open(q_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                qt, qp = [], []
                for row in reader:
                    qt.append(float(row["time"]))
                    qp.append(float(row["queue_packets"]))
                lw = 2.0 if "V2" in ctrl_id else 1.4
                ax1.plot(qt, qp, label=ctrl_label, color=color, linestyle=style, linewidth=lw)

        rtt_path = os.path.join(RESULTS_DIR, ctrl_id, "raw", scenario, "rtt.csv")
        if os.path.exists(rtt_path):
            with open(rtt_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                ra_t, ra_v = [], []
                for row in reader:
                    if row.get("flow") == "FlowA":
                        ra_t.append(float(row["time"]))
                        ra_v.append(float(row["rtt_ms"]))
                if ra_t:
                    lw = 2.0 if "V2" in ctrl_id else 1.4
                    ax2.plot(ra_t, ra_v, label=f"{ctrl_label} Flow A", color=color, linestyle=style, linewidth=lw)

    ax1.set_ylabel("Queue Depth (packets)")
    ax1.set_title("Bottleneck Buffer Queue Occupancy vs. Time")
    ax1.axhline(100.0, color="black", linestyle="--", alpha=0.7, label="Max Queue Limit (100p)")
    ax1.set_ylim(0, 105)
    ax1.grid(True)
    ax1.legend(loc="upper right", framealpha=0.9, ncol=2)

    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("RTT (ms)")
    ax2.set_title("Measured Round-Trip Time (Flow A, Min RTT = 40ms)")
    ax2.grid(True)
    ax2.legend(loc="upper right", framealpha=0.9, ncol=2)

    plt.tight_layout()
    outpath = os.path.join(OUT_DIR, outname)
    plt.savefig(outpath, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {outpath}")

def main():
    print("[INFO] Loading different-rtt simulation data...")
    diff_data = load_scenario_throughput("different-rtt")
    if diff_data:
        plot_paper_fig3a(diff_data, "different-rtt", "fig3a_paper_throughput_comparison.png")
        plot_paper_fig4a(diff_data, "different-rtt", "fig4a_paper_fairness_index_comparison.png")
        plot_paper_fig5(diff_data, "different-rtt", "fig5_paper_link_utilization.png")
        plot_paper_summary_dashboard(diff_data, "different-rtt", "paper_summary_dashboard.png")
        plot_queue_and_rtt("different-rtt", "paper_queue_and_rtt_comparison.png")

    print("[INFO] Loading equal-rtt simulation data...")
    eq_data = load_scenario_throughput("equal-rtt")
    if eq_data:
        plot_paper_fig3a(eq_data, "equal-rtt", "fig3a_equal_rtt_throughput_comparison.png")
        plot_paper_fig4a(eq_data, "equal-rtt", "fig4a_equal_rtt_fairness_comparison.png")
        plot_paper_fig5(eq_data, "equal-rtt", "fig5_equal_rtt_link_utilization.png")

    print("[SUCCESS] All publication-quality paper figures created in:", OUT_DIR)

if __name__ == "__main__":
    main()
