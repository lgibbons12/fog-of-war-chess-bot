"""bot/protocol.py speaks the arena protocol and nothing else on stdout."""
from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import chess

import bot.agents
from bot import protocol
from bot.agents.safety_agent import SafetyAgent
from referee import FowBoard, fow_moves, observation, run_match

PROTOCOL = Path(__file__).resolve().parent.parent / "bot" / "protocol.py"


def protocol_argv(agent: str, seed: int) -> list[str]:
    """Equivalent of bot/run.sh, but with this interpreter instead of PATH's python3."""
    return [sys.executable, "-u", str(PROTOCOL), "--agent", agent, "--seed", str(seed)]


class ProtocolTranscriptTests(unittest.TestCase):
    def test_ready_then_one_move_per_clock_line(self):
        board = FowBoard()
        # White receives exactly one observation before its first move.
        transcript = "fow\nw 180 2\n" + observation(board, chess.WHITE) + "\n180\n"
        for agent in ("random", "baseline", "safety"):
            with self.subTest(agent=agent):
                out = subprocess.run(protocol_argv(agent, 7), input=transcript, text=True,
                                     capture_output=True, check=True, timeout=30).stdout
                lines = out.splitlines()
                self.assertEqual(len(lines), 2)
                self.assertEqual(lines[0], "ready")
                legal = {move.uci() for move in fow_moves(board)}
                self.assertIn(lines[1].removeprefix("move "), legal)


class CrashingAgent(SafetyAgent):
    def _select(self, remaining):
        raise RuntimeError("deliberate failure")


class FallbackGuardTests(unittest.TestCase):
    def test_exception_in_choose_move_falls_back_to_a_random_legal_move(self):
        board = FowBoard()
        transcript = "fow\nw 180 2\n" + observation(board, chess.WHITE) + "\n180\n"
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(bot.agents.REGISTRY, {"crashing": CrashingAgent}), \
                mock.patch("sys.stdin", io.StringIO(transcript)), \
                mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            protocol.main(["--agent", "crashing", "--seed", "1"])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(lines[0], "ready")
        self.assertEqual(len(lines), 2)
        self.assertIn(lines[1].removeprefix("move "), {m.uci() for m in fow_moves(board)})
        self.assertIn("deliberate failure", stderr.getvalue())


@unittest.skipUnless(os.name == "posix", "referee.run_match needs POSIX pipes and process groups")
class ProtocolRefereeTests(unittest.TestCase):
    def test_referee_games_complete_without_failed_side(self):
        for white, black in [("random", "baseline"), ("baseline", "random"), ("random", "random"),
                             ("safety", "baseline"), ("baseline", "safety")]:
            with self.subTest(white=white, black=black):
                replay = run_match(protocol_argv(white, 3), protocol_argv(black, 4), max_plies=1000)
                self.assertNotIn("failedSide", replay, replay["reason"])
                self.assertIn(replay["result"], ("1-0", "0-1", "1/2-1/2"))


if __name__ == "__main__":
    unittest.main()
