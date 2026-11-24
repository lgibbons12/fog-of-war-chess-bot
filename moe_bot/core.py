"""Bounded Bayesian filtering, four experts, and robust stochastic search.

All boards are hypotheses derived from observations, never referee truth.
Stockfish is an orthodox evaluation feature, not a FOW rules engine.
"""
from collections import defaultdict
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import time
from types import SimpleNamespace

import chess
import chess.engine

from referee import FowBoard, fow_moves, observation, outcome, position_key
from transformer_bot.search import material_value, ordered_moves, repetition_counts


def find_stockfish():
    """Discover an explicitly configured, PATH, or bundled macOS engine."""
    configured = os.environ.get('STOCKFISH_PATH')
    if configured:
        return configured
    executable = shutil.which('stockfish')
    if executable:
        return executable
    bundled = (Path(__file__).resolve().parent.parent / 'engines' / 'stockfish-19' /
               'stockfish' / 'stockfish-macos-universal')
    if sys.platform == 'darwin' and bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    return None


def softmax(values):
    peak = max(values)
    weights = [math.exp(v - peak) for v in values]
    total = sum(weights)
    return [w / total for w in weights]


def entropy(probabilities):
    return -sum(p * math.log(p) for p in probabilities if p > 0)


def terminal_value(board, side):
    result = outcome(board, repetition_counts(board))
    if result is None:
        return None
    return 0.0 if result[0] == '1/2-1/2' else (1.0 if (result[0] == '1-0') == side else -1.0)


class Deadline(Exception):
    pass


def time_budget(view, side, ply, state_count, capacity, remaining, increment, max_seconds):
    """Allocate a clock-limited move budget and a phase/complexity filter share.

    Own pieces are always visible. Treat sparse own material as an endgame
    signal only after the opening; it is a heuristic, not perfect game knowledge.
    """
    own = 'PNBRQK' if side else 'pnbrqk'
    pieces = [char.upper() for char in view if char in own]
    major_minor = sum(char in 'NBRQ' for char in pieces)
    if ply < 16:
        phase, factor, share = 'opening', 0.7, 0.4
    elif ply >= 40 and (len(pieces) <= 7 or major_minor <= 2):
        phase, factor, share = 'endgame', 0.55, 0.3
    else:
        phase, factor, share = 'middlegame', 1.0, 0.65
    # Increasing the capacity must not shrink the time allocated to the same
    # existing number of hypotheses. Saturate load at 16 retained states.
    complexity = min(1.0, max(0.0, state_count / max(1, min(capacity, 16))))
    # Small beliefs need less filtering, leaving a larger share for search.
    share *= 0.65 + 0.35 * complexity
    reserve = min(0.15, max(0.0, remaining * 0.1))
    allowance = min(max_seconds * factor, remaining * 0.03 + increment * 0.2,
                    max(0.0, remaining - reserve))
    return phase, allowance, allowance * share


class Belief:
    """Weighted finite histories; uniform opponent-move prior before filtering.

    Systematic resampling bounds the number of retained histories. Identical
    sampled histories are merged by multiplicity, preserving posterior mass.
    No recovery invents a board if every retained history is contradicted.
    """
    def __init__(self, side, capacity=256, seed=0):
        if capacity < 1:
            raise ValueError('capacity must be positive')
        self.side, self.capacity = side, capacity
        self.boards, self.weights = [FowBoard()], [1.0]
        self.started, self.pending = False, None
        self.rng = random.Random(seed)

    def record_move(self, move):
        self.pending = move

    def observe(self, view, deadline=None):
        survivors, weights = [], []
        for board, prior in zip(self.boards, self.weights):
            if deadline is not None and time.monotonic() >= deadline:
                raise Deadline
            parent_counts = repetition_counts(board)
            if not self.started:
                branches = [(board, prior)]
            else:
                moves = fow_moves(board)
                if board.turn == self.side:
                    moves = [self.pending] if self.pending in moves else []
                branches = []
                for move in moves:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise Deadline
                    child = board.copy()
                    child.push(move)
                    branches.append((child, prior / len(moves)))
            for child, weight in branches:
                if deadline is not None and time.monotonic() >= deadline:
                    raise Deadline
                if observation(child, self.side) == view:
                    counts = parent_counts.copy()
                    if child is not board:
                        counts[position_key(child)] += 1
                    if outcome(child, counts) is None:
                        survivors.append(child)
                        weights.append(weight)
        total = sum(weights)
        weights = [w / total for w in weights]
        if len(survivors) > self.capacity:
            start = self.rng.random() / self.capacity
            counts = defaultdict(int)
            index, cumulative = 0, weights[0]
            for n in range(self.capacity):
                point = start + n / self.capacity
                while point > cumulative and index < len(weights) - 1:
                    index += 1
                    cumulative += weights[index]
                counts[index] += 1
            survivors, weights = ([survivors[i] for i in counts],
                                  [count / self.capacity for count in counts.values()])
        self.boards, self.weights = survivors, weights
        self.started, self.pending = True, None


