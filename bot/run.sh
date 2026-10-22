#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
# Default agent for submission; a later --agent/--seed in "$@" overrides it.
exec python3 -u protocol.py --agent baseline "$@"
