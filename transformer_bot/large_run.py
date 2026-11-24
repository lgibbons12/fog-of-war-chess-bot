"""Restartable, sequential local experiment; stage completion is explicit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--games-per-iteration", type=int, default=10)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1401, 2402])
    parser.add_argument("--evaluation-seeds", type=int, nargs="+", default=[1701, 2802])
    args = parser.parse_args()
    if min(args.epochs, args.iterations, args.games_per_iteration) < 1 or args.games_per_iteration % 2:
        parser.error("Positive counts and even games-per-iteration required")
    args.output.mkdir(parents=True, exist_ok=True)
    config = {k: str(v.resolve()) if isinstance(v, Path) else v for k, v in vars(args).items()}
    config["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    config_path = args.output / "config.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        parser.error("Existing experiment has a different configuration; use a new output directory")
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    status_path = args.output / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {"completed": []}

    def stage(name, module, options, artifact):
        if name in status["completed"]:
            if not artifact.exists():
                raise ValueError(f"Completed stage {name} is missing its artifact")
            return
        status.update(active=name, state="running", updated=time.time())
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        command = [sys.executable, "-u", "-m", module, *map(str, options)]
        print("Starting " + name, flush=True)
        with (args.output / (name + ".log")).open("a") as log:
            log.write(json.dumps(command) + "\n")
            log.flush()
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode != 0 or not artifact.exists():
            status.update(state="failed", returncode=completed.returncode)
            status_path.write_text(json.dumps(status, indent=2) + "\n")
            raise RuntimeError(f"Stage {name} failed; see its log. No later stages ran.")
        status["completed"].append(name)
        status.update(active=None, state="between_stages", updated=time.time())
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        print("Completed " + name, flush=True)

    for head in ("flat", "pair"):
        checkpoint = args.output / (head + "-supervised.pt")
        stage("supervised-" + head, "transformer_bot.train",
              ["--dataset", args.dataset, "--resume", args.benchmark / (head + ".pt"),
               "--epochs", args.epochs, "--batch-size", 16, "--tactical-weight", 1,
               "--winners-only", "--output", checkpoint, "--metrics", args.output / (head + "-learning-curve.json")], checkpoint)
        evaluation = args.output / ("eval-supervised-" + head)
        stage("evaluate-supervised-" + head, "transformer_bot.evaluate",
              ["--candidate", checkpoint, "--reference", "data/public-training/pretrained.pt",
               "--output", evaluation, "--seeds", *args.evaluation_seeds, "--tactical-opponents"], evaluation / "summary.json")
    for seed in args.seeds:
        run = args.output / f"rl-{seed}"
        checkpoint = run / f"checkpoint-{args.iterations - 1:03d}.pt"
        stage(f"selfplay-{seed}", "transformer_bot.selfplay",
              ["--initial", args.output / "pair-supervised.pt", "--output", run,
               "--opponents", args.output / "flat-supervised.pt", "data/public-training/pretrained.pt",
               "--iterations", args.iterations, "--games-per-iteration", args.games_per_iteration,
               "--max-plies", 300, "--seed", seed, "--learning-rate", "1e-5",
               "--fixed-opponents", "capture", "tactical", "search", "--tactical-weight", "0.5"], checkpoint)
        evaluation = args.output / f"eval-rl-{seed}"
        stage(f"evaluate-rl-{seed}", "transformer_bot.evaluate",
              ["--candidate", checkpoint, "--reference", args.output / "pair-supervised.pt",
               "--output", evaluation, "--seeds", *args.evaluation_seeds, "--tactical-opponents"], evaluation / "summary.json")
    status.update(state="complete", active=None, updated=time.time())
    status_path.write_text(json.dumps(status, indent=2) + "\n")


if __name__ == "__main__":
    main()
