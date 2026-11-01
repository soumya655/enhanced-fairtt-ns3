#!/usr/bin/env python3
"""
plot_paper_categories.py
Generates the publication graphs matching the paper's exact identifiers and metrics:
1. Throughput vs Time (Throughput in Mbps vs Time in seconds)
2. Fairness Index vs Time (Jain's Fairness Index vs Time in seconds)
3. Link Utilization vs Time (Bottleneck Link Utilization in % vs Time in seconds)

Organized into the two broad categories:
Category 1: Different RTT (Asymmetric RTT: Flow A 40ms vs Flow B 160ms)
Category 2: Equal RTT (Symmetric RTT: Flow A 40ms vs Flow B 40ms)
(Plus Elephant/Mice workload)

Compares:
- BBR (TcpBbr)
- FaiRTT (TcpBbrFairtt)
- Enhanced FaiRTT (TcpBbrEnhancedFairttV2)
"""

import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Professional publication styling
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9.5,
    "grid.alpha": 0.4,
    "grid.linestyle": "--",
    "figure.titlesize": 14
})

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")

CONTROLLERS = [
    ("TcpBbr", "BBR", "#1f77b4", "-"),
    ("TcpBbrFairtt", "FaiRTT", "#ff7f0e", "--"),
    ("TcpBbrEnhancedFairttV2", "Enhanced FaiRTT", "#d62728", "-")
]

