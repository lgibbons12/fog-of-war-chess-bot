"""Stable, lossless square tokens; no language-model tokenizer required."""
import chess

SYMBOLS = "?-PNBRQKpnbrqk"
PAD = len(SYMBOLS)
PROMOTIONS = (None, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
ACTION_COUNT = 64 * 64 * len(PROMOTIONS)


def encode(history, side, window=4):
    """Return tokens [window, 64], side-to-move IDs, observer ID, valid frames.

    History entries are (64-character observation, side to move). Absolute
    a1..h8 coordinates and piece colors are preserved for both observers.
    """
    if not history or window < 1:
        raise ValueError("Need a nonempty history and positive window")
    selected = history[-window:]
    tokens = [[PAD] * 64 for _ in range(window - len(selected))]
    turns = [0] * len(tokens)
    valid = [False] * len(tokens)
    for view, turn in selected:
        if len(view) != 64 or not set(view) <= set(SYMBOLS):
            raise ValueError("Expected 64 square symbols")
        tokens.append([SYMBOLS.index(symbol) for symbol in view])
        turns.append(int(turn))
        valid.append(True)
    return tokens, turns, int(side), valid


def action_index(move):
    return (move.from_square * 64 + move.to_square) * 5 + PROMOTIONS.index(move.promotion)
