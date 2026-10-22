"""In-process game loop that mirrors ``referee.run_match`` exactly."""
from __future__ import annotations

from collections import Counter
import re
import time
import traceback

import chess

from bot.agents import REGISTRY
from referee import FowBoard, fow_moves, make_frame, observation, outcome, position_key

BASE_SECONDS = 180.0
INCREMENT_SECONDS = 2.0
MOVE_PATTERN = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")


def play_game(white: str, black: str, seed_white: int, seed_black: int,
              max_plies: int = 1000, record_frames: bool = True) -> dict:
    """Play one game between two registered agents and return a replay dict.

    Loop order per ply matches ``referee.run_match``: ``outcome`` -> ply cap ->
    observation to White then Black -> mover chooses with its clock ->
    legality check -> push -> repetition count. Agents receive only
    ``observation(board, side)`` strings and a float clock. Clocks are
    simulated (base - think + increment) but never forfeit. Any agent error
    becomes a loss with the referee's reason text, so a game never raises.

    Returns ``result``, ``reason``, ``frames`` (referee schema with ``clocks``
    replaced by ``thinkSeconds``; empty if ``record_frames`` is false),
    ``plies``, ``thinkSeconds`` (per-side lists of move times), and on a bot
    failure ``failedSide`` and ``error`` (traceback text, diagnostics only).
    """
    board = FowBoard()
    clocks = [BASE_SECONDS, BASE_SECONDS]
    think: list[list[float]] = [[], []]
    replay = {"result": "*", "reason": "In progress", "frames": []}

    def add_frame(move_uci, seconds):
        if record_frames:
            frame = make_frame(board, clocks, move_uci)
            del frame["clocks"]
            frame["thinkSeconds"] = seconds
            replay["frames"].append(frame)

    def finish(result, reason, failed_index=None, error=None):
        replay.update(result=result, reason=reason, plies=len(board.move_stack),
                      thinkSeconds={"white": think[0], "black": think[1]})
        if failed_index is not None:
            replay["failedSide"] = "white" if failed_index == 0 else "black"
        if error is not None:
            replay["error"] = error
        return replay

    def loss(index, reason, error=None):
        return finish("0-1" if index == 0 else "1-0", reason, index, error)

    add_frame(None, None)
    agents = []
    for index, (name, seed) in enumerate([(white, seed_white), (black, seed_black)]):
        try:
            agents.append(REGISTRY[name](index == 0, BASE_SECONDS, INCREMENT_SECONDS, seed))
        except Exception:
            return loss(index, "Bot startup failed: Bot exited before completing startup",
                        traceback.format_exc())
    repetitions = Counter({position_key(board): 1})
    while True:
        terminal = outcome(board, repetitions)
        if terminal:
            return finish(*terminal)
        if len(board.move_stack) >= max_plies:
            return finish("1/2-1/2", "Move limit reached")
        for index, side in enumerate([chess.WHITE, chess.BLACK]):
            try:
                agents[index].observe(observation(board, side))
            except Exception:
                return loss(index, "Bot exited", traceback.format_exc())
        index = 0 if board.turn else 1
        started = time.perf_counter()
        try:
            # NoLegalMoves lands here too: the subprocess starters just exit.
            uci = agents[index].choose_move(clocks[index]).uci()
        except Exception:
            return loss(index, "Bot exited", traceback.format_exc())
        elapsed = time.perf_counter() - started
        think[index].append(elapsed)
        clocks[index] -= elapsed
        # The referee normalizes to lowercase and rejects malformed text first.
        uci = uci.lower()
        if not MOVE_PATTERN.fullmatch(uci):
            return loss(index, "Malformed move response")
        move = chess.Move.from_uci(uci)
        if move not in fow_moves(board):
            return loss(index, f"Illegal move: {uci}")
        board.push(move)
        clocks[index] += INCREMENT_SECONDS
        repetitions[position_key(board)] += 1
        add_frame(uci, elapsed)