class RecoverableBelief:
    """Retain a consistent checkpoint and replay queued observations after timeout.

    Stale checkpoints are never exposed as current hypotheses. A costly single
    observation may still exceed every deadline; retries do not resume halfway.
    """
    def __init__(self, side, capacity=256, seed=0):
        self.filter = Belief(side, capacity, seed)
        self.capacity = capacity
        self.queue = []
        self.pending = None
        self.rng = random.Random(seed + 9173)

    @property
    def boards(self):
        return [] if self.queue else self.filter.boards

    @property
    def weights(self):
        return [] if self.queue else self.filter.weights

    def record_move(self, move):
        self.pending = move

    def observe(self, view, deadline=None):
        self.queue.append((view, self.pending))
        self.pending = None
        self.catch_up(deadline)

    def catch_up(self, deadline=None):
        while self.queue:
            view, move = self.queue[0]
            self.filter.pending = move
            self.filter.observe(view, deadline)
            self.queue.pop(0)

    def search_sample(self, limit):
        boards, weights = self.boards, self.weights
        if len(boards) <= limit:
            return SimpleNamespace(boards=boards, weights=weights)
        counts = defaultdict(int)
        start = self.rng.random() / limit
        index, cumulative = 0, weights[0]
        for n in range(limit):
            point = start + n / limit
            while point > cumulative and index < len(weights) - 1:
                index += 1
                cumulative += weights[index]
            counts[index] += 1
        return SimpleNamespace(boards=[boards[i] for i in counts],
                               weights=[n / limit for n in counts.values()])


class ValueExpert:
    def __init__(self, path=None, engine_seconds=0.01):
        self.engine = chess.engine.SimpleEngine.popen_uci(path, timeout=5.0) if path else None
        if self.engine:
            self.engine.configure({'Threads': 1, 'Hash': 16})
        self.engine_seconds = engine_seconds
        self.cache = {}
        self.sources = defaultdict(int)

    def evaluate(self, board, side, deadline):
        if time.monotonic() >= deadline:
            raise Deadline
        terminal = terminal_value(board, side)
        if terminal is not None:
            return terminal
        key = (board.fen(), side)
        if key in self.cache:
            return self.cache[key]
        ordinary = chess.Board(board.fen())
        value, source = material_value(board, side), 'material'
        # Invalid orthodox positions must never be sent to Stockfish.
        if self.engine and ordinary.is_valid():
            remaining = deadline - time.monotonic()
            if remaining > self.engine_seconds + 0.02:
                try:
                    info = self.engine.analyse(ordinary, chess.engine.Limit(time=self.engine_seconds))
                    cp = info['score'].pov(side).score(mate_score=10000)
                    value, source = math.tanh(cp / 600), 'stockfish'
                except (chess.engine.EngineError, TimeoutError):
                    self.sources['engine_errors'] += 1
        value = max(-0.99, min(0.99, value))
        self.sources[source] += 1
        # A temporary deadline or engine error must not permanently replace an
        # available engine score with material on later, less constrained turns.
        if source == 'stockfish' or not self.engine or not ordinary.is_valid():
            if len(self.cache) >= 8192:
                self.cache.clear()
            self.cache[key] = value
        return value

    def close(self):
        if self.engine:
            try:
                self.engine.quit()
            except (chess.engine.EngineError, TimeoutError):
                pass


