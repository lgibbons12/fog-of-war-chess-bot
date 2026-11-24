"""Supervised policy/value bootstrap from complete local-referee replay JSONs."""
import argparse
import json
import hashlib
from pathlib import Path
import random

import chess
import torch
from torch.nn import functional as F

from uniform_random import ObservationTracker
from .encoding import action_index
from .model import HistoryTransformer, batch_inputs


def replay_examples(path, window, winners_only=False, tactics=False):
    replay = json.loads(Path(path).read_text())
    result = replay["result"]
    if result not in ("1-0", "0-1", "1/2-1/2") or "failedSide" in replay:
        raise ValueError(f"{path}: need a completed game without protocol failures")
    frames = replay["frames"]
    examples = []
    for side, field in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        tracker, history = ObservationTracker(side), []
        reward = 0.0 if result == "1/2-1/2" else (1.0 if (result == "1-0") == side else -1.0)
        # Never consume the terminal frame as an input. frame[i+1].move is the
        # action taken FROM frame[i], not a feature available at prediction time.
        for i, frame in enumerate(frames[:-1]):
            turn = i % 2 == 0
            tracker.observe(frame[field])
            history.append((frame[field], turn))
            history = history[-window:]
            if turn != side:
                continue
            legal = tracker.legal_moves()
            move = chess.Move.from_uci(frames[i + 1]["move"])
            if move not in legal:
                raise ValueError(f"{path}: invalid action at ply {i}")
            acceptable = []
            if tactics:
                from .tactics import tactical_targets
                acceptable = tactical_targets(tracker)["acceptable"]
            examples.append((list(history), side, action_index(move), reward,
                             [action_index(candidate) for candidate in legal],
                             float(not winners_only or reward > 0), acceptable))
            tracker.record_move(move)
    return examples


def loss_for(model, examples, device, tactical_weight=0.0):
    logits, values = model(*batch_inputs([(e[0], e[1]) for e in examples],
                                         model.config["window"], device))
    mask = torch.full_like(logits, float("-inf"))
    for row, example in enumerate(examples):
        mask[row, example[4]] = 0
    targets = torch.tensor([e[2] for e in examples], device=device)
    rewards = torch.tensor([e[3] for e in examples], device=device)
    weights = torch.tensor([e[5] if len(e) > 5 else 1.0 for e in examples], device=device)
    policy = (F.cross_entropy(logits + mask, targets, reduction="none") * weights).sum() / weights.sum().clamp_min(1)
    value = F.mse_loss(values, rewards)
    from .tactics import tactical_loss
    return policy + value + tactical_weight * tactical_loss(logits, examples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replays", nargs="*", type=Path)
    parser.add_argument("--dataset", type=Path, help="Frozen train/validation/test manifest")
    parser.add_argument("--winners-only", action="store_true", help="Imitate winning sides; value still learns all results")
    parser.add_argument("--output", type=Path, default=Path("transformer.pt"))
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--initialize-from", type=Path, help="Transfer compatible weights into a new architecture")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--window", type=int, default=4)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=7980)
    parser.add_argument("--policy-head", choices=["flat", "pair"], default="flat")
    parser.add_argument("--architecture", choices=["factorized", "spacetime"], default="factorized")
    parser.add_argument("--tactical-weight", type=float, default=0.0)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--metrics", type=Path)
    args = parser.parse_args()
    if args.resume and args.initialize_from:
        parser.error("--resume and --initialize-from are mutually exclusive")
    import math
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0 or not math.isfinite(args.tactical_weight) or args.tactical_weight < 0:
        parser.error("Invalid learning rate or tactical weight")
    paths = list(dict.fromkeys(path.resolve() for path in args.replays))
    if (not args.dataset and len(paths) < 2) or min(args.epochs, args.batch_size, args.window) < 1:
        parser.error("Supply at least two distinct games and positive training options")
    if args.dataset and paths:
        parser.error("Use either --dataset or positional replays")
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(2)
    rng.shuffle(paths)
    split = max(1, len(paths) // 5)
    if args.dataset:
        from .dataset import split_paths
        saved = split_paths(args.dataset)
        training_paths, validation_paths = saved["train"], saved["validation"]
    else:
        training_paths, validation_paths = paths[split:], paths[:split]
    from .model import load_model
    model = (load_model(args.resume) if args.resume else
             HistoryTransformer(window=args.window, policy_head=args.policy_head, architecture=args.architecture)).to(args.device)
    if args.initialize_from:
        from .model import initialize_from
        transferred = initialize_from(model, args.initialize_from)
        print(f"Warm-started {len(transferred)} tensors; architecture behavior changes", flush=True)
    window = model.config["window"]
    validation = [e for path in validation_paths for e in replay_examples(path, window, args.winners_only, args.tactical_weight > 0)]
    training = [e for path in training_paths for e in replay_examples(path, window, args.winners_only, args.tactical_weight > 0)]
    if not validation or not training:
        parser.error("Both training and validation splits need played moves")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.01)
    best = float("inf")
    metrics = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Prepared {len(training)} training and {len(validation)} validation decisions", flush=True)
    for epoch in range(args.epochs):
        model.train()
        rng.shuffle(training)
        total = 0.0
        for offset in range(0, len(training), args.batch_size):
            batch = training[offset:offset + args.batch_size]
            optimizer.zero_grad()
            loss = loss_for(model, batch, args.device, args.tactical_weight)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite supervised loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            total += float(loss.detach()) * len(batch)
        model.eval()
        with torch.inference_mode():
            val = sum(float(loss_for(model, validation[i:i + args.batch_size], args.device, args.tactical_weight))
                      * len(validation[i:i + args.batch_size])
                      for i in range(0, len(validation), args.batch_size)) / len(validation)
        print(f"epoch={epoch + 1} train={total / len(training):.4f} validation={val:.4f}")
        metrics.append({"epoch": epoch + 1, "train": total / len(training), "validation": val})
        if args.metrics:
            args.metrics.parent.mkdir(parents=True, exist_ok=True)
            args.metrics.write_text(json.dumps(metrics, indent=2) + "\n")
        if val < best:
            best = val
            torch.save({"config": model.config, "state_dict": model.state_dict(),
                        "validation_loss": val, "seed": args.seed,
                        "winners_only": args.winners_only,
                        "tactical_weight": args.tactical_weight, "learning_rate": args.learning_rate,
                        "initialize_from": str(args.initialize_from) if args.initialize_from else None,
                        "dataset": str(args.dataset) if args.dataset else None,
                        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest() if args.dataset else None,
                        "training_games": [str(p) for p in training_paths],
                        "validation_games": [str(p) for p in validation_paths]}, args.output)


if __name__ == "__main__":
    main()
