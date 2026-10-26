#!/usr/bin/env bash
set -Eeuo pipefail

# Run all four experiments using the topology ALREADY in this project:
#   scratch/dumbbell-baseline.cc
# The script copies that source into the configured NS-3 installation's
# scratch directory because ./ns3 run builds programs from that tree.
# It does not require a separate topology file beside this script.

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
RESULTS_DIR="${PROJECT_ROOT}/results"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "[ERROR] Your existing project topology was not found: $SOURCE_FILE" >&2
  echo "Keep your current dumbbell-baseline.cc in the project's scratch/ folder." >&2
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

# Use the existing project topology. No second topology file is requested.
cp "$SOURCE_FILE" "${NS3_SCRATCH}/dumbbell-baseline.cc"
mkdir -p "${RESULTS_DIR}/raw" "${RESULTS_DIR}/logs" "${RESULTS_DIR}/metrics"

run_experiment() {
  local name="$1" delay_a="$2" delay_b="$3" elephant_mice="$4"
  local out_dir="${RESULTS_DIR}/raw/${name}"
  local log_file="${RESULTS_DIR}/logs/${name}.log"
  mkdir -p "$out_dir" "${RESULTS_DIR}/metrics/${name}"

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
    ./ns3 run "dumbbell-baseline \
      --bottleneckBw=10Mbps \
      --bottleneckDelay=10ms \
      --accessBw=100Mbps \
      --accessDelayA=${delay_a} \
      --accessDelayB=${delay_b} \
      --queueDisc=FifoQueueDisc \
      --queueSize=100p \
      --tcpTypeId=${TCP_TYPE} \
      --simTime=${SIM_TIME} \
      --flowAStart=1.0 \
      --flowAStop=29.0 \
      --flowBStart=1.0 \
      --flowBStop=29.0 \
      --samplingInterval=0.2 \
      --enableElephantMice=${elephant_mice} \
      --outDir=${out_dir}"
  ) 2>&1 | tee "$log_file"

  if [[ -f "${out_dir}/throughput.csv" && -f "${PROJECT_ROOT}/scripts/calculate_fairness.py" ]]; then
    python3 "${PROJECT_ROOT}/scripts/calculate_fairness.py" \
      --input "${out_dir}/throughput.csv" \
      --outdir "${RESULTS_DIR}/metrics/${name}" \
      --active-start 2.0 --active-stop 29.0
  fi
  echo "[DONE] ${name}"
}

# Four experiments, all using BBR by default (TCP_TYPE can override it).
run_experiment "equal-rtt" "5ms" "5ms" "0"
run_experiment "different-rtt" "5ms" "35ms" "0"
run_experiment "elephant-mice-equal-rtt" "5ms" "5ms" "1"
run_experiment "elephant-mice-different-rtt" "5ms" "35ms" "1"

echo
echo "=========================================================="
echo "ALL FOUR EXPERIMENTS COMPLETED"
echo "Raw results: ${RESULTS_DIR}/raw/"
echo "Metrics:     ${RESULTS_DIR}/metrics/"
echo "Run logs:    ${RESULTS_DIR}/logs/"
echo "=========================================================="
