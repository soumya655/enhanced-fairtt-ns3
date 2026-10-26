#!/usr/bin/env python3
"""
calculate_fairness.py
Enhanced FaiRTT in NS-3 — Stage 1

Computes instantaneous and aggregate Jain's Fairness Index from throughput traces.
Jain's Fairness Formula:
    J = (T_A + T_B)^2 / [2 * (T_A^2 + T_B^2)]
"""

import argparse
import csv
import json
import math
import os
import sys

def calculate_jains_index(ta, tb):
    """Compute Jain's Fairness Index for two values, handling zero edge-cases."""
    s = ta + tb
    if s <= 0.0:
        return 1.0
    sum_sq = (ta * ta) + (tb * tb)
    if sum_sq <= 0.0:
        return 1.0
    return (s * s) / (2.0 * sum_sq)

def calculate_jains_index_many(values):
    """Jain's index for any number of non-negative flow throughputs."""
    values = [max(0.0, float(v)) for v in values]
    if not values:
        return 1.0
    denom = len(values) * sum(v * v for v in values)
    return (sum(values) ** 2 / denom) if denom > 0 else 1.0


def process_elephant_mice_file(filepath, active_start=1.0, active_stop=None):
    """Process long-form elephant_mice_throughput.csv data."""
    if not os.path.exists(filepath):
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    by_time = {}
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        required = {"time", "flow", "throughput_mbps"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                "Elephant/mice CSV must contain: time,flow,throughput_mbps "
                "(cumulative_rx_bytes is optional)."
            )
        for row in reader:
            t = float(row["time"])
            flow = row["flow"].strip()
            rate = max(0.0, float(row["throughput_mbps"]))
            by_time.setdefault(t, {})[flow] = rate

    if not by_time:
        raise ValueError("Empty elephant/mice throughput file.")

    times = sorted(by_time)
    if active_stop is None:
        active_stop = times[-1]
    selected_times = [t for t in times if active_start <= t <= active_stop]
    if not selected_times:
        selected_times = times

    # Fairness is evaluated only among flows with a row at that timestamp.
    # This avoids counting not-yet-started mice as zero-share active flows.
    per_time_rows = []
    for t in selected_times:
        rates = by_time[t]
        row = {"time": t, "flow_rates": rates,
               "aggregate_mbps": sum(rates.values()),
               "fairness_index": calculate_jains_index_many(list(rates.values()))}
        per_time_rows.append(row)

    all_flow_names = sorted({name for t in selected_times for name in by_time[t]})
    mean_rates = {
        name: (
            sum(by_time[t][name] for t in selected_times if name in by_time[t])
            / sum(1 for t in selected_times if name in by_time[t])
        )
        for name in all_flow_names
    }
    metrics = {
        "mode": "elephant_mice",
        "active_start_time": active_start,
        "active_stop_time": active_stop,
        "sample_count": len(selected_times),
        "flow_mean_mbps": {name: round(rate, 4) for name, rate in mean_rates.items()},
        "aggregate_mean_mbps": round(
            sum(row["aggregate_mbps"] for row in per_time_rows) / len(per_time_rows), 4
        ),
        "time_averaged_jains_index": round(
            sum(row["fairness_index"] for row in per_time_rows) / len(per_time_rows), 4
        ),
        "interpretation_note": (
            "Fairness is computed among flows that have rows at each timestamp. "
            "Because mice are staggered and finite, this is not directly comparable "
            "to a fixed set of continuously active flows."
        ),
    }
    return metrics, per_time_rows


