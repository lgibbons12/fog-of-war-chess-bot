"""Validate public replays and freeze opponent-pair-disjoint data splits."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import chess
from referee import FowBoard, fow_moves, observation, outcome, position_key
from .download_replays import NORMAL_REASONS


def validate_replay(replay):
    if replay.get("reason") not in NORMAL_REASONS or "failedSide" in replay:
        raise ValueError("Not a normal chess termination")
    board = FowBoard()
    counts = Counter({position_key(board): 1})
    frames = replay["frames"]
    if len(frames) < 2:
        raise ValueError("No played moves")
    for ply, frame in enumerate(frames):
        if ply:
            if outcome(board, counts):
                raise ValueError("Moves after terminal position")
            move = chess.Move.from_uci(frame["move"])
            if move not in fow_moves(board):
                raise ValueError(f"Illegal move at {ply}")
            board.push(move)
            counts[position_key(board)] += 1
        if frame["ply"] != ply:
            raise ValueError("Nonsequential frames")
        for side, field in ((True, "white"), (False, "black")):
            if frame[field] != observation(board, side):
                raise ValueError(f"Observation/rules mismatch at {ply}")
    terminal = outcome(board, counts)
    if terminal:
        if terminal[0] != replay["result"]:
            raise ValueError("Result disagrees with reconstructed game")
    elif replay["reason"] != "Move limit reached" or replay["result"] != "1/2-1/2":
        raise ValueError("Missing terminal position")
    return len(frames) - 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Downloader manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7980)
    args = parser.parse_args()
    groups, rejected, seen = defaultdict(list), [], set()
    manifest = json.loads(args.source.read_text())
    for game_id in manifest["ids"]:
        path = (args.source.parent / (game_id + ".json")).resolve()
        replay = json.loads(path.read_text())
        try:
            decisions = validate_replay(replay)
        except (ValueError, KeyError) as error:
            rejected.append({"path": str(path), "error": str(error)})
            continue
        trajectory = hashlib.sha256(json.dumps(
            [f["move"] for f in replay["frames"]]).encode()).hexdigest()
        if trajectory in seen:
            continue
        seen.add(trajectory)
        pair = tuple(sorted(str(replay.get(field + "PlayerId") or replay[field])
                            for field in ("white", "black")))
        groups[pair].append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "decisions": decisions, "pair": pair})
    keys = sorted(groups)
    if len(keys) < 3:
        parser.error("Need at least three distinct opponent pairs")
    random.Random(args.seed).shuffle(keys)
    holdout = max(1, len(keys) // 5)
    split_keys = {"test": keys[:holdout], "validation": keys[holdout:2 * holdout],
                  "train": keys[2 * holdout:]}
    splits = {name: [item for key in selected for item in groups[key]]
              for name, selected in split_keys.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"seed": args.seed, "grouping": "unordered opponent pair",
                                     "splits": splits, "rejected": rejected}, indent=2) + "\n")
    print(json.dumps({name: {"games": len(items), "decisions": sum(i["decisions"] for i in items)}
                      for name, items in splits.items()}))


def split_paths(path):
    """Check immutable content and disjointness before using a saved split."""
    splits = json.loads(Path(path).read_text())["splits"]
    seen, pairs = set(), set()
    result = {}
    for name in ("train", "validation", "test"):
        local_pairs = set()
        result[name] = []
        for item in splits[name]:
            source = Path(item["path"])
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if digest != item["sha256"] or digest in seen or tuple(item["pair"]) in pairs:
                raise ValueError("Dataset changed or splits overlap")
            seen.add(digest)
            local_pairs.add(tuple(item["pair"]))
            result[name].append(source)
        pairs.update(local_pairs)
    return result


if __name__ == "__main__":
    main()
