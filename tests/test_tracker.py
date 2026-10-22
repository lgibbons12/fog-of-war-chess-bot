"""bot.tracker is a verbatim copy of the starter tracker, so the starter tests cover it."""
from __future__ import annotations

import inspect
import unittest

import bot.tracker
import uniform_random

COPIED = ("infer_en_passant", "candidates", "ObservationTracker")


class TrackerCopyTests(unittest.TestCase):
    def test_source_is_identical_to_starter(self):
        for name in COPIED:
            with self.subTest(name=name):
                self.assertEqual(inspect.getsource(getattr(bot.tracker, name)),
                                 inspect.getsource(getattr(uniform_random, name)))
        self.assertEqual(bot.tracker.OBSERVATION_CHARACTERS,
                         uniform_random.OBSERVATION_CHARACTERS)


if __name__ == "__main__":
    unittest.main()
