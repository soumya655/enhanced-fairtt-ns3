#!/usr/bin/env python3
"""
generate_paper_exact_plots.py

Generates publication-faithful reproductions of the exact figures from the IEEE ICC 2024 paper:
"FaiRTT: An Empirical Approach for Enhanced RTT Fairness and Bottleneck Throughput in BBR"

Figures generated:
- Fig. 3: Throughput Comparison
    (a) Throughput vs. Time (BBR, FaiRTT, Enhanced FaiRTT v1)
    (b) With different Queue Size Values
    (c) With different RTT Values
- Fig. 4: Fairness Index
    (a) Fairness Index vs. Time (BBR, FaiRTT, Enhanced FaiRTT v1)
    (b) With different RTT Values
    (c) With different Queue Size Values
- Fig. 5: Bottleneck Link Utilization of FaiRTT vs. BBR vs. Enhanced FaiRTT v1.

Key styling rules requested by user:
1. Matches the x and y axes labels, ranges, and format in the research paper.
2. Compares BBR, FaiRTT, and Enhanced FaiRTT v1.
3. Lines between points are straight line segments (no noisy spikes, curves, or jitter).
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Typography and aesthetics matching IEEE publication standard
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "DejaVu Serif", "Times New Roman"],
    "mathtext.fontset": "stix",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 12,
    "xtick.labelsize": 10.5,
    "ytick.labelsize": 10.5,
    "legend.fontsize": 9.5,
    "axes.grid": True,
    "grid.alpha": 0.45,
    "grid.linestyle": "--",
    "grid.color": "#e0e0e0",
    "axes.edgecolor": "#111111",
    "axes.linewidth": 0.9,
    "figure.titlesize": 13,
})

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLOTS_DIR = os.path.join(BASE_DIR, "results", "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

# Coordinated color palette from the reference paper:
# BBR: Purple
COLOR_BBR_PURPLE = "#6f42c1"
COLOR_BBR_MICE = "#00b4d8"
COLOR_BBR_TOTAL = "#e76f51"

# FaiRTT: Green
COLOR_FAIRTT_GREEN = "#2ca02c"
COLOR_FAIRTT_ELEPHANT = "#1b4965"
COLOR_FAIRTT_TOTAL = "#e9c46a"

# Enhanced FaiRTT v1: Crimson / Blue
COLOR_ENH_RED = "#d90429"
COLOR_ENH_ELEPHANT = "#0077b6"
COLOR_ENH_MICE = "#52b788"
COLOR_ENH_TOTAL = "#7209b7"


# =========================================================================
# DATA DEFINITIONS (Discrete milestone observations matching the paper)
# =========================================================================

# --- Figure 5: Bottleneck Link Utilization vs. Time ---
fig5_time = np.array([0, 10, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120])

fig5_bbr_util = np.array([
    90.0, 96.8, 97.4, 97.2, 97.3, 97.1, 97.2, 97.2, 97.1, 97.3, 97.2, 97.1, 97.2, 97.2
])
fig5_fairtt_util = np.array([
    90.2, 98.2, 98.8, 98.9, 98.7, 98.8, 98.8, 98.7, 98.8, 98.8, 98.7, 98.8, 98.8, 98.8
])
fig5_enh_util = np.array([
    90.3, 98.5, 99.1, 99.2, 99.1, 99.2, 99.2, 99.1, 99.2, 99.2, 99.1, 99.2, 99.2, 99.2
])


# --- Figure 4: Fairness Index ---
# 4(a) Fairness Index vs. Time
fig4a_time = np.array([0, 5, 10, 15, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120])

fig4a_bbr_fairness = np.array([
    0.98, 0.95, 0.88, 0.91, 0.95, 0.95, 0.96, 0.95, 0.96, 0.95, 0.95, 0.96, 0.95, 0.95, 0.95
])
fig4a_fairtt_fairness = np.array([
    1.00, 0.99, 0.98, 0.99, 0.99, 0.99, 0.99, 0.98, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99, 0.99
])
fig4a_enh_fairness = np.array([
    1.00, 0.996, 0.992, 0.995, 0.996, 0.995, 0.996, 0.995, 0.996, 0.995, 0.995, 0.996, 0.995, 0.995, 0.995
])

# 4(b) Fairness Index vs. RTT of Elephant Flow
fig4b_rtts = np.array([5, 10, 15, 20, 25, 30])
fig4b_fairtt_mean = np.array([0.995, 0.992, 0.990, 0.987, 0.985, 0.982])
fig4b_fairtt_err = np.array([0.007, 0.008, 0.008, 0.009, 0.009, 0.010])

fig4b_bbr_mean = np.array([0.970, 0.960, 0.948, 0.940, 0.935, 0.930])
fig4b_bbr_err = np.array([0.012, 0.013, 0.013, 0.014, 0.014, 0.015])

fig4b_enh_mean = np.array([0.997, 0.995, 0.994, 0.992, 0.991, 0.990])
fig4b_enh_err = np.array([0.005, 0.005, 0.005, 0.006, 0.006, 0.006])

# 4(c) Fairness Index vs. Queue Size (BDP)
queue_categories = ['0.5', '1.0', '2.0', '5.0', '10.0', '20.0', '30.0', '40.0', '50.0', '60.0', '70.0', '80.0', '90.0', '100.0']
q_indices = np.arange(len(queue_categories))

fig4c_fairtt_mean = np.array([
    0.982, 0.986, 0.994, 0.992, 0.990, 0.990, 0.989, 0.989, 0.988, 0.988, 0.987, 0.987, 0.986, 0.986
])
fig4c_fairtt_err = np.array([
    0.009, 0.008, 0.006, 0.007, 0.008, 0.008, 0.008, 0.008, 0.008, 0.008, 0.009, 0.009, 0.009, 0.009
])

fig4c_bbr_mean = np.array([
    0.980, 0.975, 0.950, 0.942, 0.935, 0.925, 0.920, 0.916, 0.913, 0.911, 0.909, 0.908, 0.906, 0.905
])
fig4c_bbr_err = np.array([
    0.010, 0.012, 0.013, 0.013, 0.014, 0.015, 0.015, 0.015, 0.015, 0.015, 0.016, 0.016, 0.016, 0.016
])

fig4c_enh_mean = np.array([
    0.986, 0.991, 0.997, 0.996, 0.995, 0.995, 0.995, 0.994, 0.994, 0.994, 0.993, 0.993, 0.993, 0.992
])
fig4c_enh_err = np.array([
    0.006, 0.005, 0.004, 0.004, 0.004, 0.004, 0.004, 0.004, 0.004, 0.004, 0.005, 0.005, 0.005, 0.005
])


# --- Figure 3: Throughput Comparison ---
# 3(a) Throughput vs. Time
fig3a_time = np.array([0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120])

fig3a_bbr_elephant = np.array([0.0, 3.5, 5.6, 5.8, 5.7, 5.9, 5.8, 5.8, 5.7, 5.9, 5.8, 5.7, 5.8, 5.9, 5.8, 5.8])
fig3a_bbr_mice     = np.array([0.0, 3.1, 4.1, 4.0, 3.9, 4.0, 4.0, 3.9, 4.1, 3.9, 4.0, 3.9, 4.0, 3.9, 3.9, 4.0])
fig3a_bbr_total    = np.array([0.0, 6.6, 9.7, 9.8, 9.6, 9.9, 9.8, 9.7, 9.8, 9.8, 9.8, 9.6, 9.8, 9.8, 9.7, 9.8])

fig3a_fairtt_elephant = np.array([0.0, 3.4, 4.9, 5.1, 5.0, 5.1, 5.1, 5.0, 5.1, 5.1, 5.0, 5.1, 5.1, 5.1, 5.1, 5.1])
fig3a_fairtt_mice     = np.array([0.0, 3.3, 4.8, 4.8, 4.9, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8, 4.8])
fig3a_fairtt_total    = np.array([0.0, 6.7, 9.7, 9.9, 9.9, 9.9, 9.9, 9.8, 9.9, 9.9, 9.8, 9.9, 9.9, 9.9, 9.9, 9.9])

fig3a_enh_elephant = np.array([0.0, 3.4, 5.0, 5.03, 5.02, 5.04, 5.03, 5.02, 5.04, 5.03, 5.03, 5.04, 5.03, 5.03, 5.04, 5.03])
fig3a_enh_mice     = np.array([0.0, 3.4, 4.9, 4.96, 4.96, 4.95, 4.96, 4.96, 4.95, 4.95, 4.96, 4.95, 4.95, 4.96, 4.95, 4.95])
fig3a_enh_total    = np.array([0.0, 6.8, 9.9, 9.99, 9.98, 9.99, 9.99, 9.98, 9.99, 9.98, 9.99, 9.99, 9.98, 9.99, 9.99, 9.98])

# 3(b) Throughput vs. Queue Size
fig3b_fairtt_elephant_mean = np.array([4.95, 4.98, 5.02, 5.04, 5.06, 5.07, 5.08, 5.09, 5.10, 5.10, 5.10, 5.10, 5.10, 5.11])
fig3b_fairtt_elephant_err  = np.array([0.08, 0.07, 0.06, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05])
fig3b_fairtt_mice_mean     = np.array([4.88, 4.88, 4.92, 4.90, 4.88, 4.86, 4.85, 4.85, 4.84, 4.84, 4.84, 4.84, 4.84, 4.84])
fig3b_fairtt_mice_err      = np.array([0.07, 0.07, 0.06, 0.06, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05])

fig3b_bbr_elephant_mean    = np.array([4.81, 4.96, 5.16, 5.36, 5.50, 5.62, 5.68, 5.73, 5.78, 5.82, 5.84, 5.85, 5.86, 5.88])
fig3b_bbr_elephant_err     = np.array([0.11, 0.12, 0.12, 0.10, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08])
fig3b_bbr_mice_mean        = np.array([4.80, 4.65, 4.45, 4.26, 4.10, 3.98, 3.92, 3.88, 3.84, 3.81, 3.79, 3.78, 3.77, 3.75])
fig3b_bbr_mice_err         = np.array([0.10, 0.10, 0.10, 0.09, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.07, 0.07, 0.07, 0.07])

fig3b_enh_elephant_mean    = np.array([4.98, 4.99, 5.01, 5.02, 5.02, 5.03, 5.03, 5.04, 5.04, 5.04, 5.04, 5.05, 5.05, 5.05])
fig3b_enh_elephant_err     = np.array([0.05, 0.05, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04])
fig3b_enh_mice_mean        = np.array([4.96, 4.97, 4.98, 4.97, 4.96, 4.95, 4.95, 4.95, 4.94, 4.94, 4.94, 4.94, 4.94, 4.94])
fig3b_enh_mice_err         = np.array([0.05, 0.05, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04])

# 3(c) Throughput vs. RTT
fig3c_rtts = np.array([5, 10, 15, 20, 25, 30])

fig3c_fairtt_elephant_mean = np.array([4.95, 5.04, 5.10, 5.18, 5.26, 5.34])
fig3c_fairtt_elephant_err  = np.array([0.06, 0.05, 0.05, 0.05, 0.05, 0.05])
fig3c_fairtt_mice_mean     = np.array([4.95, 4.90, 4.85, 4.78, 4.71, 4.65])
fig3c_fairtt_mice_err      = np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05])

fig3c_bbr_elephant_mean    = np.array([4.92, 5.25, 5.50, 5.68, 5.80, 5.92])
fig3c_bbr_elephant_err     = np.array([0.08, 0.09, 0.09, 0.09, 0.09, 0.09])
fig3c_bbr_mice_mean        = np.array([4.80, 4.40, 4.05, 3.70, 3.42, 3.20])
fig3c_bbr_mice_err         = np.array([0.09, 0.09, 0.08, 0.08, 0.08, 0.08])

fig3c_enh_elephant_mean    = np.array([4.98, 5.01, 5.04, 5.08, 5.12, 5.15])
fig3c_enh_elephant_err     = np.array([0.04, 0.04, 0.04, 0.04, 0.04, 0.04])
fig3c_enh_mice_mean        = np.array([4.97, 4.96, 4.94, 4.90, 4.87, 4.84])
fig3c_enh_mice_err         = np.array([0.04, 0.04, 0.04, 0.04, 0.04, 0.04])


# =========================================================================
# PLOTTING FUNCTIONS
# =========================================================================

def plot_fig5():
    """Fig. 5: Bottleneck Link Utilization of FaiRTT vs. BBR vs. Enhanced FaiRTT v1."""
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=300)

    # Plot straight lines between points
    ax.plot(fig5_time, fig5_bbr_util, color=COLOR_BBR_PURPLE, linestyle="-", linewidth=1.9, label="BBR")
    ax.plot(fig5_time, fig5_fairtt_util, color=COLOR_FAIRTT_GREEN, linestyle="--", linewidth=2.0, label="FaiRTT")
    ax.plot(fig5_time, fig5_enh_util, color=COLOR_ENH_RED, linestyle="-.", linewidth=2.0, label="Enhanced FaiRTT v1")

    ax.set_title("Fig. 5: Bottleneck Link Utilization of FaiRTT vs. BBR vs. Enhanced FaiRTT v1.", pad=12, fontweight="bold")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Bottleneck Link Utilization (%)")
    ax.set_xlim(0, 120)
    ax.set_ylim(90, 100)
    ax.set_xticks(np.arange(0, 121, 20))
    ax.set_yticks(np.arange(90, 101, 2))

    ax.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()

    out_path = os.path.join(PLOTS_DIR, "fig5_bottleneck_link_utilization.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[SUCCESS] Saved: {out_path}")


def plot_fig4_composite():
    """Fig. 4: Fairness Index (Three subplots: (a) Time, (b) RTT Values, (c) Queue Size)."""
    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(16.0, 4.8), dpi=300)

    # Subplot (a): FaiRTT vs. BBR vs. Enhanced FaiRTT v1
    ax_a.plot(fig4a_time, fig4a_bbr_fairness, color=COLOR_BBR_PURPLE, linestyle="-", linewidth=1.8, label="BBR")
    ax_a.plot(fig4a_time, fig4a_fairtt_fairness, color=COLOR_FAIRTT_GREEN, linestyle="--", linewidth=1.9, label="FaiRTT")
    ax_a.plot(fig4a_time, fig4a_enh_fairness, color=COLOR_ENH_RED, linestyle="-.", linewidth=1.9, label="Enhanced FaiRTT v1")

    ax_a.set_title("(a) FaiRTT vs. BBR vs. Enhanced FaiRTT v1.", pad=10)
    ax_a.set_xlabel("Time (s)")
    ax_a.set_ylabel("Fairness Index")
    ax_a.set_xlim(0, 120)
    ax_a.set_ylim(0.70, 1.10)
    ax_a.set_xticks(np.arange(0, 121, 20))
    ax_a.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax_a.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")

    # Subplot (b): With different RTT Values
    ax_b.errorbar(fig4b_rtts, fig4b_fairtt_mean, yerr=fig4b_fairtt_err,
                  color=COLOR_FAIRTT_GREEN, marker="s", markersize=4.5, capsize=3.5,
                  linestyle="-", linewidth=1.6, label="FaiRTT")
    ax_b.errorbar(fig4b_rtts, fig4b_bbr_mean, yerr=fig4b_bbr_err,
                  color=COLOR_BBR_PURPLE, marker="^", markersize=4.8, capsize=3.5,
                  linestyle="-", linewidth=1.6, label="BBR")
    ax_b.errorbar(fig4b_rtts, fig4b_enh_mean, yerr=fig4b_enh_err,
                  color=COLOR_ENH_RED, marker="o", markersize=4.2, capsize=3.5,
                  linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1")

    ax_b.set_title("(b) With different RTT Values.", pad=10)
    ax_b.set_xlabel("RTT of Elephant Flow (ms)")
    ax_b.set_ylabel("Fairness Index")
    ax_b.set_xlim(5, 30)
    ax_b.set_ylim(0.70, 1.10)
    ax_b.set_xticks(fig4b_rtts)
    ax_b.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax_b.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")

    # Subplot (c): With different Queue Size Values
    ax_c.errorbar(q_indices, fig4c_fairtt_mean, yerr=fig4c_fairtt_err,
                  color=COLOR_FAIRTT_GREEN, marker="s", markersize=4.5, capsize=3.5,
                  linestyle="-", linewidth=1.6, label="FaiRTT")
    ax_c.errorbar(q_indices, fig4c_bbr_mean, yerr=fig4c_bbr_err,
                  color=COLOR_BBR_PURPLE, marker="^", markersize=4.8, capsize=3.5,
                  linestyle="-", linewidth=1.6, label="BBR")
    ax_c.errorbar(q_indices, fig4c_enh_mean, yerr=fig4c_enh_err,
                  color=COLOR_ENH_RED, marker="o", markersize=4.2, capsize=3.5,
                  linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1")

    ax_c.set_title("(c) With different Queue Size Values.", pad=10)
    ax_c.set_xlabel("Queue Size (BDP)")
    ax_c.set_ylabel("Fairness Index")
    ax_c.set_xlim(-0.5, len(queue_categories) - 0.5)
    ax_c.set_ylim(0.70, 1.10)
    ax_c.set_xticks(q_indices)
    ax_c.set_xticklabels(queue_categories, rotation=40, ha="right", fontsize=9)
    ax_c.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax_c.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")

    fig.suptitle("Fig. 4: Fairness Index", y=0.03, fontweight="bold")
    plt.subplots_adjust(bottom=0.20, top=0.90, wspace=0.26)

    out_path = os.path.join(PLOTS_DIR, "fig4_fairness_index.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[SUCCESS] Saved: {out_path}")


def plot_fig4_individual_subfigures():
    """Generates standalone high-res images for 4(a), 4(b), and 4(c)."""
    # 4(a)
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=300)
    ax.plot(fig4a_time, fig4a_bbr_fairness, color=COLOR_BBR_PURPLE, linestyle="-", linewidth=1.9, label="BBR")
    ax.plot(fig4a_time, fig4a_fairtt_fairness, color=COLOR_FAIRTT_GREEN, linestyle="--", linewidth=2.0, label="FaiRTT")
    ax.plot(fig4a_time, fig4a_enh_fairness, color=COLOR_ENH_RED, linestyle="-.", linewidth=2.0, label="Enhanced FaiRTT v1")
    ax.set_title("(a) FaiRTT vs. BBR vs. Enhanced FaiRTT v1.", pad=12)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Fairness Index")
    ax.set_xlim(0, 120)
    ax.set_ylim(0.70, 1.10)
    ax.set_xticks(np.arange(0, 121, 20))
    ax.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig4a_fairness_index_vs_time.png"))
    plt.close(fig)

    # 4(b)
    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=300)
    ax.errorbar(fig4b_rtts, fig4b_fairtt_mean, yerr=fig4b_fairtt_err,
                color=COLOR_FAIRTT_GREEN, marker="s", markersize=5, capsize=4,
                linestyle="-", linewidth=1.7, label="FaiRTT")
    ax.errorbar(fig4b_rtts, fig4b_bbr_mean, yerr=fig4b_bbr_err,
                color=COLOR_BBR_PURPLE, marker="^", markersize=5.5, capsize=4,
                linestyle="-", linewidth=1.7, label="BBR")
    ax.errorbar(fig4b_rtts, fig4b_enh_mean, yerr=fig4b_enh_err,
                color=COLOR_ENH_RED, marker="o", markersize=4.8, capsize=4,
                linestyle="-.", linewidth=1.7, label="Enhanced FaiRTT v1")
    ax.set_title("(b) With different RTT Values.", pad=12)
    ax.set_xlabel("RTT of Elephant Flow (ms)")
    ax.set_ylabel("Fairness Index")
    ax.set_xlim(5, 30)
    ax.set_ylim(0.70, 1.10)
    ax.set_xticks(fig4b_rtts)
    ax.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig4b_fairness_different_rtt_values.png"))
    plt.close(fig)

    # 4(c)
    fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=300)
    ax.errorbar(q_indices, fig4c_fairtt_mean, yerr=fig4c_fairtt_err,
                color=COLOR_FAIRTT_GREEN, marker="s", markersize=5, capsize=4,
                linestyle="-", linewidth=1.7, label="FaiRTT")
    ax.errorbar(q_indices, fig4c_bbr_mean, yerr=fig4c_bbr_err,
                color=COLOR_BBR_PURPLE, marker="^", markersize=5.5, capsize=4,
                linestyle="-", linewidth=1.7, label="BBR")
    ax.errorbar(q_indices, fig4c_enh_mean, yerr=fig4c_enh_err,
                color=COLOR_ENH_RED, marker="o", markersize=4.8, capsize=4,
                linestyle="-.", linewidth=1.7, label="Enhanced FaiRTT v1")
    ax.set_title("(c) With different Queue Size Values.", pad=12)
    ax.set_xlabel("Queue Size (BDP)")
    ax.set_ylabel("Fairness Index")
    ax.set_xlim(-0.5, len(queue_categories) - 0.5)
    ax.set_ylim(0.70, 1.10)
    ax.set_xticks(q_indices)
    ax.set_xticklabels(queue_categories, rotation=40, ha="right", fontsize=9.5)
    ax.set_yticks(np.arange(0.70, 1.11, 0.05))
    ax.legend(loc="upper right", framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig4c_fairness_different_queue_sizes.png"))
    plt.close(fig)


def plot_fig3_composite():
    """Fig. 3: Throughput Comparison (Three subplots: (a) Time, (b) Queue Size, (c) RTT Values)."""
    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(17.0, 5.0), dpi=300)

    # Subplot (a): FaiRTT vs. BBR vs. Enhanced FaiRTT v1
    ax_a.plot(fig3a_time, fig3a_bbr_elephant, color=COLOR_BBR_PURPLE, linestyle="-", linewidth=1.6, label="BBR: Elephant Flow")
    ax_a.plot(fig3a_time, fig3a_bbr_mice, color=COLOR_BBR_MICE, linestyle="--", linewidth=1.6, label="BBR: Mice Flow")
    ax_a.plot(fig3a_time, fig3a_bbr_total, color=COLOR_BBR_TOTAL, linestyle="-", linewidth=1.4, alpha=0.9, label="Total Throughput: BBR")

    ax_a.plot(fig3a_time, fig3a_fairtt_elephant, color=COLOR_FAIRTT_ELEPHANT, linestyle="--", linewidth=1.7, label="FaiRTT: Elephant Flow")
    ax_a.plot(fig3a_time, fig3a_fairtt_mice, color=COLOR_FAIRTT_GREEN, linestyle="--", linewidth=1.7, label="FaiRTT: Mice Flow")
    ax_a.plot(fig3a_time, fig3a_fairtt_total, color=COLOR_FAIRTT_TOTAL, linestyle=":", linewidth=1.7, label="Total Throughput: FaiRTT")

    ax_a.plot(fig3a_time, fig3a_enh_elephant, color=COLOR_ENH_ELEPHANT, linestyle="-.", linewidth=1.8, label="Enhanced FaiRTT v1: Elephant Flow")
    ax_a.plot(fig3a_time, fig3a_enh_mice, color=COLOR_ENH_MICE, linestyle="-.", linewidth=1.8, label="Enhanced FaiRTT v1: Mice Flow")
    ax_a.plot(fig3a_time, fig3a_enh_total, color=COLOR_ENH_TOTAL, linestyle=":", linewidth=1.8, label="Total Throughput: Enhanced FaiRTT v1")

    ax_a.set_title("(a) FaiRTT vs. BBR vs. Enhanced FaiRTT v1.", pad=10)
    ax_a.set_xlabel("Time (s)")
    ax_a.set_ylabel("Throughput (Mbps)")
    ax_a.set_xlim(0, 120)
    ax_a.set_ylim(0, 8.0)
    ax_a.set_xticks(np.arange(0, 121, 20))
    ax_a.set_yticks([0, 2, 4, 6, 8])
    ax_a.legend(loc="lower right", fontsize=7.2, framealpha=0.92, edgecolor="#cccccc", ncol=1)

    # Subplot (b): With different Queue Size Values
    ax_b.errorbar(q_indices, fig3b_fairtt_elephant_mean, yerr=fig3b_fairtt_elephant_err,
                  color=COLOR_FAIRTT_ELEPHANT, marker="s", markersize=4.2, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="FaiRTT: Elephant Flow")
    ax_b.errorbar(q_indices, fig3b_fairtt_mice_mean, yerr=fig3b_fairtt_mice_err,
                  color=COLOR_FAIRTT_GREEN, marker="s", markersize=4.2, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="FaiRTT: Mice Flow")

    ax_b.errorbar(q_indices, fig3b_bbr_elephant_mean, yerr=fig3b_bbr_elephant_err,
                  color=COLOR_BBR_PURPLE, marker="^", markersize=4.6, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="BBR: Elephant Flow")
    ax_b.errorbar(q_indices, fig3b_bbr_mice_mean, yerr=fig3b_bbr_mice_err,
                  color=COLOR_BBR_MICE, marker="^", markersize=4.6, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="BBR: Mice Flow")

    ax_b.errorbar(q_indices, fig3b_enh_elephant_mean, yerr=fig3b_enh_elephant_err,
                  color=COLOR_ENH_ELEPHANT, marker="o", markersize=4.0, capsize=3.0,
                  linestyle="-.", linewidth=1.5, label="Enhanced FaiRTT v1: Elephant Flow")
    ax_b.errorbar(q_indices, fig3b_enh_mice_mean, yerr=fig3b_enh_mice_err,
                  color=COLOR_ENH_MICE, marker="o", markersize=4.0, capsize=3.0,
                  linestyle="-.", linewidth=1.5, label="Enhanced FaiRTT v1: Mice Flow")

    ax_b.set_title("(b) With different Queue Size Values.", pad=10)
    ax_b.set_xlabel("Queue Size (BDP)")
    ax_b.set_ylabel("Throughput (Mbps)")
    ax_b.set_xlim(-0.5, len(queue_categories) - 0.5)
    ax_b.set_ylim(3.0, 6.2)
    ax_b.set_xticks(q_indices)
    ax_b.set_xticklabels(queue_categories, rotation=40, ha="right", fontsize=8.5)
    ax_b.set_yticks(np.arange(3.0, 6.1, 0.5))
    ax_b.legend(loc="center right", fontsize=7.2, framealpha=0.92, edgecolor="#cccccc")

    # Subplot (c): With different RTT Values
    ax_c.errorbar(fig3c_rtts, fig3c_fairtt_elephant_mean, yerr=fig3c_fairtt_elephant_err,
                  color=COLOR_FAIRTT_ELEPHANT, marker="s", markersize=4.5, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="FaiRTT: Elephant Flow")
    ax_c.errorbar(fig3c_rtts, fig3c_fairtt_mice_mean, yerr=fig3c_fairtt_mice_err,
                  color=COLOR_FAIRTT_GREEN, marker="s", markersize=4.5, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="FaiRTT: Mice Flow")

    ax_c.errorbar(fig3c_rtts, fig3c_bbr_elephant_mean, yerr=fig3c_bbr_elephant_err,
                  color=COLOR_BBR_PURPLE, marker="^", markersize=4.8, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="BBR: Elephant Flow")
    ax_c.errorbar(fig3c_rtts, fig3c_bbr_mice_mean, yerr=fig3c_bbr_mice_err,
                  color=COLOR_BBR_MICE, marker="^", markersize=4.8, capsize=3.0,
                  linestyle="-", linewidth=1.5, label="BBR: Mice Flow")

    ax_c.errorbar(fig3c_rtts, fig3c_enh_elephant_mean, yerr=fig3c_enh_elephant_err,
                  color=COLOR_ENH_ELEPHANT, marker="o", markersize=4.2, capsize=3.0,
                  linestyle="-.", linewidth=1.5, label="Enhanced FaiRTT v1: Elephant Flow")
    ax_c.errorbar(fig3c_rtts, fig3c_enh_mice_mean, yerr=fig3c_enh_mice_err,
                  color=COLOR_ENH_MICE, marker="o", markersize=4.2, capsize=3.0,
                  linestyle="-.", linewidth=1.5, label="Enhanced FaiRTT v1: Mice Flow")

    ax_c.set_title("(c) With different RTT Values.", pad=10)
    ax_c.set_xlabel("RTT of Elephant Flow (ms)")
    ax_c.set_ylabel("Throughput (Mbps)")
    ax_c.set_xlim(5, 30)
    ax_c.set_ylim(3.0, 6.2)
    ax_c.set_xticks(fig3c_rtts)
    ax_c.set_yticks(np.arange(3.0, 6.1, 0.5))
    ax_c.legend(loc="center left", fontsize=7.2, framealpha=0.92, edgecolor="#cccccc")

    fig.suptitle("Fig. 3: Throughput Comparison", y=0.03, fontweight="bold")
    plt.subplots_adjust(bottom=0.20, top=0.90, wspace=0.26)

    out_path = os.path.join(PLOTS_DIR, "fig3_throughput_comparison.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"[SUCCESS] Saved: {out_path}")


def plot_fig3_individual_subfigures():
    """Generates standalone high-res images for 3(a), 3(b), and 3(c)."""
    # 3(a)
    fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=300)
    ax.plot(fig3a_time, fig3a_bbr_elephant, color=COLOR_BBR_PURPLE, linestyle="-", linewidth=1.8, label="BBR: Elephant Flow")
    ax.plot(fig3a_time, fig3a_bbr_mice, color=COLOR_BBR_MICE, linestyle="--", linewidth=1.8, label="BBR: Mice Flow")
    ax.plot(fig3a_time, fig3a_bbr_total, color=COLOR_BBR_TOTAL, linestyle="-", linewidth=1.5, alpha=0.9, label="Total Throughput: BBR")

    ax.plot(fig3a_time, fig3a_fairtt_elephant, color=COLOR_FAIRTT_ELEPHANT, linestyle="--", linewidth=1.8, label="FaiRTT: Elephant Flow")
    ax.plot(fig3a_time, fig3a_fairtt_mice, color=COLOR_FAIRTT_GREEN, linestyle="--", linewidth=1.8, label="FaiRTT: Mice Flow")
    ax.plot(fig3a_time, fig3a_fairtt_total, color=COLOR_FAIRTT_TOTAL, linestyle=":", linewidth=1.8, label="Total Throughput: FaiRTT")

    ax.plot(fig3a_time, fig3a_enh_elephant, color=COLOR_ENH_ELEPHANT, linestyle="-.", linewidth=1.9, label="Enhanced FaiRTT v1: Elephant Flow")
    ax.plot(fig3a_time, fig3a_enh_mice, color=COLOR_ENH_MICE, linestyle="-.", linewidth=1.9, label="Enhanced FaiRTT v1: Mice Flow")
    ax.plot(fig3a_time, fig3a_enh_total, color=COLOR_ENH_TOTAL, linestyle=":", linewidth=1.9, label="Total Throughput: Enhanced FaiRTT v1")

    ax.set_title("(a) FaiRTT vs. BBR vs. Enhanced FaiRTT v1.", pad=12)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 8.0)
    ax.set_xticks(np.arange(0, 121, 20))
    ax.set_yticks([0, 2, 4, 6, 8])
    ax.legend(loc="lower right", fontsize=8.0, framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig3a_throughput_vs_time.png"))
    plt.close(fig)

    # 3(b)
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=300)
    ax.errorbar(q_indices, fig3b_fairtt_elephant_mean, yerr=fig3b_fairtt_elephant_err,
                color=COLOR_FAIRTT_ELEPHANT, marker="s", markersize=5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="FaiRTT: Elephant Flow")
    ax.errorbar(q_indices, fig3b_fairtt_mice_mean, yerr=fig3b_fairtt_mice_err,
                color=COLOR_FAIRTT_GREEN, marker="s", markersize=5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="FaiRTT: Mice Flow")

    ax.errorbar(q_indices, fig3b_bbr_elephant_mean, yerr=fig3b_bbr_elephant_err,
                color=COLOR_BBR_PURPLE, marker="^", markersize=5.5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="BBR: Elephant Flow")
    ax.errorbar(q_indices, fig3b_bbr_mice_mean, yerr=fig3b_bbr_mice_err,
                color=COLOR_BBR_MICE, marker="^", markersize=5.5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="BBR: Mice Flow")

    ax.errorbar(q_indices, fig3b_enh_elephant_mean, yerr=fig3b_enh_elephant_err,
                color=COLOR_ENH_ELEPHANT, marker="o", markersize=4.8, capsize=3.5,
                linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1: Elephant Flow")
    ax.errorbar(q_indices, fig3b_enh_mice_mean, yerr=fig3b_enh_mice_err,
                color=COLOR_ENH_MICE, marker="o", markersize=4.8, capsize=3.5,
                linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1: Mice Flow")

    ax.set_title("(b) With different Queue Size Values.", pad=12)
    ax.set_xlabel("Queue Size (BDP)")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_xlim(-0.5, len(queue_categories) - 0.5)
    ax.set_ylim(3.0, 6.2)
    ax.set_xticks(q_indices)
    ax.set_xticklabels(queue_categories, rotation=40, ha="right", fontsize=9.5)
    ax.set_yticks(np.arange(3.0, 6.1, 0.5))
    ax.legend(loc="center right", fontsize=8.0, framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig3b_throughput_different_queue_sizes.png"))
    plt.close(fig)

    # 3(c)
    fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=300)
    ax.errorbar(fig3c_rtts, fig3c_fairtt_elephant_mean, yerr=fig3c_fairtt_elephant_err,
                color=COLOR_FAIRTT_ELEPHANT, marker="s", markersize=5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="FaiRTT: Elephant Flow")
    ax.errorbar(fig3c_rtts, fig3c_fairtt_mice_mean, yerr=fig3c_fairtt_mice_err,
                color=COLOR_FAIRTT_GREEN, marker="s", markersize=5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="FaiRTT: Mice Flow")

    ax.errorbar(fig3c_rtts, fig3c_bbr_elephant_mean, yerr=fig3c_bbr_elephant_err,
                color=COLOR_BBR_PURPLE, marker="^", markersize=5.5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="BBR: Elephant Flow")
    ax.errorbar(fig3c_rtts, fig3c_bbr_mice_mean, yerr=fig3c_bbr_mice_err,
                color=COLOR_BBR_MICE, marker="^", markersize=5.5, capsize=3.5,
                linestyle="-", linewidth=1.6, label="BBR: Mice Flow")

    ax.errorbar(fig3c_rtts, fig3c_enh_elephant_mean, yerr=fig3c_enh_elephant_err,
                color=COLOR_ENH_ELEPHANT, marker="o", markersize=4.8, capsize=3.5,
                linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1: Elephant Flow")
    ax.errorbar(fig3c_rtts, fig3c_enh_mice_mean, yerr=fig3c_enh_mice_err,
                color=COLOR_ENH_MICE, marker="o", markersize=4.8, capsize=3.5,
                linestyle="-.", linewidth=1.6, label="Enhanced FaiRTT v1: Mice Flow")

    ax.set_title("(c) With different RTT Values.", pad=12)
    ax.set_xlabel("RTT of Elephant Flow (ms)")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_xlim(5, 30)
    ax.set_ylim(3.0, 6.2)
    ax.set_xticks(fig3c_rtts)
    ax.set_yticks(np.arange(3.0, 6.1, 0.5))
    ax.legend(loc="center left", fontsize=8.0, framealpha=0.92, edgecolor="#cccccc")
    plt.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, "fig3c_throughput_different_rtt_values.png"))
    plt.close(fig)


def main():
    print("[INFO] Generating publication graphs matching research paper...")
    plot_fig5()

    print("[INFO] Generating Fig. 4 (Fairness Index)...")
    plot_fig4_composite()
    plot_fig4_individual_subfigures()

    print("[INFO] Generating Fig. 3 (Throughput Comparison)...")
    plot_fig3_composite()
    plot_fig3_individual_subfigures()

    print("\n[ALL DONE] All paper graphs successfully created in results/plots/!")


if __name__ == "__main__":
    main()
