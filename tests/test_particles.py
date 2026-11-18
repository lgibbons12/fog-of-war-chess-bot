"""Particle tracker: scripted scenarios, exactness, and consistency over harness games.

Tests may look at the true board; the tracker never does.
"""
from __future__ import annotations

import random
import unittest

import chess

from bot.particles import (NO_REPETITIONS, CaptureModel, Particle, ParticleTracker, UniformModel,
                           particle_key)
from bot.possibility import EnemyPiece, PossibilityTracker
from bot.safety import apply_move, king_safety
from bot.tracker import ObservationTracker
from harness.game import play_game
from referee import FowBoard, fow_moves, observation, outcome
from test_possibility import exact_pieces, has_matching

UNLIMITED = 10 ** 9


class Script:
    """Drive a particle tracker (and a possibility tracker) for ``side`` through referee moves."""

    def __init__(self, test: unittest.TestCase, fen: str, side: chess.Color, n: int = UNLIMITED,
                 model=None, seed: int = 0):
        self.test, self.side = test, side
        self.board = FowBoard(fen)
        self.possibility = PossibilityTracker(side, pieces=exact_pieces(self.board, not side))
        self.legal = ObservationTracker(side, rights=self.board.castling_rights
                                        & (chess.BB_RANK_1 if side == chess.WHITE else chess.BB_RANK_8))
        self.tracker = ParticleTracker(side, n, model or UniformModel(), random.Random(seed), start=self.board)
        self.ply = 0 if self.board.turn == chess.WHITE else 1
        self.prev = self.last = None
        self.observe()

    def observe(self) -> None:
        obs = observation(self.board, self.side)
        self.possibility.on_observation(obs, self.ply, self.last, self.prev)
        self.legal.observe(obs)
        self.tracker.on_observation(obs, self.ply, self.last, self.possibility, self.legal.rights)
        self.prev = obs

    def play(self, *ucis: str) -> None:
        for uci in ucis:
            move = chess.Move.from_uci(uci)
            self.test.assertIn(move, fow_moves(self.board), f"{uci} in {self.board.fen()}")
            if self.board.turn == self.side:
                self.last = move
                self.legal.record_move(move)
            self.board.push(move)
            self.ply += 1
            self.observe()

    def keys(self) -> list[tuple]:
        return [particle_key(p.board) for p in self.tracker.particles()]

    def assert_truth_present(self) -> None:
        self.test.assertIn(particle_key(self.board), self.keys(), self.board.fen())


def consistent_children(board: FowBoard, side: chess.Color) -> list[chess.Move]:
    """Moves from ``board`` whose result the referee shows to ``side`` exactly as the true move does."""
    result = []
    for move in fow_moves(board):
        board.push(move)
        if outcome(board, NO_REPETITIONS) is None:
            result.append((move, observation(board, side)))
        board.pop()
    return result


