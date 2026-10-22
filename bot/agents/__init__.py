"""Registry of agent classes by name (used by the protocol and the harness)."""
from __future__ import annotations

from bot.agent import Agent
from bot.agents.baseline_agent import BaselineAgent
from bot.agents.random_agent import RandomAgent
from bot.agents.safety_agent import SafetyAgent, SafetyBinaryAgent

REGISTRY: dict[str, type[Agent]] = {
    "random": RandomAgent,
    "baseline": BaselineAgent,
    "safety": SafetyAgent,
    "safety_binary": SafetyBinaryAgent,
}
