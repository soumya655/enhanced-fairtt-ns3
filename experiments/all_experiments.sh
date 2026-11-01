#!/usr/bin/env bash
set -Eeuo pipefail

# Run all four experiments using the topology in this project. A unique
# temporary NS-3 scratch source is used so existing files are not overwritten.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(basename "$SCRIPT_DIR")" == "experiments" ]]; then
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  PROJECT_ROOT="$SCRIPT_DIR"
fi

NS3_DIR="${NS3_DIR:-/home/soumyadeep/ns-3-dev}"
TCP_TYPE="${TCP_TYPE:-TcpBbr}"
SIM_TIME="${SIM_TIME:-30}"
SOURCE_FILE="${PROJECT_ROOT}/scratch/dumbbell-elephant-mice.cc"
NS3_SCRATCH="${NS3_DIR}/scratch"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/results/${TCP_TYPE}}"
PLOTS_DIR="${PLOTS_DIR:-${PROJECT_ROOT}/results/plots}"
RNG_SEED="${RNG_SEED:-1}"
RNG_RUN="${RNG_RUN:-1}"
V2_FAIRNESS_FLOOR_STRENGTH="${V2_FAIRNESS_FLOOR_STRENGTH:-0.70}"
V2_FAIRNESS_TRANSITION="${V2_FAIRNESS_TRANSITION:-0.15}"
V2_BDP_SMOOTHING_TIME_MS="${V2_BDP_SMOOTHING_TIME_MS:-50}"
V2_MAX_INFLIGHT_BYTES="${V2_MAX_INFLIGHT_BYTES:-524288}"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "[ERROR] Your existing project topology was not found: $SOURCE_FILE" >&2
  exit 1
fi
if [[ ! -x "${NS3_DIR}/ns3" ]]; then
  echo "[ERROR] NS-3 launcher not found/executable: ${NS3_DIR}/ns3" >&2
  echo "Set NS3_DIR to your actual NS-3 installation, e.g.:" >&2
  echo "  NS3_DIR=/path/to/ns-3-dev ./experiments/all_experiments.sh" >&2
  exit 1
fi
if [[ ! -d "$NS3_SCRATCH" ]]; then
  echo "[ERROR] NS-3 scratch directory not found: $NS3_SCRATCH" >&2
  exit 1
fi

# Keep the NS-3 scratch tree untouched apart from this uniquely named
# temporary source file; remove only the file created by this invocation.
SCRATCH_SOURCE="$(mktemp "${NS3_SCRATCH}/dumbbell-fairtt-XXXXXX.cc")"
PROGRAM_NAME="$(basename "$SCRATCH_SOURCE" .cc)"
cleanup() {
  rm -f -- "$SCRATCH_SOURCE"
}
trap cleanup EXIT
cp "$SOURCE_FILE" "$SCRATCH_SOURCE"

mkdir -p "${RESULTS_DIR}/raw" "${RESULTS_DIR}/logs" "${RESULTS_DIR}/metrics"

