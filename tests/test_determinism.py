"""run_match_pairs is a pure function of its arguments (timing aside)."""
from __future__ import annotations

from dataclasses import asdict
import unittest

from harness.match import run_match_pairs

TIMING_FIELDS = ("a_think_total", "a_think_max")


def without_timing(summaries):
    rows = [asdict(summary) for summary in summaries]
    for row in rows:
        for field in TIMING_FIELDS:
            del row[field]
    return rows


class DeterminismTests(unittest.TestCase):
    def test_same_args_same_summaries_across_worker_counts(self):
        for agent_a, agent_b in [("random", "baseline"), ("random", "random")]:
            with self.subTest(a=agent_a, b=agent_b):
                serial = run_match_pairs(agent_a, agent_b, 4, 11, workers=1)
                parallel = run_match_pairs(agent_a, agent_b, 4, 11, workers=4)
                again = run_match_pairs(agent_a, agent_b, 4, 11, workers=1)
                self.assertEqual(len(serial), 8)
                self.assertEqual(without_timing(serial), without_timing(parallel))
                self.assertEqual(without_timing(serial), without_timing(again))


if __name__ == "__main__":
    unittest.main()
