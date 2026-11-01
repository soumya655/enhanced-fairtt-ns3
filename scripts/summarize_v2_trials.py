#!/usr/bin/env python3
"""Aggregate paired-seed controller metrics and retain the V2 tuning log."""

import argparse
import csv
import json
import os
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCENARIOS = (
    "equal-rtt",
    "different-rtt",
    "elephant-mice-equal-rtt",
    "elephant-mice-different-rtt",
)
SCENARIO_LABELS = (
    "Equal RTT",
    "Different RTT",
    "Equal RTT elephant/mice",
    "Different RTT elephant/mice",
)
CONTROLLERS = (
    ("TcpBbr", "bbr"),
    ("TcpBbrFairtt", "fairtt"),
    ("TcpBbrEnhancedFairtt", "enhanced"),
    ("TcpBbrEnhancedFairttV2", "enhanced_v2"),
)
METRICS = (
    "aggregate_mean_mbps",
    "time_averaged_jains_index",
    "overall_jains_index",
)
SEEDS = (1, 2, 3)


def load_metrics(root, scenario):
    path = os.path.join(root, "metrics", scenario, "metrics.json")
    with open(path, encoding="utf-8") as metrics_file:
        return json.load(metrics_file)


def seed_roots(args, seed):
    return {
        "bbr": getattr(args, f"seed{seed}_bbr"),
        "fairtt": getattr(args, f"seed{seed}_fairtt"),
        "enhanced": getattr(args, f"seed{seed}_enhanced"),
        "enhanced_v2": getattr(args, f"seed{seed}_enhanced_v2"),
    }


