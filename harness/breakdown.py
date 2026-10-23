"""Loss/draw breakdown, exposure metrics and timings from saved replays of one agent.

``python -m harness.breakdown DIR --agent NAME`` reads every replay JSON
under DIR (recursively; from ``harness.cli --save-replays``). King-capture
losses of the agent are classified from its last decision record plus the
true board:

- (a) a safe move (not a known loss, exposure 0) existed but we chose an exposed one;
- (b) every non-losing move was exposed and the hidden threat was real;
- (c) every move was a known loss.

Exposure metrics, over all of the agent's decisions:

- safe-move availability: fraction of decisions with a non-losing, unexposed move;
- false-alarm rate: fraction of the chosen move's exposed squares that hold no
  real attacker on the true board, overall and per possible type;
- tracker precision by ply (tracked agents only): mean support per hypothesis
  and the fraction of '?' squares where a queen is possible.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics

import chess

from referee import FowBoard

PLY_BUCKET = 20


def decisions(replay: dict, side_name: str):
    """Yield (ply, decision, true board right after that move) for each move by ``side_name``."""
    board = FowBoard()
    for frame in replay["frames"][1:]:
        mover_is_white = board.turn == chess.WHITE
        board.push_uci(frame["move"])
        if mover_is_white == (side_name == "white"):
            yield frame["ply"], frame["decision"], board.copy(stack=False)


def classify_loss(decision: dict, board: chess.Board, side: chess.Color) -> str:
    """Return 'a', 'b', 'c', or a description for a king-capture loss on ``decision``."""
    if decision is None:
        return "no decision record"
    if decision["non_losing_moves"] == 0:
        return "c"
    report = decision["report"]
    if report["known_loss"]:
        return "chose known loss despite a non-losing move (impossible)"
    if decision["min_safe_exposure"] == 0 and report["exposed"]:
        return "a"
    if decision["min_safe_exposure"] > 0 and board.attackers(not side, board.king(side)):
        return "b"
    return "unexplained (soundness bug?)"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay_dir")
    parser.add_argument("--agent", default="safety")
    args = parser.parse_args(argv)

    outcomes, losses, draws, other_losses = Counter(), Counter(), Counter(), Counter()
    hidden_attackers = Counter()
    plies, think, updates = [], [], []
    decision_count = safe_available = 0
    flagged, false_alarms = Counter(), Counter()
    precision = defaultdict(lambda: [0.0, 0.0, 0])  # bucket -> [support sum, queen sum, n]
    for path in sorted(Path(args.replay_dir).rglob("*.json")):
        replay = json.loads(path.read_text())
        for side_name in ("white", "black"):
            if replay[side_name] != args.agent:
                continue
            side = side_name == "white"
            plies.append(replay["plies"])
            think.extend(replay["thinkSeconds"][side_name])
            last = None
            for ply, decision, board in decisions(replay, side_name):
                last = (decision, board)
                if decision is None:
                    continue
                decision_count += 1
                safe_available += decision["min_safe_exposure"] == 0
                updates.extend(decision.get("update_seconds") or [])
                attackers = board.attackers(not side, board.king(side))
                for name, types in decision.get("exposed_types", {}).items():
                    real = chess.parse_square(name) in attackers
                    for kind in types + "*":  # '*' = all flagged squares
                        flagged[kind] += 1
                        false_alarms[kind] += not real
                if decision.get("tracker"):
                    bucket = precision[ply // PLY_BUCKET * PLY_BUCKET]
                    bucket[0] += decision["tracker"]["mean_support"]
                    bucket[1] += decision["tracker"]["queen_fraction"]
                    bucket[2] += 1
            won = replay["result"] == ("1-0" if side else "0-1")
            if replay["result"] == "1/2-1/2":
                outcomes["draw"] += 1
                draws[replay["reason"]] += 1
            elif won:
                outcomes["win"] += 1
            else:
                outcomes["loss"] += 1
                if replay["reason"] == "King capturable" and last is not None:
                    category = classify_loss(last[0], last[1], side)
                    losses[category] += 1
                    if category == "b":
                        board = last[1]
                        for square in board.attackers(not side, board.king(side)):
                            hidden_attackers[board.piece_at(square).symbol().upper()] += 1
                else:
                    other_losses[replay["reason"]] += 1
            break  # an agent playing itself is counted once, as White

    print(f"{args.agent}: {sum(outcomes.values())} games  W/D/L "
          f"{outcomes['win']}/{outcomes['draw']}/{outcomes['loss']}  mean plies "
          f"{statistics.mean(plies) if plies else 0:.1f}")
    print("King-capture losses:")
    for label, text in [("a", "safe move existed, chose exposed"),
                        ("b", "all non-losing moves exposed, threat real"),
                        ("c", "every move a known loss")]:
        print(f"  ({label}) {losses.pop(label, 0):5d}  {text}")
    for category, count in losses.items():
        print(f"  (!) {count:5d}  {category}")
    print(f"  hidden attacker types in (b): {dict(hidden_attackers.most_common())}")
    print(f"Other losses: {dict(other_losses)}")
    print(f"Draws: {dict(draws)}")
    if decision_count:
        print(f"Safe-move availability: {safe_available / decision_count:.3f} of {decision_count} decisions")
    if flagged["*"]:
        per_type = "  ".join(f"{kind}:{false_alarms[kind] / flagged[kind]:.3f}(n={flagged[kind]})"
                             for kind in "PNBRQK" if flagged[kind])
        print(f"False alarms: {false_alarms['*'] / flagged['*']:.3f} of {flagged['*']} flagged squares; "
              f"by possible type {per_type}")
    if precision:
        print("Tracker precision by ply (mean support per hypothesis, fraction of '?' where Q possible):")
        for start in sorted(precision):
            support, queen, n = precision[start]
            print(f"  plies {start:3d}-{start + PLY_BUCKET - 1:3d}: support {support / n:5.2f}  "
                  f"Q-possible {queen / n:.3f}  (n={n})")
    if updates:
        print(f"Tracker update: median {1000 * statistics.median(updates):.3f} ms, "
              f"max {1000 * max(updates):.3f} ms over {len(updates)} updates")
    if think:
        print(f"choose_move: median {1000 * statistics.median(think):.3f} ms, "
              f"max {1000 * max(think):.3f} ms over {len(think)} moves")


if __name__ == "__main__":
    main()
