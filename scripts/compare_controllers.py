#!/usr/bin/env python3
"""Build consistent metric tables and plots for BBR, FaiRTT, and enhanced variants."""

import argparse
import csv
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCENARIOS = {
    "equal-rtt": "Equal RTT",
    "different-rtt": "Different RTT",
    "elephant-mice-equal-rtt": "Equal RTT elephant/mice",
    "elephant-mice-different-rtt": "Different RTT elephant/mice",
}
CONTROLLERS = (
    ("TcpBbr", "bbr"),
    ("TcpBbrFairtt", "fairtt"),
    ("TcpBbrEnhancedFairtt", "enhanced"),
    ("TcpBbrEnhancedFairttV2", "enhanced_v2"),
)

CONTROLLER_COLORS = {
    "TcpBbr": "#1f77b4",
    "TcpBbrFairtt": "#ff7f0e",
    "TcpBbrEnhancedFairtt": "#2ca02c",
    "TcpBbrEnhancedFairttV2": "#d62728",
}


def load_metrics(root, scenario):
    metrics_path = os.path.join(root, "metrics", scenario, "metrics.json")
    with open(metrics_path, encoding="utf-8") as metrics_file:
        return json.load(metrics_file)


def available_controllers(roots):
        return tuple(
            (controller, argument)
            for controller, argument in CONTROLLERS
            if argument in roots
        )


def flow_mean_rates(metrics):
    if "flow_mean_mbps" in metrics:
        return metrics["flow_mean_mbps"]
    return {
        "flowA": metrics["flowA_mean_mbps"],
        "flowB": metrics["flowB_mean_mbps"],
    }


def load_comparison(roots, controllers):
    rows = []
    for scenario, label in SCENARIOS.items():
        metrics_by_controller = {
            controller: load_metrics(roots[argument], scenario)
            for controller, argument in controllers
        }
        fairtt = metrics_by_controller["TcpBbrFairtt"]
        for controller, _ in controllers:
            metrics = metrics_by_controller[controller]
            rows.append(
                {
                    "scenario": scenario,
                    "scenario_label": label,
                    "controller": controller,
                    "aggregate_mean_mbps": metrics["aggregate_mean_mbps"],
                    "time_averaged_jains_index": metrics["time_averaged_jains_index"],
                    "overall_jains_index": metrics["overall_jains_index"],
                    "delta_time_averaged_jain_vs_fairtt": round(
                        metrics["time_averaged_jains_index"]
                        - fairtt["time_averaged_jains_index"],
                        4,
                    ),
                    "delta_overall_jain_vs_fairtt": round(
                        metrics["overall_jains_index"] - fairtt["overall_jains_index"],
                        4,
                    ),
                    "delta_aggregate_mbps_vs_fairtt": round(
                        metrics["aggregate_mean_mbps"] - fairtt["aggregate_mean_mbps"],
                        4,
                    ),
                    "per_flow_mean_mbps": flow_mean_rates(metrics),
                    "cwnd_stability": metrics.get("cwnd_stability", {}).get("per_flow", {}),
                    "cwnd_sampling_interval_seconds": metrics.get(
                        "cwnd_stability", {}
                    ).get("sampling_interval_seconds"),
                    "experiment_metadata": metrics.get("experiment_metadata", {}),
                }
            )
    return rows


def write_tables(rows, output_dir):
    json_path = os.path.join(output_dir, "controller-comparison.json")
    with open(json_path, "w", encoding="utf-8") as json_file:
        json.dump(rows, json_file, indent=2)

    csv_path = os.path.join(output_dir, "controller-comparison.csv")
    fields = (
        "scenario",
        "scenario_label",
        "controller",
        "aggregate_mean_mbps",
        "time_averaged_jains_index",
        "overall_jains_index",
        "delta_time_averaged_jain_vs_fairtt",
        "delta_overall_jain_vs_fairtt",
        "delta_aggregate_mbps_vs_fairtt",
        "per_flow_mean_mbps",
        "cwnd_stability",
        "cwnd_sampling_interval_seconds",
        "experiment_metadata",
    )
    with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["per_flow_mean_mbps"] = json.dumps(row["per_flow_mean_mbps"], sort_keys=True)
            output_row["cwnd_stability"] = json.dumps(row["cwnd_stability"], sort_keys=True)
            output_row["experiment_metadata"] = json.dumps(
                row["experiment_metadata"], sort_keys=True
            )
            writer.writerow(output_row)

    flow_csv_path = os.path.join(output_dir, "per-flow-throughput.csv")
    with open(flow_csv_path, "w", newline="", encoding="utf-8") as flow_csv:
        writer = csv.DictWriter(
            flow_csv,
            fieldnames=("scenario", "scenario_label", "controller", "flow", "mean_mbps"),
        )
        writer.writeheader()
        for row in rows:
            for flow, mean_rate in sorted(row["per_flow_mean_mbps"].items()):
                writer.writerow(
                    {
                        "scenario": row["scenario"],
                        "scenario_label": row["scenario_label"],
                        "controller": row["controller"],
                        "flow": flow,
                        "mean_mbps": mean_rate,
                    }
                )

    stability_csv_path = os.path.join(output_dir, "cwnd-stability.csv")
    with open(stability_csv_path, "w", newline="", encoding="utf-8") as stability_csv:
        writer = csv.DictWriter(
            stability_csv,
            fieldnames=(
                "scenario",
                "controller",
                "flow",
                "sampling_interval_seconds",
                "sample_count",
                "mean_cwnd_packets",
                "cwnd_coefficient_of_variation",
                "mean_absolute_relative_step",
                "max_absolute_relative_step",
            ),
        )
        writer.writeheader()
        for row in rows:
            for flow, values in sorted(row["cwnd_stability"].items()):
                writer.writerow(
                    {
                        "scenario": row["scenario"],
                        "controller": row["controller"],
                        "flow": flow,
                        "sampling_interval_seconds": row[
                            "cwnd_sampling_interval_seconds"
                        ],
                        **values,
                    }
                )
    return json_path, csv_path, flow_csv_path, stability_csv_path


