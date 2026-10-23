"""Observation-only king-safety check: a sound over-approximation of capture risk.

Every non-'?' character of the current observation is accurate at our
decision time, and enemy pieces do not move between our move and the
referee's king-capture check. So scanning the post-move squares from our
king, treating each '?' as possibly any enemy piece, never misses a real
attacker: a hidden attacker either sits on a '?' that the scan reports, or
its line to our king passes through a '?' that the scan reports first.
An optional possibility tracker narrows which '?' squares can attack.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess

ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def _ray(square: int, file_step: int, rank_step: int) -> tuple[int, ...]:
    """Squares from ``square`` outward (excluding it) until the board edge."""
    file, rank = chess.square_file(square) + file_step, chess.square_rank(square) + rank_step
    squares = []
    while 0 <= file < 8 and 0 <= rank < 8:
        squares.append(chess.square(file, rank))
        file, rank = file + file_step, rank + rank_step
    return tuple(squares)


# RAYS[sq] holds (is_diagonal, rank_step, squares) for each of the 8 directions.
RAYS = tuple(
    tuple((file_step != 0 and rank_step != 0, rank_step, _ray(square, file_step, rank_step))
          for file_step, rank_step in ORTHOGONAL + DIAGONAL)
    for square in chess.SQUARES)
KNIGHT_SQUARES = tuple(tuple(chess.SquareSet(chess.BB_KNIGHT_ATTACKS[square]))
                       for square in chess.SQUARES)


@dataclass(frozen=True)
class SafetyReport:
    known_loss: bool                 # a visible enemy piece attacks our king after the move
    exposed: frozenset[int]          # '?' squares that could hold an attacker of our king (with a
                                     # tracker, also visible attackers whose line crosses a '?')
    king_square: int


def apply_move(obs: str, move: chess.Move, side: chess.Color) -> list[str]:
    """Return the 64-char array after our move, from our perspective.

    Derived only from the observation and the move: castling also moves the
    rook, en passant also empties the captured pawn's square, promotion
    places the promoted piece. ``move`` must come from the tracker's legal
    moves, so ``from`` holds our piece and ``to`` is not '?'.
    """
    cells = list(obs)
    piece = cells[move.from_square]
    assert piece not in "?-" and piece.isupper() == side, f"{move} does not move our piece"
    assert cells[move.to_square] != "?", f"{move} lands on an unseen square"
    moved = piece
    if move.promotion:
        symbol = chess.piece_symbol(move.promotion)
        moved = symbol.upper() if side else symbol
    from_file, to_file = chess.square_file(move.from_square), chess.square_file(move.to_square)
    if piece.lower() == "k" and abs(to_file - from_file) == 2:
        rank = chess.square_rank(move.from_square)
        rook_from, rook_to = ((chess.square(7, rank), chess.square(5, rank)) if to_file > from_file
                              else (chess.square(0, rank), chess.square(3, rank)))
        assert cells[rook_from] == ("R" if side else "r"), f"{move} castles without a rook"
        cells[rook_to], cells[rook_from] = cells[rook_from], "-"
    elif piece.lower() == "p" and from_file != to_file and cells[move.to_square] == "-":
        cells[move.to_square - 8 if side else move.to_square + 8] = "-"
    cells[move.from_square] = "-"
    cells[move.to_square] = moved
    return cells


def attacks_along(kind: str, diagonal: bool, distance: int, rank_step: int, pawn_step: int) -> bool:
    """Does an enemy piece of ``kind`` (any case) attack along this ray at this distance?

    ``rank_step`` is the ray's rank direction from the target; ``pawn_step``
    is the rank step from a target to an enemy pawn that attacks it.
    """
    kind = kind.lower()
    return (kind == "q" or kind == ("b" if diagonal else "r")
            or (distance == 1 and (kind == "k" or (kind == "p" and diagonal and rank_step == pawn_step))))


def attackers_of(cells: list[str], square: int, side: chess.Color,
                 tracker=None) -> tuple[list[int], list[int]]:
    """Return (known enemy attacker squares, possible '?' attacker squares) for any square.

    Known attackers are visible enemy pieces whose type attacks ``square``
    along an all-'-' line. Each square appears at most once.

    ``tracker=None`` (Step 1): every '?' may hold any enemy piece; possible
    attackers are '?' squares at a knight offset or first along a ray, and
    the scan stops at any '?' or piece.

    With a ``PossibilityTracker``: a '?' is a possible attacker only if some
    type possible there attacks along this ray at this distance (or is a
    knight, at a knight offset). A ray stops at our pieces, visible enemy
    pieces, possible attackers and certainly occupied squares, and continues
    through other '?' squares (which may be empty). A visible enemy attacker
    behind such a '?' is only possible (its square is reported as possible),
    since the '?' may block it; so ``known`` stays exact. Sound as long as the
    tracker is: a real attacker's line is truly empty, so the scan reaches it.
    Stopping at a flagged '?' keeps the report identical to Step 1's when
    every type is possible everywhere.
    """
    own = str.isupper if side else str.islower
    enemy_knight = "n" if side else "N"
    # Rank step from the target to an enemy pawn that attacks it: Black pawns
    # attack downward, so they sit one rank above what they attack.
    enemy_pawn_step = 1 if side else -1
    occupied = tracker.certainly_occupied() if tracker is not None else 0
    known, possible = [], []
    for other in KNIGHT_SQUARES[square]:
        char = cells[other]
        if char == enemy_knight:
            known.append(other)
        elif char == "?" and (tracker is None or "N" in tracker.possible_types_at(other)):
            possible.append(other)
    for diagonal, rank_step, ray in RAYS[square]:
        behind_unknown = False
        for distance, other in enumerate(ray, 1):
            char = cells[other]
            if char == "-":
                continue
            if char == "?":
                if tracker is None or any(attacks_along(kind, diagonal, distance, rank_step, enemy_pawn_step)
                                          for kind in tracker.possible_types_at(other)):
                    possible.append(other)
                    break
                if occupied & chess.BB_SQUARES[other]:
                    break
                behind_unknown = True
                continue
            if not own(char) and attacks_along(char, diagonal, distance, rank_step, enemy_pawn_step):
                # Behind a '?' the line may be blocked, so the attack is only possible.
                (possible if behind_unknown else known).append(other)
            break
    return known, possible


def king_safety(cells: list[str], side: chess.Color, tracker=None) -> SafetyReport:
    """Scan from our king; see ``attackers_of``."""
    king_square = cells.index("K" if side else "k")
    known, possible = attackers_of(cells, king_square, side, tracker)
    return SafetyReport(bool(known), frozenset(possible), king_square)
