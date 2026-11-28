"""Observation-only tactical and belief-search opponents shared by training/evaluation."""
import argparse
import random
import sys

import chess
from uniform_random import ObservationTracker, candidates, OBSERVATION_CHARACTERS
from .search import Belief, choose_move, material_value


def tactical_scores(tracker, legal, rng):
    board, _ = candidates(tracker.current, tracker.side, tracker.rights, tracker.previous)
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
    scores = {}
    for move in legal:
        victim = board.piece_at(move.to_square)
        capture = values[victim.piece_type] if victim else 0
        if board.is_en_passant(move):
            capture = 1
        board.push(move)
        king = board.king(tracker.side)
        unsafe = king is None or board.is_attacked_by(not tracker.side, king)
        piece = board.piece_at(move.to_square)
        exposed = board.is_attacked_by(not tracker.side, move.to_square)
        scores[move] = (-1000 * unsafe + 10 * capture
                        + (values[move.promotion] - 1 if move.promotion else 0)
                        - (values[piece.piece_type] if exposed else 0) + rng.random() * 0.01)
        board.pop()
    return scores


class Opponent:
    def __init__(self, side, kind="tactical", seed=0, seconds=0.03):
        self.kind, self.seconds = kind, seconds
        self.rng = random.Random(seed)
        self.belief = Belief(side, capacity=2, reserve=8, seed=seed, recovery_seconds=0)

    def observe(self, view):
        if self.kind == "search":
            self.belief.observe(view)

    def choose(self, tracker, history, legal):
        scores = tactical_scores(tracker, legal, self.rng)
        if self.kind == "tactical":
            return max(legal, key=scores.get)
        return choose_move(self.belief.boards, legal, history, tracker.side,
                           lambda h, s, b: material_value(b, s), scores, 2, self.seconds)

    def record_move(self, move):
        self.belief.record_move(move)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["tactical", "search"], default="tactical")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=0.03)
    args = parser.parse_args()
    if input().strip() != "fow":
        return
    side = input().split()[0] == "w"
    tracker = ObservationTracker(side)
    agent = Opponent(side, args.kind, args.seed, args.seconds)
    history, ply = [], 0
    print("ready", flush=True)
    for raw in sys.stdin:
        line = raw.strip()
        if len(line) == 64 and set(line) <= OBSERVATION_CHARACTERS:
            tracker.observe(line)
            agent.observe(line)
            history = (history + [(line, ply % 2 == 0)])[-4:]
            ply += 1
            continue
        float(line)
        legal = tracker.legal_moves()
        if not legal:
            return
        move = agent.choose(tracker, history, legal)
        tracker.record_move(move)
        agent.record_move(move)
        print("move " + move.uci(), flush=True)


if __name__ == "__main__":
    main()