def write_rows(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_reports(args):
    per_seed_rows = []
    experiment_rows = []
    values = {}
    flow_values = {}
    cwnd_values = {}
    for seed in SEEDS:
        roots = seed_roots(args, seed)
        for scenario in SCENARIOS:
            metrics_by_controller = {
                name: load_metrics(roots[argument], scenario)
                for name, argument in CONTROLLERS
            }
            enhanced = metrics_by_controller["TcpBbrEnhancedFairtt"]
            for name, _ in CONTROLLERS:
                metrics = metrics_by_controller[name]
                flow_rates = metrics.get(
                    "flow_mean_mbps",
                    {
                        "flowA": metrics.get("flowA_mean_mbps", 0.0),
                        "flowB": metrics.get("flowB_mean_mbps", 0.0),
                    },
                )
                row = {
                    "seed": seed,
                    "scenario": scenario,
                    "controller": name,
                    **{metric: metrics[metric] for metric in METRICS},
                    "per_flow_mean_mbps": json.dumps(flow_rates, sort_keys=True),
                    "cwnd_stability": json.dumps(
                        metrics.get("cwnd_stability", {}).get("per_flow", {}),
                        sort_keys=True,
                    ),
                }
                per_seed_rows.append(row)
                values.setdefault((scenario, name), []).append(row)
                for flow, rate in flow_rates.items():
                    flow_values.setdefault((scenario, name, flow), []).append(float(rate))
                stability = metrics.get("cwnd_stability", {}).get("per_flow", {})
                for flow, flow_stats in stability.items():
                    for metric in (
                        "mean_cwnd_packets",
                        "cwnd_coefficient_of_variation",
                        "mean_absolute_relative_step",
                        "max_absolute_relative_step",
                    ):
                        key = (scenario, name, flow, metric)
                        cwnd_values.setdefault(key, []).append(float(flow_stats[metric]))
                parameters = dict(metrics.get("experiment_metadata", {}))
                equations = ""
                if name == "TcpBbrEnhancedFairttV2":
                    parameters.update(
                        {
                            "v2FairnessFloorStrength": 0.70,
                            "v2FairnessTransition": 0.15,
                            "v2BdpSmoothingTimeMs": 50,
                            "v2MaxInflightBytes": 512 * 1024,
                            "queueGammaPenalty": 0.10,
                        }
                    )
                    equations = (
                        "e=(maxPathMinRTT-minPathMinRTT)/maxPathMinRTT; "
                        "beta=clamp(0.8-0.4e,0.2,0.8); "
                        "gamma=clamp(0.99-0.25e-0.10q,0.55,0.99); "
                        "q=max(0,lastRTT/minRTT-1); "
                        "s=floor+(1-floor)*(e/(e+transition))*flowRTTExcess; "
                        "target=1-s*(1-clamp(gamma*minRTT/lastRTT,0.05,1)); "
                        "S_t=exp(-dt/tau)S_(t-1)+(1-exp(-dt/tau))target; "
                        "inflightTarget<=512KiB; GetSsThresh<=512KiB"
                    )
                experiment_rows.append(
                    {
                        **row,
                        "variant": (
                            "V2-selected"
                            if name == "TcpBbrEnhancedFairttV2"
                            else "paired-controller"
                        ),
                        "parameters": json.dumps(parameters, sort_keys=True),
                        "equations": equations,
                        "delta_time_jain_vs_enhanced": round(
                            metrics["time_averaged_jains_index"]
                            - enhanced["time_averaged_jains_index"],
                            4,
                        ),
                        "delta_overall_jain_vs_enhanced": round(
                            metrics["overall_jains_index"]
                            - enhanced["overall_jains_index"],
                            4,
                        ),
                        "delta_aggregate_mbps_vs_enhanced": round(
                            metrics["aggregate_mean_mbps"]
                            - enhanced["aggregate_mean_mbps"],
                            4,
                        ),
                        "cwnd_stability": json.dumps(
                            metrics.get("cwnd_stability", {}).get("per_flow", {}),
                            sort_keys=True,
                        ),
                    }
                )

    if args.v2_trial_default:
        for scenario in SCENARIOS:
            metrics = load_metrics(args.v2_trial_default, scenario)
            enhanced = load_metrics(args.seed1_enhanced, scenario)
            experiment_rows.append(
                {
                    "seed": 1,
                    "scenario": scenario,
                    "controller": "TcpBbrEnhancedFairttV2",
                    "aggregate_mean_mbps": metrics["aggregate_mean_mbps"],
                    "time_averaged_jains_index": metrics["time_averaged_jains_index"],
                    "overall_jains_index": metrics["overall_jains_index"],
                    "variant": "V2-trial-floor035-no-queue-gamma-unverified-seed",
                    "parameters": json.dumps(
                        {
                            "fairnessFloorStrength": 0.35,
                            "fairnessTransition": 0.15,
                            "smoothingTimeMs": 50,
                            "queueGammaPenalty": 0.0,
                            "maxInflightBytes": "uint32 saturation only",
                            "seedMetadata": "unavailable; tuning only",
                        },
                        sort_keys=True,
                    ),
                    "equations": (
                        "e=(maxPathMinRTT-minPathMinRTT)/maxPathMinRTT; "
                        "beta=clamp(0.8-0.4e,0.2,0.8); "
                        "gamma=clamp(0.99-0.25e,0.55,0.99); "
                        "s=floor+(1-floor)*(e/(e+transition))*flowRTTExcess; "
                        "target=1-s*(1-clamp(gamma*minRTT/lastRTT,0.05,1)); "
                        "S_t=exp(-dt/tau)S_(t-1)+(1-exp(-dt/tau))target"
                    ),
                    "delta_time_jain_vs_enhanced": round(
                        metrics["time_averaged_jains_index"]
                        - enhanced["time_averaged_jains_index"],
                        4,
                    ),
                    "delta_overall_jain_vs_enhanced": round(
                        metrics["overall_jains_index"] - enhanced["overall_jains_index"],
                        4,
                    ),
                    "delta_aggregate_mbps_vs_enhanced": round(
                        metrics["aggregate_mean_mbps"]
                        - enhanced["aggregate_mean_mbps"],
                        4,
                    ),
                    "cwnd_stability": json.dumps(
                        metrics.get("cwnd_stability", {}).get("per_flow", {}),
                        sort_keys=True,
                    ),
                }
            )
    if args.v2_trial_floor70_capped:
        for scenario in SCENARIOS:
            metrics = load_metrics(args.v2_trial_floor70_capped, scenario)
            enhanced = load_metrics(args.seed1_enhanced, scenario)
            experiment_rows.append(
                {
                    "seed": 1,
                    "scenario": scenario,
                    "controller": "TcpBbrEnhancedFairttV2",
                    "aggregate_mean_mbps": metrics["aggregate_mean_mbps"],
                    "time_averaged_jains_index": metrics["time_averaged_jains_index"],
                    "overall_jains_index": metrics["overall_jains_index"],
                    "variant": "V2-trial-floor070-qgamma10-cap512-ssThresh-unbounded",
                    "parameters": json.dumps(
                        {
                            "fairnessFloorStrength": 0.70,
                            "fairnessTransition": 0.15,
                            "smoothingTimeMs": 50,
                            "queueGammaPenalty": 0.10,
                            "maxInflightBytes": 524288,
                            "GetSsThresh": "not yet capped",
                            "seedMetadata": "unavailable; tuning only",
                        },
                        sort_keys=True,
                    ),
                    "equations": (
                        "e=(maxPathMinRTT-minPathMinRTT)/maxPathMinRTT; "
                        "beta=clamp(0.8-0.4e,0.2,0.8); "
                        "gamma=clamp(0.99-0.25e-0.10q,0.55,0.99); "
                        "q=max(0,lastRTT/minRTT-1); "
                        "s=floor+(1-floor)*(e/(e+transition))*flowRTTExcess; "
                        "target=1-s*(1-clamp(gamma*minRTT/lastRTT,0.05,1)); "
                        "S_t=exp(-dt/tau)S_(t-1)+(1-exp(-dt/tau))target"
                    ),
                    "delta_time_jain_vs_enhanced": round(
                        metrics["time_averaged_jains_index"]
                        - enhanced["time_averaged_jains_index"],
                        4,
                    ),
                    "delta_overall_jain_vs_enhanced": round(
                        metrics["overall_jains_index"] - enhanced["overall_jains_index"],
                        4,
                    ),
                    "delta_aggregate_mbps_vs_enhanced": round(
                        metrics["aggregate_mean_mbps"]
                        - enhanced["aggregate_mean_mbps"],
                        4,
                    ),
                }
            )

    os.makedirs(args.outdir, exist_ok=True)
    per_seed_path = os.path.join(args.outdir, "per-seed-controller-metrics.csv")
    aggregate_path = os.path.join(args.outdir, "seed-aggregate-comparison.csv")
    flow_path = os.path.join(args.outdir, "seed-aggregate-per-flow.csv")
    log_path = os.path.join(args.outdir, "v2-experiment-log.csv")
    write_rows(
        per_seed_path,
        (
            "seed",
            "scenario",
            "controller",
            *METRICS,
            "per_flow_mean_mbps",
            "cwnd_stability",
        ),
        per_seed_rows,
    )

    aggregate_rows = []
    for (scenario, controller), rows in sorted(values.items()):
        summary = {"scenario": scenario, "controller": controller, "seed_count": len(rows)}
        for metric in METRICS:
            samples = [row[metric] for row in rows]
            summary[f"{metric}_mean"] = round(statistics.mean(samples), 6)
            summary[f"{metric}_sample_sd"] = round(
                statistics.stdev(samples) if len(samples) > 1 else 0.0, 6
            )
        aggregate_rows.append(summary)
    aggregate_fields = ("scenario", "controller", "seed_count") + tuple(
        field
        for metric in METRICS
        for field in (f"{metric}_mean", f"{metric}_sample_sd")
    )
    write_rows(aggregate_path, aggregate_fields, aggregate_rows)
    flow_rows = []
    for (scenario, controller, flow), samples in sorted(flow_values.items()):
        flow_rows.append(
            {
                "scenario": scenario,
                "controller": controller,
                "flow": flow,
                "seed_count": len(samples),
                "mean_mbps": round(statistics.mean(samples), 6),
                "sample_sd_mbps": round(
                    statistics.stdev(samples) if len(samples) > 1 else 0.0, 6
                ),
            }
        )
    write_rows(
        flow_path,
        ("scenario", "controller", "flow", "seed_count", "mean_mbps", "sample_sd_mbps"),
        flow_rows,
    )
    cwnd_rows = []
    for (scenario, controller, flow, metric), samples in sorted(cwnd_values.items()):
        cwnd_rows.append(
            {
                "scenario": scenario,
                "controller": controller,
                "flow": flow,
                "metric": metric,
                "seed_count": len(samples),
                "mean": round(statistics.mean(samples), 6),
                "sample_sd": round(
                    statistics.stdev(samples) if len(samples) > 1 else 0.0, 6
                ),
            }
        )
    write_rows(
        os.path.join(args.outdir, "seed-aggregate-cwnd-stability.csv"),
        ("scenario", "controller", "flow", "metric", "seed_count", "mean", "sample_sd"),
        cwnd_rows,
    )

    figure, axes = plt.subplots(1, 3, figsize=(17, 5))
    positions = list(range(len(SCENARIOS)))
    width = 0.75 / len(CONTROLLERS)
    metric_titles = (
        ("time_averaged_jains_index", "Time-averaged Jain fairness", (0, 1.05)),
        ("overall_jains_index", "Overall Jain fairness", (0, 1.05)),
        ("aggregate_mean_mbps", "Aggregate throughput (Mbps)", (0, 10.5)),
    )
    colors = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728")
    for axis, (metric, title, limits) in zip(axes, metric_titles):
        for index, (controller, _) in enumerate(CONTROLLERS):
            selected = {
                row["scenario"]: row
                for row in aggregate_rows
                if row["controller"] == controller
            }
            means = [selected[scenario][f"{metric}_mean"] for scenario in SCENARIOS]
            deviations = [
                selected[scenario][f"{metric}_sample_sd"] for scenario in SCENARIOS
            ]
            offset = (index - (len(CONTROLLERS) - 1) / 2) * width
            axis.bar(
                [position + offset for position in positions],
                means,
                width,
                yerr=deviations,
                capsize=2,
                color=colors[index],
                label=controller,
            )
        axis.set_title(title)
        axis.set_xticks(positions, SCENARIO_LABELS, rotation=20, ha="right")
        axis.set_ylim(*limits)
        axis.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8)
    figure.tight_layout()
    plot_path = os.path.join(args.outdir, "seed-aggregate-comparison.png")
    figure.savefig(plot_path, dpi=220)
    plt.close(figure)

    stability_figure, stability_axes = plt.subplots(2, 2, figsize=(14, 9))
    for axis, scenario, label in zip(
        stability_axes.flat, SCENARIOS, SCENARIO_LABELS
    ):
        scenario_rows = [
            row
            for row in cwnd_rows
            if row["scenario"] == scenario
            and row["metric"] == "cwnd_coefficient_of_variation"
        ]
        flows = sorted({row["flow"] for row in scenario_rows})
        if not flows:
            axis.set_visible(False)
            continue
        width = 0.75 / len(CONTROLLERS)
        for index, (controller, _) in enumerate(CONTROLLERS):
            means = []
            deviations = []
            for flow in flows:
                row = next(
                    (
                        item
                        for item in scenario_rows
                        if item["controller"] == controller and item["flow"] == flow
                    ),
                    None,
                )
                means.append(row["mean"] if row else 0.0)
                deviations.append(row["sample_sd"] if row else 0.0)
            offset = (index - (len(CONTROLLERS) - 1) / 2) * width
            axis.bar(
                [position + offset for position in range(len(flows))],
                means,
                width,
                yerr=deviations,
                capsize=2,
                color=colors[index],
                label=controller,
            )
        axis.set_title(label)
        axis.set_xticks(range(len(flows)), flows)
        axis.set_ylabel("Cwnd coefficient of variation")
        axis.grid(axis="y", alpha=0.3)
    stability_axes.flat[0].legend(fontsize=8)
    stability_figure.tight_layout()
    stability_figure.savefig(
        os.path.join(args.outdir, "seed-aggregate-cwnd-stability.png"), dpi=220
    )
    plt.close(stability_figure)

    log_fields = (
        "variant",
        "seed",
        "scenario",
        "controller",
        "parameters",
        "equations",
        "per_flow_mean_mbps",
        *METRICS,
        "cwnd_stability",
        "delta_time_jain_vs_enhanced",
        "delta_overall_jain_vs_enhanced",
        "delta_aggregate_mbps_vs_enhanced",
    )
    write_rows(log_path, log_fields, experiment_rows)
    print(
        f"Wrote {per_seed_path}, {aggregate_path}, {flow_path}, {log_path}, "
        f"{plot_path}, and seed-aggregate-cwnd-stability.csv/.png"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for seed in SEEDS:
        for label in ("bbr", "fairtt", "enhanced", "enhanced-v2"):
            parser.add_argument(f"--seed{seed}-{label}", required=True)
    parser.add_argument(
        "--v2-trial-default",
        help="V2 seed-1 trial root using floor=0.35 and no queue-dependent gamma term",
    )
    parser.add_argument(
        "--v2-trial-floor70-capped",
        help="V2 seed-1 cap trial before GetSsThresh was bounded",
    )
    parser.add_argument("--outdir", required=True)
    build_reports(parser.parse_args())


if __name__ == "__main__":
    main()
