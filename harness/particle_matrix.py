"""Step 3 particle-tracker decision matrix: every tracker configuration on the same replayed games.

The tracker is passive (it doesn't choose moves), so each configuration is
scored by replaying a fixed set of harness games (``tracked_v2`` against
random, baseline and safety_v2, both colors) and comparing against the true
board, which only the harness sees.

Factors: particle count ``n``, opponent model, resampling trigger, depletion
recovery, and diversity resampling (see ``bot.particles.ParticleTracker``).

Per configuration it measures:
- truth coverage: is the true board among the particles, and its weight;
- set health: depletions, recoveries, observations without particles;
- ``p_loss`` quality on every legal move at every decision of ours, against
  whether the move really leaves our king capturable: Brier score, log loss,
  calibration buckets, "missed" losses (p = 0 but the move loses), and how
  often the lowest-risk move actually loses;
- time per move (both tracker updates since our last decision plus scoring
  every legal move), which is contended when run with many workers.

A ``possibility`` reference row scores the Step 2 tracker as a predictor:
p = 1 for known losses, the pooled loss rate of exposed moves for exposed
ones, 0 otherwise (calibrated in-sample, so it is a generous baseline).

Usage:
    python -m harness.particle_matrix --out docs/results/<dir> [--seeds 7] [--workers 20]
    python -m harness.particle_matrix --out docs/results/<dir> --timing   # single worker, n grid
"""
from __future__ import annotations

import argparse
import gzip
from functools import lru_cache
import itertools
import json
import math
import multiprocessing
from pathlib import Path
import random
import statistics
import time

import chess

from bot.particles import MODELS, NO_REPETITIONS, ParticleTracker, particle_key
from bot.possibility import PossibilityTracker
from bot.safety import apply_move, king_safety
from bot.tracker import ObservationTracker
from harness.game import play_game
from referee import FowBoard, observation, outcome

OPPONENTS = ("random", "baseline", "safety_v2")
OURS = "tracked_v2"
SEED_OFFSET = 5000
N_GRID = (32, 64, 128, 256, 512)
BUCKETS = ((0.0, 0.0), (0.0, 0.01), (0.01, 0.05), (0.05, 0.2), (0.2, 0.5), (0.5, 0.999999), (1.0, 1.0))
BUCKET_NAMES = ("0", "(0,.01]", "(.01,.05]", "(.05,.2]", "(.2,.5]", "(.5,1)", "1")
EPS = 1e-4


def games(seeds: int) -> list[tuple[str, str, int, bool]]:
    """(white, black, seed, our side is White) for every replayed game, in a fixed order."""
    result = []
    for opponent in OPPONENTS:
        for seed in range(seeds):
            result.append((OURS, opponent, seed, True))
            result.append((opponent, OURS, seed, False))
    return result


@lru_cache(maxsize=None)
def replay_for(white: str, black: str, seed: int) -> dict:
    return play_game(white, black, seed, seed + SEED_OFFSET)


def configs(full: bool) -> list[dict]:
    if not full:
        return [{"n": n, "model": "uniform", "trigger": "above_n", "recovery": recovery, "diversity": False}
                for n in N_GRID for recovery in ("supports", "reexpand")]
    return [{"n": n, "model": model, "trigger": trigger, "recovery": recovery, "diversity": diversity}
            for n, model, trigger, recovery, diversity in itertools.product(
                N_GRID, ("uniform", "capture"), ("above_n", "ess"), ("supports", "reexpand"), (False, True))]


def config_name(config: dict) -> str:
    if config.get("reference"):
        return "possibility"
    return (f"n{config['n']}-{config['model']}-{config['trigger']}-{config['recovery']}-"
            f"{'div' if config['diversity'] else 'sys'}")


def bucket_of(p: float) -> int:
    if p <= 0.0:
        return 0
    if p >= 1.0:
        return 6
    for index, (low, high) in enumerate(BUCKETS[1:-1], start=1):
        if low < p <= high:
            return index
    return 5


