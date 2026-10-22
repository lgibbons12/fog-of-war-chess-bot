"""Unit tests for bot.safety: apply_move and attackers_of."""
from __future__ import annotations

import unittest

import chess

from bot.safety import apply_move, attackers_of, king_safety
from referee import FowBoard, observation


def truth_after(board: FowBoard, move: chess.Move) -> list[str]:
    after = board.copy(stack=False)
    after.push(move)
    return [after.piece_at(sq).symbol() if after.piece_at(sq) else "-" for sq in chess.SQUARES]


class ApplyMoveTests(unittest.TestCase):
    def check(self, fen: str, uci: str, expected: dict[str, str], before: list[str] = ()) -> None:
        """apply_move agrees with the true board on every non-'?' square, and on ``expected``."""
        board = FowBoard(fen)
        for pre in before:
            board.push_uci(pre)
        side = board.turn
        obs = observation(board, side)
        move = chess.Move.from_uci(uci)
        cells = apply_move(obs, move, side)
        truth = truth_after(board, move)
        for square in chess.SQUARES:
            expect = "?" if obs[square] == "?" else truth[square]
            self.assertEqual(cells[square], expect, chess.square_name(square))
        for name, char in expected.items():
            self.assertEqual(cells[chess.parse_square(name)], char, name)

    def test_quiet_move(self):
        self.check(chess.STARTING_FEN, "e2e4", {"e2": "-", "e4": "P"})
        self.check(chess.STARTING_FEN.replace(" w ", " b "), "g8f6", {"g8": "-", "f6": "n"})

    def test_capture(self):
        self.check("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4d5", {"e4": "-", "d5": "P"})
        self.check("4k3/8/8/3p4/4P3/8/8/4K3 b - - 0 1", "d5e4", {"d5": "-", "e4": "p"})

    def test_each_promotion(self):
        for piece in "qrbn":
            with self.subTest(piece=piece):
                self.check("k5r1/7P/8/8/8/8/8/K7 w - - 0 1", "h7h8" + piece, {"h7": "-", "h8": piece.upper()})
                self.check("k5r1/7P/8/8/8/8/8/K7 w - - 0 1", "h7g8" + piece, {"g8": piece.upper()})
        self.check("k7/8/8/8/8/8/p7/7K b - - 0 1", "a2a1q", {"a2": "-", "a1": "q"})

    def test_castling_both_sides_both_colors(self):
        fen = "r3k2r/8/8/8/8/8/8/R3K2R {} KQkq - 0 1"
        self.check(fen.format("w"), "e1g1", {"e1": "-", "f1": "R", "g1": "K", "h1": "-"})
        self.check(fen.format("w"), "e1c1", {"a1": "-", "c1": "K", "d1": "R", "e1": "-"})
        self.check(fen.format("b"), "e8g8", {"e8": "-", "f8": "r", "g8": "k", "h8": "-"})
        self.check(fen.format("b"), "e8c8", {"a8": "-", "c8": "k", "d8": "r", "e8": "-"})

    def test_en_passant_both_colors(self):
        self.check("k3r3/3p4/8/4P3/8/8/8/4K3 b - - 0 1", "e5d6",
                   {"e5": "-", "d6": "P", "d5": "-"}, before=["d7d5"])
        self.check("4k3/8/8/8/4p3/8/3P4/K3R3 w - - 0 1", "e4d3",
                   {"e4": "-", "d3": "p", "d4": "-"}, before=["d2d4"])


def cells_with(pieces: dict[str, str], unknown: tuple[str, ...] = ()) -> list[str]:
    cells = ["-"] * 64
    for name, char in pieces.items():
        cells[chess.parse_square(name)] = char
    for name in unknown:
        cells[chess.parse_square(name)] = "?"
    return cells


def names(squares) -> set[str]:
    return {chess.square_name(square) for square in squares}


class AttackersOfTests(unittest.TestCase):
    def attackers(self, pieces, unknown=(), target="d4", side=chess.WHITE):
        known, possible = attackers_of(cells_with(pieces, unknown), chess.parse_square(target), side)
        self.assertEqual(len(possible), len(set(possible)))
        return names(known), names(possible)

    def test_each_piece_type_as_known_attacker(self):
        for square, piece in [("e6", "n"), ("g7", "b"), ("d8", "r"), ("a4", "q"), ("a1", "q"),
                              ("e5", "k"), ("c5", "p")]:
            with self.subTest(piece=piece, square=square):
                self.assertEqual(self.attackers({square: piece}), ({square}, set()))

    def test_each_piece_type_as_blocked_or_non_attacker(self):
        cases = [
            ({"d8": "r", "d6": "P"}, "rook blocked by our piece"),
            ({"g7": "b", "f6": "P"}, "bishop blocked by our piece"),
            ({"a4": "q", "b4": "P"}, "queen blocked by our piece"),
            ({"d8": "r", "d6": "n"}, "rook blocked by an enemy knight"),
            ({"d7": "b"}, "bishop on an orthogonal"),
            ({"g7": "r"}, "rook on a diagonal"),
            ({"d6": "k"}, "king at distance 2"),
            ({"e4": "n"}, "knight adjacent"),
            ({"b6": "p"}, "pawn at distance 2"),
            ({"d5": "p"}, "pawn straight ahead"),
        ]
        for pieces, label in cases:
            with self.subTest(label):
                self.assertEqual(self.attackers(pieces), (set(), set()))

    def test_pawn_direction_both_colors(self):
        # Black pawns attack downward: from c5/e5 onto d4, not from c3/e3.
        self.assertEqual(self.attackers({"c5": "p", "e5": "p", "c3": "p", "e3": "p"}),
                         ({"c5", "e5"}, set()))
        # White pawns attack upward: from c3/e3 onto d4 when we are Black.
        self.assertEqual(self.attackers({"c5": "P", "e5": "P", "c3": "P", "e3": "P"}, side=chess.BLACK),
                         ({"c3", "e3"}, set()))

    def test_unknown_on_open_ray_is_possible(self):
        self.assertEqual(self.attackers({}, unknown=("d7",)), (set(), {"d7"}))
        self.assertEqual(self.attackers({}, unknown=("h8",)), (set(), {"h8"}))

    def test_unknown_behind_blocker_is_not_possible(self):
        self.assertEqual(self.attackers({"d5": "P"}, unknown=("d6",)), (set(), set()))
        self.assertEqual(self.attackers({"d5": "n"}, unknown=("d6",)), (set(), set()))

    def test_unknown_on_knight_square_is_possible(self):
        self.assertEqual(self.attackers({}, unknown=("e6", "b3")), (set(), {"e6", "b3"}))

    def test_king_safety_wraps_attackers_of_our_king(self):
        report = king_safety(cells_with({"d4": "K", "d8": "r"}, unknown=("a1",)), chess.WHITE)
        self.assertTrue(report.known_loss)
        self.assertEqual(names(report.exposed), {"a1"})
        self.assertEqual(report.king_square, chess.D4)


if __name__ == "__main__":
    unittest.main()
