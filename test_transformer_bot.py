"""Run with python -m unittest test_transformer_bot."""
import importlib.util
import unittest

import chess

from referee import FowBoard, observation
from transformer_bot.encoding import PAD, action_index, encode
from transformer_bot.search import Belief, choose_move, material_value


class EncodingTests(unittest.TestCase):
    def test_hidden_empty_padding_and_turn_are_distinct(self):
        tokens, turns, side, valid = encode([("?-" + "P" * 62, False)], True, 2)
        self.assertEqual(tokens[0], [PAD] * 64)
        self.assertNotEqual(tokens[1][0], tokens[1][1])
        self.assertEqual((turns, side, valid), ([0, 0], 1, [False, True]))

    def test_all_promotion_actions_are_distinct(self):
        self.assertEqual(len({action_index(chess.Move.from_uci("a7a8" + suffix))
                              for suffix in "qrbn"}), 4)

    def test_bad_observation_rejected(self):
        with self.assertRaises(ValueError):
            encode([("x" * 64, True)], True)


class SearchTests(unittest.TestCase):
    def test_recovery_replays_known_actions_and_observations(self):
        board = FowBoard()
        belief = Belief(True, capacity=2, reserve=4, recovery_seconds=2)
        belief.observe(observation(board, True))
        move = chess.Move.from_uci("e2e4")
        belief.record_move(move)
        board.push(move)
        belief.pool = []  # Simulate loss of all retained hypotheses.
        belief.observe(observation(board, True))
        self.assertEqual(belief.recoveries, 1)
        self.assertTrue(belief.boards)
        self.assertTrue(all(b.move_stack == [move] for b in belief.boards))
        self.assertTrue(all(observation(b, True) == observation(board, True) for b in belief.boards))

    def test_failed_recovery_does_not_return_stale_boards(self):
        belief = Belief(True, recovery_seconds=0.01)
        belief.observe("-" * 64)
        self.assertEqual(belief.boards, [])
        self.assertEqual(belief.recovery_attempts, 1)

    def test_belief_tracks_both_observation_phases_for_both_colors(self):
        for side in (True, False):
            board = FowBoard()
            belief = Belief(side, capacity=10000)
            belief.observe(observation(board, side))
            for uci in ("e2e4", "e7e5", "g1f3", "b8c6"):
                move = chess.Move.from_uci(uci)
                if board.turn == side:
                    belief.record_move(move)
                board.push(move)
                belief.observe(observation(board, side))
                self.assertTrue(belief.boards)
                self.assertTrue(all(observation(candidate, side) == observation(board, side)
                                    for candidate in belief.boards))
                self.assertTrue(any(candidate.fen() == board.fen() for candidate in belief.boards))

    def test_impossible_observation_exhausts_belief(self):
        belief = Belief(True)
        belief.observe("-" * 64)
        self.assertEqual(belief.boards, [])

    def test_search_avoids_immediate_king_exposure(self):
        # e2 rook shields e1 king from e8 rook; moving sideways loses at once.
        board = FowBoard("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        safe, losing = [chess.Move.from_uci(s) for s in ("e2e8", "e2d2")]
        initial = board.fen()
        result = choose_move([board], [losing, safe], [(observation(board, True), True)],
                             True, lambda h, s, b: material_value(b, s),
                             max_depth=1, seconds=5)
        self.assertEqual(result, safe)
        self.assertEqual(board.fen(), initial)
        self.assertEqual(len(board.move_stack), 0)

    def test_timeout_and_exhaustion_use_legal_policy_fallback(self):
        board = FowBoard()
        a, b = chess.Move.from_uci("e2e4"), chess.Move.from_uci("d2d4")
        for boards in ([], [board]):
            move = choose_move(boards, [a, b], [], True, lambda *args: 0,
                               {a: 0, b: 1}, seconds=0)
            self.assertEqual(move, b)
            self.assertEqual(len(board.move_stack), 0)


@unittest.skipUnless(importlib.util.find_spec("torch"), "PyTorch not installed")
class ModelTests(unittest.TestCase):
    def test_forward_and_training_gradient(self):
        import torch
        from transformer_bot.encoding import ACTION_COUNT
        from transformer_bot.model import HistoryTransformer, batch_inputs
        torch.set_num_threads(1)
        model = HistoryTransformer(window=2, width=16, heads=2, layers=1)
        view = observation(FowBoard(), True)
        inputs = batch_inputs([([(view, True)], True)], 2)
        logits, value = model(*inputs)
        self.assertEqual(tuple(logits.shape), (1, ACTION_COUNT))
        self.assertTrue(torch.isfinite(logits).all())
        self.assertTrue(torch.isfinite(value).all())
        (logits.square().mean() + value.square().mean()).backward()
        self.assertTrue(torch.isfinite(model.symbol.weight.grad).all())


if __name__ == "__main__":
    unittest.main()