class InformationExpert:
    @staticmethod
    def state(board, side, deadline):
        before = observation(board, side)
        gains = []
        for move in fow_moves(board):
            if time.monotonic() >= deadline:
                raise Deadline
            child = board.copy(stack=False)
            child.push(move)
            after = observation(child, side)
            gains.append(sum(a == '?' and b != '?' for a, b in zip(before, after)) / 64)
        return sum(gains) / max(1, len(gains))

    @staticmethod
    def partition(boards, probabilities, side):
        """Immediate expected entropy reduction, in nats (not exact utility VOI)."""
        groups = defaultdict(float)
        surprises = []
        keys = []
        for board, p in zip(boards, probabilities):
            result = terminal_value(board, side)
            key = ('result', result) if result is not None else ('view', observation(board, side))
            keys.append(key)
            groups[key] += p
        for key in keys:
            surprises.append(-math.log(max(groups[key], 1e-30)))
        return entropy(groups.values()), surprises


class RiskExpert:
    @staticmethod
    def state(board, side):
        king = board.king(side)
        if king is None:
            return 1.0
        king_threat = float(board.is_attacked_by(not side, king))
        exposed = sum(len(board.attackers(not side, sq)) > 0
                      for sq in chess.SquareSet(board.occupied_co[side]))
        return min(1.0, king_threat + exposed / 32)

    @staticmethod
    def move(values, probabilities):
        mean = sum(p * v for p, v in zip(probabilities, values))
        loss = sum(p for p, v in zip(probabilities, values) if v <= -1)
        downside = math.sqrt(sum(p * min(0, v - mean) ** 2
                                 for p, v in zip(probabilities, values)))
        return loss, downside


class TimeExpert:
    """Online EMA of seconds per visited node; branching projection is capped."""
    def __init__(self):
        self.seconds_per_node = 0.0005

    def forecast(self, board, depth):
        branch = max(1, len(fow_moves(board)))
        return self.seconds_per_node * min(1e6, sum(branch ** d for d in range(depth + 1)))

    def update(self, seconds, nodes):
        if nodes:
            self.seconds_per_node = 0.8 * self.seconds_per_node + 0.2 * seconds / nodes


class Mixture:
    """Four state distributions mixed by a contextual softmax gate.

    q_e(s) = softmax(log prior(s) + scale_e * feature_e(s)).
    Default zero scales retain the filtering prior, avoiding an unsupported
    assumption that strong/cheap positions are more likely to be real.
    """
    def __init__(self, scales=None, gate=None):
        self.scales = list(scales) if scales is not None else [0.0] * 4
        self.gate = gate if gate is not None else [[0.0] * 3 for _ in range(4)]
        if len(self.scales) != 4 or len(self.gate) != 4 or any(len(r) != 3 for r in self.gate):
            raise ValueError('Expected four scales and a 4 x 3 gate')
        if not all(math.isfinite(x) for x in self.scales + [x for row in self.gate for x in row]):
            raise ValueError('Mixture parameters must be finite')

    def components(self, features, prior, context):
        experts = [softmax([math.log(max(p, 1e-30)) + self.scales[e] * f[e]
                            for f, p in zip(features, prior)]) for e in range(4)]
        gate = softmax([sum(w * x for w, x in zip(row, context)) for row in self.gate])
        posterior = [sum(gate[e] * experts[e][i] for e in range(4)) for i in range(len(prior))]
        return posterior, gate, experts

    def fit_one(self, features, prior, context, target, rate=0.02):
        posterior, gate, experts = self.components(features, prior, context)
        probability = max(posterior[target], 1e-30)
        # Exact negative-log-likelihood gradients for a labeled retained state.
        for e in range(4):
            responsibility = gate[e] * experts[e][target] / probability
            mean = sum(p * f[e] for p, f in zip(experts[e], features))
            self.scales[e] -= rate * responsibility * (mean - features[target][e])
            for j in range(3):
                self.gate[e][j] -= rate * (gate[e] - responsibility) * context[j]
        return -math.log(probability)

    def save(self, path):
        with open(path, 'w') as stream:
            json.dump({'version': 1, 'scales': self.scales, 'gate': self.gate}, stream)

    @classmethod
    def load(cls, path):
        with open(path) as stream:
            data = json.load(stream)
        if data['version'] != 1:
            raise ValueError('Unsupported mixture version')
        return cls(data['scales'], data['gate'])


