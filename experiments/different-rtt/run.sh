#!/usr/bin/env bash
set -euo pipefail

# Experiment B: Different RTT
# Flow A: 5ms access + 10ms bottleneck + 5ms access = 20ms one-way -> RTT ~ 40ms
# Flow B: 35ms access + 10ms bottleneck + 35ms access = 80ms one-way -> RTT ~ 160ms (4:1 RTT ratio)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NS3_DIR="${NS3_DIR:-/home/soumyadeep/ns-3-dev}"

OUT_RAW="${REPO_ROOT}/results/raw/different-rtt"
OUT_METRICS="${REPO_ROOT}/results/metrics/different-rtt"

mkdir -p "${OUT_RAW}" "${OUT_METRICS}"

echo "=========================================================="
echo "Running Experiment B: Different RTT (Flow A ~40ms, Flow B ~160ms)"
echo "NS-3 Directory: ${NS3_DIR}"
echo "Output Directory: ${OUT_RAW}"
echo "=========================================================="

# Ensure latest dumbbell-baseline.cc is synchronized to NS-3 scratch
cp "${REPO_ROOT}/scratch/dumbbell-baseline.cc" "${NS3_DIR}/scratch/dumbbell-baseline.cc"

cd "${NS3_DIR}"
./ns3 run "dumbbell-baseline \
  --bottleneckBw=10Mbps \
  --bottleneckDelay=10ms \
  --accessBw=100Mbps \
  --accessDelayA=5ms \
  --accessDelayB=35ms \
  --queueDisc=FifoQueueDisc \
  --queueSize=100p \
  --tcpTypeId=TcpCubic \
  --simTime=30 \
  --flowAStart=1.0 \
  --flowAStop=29.0 \
  --flowBStart=1.0 \
  --flowBStop=29.0 \
  --samplingInterval=0.2 \
  --outDir=${OUT_RAW}"

echo "[INFO] Calculating fairness metrics..."
python3 "${REPO_ROOT}/scripts/calculate_fairness.py" \
  --input "${OUT_RAW}/throughput.csv" \
  --outdir "${OUT_METRICS}" \
  --active-start 2.0 \
  --active-stop 29.0

echo "[DONE] Experiment B finished successfully."