run_experiment() {
  local name="$1" delay_a="$2" delay_b="$3" elephant_mice="$4"
  local out_dir="${RESULTS_DIR}/raw/${name}"
  local log_file="${RESULTS_DIR}/logs/${name}.log"
  local metrics_input="${out_dir}/throughput.csv"
  local active_stop
  active_stop="$(awk -v sim_time="$SIM_TIME" 'BEGIN { print (sim_time < 29.0) ? sim_time : 29.0 }')"
  mkdir -p "$out_dir" "${RESULTS_DIR}/metrics/${name}"
  if [[ "$elephant_mice" == "1" ]]; then
    metrics_input="${out_dir}/elephant_mice_throughput.csv"
  fi

  echo
  echo "=========================================================="
  echo "Experiment: ${name}"
  echo "Topology:   ${SOURCE_FILE}"
  echo "Controller: ${TCP_TYPE}"
  echo "RTT access delays A/B: ${delay_a} / ${delay_b}"
  echo "Elephant/mice mode: ${elephant_mice}"
  echo "Output: ${out_dir}"
  echo "=========================================================="

  (
    cd "$NS3_DIR"
    ./ns3 run "${PROGRAM_NAME} \
      --bottleneckBw=10Mbps \
      --bottleneckDelay=10ms \
      --accessBw=100Mbps \
      --accessDelayA=${delay_a} \
      --accessDelayB=${delay_b} \
      --queueDisc=FifoQueueDisc \
      --queueSize=100p \
      --tcpTypeId=${TCP_TYPE} \
      --v2FairnessFloorStrength=${V2_FAIRNESS_FLOOR_STRENGTH} \
      --v2FairnessTransition=${V2_FAIRNESS_TRANSITION} \
      --v2BdpSmoothingTimeMs=${V2_BDP_SMOOTHING_TIME_MS} \
      --v2MaxInflightBytes=${V2_MAX_INFLIGHT_BYTES} \
      --seed=${RNG_SEED} \
      --run=${RNG_RUN} \
      --simTime=${SIM_TIME} \
      --flowAStart=1.0 \
      --flowAStop=29.0 \
      --flowBStart=1.0 \
      --flowBStop=29.0 \
      --samplingInterval=0.2 \
      --enableElephantMice=${elephant_mice} \
      --outDir=${out_dir}"
  ) 2>&1 | tee "$log_file"

  if [[ ! -f "$metrics_input" ]]; then
    echo "[ERROR] Expected throughput data was not generated: $metrics_input" >&2
    return 1
  fi
  python3 "${PROJECT_ROOT}/scripts/modified_calculate_fairness.py" \
    --input "$metrics_input" \
    --outdir "${RESULTS_DIR}/metrics/${name}" \
    --active-start 2.0 --active-stop "$active_stop"
  echo "[DONE] ${name}"
}

# BBR is used by default. TcpBbrFairtt applies Algorithm 1 with the documented
# alpha-threshold interpretation described in Fairtt-implementation/README-fairtt-setup.txt.
run_experiment "equal-rtt" "5ms" "5ms" "0"
run_experiment "different-rtt" "5ms" "35ms" "0"
run_experiment "elephant-mice-equal-rtt" "5ms" "5ms" "1"
run_experiment "elephant-mice-different-rtt" "5ms" "35ms" "1"

CONTROLLER_PLOTS_DIR="${PLOTS_DIR}/${TCP_TYPE}"
python3 "${PROJECT_ROOT}/scripts/modified_plot_results.py" \
  --equal-rtt "${RESULTS_DIR}/raw/equal-rtt" \
  --diff-rtt "${RESULTS_DIR}/raw/different-rtt" \
  --elephant-mice-equal "${RESULTS_DIR}/raw/elephant-mice-equal-rtt" \
  --elephant-mice-diff "${RESULTS_DIR}/raw/elephant-mice-different-rtt" \
  --outdir "$CONTROLLER_PLOTS_DIR"

if [[ "$TCP_TYPE" == "TcpBbrEnhancedFairttV2" ]]; then
  python3 "${PROJECT_ROOT}/scripts/plot_v2_control.py" \
    --results "$RESULTS_DIR" \
    --outdir "$CONTROLLER_PLOTS_DIR"
fi

if [[ -n "${COMPARE_BBR_DIR:-}" &&
      -n "${COMPARE_FAIRTT_DIR:-}" &&
      -n "${COMPARE_ENHANCED_DIR:-}" ]]; then
  compare_args=(
    --bbr "$COMPARE_BBR_DIR" \
    --fairtt "$COMPARE_FAIRTT_DIR" \
    --enhanced "$COMPARE_ENHANCED_DIR" \
    --outdir "${PLOTS_DIR}/controller-comparison-v2"
  )
  if [[ -n "${COMPARE_ENHANCED_V2_DIR:-}" ]]; then
    compare_args+=(--enhanced-v2 "$COMPARE_ENHANCED_V2_DIR")
  fi
  python3 "${PROJECT_ROOT}/scripts/compare_controllers.py" "${compare_args[@]}"
fi

echo
echo "=========================================================="
echo "ALL FOUR EXPERIMENTS COMPLETED"
echo "Raw results: ${RESULTS_DIR}/raw/"
echo "Metrics:     ${RESULTS_DIR}/metrics/"
echo "Run logs:    ${RESULTS_DIR}/logs/"
echo "Plots:       ${CONTROLLER_PLOTS_DIR}"
echo "=========================================================="
