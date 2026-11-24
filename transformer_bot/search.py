"""Particle filtering and alpha-beta determinization, not an equilibrium solver."""
from collections import Counter
import math
import random
import time

import chess

from referee import FowBoard, fow_moves, observation, outcome, position_key


class Belief:
    """Keep a bounded uniform sample of distinct histories consistent with views.

    Starts from the known initial board. Unobserved opponent moves are expanded
    uniformly; this is an approximate prior, not a learned opponent model.
    A larger reserve preserves alternatives to the boards used by search.
    On depletion, bounded replay from the initial position tries to recover
    histories consistent with EVERY observation and known own action.
    """
    def __init__(self, side, capacity=16, seed=0, reserve=32, recovery_seconds=0.2):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.side, self.capacity = side, capacity
        self.rng = random.Random(seed)
        self.boards = [FowBoard()]
        self.pool = list(self.boards)
        self.reserve = max(capacity, reserve)
        self.recovery_seconds = recovery_seconds
        self.evidence = []
        self.recoveries = 0
        self.recovery_attempts = 0
        self.started = False
        self.pending = None

    def _advance(self, boards, view, own_move, initial, capacity, deadline=None):
        survivors, seen = [], 0
        for board in boards:
            if deadline is not None and time.monotonic() >= deadline:
                raise SearchTimeout
            if initial:
                children = [board]
            else:
                moves = ([own_move] if board.turn == self.side
                         and own_move is not None else
                         [] if board.turn == self.side else fow_moves(board))
                children = []
                for move in moves:
                    if move not in fow_moves(board):
                        continue
                    child = board.copy()
                    child.push(move)
                    children.append(child)
            for child in children:
                if deadline is not None and time.monotonic() >= deadline:
                    raise SearchTimeout
                if observation(child, self.side) != view:
                    continue
                # A delivered observation proves play has not terminated.
                if outcome(child, repetition_counts(child)) is not None:
                    continue
                # Reservoir sampling bounds memory without depending on move order.
                seen += 1
                if len(survivors) < capacity:
                    survivors.append(child)
                else:
                    index = self.rng.randrange(seen)
                    if index < capacity:
                        survivors[index] = child
        return survivors

    def observe(self, view):
        self.evidence.append((view, self.pending))
        self.pool = self._advance(self.pool, view, self.pending, not self.started, self.reserve)
        if not self.pool and self.recovery_seconds > 0:
            self.recovery_attempts += 1
            deadline = time.monotonic() + self.recovery_seconds
            try:
                # Resampling can recover previously discarded branches. Never
                # return a partially replayed board after the deadline.
                while time.monotonic() < deadline and not self.pool:
                    recovered = [FowBoard()]
                    for index, (old_view, move) in enumerate(self.evidence):
                        recovered = self._advance(recovered, old_view, move, index == 0,
                                                  self.reserve * 4, deadline)
                        if not recovered:
                            break
                    if recovered:
                        self.pool = self.rng.sample(recovered, min(self.reserve, len(recovered)))
                        self.recoveries += 1
            except SearchTimeout:
                pass
        self.boards = self.rng.sample(self.pool, min(self.capacity, len(self.pool)))
        self.started = True
        self.pending = None

    def record_move(self, move):
        self.pending = move


class SearchTimeout(Exception):
    pass


def repetition_counts(board):
    copy = board.copy()
    counts = Counter([position_key(copy)])
    while copy.move_stack:
        copy.pop()
        counts[position_key(copy)] += 1
    return counts


def material_value(board, side):
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2,
              chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
    total = sum(value * (len(board.pieces(piece, side)) -
                         len(board.pieces(piece, not side)))
                for piece, value in values.items())
    return math.tanh(total / 12)


def ordered_moves(board):
    def priority(move):
        victim = board.piece_at(move.to_square)
        return (100 if victim and victim.piece_type == chess.KING else 0,
                bool(victim) or board.is_en_passant(move), bool(move.promotion))
    return sorted(fow_moves(board), key=priority, reverse=True)


def choose_move(boards, legal, history, side, evaluate, policy_scores=None,
                max_depth=2, seconds=0.5):
    """Average root scores across particles; alpha-beta inside each full board.

    Only complete iterations replace the fallback, avoiding partial-root bias.
    evaluate(history, side, board) returns a value from the observer's perspective.
    """
    if not legal:
        return None
    scores = policy_scores or {}
    roots = sorted(legal, key=lambda move: scores.get(move, 0), reverse=True)
    best = roots[0]
    if not boards:
        return best
    deadline = time.monotonic() + max(0, seconds)

    def check_time():
        if time.monotonic() >= deadline:
            raise SearchTimeout

    def search(board, depth, alpha, beta, prefix, counts):
        check_time()
        terminal = outcome(board, counts)
        if terminal:
            result = terminal[0]
            return 0.0 if result == "1/2-1/2" else (
                1.0 if (result == "1-0") == side else -1.0)
        if depth == 0:
            # Keep learned/heuristic leaves strictly inside terminal win/loss.
            value = max(-0.99, min(0.99, float(evaluate(prefix, side, board))))
            check_time()
            return value
        maximizing = board.turn == side
        value = -math.inf if maximizing else math.inf
        for move in ordered_moves(board):
            board.push(move)
            key = position_key(board)
            counts[key] += 1
            try:
                child_history = prefix + [(observation(board, side), board.turn)]
                child = search(board, depth - 1, alpha, beta, child_history, counts)
            finally:
                counts[key] -= 1
                board.pop()
            if maximizing:
                value, alpha = max(value, child), max(alpha, child)
            else:
                value, beta = min(value, child), min(beta, child)
            if alpha >= beta:
                break
        return value

    counts_by_board = [repetition_counts(board) for board in boards]
    for depth in range(1, max_depth + 1):
        values = {}
        try:
            for move in roots:
                total = 0.0
                for board, counts in zip(boards, counts_by_board):
                    check_time()
                    if move not in fow_moves(board):
                        raise ValueError("Belief board disagrees with legal root moves")
                    board.push(move)
                    key = position_key(board)
                    counts[key] += 1
                    try:
                        prefix = history + [(observation(board, side), board.turn)]
                        total += search(board, depth - 1, -math.inf, math.inf, prefix, counts)
                    finally:
                        counts[key] -= 1
                        board.pop()
                values[move] = total / len(boards)
        except SearchTimeout:
            break
        best = max(roots, key=values.get)
        roots.sort(key=values.get, reverse=True)
    return best