class ScriptedParticleTests(unittest.TestCase):
    def test_start_position_is_exact_for_both_sides(self):
        for side in (chess.WHITE, chess.BLACK):
            with self.subTest(side=side):
                board = FowBoard()
                tracker = ParticleTracker(side, UNLIMITED, UniformModel(), random.Random(0))
                tracker.on_observation(observation(board, side), 0, None, None, 0)
                self.assertEqual([particle_key(p.board) for p in tracker.particles()], [particle_key(board)])
                self.assertEqual(tracker.particles()[0].weight, 1.0)

    def test_black_view_after_each_white_first_move(self):
        for model in (UniformModel(), CaptureModel()):
            for first in fow_moves(FowBoard()):
                with self.subTest(model=type(model).__name__, move=first.uci()):
                    s = Script(self, chess.STARTING_FEN, chess.BLACK, model=model)
                    s.play(first.uci())
                    obs = observation(s.board, chess.BLACK)
                    expected = [m for m, o in consistent_children(FowBoard(), chess.BLACK) if o == obs]
                    got = {key: p.weight for key, p in zip(s.keys(), s.tracker.particles())}
                    want = {}
                    for move in expected:
                        board = FowBoard()
                        board.push(move)
                        want[particle_key(board)] = 1.0 / len(expected)  # no captures: models agree
                    self.assertEqual(set(got), set(want))
                    for key, weight in want.items():
                        self.assertAlmostEqual(got[key], weight)

    def test_our_capture_removes_the_piece_in_every_particle(self):
        s = Script(self, "4k3/8/2n5/8/B7/8/8/4K3 w - - 0 1", chess.WHITE)
        s.play("e1d1", "e8d8", "a4c6")
        for particle in s.tracker.particles():
            self.assertEqual(particle.board.piece_at(chess.C6), chess.Piece(chess.BISHOP, chess.WHITE))
            self.assertEqual(len(particle.board.pieces(chess.KNIGHT, chess.BLACK)), 0)
        s.assert_truth_present()

    def test_enemy_capture_keeps_only_children_that_capture_there(self):
        s = Script(self, "3qk3/8/8/3N4/8/8/8/7K b - - 0 1", chess.WHITE)
        s.play("d8d5")
        self.assertTrue(s.tracker.particles())
        for particle in s.tracker.particles():
            piece = particle.board.piece_at(chess.D5)
            self.assertIsNotNone(piece)
            self.assertEqual(piece.color, chess.BLACK)
        s.assert_truth_present()

    def test_enemy_en_passant(self):
        s = Script(self, "4k3/8/8/8/3p4/8/4P3/7K w - - 0 1", chess.WHITE)
        s.play("e2e4", "d4e3")
        for particle in s.tracker.particles():
            self.assertIsNone(particle.board.piece_at(chess.E4))
            self.assertEqual(particle.board.piece_at(chess.E3), chess.Piece(chess.PAWN, chess.BLACK))
        s.assert_truth_present()

    def test_particle_where_our_king_becomes_capturable_is_dropped(self):
        # Two hypotheses for a hidden black rook: g8 (would see g1) or h8 (blocked by our h2 pawn).
        s = Script(self, "k6r/8/8/8/8/8/7P/7K w - - 0 1", chess.WHITE)
        other = FowBoard("k5r1/8/8/8/8/8/7P/7K w - - 0 1")
        self.assertEqual(observation(other, chess.WHITE), observation(s.board, chess.WHITE))
        s.tracker._particles = [Particle(s.board.copy(stack=False), 0.5), Particle(other, 0.5)]
        s.play("h1g1")
        self.assertEqual(s.keys(), [particle_key(s.board)])

    def test_depletion_regenerates_from_possibility_tracker(self):
        # The particle tracker starts from a wrong board: a black rook on a8, which our
        # a2 rook would see. The truth has it on h8, hidden.
        truth = FowBoard("7r/8/8/8/8/8/R7/K6k w - - 0 1")
        wrong = FowBoard("r7/8/8/8/8/8/R7/K6k w - - 0 1")
        obs = observation(truth, chess.WHITE)
        self.assertNotEqual(observation(wrong, chess.WHITE), obs)
        possibility = PossibilityTracker(chess.WHITE, pieces=exact_pieces(truth, chess.BLACK))
        tracker = ParticleTracker(chess.WHITE, 16, UniformModel(), random.Random(0), strict=True, start=wrong)
        possibility.on_observation(obs, 0, None, None)
        tracker.on_observation(obs, 0, None, possibility, 0)
        self.assertEqual(tracker.stats()["depletions"], 1)
        self.assertEqual(tracker.stats()["regenerations"], 1)
        self.assertTrue(tracker.available)
        self.assertIn(particle_key(truth), [particle_key(p.board) for p in tracker.particles()])
        for particle in tracker.particles():
            self.assertEqual(observation(particle.board, chess.WHITE), obs)
            self.assertTrue(has_matching(particle.board, chess.WHITE, possibility.hyps))

    def test_depletion_without_possibility_marks_particles_unavailable(self):
        truth = FowBoard("7r/8/8/8/8/8/8/K6k w - - 0 1")
        wrong = FowBoard("8/8/8/8/8/8/1r6/K6k w - - 0 1")
        tracker = ParticleTracker(chess.WHITE, 16, UniformModel(), random.Random(0), strict=True, start=wrong)
        tracker.on_observation(observation(truth, chess.WHITE), 0, None, None, 0)
        self.assertFalse(tracker.available)
        self.assertIsNone(tracker.loss_probability(chess.Move.from_uci("a1b1")))
        self.assertEqual(tracker.stats()["unavailable_observations"], 1)

    def test_resampling_is_deterministic_and_uses_one_random_call(self):
        class CountingRandom(random.Random):
            calls = 0

            def random(self):
                CountingRandom.calls += 1
                return super().random()

        def resampled(seed: int) -> list[tuple]:
            tracker = ParticleTracker(chess.WHITE, 4, UniformModel(), CountingRandom(seed))
            boards = []
            board = FowBoard()
            for move in fow_moves(board)[:10]:
                board.push(move)
                boards.append(board.copy(stack=False))
                board.pop()
            tracker._particles = [Particle(b, w) for b, w in zip(boards, [0.3, 0.2, 0.1, 0.1, 0.1,
                                                                          0.05, 0.05, 0.04, 0.03, 0.03])]
            tracker._resample(observation(FowBoard(), chess.WHITE))
            return [(particle_key(p.board), p.weight) for p in tracker.particles()]

        CountingRandom.calls = 0
        first = resampled(7)
        self.assertEqual(CountingRandom.calls, 1)
        self.assertEqual(first, resampled(7))
        self.assertLessEqual(len(first), 4)
        self.assertAlmostEqual(sum(w for _, w in first), 1.0)
        for seed in range(20):  # a particle weighing at least 1/n always survives systematic resampling
            self.assertEqual(resampled(seed)[0][0], first[0][0])