def evaluate(task: tuple[dict, tuple]) -> dict:
    """Score one configuration on one replayed game. Deterministic except for timings."""
    config, (white, black, seed, ours_white) = task
    side = chess.WHITE if ours_white else chess.BLACK
    replay = replay_for(white, black, seed)
    board = FowBoard()
    possibility = PossibilityTracker(side, strict=True)
    legal = ObservationTracker(side)
    reference = config.get("reference", False)
    tracker = None
    if not reference:
        tracker = ParticleTracker(side, config["n"], MODELS[config["model"]](),
                                  random.Random(f"matrix:{white}:{black}:{seed}"), strict=True,
                                  trigger=config["trigger"], recovery=config["recovery"],
                                  diversity=config["diversity"])
    row = {"config": config_name(config), **{k: v for k, v in config.items() if k != "reference"},
           "white": white, "black": black, "seed": seed, "side": "white" if ours_white else "black",
           "plies": replay["plies"], "observations": 0, "truth_present": 0, "truth_weight": 0.0,
           "distinct_sum": 0, "unavailable_observations": 0, "moves": 0, "moves_unscored": 0,
           "brier": 0.0, "logloss": 0.0, "losing_moves": 0, "missed_losses": 0, "false_certain": 0,
           "decisions": 0, "decisions_with_safe_move": 0, "min_risk_pick_loses": 0,
           "bucket_n": [0] * len(BUCKETS), "bucket_pos": [0] * len(BUCKETS),
           "ref": {"known": [0, 0], "exposed": [0, 0], "safe": [0, 0]},
           "move_seconds": []}
    last = prev = None
    pending = 0.0
    for ply in range(replay["plies"]):
        obs = observation(board, side)
        possibility.on_observation(obs, ply, last, prev)
        legal.observe(obs)
        if tracker is not None:
            tracker.on_observation(obs, ply, last, possibility, legal.rights)
            pending += tracker.last_update_seconds
            particles = tracker.particles()
            row["observations"] += 1
            row["distinct_sum"] += len(particles)
            if not particles:
                row["unavailable_observations"] += 1
            truth = particle_key(board)
            for particle in particles:
                if particle_key(particle.board) == truth:
                    row["truth_present"] += 1
                    row["truth_weight"] += particle.weight
                    break
        move_uci = replay["frames"][ply + 1]["move"]
        if board.turn == side:
            moves = legal.legal_moves()
            actual = []
            for move in moves:
                board.push(move)
                result = outcome(board, NO_REPETITIONS)
                board.pop()
                actual.append(result is not None and result[1] == "King capturable")
            row["decisions"] += 1
            row["decisions_with_safe_move"] += not all(actual)
            if reference:
                exposure = []
                for move, loses in zip(moves, actual):
                    report = king_safety(apply_move(obs, move, side), side, possibility)
                    kind = "known" if report.known_loss else ("exposed" if report.exposed else "safe")
                    row["ref"][kind][0] += 1
                    row["ref"][kind][1] += loses
                    exposure.append((report.known_loss, len(report.exposed)))
                pick = min(range(len(moves)), key=lambda i: exposure[i])
                row["min_risk_pick_loses"] += actual[pick] and not all(actual)
            else:
                started = time.perf_counter()
                risks = [tracker.loss_probability(move) for move in moves]
                pending += time.perf_counter() - started
                row["move_seconds"].append(pending)
                pending = 0.0
                if risks and risks[0] is None:
                    row["moves_unscored"] += len(moves)
                else:
                    for p, loses in zip(risks, actual):
                        row["moves"] += 1
                        row["brier"] += (p - loses) ** 2
                        clipped = min(max(p, EPS), 1 - EPS)
                        row["logloss"] -= math.log(clipped if loses else 1 - clipped)
                        row["losing_moves"] += loses
                        row["missed_losses"] += loses and p == 0.0
                        row["false_certain"] += (not loses) and p >= 1.0
                        index = bucket_of(p)
                        row["bucket_n"][index] += 1
                        row["bucket_pos"][index] += loses
                    pick = min(range(len(moves)), key=lambda i: risks[i])
                    row["min_risk_pick_loses"] += actual[pick] and not all(actual)
            last = chess.Move.from_uci(move_uci)
            legal.record_move(last)
        board.push_uci(move_uci)
        prev = obs
    if tracker is not None:
        stats = tracker.stats()
        for key in ("depletions", "regenerations", "regeneration_failures", "reexpansions",
                    "reexpansion_failures", "resamples"):
            row[key] = stats[key]
    return row


