"""stdin/stdout arena protocol driving one registered Agent.

Run as ``python3 -u bot/protocol.py --agent NAME [--seed INT]``. Port of
``uniform_random.main()``. The only stdout lines ever written are ``ready``
and ``move <uci>``; anything else would forfeit, so diagnostics go to stderr.
If the agent raises while choosing, the traceback goes to stderr and the bot
plays a uniformly random legal move instead (fallback guard).
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback

import chess

if __package__ in (None, ""):
    # Run as a script: make the ``bot`` package and ``referee`` (both found in
    # this file's parent directory) importable.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.agent import Agent, NoLegalMoves  # noqa: E402
from bot.agents import REGISTRY  # noqa: E402
from bot.tracker import OBSERVATION_CHARACTERS  # noqa: E402


def fallback_move(agent: Agent) -> chess.Move | None:
    """The random agent's choice from ``agent``'s own tracker, recorded in it.

    Used only when ``choose_move`` raised. ``record_move`` is the last step
    of ``choose_move``, so the tracker has not yet seen any move this turn.
    """
    moves = agent.tracker.legal_moves()
    if not moves:
        return None
    move = agent.rng.choice(moves)
    agent.tracker.record_move(move)
    return move


def main(argv: list[str] | None = None) -> None:
    """Serve one game. Returns (exits) when we have no legal move, like the starters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, choices=sorted(REGISTRY))
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)
    if sys.stdin.readline().strip().lower() != "fow":
        return
    header = sys.stdin.readline().split()
    if len(header) != 3 or header[0].lower() not in ("w", "b"):
        raise ValueError("Expected color, base time, and increment")
    agent = REGISTRY[args.agent](header[0].lower() == "w", float(header[1]),
                                 float(header[2]), args.seed)
    print("ready", flush=True)
    for raw in sys.stdin:
        line = raw.strip()
        if len(line) == 64 and set(line) <= OBSERVATION_CHARACTERS:
            agent.observe(line)
            continue
        try:
            remaining = float(line)
        except ValueError:
            continue
        try:
            move = agent.choose_move(remaining)
        except NoLegalMoves:
            print("no legal moves; exiting", file=sys.stderr, flush=True)
            return
        except Exception:
            traceback.print_exc(file=sys.stderr)
            move = fallback_move(agent)
            if move is None:
                print("no legal moves; exiting", file=sys.stderr, flush=True)
                return
        print("move " + move.uci(), flush=True)


if __name__ == "__main__":
    main()
