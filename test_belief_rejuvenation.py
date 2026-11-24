"""Tests for the experimental checkpoint-replay belief audit."""
import unittest

import chess
from referee import FowBoard, observation
from moe_bot.coverage_experiment import RejuvenatedBelief


class RejuvenationTests(unittest.TestCase):
    def test_retained_histories_match_all_observations_and_own_moves(self):
        for side in (chess.WHITE, chess.BLACK):
            truth = FowBoard()
            belief = RejuvenatedBelief(side, capacity=8, seed=7)
            views = [observation(truth, side)]
            known = []
            belief.observe(views[0])
            for uci in ('e2e4', 'e7e5', 'g1f3', 'b8c6'):
                move = chess.Move.from_uci(uci)
                own = truth.turn == side
                known.append(move if own else None)
                if own:
                    belief.record_move(move)
                truth.push(move)
                views.append(observation(truth, side))
                belief.observe(views[-1])
            self.assertTrue(belief.pool)
            for candidate in belief.pool:
                self.assertEqual(len(candidate.move_stack), len(known))
                reconstructed = FowBoard()
                self.assertEqual(observation(reconstructed, side), views[0])
                for index, move in enumerate(candidate.move_stack):
                    if known[index] is not None:
                        self.assertEqual(move, known[index])
                    reconstructed.push(move)
                    self.assertEqual(observation(reconstructed, side), views[index + 1])

    def test_impossible_observation_never_reintroduces_stale_board(self):
        belief = RejuvenatedBelief(chess.WHITE, capacity=8, seed=1)
        belief.observe(observation(FowBoard(), chess.WHITE))
        belief.observe('-' * 64)
        self.assertEqual(belief.pool, [])
        self.assertEqual(belief.boards, [])


if __name__ == '__main__':
    unittest.main()
