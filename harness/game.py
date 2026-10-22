"""In-process game loop that mirrors ``referee.run_match`` exactly."""
from __future__ import annotations

from collections import Counter
import dataclasses
import re
import time
import traceback

import chess

from bot.agent import NoLegalMoves
from bot.agents import REGISTRY
from referee import FowBoard, fow_moves, make_frame, observation, outcome, position_key

BASE_SECONDS = 180.0
INCREMENT_SECONDS = 2.0
MOVE_PATTERN = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")


def jsonable(value):
    """Convert an agent's decision record to plain JSON types.

    Moves become UCI strings, dataclasses dicts, sets sorted lists.
    """
    if isinstance(value, chess.Move):
        return value.uci()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted(jsonable(item) for item in value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def play_game(white: str, black: str, seed_white: int, seed_black: int,
              max_plies: int = 1000, record_frames: bool = True, strict: bool = True) -> dict:
    """Play one game between two registered agents and return a replay dict.

    Loop order per ply matches ``referee.run_match``: ``outcome`` -> ply cap ->
    observation to White then Black -> mover chooses with its clock ->
    legality check -> push -> repetition count. Agents receive only
    ``observation(board, side)`` strings and a float clock. Clocks are
    simulated (base - think + increment) but never forfeit.

    ``NoLegalMoves`` and illegal or malformed moves always become losses with
    the referee's reason text. Other agent exceptions propagate when
    ``strict`` (so bugs fail loudly); otherwise they become "Bot exited"
    losses, which is what the subprocess referee would record.

    Returns ``white``/``black`` agent names, ``result``, ``reason``, ``frames``
    (referee schema with ``clocks`` replaced by ``thinkSeconds`` plus the
    mover's ``decision`` record, if it keeps one; empty if ``record_frames``
    is false), ``plies``, ``thinkSeconds`` (per-side lists of move times),
    and on a bot failure ``failedSide`` and ``error`` (diagnostics only).
    """
    board = FowBoard()
    clocks = [BASE_SECONDS, BASE_SECONDS]
    think: list[list[float]] = [[], []]
    replay = {"white": white, "black": black, "result": "*", "reason": "In progress", "frames": []}

    def add_frame(move_uci, seconds, decision):
        if record_frames:
            frame = make_frame(board, clocks, move_uci)
            del frame["clocks"]
            frame["thinkSeconds"] = seconds
            frame["decision"] = jsonable(decision)
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

    add_frame(None, None, None)
    agents = []
    for index, (name, seed) in enumerate([(white, seed_white), (black, seed_black)]):
        try:
            agents.append(REGISTRY[name](index == 0, BASE_SECONDS, INCREMENT_SECONDS, seed))
        except Exception:
            if strict:
                raise
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
                if strict:
                    raise
                return loss(index, "Bot exited", traceback.format_exc())
        index = 0 if board.turn else 1
        started = time.perf_counter()
        try:
            uci = agents[index].choose_move(clocks[index]).uci()
        except NoLegalMoves:
            # The subprocess starters just exit, which the referee sees as an exit.
            return loss(index, "Bot exited", "NoLegalMoves")
        except Exception:
            if strict:
                raise
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
        add_frame(uci, elapsed, getattr(agents[index], "last_decision", None))
