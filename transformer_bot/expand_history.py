"""Create a longer-history checkpoint without overwriting the trained source."""
import argparse
import hashlib
from pathlib import Path

import torch
from .model import HistoryTransformer, initialize_from


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", type=int, default=8)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.source.resolve():
        parser.error("Output must be a new checkpoint path")
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=True)
    config = dict(checkpoint["config"])
    if args.window <= config["window"]:
        parser.error("New window must exceed the source window")
    old_window = config["window"]
    config["window"] = args.window
    model = HistoryTransformer(**config)
    initialize_from(model, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"config": model.config, "state_dict": model.state_dict(),
                "history_expansion": {"source": str(args.source.resolve()),
                                      "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                                      "old_window": old_window, "new_window": args.window,
                                      "fine_tuned": False}}, args.output)
    print(f"Expanded {old_window} to {args.window} observations ({64 * args.window} tokens). New time slots require fine-tuning.")


if __name__ == "__main__":
    main()
