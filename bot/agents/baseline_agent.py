"""Port of the starter ``baseline.py``, including its missing en passant."""
from __future__ import annotations

import chess

from bot.agent import Agent, NoLegalMoves
from referee import FowBoard, fow_moves


def candidates(observation, side, rights):
    """Copied verbatim from ``baseline.py``: visible-only board and moves.

    Unlike ``bot.tracker.candidates`` this never generates en passant and
    does not mask castling through unseen squares.
    """
    board = FowBoard(None)
    board.turn = side
    for square, char in enumerate(observation):
        if char not in '?-':
            board.set_piece_at(square, chess.Piece.from_symbol(char))
    board.castling_rights = rights
    result = []
    for move in fow_moves(board):
        if observation[move.to_square] == '?':
            continue
        piece = board.piece_at(move.from_square)
        if piece.piece_type != chess.KNIGHT:
            if any(observation[sq] == '?' for sq in chess.SquareSet(chess.between(move.from_square, move.to_square))):
                continue
        result.append(move)
    return board, result


VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


class BaselineAgent(Agent):
    """Greedy capture/promotion scorer with ``rng.random()`` tie-breaking.

    Castling rights come from the shared tracker, whose update rules are
    identical to ``baseline.py``'s. The starter's ``--seed`` defaults to 1, so
    ``seed=None`` means 1 here too. ``max`` evaluates the key once per move
    in list order, giving the same RNG call sequence as the starter.
    """

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None,
                 strict: bool = False):
        super().__init__(side, base, increment, 1 if seed is None else seed, strict)

    def _select(self, remaining: float) -> chess.Move:
        board, moves = candidates(self.tracker.current, self.side, self.tracker.rights)
        if not moves:
            raise NoLegalMoves()

        def score(move):
            target = board.piece_at(move.to_square)
            value = VALUES[target.piece_type] * 10 if target else 0
            if move.promotion:
                value += VALUES[move.promotion] * 5
            return value + self.rng.random()
        return max(moves, key=score)
