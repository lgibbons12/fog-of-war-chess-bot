#!/bin/bash
set -eu
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
exec python3 -u bot.py
