"""Color-balanced batches of in-process games, optionally in parallel."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import multiprocessing
import os
from pathlib import Path
import random

from harness.game import play_game


@dataclass(frozen=True)
class GameSummary:
    """One game from agent A's point of view. ``result`` is the raw PGN result."""
    pair: int
    a_color: str
    result: str
    reason: str
    plies: int
    a_think_total: float
    a_think_max: float


def pair_seeds(base_seed: int, pair: int) -> tuple[int, int]:
    """Seeds (for A, for B) of pair ``pair``; both games of a pair reuse them."""
    rng = random.Random(base_seed + pair)
    return rng.getrandbits(32), rng.getrandbits(32)


def _play_task(task: tuple) -> GameSummary:
    """Pool worker: play one game named by strings, optionally save its replay."""
    agent_a, agent_b, pair, a_color, seed_a, seed_b, max_plies, replay_dir = task
    if a_color == "white":
        replay = play_game(agent_a, agent_b, seed_a, seed_b, max_plies, replay_dir is not None)
    else:
        replay = play_game(agent_b, agent_a, seed_b, seed_a, max_plies, replay_dir is not None)
    if replay_dir is not None:
        path = Path(replay_dir) / f"pair{pair:05d}_a{a_color}.json"
        path.write_text(json.dumps(replay) + "\n")
    times = replay["thinkSeconds"][a_color]
    return GameSummary(pair, a_color, replay["result"], replay["reason"], replay["plies"],
                       sum(times), max(times, default=0.0))


def run_match_pairs(agent_a: str, agent_b: str, n_pairs: int, base_seed: int,
                    workers: int = os.cpu_count(), max_plies: int = 1000,
                    replay_dir: str | None = None) -> list[GameSummary]:
    """Play ``n_pairs`` pairs (A-White then B-White) and return summaries in task order.

    Results do not depend on ``workers``: seeds come only from
    ``base_seed + pair``, and ``imap`` preserves task order.
    """
    if replay_dir is not None:
        Path(replay_dir).mkdir(parents=True, exist_ok=True)
    tasks = []
    for pair in range(n_pairs):
        seed_a, seed_b = pair_seeds(base_seed, pair)
        for a_color in ("white", "black"):
            tasks.append((agent_a, agent_b, pair, a_color, seed_a, seed_b, max_plies, replay_dir))
    if workers <= 1:
        return [_play_task(task) for task in tasks]
    with multiprocessing.Pool(workers) as pool:
        return list(pool.imap(_play_task, tasks, chunksize=1))


def write_jsonl(summaries: list[GameSummary], path: str | Path) -> None:
    """Write one JSON object per summary."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for summary in summaries:
            handle.write(json.dumps(asdict(summary)) + "\n")
