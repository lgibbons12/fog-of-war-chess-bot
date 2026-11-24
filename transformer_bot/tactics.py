"""Conservative observation-derived tactical labels; not an optimal-move oracle."""
import chess
from uniform_random import candidates
from .encoding import action_index

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2,
          chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def proven_attackers(board, square, enemy, view):
    if square is None:
        return []
    return [attacker for attacker in board.attackers(enemy, square)
            if view[attacker] != "?" and all(view[s] != "?" for s in chess.SquareSet(chess.between(attacker, square)))]


def tactical_targets(tracker):
    board, legal = candidates(tracker.current, tracker.side, tracker.rights, tracker.previous)
    safe, bad, captures, promotions = [], [], {}, []
    for move in legal:
        victim = board.piece_at(move.to_square)
        gain = VALUES[victim.piece_type] if victim else (1 if board.is_en_passant(move) else 0)
        board.push(move)
        unsafe = bool(proven_attackers(board, board.king(tracker.side), not tracker.side, tracker.current))
        exposed = bool(proven_attackers(board, move.to_square, not tracker.side, tracker.current))
        piece = board.piece_at(move.to_square)
        index = action_index(move)
        if unsafe:
            bad.append(index)
        else:
            safe.append(index)
            if move.promotion == chess.QUEEN:
                promotions.append(index)
            if gain > 0:
                captures[index] = gain - (VALUES[piece.piece_type] if exposed else 0)
        board.pop()
    all_indices = [action_index(m) for m in legal]
    if bad and safe:
        return {"kind": "king_safety", "legal": all_indices, "acceptable": safe, "bad": bad}
    if promotions:
        return {"kind": "promotion", "legal": all_indices, "acceptable": promotions, "bad": []}
    if captures and max(captures.values()) > 0:
        best = max(captures.values())
        return {"kind": "capture", "legal": all_indices,
                "acceptable": [a for a, gain in captures.items() if gain == best], "bad": []}
    return {"kind": "none", "legal": all_indices, "acceptable": [], "bad": bad}


def tactical_loss(logits, examples):
    """Negative log probability mass of acceptable moves, within legal moves."""
    import torch
    losses = []
    for row, example in enumerate(examples):
        if len(example) > 6 and example[6]:
            losses.append(torch.logsumexp(logits[row, example[4]], 0) -
                          torch.logsumexp(logits[row, example[6]], 0))
    return torch.stack(losses).mean() if losses else logits.sum() * 0
