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
    - ``observe`` is called exactly once before every ply (both sides get
      every observation), so ``self.ply`` is the index of the ply about to
      be played; ply p is ours iff (p % 2 == 0) == (side == WHITE).
    - ``choose_move`` is called only on our plies, after ``observe``, and
      records the returned move (tracker + ``last_move``) before returning.
      Subclasses implement ``_select`` only.
    - All randomness comes from ``self.rng``.
    - ``strict`` is set by the harness so internal inconsistencies raise;
      the arena leaves it False so the bot degrades instead of crashing.
    """

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None,
                 strict: bool = False):
        self.side = side
        self.base = base
        self.increment = increment
        self.strict = strict
        self.rng = random.Random(seed)
        self.tracker = ObservationTracker(side)
        self.ply = -1
        self.last_move: chess.Move | None = None

    def observe(self, obs: str) -> None:
        """Record the latest observation (validated by the tracker)."""
        self.tracker.observe(obs)
        self.ply += 1

    def choose_move(self, remaining: float) -> chess.Move:
        """Pick a move with ``remaining`` seconds on our clock and record it."""
        assert (self.ply % 2 == 0) == (self.side == chess.WHITE), f"ply {self.ply} is not ours"
        move = self._select(remaining)
        self.record(move)
        return move

    def record(self, move: chess.Move) -> None:
        """Note that we played ``move`` (also used by the protocol's fallback)."""
        self.tracker.record_move(move)
        self.last_move = move

    def _select(self, remaining: float) -> chess.Move:
        """Return the move to play; raise ``NoLegalMoves`` if there is none."""
        raise NotImplementedError
