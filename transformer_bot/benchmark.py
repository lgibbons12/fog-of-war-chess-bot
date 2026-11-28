"""Synthetic observation-only tactical fitting/generalization benchmark."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random

import chess
import torch
from referee import FowBoard, observation
from uniform_random import ObservationTracker
from .model import HistoryTransformer, batch_inputs, load_model
from .tactics import tactical_targets, tactical_loss


def make_examples(count=96, seed=0, held_out=False):
    rng = random.Random(seed)
    examples, seen = [], set()
    files = [5, 6] if held_out else [1, 2, 3, 4]
    kinds = ["king_safety", "capture", "promotion"]
    for attempt in range(count * 500):
        if len(examples) == count:
            return examples
        kind = kinds[len(examples) % 3]
        board = FowBoard(None)
        file = rng.choice(files)
        if kind == "king_safety":
            king = chess.square(file, rng.choice([0, 1]))
            board.set_piece_at(king, chess.Piece(chess.KING, True))
            board.set_piece_at(chess.square(file, rng.choice([2, 3, 4])), chess.Piece(chess.ROOK, True))
            board.set_piece_at(chess.square(file, 7), chess.Piece(chess.ROOK, False))
            board.set_piece_at(chess.A8, chess.Piece(chess.KING, False))
            pawn = chess.square(rng.randrange(8), 1)
            if board.piece_at(pawn) is None:
                board.set_piece_at(pawn, chess.Piece(chess.PAWN, True))
        else:
            board.set_piece_at(chess.A1, chess.Piece(chess.KING, True))
            board.set_piece_at(chess.H8, chess.Piece(chess.KING, False))
            square = chess.square(file, 6 if kind == "promotion" else rng.randrange(2, 6))
            board.set_piece_at(square, chess.Piece(chess.PAWN if kind == "promotion" else chess.QUEEN, True))
            enemy = rng.randrange(8, 56)
            if board.piece_at(enemy) is None:
                board.set_piece_at(enemy, chess.Piece(rng.choice([chess.ROOK, chess.KNIGHT, chess.BISHOP]), False))
        # Vary an always-observed friendly piece as well: moving only hidden
        # enemies otherwise creates duplicate observation puzzles, especially
        # for promotion positions.
        extra = chess.square(rng.randrange(8), rng.randrange(4))
        if board.piece_at(extra) is None:
            board.set_piece_at(extra, chess.Piece(chess.KNIGHT, True))
        board.turn = True
        if board.is_attacked_by(False, board.king(True)) or board.is_attacked_by(True, board.king(False)):
            continue
        if rng.random() < 0.5:
            board = board.mirror()
        side = board.turn
        view = observation(board, side)
        key = (view, side)
        if key in seen:
            continue
        tracker = ObservationTracker(side, rights=0)
        tracker.observe(view)
        labels = tactical_targets(tracker)
        if labels["kind"] != kind or not labels["acceptable"] or len(labels["acceptable"]) == len(labels["legal"]):
            continue
        seen.add(key)
        examples.append(([(view, side)], side, labels["acceptable"][0], 0.0,
                         labels["legal"], 0.0, labels["acceptable"], kind))
    raise ValueError(f"Unable to generate requested unique tactical examples: generated {len(examples)}/{count}")


def score(model, examples):
    correct, total, losses = Counter(), Counter(), 0.0
    model.eval()
    with torch.inference_mode():
        for offset in range(0, len(examples), 16):
            batch = examples[offset:offset + 16]
            logits, _ = model(*batch_inputs([(e[0], e[1]) for e in batch], model.config["window"]))
            losses += float(tactical_loss(logits, batch)) * len(batch)
            for row, example in enumerate(batch):
                legal = example[4]
                choice = legal[int(logits[row, legal].argmax())]
                correct[example[7]] += choice in example[6]
                total[example[7]] += 1
    return {"loss": losses / len(examples), "accuracy": sum(correct.values()) / len(examples),
            "by_kind": {k: {"correct": correct[k], "total": n} for k, n in total.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=150)
    parser.add_argument("--seed", type=int, default=19)
    parser.add_argument("--checkpoint", type=Path, help="Only score an existing checkpoint")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    training = make_examples(96, args.seed)
    test = make_examples(96, args.seed + 1, held_out=True)
    assert not {(e[0][0][0], e[1]) for e in training} & {(e[0][0][0], e[1]) for e in test}
    (args.output / "examples.json").write_text(json.dumps({"training": training, "held_out": test}) + "\n")
    results = {}
    if args.checkpoint:
        results["checkpoint"] = score(load_model(args.checkpoint), test)
    else:
        for head in ("flat", "pair"):
            torch.manual_seed(args.seed)
            rng = random.Random(args.seed)
            model = HistoryTransformer(policy_head=head)
            optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
            before = score(model, test)
            for step in range(args.steps):
                model.train()
                batch = rng.sample(training, 16)
                logits, _ = model(*batch_inputs([(e[0], e[1]) for e in batch], model.config["window"]))
                loss = tactical_loss(logits, batch)
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite benchmark loss")
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
                optimizer.step()
            results[head] = {"initial_test": before, "training": score(model, training), "held_out": score(model, test),
                             "parameters": sum(p.numel() for p in model.parameters()), "steps": args.steps}
            torch.save({"config": model.config, "state_dict": model.state_dict()}, args.output / (head + ".pt"))
            print(json.dumps({head: results[head]}), flush=True)
    (args.output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
