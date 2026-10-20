#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Detect python with matplotlib
PYTHON_EXEC="python3"
if [ -x "/home/soumyadeep/nest/venv/bin/python" ]; then
  PYTHON_EXEC="/home/soumyadeep/nest/venv/bin/python"
elif [ -x "/home/soumyadeep/venv/bin/python" ]; then
  PYTHON_EXEC="/home/soumyadeep/venv/bin/python"
fi

echo "=========================================================="
echo "Enhanced FaiRTT - Stage 1: Running All Experiments"
echo "Repository Root: ${REPO_ROOT}"
echo "Using Python:    ${PYTHON_EXEC}"
echo "=========================================================="

# 1. Run Experiment A (Equal RTT)
bash "${REPO_ROOT}/experiments/equal-rtt/run.sh"

# 2. Run Experiment B (Different RTT)
bash "${REPO_ROOT}/experiments/different-rtt/run.sh"

# 3. Generate Plots
echo "=========================================================="
echo "Generating Publication-Quality Plots..."
echo "=========================================================="
${PYTHON_EXEC} "${REPO_ROOT}/scripts/plot_results.py" \
  --equal-rtt "${REPO_ROOT}/results/raw/equal-rtt" \
  --diff-rtt "${REPO_ROOT}/results/raw/different-rtt" \
  --outdir "${REPO_ROOT}/results/plots"

echo "=========================================================="
echo "[SUCCESS] All experiments and visualizations completed!"
echo "Check results in:"
echo "  Raw CSVs:  ${REPO_ROOT}/results/raw/"
echo "  Metrics:   ${REPO_ROOT}/results/metrics/"
echo "  Plots:     ${REPO_ROOT}/results/plots/"
echo "=========================================================="
