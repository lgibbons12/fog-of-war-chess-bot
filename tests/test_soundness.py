"""The observation-only safety check over-approximates true king capture.

Replays harness games and, at every decision, checks every legal move
against the true board (tests may see it; the agent never does).
"""
from __future__ import annotations

import unittest

import chess

from bot.safety import apply_move, king_safety
from bot.tracker import ObservationTracker
from harness.game import play_game
from referee import FowBoard, observation

GAMES_PER_SETUP = 50  # x 2 opponents x 2 colors = 200 games


class SoundnessTests(unittest.TestCase):
    def check_game(self, replay: dict) -> int:
        """Return the number of (decision, move) pairs checked for the safety side(s)."""
        sides = [side for side, name in ((chess.WHITE, replay["white"]), (chess.BLACK, replay["black"]))
                 if name == "safety"]
        board = FowBoard()
        trackers = {side: ObservationTracker(side) for side in sides}
        checked = 0
        for frame in replay["frames"][1:]:
            for side in sides:
                trackers[side].observe(observation(board, side))
            side = board.turn
            if side in trackers:
                obs = trackers[side].current
                for move in trackers[side].legal_moves():
                    report = king_safety(apply_move(obs, move, side), side)
                    board.push(move)
                    attacked = board.is_attacked_by(not side, board.king(side))
                    board.pop()
                    if report.known_loss:
                        self.assertTrue(attacked, f"{board.fen()} {move}: known loss but safe")
                    elif not report.exposed:
                        self.assertFalse(attacked, f"{board.fen()} {move}: reported safe but attacked")
                    checked += 1
                decision = frame["decision"]
                self.assertEqual(decision["move"], frame["move"])
                if decision["min_safe_exposure"] == 0:  # count mode never picks exposure over safety
                    self.assertFalse(decision["report"]["known_loss"])
                    self.assertEqual(decision["report"]["exposed"], [])
                trackers[side].record_move(chess.Move.from_uci(frame["move"]))
            board.push_uci(frame["move"])
            self.assertEqual(frame["board"], "".join(
                board.piece_at(sq).symbol() if board.piece_at(sq) else "-" for sq in chess.SQUARES))
        return checked

    def test_reports_bound_true_king_capture(self):
        checked = 0
        for opponent in ("random", "baseline"):
            for seed in range(GAMES_PER_SETUP):
                for white, black in (("safety", opponent), (opponent, "safety")):
                    with self.subTest(white=white, black=black, seed=seed):
                        checked += self.check_game(play_game(white, black, seed, seed + 500))
        self.assertGreater(checked, 50000)


if __name__ == "__main__":
    unittest.main()
