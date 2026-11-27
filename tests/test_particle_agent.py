"""Particle agents: sort keys, fallbacks (unavailable, time guard, errors) and the decision record."""
from __future__ import annotations

import io
import unittest
from unittest import mock

import chess

from bot.agents import REGISTRY
from bot.agents.particle_agent import TIME_GUARD_SECONDS, ParticleAgent
from referee import FowBoard, fow_moves, observation


def started_agent(name: str = "particle_ev300", strict: bool = True, seed: int = 5) -> ParticleAgent:
    agent = REGISTRY[name](chess.WHITE, 180.0, 2.0, seed, strict=strict)
    agent.observe(observation(FowBoard(), chess.WHITE))
    return agent


class ParticleAgentTests(unittest.TestCase):
    def test_registry_variants(self):
        self.assertIsNone(REGISTRY["particle_v2"](chess.WHITE, 180.0, 2.0, 1).lam)
        for lam in (100, 300, 1000):
            agent = REGISTRY[f"particle_ev{lam}"](chess.WHITE, 180.0, 2.0, 1)
            self.assertEqual(agent.lam, lam)
            self.assertEqual(agent.particles.n, 64)
            self.assertEqual(agent.particles.recovery, "reexpand")

    def test_one_rng_call_per_legal_move(self):
        agent = started_agent()
        calls = []
        original = agent.rng.random
        with mock.patch.object(agent.rng, "random", side_effect=lambda: calls.append(1) or original()):
            agent.choose_move(180.0)
        self.assertEqual(len(calls), len(fow_moves(FowBoard())))

    def test_decision_record_at_start(self):
        agent = started_agent()
        move = agent.choose_move(180.0)
        decision = agent.last_decision
        self.assertEqual(decision["move"], move)
        self.assertEqual(decision["particle_mode"], "particles")
        self.assertEqual(decision["p_loss"], 0.0)
        self.assertEqual(decision["min_p_loss"], 0.0)
        self.assertEqual(decision["particles"]["distinct"], 1)
        self.assertGreaterEqual(decision["decision_seconds"], 0.0)
        self.assertEqual(len(agent.last_scores), 20)

    def test_unavailable_particles_use_exposure_as_p_loss(self):
        agent = started_agent()
        agent.particles._particles = []
        agent.particles.available = False
        agent.choose_move(180.0)
        self.assertEqual(agent.last_decision["particle_mode"], "unavailable")
        for _, report, p_loss in agent.last_scores:
            self.assertEqual(p_loss, float(bool(report.exposed)))

    def test_time_guard_switches_particles_off_for_the_rest_of_the_game(self):
        agent = started_agent()
        with mock.patch("sys.stderr", io.StringIO()):
            agent.choose_move(TIME_GUARD_SECONDS - 0.5)
        self.assertEqual(agent.last_decision["particle_mode"], "time_guard")
        self.assertIsNone(agent.particles)
        self.assertIsNone(agent.last_decision["particles"])
        # Later observations and decisions keep working without particles.
        board = FowBoard()
        board.push(agent.last_move)
        board.push(chess.Move.from_uci("e7e5") if board.is_legal(chess.Move.from_uci("e7e5"))
                   else next(iter(fow_moves(board))))
        agent.observe(observation(board, chess.WHITE))
        agent.observe(observation(board, chess.WHITE))
        agent.choose_move(180.0)
        self.assertEqual(agent.last_decision["particle_mode"], "time_guard")

    def test_particle_error_is_fatal_in_strict_mode_only(self):
        for strict in (True, False):
            with self.subTest(strict=strict):
                agent = started_agent(strict=strict)
                with mock.patch.object(type(agent.particles), "loss_probability",
                                       side_effect=RuntimeError("boom")), \
                        mock.patch("sys.stderr", io.StringIO()):
                    if strict:
                        with self.assertRaises(RuntimeError):
                            agent.choose_move(180.0)
                    else:
                        agent.choose_move(180.0)
                        self.assertEqual(agent.last_decision["particle_mode"], "error")
                        self.assertIsNone(agent.particles)

    def test_update_error_switches_off_outside_strict_mode(self):
        agent = REGISTRY["particle_ev300"](chess.WHITE, 180.0, 2.0, 5, strict=False)
        with mock.patch.object(type(agent.particles), "on_observation", side_effect=ValueError("bad")), \
                mock.patch("sys.stderr", io.StringIO()):
            agent.observe(observation(FowBoard(), chess.WHITE))
        self.assertEqual(agent.off_reason, "error")
        agent.choose_move(180.0)
        self.assertEqual(agent.last_decision["particle_mode"], "error")

    def test_keys_trade_material_against_risk(self):
        # Pretend e2e4 wins a rook (50 units) but loses the king in 30% of particles.
        target = chess.Move.from_uci("e2e4")
        material = lambda obs, cells, move, side: 50 if move == target else 0
        risk = lambda self, move: 0.3 if move == target else 0.0
        expected = {"particle_v2": True, "particle_ev100": True, "particle_ev300": False,
                    "particle_ev1000": False}
        for name, picks_target in expected.items():
            with self.subTest(agent=name):
                agent = started_agent(name)
                with mock.patch("bot.agents.particle_agent.material_score", material),                         mock.patch.object(type(agent.particles), "loss_probability", risk):
                    move = agent.choose_move(180.0)
                self.assertEqual(move == target, picks_target)


if __name__ == "__main__":
    unittest.main()
