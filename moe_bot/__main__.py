"""Run with python3 -m moe_bot; stdout is reserved for the referee protocol."""
import argparse
import json
import sys
import time

from uniform_random import ObservationTracker, OBSERVATION_CHARACTERS
from .core import RecoverableBelief, Bot, Deadline, Mixture, ValueExpert, find_stockfish, time_budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    engine = parser.add_mutually_exclusive_group()
    engine.add_argument('--stockfish', help='Path to a local UCI Stockfish executable')
    engine.add_argument('--no-stockfish', action='store_true', help='Use material evaluation')
    parser.add_argument('--weights', help='Trained mixture JSON')
    parser.add_argument('--particles', type=int, default=256)
    parser.add_argument('--search-particles', type=int, default=16)
    parser.add_argument('--depth', type=int, default=2)
    parser.add_argument('--seconds', type=float, default=1.0)
    parser.add_argument('--engine-seconds', type=float, default=0.01)
    parser.add_argument('--temperature', type=float, default=0.08)
    parser.add_argument('--robustness', type=float, default=0.35)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--diagnostics', action='store_true')
    args = parser.parse_args()
    if (args.particles < 1 or args.search_particles < 1 or args.depth < 1 or args.seconds <= 0 or
            args.engine_seconds <= 0 or args.temperature < 0 or not 0 <= args.robustness <= 1):
        parser.error('Invalid particle count, depth, time, temperature, or robustness')
    if input().strip() != 'fow':
        return
    color, _, increment = input().split()
    side = color == 'w'
    tracker = ObservationTracker(side)
    belief = RecoverableBelief(side, args.particles, args.seed)
    engine_path = None if args.no_stockfish else (args.stockfish or find_stockfish())
    value = ValueExpert(engine_path, args.engine_seconds)
    bot = Bot(side, value, Mixture.load(args.weights) if args.weights else None,
              args.seed, args.depth, args.robustness, args.temperature)
    if not engine_path:
        print('Stockfish not configured: material evaluation fallback.', file=sys.stderr)
    else:
        print('Stockfish engine: ' + engine_path, file=sys.stderr)
    print('ready', flush=True)
    # Queued observations are processed after the clock line so their filtering
    # cost can be deducted from the time allowance reported by the referee.
    pending = []
    warned = False
    observations = 0
    try:
        for raw in sys.stdin:
            line = raw.strip()
            if len(line) == 64 and set(line) <= OBSERVATION_CHARACTERS:
                pending.append(line)
                continue
            remaining = float(line)
            started = time.monotonic()
            if not pending:
                return
            phase, allowance, filter_seconds = time_budget(
                pending[-1], side, observations + len(pending) - 1,
                len(belief.filter.boards), belief.capacity, remaining, float(increment), args.seconds)
            filter_deadline = started + filter_seconds
            timed_out = False
            for view in pending:
                tracker.observe(view)
                try:
                    belief.observe(view, deadline=filter_deadline)
                except Deadline:
                    # Keep the last consistent checkpoint for a later retry.
                    timed_out = True
            observations += len(pending)
            pending.clear()
            legal = tracker.legal_moves()
            if not legal:
                return
            if not belief.boards and not warned:
                print('Particle depletion: using observation-legal capture fallback.', file=sys.stderr)
                warned = True
            budget = max(0, allowance - (time.monotonic() - started))
            sample = belief.search_sample(args.search_particles)
            move = bot.choose(sample, legal, tracker.current, budget)
            tracker.record_move(move)
            belief.record_move(move)
            if args.diagnostics:
                print(json.dumps({'depth': bot.report['depth'], 'states': len(belief.boards),
                                  'mode': bot.report['mode'], 'value_sources': dict(value.sources),
                                  'phase': phase, 'move_budget': allowance,
                                  'filter_budget': filter_seconds, 'filter_timeout': timed_out,
                                  'pending_observations': len(belief.queue),
                                  'search_states': len(sample.boards)}),
                      file=sys.stderr, flush=True)
            print('move ' + move.uci(), flush=True)
    finally:
        value.close()


if __name__ == '__main__':
    main()
