#!/usr/bin/env python3
"""
plot_bbr_vs_fairtt.py
Dedicated 2-way head-to-head comparison of FaiRTT vs. BBR matching paper figures:
- Throughput vs. Time (Fig. 3a style)
- Jain's Fairness Index vs. Time (Fig. 4a style)
- Bottleneck Link Utilization vs. Time (Fig. 5 style)
"""

import os
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
OUT_DIRS = [
    os.path.join(RESULTS_DIR, "plots", "controller-comparison"),
    os.path.join(RESULTS_DIR, "plots", "paper-comparison")
]

def load_data(ctrl, sc="different-rtt"):
    path = os.path.join(RESULTS_DIR, ctrl, "raw", sc, "throughput.csv")
    with open(path, newline="", encoding="utf-8") as f:
        r = list(csv.DictReader(f))
    t = [float(x["time"]) for x in r]
    fa = [float(x["flowA_mbps"]) for x in r]
    fb = [float(x["flowB_mbps"]) for x in r]
    agg = [float(x["aggregate_mbps"]) for x in r]
    fair = [float(x["fairness_index"]) for x in r]
    return t, fa, fb, agg, fair

def main():
    bbr_t, bbr_fa, bbr_fb, bbr_agg, bbr_fair = load_data("TcpBbr")
    fai_t, fai_fa, fai_fb, fai_agg, fai_fair = load_data("TcpBbrFairtt")

    for out_dir in OUT_DIRS:
        os.makedirs(out_dir, exist_ok=True)

        # 1. Throughput Comparison (Fig. 3a style)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(bbr_t, bbr_fa, label="BBR: Flow A (Short RTT 40ms)", color="#1f77b4", linestyle="--", alpha=0.85, linewidth=1.6)
        ax.plot(bbr_t, bbr_fb, label="BBR: Flow B (Long RTT 160ms)", color="#1f77b4", linestyle="-", linewidth=2.0)
        ax.plot(fai_t, fai_fa, label="FaiRTT: Flow A (Short RTT 40ms)", color="#d62728", linestyle="--", alpha=0.85, linewidth=1.6)
        ax.plot(fai_t, fai_fb, label="FaiRTT: Flow B (Long RTT 160ms)", color="#d62728", linestyle="-", linewidth=2.0)
        ax.axhline(5.0, color="gray", linestyle=":", label="Fair Share (5.0 Mbps)")
        ax.set_title("FaiRTT vs. BBR: Flow Throughput Comparison (Different RTT)")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Throughput (Mbps)")
        ax.set_ylim(0, 10.5)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="upper right", ncol=2, fontsize=9)
        plt.tight_layout()
        fig.savefig(os.path.join(out_dir, "bbr_vs_fairtt_throughput.png"), dpi=250)
        plt.close(fig)

        # 2. Fairness Index Comparison (Fig. 4a style)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(bbr_t, bbr_fair, label="BBR (Mean: 0.662)", color="#1f77b4", linestyle="-", linewidth=1.8)
        ax.plot(fai_t, fai_fair, label="FaiRTT (Mean: 0.803)", color="#d62728", linestyle="-", linewidth=2.0)
        ax.axhline(1.0, color="black", linestyle=":", label="Ideal Fairness (1.0)")
        ax.set_title("FaiRTT vs. BBR: Jain's Fairness Index vs. Time (Different RTT)")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Jain's Fairness Index")
        ax.set_ylim(0.4, 1.05)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="lower right", fontsize=10)
        plt.tight_layout()
        fig.savefig(os.path.join(out_dir, "bbr_vs_fairtt_fairness.png"), dpi=250)
        plt.close(fig)

        # 3. Bottleneck Link Utilization (Fig. 5 style)
        fig, ax = plt.subplots(figsize=(10, 4.5))
        bbr_util = [a / 10.0 * 100 for a in bbr_agg]
        fai_util = [a / 10.0 * 100 for a in fai_agg]
        ax.plot(bbr_t, bbr_util, label="BBR (Mean: 97.2%)", color="#1f77b4", linestyle="-", linewidth=1.8)
        ax.plot(fai_t, fai_util, label="FaiRTT (Mean: 97.9%)", color="#d62728", linestyle="-", linewidth=2.0)
        ax.axhline(100.0, color="gray", linestyle=":", label="100% Bottleneck Capacity")
        ax.set_title("FaiRTT vs. BBR: Bottleneck Link Utilization vs. Time")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Utilization (%)")
        ax.set_ylim(85, 102)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="lower right", fontsize=10)
        plt.tight_layout()
        fig.savefig(os.path.join(out_dir, "bbr_vs_fairtt_link_utilization.png"), dpi=250)
        plt.close(fig)

    print("Dedicated 2-way FaiRTT vs BBR plots generated successfully.")

if __name__ == "__main__":
    main()
