"""Train a mixture gate with validation-based epoch selection."""
import argparse
import json
import math
import random
from pathlib import Path
from .core import Mixture


def read(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError('No examples in ' + str(path))
    return rows


def scores(model, rows):
    values = [-math.log(max(model.components(r['features'], r['prior'], r['context'])[0][r['target']], 1e-30)) for r in rows]
    multiple = [v for v, r in zip(values, rows) if len(r['prior']) > 1]
    return {'rows': len(rows), 'multistate_rows': len(multiple),
            'nll': sum(values) / len(values),
            'multistate_nll': sum(multiple) / len(multiple) if multiple else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train', type=Path, required=True)
    p.add_argument('--validation', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=100)
    p.add_argument('--patience', type=int, default=10)
    p.add_argument('--rate', type=float, default=0.02)
    p.add_argument('--seed', type=int, default=7980)
    a = p.parse_args()
    if min(a.epochs, a.patience, a.rate) <= 0:
        p.error('epochs, patience and rate must be positive')
    a.output.mkdir(parents=True, exist_ok=True)
    if (a.output / 'metrics.json').exists() or (a.output / 'mixture.json').exists():
        p.error('Choose a fresh output directory')
    train, validation = read(a.train), read(a.validation)
    model, rng = Mixture(), random.Random(a.seed)
    best, best_epoch, best_model, stale = scores(model, validation)['nll'], 0, Mixture(), 0
    history = [{'epoch': 0, 'validation': scores(model, validation)}]
    for epoch in range(1, a.epochs + 1):
        rng.shuffle(train)
        train_nll = sum(model.fit_one(r['features'], r['prior'], r['context'], r['target'], a.rate) for r in train) / len(train)
        valid = scores(model, validation)
        history.append({'epoch': epoch, 'train_nll': train_nll, 'validation': valid})
        if valid['nll'] < best - 1e-9:
            best, best_epoch, stale = valid['nll'], epoch, 0
            best_model = Mixture(list(model.scales), [list(row) for row in model.gate])
        else:
            stale += 1
        if stale >= a.patience:
            break
    best_model.save(a.output / 'mixture.json')
    result = {'train_path': str(a.train), 'validation_path': str(a.validation), 'seed': a.seed,
              'rate': a.rate, 'selected_epoch': best_epoch, 'epochs_run': len(history)-1,
              'validation_prior': scores(Mixture(), validation),
              'validation_selected': scores(best_model, validation), 'history': history}
    (a.output / 'metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'history'}))


if __name__ == '__main__':
    main()
