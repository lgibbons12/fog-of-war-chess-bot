"""Score, Wilson intervals, and termination reasons for a list of GameSummary."""
from __future__ import annotations

from collections import Counter
import math

from harness.match import GameSummary


def a_points(summary: GameSummary) -> float:
    """1, 0.5 or 0 from A's perspective."""
    if summary.result == "1/2-1/2":
        return 0.5
    a_won = (summary.result == "1-0") == (summary.a_color == "white")
    return 1.0 if a_won else 0.0


def wdl(summaries: list[GameSummary]) -> tuple[int, int, int]:
    """(wins, draws, losses) for A. Unfinished ('*') games count as nothing."""
    points = [a_points(s) for s in summaries if s.result != "*"]
    return points.count(1.0), points.count(0.5), points.count(0.0)


def wilson(score: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for proportion ``score`` over ``n`` games."""
    if n == 0:
        return 0.0, 1.0
    denominator = 1 + z * z / n
    centre = (score + z * z / (2 * n)) / denominator
    half = z * math.sqrt(score * (1 - score) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def score_with_ci(summaries: list[GameSummary]) -> tuple[float, float, float, int]:
    """(score, low, high, n) where score = (W + D/2) / N for A."""
    wins, draws, losses = wdl(summaries)
    n = wins + draws + losses
    score = (wins + 0.5 * draws) / n if n else 0.0
    low, high = wilson(score, n)
    return score, low, high, n


def reason_histogram(summaries: list[GameSummary]) -> Counter:
    """Counts of termination reasons."""
    return Counter(s.reason for s in summaries)


def a_moves(summary: GameSummary) -> int:
    """Number of moves A made (White moves on even plies)."""
    return (summary.plies + 1) // 2 if summary.a_color == "white" else summary.plies // 2
