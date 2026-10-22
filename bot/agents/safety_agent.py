"""Safety agent: never make a known-losing move, minimize hidden exposure, then grab material."""
from __future__ import annotations

import chess

from bot.agent import Agent, NoLegalMoves
from bot.safety import SafetyReport, apply_move, attackers_of, king_safety

# The king is 0: walking into a known attack is already a known loss.
VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}


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
    """Choose the legal move minimizing (known_loss, exposure, -material, rng.random()).

    Makes exactly one ``rng.random()`` call per legal move, in tracker order.
    After each choice ``last_decision`` holds the chosen move, its report,
    the number of legal and non-losing moves, the minimum exposure over all
    moves, and the minimum over non-losing moves (None if there are none).
    """

    exposure_mode = "count"

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None):
        super().__init__(side, base, increment, seed)
        self.last_decision: dict | None = None

    def exposure_term(self, report: SafetyReport) -> int:
        if self.exposure_mode == "binary":
            return 0 if not report.exposed else 1
        return len(report.exposed)

    def _select(self, remaining: float) -> chess.Move:
        obs = self.tracker.current
        moves = self.tracker.legal_moves()
        if not moves:
            raise NoLegalMoves()
        scored = []
        for move in moves:
            cells = apply_move(obs, move, self.side)
            report = king_safety(cells, self.side)
            key = (report.known_loss, self.exposure_term(report),
                   -material_score(obs, cells, move, self.side), self.rng.random())
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
        }
        return move


class SafetyBinaryAgent(SafetyAgent):
    """Ablation: exposure only matters as exposed vs not exposed."""

    exposure_mode = "binary"
