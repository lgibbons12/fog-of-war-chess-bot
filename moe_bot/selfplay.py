"""Generate a bounded, reproducible batch of local MoE self-play replays."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--games', type=int, default=8)
    parser.add_argument('--seed', type=int, default=7980)
    parser.add_argument('--seconds', type=float, default=0.1)
    parser.add_argument('--particles', type=int, default=256)
    parser.add_argument('--max-plies', type=int, default=160)
    engine = parser.add_mutually_exclusive_group()
    engine.add_argument('--stockfish')
    engine.add_argument('--no-stockfish', action='store_true')
    parser.add_argument('--weights')
    args = parser.parse_args()
    if min(args.games, args.particles, args.max_plies, args.seconds) <= 0:
        parser.error('games, particles, max-plies and seconds must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / 'manifest.json'
    if manifest_path.exists() or any(args.output.glob('game-*.json')):
        parser.error('Choose a fresh output directory to preserve previous runs')
    root = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    manifest = {'kind': 'moe-selfplay', 'settings': {**vars(args), 'output': str(output)}, 'games': []}
    for index in range(args.games):
        commands = []
        seeds = [args.seed + index * 2, args.seed + index * 2 + 1]
        for seed in seeds:
            command = [sys.executable, '-m', 'moe_bot', '--seed', str(seed),
                       '--seconds', str(args.seconds), '--particles', str(args.particles),
                       '--diagnostics']
            if args.stockfish:
                command += ['--stockfish', str(Path(args.stockfish).resolve())]
            elif args.no_stockfish:
                command += ['--no-stockfish']
            if args.weights:
                command += ['--weights', str(Path(args.weights).resolve())]
            commands.append(shlex.join(command))
        path = output / f'game-{index:04d}.json'
        with (output / f'game-{index:04d}.log').open('w') as log:
            subprocess.run([sys.executable, 'referee.py', '--trusted-local',
                            '--white', commands[0], '--black', commands[1],
                            '--white-name', f'MoE seed {seeds[0]}',
                            '--black-name', f'MoE seed {seeds[1]}',
                            '--base-time', '60', '--increment', '0.5',
                            '--max-plies', str(args.max_plies), '--output', str(path)],
                           cwd=root, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
        replay = json.loads(path.read_text())
        record = {'path': str(path), 'seeds': seeds, 'result': replay['result'],
                  'reason': replay['reason'], 'plies': len(replay['frames']) - 1}
        manifest['games'].append(record)
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
