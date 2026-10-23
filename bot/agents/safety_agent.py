"""Safety agents: never make a known-losing move, then order by material and exposure.

All registry variants are this one class with a different sort key and,
optionally, a possibility tracker as the exposure source.
"""
from __future__ import annotations

import time

import chess

from bot.agent import Agent, NoLegalMoves
from bot.possibility import ALL_TYPES, PossibilityTracker
from bot.safety import SafetyReport, apply_move, attackers_of, king_safety

# The king is 0: walking into a known attack is already a known loss.
VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}

# Sort-key terms (smaller is better); rng.random() is always appended last.
#   known_loss: report.known_loss          exposure: len(report.exposed)
#   exposed:    bool(report.exposed)       material: -material_score(move)
COUNT_FIRST = ("known_loss", "exposure", "material")      # Step 1 "safety"
BINARY_FIRST = ("known_loss", "exposed", "material")      # Step 1 "safety_binary"
MATERIAL_FIRST = ("known_loss", "material", "exposure")   # "safety_v2"
MATERIAL_ONLY = ("known_loss", "material")                # "safe_material" control


def material_score(obs: str, cells: list[str], move: chess.Move, side: chess.Color) -> int:
    """Integer material gain of ``move`` judged from visible pieces only.

    +10 x captured value (en passant captures a pawn), +5 x promotion value,
    and -10 x the value of the piece now on ``to`` if a visible enemy piece
    attacks that square after the move (crude trade check). For promotions
    that is the promoted piece, since that is what would be lost.
    """
    score = 0
    target = obs[move.to_square]
    if target not in "?-":
        score += 10 * VALUES[target.lower()]
    elif (obs[move.from_square].lower() == "p"
          and chess.square_file(move.from_square) != chess.square_file(move.to_square)):
        score += 10 * VALUES["p"]
    if move.promotion:
        score += 5 * VALUES[chess.piece_symbol(move.promotion)]
    known, _ = attackers_of(cells, move.to_square, side)
    if known:
        score -= 10 * VALUES[cells[move.to_square].lower()]
    return score


class SafetyAgent(Agent):
    """Choose the legal move with the smallest key ``key_terms + (rng.random(),)``.

    Makes exactly one ``rng.random()`` call per legal move, in tracker order.
    With ``tracked`` the exposure comes from a ``PossibilityTracker`` updated
    on every observation; otherwise every '?' may hold any piece (Step 1).
    After each choice ``last_decision`` holds the chosen move and report, the
    number of legal and non-losing moves, the minimum exposure over all moves
    and over non-losing moves (None if none), the possible types on each
    exposed square, tracker resets and precision, and tracker update times
    since the previous decision.
    """

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None,
                 strict: bool = False, *, key: tuple[str, ...] = COUNT_FIRST, tracked: bool = False):
        super().__init__(side, base, increment, seed, strict)
        self.key_terms = key
        self.possibility = PossibilityTracker(side, strict=strict) if tracked else None
        self.update_seconds: list[float] = []
        self.last_decision: dict | None = None

    def observe(self, obs: str) -> None:
        super().observe(obs)
        if self.possibility is not None:
            started = time.perf_counter()
            self.possibility.on_observation(obs, self.ply, self.last_move, self.tracker.previous)
            self.update_seconds.append(time.perf_counter() - started)

    def _select(self, remaining: float) -> chess.Move:
        obs = self.tracker.current
        moves = self.tracker.legal_moves()
        if not moves:
            raise NoLegalMoves()
        scored = []
        for move in moves:
            cells = apply_move(obs, move, self.side)
            report = king_safety(cells, self.side, self.possibility)
            terms = {"known_loss": report.known_loss, "exposure": len(report.exposed),
                     "exposed": bool(report.exposed)}
            if "material" in self.key_terms:
                terms["material"] = -material_score(obs, cells, move, self.side)
            key = tuple(terms[name] for name in self.key_terms) + (self.rng.random(),)
            scored.append((key, move, report))
        _, move, report = min(scored, key=lambda item: item[0])
        safe_exposures = [len(r.exposed) for _, _, r in scored if not r.known_loss]
        self.last_decision = {
            "move": move,
            "report": report,
            "legal_moves": len(moves),
            "non_losing_moves": len(safe_exposures),
            "min_exposure": min(len(r.exposed) for _, _, r in scored),
            "min_safe_exposure": min(safe_exposures, default=None),
            "exposed_types": self._exposed_types(report),
            "tracker": self._tracker_stats(obs),
            "update_seconds": self.update_seconds,
        }
        self.update_seconds = []
        return move

    def _exposed_types(self, report: SafetyReport) -> dict[str, str]:
        """Possible enemy types on each exposed square (all six without a tracker).

        A visible attacker behind a '?' (tracker mode) is listed with its own type.
        """
        obs = self.tracker.current
        types = {}
        for square in sorted(report.exposed):
            if obs[square] != "?":
                possible = frozenset(obs[square].upper())
            elif self.possibility is None:
                possible = ALL_TYPES
            else:
                possible = self.possibility.possible_types_at(square)
            types[chess.square_name(square)] = "".join(sorted(possible))
        return types

    def _tracker_stats(self, obs: str) -> dict | None:
        if self.possibility is None:
            return None
        hyps = self.possibility.hyps
        unknown = [square for square, char in enumerate(obs) if char == "?"]
        queen = sum("Q" in self.possibility.possible_types_at(square) for square in unknown)
        return {
            "resets": self.possibility.resets,
            "hypotheses": len(hyps),
            "mean_support": sum(chess.popcount(h.squares) for h in hyps) / max(len(hyps), 1),
            "queen_fraction": queen / max(len(unknown), 1),
        }