class Bot:
    def __init__(self, side, value=None, mixture=None, seed=0, depth=2,
                 robustness=0.35, temperature=0.08):
        self.side, self.depth = side, depth
        self.value, self.mixture = value or ValueExpert(), mixture or Mixture()
        self.information, self.risk, self.timing = InformationExpert(), RiskExpert(), TimeExpert()
        self.robustness, self.temperature = robustness, temperature
        self.rng = random.Random(seed)
        self.report = {}
        self.nodes = 0

    def features(self, boards, deadline):
        return [[self.value.evaluate(b, self.side, deadline),
                 self.information.state(b, self.side, deadline),
                 self.risk.state(b, self.side),
                 math.log1p(self.timing.forecast(b, self.depth))] for b in boards]

    def search(self, board, depth, alpha, beta, deadline, use_engine=True):
        if time.monotonic() >= deadline:
            raise Deadline
        self.nodes += 1
        terminal = terminal_value(board, self.side)
        if terminal is not None:
            return terminal
        if depth == 0:
            return (self.value.evaluate(board, self.side, deadline) if use_engine
                    else material_value(board, self.side))
        maximizing = board.turn == self.side
        best = -math.inf if maximizing else math.inf
        for move in ordered_moves(board):
            board.push(move)
            try:
                value = self.search(board, depth - 1, alpha, beta, deadline, use_engine)
            finally:
                board.pop()
            if maximizing:
                best, alpha = max(best, value), max(alpha, value)
            else:
                best, beta = min(best, value), min(beta, value)
            if alpha >= beta:
                break
        return best

    def choose(self, belief, legal, view, seconds):
        if not legal:
            return None
        capture_values = dict(zip('pnbrqk', [1, 3, 3, 5, 9, 100]))
        fallback = max(legal, key=lambda m: capture_values.get(view[m.to_square].lower(), 0)
                       + bool(m.promotion))
        self.report = {'mode': 'fallback', 'states': len(belief.boards), 'depth': 0}
        if not belief.boards or seconds <= 0:
            return fallback
        started = time.monotonic()
        deadline = started + seconds
        self.nodes = 0
        # Discard any hypothesis inconsistent with the exact observed action set.
        pairs = [(b, p) for b, p in zip(belief.boards, belief.weights) if set(fow_moves(b)) == set(legal)]
        if not pairs:
            return fallback
        boards, prior = map(list, zip(*pairs))
        total = sum(prior)
        prior = [p / total for p in prior]
        context = [1.0, entropy(prior) / max(1, math.log(len(prior))), min(1.0, seconds / 5)]
        completed = None
        try:
            features = self.features(boards, deadline)
            probabilities, gate, _ = self.mixture.components(features, prior, context)
            for depth in range(1, self.depth + 1):
                rows = []
                for move in legal:
                    values, children, costs = [], [], []
                    for board in boards:
                        child = board.copy()
                        child.push(move)
                        values.append(self.search(child, depth - 1, -math.inf, math.inf, deadline,
                                                  use_engine=depth > 1))
                        children.append(child)
                        costs.append(self.timing.forecast(child, self.depth))
                    gain, _ = self.information.partition(children, probabilities, self.side)
                    loss, downside = self.risk.move(values, probabilities)
                    expected = sum(p * v for p, v in zip(probabilities, values))
                    cost = sum(p * c for p, c in zip(probabilities, costs))
                    utility = ((1 - self.robustness) * expected + self.robustness * min(values)
                               + 0.05 * gain - 0.3 * loss - 0.15 * downside
                               - 0.01 * math.log1p(cost))
                    rows.append({'move': move.uci(), 'expected': expected, 'worst': min(values),
                                 'information_nats': gain, 'loss_probability': loss,
                                 'downside': downside, 'future_seconds': cost, 'utility': utility})
                if time.monotonic() >= deadline:
                    raise Deadline
                completed = rows
                self.report = {'mode': 'search', 'states': len(boards), 'depth': depth,
                               'posterior': probabilities, 'gate': gate, 'features': features,
                               'prior': prior, 'context': context, 'moves': rows}
        except Deadline:
            pass
        finally:
            self.timing.update(time.monotonic() - started, self.nodes)
        if completed is None:
            return fallback
        # Never randomize into a known forced loss if an alternative exists;
        # take a proven win across all retained states immediately.
        wins = [r for r in completed if r['worst'] == 1]
        safe = [r for r in completed if r['loss_probability'] == 0]
        choices = wins or safe or completed
        if self.temperature == 0:
            selected = max(choices, key=lambda r: r['utility'])
        else:
            weights = softmax([r['utility'] / self.temperature for r in choices])
            selected = self.rng.choices(choices, weights=weights, k=1)[0]
        return chess.Move.from_uci(selected['move'])
