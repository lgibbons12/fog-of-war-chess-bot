"""bot/protocol.py speaks the arena protocol and nothing else on stdout."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

import chess

from referee import FowBoard, fow_moves, observation, run_match

PROTOCOL = Path(__file__).resolve().parent.parent / "bot" / "protocol.py"


def protocol_argv(agent: str, seed: int) -> list[str]:
    """Equivalent of bot/run.sh, but with this interpreter instead of PATH's python3."""
    return [sys.executable, "-u", str(PROTOCOL), "--agent", agent, "--seed", str(seed)]


class ProtocolTranscriptTests(unittest.TestCase):
    def test_ready_then_one_move_per_clock_line(self):
        board = FowBoard()
        transcript = ("fow\nw 180 2\n" + observation(board, chess.WHITE) + "\n"
                      + observation(board, chess.WHITE) + "\n180\n")
        for agent in ("random", "baseline"):
            with self.subTest(agent=agent):
                out = subprocess.run(protocol_argv(agent, 7), input=transcript, text=True,
                                     capture_output=True, check=True, timeout=30).stdout
                lines = out.splitlines()
                self.assertEqual(len(lines), 2)
                self.assertEqual(lines[0], "ready")
                legal = {move.uci() for move in fow_moves(board)}
                self.assertIn(lines[1].removeprefix("move "), legal)


@unittest.skipUnless(os.name == "posix", "referee.run_match needs POSIX pipes and process groups")
class ProtocolRefereeTests(unittest.TestCase):
    def test_referee_games_complete_without_failed_side(self):
        for white, black in [("random", "baseline"), ("baseline", "random"), ("random", "random")]:
            with self.subTest(white=white, black=black):
                replay = run_match(protocol_argv(white, 3), protocol_argv(black, 4), max_plies=1000)
                self.assertNotIn("failedSide", replay, replay["reason"])
                self.assertIn(replay["result"], ("1-0", "0-1", "1/2-1/2"))


if __name__ == "__main__":
    unittest.main()