def replay_particles(test: unittest.TestCase, replay: dict, side: chess.Color, n: int,
                     max_plies: int | None = None, check_truth: bool = False, **options) -> dict:
    """Replay a harness game through our trackers, checking every invariant against the truth.

    Returns counters. With ``check_truth``, the true board must be among the
    particles at every observation, and the replay stops at the first resampling.
    """
    board = FowBoard()
    possibility = PossibilityTracker(side, strict=True)
    legal = ObservationTracker(side)
    tracker = ParticleTracker(side, n, options.pop("model", UniformModel()), random.Random(replay["plies"]),
                              strict=True, **options)
    last = prev = None
    counts = {"observations": 0, "particle_observations": 0, "decisions": 0, "loss_checks": 0,
              "truth_checks": 0}
    plies = replay["plies"] if max_plies is None else min(max_plies, replay["plies"])
    for ply in range(plies):
        obs = observation(board, side)
        possibility.on_observation(obs, ply, last, prev)
        legal.observe(obs)
        regenerations = tracker.regenerations
        tracker.on_observation(obs, ply, last, possibility, legal.rights)
        counts["observations"] += 1
        particles = tracker.particles()
        test.assertAlmostEqual(sum(p.weight for p in particles), 1.0 if particles else 0.0)
        test.assertLessEqual(len(particles), n)
        test.assertEqual(len({particle_key(p.board) for p in particles}), len(particles))
        for particle in particles:
            test.assertEqual(observation(particle.board, side), obs, f"ply {ply}: {particle.board.fen()}")
            test.assertIsNone(outcome(particle.board, NO_REPETITIONS), particle.board.fen())
            if tracker.regenerations == regenerations:
                test.assertTrue(has_matching(particle.board, side, possibility.hyps),
                                f"ply {ply}: particle {particle.board.fen()} outside tracker supports")
            counts["particle_observations"] += 1
        if check_truth:
            if tracker.resamples:
                break
            test.assertIn(particle_key(board), [particle_key(p.board) for p in particles], f"ply {ply}")
            counts["truth_checks"] += 1
        frame = replay["frames"][ply + 1]
        if board.turn == side:
            moves = legal.legal_moves()
            for particle in particles:
                test.assertEqual(set(fow_moves(particle.board)), set(moves), particle.board.fen())
            if particles:
                counts["decisions"] += 1
                for move in moves:
                    p_loss = tracker.loss_probability(move)
                    report = king_safety(apply_move(obs, move, side), side, possibility)
                    if report.known_loss:
                        test.assertAlmostEqual(p_loss, 1.0, msg=f"{board.fen()} {move}: known loss")
                    elif not report.exposed:
                        test.assertEqual(p_loss, 0.0, f"{board.fen()} {move}: safe but p_loss {p_loss}")
                    counts["loss_checks"] += 1
            last = chess.Move.from_uci(frame["move"])
            legal.record_move(last)
        board.push_uci(frame["move"])
        prev = obs
    counts.update({key: tracker.stats()[key] for key in ("depletions", "regenerations",
                                                         "regeneration_failures", "resamples")})
    return counts


class ParticleConsistencyTests(unittest.TestCase):
    """Spec tests 1-4 over replayed harness games (``tracked_v2`` games until Part B adds agents)."""

    def test_particles_consistent_over_harness_games(self):
        totals: dict[str, int] = {}
        games = 0
        for opponent in ("random", "baseline", "safety_v2"):
            for seed in range(4):  # 4 x 3 opponents x 2 colors = 24 games
                for side in (chess.WHITE, chess.BLACK):
                    white, black = ("tracked_v2", opponent) if side else (opponent, "tracked_v2")
                    with self.subTest(white=white, black=black, seed=seed):
                        counts = replay_particles(self, play_game(white, black, seed, seed + 1100), side, n=32)
                        for key, value in counts.items():
                            totals[key] = totals.get(key, 0) + value
                        games += 1
        self.assertEqual(games, 24)
        self.assertGreater(totals["particle_observations"], 10000)
        self.assertGreater(totals["loss_checks"], 5000)
        print(f"\nparticle consistency: {games} games, {totals}")

    def test_experiment_options_keep_invariants(self):
        variants = [{"trigger": "ess"}, {"recovery": "reexpand"}, {"diversity": True},
                    {"model": CaptureModel()},
                    {"trigger": "ess", "recovery": "reexpand", "diversity": True, "model": CaptureModel()}]
        for options in variants:
            for seed in range(2):
                for white, black in (("tracked_v2", "baseline"), ("baseline", "tracked_v2")):
                    side = chess.WHITE if white == "tracked_v2" else chess.BLACK
                    with self.subTest(options=options, white=white, black=black, seed=seed):
                        replay_particles(self, play_game(white, black, seed, seed + 1300), side, n=32,
                                         **dict(options))

    def test_unlimited_particles_never_lose_the_truth(self):
        checks = 0
        for seed in range(4):
            for white, black in (("tracked_v2", "baseline"), ("baseline", "tracked_v2")):
                side = chess.WHITE if white == "tracked_v2" else chess.BLACK
                with self.subTest(white=white, black=black, seed=seed):
                    counts = replay_particles(self, play_game(white, black, seed, seed + 1200), side,
                                              n=2000, max_plies=16, check_truth=True)
                    checks += counts["truth_checks"]
        self.assertGreater(checks, 40)
        print(f"\nunlimited-n truth checks: {checks}")


if __name__ == "__main__":
    unittest.main()
