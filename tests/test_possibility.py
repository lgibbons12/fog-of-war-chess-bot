"""Possibility tracker: scripted scenarios, soundness over harness games, reduction to Step 1.

Tests may look at the true board; the tracker never does.
"""
from __future__ import annotations

import unittest

import chess

from bot.possibility import ALL_TYPES, EnemyPiece, PossibilityTracker
from bot.safety import apply_move, king_safety
from bot.tracker import ObservationTracker
from harness.game import play_game
from referee import FowBoard, fow_moves, observation


def has_matching(board: chess.Board, side: chess.Color, hyps: list[EnemyPiece]) -> bool:
    """Is there a one-to-one assignment of true enemy pieces to hypotheses? (augmenting paths)"""
    pieces = [(sq, board.piece_at(sq).symbol().upper()) for sq in chess.SquareSet(board.occupied_co[not side])]
    if len(pieces) != len(hyps):
        return False
    owner = [-1] * len(hyps)

    def assign(i: int, seen: set[int]) -> bool:
        square, kind = pieces[i]
        for j, h in enumerate(hyps):
            if j not in seen and kind in h.types and h.squares & chess.BB_SQUARES[square]:
                seen.add(j)
                if owner[j] == -1 or assign(owner[j], seen):
                    owner[j] = i
                    return True
        return False

    return all(assign(i, set()) for i in range(len(pieces)))


def exact_pieces(board: chess.Board, enemy: chess.Color) -> list[EnemyPiece]:
    return [EnemyPiece(frozenset(board.piece_at(sq).symbol().upper()), chess.BB_SQUARES[sq])
            for sq in chess.SquareSet(board.occupied_co[enemy])]


def squares(*names: str) -> int:
    return sum(chess.BB_SQUARES[chess.parse_square(name)] for name in names)


class Script:
    """Drive a tracker for ``side`` through referee moves from a FEN, checking soundness."""

    def __init__(self, test: unittest.TestCase, fen: str, side: chess.Color,
                 pieces: list[EnemyPiece] | None = None):
        self.test, self.side = test, side
        self.board = FowBoard(fen)
        self.tracker = PossibilityTracker(side, pieces=pieces or exact_pieces(self.board, not side))
        self.ply = 0 if self.board.turn == chess.WHITE else 1
        self.prev = None
        self.last = None
        self.observe()

    def observe(self) -> None:
        obs = observation(self.board, self.side)
        self.tracker.on_observation(obs, self.ply, self.last, self.prev)
        self.prev = obs
        self.test.assertTrue(has_matching(self.board, self.side, self.tracker.hyps), self.board.fen())
        self.test.assertFalse(self.tracker.certainly_occupied() & ~self.board.occupied_co[not self.side])

    def play(self, *ucis: str) -> None:
        for uci in ucis:
            move = chess.Move.from_uci(uci)
            self.test.assertIn(move, fow_moves(self.board), f"{uci} in {self.board.fen()}")
            if self.board.turn == self.side:
                self.last = move
            self.board.push(move)
            self.ply += 1
            self.observe()

    def hyp(self, kind: str) -> EnemyPiece:
        """The unique hypothesis whose types include ``kind``."""
        found = [h for h in self.tracker.hyps if kind in h.types]
        self.test.assertEqual(len(found), 1, [(h.types, h.squares) for h in self.tracker.hyps])
        return found[0]


