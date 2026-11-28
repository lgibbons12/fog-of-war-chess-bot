"""Run from the repository root: python -m transformer_bot [--weights model.pt]."""
import argparse
from pathlib import Path
import sys

import chess

from uniform_random import ObservationTracker, OBSERVATION_CHARACTERS
from .encoding import action_index
from .search import Belief, choose_move, material_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--particles", type=int, default=4)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--reserve", type=int, default=32)
    parser.add_argument("--recovery-seconds", type=float, default=0.2)
    parser.add_argument("--policy-only", action="store_true", help="Disable belief/search for policy evaluation")
    args = parser.parse_args()
    if args.particles < 1 or args.depth < 1 or args.seconds <= 0:
        parser.error("particles, depth, and seconds must be positive")
    if input().strip() != "fow":
        return
    color, _, increment = input().split()
    side = color == "w"
    if args.reserve < 1 or args.recovery_seconds < 0:
        parser.error("reserve must be positive and recovery-seconds nonnegative")
    tracker = ObservationTracker(side)
    belief = Belief(side, args.particles, args.seed, args.reserve, args.recovery_seconds)
    model = None
    if args.weights:
        import torch
        from .model import batch_inputs, load_model
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        model = load_model(args.weights)
        def predict(history):
            with torch.inference_mode():
                return model(*batch_inputs([(history, side)], model.config["window"]))
        predict([("?" * 64, chess.WHITE)])
    else:
        print("No weights: using material search and capture fallback.", file=sys.stderr)
    print("ready", flush=True)
    history = []
    ply = 0
    warned = False
    for raw in sys.stdin:
        line = raw.strip()
        if len(line) == 64 and set(line) <= OBSERVATION_CHARACTERS:
            tracker.observe(line)
            recovered_before = belief.recoveries
            if not args.policy_only:
                belief.observe(line)
            if belief.recoveries > recovered_before:
                print(f"Belief recovered at ply {ply} from full observation history.", file=sys.stderr)
                warned = False
            history.append((line, ply % 2 == 0))
            history = history[-(model.config["window"] if model else 4):]
            ply += 1
            continue
        remaining = float(line)
        legal = tracker.legal_moves()
        if not legal:
            return
        if model:
            logits, _ = predict(history)
            scores = {move: float(logits[0, action_index(move)]) for move in legal}
            def evaluate(prefix, observer, board):
                return float(predict(prefix)[1][0])
        else:
            values = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 100}
            scores = {move: values.get(tracker.current[move.to_square].lower(), 0)
                      + (1 if move.promotion else 0) for move in legal}
            def evaluate(prefix, observer, board):
                return material_value(board, observer)
        if not args.policy_only and not belief.boards and not warned:
            print("Belief exhausted; falling back to masked policy/captures.", file=sys.stderr)
            warned = True
        budget = min(args.seconds, max(0, remaining * 0.02 + float(increment) * 0.1),
                     max(0, remaining - 0.1))
        move = choose_move([] if args.policy_only else belief.boards, legal, history, side, evaluate, scores,
                           args.depth, budget)
        tracker.record_move(move)
        belief.record_move(move)
        print("move " + move.uci(), flush=True)


if __name__ == "__main__":
    main()
