import unittest
import random
import chess
import torch
from referee import FowBoard, observation
from uniform_random import ObservationTracker
from transformer_bot.model import HistoryTransformer, batch_inputs
from transformer_bot.tactics import proven_attackers, tactical_targets, tactical_loss
from transformer_bot.encoding import action_index, ACTION_COUNT
from transformer_bot.benchmark import make_examples


class DiagnosticsTests(unittest.TestCase):
    def test_unknown_ray_is_not_proof_of_attack(self):
        board = FowBoard("k3r3/8/8/8/8/8/8/4K3 w - - 0 1")
        view = list("-" * 64)
        view[chess.E8] = "r"
        view[chess.E1] = "K"
        self.assertEqual(proven_attackers(board, chess.E1, False, view), [chess.E8])
        view[chess.E4] = "?"
        self.assertEqual(proven_attackers(board, chess.E1, False, view), [])

    def test_exposure_labels_have_safe_and_unsafe_alternatives(self):
        board = FowBoard("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        tracker = ObservationTracker(True, rights=0)
        tracker.observe(observation(board, True))
        labels = tactical_targets(tracker)
        self.assertIn(action_index(chess.Move.from_uci("e2d2")), labels["bad"])
        self.assertIn(action_index(chess.Move.from_uci("e2e8")), labels["acceptable"])

    def test_pair_head_forward_backward_and_action_shape(self):
        torch.set_num_threads(1)
        model = HistoryTransformer(width=16, heads=2, layers=1, policy_head="pair")
        examples = make_examples(6)
        logits, value = model(*batch_inputs([(e[0], e[1]) for e in examples], 4))
        self.assertEqual(tuple(logits.shape), (6, ACTION_COUNT))
        loss = tactical_loss(logits, examples) + value.square().mean()
        loss.backward()
        self.assertTrue(torch.isfinite(model.source.weight.grad).all())
        self.assertGreater(float(model.source.weight.grad.abs().sum()), 0)

    def test_benchmark_inputs_are_disjoint_and_labels_legal(self):
        train, held = make_examples(24), make_examples(24, held_out=True)
        self.assertFalse({e[0][0][0] for e in train} & {e[0][0][0] for e in held})
        for e in train + held:
            self.assertTrue(set(e[6]) <= set(e[4]))
            self.assertTrue(e[6])


if __name__ == "__main__":
    unittest.main()
