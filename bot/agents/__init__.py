"""Registry of agent factories by name (used by the protocol and the harness).

Each entry is called as ``factory(side, base, increment, seed, strict=...)``.
Safety variants are sort-key variants of one class, not separate classes.
"""
from __future__ import annotations

from functools import partial
from typing import Callable

from bot.agent import Agent
from bot.agents.baseline_agent import BaselineAgent
from bot.agents.particle_agent import ParticleAgent
from bot.agents.random_agent import RandomAgent
from bot.agents.safety_agent import (BINARY_FIRST, COUNT_FIRST, MATERIAL_FIRST, MATERIAL_ONLY,
                                     SafetyAgent)

REGISTRY: dict[str, Callable[..., Agent]] = {
    "random": RandomAgent,
    "baseline": BaselineAgent,
    # Step 1: exposure from the observation alone.
    "safety": partial(SafetyAgent, key=COUNT_FIRST),
    "safety_binary": partial(SafetyAgent, key=BINARY_FIRST),
    "safety_v2": partial(SafetyAgent, key=MATERIAL_FIRST),
    "safe_material": partial(SafetyAgent, key=MATERIAL_ONLY),
    # Step 2: exposure from the possibility tracker.
    "tracked_v2": partial(SafetyAgent, key=MATERIAL_FIRST, tracked=True),
    "tracked_count": partial(SafetyAgent, key=COUNT_FIRST, tracked=True),
    "tracked_binary": partial(SafetyAgent, key=BINARY_FIRST, tracked=True),
    # Step 3: particle-estimated loss probability (n = 64, uniform, re-expand; ADRs 0016, 0018).
    "particle_v2": partial(ParticleAgent, lam=None),
    "particle_ev100": partial(ParticleAgent, lam=100),
    "particle_ev300": partial(ParticleAgent, lam=300),
    "particle_ev1000": partial(ParticleAgent, lam=1000),
    # Particle-count variants: the timing run and the "does more compute help?" experiment.
    # n32 is also the fast variant for the consistency tests (spec Test 1).
    **{f"particle_ev300_n{n}": partial(ParticleAgent, lam=300, n=n) for n in (32, 128, 256, 512)},
}
