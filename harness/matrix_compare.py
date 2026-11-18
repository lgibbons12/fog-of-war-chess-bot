"""Paired bootstrap comparisons between particle-matrix configurations (same replayed games).

Resamples games with replacement and reports the 95% interval of the
difference (A - B) in Brier score (x100) and truth coverage, pooled over
the resampled games. Usage:
    python -m harness.matrix_compare docs/results/<dir> > docs/results/<dir>/comparisons.md
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
import random
import sys

PAIRS = [
    ("trigger: above_n vs ess", "n256-uniform-above_n-supports-sys", "n256-uniform-ess-supports-sys"),
    ("recovery: reexpand vs supports", "n256-uniform-above_n-reexpand-sys", "n256-uniform-above_n-supports-sys"),
    ("diversity: div vs sys", "n256-uniform-above_n-reexpand-div", "n256-uniform-above_n-reexpand-sys"),
    ("model: capture vs uniform", "n256-capture-above_n-reexpand-sys", "n256-uniform-above_n-reexpand-sys"),
    ("n: 256 vs 128", "n256-uniform-above_n-reexpand-sys", "n128-uniform-above_n-reexpand-sys"),
    ("n: 512 vs 256", "n512-uniform-above_n-reexpand-sys", "n256-uniform-above_n-reexpand-sys"),
    ("n: 128 vs 32", "n128-uniform-above_n-supports-sys", "n32-uniform-above_n-supports-sys"),
]
DRAWS = 2000


def main() -> None:
    folder = Path(sys.argv[1])
    games: dict[str, dict[tuple, dict]] = {}
    for line in gzip.open(folder / "matrix_raw.jsonl.gz", "rt", encoding="utf-8"):
        row = json.loads(line)
        games.setdefault(row["config"], {})[(row["white"], row["black"], row["seed"])] = row
    rng = random.Random(0)
    print("| Comparison (A vs B) | Brier x100: A - B [95% CI] | Truth coverage: A - B [95% CI] |")
    print("|---|---|---|")
    for label, a, b in PAIRS:
        keys = sorted(games[a])
        def pooled(rows, num, den):
            return sum(r[num] for r in rows) / max(sum(r[den] for r in rows), 1)
        def diff(sample):
            ra, rb = [games[a][k] for k in sample], [games[b][k] for k in sample]
            return (100 * (pooled(ra, "brier", "moves") - pooled(rb, "brier", "moves")),
                    pooled(ra, "truth_present", "observations") - pooled(rb, "truth_present", "observations"))
        point = diff(keys)
        draws = sorted(diff([rng.choice(keys) for _ in keys]) for _ in range(DRAWS))
        brier = sorted(d[0] for d in draws)
        truth = sorted(d[1] for d in draws)
        lo, hi = int(0.025 * DRAWS), int(0.975 * DRAWS) - 1
        print(f"| {label} | {point[0]:+.3f} [{brier[lo]:+.3f}, {brier[hi]:+.3f}] "
              f"| {point[1]:+.3f} [{truth[lo]:+.3f}, {truth[hi]:+.3f}] |")


if __name__ == "__main__":
    main()
