"""Run a reproducible Stockfish-labeled MoE experiment from a split manifest."""
import argparse
import json
import math
from pathlib import Path

from .core import Mixture
from .train import collect, train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--splits', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--particles', type=int, default=16)
    parser.add_argument('--max-plies', type=int, default=12)
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--train-games', type=int, help='Limit number of training games')
    parser.add_argument('--validation-games', type=int, help='Limit number of validation games')
    args = parser.parse_args()
    if min(args.particles, args.max_plies, args.epochs) < 1:
        parser.error('particles, max-plies and epochs must be positive')
    if any(n is not None and n < 1 for n in (args.train_games, args.validation_games)):
        parser.error('game limits must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    marker = args.output / 'settings.json'
    if marker.exists():
        parser.error('Use a new experiment directory')
    splits = json.loads(args.splits.read_text())['splits']
    paths = {split: [item['path'] for item in splits[split]]
             for split in ('train', 'validation')}
    paths['train'] = paths['train'][:args.train_games]
    paths['validation'] = paths['validation'][:args.validation_games]
    marker.write_text(json.dumps({'splits': str(args.splits.resolve()), 'paths': paths,
                                  'stockfish': str(Path(args.stockfish).resolve()),
                                  'particles': args.particles, 'max_plies': args.max_plies,
                                  'epochs': args.epochs}, indent=2) + '\n')
    for split, games in paths.items():
        print(json.dumps({'stage': split, 'games': len(games)}), flush=True)
        collect(games, args.output / (split + '.jsonl'), args.particles,
                args.stockfish, args.max_plies)
    train(args.output / 'train.jsonl', args.output / 'mixture.json', args.epochs)
    model = Mixture.load(args.output / 'mixture.json')
    rows = [json.loads(line) for line in (args.output / 'validation.jsonl').read_text().splitlines()]
    if not rows:
        raise ValueError('No retained validation states')
    def nll(estimator, examples):
        if not examples:
            return None
        return sum(-math.log(max(estimator.components(r['features'], r['prior'], r['context'])[0][r['target']], 1e-30)) for r in examples) / len(examples)
    ambiguous = [r for r in rows if len(r['prior']) > 1]
    report = {'validation_rows': len(rows), 'validation_multistate_rows': sum(len(r['prior']) > 1 for r in rows),
              'prior_nll': nll(Mixture(), rows), 'trained_nll': nll(model, rows),
              'multistate_prior_nll': nll(Mixture(), ambiguous),
              'multistate_trained_nll': nll(model, ambiguous),
              'scope': 'retained histories within first %d plies only' % args.max_plies}
    (args.output / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
