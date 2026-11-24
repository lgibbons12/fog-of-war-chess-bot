"""Run: python3 -m unittest test_moe_bot test_uniform_random test_transformer_bot."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

import chess
import chess.engine

from referee import FowBoard, fow_moves, observation
from moe_bot.core import Belief, Bot, Deadline, InformationExpert, Mixture, TimeExpert, ValueExpert, time_budget
from moe_bot.train import collect, train


class BeliefTests(unittest.TestCase):
    def test_default_belief_capacity(self):
        self.assertEqual(Belief(True).capacity, 256)

    def test_filter_deadline_does_not_publish_partial_expansion(self):
        belief = Belief(True)
        original = belief.boards[0].fen()
        with self.assertRaises(Deadline):
            belief.observe(observation(FowBoard(), True), deadline=time.monotonic() - 1)
        self.assertEqual(belief.boards[0].fen(), original)
        self.assertFalse(belief.started)

    def test_phase_budget_and_clock_reserve(self):
        full = observation(FowBoard(), True)
        sparse = 'KPP-----' + '?' * 56
        opening = time_budget(full, True, 4, 16, 16, 180, 2, 2)
        middle = time_budget(full, True, 30, 16, 16, 180, 2, 2)
        end = time_budget(sparse, True, 60, 2, 16, 180, 2, 2)
        self.assertEqual([opening[0], middle[0], end[0]], ['opening', 'middlegame', 'endgame'])
        self.assertGreater(middle[2], opening[2])
        self.assertGreater(opening[2], end[2])
        self.assertLessEqual(time_budget(full, True, 30, 16, 16, 0.1, 0, 2)[1], 0.1)
        self.assertEqual(time_budget(full, True, 30, 16, 32, 180, 2, 2)[2], middle[2])

    def test_both_colors_and_observation_phases(self):
        for side in (True, False):
            board, belief = FowBoard(), Belief(side, 10000)
            belief.observe(observation(board, side))
            for uci in ('e2e4', 'e7e5', 'g1f3'):
                move = chess.Move.from_uci(uci)
                if board.turn == side:
                    belief.record_move(move)
                board.push(move)
                belief.observe(observation(board, side))
                self.assertAlmostEqual(sum(belief.weights), 1)
                self.assertTrue(any(b.fen() == board.fen() for b in belief.boards))
                self.assertTrue(all(observation(b, side) == observation(board, side) for b in belief.boards))

    def test_capacity_and_depletion(self):
        board, belief = FowBoard(), Belief(False, 3)
        belief.observe(observation(board, False))
        board.push_uci('e2e4')
        belief.observe(observation(board, False))
        self.assertLessEqual(len(belief.boards), 3)
        self.assertAlmostEqual(sum(belief.weights), 1)
        belief.observe('-' * 64)
        self.assertEqual(belief.boards, [])
        self.assertEqual(belief.weights, [])


class ExpertTests(unittest.TestCase):
    def test_information_partition(self):
        a, b = FowBoard(), FowBoard()
        b.remove_piece_at(chess.A2)
        gain, _ = InformationExpert.partition([a, b], [0.5, 0.5], True)
        self.assertAlmostEqual(gain, math.log(2))
        gain, _ = InformationExpert.partition([a, a], [0.5, 0.5], True)
        self.assertEqual(gain, 0)

    def test_stockfish_score_and_perspective(self):
        expert = ValueExpert()
        expert.engine = Mock()
        expert.engine.analyse.return_value = {'score': chess.engine.PovScore(chess.engine.Cp(200), True)}
        board = FowBoard()
        value = expert.evaluate(board, False, time.monotonic() + 5)
        self.assertAlmostEqual(value, math.tanh(-200 / 600))
        self.assertEqual(expert.sources['stockfish'], 1)

    def test_time_limited_material_fallback_is_not_cached_as_engine_score(self):
        expert = ValueExpert()
        expert.engine = Mock()
        expert.engine.analyse.return_value = {'score': chess.engine.PovScore(chess.engine.Cp(200), True)}
        board = FowBoard()
        self.assertEqual(expert.evaluate(board, True, time.monotonic() + 0.001), 0)
        self.assertAlmostEqual(expert.evaluate(board, True, time.monotonic() + 5), math.tanh(200 / 600))
        expert.engine.analyse.assert_called_once()

    def test_terminal_uses_referee_before_engine(self):
        expert = ValueExpert()
        expert.engine = Mock()
        board = FowBoard('k3r3/8/8/8/8/8/3R4/4K3 b - - 1 1')
        self.assertEqual(expert.evaluate(board, True, time.monotonic() + 5), -1)
        expert.engine.analyse.assert_not_called()

    def test_time_forecast_learns(self):
        expert = TimeExpert()
        before = expert.forecast(FowBoard(), 2)
        expert.update(1, 1)
        self.assertGreater(expert.forecast(FowBoard(), 2), before)


class MixtureTests(unittest.TestCase):
    def test_default_preserves_prior_and_training_learns(self):
        model = Mixture()
        features, prior, context = [[-1] * 4, [1] * 4], [0.7, 0.3], [1, 0.5, 0.2]
        posterior, gate, _ = model.components(features, prior, context)
        self.assertAlmostEqual(posterior[0], 0.7)
        self.assertAlmostEqual(sum(gate), 1)
        for _ in range(100):
            model.fit_one(features, prior, context, 1, 0.1)
        self.assertGreater(model.components(features, prior, context)[0][1], 0.8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weights.json'
            model.save(path)
            self.assertEqual(model.components(features, prior, context),
                             Mixture.load(path).components(features, prior, context))

    def test_gradients_match_finite_difference(self):
        features, prior, context = [[0.1, -0.4, 0.3, 0.7], [0.9, 0.2, 0.1, -0.5]], [0.4, 0.6], [1, 0.5, 0.2]
        model = Mixture([0.2, -0.1, 0.4, 0.8])
        old = model.scales[2]
        epsilon = 1e-6
        def loss():
            return -math.log(model.components(features, prior, context)[0][1])
        model.scales[2] = old + epsilon
        high = loss()
        model.scales[2] = old - epsilon
        low = loss()
        model.scales[2] = old
        model.fit_one(features, prior, context, 1, 0.01)
        self.assertAlmostEqual((old - model.scales[2]) / 0.01, (high - low) / (2 * epsilon), places=6)


class BotTests(unittest.TestCase):
    def test_avoids_king_exposure_and_restores_boards(self):
        board = FowBoard('k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1')
        initial = board.fen()
        belief = Belief(True)
        belief.boards = [board]
        bot = Bot(True, depth=1, temperature=0)
        move = bot.choose(belief, fow_moves(board), observation(board, True), 10)
        self.assertNotEqual(move.uci(), 'e2d2')
        self.assertEqual(bot.report['mode'], 'search')
        selected = next(r for r in bot.report['moves'] if r['move'] == move.uci())
        self.assertEqual(selected['loss_probability'], 0)
        self.assertEqual(board.fen(), initial)
        self.assertEqual(board.move_stack, [])

    def test_timeout_and_depletion_fallback_are_legal(self):
        board, belief, bot = FowBoard(), Belief(True), Bot(True)
        legal = fow_moves(board)
        self.assertIn(bot.choose(belief, legal, observation(board, True), 0), legal)
        belief.boards, belief.weights = [], []
        self.assertIn(bot.choose(belief, legal, observation(board, True), 1), legal)

    def test_protocol(self):
        board = FowBoard()
        result = subprocess.run([sys.executable, '-m', 'moe_bot', '--seconds', '0.01'],
                                input='fow\nw 180 2\n' + observation(board, True) + '\n180\n',
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], 'ready')
        self.assertEqual(len(lines), 2)
        self.assertIn(chess.Move.from_uci(lines[1].removeprefix('move ')), fow_moves(board))

    def test_replay_collection_and_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay, data, weights = root / 'game.json', root / 'data.jsonl', root / 'weights.json'
            replay.write_text(json.dumps({'frames': [{'move': None}, {'move': 'e2e4'}, {'move': 'e7e5'}]}))
            collect([replay], data, particles=1000)
            self.assertGreater(len(data.read_text().splitlines()), 0)
            train(data, weights, epochs=2)
            self.assertEqual(len(Mixture.load(weights).scales), 4)


if __name__ == '__main__':
    unittest.main()
