"""Collect labeled belief sets from referee replays, or train the small MoE gate."""
import argparse
import json
import math
import random
import time

import chess

from referee import FowBoard, observation
from .core import Belief, Bot, Mixture, ValueExpert, entropy, terminal_value


def collect(paths, output, particles=64, stockfish=None, max_plies=None):
    retained, missed = 0, 0
    evaluator = ValueExpert(stockfish)
    try:
        with open(output, 'w') as destination:
            for path in paths:
                with open(path) as source:
                    frames = json.load(source)['frames']
                for side in (True, False):
                    truth, belief = FowBoard(), Belief(side, particles)
                    bot = Bot(side, evaluator)
                    for index, frame in enumerate(frames):
                        if max_plies is not None and index >= max_plies:
                            break
                        if index:
                            move = chess.Move.from_uci(frame['move'])
                            if truth.turn == side:
                                belief.record_move(move)
                            truth.push(move)
                        if terminal_value(truth, side) is not None:
                            break
                        # Only the observation enters inference; truth is used
                        # below solely to assign supervised training labels.
                        view = observation(truth, side)
                        belief.observe(view)
                        if not belief.boards:
                            if truth.turn == side:
                                missed += 1
                            continue
                        if truth.turn != side:
                            continue
                        matches = [i for i, b in enumerate(belief.boards)
                                   if b.fen() == truth.fen() and b.move_stack == truth.move_stack]
                        if not matches:
                            missed += 1
                            continue
                        features = bot.features(belief.boards, time.monotonic() + 3600)
                        row = {'features': features, 'prior': belief.weights,
                               'context': [1.0, entropy(belief.weights) / max(1, math.log(len(features))), 0.2],
                               'target': matches[0], 'game': str(path), 'ply': index,
                               'stockfish': bool(stockfish)}
                        destination.write(json.dumps(row) + '\n')
                        retained += 1
                destination.flush()
                print(json.dumps({'game': str(path), 'retained_labels': retained,
                                  'truth_missing': missed}), flush=True)
    finally:
        evaluator.close()
    print(json.dumps({'retained_labels': retained, 'truth_missing': missed,
                      'coverage': retained / max(1, retained + missed)}))


def train(path, output, epochs=20, rate=0.02, seed=0):
    with open(path) as source:
        rows = [json.loads(line) for line in source if line.strip()]
    if not rows:
        raise ValueError('No training records')
    for row in rows:
        n = len(row['prior'])
        if (not n or len(row['features']) != n or len(row['context']) != 3 or
                any(len(f) != 4 for f in row['features']) or not 0 <= row['target'] < n or
                any(p <= 0 for p in row['prior']) or not math.isclose(sum(row['prior']), 1)):
            raise ValueError('Invalid training record')
        if not all(math.isfinite(x) for x in row['prior'] + row['context'] +
                   [v for f in row['features'] for v in f]):
            raise ValueError('Nonfinite training data')
    model, rng = Mixture(), random.Random(seed)
    for epoch in range(epochs):
        rng.shuffle(rows)
        loss = sum(model.fit_one(r['features'], r['prior'], r['context'], r['target'], rate)
                   for r in rows) / len(rows)
        print(json.dumps({'epoch': epoch + 1, 'train_nll': loss}))
    model.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    collect_parser = sub.add_parser('collect')
    collect_parser.add_argument('replays', nargs='+')
    collect_parser.add_argument('--output', required=True)
    collect_parser.add_argument('--particles', type=int, default=64)
    collect_parser.add_argument('--stockfish')
    collect_parser.add_argument('--max-plies', type=int, help='Limit replay to early plies')
    fit_parser = sub.add_parser('fit')
    fit_parser.add_argument('data')
    fit_parser.add_argument('--output', required=True)
    fit_parser.add_argument('--epochs', type=int, default=20)
    fit_parser.add_argument('--rate', type=float, default=0.02)
    fit_parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'collect':
        if args.particles < 1 or (args.max_plies is not None and args.max_plies < 1):
            parser.error('particles and max-plies must be positive')
        collect(args.replays, args.output, args.particles, args.stockfish, args.max_plies)
    else:
        if args.epochs < 1 or args.rate <= 0:
            parser.error('epochs and rate must be positive')
        train(args.data, args.output, args.epochs, args.rate, args.seed)


if __name__ == '__main__':
    main()
