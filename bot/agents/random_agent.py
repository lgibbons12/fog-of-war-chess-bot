"""Port of the starter ``uniform_random.py``."""
from __future__ import annotations

import chess

from bot.agent import Agent, NoLegalMoves


class RandomAgent(Agent):
    """Uniform choice over the tracker's exact legal moves.

    Makes exactly one ``rng.choice`` call per move, like the starter, so a
    given seed reproduces the starter's games move for move.
    """

    def _select(self, remaining: float) -> chess.Move:
        moves = self.tracker.legal_moves()
        if not moves:
            raise NoLegalMoves()
        return self.rng.choice(moves)
