"""Particle agents (Step 3 Part B): safety_v2's ordering with a particle-estimated loss probability.

The possibility layer still decides king safety: a known loss always sorts
last (ADR 0008). Among the rest, ``p_loss`` (the weighted fraction of
particles in which the move leaves our king capturable) enters either as a
tie-break after material (``particle_v2``) or as an expected-value penalty
``material - lam * p_loss`` (``particle_ev<lam>``), in material units of
10 x piece value.
"""
from __future__ import annotations

import random
import sys
import time
import traceback

import chess

from bot.agent import NoLegalMoves
from bot.agents.safety_agent import MATERIAL_FIRST, SafetyAgent, material_score
from bot.particles import MODELS, ParticleTracker
from bot.safety import apply_move, king_safety

# Below this many seconds on our clock, particles are switched off for the rest
# of the game and moves are ranked exactly as safety_v2 ranks them (ADR 0017).
TIME_GUARD_SECONDS = 20.0

# Default tracker configuration: ADR 0016, with n from the Part B timing run (ADR 0018).
DEFAULT_N = 64
DEFAULT_RECOVERY = "reexpand"


class ParticleAgent(SafetyAgent):
    """Safety agent whose ranking adds a particle-estimated ``p_loss``.

    ``lam=None`` gives ``particle_v2``: key ``(known_loss, -material, p_loss,
    exposure, rng)``. Otherwise the key is ``(known_loss, -(material - lam *
    p_loss), exposure, rng)``.

    Invariants:
    - exactly one ``self.rng.random()`` call per legal move, in tracker order
      (the particle tracker has its own ``random.Random``, seeded from
      ``self.rng`` once at construction);
    - when particles are unavailable (depleted, or switched off), ``p_loss`` is
      ``float(exposure_count > 0)`` for that decision ("unavailable" mode);
    - once the time guard fires, or (outside strict mode) the particle code
      raises, particles stay off and the key is safety_v2's ("time_guard" /
      "error" mode). In strict mode particle exceptions propagate.

    ``last_scores`` holds ``(move, report, p_loss)`` for every legal move of
    the last decision (for tests; not part of the decision record).
    """

    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None,
                 strict: bool = False, *, lam: float | None = None, n: int = DEFAULT_N,
                 model: str = "uniform", recovery: str = DEFAULT_RECOVERY):
        super().__init__(side, base, increment, seed, strict, key=MATERIAL_FIRST, tracked=True)
        self.lam = lam
        self.particles: ParticleTracker | None = ParticleTracker(
            side, n, MODELS[model](), random.Random(self.rng.getrandbits(64)), strict=strict,
            recovery=recovery)
        self.off_reason: str | None = None   # "time_guard" or "error" once particles are off
        self.particle_seconds = 0.0          # particle update time since the last decision
        self.last_scores: list[tuple[chess.Move, object, float]] = []

    def observe(self, obs: str) -> None:
        super().observe(obs)
        if self.particles is None:
            return
        try:
            self.particles.on_observation(obs, self.ply, self.last_move, self.possibility,
                                          self.tracker.rights)
            self.particle_seconds += self.particles.last_update_seconds
        except Exception:
            self._switch_off("error")

    def _switch_off(self, reason: str) -> None:
        """Stop using particles for the rest of the game (re-raises in strict mode on errors)."""
        if reason == "error":
            if self.strict:
                raise
            traceback.print_exc(file=sys.stderr)
        print(f"particles off at ply {self.ply}: {reason}", file=sys.stderr, flush=True)
        self.particles = None
        self.off_reason = reason

    def _select(self, remaining: float) -> chess.Move:
        started = time.perf_counter()
        obs = self.tracker.current
        moves = self.tracker.legal_moves()
        if not moves:
            raise NoLegalMoves()
        if self.particles is not None and remaining < TIME_GUARD_SECONDS:
            self._switch_off("time_guard")
        mode = self.off_reason or ("particles" if self.particles.available else "unavailable")
        scored = []
        for move in moves:
            cells = apply_move(obs, move, self.side)
            report = king_safety(cells, self.side, self.possibility)
            material = material_score(obs, cells, move, self.side)
            p_loss = None
            if mode == "particles":
                try:
                    p_loss = self.particles.loss_probability(move)
                except Exception:
                    self._switch_off("error")
                    mode = "error"
            if p_loss is None:
                p_loss = float(bool(report.exposed))
            scored.append([move, report, material, p_loss])
        if mode == "error":  # an error mid-loop: rank everything as safety_v2 does
            for item in scored:
                item[3] = float(bool(item[1].exposed))
        keyed = []
        for move, report, material, p_loss in scored:
            exposure = len(report.exposed)
            if mode in ("time_guard", "error"):
                key = (report.known_loss, -material, exposure)
            elif self.lam is None:
                key = (report.known_loss, -material, p_loss, exposure)
            else:
                key = (report.known_loss, -(material - self.lam * p_loss), exposure)
            keyed.append((key + (self.rng.random(),), move, report, p_loss))
        _, move, report, p_loss = min(keyed, key=lambda item: item[0])
        self.last_scores = [(m, r, p) for _, m, r, p in keyed]
        safe_exposures = [len(r.exposed) for _, _, r, _ in keyed if not r.known_loss]
        stats = self.particles.stats() if self.particles is not None else None
        self.last_decision = {
            "move": move,
            "report": report,
            "legal_moves": len(moves),
            "non_losing_moves": len(safe_exposures),
            "min_exposure": min(len(r.exposed) for _, _, r, _ in keyed),
            "min_safe_exposure": min(safe_exposures, default=None),
            "exposed_types": self._exposed_types(report),
            "tracker": self._tracker_stats(obs),
            "update_seconds": self.update_seconds,
            "particle_mode": mode,
            "p_loss": p_loss,
            "min_p_loss": min(p for _, _, _, p in keyed),
            "min_safe_p_loss": min((p for _, _, r, p in keyed if not r.known_loss), default=None),
            "particles": None if stats is None else {
                key: stats[key] for key in ("distinct", "ess", "depletions", "regenerations",
                                            "regeneration_failures", "reexpansions", "resamples")},
            "particle_update_seconds": self.particle_seconds,
            "decision_seconds": time.perf_counter() - started,
        }
        self.update_seconds = []
        self.particle_seconds = 0.0
        return move