def aggregate(rows: list[dict]) -> list[dict]:
    """One summary per configuration, in first-seen order."""
    by_config: dict[str, list[dict]] = {}
    for row in rows:
        by_config.setdefault(row["config"], []).append(row)
    summaries = []
    for name, group in by_config.items():
        first = group[0]
        summary = {"config": name}
        for key in ("n", "model", "trigger", "recovery", "diversity"):
            summary[key] = first.get(key, "")
        summary["games"] = len(group)
        decisions = sum(r["decisions"] for r in group)
        with_safe = sum(r["decisions_with_safe_move"] for r in group)
        summary["decisions"] = decisions
        summary["min_risk_pick_loses"] = sum(r["min_risk_pick_loses"] for r in group) / max(with_safe, 1)
        if name == "possibility":
            ref = {kind: [sum(r["ref"][kind][i] for r in group) for i in (0, 1)]
                   for kind in ("known", "exposed", "safe")}
            rate = ref["exposed"][1] / max(ref["exposed"][0], 1)
            moves = sum(ref[k][0] for k in ref)
            brier = (ref["known"][0] - ref["known"][1]) + ref["safe"][1] \
                + ref["exposed"][1] * (1 - rate) ** 2 + (ref["exposed"][0] - ref["exposed"][1]) * rate ** 2
            clipped = min(max(rate, EPS), 1 - EPS)
            logloss = -((ref["known"][0] - ref["known"][1]) * math.log(EPS) + ref["safe"][1] * math.log(EPS)
                        + ref["exposed"][1] * math.log(clipped)
                        + (ref["exposed"][0] - ref["exposed"][1]) * math.log(1 - clipped))
            summary.update({"moves": moves, "brier": brier / moves, "logloss": logloss / moves,
                            "exposed_loss_rate": rate, "ref_counts": ref})
            summaries.append(summary)
            continue
        observations = sum(r["observations"] for r in group)
        moves = sum(r["moves"] for r in group)
        seconds = [s for r in group for s in r["move_seconds"]]
        losing = sum(r["losing_moves"] for r in group)
        summary.update({
            "observations": observations,
            "truth_coverage": sum(r["truth_present"] for r in group) / observations,
            "truth_weight": sum(r["truth_weight"] for r in group) / observations,
            "mean_distinct": sum(r["distinct_sum"] for r in group) / observations,
            "unavailable_frac": sum(r["unavailable_observations"] for r in group) / observations,
            "depletions_per_game": sum(r["depletions"] for r in group) / len(group),
            "regeneration_failures": sum(r["regeneration_failures"] for r in group),
            "reexpansions": sum(r["reexpansions"] for r in group),
            "reexpansion_failures": sum(r["reexpansion_failures"] for r in group),
            "moves": moves,
            "moves_unscored": sum(r["moves_unscored"] for r in group),
            "brier": sum(r["brier"] for r in group) / max(moves, 1),
            "logloss": sum(r["logloss"] for r in group) / max(moves, 1),
            "losing_moves": losing,
            "missed_loss_frac": sum(r["missed_losses"] for r in group) / max(losing, 1),
            "false_certain": sum(r["false_certain"] for r in group),
            "median_move_s": statistics.median(seconds) if seconds else 0.0,
            "p95_move_s": sorted(seconds)[int(0.95 * (len(seconds) - 1))] if seconds else 0.0,
            "max_move_s": max(seconds) if seconds else 0.0,
            "bucket_n": [sum(r["bucket_n"][i] for r in group) for i in range(len(BUCKETS))],
            "bucket_pos": [sum(r["bucket_pos"][i] for r in group) for i in range(len(BUCKETS))],
        })
        summaries.append(summary)
    return summaries


