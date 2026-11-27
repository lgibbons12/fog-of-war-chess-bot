#!/usr/bin/env bash
# Step 3 Part B gate: every particle agent vs safety_v2, 200 pairs x seeds 0-2.
# Usage (repo root): bash docs/results/2026-11-22-step3-gate/run.sh [python] [workers]
set -euo pipefail
PY=${1:-.venv/Scripts/python.exe}
WORKERS=${2:-20}
OUT=docs/results/2026-11-22-step3-gate
for agent in ${AGENTS:-particle_v2 particle_ev100 particle_ev300 particle_ev1000}; do
  "$PY" -m harness.cli "$agent" safety_v2 --pairs 200 --seed 0 1 2 --workers "$WORKERS" \
    --save-replays "replays/gate/$agent" --summary "$OUT/summaries" > "$OUT/cli_${agent}.txt" 2>/dev/null
  "$PY" -m harness.breakdown "replays/gate/$agent" --agent "$agent" > "$OUT/breakdown_${agent}.txt"
done
