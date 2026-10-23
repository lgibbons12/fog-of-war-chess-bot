"""``python -m harness.cli A B --pairs 200 --seed 0 [1 2 ...] [--workers N] [--save-replays DIR]``.

With several seeds, prints one score line per seed and then the pooled report.
Replays go to DIR/seed<S>/ and summaries to one JSONL per seed.
"""
from __future__ import annotations

import argparse
import os
import time

from bot.agents import REGISTRY
from harness.match import run_match_pairs, write_jsonl
from harness.stats import a_moves, reason_histogram, score_with_ci, wdl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_a", choices=sorted(REGISTRY))
    parser.add_argument("agent_b", choices=sorted(REGISTRY))
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--seed", type=int, nargs="+", default=[0])
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--max-plies", type=int, default=1000)
    parser.add_argument("--save-replays", metavar="DIR", default=None)
    parser.add_argument("--summary", metavar="DIR", default="replays",
                        help="directory for <A>_vs_<B>_seed<S>.jsonl summaries")
    args = parser.parse_args(argv)

    summaries, wall = [], 0.0
    print(f"{args.agent_a} vs {args.agent_b}: {args.pairs} pairs per seed, seeds {args.seed}")
    for seed in args.seed:
        replay_dir = os.path.join(args.save_replays, f"seed{seed}") if args.save_replays else None
        started = time.perf_counter()
        batch = run_match_pairs(args.agent_a, args.agent_b, args.pairs, seed,
                                args.workers, args.max_plies, replay_dir)
        wall += time.perf_counter() - started
        write_jsonl(batch, os.path.join(args.summary, f"{args.agent_a}_vs_{args.agent_b}_seed{seed}.jsonl"))
        score, low, high, n = score_with_ci(batch)
        print(f"  seed {seed}: {score:.3f}  [{low:.3f}, {high:.3f}]  W/D/L {'/'.join(map(str, wdl(batch)))}")
        summaries += batch

    wins, draws, losses = wdl(summaries)
    score, low, high, n = score_with_ci(summaries)
    label = "Pooled" if len(args.seed) > 1 else "Score"
    print(f"W/D/L (A): {wins}/{draws}/{losses}  ({n} games)")
    print(f"{label} (A): {score:.3f}  95% CI [{low:.3f}, {high:.3f}]")
    for color in ("white", "black"):
        c_score, c_low, c_high, c_n = score_with_ci([s for s in summaries if s.a_color == color])
        print(f"  A as {color}: {c_score:.3f}  [{c_low:.3f}, {c_high:.3f}]  n={c_n}")
    print("Reasons:")
    for reason, count in reason_histogram(summaries).most_common():
        print(f"  {count:5d}  {reason}")
    moves = sum(a_moves(s) for s in summaries)
    total = sum(s.a_think_total for s in summaries)
    peak = max((s.a_think_max for s in summaries), default=0.0)
    print(f"Mean plies: {sum(s.plies for s in summaries) / max(len(summaries), 1):.1f}")
    print(f"Think (A): mean {1000 * total / max(moves, 1):.3f} ms/move, max {1000 * peak:.3f} ms")
    print(f"Throughput: {len(summaries) / wall:.2f} games/s ({wall:.1f} s, {args.workers} workers)")


if __name__ == "__main__":
    main()