def load_data(ctrl_id, scenario):
    path = os.path.join(RESULTS_DIR, ctrl_id, "raw", scenario, "throughput.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        t, fa, fb, agg, fair = [], [], [], [], []
        for row in reader:
            t.append(float(row["time"]))
            fa.append(float(row["flowA_mbps"]))
            fb.append(float(row["flowB_mbps"]))
            agg.append(float(row["aggregate_mbps"]))
            fair.append(float(row["fairness_index"]))
    return {
        "time": np.array(t),
        "flowA": np.array(fa),
        "flowB": np.array(fb),
        "aggregate": np.array(agg),
        "fairness": np.array(fair),
        "utilization": np.array(agg) / 10.0 * 100.0  # % of 10 Mbps link
    }

def generate_category_plots(scenario, cat_name, out_subdir):
    out_dir = os.path.join(PLOTS_DIR, out_subdir)
    os.makedirs(out_dir, exist_ok=True)

    series = {}
    for ctrl_id, label, color, style in CONTROLLERS:
        data = load_data(ctrl_id, scenario)
        if data:
            series[ctrl_id] = {
                "label": label,
                "color": color,
                "style": style,
                **data
            }

    if not series:
        print(f"[WARN] No data found for {scenario}")
        return

    # -------------------------------------------------------------
    # 1. Throughput vs Time
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.5), sharex=True)

    # Subplot 1: Short-RTT Flow (Flow A)
    for ctrl_id, d in series.items():
        lw = 2.2 if "Enhanced" in d["label"] else 1.7
        ax1.plot(d["time"], d["flowA"], label=f"{d['label']}",
                 color=d["color"], linestyle=d["style"], linewidth=lw)
    ax1.axhline(5.0, color="#555555", linestyle=":", linewidth=1.5, label="Optimal Fair Share (5.0 Mbps)")
    ax1.set_ylabel("Throughput (Mbps)")
    flow_a_desc = "Flow A (Short RTT ~ 40ms)" if "different" in scenario else "Flow A (RTT 40ms)"
    ax1.set_title(f"Throughput vs. Time: {flow_a_desc} — {cat_name}")
    ax1.set_ylim(0, 8.5)
    ax1.grid(True)
    ax1.legend(loc="upper right", framealpha=0.9)

    # Subplot 2: Long-RTT Flow (Flow B)
    for ctrl_id, d in series.items():
        lw = 2.2 if "Enhanced" in d["label"] else 1.7
        ax2.plot(d["time"], d["flowB"], label=f"{d['label']}",
                 color=d["color"], linestyle=d["style"], linewidth=lw)
    ax2.axhline(5.0, color="#555555", linestyle=":", linewidth=1.5, label="Optimal Fair Share (5.0 Mbps)")
    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Throughput (Mbps)")
    flow_b_desc = "Flow B (Long RTT ~ 160ms)" if "different" in scenario else "Flow B (RTT 40ms)"
    ax2.set_title(f"Throughput vs. Time: {flow_b_desc} — {cat_name}")
    ax2.set_ylim(0, 10.5)
    ax2.grid(True)
    ax2.legend(loc="upper right", framealpha=0.9)

    plt.tight_layout()
    tp_path = os.path.join(out_dir, "throughput_vs_time.png")
    plt.savefig(tp_path, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {tp_path}")

    # -------------------------------------------------------------
    # 2. Fairness Index vs Time
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10.5, 5))
    for ctrl_id, d in series.items():
        lw = 2.4 if "Enhanced" in d["label"] else 1.8
        # compute active window mean
        mask = d["time"] >= 2.0
        mean_fair = np.mean(d["fairness"][mask]) if np.any(mask) else np.mean(d["fairness"])
        ax.plot(d["time"], d["fairness"], label=f"{d['label']} (Mean: {mean_fair:.3f})",
                color=d["color"], linestyle=d["style"], linewidth=lw)

    ax.axhline(1.0, color="black", linestyle=":", linewidth=1.5, label="Ideal Fairness (1.00)")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Jain's Fairness Index")
    ax.set_title(f"Fairness Index vs. Time — {cat_name}")
    
    # Adjusted scale for clear readability of pattern
    if "different" in scenario:
        ax.set_ylim(0.55, 1.03)
    else:
        ax.set_ylim(0.98, 1.005)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    fair_path = os.path.join(out_dir, "fairness_index_vs_time.png")
    plt.savefig(fair_path, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {fair_path}")

    # -------------------------------------------------------------
    # 3. Link Utilization vs Time
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10.5, 5))
    for ctrl_id, d in series.items():
        lw = 2.2 if "Enhanced" in d["label"] else 1.7
        mask = d["time"] >= 2.0
        mean_util = np.mean(d["utilization"][mask]) if np.any(mask) else np.mean(d["utilization"])
        ax.plot(d["time"], d["utilization"], label=f"{d['label']} (Mean: {mean_util:.2f}%)",
                color=d["color"], linestyle=d["style"], linewidth=lw)

    ax.axhline(100.0, color="#555555", linestyle=":", linewidth=1.5, label="100% Bottleneck Capacity (10 Mbps)")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Bottleneck Link Utilization (%)")
    ax.set_title(f"Link Utilization vs. Time — {cat_name}")
    ax.set_ylim(88, 102)
    ax.grid(True)
    ax.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    util_path = os.path.join(out_dir, "link_utilization_vs_time.png")
    plt.savefig(util_path, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {util_path}")

def generate_elephant_mice_category():
    """Generates the elephant-mice coexistence scenario comparison."""
    out_dir = os.path.join(PLOTS_DIR, "elephant-mice")
    os.makedirs(out_dir, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.5, 7.5), sharex=True)

    for ctrl_id, label, color, style in CONTROLLERS:
        path = os.path.join(RESULTS_DIR, ctrl_id, "raw", "elephant-mice-different-rtt", "throughput.csv")
        if not os.path.exists(path):
            continue
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            t, agg, fair = [], [], []
            for row in reader:
                t.append(float(row["time"]))
                agg.append(float(row["aggregate_mbps"]))
                fair.append(float(row["fairness_index"]))
        lw = 2.2 if "Enhanced" in label else 1.7
        ax1.plot(t, agg, label=label, color=color, linestyle=style, linewidth=lw)
        ax2.plot(t, fair, label=label, color=color, linestyle=style, linewidth=lw)

    ax1.axhline(10.0, color="gray", linestyle=":", label="Bottleneck Capacity (10 Mbps)")
    ax1.set_ylabel("Aggregate Throughput (Mbps)")
    ax1.set_title("Throughput vs. Time: Elephant & Mice Flows (Different RTT)")
    ax1.set_ylim(8.0, 10.5)
    ax1.grid(True)
    ax1.legend(loc="lower right", framealpha=0.9)

    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Jain's Fairness Index")
    ax2.set_title("Fairness Index vs. Time: Elephant & Mice Flows (Different RTT)")
    ax2.set_ylim(0.4, 1.02)
    ax2.grid(True)
    ax2.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    em_path = os.path.join(out_dir, "elephant_mice_comparison_vs_time.png")
    plt.savefig(em_path, dpi=300)
    plt.close(fig)
    print(f"[PLOT] Generated: {em_path}")

def main():
    print("Generating Category 1: Different RTT (Asymmetric Delay)...")
    generate_category_plots("different-rtt", "Different RTT (40ms vs. 160ms)", "different-rtt")

    print("Generating Category 2: Equal RTT (Symmetric Delay)...")
    generate_category_plots("equal-rtt", "Equal RTT (40ms vs. 40ms)", "equal-rtt")

    print("Generating Elephant/Mice Category...")
    generate_elephant_mice_category()

    print("\n[SUCCESS] Clean paper-style plots created in results/plots/")

if __name__ == "__main__":
    main()
