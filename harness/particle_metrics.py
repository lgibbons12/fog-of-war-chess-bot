"""Step 3 metrics for a particle agent, from saved replays plus the true board.

The agent is deterministic, so its internal state can be rebuilt after the
game: ``replay_agent`` re-creates it with the game's seed, feeds it the same
observations and clocks, and checks it plays the recorded moves. That lets
us compare its particles with the true board, which only the harness sees.

``python -m harness.particle_metrics DIR --agent NAME --out OUTDIR`` reads
replays saved by ``harness.cli --save-replays DIR`` (layout
``DIR/seed<S>/pair<P>_a<color>.json``, with NAME as agent A) and writes
``particle_metrics.json`` and ``particle_metrics.md``:

- **calibration**: the chosen move's ``p_loss`` (from the decision record)
  bucketed against whether that move really left our king capturable, by
  particle mode;
- **truth coverage**: fraction of observations whose true board is among the
  particles, and its mean normalized weight, by ply bucket;
- **per-square log loss** on '?' squares of the particle marginals against the
  truth, by ply bucket, next to a "uniform over support" baseline from the
  possibility tracker (each hypothesis spread uniformly over its support and
  types; occupancy capped at 1 - EPS);
- **set health**: distinct particles, ESS, depletions and recoveries per game;
- **time**: per move, particle updates since the previous decision plus the
  decision itself (single-process timings are only meaningful with 1 worker).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import multiprocessing
from pathlib import Path
import re
import statistics
from typing import Callable

import chess

from bot.agents import REGISTRY
from bot.particles import NO_REPETITIONS, particle_key
from harness.game import BASE_SECONDS, INCREMENT_SECONDS
from harness.match import pair_seeds
from referee import FowBoard, observation, outcome

PLY_BUCKET = 20
EPS = 1e-4
BUCKETS = ((0.0, 0.0), (0.0, 0.01), (0.01, 0.05), (0.05, 0.2), (0.2, 1.0))
BUCKET_NAMES = ("0", "(0,.01]", "(.01,.05]", "(.05,.2]", ">.2")
CLASSES = (None, "P", "N", "B", "R", "Q", "K")  # enemy piece on a '?' square, or empty
REPLAY_NAME = re.compile(r"pair(\d+)_a(white|black)\.json$")


class ReplayMismatch(Exception):
    """The rebuilt agent chose a different move than the recorded game."""


def replay_agent(replay: dict, side: chess.Color, factory: Callable, seed: int,
                 on_observation: Callable | None = None, on_decision: Callable | None = None):
    """Rebuild ``factory``'s agent for ``side`` through ``replay``; return it.

    Calls ``on_observation(ply, obs, agent, board)`` after every ``observe``
    and ``on_decision(ply, obs, agent, board)`` after every ``choose_move``
    (``board`` is the true board before the move; callbacks must not mutate
    it). Clocks are rebuilt from the replay's think times exactly as the
    harness computed them. Raises ``ReplayMismatch`` if a move differs.
    """
    agent = factory(side, BASE_SECONDS, INCREMENT_SECONDS, seed, strict=True)
    board = FowBoard()
    clock = BASE_SECONDS
    for ply in range(replay["plies"]):
        obs = observation(board, side)
        agent.observe(obs)
        if on_observation is not None:
            on_observation(ply, obs, agent, board)
        frame = replay["frames"][ply + 1]
        if board.turn == side:
            move = agent.choose_move(clock)
            if move.uci() != frame["move"]:
                raise ReplayMismatch(f"ply {ply}: rebuilt {move.uci()}, recorded {frame['move']}")
            clock += INCREMENT_SECONDS - frame["thinkSeconds"]
            if on_decision is not None:
                on_decision(ply, obs, agent, board)
        board.push_uci(frame["move"])
    return agent


def bucket_of(p: float) -> int:
    if p <= 0.0:
        return 0
    for index, (low, high) in enumerate(BUCKETS[1:], start=1):
        if low < p <= high:
            return index
    return len(BUCKETS) - 1


def possibility_marginal(hyps, square: int) -> list[float]:
    """Uniform-over-support distribution over ``CLASSES`` for one '?' square."""
    mass = [0.0] * len(CLASSES)
    for h in hyps:
        if h.squares & chess.BB_SQUARES[square]:
            share = 1.0 / (chess.popcount(h.squares) * len(h.types))
            for kind in h.types:
                mass[CLASSES.index(kind)] += share
    occupied = sum(mass)
    if occupied > 1 - EPS:
        mass = [m * (1 - EPS) / occupied for m in mass]
        occupied = 1 - EPS
    mass[0] = 1.0 - occupied
    return mass


def particle_marginal(particles, square: int, enemy: chess.Color) -> list[float]:
    """Weighted distribution over ``CLASSES`` for one square across particles."""
    mass = [0.0] * len(CLASSES)
    for particle in particles:
        piece = particle.board.piece_at(square)
        kind = piece.symbol().upper() if piece is not None and piece.color == enemy else None
        mass[CLASSES.index(kind)] += particle.weight
    return mass


def true_class(board: chess.Board, square: int, enemy: chess.Color) -> int:
    piece = board.piece_at(square)
    return CLASSES.index(piece.symbol().upper() if piece is not None and piece.color == enemy else None)


def game_metrics(task: tuple[str, str, int, str]) -> dict:
    """All per-game counters for one saved replay (pool worker)."""
    path, agent_name, seed, color = task
    replay = json.loads(Path(path).read_text())
    side = color == "white"
    enemy = not side
    row = {"path": path, "plies": replay["plies"], "result": replay["result"], "reason": replay["reason"],
           "buckets": {}, "calibration": {}, "times": [], "distinct": [], "ess": []}

    def bucket(ply: int) -> dict:
        key = str(ply // PLY_BUCKET * PLY_BUCKET)
        return row["buckets"].setdefault(key, {"observations": 0, "truth_present": 0, "truth_weight": 0.0,
                                               "squares": 0, "particle_logloss": 0.0,
                                               "possibility_logloss": 0.0, "unavailable": 0})

    def on_observation(ply, obs, agent, board):
        b = bucket(ply)
        b["observations"] += 1
        tracker = agent.particles
        particles = tracker.particles() if tracker is not None and tracker.available else []
        if not particles:
            b["unavailable"] += 1
            return
        truth = particle_key(board)
        for particle in particles:
            if particle_key(particle.board) == truth:
                b["truth_present"] += 1
                b["truth_weight"] += particle.weight
                break
        hyps = agent.possibility.hyps
        for square, char in enumerate(obs):
            if char != "?":
                continue
            actual = true_class(board, square, enemy)
            p = particle_marginal(particles, square, enemy)[actual]
            q = possibility_marginal(hyps, square)[actual]
            b["squares"] += 1
            b["particle_logloss"] -= math.log(min(max(p, EPS), 1.0))
            b["possibility_logloss"] -= math.log(min(max(q, EPS), 1.0))

    def on_decision(ply, obs, agent, board):
        decision = agent.last_decision
        after = board.copy(stack=False)
        after.push(decision["move"])
        result = outcome(after, NO_REPETITIONS)
        lost = result is not None and result[1] == "King capturable"
        cell = row["calibration"].setdefault(decision["particle_mode"], [[0, 0, 0.0] for _ in BUCKETS])
        entry = cell[bucket_of(decision["p_loss"])]
        entry[0] += 1
        entry[1] += lost
        entry[2] += decision["p_loss"]
        row["times"].append(decision["particle_update_seconds"] + decision["decision_seconds"])
        if decision["particles"] is not None:
            row["distinct"].append(decision["particles"]["distinct"])
            row["ess"].append(decision["particles"]["ess"])

    agent = replay_agent(replay, side, REGISTRY[agent_name], seed, on_observation, on_decision)
    stats = agent.particles.stats() if agent.particles is not None else {}
    for key in ("depletions", "regenerations", "regeneration_failures", "reexpansions",
                "reexpansion_failures", "resamples", "unavailable_observations"):
        row[key] = stats.get(key, 0)
    row["off_reason"] = agent.off_reason
    return row


def tasks_for(replay_dir: Path, agent: str) -> list[tuple[str, str, int, str]]:
    """(path, agent, agent seed, agent color) for every replay where ``agent`` is A."""
    tasks = []
    for seed_dir in sorted(replay_dir.glob("seed*")):
        base_seed = int(seed_dir.name.removeprefix("seed"))
        for path in sorted(seed_dir.glob("pair*_a*.json")):
            match = REPLAY_NAME.search(path.name)
            pair, color = int(match.group(1)), match.group(2)
            tasks.append((str(path), agent, pair_seeds(base_seed, pair)[0], color))
    return tasks


def aggregate(rows: list[dict]) -> dict:
    buckets: dict[str, Counter] = {}
    for row in rows:
        for key, values in row["buckets"].items():
            buckets.setdefault(key, Counter()).update(values)
    calibration: dict[str, list[list[float]]] = {}
    for row in rows:
        for mode, cells in row["calibration"].items():
            total = calibration.setdefault(mode, [[0, 0, 0.0] for _ in BUCKETS])
            for t, c in zip(total, cells):
                for i in range(3):
                    t[i] += c[i]
    times = [t for row in rows for t in row["times"]]
    distinct = [d for row in rows for d in row["distinct"]]
    ess = [e for row in rows for e in row["ess"]]
    games = len(rows)
    counts = {key: sum(row[key] for row in rows) for key in
              ("depletions", "regenerations", "regeneration_failures", "reexpansions", "reexpansion_failures",
               "resamples", "unavailable_observations")}
    totals = sum(buckets.values(), Counter())
    return {
        "games": games,
        "off_reasons": dict(Counter(row["off_reason"] for row in rows if row["off_reason"])),
        "calibration": calibration,
        "buckets": {key: dict(buckets[key]) for key in sorted(buckets, key=int)},
        "overall": {
            "observations": totals["observations"],
            "truth_coverage": totals["truth_present"] / max(totals["observations"], 1),
            "truth_weight": totals["truth_weight"] / max(totals["observations"], 1),
            "squares": totals["squares"],
            "particle_logloss": totals["particle_logloss"] / max(totals["squares"], 1),
            "possibility_logloss": totals["possibility_logloss"] / max(totals["squares"], 1),
        },
        "health": {**counts, "depletions_per_game": counts["depletions"] / max(games, 1),
                   "recovery_success": (counts["regenerations"] + counts["reexpansions"])
                   / max(counts["depletions"], 1),
                   "median_distinct": statistics.median(distinct) if distinct else 0,
                   "median_ess": statistics.median(ess) if ess else 0.0},
        "time": {"moves": len(times), "median_s": statistics.median(times) if times else 0.0,
                 "p95_s": sorted(times)[int(0.95 * (len(times) - 1))] if times else 0.0,
                 "max_s": max(times, default=0.0)},
    }


def markdown(summary: dict, agent: str) -> str:
    lines = [f"# Particle metrics: `{agent}` ({summary['games']} games)", ""]
    lines += ["## Calibration (chosen move's p_loss vs immediate king-capture loss)", "",
              "| Mode | Bucket | Moves | Mean p_loss | Lost | Loss rate |", "|---|---|---|---|---|---|"]
    for mode, cells in sorted(summary["calibration"].items()):
        for name, (moves, lost, p_sum) in zip(BUCKET_NAMES, cells):
            if moves:
                lines.append(f"| {mode} | {name} | {moves} | {p_sum / moves:.4f} | {lost} | {lost / moves:.4f} |")
    o = summary["overall"]
    lines += ["", "## Truth coverage and per-square log loss on '?' squares", "",
              f"Overall: coverage {o['truth_coverage']:.3f}, truth weight {o['truth_weight']:.3f} over "
              f"{o['observations']} observations; log loss particles {o['particle_logloss']:.4f} vs "
              f"possibility {o['possibility_logloss']:.4f} nats over {o['squares']} squares.", "",
              "| Plies | Observations | Coverage | Truth weight | Unavailable | Log loss (particles) | "
              "Log loss (possibility) |", "|---|---|---|---|---|---|---|"]
    for key, b in summary["buckets"].items():
        start = int(key)
        n = max(b.get("observations", 0), 1)
        squares = max(b.get("squares", 0), 1)
        lines.append(f"| {start}-{start + PLY_BUCKET - 1} | {b.get('observations', 0)} | "
                     f"{b.get('truth_present', 0) / n:.3f} | {b.get('truth_weight', 0) / n:.3f} | "
                     f"{b.get('unavailable', 0)} | {b.get('particle_logloss', 0) / squares:.4f} | "
                     f"{b.get('possibility_logloss', 0) / squares:.4f} |")
    h, t = summary["health"], summary["time"]
    lines += ["", "## Set health", ""] + [f"- {key}: {value:.3f}" if isinstance(value, float) else
                                          f"- {key}: {value}" for key, value in h.items()]
    lines += [f"- particles switched off: {summary['off_reasons'] or 'never'}", "", "## Time per move", "",
              f"{t['moves']} moves: median {t['median_s']:.3f} s, p95 {t['p95_s']:.3f} s, max {t['max_s']:.3f} s "
              "(updates since the previous decision plus the decision)."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("replay_dir", type=Path)
    parser.add_argument("--agent", required=True, choices=sorted(REGISTRY))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=max(1, multiprocessing.cpu_count() - 2))
    args = parser.parse_args(argv)
    tasks = tasks_for(args.replay_dir, args.agent)
    if args.workers <= 1:
        rows = [game_metrics(task) for task in tasks]
    else:
        with multiprocessing.Pool(args.workers) as pool:
            rows = list(pool.imap(game_metrics, tasks, chunksize=1))
    summary = aggregate(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "particle_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out / "particle_metrics.md").write_text(markdown(summary, args.agent))
    print(markdown(summary, args.agent))


if __name__ == "__main__":
    main()
