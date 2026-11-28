"""Fixed-seed, both-color protocol matches; never automatically promote a model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from referee import run_match


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", nargs="+", type=int, default=[101, 202, 303])
    parser.add_argument("--search", action="store_true", help="Evaluate deployed search as well as network")
    parser.add_argument("--max-plies", type=int, default=1000)
    parser.add_argument("--dataset", type=Path, help="Optional final held-out replay evaluation")
    parser.add_argument("--tactical-opponents", action="store_true")
    args = parser.parse_args()
    if args.max_plies < 1:
        parser.error("max-plies must be positive")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parent.parent
    def bot(weights, seed):
        cmd = [sys.executable, "-m", "transformer_bot", "--weights", str(weights.resolve()), "--seed", str(seed)]
        return cmd if args.search else cmd + ["--policy-only"]
    records = []
    for seed in args.seeds:
        opponents = {"random": [sys.executable, str(root / "uniform_random.py"), "--seed", str(seed)],
                     "baseline": [sys.executable, str(root / "baseline.py"), "--seed", str(seed)],
                     "reference": bot(args.reference, seed)}
        if args.tactical_opponents:
            opponents.update({name: [sys.executable, "-m", "transformer_bot.opponents", "--kind", name, "--seed", str(seed)]
                              for name in ("tactical", "search")})
        for name, opponent in opponents.items():
            for side in (True, False):
                candidate = bot(args.candidate, seed)
                white, black = (candidate, opponent) if side else (opponent, candidate)
                replay = run_match(white, black, max_plies=args.max_plies,
                                   white_name="candidate" if side else name,
                                   black_name=name if side else "candidate")
                result = replay["result"]
                score = (0.5 if result == "1/2-1/2" else
                         float((result == "1-0") == side) if result in ("1-0", "0-1") else None)
                record = {"opponent": name, "seed": seed, "candidate_white": side,
                          "result": result, "score": score, "reason": replay["reason"],
                          "failedSide": replay.get("failedSide"), "warnings": replay.get("warnings", []),
                          "plies": len(replay["frames"]) - 1}
                records.append(record)
                (args.output / f"{name}-{seed}-{'white' if side else 'black'}.json").write_text(json.dumps(replay) + "\n")
                print(json.dumps(record), flush=True)
    summary = {"mode": "search" if args.search else "policy_only", "games": records,
               "candidate": str(args.candidate.resolve()), "reference": str(args.reference.resolve()),
               "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
               "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
               "automatically_promoted": False}
    summary["scores"] = {name: sum(r["score"] for r in records if r["opponent"] == name and r["score"] is not None) /
                         max(1, sum(r["score"] is not None for r in records if r["opponent"] == name))
                         for name in opponents}
    if args.dataset:
        import torch
        from .dataset import split_paths
        from .model import load_model, batch_inputs
        from .train import replay_examples
        from .selfplay import distribution
        torch.set_num_threads(2)
        test = split_paths(args.dataset)["test"]
        summary["held_out"] = {}
        for label, checkpoint in (("candidate", args.candidate), ("reference", args.reference)):
            model = load_model(checkpoint)
            examples = [e for p in test for e in replay_examples(p, model.config["window"])]
            mse = nll = 0.0
            with torch.inference_mode():
                for offset in range(0, len(examples), 16):
                    batch = examples[offset:offset + 16]
                    logits, values = model(*batch_inputs([(e[0], e[1]) for e in batch], model.config["window"]))
                    mse += float((values - torch.tensor([e[3] for e in batch])).square().sum())
                    nll -= float(distribution(logits, [e[4] for e in batch]).log_prob(torch.tensor([e[2] for e in batch])).sum())
            summary["held_out"][label] = {"positions": len(examples), "value_mse": mse / len(examples),
                                          "all_moves_nll": nll / len(examples)}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"scores": summary["scores"], "held_out": summary.get("held_out")}), flush=True)


if __name__ == "__main__":
    main()
