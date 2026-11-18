"""Render markdown tables from a particle-matrix results folder (see ``harness.particle_matrix``).

Usage: python -m harness.matrix_report docs/results/<dir>  > docs/results/<dir>/tables.md
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys

FACTORS = ("n", "model", "trigger", "recovery", "diversity")
METRICS = (("truth_coverage", "Truth coverage", "{:.3f}"), ("truth_weight", "Truth weight", "{:.3f}"),
           ("depletions_per_game", "Depletions/game", "{:.2f}"), ("brier", "Brier (x100)", "{:.3f}"),
           ("logloss", "Log loss", "{:.4f}"), ("missed_loss_frac", "Missed losses", "{:.3f}"),
           ("min_risk_pick_loses", "Min-risk pick loses", "{:.4f}"),
           ("median_move_s", "Median s/move", "{:.3f}"), ("max_move_s", "Max s/move", "{:.2f}"))


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def value(row: dict, key: str) -> float:
    number = float(row[key])
    return number * 100 if key == "brier" else number


def table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    folder = Path(sys.argv[1])
    rows = load(folder / "matrix_summary.csv")
    reference = next(r for r in rows if r["config"] == "possibility")
    configs = [r for r in rows if r["config"] != "possibility"]
    out = []

    out.append("## Main effects (mean over all other factors)\n")
    for factor in FACTORS:
        levels = list(dict.fromkeys(r[factor] for r in configs))
        body = []
        for level in levels:
            group = [r for r in configs if r[factor] == level]
            body.append([level, str(len(group))] + [fmt.format(sum(value(r, key) for r in group) / len(group))
                                                    for key, _, fmt in METRICS])
        out.append(f"### {factor}\n")
        out.append(table([factor, "configs"] + [label for _, label, _ in METRICS], body) + "\n")

    out.append("## Reference: possibility tracker as a predictor\n")
    out.append(table(["Brier (x100)", "Log loss", "Min-risk pick loses"],
                     [[f"{value(reference, 'brier'):.3f}", f"{float(reference['logloss']):.4f}",
                       f"{float(reference['min_risk_pick_loses']):.4f}"]]) + "\n")

    def ranked(key: str, reverse: bool, count: int = 10) -> str:
        best = sorted(configs, key=lambda r: value(r, key), reverse=reverse)[:count]
        return table(["config"] + [label for _, label, _ in METRICS],
                     [[r["config"]] + [fmt.format(value(r, k)) for k, _, fmt in METRICS] for r in best])

    out.append("## Top 10 by Brier score (lower is better)\n")
    out.append(ranked("brier", False) + "\n")
    out.append("## Top 10 by truth coverage\n")
    out.append(ranked("truth_coverage", True) + "\n")

    out.append("## All configurations\n")
    out.append(table(["config"] + [label for _, label, _ in METRICS],
                     [[r["config"]] + [fmt.format(value(r, k)) for k, _, fmt in METRICS] for r in configs]) + "\n")

    timing_path = folder / "timing_summary.csv"
    if timing_path.exists():
        timing = load(timing_path)
        out.append("## Timing run (single worker)\n")
        out.append(table(["config", "Median s/move", "p95 s/move", "Max s/move", "Truth coverage"],
                         [[r["config"], f"{float(r['median_move_s']):.3f}", f"{float(r['p95_move_s']):.3f}",
                           f"{float(r['max_move_s']):.2f}", f"{float(r['truth_coverage']):.3f}"]
                          for r in timing]) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
