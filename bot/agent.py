"""Agent base class shared by the arena protocol and the in-process harness."""
from __future__ import annotations

import random

import chess

from bot.tracker import ObservationTracker


class NoLegalMoves(Exception):
    """Raised by ``choose_move`` when the agent sees no legal move.

    The subprocess starters simply exit in this case, so the referee records
    "Bot exited"; the harness and protocol mirror that.
    """


class Agent:
    """One side of one game. Sees only observation strings and its own clock.

    Invariants:
    - ``observe`` may be called any number of times between moves (the
      referee sends an observation to both sides before every ply).
    - ``choose_move`` is called only on our turn, after at least one
      ``observe``, and records the returned move in the tracker before
      returning it. Subclasses implement ``_select`` only.
    - All randomness comes from ``self.rng``.
    """

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None):
        self.side = side
        self.base = base
        self.increment = increment
        self.rng = random.Random(seed)
        self.tracker = ObservationTracker(side)

    def observe(self, obs: str) -> None:
        """Record the latest observation (validated by the tracker)."""
        self.tracker.observe(obs)

    def choose_move(self, remaining: float) -> chess.Move:
        """Pick a move with ``remaining`` seconds on our clock and record it."""
        move = self._select(remaining)
        self.tracker.record_move(move)
        return move

    def _select(self, remaining: float) -> chess.Move:
        """Return the move to play; raise ``NoLegalMoves`` if there is none."""
        raise NotImplementedError
