"""Tests for outcome-based learning, masking, and data isolation."""
import json
import hashlib
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

import torch

from referee import FowBoard, make_frame
from transformer_bot.dataset import validate_replay, split_paths
from transformer_bot.model import HistoryTransformer
from transformer_bot.selfplay import actor_critic_loss, distribution, play_episode, update


class TrainingTests(unittest.TestCase):
    def test_tactical_opponent_avoids_visible_king_exposure(self):
        import chess
        from referee import observation
        from uniform_random import ObservationTracker
        from transformer_bot.opponents import Opponent
        board = FowBoard("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1")
        tracker = ObservationTracker(True, rights=0)
        tracker.observe(observation(board, True))
        safe, losing = [chess.Move.from_uci(s) for s in ("e2e8", "e2d2")]
        agent = Opponent(True)
        self.assertEqual(agent.choose(tracker, [(tracker.current, True)], [losing, safe]), safe)

    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_positive_and_negative_rewards_push_selected_action_opposite_ways(self):
        for reward, expected in ((1.0, -1), (-1.0, 1)):
            logits = torch.zeros(1, 3, requires_grad=True)
            loss = actor_critic_loss(logits, torch.zeros(1), torch.tensor([0]),
                                     torch.tensor([reward]), [[0, 1]], entropy_weight=0)
            loss.backward()
            self.assertEqual(int(torch.sign(logits.grad[0, 0])), expected)
            self.assertEqual(float(logits.grad[0, 2]), 0)

    def test_illegal_action_has_zero_probability(self):
        policy = distribution(torch.tensor([[0.0, 100.0, 0.0]]), [[0, 2]])
        self.assertEqual(float(policy.probs[0, 1]), 0)

    def test_losing_demonstration_updates_value_but_not_policy_head(self):
        from transformer_bot.train import loss_for
        from referee import observation
        model = HistoryTransformer(width=16, heads=2, layers=1).eval()
        view = observation(FowBoard(), True)
        example = ([(view, True)], True, 1, -1.0, [1, 2], 0.0)
        loss_for(model, [example], "cpu").backward()
        self.assertEqual(float(model.policy.weight.grad.abs().sum()), 0)
        self.assertGreater(float(model.value.weight.grad.abs().sum()), 0)

    def test_rollout_cutoff_is_not_a_draw_training_target(self):
        model = HistoryTransformer(width=16, heads=2, layers=1).eval()
        transitions, replay = play_episode(model, "random", True, random.Random(0), max_plies=1)
        self.assertEqual(transitions, [])
        self.assertTrue(replay["truncated"])
        self.assertEqual(replay["result"], "*")

    def test_environment_rejects_corrupt_observations(self):
        board = FowBoard()
        frames = [make_frame(board, [0, 0])]
        board.push_uci("e2e4")
        frames.append(make_frame(board, [0, 0], "e2e4"))
        frames[0]["white"] = "?" * 64
        with self.assertRaises(ValueError):
            validate_replay(dict(frames=frames, result="1/2-1/2", reason="Move limit reached"))

    def test_changed_dataset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.json"
            path.write_text("changed")
            manifest = Path(directory) / "split.json"
            manifest.write_text(json.dumps({"splits": {"train": [{"path": str(path), "sha256": "wrong", "pair": ["a", "b"]}],
                                                       "validation": [], "test": []}}))
            with self.assertRaises(ValueError):
                split_paths(manifest)

    def test_opponent_pair_cannot_cross_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = []
            for name in ("a", "b"):
                source = Path(directory) / (name + ".json")
                source.write_text(name)
                entries.append({"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                "pair": ["same", "opponents"]})
            manifest = Path(directory) / "split.json"
            manifest.write_text(json.dumps({"splits": {"train": entries[:1], "validation": entries[1:], "test": []}}))
            with self.assertRaises(ValueError):
                split_paths(manifest)

    def test_selfplay_cli_saves_reproducible_metadata_and_checkpoint(self):
        from transformer_bot.selfplay import main
        with tempfile.TemporaryDirectory() as directory:
            initial = Path(directory) / "initial.pt"
            output = Path(directory) / "run"
            model = HistoryTransformer(width=16, heads=2, layers=1)
            torch.save({"config": model.config, "state_dict": model.state_dict()}, initial)
            argv = ["selfplay", "--initial", str(initial), "--output", str(output),
                    "--iterations", "1", "--games-per-iteration", "2", "--max-plies", "1",
                    "--learning-rate", "0.0003", "--stationary-pool", "--fixed-opponents", "tactical"]
            with patch("sys.argv", argv), redirect_stdout(io.StringIO()):
                main()
            metadata = json.loads((output / "experiment.json").read_text())
            self.assertEqual(metadata["initial_sha256"], hashlib.sha256(initial.read_bytes()).hexdigest())
            self.assertEqual(metadata["learning_rate"], 0.0003)
            self.assertTrue(metadata["stationary_pool"])
            metrics = json.loads((output / "metrics.json").read_text())
            self.assertEqual(metrics[0]["transitions"], 0)
            self.assertIsNone(metrics[0]["loss"])
            saved = torch.load(output / "checkpoint-000.pt", weights_only=True)
            for key, value in model.state_dict().items():
                self.assertTrue(torch.equal(value, saved["state_dict"][key]))


if __name__ == "__main__":
    unittest.main()