SUMMARY_COLUMNS = ("config", "n", "model", "trigger", "recovery", "diversity", "games", "observations",
                   "truth_coverage", "truth_weight", "mean_distinct", "unavailable_frac", "depletions_per_game",
                   "regeneration_failures", "reexpansions", "reexpansion_failures", "moves", "moves_unscored",
                   "brier", "logloss", "losing_moves", "missed_loss_frac", "false_certain",
                   "min_risk_pick_loses", "median_move_s", "p95_move_s", "max_move_s")


def write_outputs(out: Path, stem: str, rows: list[dict], summaries: list[dict], meta: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / f"{stem}_raw.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    with open(out / f"{stem}_summary.csv", "w", encoding="utf-8") as handle:
        handle.write(",".join(SUMMARY_COLUMNS) + "\n")
        for summary in summaries:
            values = []
            for column in SUMMARY_COLUMNS:
                value = summary.get(column, "")
                values.append(f"{value:.6g}" if isinstance(value, float) else str(value))
            handle.write(",".join(values) + "\n")
    with open(out / f"{stem}_calibration.csv", "w", encoding="utf-8") as handle:
        handle.write("config,bucket,moves,losing,loss_rate\n")
        for summary in summaries:
            for name, count, positive in zip(BUCKET_NAMES, summary.get("bucket_n", []), summary.get("bucket_pos", [])):
                rate = f"{positive / count:.6g}" if count else ""
                handle.write(f"{summary['config']},{name},{count},{positive},{rate}\n")
    with open(out / f"{stem}_meta.json", "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seeds", type=int, default=7, help="seeds per (opponent, color); games = 6 x seeds")
    parser.add_argument("--workers", type=int, default=max(1, multiprocessing.cpu_count() - 2))
    parser.add_argument("--timing", action="store_true",
                        help="single worker; only n grid x recovery, uniform model, default trigger")
    args = parser.parse_args()
    game_list = games(args.seeds)
    workers = 1 if args.timing else args.workers
    config_list = configs(full=not args.timing)
    if not args.timing:
        config_list = [{"reference": True}] + config_list
    tasks = [(config, game) for config in config_list for game in game_list]
    stem = "timing" if args.timing else "matrix"
    started = time.time()
    print(f"{len(config_list)} configs x {len(game_list)} games = {len(tasks)} tasks on {workers} workers",
          flush=True)
    rows = []
    if workers == 1:
        for index, task in enumerate(tasks):
            rows.append(evaluate(task))
            if (index + 1) % 20 == 0:
                print(f"  {index + 1}/{len(tasks)} ({time.time() - started:.0f}s)", flush=True)
    else:
        with multiprocessing.Pool(workers) as pool:
            for index, row in enumerate(pool.imap(evaluate, tasks, chunksize=1)):
                rows.append(row)
                if (index + 1) % 100 == 0:
                    print(f"  {index + 1}/{len(tasks)} ({time.time() - started:.0f}s)", flush=True)
    summaries = aggregate(rows)
    meta = {"command": "python -m harness.particle_matrix " + " ".join(
                f"--{k} {v}" for k, v in (("out", args.out), ("seeds", args.seeds), ("workers", workers))
            ) + (" --timing" if args.timing else ""),
            "games": [list(g) for g in game_list], "ours": OURS, "opponents": OPPONENTS,
            "seed_offset": SEED_OFFSET, "workers": workers, "elapsed_seconds": time.time() - started,
            "configs": len(config_list)}
    write_outputs(args.out, stem, rows, summaries, meta)
    print(f"wrote {args.out} in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