def plot_metric_comparison(rows, output_dir, controllers):
    names = [name for name, _ in controllers]
    labels = list(SCENARIOS.values())
    positions = list(range(len(labels)))
    width = 0.75 / len(names)
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    metric_fields = (
        ("time_averaged_jains_index", "Time-averaged Jain fairness", (0, 1.05)),
        ("overall_jains_index", "Overall Jain fairness", (0, 1.05)),
        ("aggregate_mean_mbps", "Aggregate throughput (Mbps)", (0, 10.5)),
    )
    for axis, (field, title, limits) in zip(axes, metric_fields):
        for index, controller in enumerate(names):
            selected = [row for row in rows if row["controller"] == controller]
            values = [next(row[field] for row in selected if row["scenario_label"] == label)
                      for label in labels]
            offset = (index - (len(names) - 1) / 2) * width
            axis.bar([position + offset for position in positions], values, width, label=controller)
        axis.set_title(title)
        axis.set_xticks(positions, labels, rotation=20, ha="right")
        axis.set_ylim(*limits)
        axis.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    path = os.path.join(output_dir, "controller-metrics-comparison.png")
    fig.savefig(path, dpi=220)
    plt.close(fig)


def plot_per_flow_comparison(roots, output_dir, controllers):
    for scenario, label in SCENARIOS.items():
        figure, axis = plt.subplots(figsize=(11, 5))
        series = []
        for controller, argument in controllers:
            path = os.path.join(roots[argument], "metrics", scenario, "metrics.json")
            with open(path, encoding="utf-8") as metrics_file:
                metrics = json.load(metrics_file)
            flows = flow_mean_rates(metrics)
            series.append((controller, flows))

        flow_names = sorted({flow for _, flows in series for flow in flows})
        positions = list(range(len(flow_names)))
        width = 0.75 / len(series)
        for index, (controller, flows) in enumerate(series):
            values = [flows.get(flow, 0.0) for flow in flow_names]
            axis.bar(
                [position + (index - (len(series) - 1) / 2) * width
                 for position in positions],
                values,
                width,
                label=controller,
            )
        axis.set_title(f"Per-flow mean throughput: {label}")
        axis.set_ylabel("Mbps")
        axis.set_xticks(positions, flow_names, rotation=20, ha="right")
        axis.grid(axis="y", alpha=0.3)
        axis.legend(fontsize=8)
        figure.tight_layout()
        figure.savefig(
            os.path.join(output_dir, f"{scenario}-per-flow-throughput.png"),
            dpi=220,
        )
        plt.close(figure)


def plot_cwnd_comparison(roots, output_dir, controllers):
    for scenario, label in SCENARIOS.items():
        figure, axis = plt.subplots(figsize=(12, 5))
        drew_data = False
        for controller, argument in controllers:
            path = os.path.join(roots[argument], "raw", scenario, "cwnd.csv")
            if not os.path.isfile(path):
                continue
            with open(path, newline="", encoding="utf-8") as cwnd_file:
                samples = list(csv.DictReader(cwnd_file))
            for flow in sorted({row["flow"] for row in samples}):
                rows_for_flow = [row for row in samples if row["flow"] == flow]
                times = [float(row["time"]) for row in rows_for_flow]
                window = [float(row["cwnd_packets"]) for row in rows_for_flow]
                axis.plot(
                    times,
                    window,
                    color=CONTROLLER_COLORS[controller],
                    alpha=0.8,
                    linewidth=1.0,
                    label=f"{controller} {flow}",
                )
                drew_data = True
        if not drew_data:
            plt.close(figure)
            continue
        axis.set_title(f"Congestion-window stability proxy: {label}")
        axis.set_xlabel("Time (seconds)")
        axis.set_ylabel("Congestion window (packets)")
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize=7, ncol=2)
        figure.tight_layout()
        figure.savefig(os.path.join(output_dir, f"{scenario}-cwnd-stability.png"), dpi=220)
        plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbr", required=True, help="TcpBbr result root")
    parser.add_argument("--fairtt", required=True, help="TcpBbrFairtt result root")
    parser.add_argument("--enhanced", required=True, help="TcpBbrEnhancedFairtt result root")
    parser.add_argument(
        "--enhanced-v2", help="Optional TcpBbrEnhancedFairttV2 result root"
    )
    parser.add_argument("--outdir", required=True, help="Comparison output directory")
    args = parser.parse_args()

    roots = {"bbr": args.bbr, "fairtt": args.fairtt, "enhanced": args.enhanced}
    if args.enhanced_v2:
        roots["enhanced_v2"] = args.enhanced_v2
    controllers = available_controllers(roots)
    os.makedirs(args.outdir, exist_ok=True)
    rows = load_comparison(roots, controllers)
    json_path, csv_path, flow_csv_path, stability_csv_path = write_tables(rows, args.outdir)
    plot_metric_comparison(rows, args.outdir, controllers)
    plot_per_flow_comparison(roots, args.outdir, controllers)
    plot_cwnd_comparison(roots, args.outdir, controllers)
    print(f"Wrote {json_path}, {csv_path}, {flow_csv_path}, and {stability_csv_path}")


if __name__ == "__main__":
    main()