class ScriptedTrackerTests(unittest.TestCase):
    def test_hidden_knight_tour_stays_within_knight_reach(self):
        s = Script(self, "n3k3/8/8/8/8/8/8/7K w - - 0 1", chess.WHITE)
        reach = squares("a8")
        for ours, theirs in [("h1g1", "a8b6"), ("g1h1", "b6c4"), ("h1g1", "c4e5"), ("g1h1", "e5g6")]:
            s.play(ours, theirs)
            for square in chess.SquareSet(reach):
                reach |= chess.BB_KNIGHT_ATTACKS[square]
            knight = s.hyp("N")
            self.assertEqual(knight.types, frozenset("N"))
            self.assertFalse(knight.squares & ~reach, "knight hypothesis outside knight reach")
            self.assertTrue(knight.squares & chess.BB_SQUARES[s.board.pieces(chess.KNIGHT, chess.BLACK).pop()])

    def test_queen_blocked_by_pawn_until_pawn_has_had_a_ply(self):
        s = Script(self, "3qk3/3p4/8/8/8/8/8/7K w - - 0 1", chess.WHITE)
        s.play("h1g1", "e8f8")  # the pawn on d7 is a singleton blocker during this ply
        self.assertFalse(s.hyp("Q").squares & squares("d6", "d5"))
        s.play("g1h1", "f8e8")  # the pawn might have moved last ply, so d7 no longer blocks
        self.assertTrue(s.hyp("Q").squares & squares("d6"))

    def test_enemy_capture_only_expands_hypotheses_that_could_capture(self):
        s = Script(self, "3qk3/8/b7/3N4/8/8/8/7K b - - 0 1", chess.WHITE)
        before = {kind: s.hyp(kind).squares for kind in "KB"}
        s.play("d8d5")
        self.assertTrue(s.hyp("Q").squares & squares("d5"))
        for kind in "KB":
            self.assertEqual(s.hyp(kind).squares, before[kind], kind)

    def test_enemy_en_passant(self):
        s = Script(self, "4k3/8/8/8/3p4/8/4P3/7K w - - 0 1", chess.WHITE)
        s.play("e2e4", "d4e3")
        self.assertTrue(s.hyp("P").squares & squares("e3"))

    def test_enemy_castling_both_directions(self):
        for king_to, rook_from, rook_to in [("g8", "h8", "f8"), ("c8", "a8", "d8")]:
            with self.subTest(king_to=king_to):
                s = Script(self, "r3k2r/8/8/8/8/8/8/K7 b kq - 0 1", chess.WHITE)
                rook = next(h for h in s.tracker.hyps if h.squares == squares(rook_from))
                s.play("e8" + king_to)
                self.assertTrue(s.hyp("K").squares & squares(king_to))
                self.assertTrue(rook.squares & squares(rook_to))

    def test_enemy_promotion_adds_piece_types(self):
        s = Script(self, "4k3/8/8/8/8/8/p7/7K b - - 0 1", chess.WHITE)
        s.play("a2a1q")
        pawn = s.hyp("P")
        self.assertTrue(PROMOTION <= pawn.types)
        self.assertTrue(pawn.squares & squares("a1"))

    def test_our_ambiguous_capture_merges_candidates(self):
        # Truth: knights on c6 and e6. Both hypotheses could be the c6 knight.
        pieces = [EnemyPiece(frozenset("N"), squares("c6", "e6")),
                  EnemyPiece(frozenset("N"), squares("c6", "g6")),
                  EnemyPiece(frozenset("K"), squares("h8"))]
        s = Script(self, "7k/8/2n1n3/8/B7/8/8/7K w - - 0 1", chess.WHITE, pieces)
        s.play("a4c6")
        knights = [h for h in s.tracker.hyps if "N" in h.types]
        self.assertEqual(len(s.tracker.hyps), 2)
        self.assertEqual(len(knights), 1)
        self.assertEqual((knights[0].types, knights[0].squares), (frozenset("N"), squares("e6", "g6")))

    def test_bishop_never_reaches_off_color_squares(self):
        s = Script(self, "2b1k3/8/8/8/8/8/8/7K w - - 0 1", chess.WHITE)
        for ours, theirs in [("h1g1", "c8b7"), ("g1h1", "b7a6"), ("h1g1", "a6c4"), ("g1h1", "c4e2"),
                             ("h1g1", "e2b5")]:
            s.play(ours, theirs)
            self.assertFalse(s.hyp("B").squares & chess.BB_DARK_SQUARES)


PROMOTION = frozenset("NBRQ")