def process_throughput_file(filepath, active_start=1.0, active_stop=None):
    if not os.path.exists(filepath):
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    # Detect long-form elephant/mice CSV by its header.
    with open(filepath, "r", newline="") as f:
        header = next(csv.reader(f), [])
    if {"time", "flow", "throughput_mbps"}.issubset(set(header)):
        return process_elephant_mice_file(filepath, active_start, active_stop)

    rows = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            t = float(r["time"])
            ta = float(r["flowA_mbps"])
            tb = float(r["flowB_mbps"])
            agg = float(r["aggregate_mbps"])
            # Recompute or verify fairness index
            j = calculate_jains_index(ta, tb)
            rows.append({
                "time": t,
                "flowA_mbps": ta,
                "flowB_mbps": tb,
                "aggregate_mbps": agg,
                "fairness_index": j
            })

    if not rows:
        print("Error: empty throughput file", file=sys.stderr)
        sys.exit(1)

    if active_stop is None:
        active_stop = rows[-1]["time"]

    # Filter active rows
    active_rows = [r for r in rows if active_start <= r["time"] <= active_stop]
    if not active_rows:
        active_rows = rows

    mean_ta = sum(r["flowA_mbps"] for r in active_rows) / len(active_rows)
    mean_tb = sum(r["flowB_mbps"] for r in active_rows) / len(active_rows)
    mean_agg = sum(r["aggregate_mbps"] for r in active_rows) / len(active_rows)
    mean_jains = sum(r["fairness_index"] for r in active_rows) / len(active_rows)
    overall_jains = calculate_jains_index(mean_ta, mean_tb)

    metrics = {
        "active_start_time": active_start,
        "active_stop_time": active_stop,
        "sample_count": len(active_rows),
        "flowA_mean_mbps": round(mean_ta, 4),
        "flowB_mean_mbps": round(mean_tb, 4),
        "aggregate_mean_mbps": round(mean_agg, 4),
        "time_averaged_jains_index": round(mean_jains, 4),
        "overall_jains_index": round(overall_jains, 4),
        "throughput_ratio_A_to_B": round(mean_ta / mean_tb, 4) if mean_tb > 0 else None
    }

    return metrics, rows

def main():
    parser = argparse.ArgumentParser(description="Calculate Jain's Fairness Index from throughput CSV.")
    parser.add_argument("--input", "-i", required=True, help="Path to throughput.csv")
    parser.add_argument("--outdir", "-o", default=None, help="Directory to save metrics.json")
    parser.add_argument("--active-start", type=float, default=2.0, help="Start time for steady-state analysis")
    parser.add_argument("--active-stop", type=float, default=None, help="Stop time for steady-state analysis")
    args = parser.parse_args()

    metrics, rows = process_throughput_file(args.input, args.active_start, args.active_stop)

    print("\n================ FAIRNESS METRICS ================")
    print(f"File:                      {args.input}")
    print(f"Analysis Window:           {metrics['active_start_time']}s - {metrics['active_stop_time']}s")
    if metrics.get("mode") == "elephant_mice":
        for flow_name, rate in metrics["flow_mean_mbps"].items():
            print(f"{flow_name} Mean Throughput: {rate} Mbps")
        print(f"Aggregate Mean Throughput: {metrics['aggregate_mean_mbps']} Mbps")
        print(f"Time-Averaged Jain's:      {metrics['time_averaged_jains_index']}")
        print(f"Note: {metrics['interpretation_note']}")
    else:
        print(f"Flow A Mean Throughput:    {metrics['flowA_mean_mbps']} Mbps")
        print(f"Flow B Mean Throughput:    {metrics['flowB_mean_mbps']} Mbps")
        print(f"Aggregate Mean Throughput: {metrics['aggregate_mean_mbps']} Mbps")
        print(f"Time-Averaged Jain's:      {metrics['time_averaged_jains_index']}")
        print(f"Overall (Mean) Jain's:     {metrics['overall_jains_index']}")
        if metrics['throughput_ratio_A_to_B'] is not None:
            print(f"Throughput Ratio (A / B):  {metrics['throughput_ratio_A_to_B']}")
    print("==================================================\n")

    out_dir = args.outdir or os.path.dirname(args.input)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        metrics_file = os.path.join(out_dir, "metrics.json")
        with open(metrics_file, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Metrics saved to {metrics_file}")

if __name__ == "__main__":
    main()
