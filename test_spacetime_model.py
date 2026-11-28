import tempfile
from pathlib import Path
import unittest

import torch

from transformer_bot.model import HistoryTransformer, batch_inputs, load_model, initialize_from
from transformer_bot.encoding import ACTION_COUNT


class SpacetimeTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(47)
        self.model = HistoryTransformer(window=3, width=16, heads=2, layers=1,
                                        policy_head="pair", architecture="spacetime").eval()

    def inputs(self):
        return batch_inputs([([("?" * 64, True), ("-" * 64, False)], True)], 3)

    def test_shapes_gradients_and_history_dependence(self):
        inputs = self.inputs()
        logits, value = self.model(*inputs)
        self.assertEqual(tuple(logits.shape), (1, ACTION_COUNT))
        (logits.square().mean() + value.square().mean()).backward()
        for embedding in (self.model.file, self.model.rank, self.model.time):
            self.assertTrue(torch.isfinite(embedding.weight.grad).all())
            self.assertGreater(float(embedding.weight.grad.abs().sum()), 0)
        changed = tuple(x.clone() for x in inputs)
        changed[0][0, 1, 0] = 2
        with torch.inference_mode():
            new_logits, _ = self.model(*changed)
        self.assertGreater(float((new_logits - logits).abs().max()), 1e-6)

    def test_padding_cannot_change_prediction(self):
        inputs = self.inputs()
        changed = tuple(x.clone() for x in inputs)
        changed[0][0, 0, :] = 2
        changed[1][0, 0] = 1
        with torch.inference_mode():
            first = self.model(*inputs)
            second = self.model(*changed)
        for a, b in zip(first, second):
            torch.testing.assert_close(a, b)

    def test_checkpoint_roundtrip_and_warm_start(self):
        old = HistoryTransformer(window=3, width=16, heads=2, layers=1, policy_head="pair")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.pt"
            torch.save({"config": old.config, "state_dict": old.state_dict()}, path)
            transferred = initialize_from(self.model, path)
            self.assertIn("file.weight", transferred)
            self.assertIn("joint.layers.0.self_attn.in_proj_weight", transferred)
            torch.save({"config": self.model.config, "state_dict": self.model.state_dict()}, path)
            restored = load_model(path)
            with torch.inference_mode():
                for a, b in zip(self.model(*self.inputs()), restored(*self.inputs())):
                    torch.testing.assert_close(a, b)

    def test_expansion_preserves_recent_ages_and_uses_older_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.pt"
            torch.save({"config": self.model.config, "state_dict": self.model.state_dict()}, path)
            config = dict(self.model.config, window=8)
            expanded = HistoryTransformer(**config).eval()
            initialize_from(expanded, path)
            torch.testing.assert_close(expanded.time.weight[-3:], self.model.time.weight)
            short_history = [("?" * 64, True), ("-" * 64, False)]
            with torch.inference_mode():
                a = self.model(*batch_inputs([(short_history, True)], 3))
                b = expanded(*batch_inputs([(short_history, True)], 8))
            for x, y in zip(a, b):
                torch.testing.assert_close(x, y, atol=1e-5, rtol=1e-5)
            history = [("?" * 64, i % 2 == 0) for i in range(8)]
            inputs = batch_inputs([(history, True)], 8)
            changed = tuple(x.clone() for x in inputs)
            changed[0][0, 0, 0] = 2
            with torch.inference_mode():
                before, _ = expanded(*inputs)
                after, _ = expanded(*changed)
            self.assertGreater(float((before - after).abs().max()), 1e-6)


if __name__ == "__main__":
    unittest.main()
