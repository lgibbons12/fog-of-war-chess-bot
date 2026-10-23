#!/bin/bash
# Build dist/bot.zip for the arena: bot/ (as a package), referee.py, and a
# root run.sh that starts the arena agent (default safety_v2; override with
# `scripts/package.sh <registry name>`). harness/, tests/, replays and
# virtualenvs are never included. Needs only a Python 3 (stdlib zipfile).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "${PYTHON:-}" ]; then :
elif [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then PYTHON=.venv/Scripts/python.exe
else PYTHON=python3
fi

AGENT="${1:-safety_v2}"
mkdir -p dist
rm -f dist/bot.zip
AGENT="$AGENT" "$PYTHON" - <<'EOF'
import os
from pathlib import Path
import zipfile

from bot.agents import REGISTRY

agent = os.environ["AGENT"]
if agent not in REGISTRY:
    raise SystemExit(f"unknown agent {agent!r}; choose from {sorted(REGISTRY)}")

RUN_SH = """#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -u -m bot.protocol --agent {agent}
"""

with zipfile.ZipFile("dist/bot.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    info = zipfile.ZipInfo("run.sh")
    info.external_attr = 0o100755 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, RUN_SH.format(agent=agent))
    archive.write("referee.py", "referee.py")
    for path in sorted(Path("bot").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            archive.write(path, path.as_posix())
    names = archive.namelist()
print(f"dist/bot.zip: agent {agent}, {len(names)} files")
for name in names:
    print("  " + name)
EOF
