"""Loss/draw breakdown and think times from saved replays of one agent.

``python -m harness.breakdown DIR --agent safety`` reads every replay JSON
in DIR (from ``harness.cli --save-replays``). King-capture losses of the
agent are classified from its last decision record plus the true board:

- (a) a safe move (not a known loss, exposure 0) existed but we chose an exposed one;
- (b) every non-losing move was exposed and the hidden threat was real;
- (c) every move was a known loss.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics

import chess

from referee import FowBoard


def our_last_decision(replay: dict, side_name: str) -> tuple[dict | None, FowBoard]:
    """The agent's final decision record and the true board right after that move."""
    board = FowBoard()
    decision = None
    last_board = board.copy()
    for frame in replay["frames"][1:]:
        mover_is_white = board.turn == chess.WHITE
        board.push_uci(frame["move"])
        if mover_is_white == (side_name == "white"):
            decision = frame["decision"]
            last_board = board.copy()
    return decision, last_board


def classify_loss(replay: dict, side_name: str) -> str:
    """Return 'a', 'b', 'c', or a description for a king-capture loss by ``side_name``."""
    decision, board = our_last_decision(replay, side_name)
    if decision is None:
        return "no decision record"
    if decision["non_losing_moves"] == 0:
        return "c"
    report = decision["report"]
    if report["known_loss"]:
        return "chose known loss despite a non-losing move (impossible)"
    if decision["min_safe_exposure"] == 0 and report["exposed"]:
        return "a"
    side = side_name == "white"
    attackers = set(board.attackers(not side, board.king(side)))
    if decision["min_safe_exposure"] > 0 and attackers:
        return "b"
    return "unexplained (soundness bug?)"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay_dir")
    parser.add_argument("--agent", default="safety")
    args = parser.parse_args(argv)

    outcomes, losses, draws, other_losses = Counter(), Counter(), Counter(), Counter()
    plies, think = [], []
    hidden_attackers = Counter()
    for path in sorted(Path(args.replay_dir).glob("*.json")):
        replay = json.loads(path.read_text())
        for side_name in ("white", "black"):
            if replay[side_name] != args.agent:
                continue
            plies.append(replay["plies"])
            think.extend(replay["thinkSeconds"][side_name])
            won = replay["result"] == ("1-0" if side_name == "white" else "0-1")
            if replay["result"] == "1/2-1/2":
                outcomes["draw"] += 1
                draws[replay["reason"]] += 1
            elif won:
                outcomes["win"] += 1
            else:
                outcomes["loss"] += 1
                if replay["reason"] == "King capturable":
                    category = classify_loss(replay, side_name)
                    losses[category] += 1
                    if category == "b":
                        _, board = our_last_decision(replay, side_name)
                        side = side_name == "white"
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
    if think:
        print(f"choose_move: median {1000 * statistics.median(think):.3f} ms, "
              f"max {1000 * max(think):.3f} ms over {len(think)} moves")


if __name__ == "__main__":
    main()
