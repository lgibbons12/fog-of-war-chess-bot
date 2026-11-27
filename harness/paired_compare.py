"""Paired bootstrap of score differences between two runs against the same opponent.

``python -m harness.paired_compare BASE.jsonl... --vs OTHER.jsonl... [--boot 4000]``

Each run is the per-seed summary JSONL files written by ``harness.cli``. Games
are paired by (seed, pair): both runs then share agent and opponent seeds, so
the difference in a pair's mean score (two games, one per color) removes most
seed-to-seed noise. Prints the mean difference OTHER - BASE and a percentile
bootstrap 95% CI over pairs (``random.Random(0)``, so it is reproducible).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import re


def pair_scores(paths: list[str]) -> dict[tuple[int, int], float]:
    """Mean score of A per (seed, pair) over the files; seed parsed from ``..._seed<S>.jsonl``."""
    points: dict[tuple[int, int], list[float]] = {}
    for path in paths:
        seed = int(re.search(r"seed(\d+)\.jsonl$", path).group(1))
        for line in Path(path).read_text().splitlines():
            row = json.loads(line)
            if row["result"] == "1/2-1/2":
                score = 0.5
            else:
                score = 1.0 if (row["result"] == "1-0") == (row["a_color"] == "white") else 0.0
            points.setdefault((seed, row["pair"]), []).append(score)
    return {key: sum(values) / len(values) for key, values in points.items()}


def paired_difference(base: dict, other: dict, boot: int = 4000, seed: int = 0) -> tuple[float, float, float, int]:
    """(mean OTHER - BASE, CI low, CI high, pairs) over the pairs both runs played."""
    keys = sorted(set(base) & set(other))
    diffs = [other[k] - base[k] for k in keys]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(boot))
    return sum(diffs) / len(diffs), means[int(0.025 * boot)], means[int(0.975 * boot) - 1], len(diffs)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", nargs="+")
    parser.add_argument("--vs", nargs="+", required=True)
    parser.add_argument("--boot", type=int, default=4000)
    args = parser.parse_args(argv)
    mean, low, high, pairs = paired_difference(pair_scores(args.base), pair_scores(args.vs), args.boot)
    print(f"{mean:+.4f}  95% CI [{low:+.4f}, {high:+.4f}]  pairs={pairs}")


if __name__ == "__main__":
    main()
