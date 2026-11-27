"""Per-move particle time and set health from a particle agent's decision records.

``python -m harness.particle_timing DIR [DIR ...] --agent-prefix particle_ev300``
reads every replay JSON under each DIR (from ``harness.cli --save-replays``)
and prints one Markdown row per DIR. Time per move is the particle updates
since the previous decision plus the decision itself (scoring every legal
move), as recorded by the agent; it is only meaningful for single-worker runs.
Needs no reconstruction, unlike ``harness.particle_metrics``.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(replay_dir: Path, prefix: str) -> dict:
    times, distinct, ess, modes = [], [], [], Counter()
    games = depletions = 0
    for path in sorted(replay_dir.rglob("*.json")):
        replay = json.loads(path.read_text())
        for color in ("white", "black"):
            if not replay[color].startswith(prefix):
                continue
            games += 1
            last = None
            for index, frame in enumerate(replay["frames"][1:]):
                decision = frame["decision"]
                if (index % 2 == 0) != (color == "white") or not decision:
                    continue
                times.append(decision["particle_update_seconds"] + decision["decision_seconds"])
                modes[decision["particle_mode"]] += 1
                if decision["particles"]:
                    distinct.append(decision["particles"]["distinct"])
                    ess.append(decision["particles"]["ess"])
                    last = decision["particles"]
            depletions += last["depletions"] if last else 0
    ordered = sorted(times)
    return {
        "dir": str(replay_dir), "games": games, "moves": len(times),
        "median_s": statistics.median(times) if times else 0.0,
        "p95_s": ordered[int(0.95 * (len(ordered) - 1))] if ordered else 0.0,
        "p99_s": ordered[int(0.99 * (len(ordered) - 1))] if ordered else 0.0,
        "max_s": max(times, default=0.0),
        "over_1_5s": sum(t > 1.5 for t in times),
        "median_distinct": statistics.median(distinct) if distinct else 0,
        "median_ess": statistics.median(ess) if ess else 0.0,
        "depletions_per_game": depletions / max(games, 1),
        "modes": dict(modes),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dirs", nargs="+", type=Path)
    parser.add_argument("--agent-prefix", default="particle_")
    parser.add_argument("--json", type=Path, default=None, help="also write all rows to this file")
    args = parser.parse_args(argv)
    rows = [summarize(d, args.agent_prefix) for d in args.dirs]
    print("| Run | Games | Moves | Median s | p95 s | p99 s | Max s | Moves > 1.5 s | Median distinct | "
          "Median ESS | Depletions/game | Modes |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {Path(r['dir']).name} | {r['games']} | {r['moves']} | {r['median_s']:.3f} | {r['p95_s']:.3f} | "
              f"{r['p99_s']:.3f} | {r['max_s']:.3f} | {r['over_1_5s']} | {r['median_distinct']} | "
              f"{r['median_ess']:.1f} | {r['depletions_per_game']:.2f} | {r['modes']} |")
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
