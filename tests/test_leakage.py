"""Code under bot/ sees only observation strings and clock floats."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest
from unittest import mock

import bot.agents
from bot.agents.random_agent import RandomAgent
from harness.game import play_game

BOT_DIR = Path(__file__).resolve().parent.parent / "bot"
ALLOWED_TOP_LEVEL = set(sys.stdlib_module_names) | {"chess", "referee", "bot"}
OBSERVATION_CHARACTERS = set("?-PNBRQKpnbrqk")


def imported_modules(path: Path) -> list[str]:
    """Absolute module names imported by a file (relative imports map to 'bot')."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append("bot" if node.level else node.module)
    return names


class SpyAgent(RandomAgent):
    """Random agent that records every argument it receives."""
    observed: list = []
    clocks: list = []

    def observe(self, obs):
        SpyAgent.observed.append(obs)
        super().observe(obs)

    def choose_move(self, remaining):
        SpyAgent.clocks.append(remaining)
        return super().choose_move(remaining)


class LeakageTests(unittest.TestCase):
    def test_bot_imports_only_stdlib_chess_referee_and_bot(self):
        files = sorted(BOT_DIR.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            for name in imported_modules(path):
                top = name.split(".")[0]
                self.assertNotEqual(top, "harness", f"{path} imports {name}")
                self.assertIn(top, ALLOWED_TOP_LEVEL, f"{path} imports {name}")

    def test_agents_receive_only_observation_strings_and_float_clocks(self):
        SpyAgent.observed, SpyAgent.clocks = [], []
        with mock.patch.dict(bot.agents.REGISTRY, {"spy": SpyAgent}):
            for seed in range(5):
                play_game("spy", "spy", seed, seed + 100)
        self.assertGreater(len(SpyAgent.observed), 0)
        self.assertGreater(len(SpyAgent.clocks), 0)
        for obs in SpyAgent.observed:
            self.assertIs(type(obs), str)
            self.assertEqual(len(obs), 64)
            self.assertLessEqual(set(obs), OBSERVATION_CHARACTERS)
        for clock in SpyAgent.clocks:
            self.assertIs(type(clock), float)


if __name__ == "__main__":
    unittest.main()
