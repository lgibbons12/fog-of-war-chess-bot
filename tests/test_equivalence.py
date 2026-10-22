"""The in-process harness + ported agents reproduce the subprocess referee + starters."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

from harness.game import play_game
from referee import run_match

ROOT = Path(__file__).resolve().parent.parent
STARTERS = {"random": ROOT / "uniform_random.py", "baseline": ROOT / "baseline.py"}
MATCHUPS = [("random", "random"), ("random", "baseline")]
SEEDS = range(10)
MAX_PLIES = 1000


def starter_argv(name: str, seed: int) -> list[str]:
    return [sys.executable, "-u", str(STARTERS[name]), "--seed", str(seed)]


@unittest.skipUnless(os.name == "posix", "referee.run_match needs POSIX pipes and process groups")
class EquivalenceTests(unittest.TestCase):
    def test_harness_matches_subprocess_referee(self):
        for white, black in MATCHUPS:
            for seed in SEEDS:
                seed_white, seed_black = seed, seed + 100
                with self.subTest(white=white, black=black, seed=seed):
                    expected = run_match(starter_argv(white, seed_white),
                                         starter_argv(black, seed_black), max_plies=MAX_PLIES)
                    # strict=False: like the referee, a crashing bot loses instead of raising.
                    actual = play_game(white, black, seed_white, seed_black, MAX_PLIES, strict=False)
                    self.assertNotIn("failedSide", expected)
                    self.assertEqual(actual["result"], expected["result"])
                    self.assertEqual(actual["reason"], expected["reason"])
                    self.assertEqual(len(actual["frames"]), len(expected["frames"]))
                    for got, want in zip(actual["frames"], expected["frames"]):
                        for key in ("ply", "board", "white", "black", "move"):
                            self.assertEqual(got[key], want[key], f"ply {want['ply']} {key}")


if __name__ == "__main__":
    unittest.main()
