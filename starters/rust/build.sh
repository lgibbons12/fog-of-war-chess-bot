#!/bin/bash
set -euo pipefail
rustc --edition=2021 -C opt-level=2 bot.rs -o bot
