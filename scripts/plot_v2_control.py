#!/usr/bin/env python3
"""Plot V2's directly traced BDP reduction and fairness-control signals."""

import argparse
import csv
import math
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCENARIOS = (
    "equal-rtt",
    "different-rtt",
    "elephant-mice-equal-rtt",
    "elephant-mice-different-rtt",
)
TRACES = ("BdpReduction", "FairnessError", "ReductionStrength")


def load_trace(path):
    grouped = defaultdict(lambda: defaultdict(list))
    with open(path, newline="", encoding="utf-8") as trace_file:
        reader = csv.DictReader(trace_file)
        expected = {"time", "flow", "trace", "old_value", "new_value"}
        if not expected.issubset(reader.fieldnames or ()):
            raise ValueError(f"{path} is missing required V2 trace columns")
        for row in reader:
            time = float(row["time"])
            value = float(row["new_value"])
            if not math.isfinite(time) or not math.isfinite(value):
                raise ValueError(f"{path} contains a non-finite trace value")
            if row["trace"] not in TRACES:
                raise ValueError(f"{path} contains unknown trace {row['trace']!r}")
            grouped[row["trace"]][row["flow"]].append((time, value))
    return grouped


def plot_scenario(path, outdir, scenario):
    grouped = load_trace(path)
    if not any(grouped.values()):
        raise ValueError(f"{path} contains no V2 controller trace events")

    figure, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    for axis, trace_name in zip(axes, TRACES):
        for flow, samples in sorted(grouped[trace_name].items()):
            samples.sort()
            axis.plot(
                [sample[0] for sample in samples],
                [sample[1] for sample in samples],
                label=flow,
                linewidth=1.2,
            )
        axis.set_ylabel(trace_name)
        axis.grid(alpha=0.3)
        axis.set_ylim(0.0, 1.05)
        if grouped[trace_name]:
            axis.legend()
    axes[-1].set_xlabel("Simulation time (s)")
    figure.suptitle(f"V2 control signals: {scenario}")
    figure.tight_layout()
    output_path = os.path.join(outdir, f"{scenario}-v2-control.png")
    figure.savefig(output_path, dpi=200)
    plt.close(figure)
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, help="Controller results root")
    parser.add_argument("--outdir", required=True, help="Output directory for PNG plots")
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    outputs = []
    for scenario in SCENARIOS:
        trace_path = os.path.join(args.results, "raw", scenario, "v2_controller.csv")
        if not os.path.isfile(trace_path):
            raise FileNotFoundError(f"V2 control trace not found: {trace_path}")
        outputs.append(plot_scenario(trace_path, args.outdir, scenario))
    print("Wrote V2 control plots: " + ", ".join(outputs))


if __name__ == "__main__":
    main()
