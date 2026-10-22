#!/bin/bash
# Pre-upload check: unzip dist/bot.zip into a temp directory and, from there,
# play one local referee.py game in each color against baseline.py.
# POSIX only (the referee is). PYTHON must have chess installed; its directory
# is put first on PATH so the zip's run.sh finds that python3.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
# Absolute path without resolving symlinks (resolving would escape the venv).
PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
export PATH="$(dirname "$PYTHON"):$PATH"
REPO="$PWD"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$PYTHON" -m zipfile -e dist/bot.zip "$TMP/bot"
cd "$TMP/bot"
BOT="bash $TMP/bot/run.sh"
BASELINE="$PYTHON $REPO/baseline.py --seed 1"
status=0
for color in white black; do
    if [ "$color" = white ]; then white="$BOT"; black="$BASELINE"; else white="$BASELINE"; black="$BOT"; fi
    "$PYTHON" referee.py --trusted-local --white "$white" --black "$black" \
        --max-plies 1000 --output "$TMP/$color.json"
    "$PYTHON" - "$TMP/$color.json" "$color" <<'EOF' || status=1
import json, sys
replay = json.load(open(sys.argv[1]))
print(f"  bot as {sys.argv[2]}: {replay['result']} {replay['reason']}")
if "failedSide" in replay:
    sys.exit(f"  FAILED: {replay['failedSide']} failed: {replay['reason']}")
EOF
done
exit $status
