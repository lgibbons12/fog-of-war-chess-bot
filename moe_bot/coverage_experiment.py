"""Measure full-game belief coverage on held-out replay observations."""
import argparse
import json
from pathlib import Path
import random
import statistics
import time

import chess
from referee import FowBoard, observation, outcome
from transformer_bot.search import Belief as ReserveBelief, SearchTimeout, repetition_counts
from .core import Belief


class RejuvenatedBelief(ReserveBelief):
    """Experimental uniform reservoir with checkpointed, evidence-consistent replay."""
    def __init__(self, side, capacity, seed, rejuvenate=True):
        super().__init__(side, capacity=capacity, reserve=32, seed=seed, recovery_seconds=0)
        self.checkpoints = []
        self.rejuvenate = rejuvenate
        self.proposals = self.accepted = 0
        self.proposal_rng = random.Random(seed + 1000003)

    def observe(self, view):
        super().observe(view)
        # Each checkpoint was produced after the associated observation; replay
        # starts at the next one and must finish all the way to the present.
        if self.rejuvenate and self.checkpoints:
            self.proposals += 1
            deadline = time.monotonic() + 0.05
            index, boards = self.proposal_rng.choice(self.checkpoints)
            main_rng = self.rng
            self.rng = self.proposal_rng
            try:
                proposal = [b.copy() for b in boards]
                for step in range(index + 1, len(self.evidence)):
                    old_view, move = self.evidence[step]
                    proposal = self._advance(proposal, old_view, move, False, self.reserve, deadline)
                    if not proposal:
                        break
                if proposal and time.monotonic() < deadline:
                    keys = {tuple(b.move_stack) for b in self.pool}
                    novel = [b for b in proposal if tuple(b.move_stack) not in keys]
                    if novel:
                        self.pool = self.rng.sample(self.pool + novel, min(self.reserve, len(self.pool + novel)))
                        self.accepted += len(novel)
            except SearchTimeout:
                pass
            finally:
                self.rng = main_rng
        if self.pool:
            self.checkpoints.append((len(self.evidence) - 1, [b.copy() for b in self.pool]))
            # Bound retained memory; preserve the first checkpoint for recovery.
            if len(self.checkpoints) > 8:
                del self.checkpoints[1]
        self.boards = self.rng.sample(self.pool, min(self.capacity, len(self.pool)))


def audit(path, side, algorithm, capacity, seed):
    with open(path) as stream:
        frames = json.load(stream)['frames']
    truth = FowBoard()
    belief = (RejuvenatedBelief(side, capacity=capacity, seed=seed, rejuvenate=algorithm == 'rejuvenate')
              if algorithm in ('reserve', 'rejuvenate') else
              ReserveBelief(side, capacity=capacity, reserve=capacity, seed=seed,
                           recovery_seconds=0.05 if algorithm == 'recovery' else 0)
              if algorithm in ('reservoir', 'recovery') else Belief(side, capacity=capacity, seed=seed))
    records = []
    queued_seconds = 0.0
    for index, frame in enumerate(frames):
        if index:
            move = chess.Move.from_uci(frame['move'])
            if truth.turn == side:
                belief.record_move(move)
            truth.push(move)
        if outcome(truth, repetition_counts(truth)) is not None:
            break
        start = time.perf_counter()
        belief.observe(observation(truth, side))
        queued_seconds += time.perf_counter() - start
        if truth.turn != side:
            continue
        candidates = belief.boards
        pool = getattr(belief, 'pool', candidates)
        records.append({'ply': index, 'seconds': queued_seconds, 'particles': len(candidates),
                        'pool_particles': len(pool),
                        'proposals': getattr(belief, 'proposals', 0),
                        'accepted': getattr(belief, 'accepted', 0),
                        'pool_state': any(b.fen() == truth.fen() for b in pool),
                        'state': any(b.fen() == truth.fen() for b in candidates),
                        'history': any(b.fen() == truth.fen() and b.move_stack == truth.move_stack
                                       for b in candidates)})
        queued_seconds = 0.0
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--games', nargs='+', required=True, help='Held-out game IDs')
    parser.add_argument('--seeds', nargs='+', type=int, default=[1, 2])
    parser.add_argument('--recovery-only', action='store_true',
                        help='Test the reservoir filter with 50 ms recovery attempts')
    parser.add_argument('--reservoir-only', action='store_true',
                        help='Test only the 32-particle reservoir filter')
    parser.add_argument('--rejuvenation-test', action='store_true',
                        help='Compare 32-history reserve with and without replay rejuvenation, searching 8')
    args = parser.parse_args()
    entries = json.loads(args.split.read_text())['splits']['validation']
    valid = {Path(e['path']).stem: e['path'] for e in entries}
    if any(game not in valid for game in args.games):
        parser.error('Every game must be in the validation split')
    args.output.mkdir(parents=True, exist_ok=True)
    raw_path = args.output / 'runs.jsonl'
    if raw_path.exists():
        parser.error('Choose a new output directory')
    configurations = ([('reserve', 8), ('rejuvenate', 8)] if args.rejuvenation_test else
                      [('recovery', 32)] if args.recovery_only else
                      [('reservoir', 32)] if args.reservoir_only else
                      [('weighted', 8), ('weighted', 32), ('weighted', 128), ('reservoir', 32)])
    with raw_path.open('w') as output:
        for algorithm, capacity in configurations:
            for game in args.games:
                for seed in args.seeds:
                    for side in (True, False):
                        rows = audit(valid[game], side, algorithm, capacity, seed)
                        result = {'game': game, 'side': 'white' if side else 'black',
                                  'algorithm': algorithm, 'capacity': capacity, 'seed': seed,
                                  'records': rows}
                        output.write(json.dumps(result) + '\n')
                        output.flush()
                        print(json.dumps({'algorithm': algorithm, 'capacity': capacity,
                                          'game': game, 'side': result['side'], 'seed': seed,
                                          'covered': sum(r['state'] for r in rows),
                                          'turns': len(rows),
                                          'seconds': round(sum(r['seconds'] for r in rows), 3)}), flush=True)
    runs = [json.loads(line) for line in raw_path.read_text().splitlines()]
    summaries = []
    for algorithm, capacity in configurations:
        rows = [row for run in runs if run['algorithm'] == algorithm and run['capacity'] == capacity
                for row in run['records']]
        times = sorted(r['seconds'] for r in rows)
        summaries.append({'algorithm': algorithm, 'capacity': capacity, 'decisions': len(rows),
                          'board_coverage': sum(r['state'] for r in rows) / len(rows),
                          'pool_coverage': sum(r['pool_state'] for r in rows) / len(rows),
                          'history_coverage': sum(r['history'] for r in rows) / len(rows),
                          'nonempty': sum(r['particles'] > 0 for r in rows) / len(rows),
                          'mean_seconds': statistics.mean(times),
                          'p95_seconds': times[min(len(times)-1, int(0.95*len(times)))],
                          'max_seconds': max(times)})
    (args.output / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