class TrackerSoundnessTests(unittest.TestCase):
    """Key test: our tracker never excludes the truth over 200+ harness games."""

    def check_game(self, replay: dict, side: chess.Color) -> tuple[int, int]:
        """Return (observations checked, (decision, move) safety pairs checked)."""
        board = FowBoard()
        tracker = PossibilityTracker(side, strict=True)
        legal = ObservationTracker(side)
        prev = last = None
        observations = moves_checked = 0
        for ply in range(replay["plies"]):
            obs = observation(board, side)
            tracker.on_observation(obs, ply, last, prev)
            legal.observe(obs)
            self.assertTrue(has_matching(board, side, tracker.hyps), f"ply {ply}: {board.fen()}")
            self.assertFalse(tracker.certainly_occupied() & ~board.occupied_co[not side], board.fen())
            observations += 1
            frame = replay["frames"][ply + 1]
            if board.turn == side:
                self.assertEqual(frame["decision"]["tracker"]["resets"], 0)
                for move in legal.legal_moves():
                    report = king_safety(apply_move(obs, move, side), side, tracker)
                    board.push(move)
                    attacked = board.is_attacked_by(not side, board.king(side))
                    board.pop()
                    if report.known_loss:
                        self.assertTrue(attacked, f"{board.fen()} {move}: known loss but safe")
                    elif not report.exposed:
                        self.assertFalse(attacked, f"{board.fen()} {move}: reported safe but attacked")
                    moves_checked += 1
                last = chess.Move.from_uci(frame["move"])
                legal.record_move(last)
            board.push_uci(frame["move"])
            prev = obs
        return observations, moves_checked

    def test_tracker_and_tracked_safety_are_sound(self):
        observations = moves_checked = games = 0
        for opponent in ("random", "baseline", "safety_v2"):
            for seed in range(34):  # 34 x 3 opponents x 2 colors = 204 games
                for side in (chess.WHITE, chess.BLACK):
                    white, black = ("tracked_v2", opponent) if side else (opponent, "tracked_v2")
                    with self.subTest(white=white, black=black, seed=seed):
                        o, m = self.check_game(play_game(white, black, seed, seed + 700), side)
                        observations, moves_checked, games = observations + o, moves_checked + m, games + 1
        self.assertEqual(games, 204)
        self.assertGreater(observations, 8000)
        self.assertGreater(moves_checked, 50000)


def coarse_tracker(side: chess.Color, obs: str, count: int) -> PossibilityTracker:
    """Every enemy piece may be any type on any '?' or visible enemy square."""
    support = sum(chess.BB_SQUARES[sq] for sq, char in enumerate(obs)
                  if char == "?" or (char not in "-?" and char.isupper() != side))
    tracker = PossibilityTracker(side, pieces=[EnemyPiece(ALL_TYPES, support) for _ in range(count)])
    tracker.on_observation(obs, 0, None, None)
    return tracker


class ReductionTests(unittest.TestCase):
    def test_coarse_tracker_reproduces_step1_reports(self):
        compared = 0
        for seed in range(10):
            for white, black in (("safety_v2", "baseline"), ("baseline", "safety_v2")):
                replay = play_game(white, black, seed, seed + 900)
                side = chess.WHITE if white == "safety_v2" else chess.BLACK
                board, legal = FowBoard(), ObservationTracker(side)
                for ply in range(replay["plies"]):
                    obs = observation(board, side)
                    legal.observe(obs)
                    move_uci = replay["frames"][ply + 1]["move"]
                    if board.turn == side:
                        count = chess.popcount(board.occupied_co[not side])
                        tracker = coarse_tracker(side, obs, count)
                        for move in legal.legal_moves():
                            cells = apply_move(obs, move, side)
                            self.assertEqual(king_safety(cells, side, tracker), king_safety(cells, side),
                                             f"{board.fen()} {move}")
                            compared += 1
                        legal.record_move(chess.Move.from_uci(move_uci))
                    board.push_uci(move_uci)
        self.assertGreater(compared, 5000)


if __name__ == "__main__":
    unittest.main()
