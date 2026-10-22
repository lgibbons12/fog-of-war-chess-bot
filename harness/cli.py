"""``python -m harness.cli A B --pairs 200 --seed 0 [--workers N] [--save-replays DIR]``."""
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
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--max-plies", type=int, default=1000)
    parser.add_argument("--save-replays", metavar="DIR", default=None)
    parser.add_argument("--summary", metavar="PATH", default=None,
                        help="JSONL output (default replays/<A>_vs_<B>_seed<S>.jsonl)")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    summaries = run_match_pairs(args.agent_a, args.agent_b, args.pairs, args.seed,
                                args.workers, args.max_plies, args.save_replays)
    wall = time.perf_counter() - started
    summary_path = args.summary or f"replays/{args.agent_a}_vs_{args.agent_b}_seed{args.seed}.jsonl"
    write_jsonl(summaries, summary_path)

    wins, draws, losses = wdl(summaries)
    score, low, high, n = score_with_ci(summaries)
    print(f"{args.agent_a} vs {args.agent_b}: {n} games, {args.pairs} pairs, seed {args.seed}")
    print(f"W/D/L (A): {wins}/{draws}/{losses}")
    print(f"Score (A): {score:.3f}  95% CI [{low:.3f}, {high:.3f}]")
    for color in ("white", "black"):
        c_score, c_low, c_high, c_n = score_with_ci([s for s in summaries if s.a_color == color])
        print(f"  A as {color}: {c_score:.3f}  [{c_low:.3f}, {c_high:.3f}]  n={c_n}")
    print("Reasons:")
    for reason, count in reason_histogram(summaries).most_common():
        print(f"  {count:5d}  {reason}")
    moves = sum(a_moves(s) for s in summaries)
    total = sum(s.a_think_total for s in summaries)
    peak = max((s.a_think_max for s in summaries), default=0.0)
    print(f"Think (A): mean {1000 * total / max(moves, 1):.3f} ms/move, max {1000 * peak:.3f} ms")
    print(f"Throughput: {len(summaries) / wall:.2f} games/s ({wall:.1f} s, {args.workers} workers)")
    print(f"Summaries: {summary_path}")


if __name__ == "__main__":
    main()
