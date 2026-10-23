"""History-based, sound possibility tracker over enemy pieces.

One hypothesis per enemy piece (an identity, not a type): the set of types
it might be and the bitboard of squares it might be on.

Soundness invariant (blocking): after every observation there is a one-to-
one assignment of the true enemy pieces to hypotheses with each piece's
square in its hypothesis's ``squares`` and its type in ``types``. The number
of hypotheses always equals the number of enemy pieces (captures are always
visible to us). The tracker may be imprecise; it never excludes the truth.

Per observation p (ply p is ours iff (p % 2 == 0) == (side == WHITE)):
- the first observation: filter only;
- ply p-1 was ours: remove what our move captured, then filter;
- ply p-1 was theirs: expand every hypothesis by one move, then filter.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

import chess

ALL_TYPES = frozenset("PNBRQK")
PROMOTION_TYPES = frozenset("NBRQ")
ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
SLIDES = {"R": ORTHOGONAL, "B": DIAGONAL, "Q": ORTHOGONAL + DIAGONAL}
START_TYPES = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B",
               chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}


def _ray(square: int, file_step: int, rank_step: int) -> tuple[int, ...]:
    file, rank = chess.square_file(square) + file_step, chess.square_rank(square) + rank_step
    squares = []
    while 0 <= file < 8 and 0 <= rank < 8:
        squares.append(chess.square(file, rank))
        file, rank = file + file_step, rank + rank_step
    return tuple(squares)


RAYS = {kind: tuple(tuple(_ray(square, df, dr) for df, dr in directions) for square in chess.SQUARES)
        for kind, directions in SLIDES.items()}


def _bits(bitboard: int):
    return chess.scan_forward(bitboard)


def _single(bitboard: int) -> bool:
    return bitboard != 0 and bitboard & (bitboard - 1) == 0


class TrackerInconsistency(Exception):
    """The observations contradict the tracker. Under soundness this is a bug."""


@dataclass
class EnemyPiece:
    types: frozenset[str]     # subset of {"P","N","B","R","Q","K"}
    squares: int              # bitboard (python int, chess.BB_* convention)


class PossibilityTracker:
    """Factored possibility state for the enemy pieces, seen from ``side``.

    ``strict`` raises ``TrackerInconsistency``; otherwise an inconsistency is
    logged to stderr and the state resets to a coarse but sound one (counted
    in ``resets``). ``pieces`` overrides the 16 exact starting hypotheses
    (used by tests that start from a FEN).
    """

    def __init__(self, side: chess.Color, strict: bool = True,
                 pieces: list[EnemyPiece] | None = None):
        self.side = side
        self.enemy = not side
        self.strict = strict
        self.resets = 0
        if pieces is None:
            start = chess.Board()
            pieces = [EnemyPiece(frozenset(START_TYPES[start.piece_type_at(square)]), chess.BB_SQUARES[square])
                      for square in chess.SquareSet(start.occupied_co[self.enemy])]
        self.hyps = [EnemyPiece(piece.types, piece.squares) for piece in pieces]
        self.count = len(self.hyps)
        self.visible_enemy = 0
        self.observed = False
        self._types_cache: list[frozenset[str]] | None = None
        # Geometry of the enemy's pawns and castling, from our point of view.
        self.pawn_step = 8 if self.enemy == chess.WHITE else -8
        self.pawn_start_rank = 1 if self.enemy == chess.WHITE else 6
        self.promotion_rank = 7 if self.enemy == chess.WHITE else 0
        back = 0 if self.enemy == chess.WHITE else 7
        self.king_start = chess.square(4, back)
        # (rook start, king target, rook target, squares that must be empty)
        self.castles = [
            (chess.square(7, back), chess.square(6, back), chess.square(5, back),
             chess.BB_SQUARES[chess.square(5, back)] | chess.BB_SQUARES[chess.square(6, back)]),
            (chess.square(0, back), chess.square(2, back), chess.square(3, back),
             chess.BB_SQUARES[chess.square(1, back)] | chess.BB_SQUARES[chess.square(2, back)]
             | chess.BB_SQUARES[chess.square(3, back)]),
        ]

    # ----- public queries -------------------------------------------------

    def pieces(self) -> list[EnemyPiece]:
        """Copies of the current hypotheses."""
        return [EnemyPiece(h.types, h.squares) for h in self.hyps]

    def possible_types_at(self, sq: int) -> frozenset[str]:
        """Union of the types of every hypothesis that may be on ``sq``."""
        if self._types_cache is None:
            cache = [frozenset()] * 64
            for h in self.hyps:
                for square in _bits(h.squares):
                    cache[square] = cache[square] | h.types
            self._types_cache = cache
        return self._types_cache[sq]

    def certainly_occupied(self) -> int:
        """Bitboard of squares definitely holding an enemy piece.

        Visible enemy pieces, plus singleton supports: hypotheses and enemy
        pieces are in bijection, so a one-square hypothesis is really there.
        """
        occupied = self.visible_enemy
        for h in self.hyps:
            if _single(h.squares):
                occupied |= h.squares
        return occupied

    # ----- updates ----------------------------------------------------------

    def on_observation(self, obs: str, ply: int, our_last_move: chess.Move | None,
                       prev_obs: str | None) -> None:
        """Advance to observation ``ply``.

        ``our_last_move`` is our most recent move (None before we have moved);
        ``prev_obs`` is observation ``ply - 1``.
        """
        self._types_cache = None
        try:
            if self.observed:
                if ((ply - 1) % 2 == 0) == (self.side == chess.WHITE):
                    self._apply_our_move(our_last_move, prev_obs)
                else:
                    self._opponent_ply(obs, prev_obs, our_last_move)
            self._filter(obs)
        except TrackerInconsistency as error:
            if self.strict:
                raise TrackerInconsistency(f"ply {ply}: {error}; obs {obs}") from None
            print(f"possibility tracker reset at ply {ply}: {error}", file=sys.stderr, flush=True)
            self._reset(obs)
        self.observed = True
        self._types_cache = None

    def _ours(self, char: str) -> bool:
        return char not in "?-" and char.isupper() == (self.side == chess.WHITE)

    def _theirs(self, char: str) -> bool:
        return char not in "?-" and char.isupper() != (self.side == chess.WHITE)

    def _reset(self, obs: str) -> None:
        """Coarse but sound: every enemy piece may be anything on any '?' or visible enemy square."""
        squares = 0
        for square, char in enumerate(obs):
            if char == "?" or self._theirs(char):
                squares |= chess.BB_SQUARES[square]
        self.hyps = [EnemyPiece(ALL_TYPES, squares) for _ in range(self.count)]
        self.visible_enemy = sum(chess.BB_SQUARES[sq] for sq, char in enumerate(obs) if self._theirs(char))
        self.resets += 1

    # Our move ---------------------------------------------------------------

    def _apply_our_move(self, move: chess.Move | None, prev_obs: str | None) -> None:
        """Remove the enemy piece our move captured, if any (captures are always visible)."""
        if move is None or prev_obs is None:
            return
        target = prev_obs[move.to_square]
        if self._theirs(target):
            self.count -= 1
            self._remove_captured(target.upper(), move.to_square)
        elif (prev_obs[move.from_square].upper() == "P"
              and chess.square_file(move.from_square) != chess.square_file(move.to_square)):
            self.count -= 1
            captured = move.to_square - 8 if self.side == chess.WHITE else move.to_square + 8
            self._remove_captured("P", captured)

    def _remove_captured(self, kind: str, square: int) -> None:
        """Delete the captured piece's hypothesis; merge k > 1 candidates into k - 1."""
        bit = chess.BB_SQUARES[square]
        candidates = [i for i, h in enumerate(self.hyps) if kind in h.types and h.squares & bit]
        if not candidates:
            raise TrackerInconsistency(f"no hypothesis for captured {kind} on {chess.square_name(square)}")
        others = [h for i, h in enumerate(self.hyps) if i not in candidates]
        if len(candidates) > 1:
            types = frozenset().union(*(self.hyps[i].types for i in candidates))
            squares = 0
            for i in candidates:
                squares |= self.hyps[i].squares
            squares &= ~bit
            others += [EnemyPiece(types, squares) for _ in range(len(candidates) - 1)]
        self.hyps = others

    # Opponent ply -------------------------------------------------------------

    def _opponent_ply(self, obs: str, prev_obs: str, our_last_move: chess.Move | None) -> None:
        """Expand every hypothesis by one possible enemy move."""
        lost = [sq for sq in chess.SQUARES if self._ours(prev_obs[sq]) and prev_obs[sq] != obs[sq]]
        if len(lost) > 1:
            raise TrackerInconsistency(f"several of our pieces vanished: {lost}")
        blockers = 0
        for square, char in enumerate(prev_obs):
            if char not in "?-":
                blockers |= chess.BB_SQUARES[square]
        for h in self.hyps:
            if _single(h.squares):
                blockers |= h.squares
        if lost:
            self._expand_capture(lost[0], blockers, prev_obs, our_last_move)
        else:
            self._expand_quiet(blockers)

    def _expand_quiet(self, blockers: int) -> None:
        """Non-capture ply: each hypothesis independently may have made any quiet move.

        Quiet moves never land on a blocker (an occupied square), so blocker
        squares are excluded from the reach as well as stopping slides.
        """
        updates = []
        for h in self.hyps:
            reach, promoted = 0, False
            for square in _bits(h.squares):
                for kind in h.types:
                    if kind == "N":
                        reach |= chess.BB_KNIGHT_ATTACKS[square] & ~blockers
                    elif kind == "K":
                        reach |= chess.BB_KING_ATTACKS[square] & ~blockers
                    elif kind == "P":
                        pushes = self._pawn_pushes(square, blockers)
                        reach |= pushes
                        promoted |= bool(pushes & chess.BB_RANKS[self.promotion_rank])
                    else:
                        reach |= self._slide(square, kind, blockers)
            updates.append((reach, promoted))
        castle_king, castle_rook = self._castling(blockers)
        for i, (h, (reach, promoted)) in enumerate(zip(self.hyps, updates)):
            h.squares |= reach | castle_king[i] | castle_rook[i]
            if promoted:
                h.types = h.types | PROMOTION_TYPES

    def _castling(self, blockers: int) -> tuple[list[int], list[int]]:
        """Joint castling update: a K and an R hypothesis both still on their start squares."""
        n = len(self.hyps)
        king_add, rook_add = [0] * n, [0] * n
        king_bit = chess.BB_SQUARES[self.king_start]
        for rook_start, king_to, rook_to, between in self.castles:
            if between & blockers:
                continue
            rook_bit = chess.BB_SQUARES[rook_start]
            kings = [i for i, h in enumerate(self.hyps) if "K" in h.types and h.squares & king_bit]
            rooks = [i for i, h in enumerate(self.hyps) if "R" in h.types and h.squares & rook_bit]
            if kings and rooks:
                for i in kings:
                    king_add[i] |= chess.BB_SQUARES[king_to]
                for i in rooks:
                    rook_add[i] |= chess.BB_SQUARES[rook_to]
        return king_add, rook_add

    def _expand_capture(self, target: int, blockers: int, prev_obs: str,
                        our_last_move: chess.Move | None) -> None:
        """Capture ply on ``target``: only hypotheses that could capture there may have moved."""
        target_bit = chess.BB_SQUARES[target]
        ep_landing = None
        if (our_last_move is not None and our_last_move.to_square == target
                and prev_obs[target].upper() == "P"
                and abs(our_last_move.to_square - our_last_move.from_square) == 16):
            ep_landing = (our_last_move.from_square + our_last_move.to_square) // 2
        for h in self.hyps:
            add, promoted = 0, False
            for square in _bits(h.squares):
                for kind in h.types:
                    if self._attacks(kind, square, target, blockers):
                        add |= target_bit
                        if kind == "P" and target_bit & chess.BB_RANKS[self.promotion_rank]:
                            promoted = True
                    if (kind == "P" and ep_landing is not None
                            and chess.BB_PAWN_ATTACKS[self.enemy][square] & chess.BB_SQUARES[ep_landing]):
                        add |= chess.BB_SQUARES[ep_landing]
            h.squares |= add
            if promoted:
                h.types = h.types | PROMOTION_TYPES

    def _attacks(self, kind: str, square: int, target: int, blockers: int) -> bool:
        """Could a ``kind`` on ``square`` capture on ``target``, given pre-move blockers?"""
        if kind == "N":
            return bool(chess.BB_KNIGHT_ATTACKS[square] & chess.BB_SQUARES[target])
        if kind == "K":
            return bool(chess.BB_KING_ATTACKS[square] & chess.BB_SQUARES[target])
        if kind == "P":
            return bool(chess.BB_PAWN_ATTACKS[self.enemy][square] & chess.BB_SQUARES[target])
        file_gap = abs(chess.square_file(square) - chess.square_file(target))
        rank_gap = abs(chess.square_rank(square) - chess.square_rank(target))
        orthogonal = (file_gap == 0) != (rank_gap == 0)
        diagonal = file_gap == rank_gap and file_gap > 0
        if not ((kind in "RQ" and orthogonal) or (kind in "BQ" and diagonal)):
            return False
        return not chess.between(square, target) & blockers

    def _pawn_pushes(self, square: int, blockers: int) -> int:
        one = square + self.pawn_step
        if not 0 <= one < 64 or blockers & chess.BB_SQUARES[one]:
            return 0
        pushes = chess.BB_SQUARES[one]
        if chess.square_rank(square) == self.pawn_start_rank:
            two = one + self.pawn_step
            if not blockers & chess.BB_SQUARES[two]:
                pushes |= chess.BB_SQUARES[two]
        return pushes

    @staticmethod
    def _slide(square: int, kind: str, blockers: int) -> int:
        reach = 0
        for ray in RAYS[kind][square]:
            for other in ray:
                bit = chess.BB_SQUARES[other]
                if blockers & bit:
                    break
                reach |= bit
        return reach

    # Filter ---------------------------------------------------------------------

    def _filter(self, obs: str) -> None:
        """Intersect with the observation, iterating unique visible matches to a fixpoint."""
        clear, visible = 0, []
        for square, char in enumerate(obs):
            if char == "-" or self._ours(char):
                clear |= chess.BB_SQUARES[square]
            elif char != "?":
                visible.append((square, char.upper()))
        for h in self.hyps:
            h.squares &= ~clear
        changed = True
        while changed:
            changed = False
            for square, kind in visible:
                bit = chess.BB_SQUARES[square]
                candidates = [h for h in self.hyps if kind in h.types and h.squares & bit]
                if not candidates:
                    raise TrackerInconsistency(f"no hypothesis for visible {kind} on {chess.square_name(square)}")
                for h in self.hyps:
                    if h.squares & bit and not any(h is c for c in candidates):
                        h.squares &= ~bit
                        changed = True
                if len(candidates) == 1:
                    h = candidates[0]
                    if h.squares != bit or h.types != frozenset(kind):
                        h.squares, h.types = bit, frozenset(kind)
                        changed = True
        for h in self.hyps:
            if not h.squares or not h.types:
                raise TrackerInconsistency("a hypothesis has no remaining squares or types")
        self.visible_enemy = sum(chess.BB_SQUARES[square] for square, _ in visible)
