"""Audit terminal candidate losses, separating observable evidence from hindsight."""
import argparse
from collections import Counter
import json
from pathlib import Path

import chess
from referee import FowBoard, fow_moves
from uniform_random import ObservationTracker
from .encoding import action_index
from .tactics import tactical_targets, proven_attackers


def analyze(path):
    replay = json.loads(Path(path).read_text())
    if "frames" not in replay or replay.get("result") not in ("1-0", "0-1"):
        return None
    side = True if replay.get("white") == "candidate" else False if replay.get("black") == "candidate" else None
    if side is None or ((replay["result"] == "1-0") == side):
        return None
    row = {"path": str(path), "reason": replay["reason"], "candidate_white": side}
    diagnostics = replay.get("privateDiagnostics", {}).get("white" if side else "black", "")
    row["belief_exhaustion_logged"] = "Belief exhausted" in diagnostics
    row["search_timeout_status"] = "not instrumented; cannot attribute from replay"
    if replay.get("failedSide"):
        row["classification"] = "protocol_failure"
        return row
    if replay["reason"] != "King capturable":
        row["classification"] = "other_terminal_loss"
        return row
    board = FowBoard()
    tracker = ObservationTracker(side)
    frames = replay["frames"]
    for ply, frame in enumerate(frames[:-1]):
        tracker.observe(frame["white" if side else "black"])
        move = chess.Move.from_uci(frames[ply + 1]["move"])
        if ply == len(frames) - 2:
            if board.turn != side:
                row["classification"] = "unexpected_terminal_sequence"
                return row
            labels = tactical_targets(tracker)
            safe_actual = []
            for alternative in fow_moves(board):
                board.push(alternative)
                king = board.king(side)
                if king is not None and not board.is_attacked_by(not side, king):
                    safe_actual.append(alternative.uci())
                board.pop()
            row.update(ply=ply, move=move.uci(), observation=tracker.current,
                       alternative_moves_safe_in_true_board=safe_actual,
                       alternatives_not_proven_unsafe=len(labels["legal"]) - len(labels["bad"]))
            visible = action_index(move) in labels["bad"]
            row["classification"] = ("observable_king_exposure" if visible else "hidden_or_unproven_attack")
            row["no_safe_move_in_actual_board"] = not safe_actual
        if board.turn == side:
            tracker.record_move(move)
        board.push(move)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [row for directory in args.directories for path in sorted(directory.glob("*.json"))
            if (row := analyze(path)) is not None]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"losses": len(rows), "classifications": dict(Counter(r["classification"] for r in rows)),
              "observable_with_hindsight_safe_alternative": sum(r["classification"] == "observable_king_exposure" and bool(r.get("alternative_moves_safe_in_true_board")) for r in rows),
              "notes": "Full board is diagnostic hindsight only. Not-proven-unsafe is not guaranteed safe. Missing timeout telemetry is not evidence of no timeouts.",
              "games": rows}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "games"}))


if __name__ == "__main__":
    main()
