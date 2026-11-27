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
    "particle_ev30": partial(ParticleAgent, lam=30),   # grid extension: best of {100,300,1000} was 100
    "particle_ev100": partial(ParticleAgent, lam=100),
    "particle_ev300": partial(ParticleAgent, lam=300),
    "particle_ev1000": partial(ParticleAgent, lam=1000),
    # Ablations of each EV agent: particle count ("does more compute help?") and the capture
    # opponent model. particle_ev300_n32 is also the consistency tests' fast agent (spec Test 1);
    # particle_ev300_n512 was used only by the timing run.
    **{f"particle_ev{lam}_n{n}": partial(ParticleAgent, lam=lam, n=n)
       for lam in (30, 100, 300, 1000) for n in (32, 128, 256)},
    **{f"particle_ev{lam}_capture": partial(ParticleAgent, lam=lam, model="capture")
       for lam in (30, 100, 300, 1000)},
    "particle_ev300_n512": partial(ParticleAgent, lam=300, n=512),
}
