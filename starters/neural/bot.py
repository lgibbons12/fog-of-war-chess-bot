"""Observation-only neural example with optional bounded one-ply value search."""
import json
import sys
import time
from pathlib import Path

started = time.monotonic()
import chess
import numpy as np
import onnxruntime as ort
from baseline import candidates


def encode(observation):
    planes = np.zeros((14, 8, 8), dtype=np.float32)
    symbols = 'PNBRQKpnbrqk?-'
    for square, symbol in enumerate(observation):
        planes[symbols.index(symbol), square // 8, square % 8] = 1
    return planes


def metric(**values):
    print('FOW_BENCH ' + json.dumps(values), file=sys.stderr, flush=True)


def main():
    if input().strip() != 'fow':
        return
    color, _, _ = input().split()
    side = color == 'w'
    metadata = json.loads(Path('policy.json').read_text())
    kind = metadata['kind']
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession('policy.onnx', options, providers=['CPUExecutionProvider'])
    hidden = np.zeros((1, 256), dtype=np.float32)

    def predict(batch, state=None):
        inputs = {'observation': batch}
        if kind == 'recurrent':
            inputs['hidden'] = state
        return session.run(None, inputs)

    predict(np.zeros((1, 14, 8, 8), dtype=np.float32), hidden)
    metric(event='initialized', seconds=time.monotonic() - started,
           kind=kind, parameters=metadata['parameters'],
           runtime='onnxruntime', version=ort.__version__)
    print('ready', flush=True)
    rank = 0 if side else 7
    king = chess.square(4, rank)
    rooks = [chess.square(0, rank), chess.square(7, rank)]
    rights = sum(chess.BB_SQUARES[sq] for sq in rooks)
    current = None
    for raw in sys.stdin:
        line = raw.strip()
        if len(line) == 64:
            current = line
            if current[king] != ('K' if side else 'k'):
                rights = 0
            for rook in rooks:
                if current[rook] != ('R' if side else 'r'):
                    rights &= ~chess.BB_SQUARES[rook]
            continue
        float(line)
        move_started = time.monotonic()
        board, moves = candidates(current, side, rights)
        if not moves:
            return
        logits, _, hidden = predict(encode(current)[None], hidden)
        indices = [m.from_square * 64 + m.to_square for m in moves]
        scores = logits[0, indices]
        evaluated = 1
        if kind == 'search':
            # At most 64 legal candidate moves, one ply, batch size 8.
            # Hypothetical observations retain every unknown square. This
            # illustrative heuristic does not reconstruct the hidden board.
            selected = sorted(range(len(moves)), key=lambda i: float(scores[i]), reverse=True)[:64]
            children = []
            for i in selected:
                move = moves[i]
                view = list(current)
                piece = board.piece_at(move.from_square)
                symbol = chess.Piece(move.promotion, side).symbol() if move.promotion else piece.symbol()
                view[move.from_square], view[move.to_square] = '-', symbol
                if board.is_castling(move):
                    rf, rt = (7, 5) if move.to_square > move.from_square else (0, 3)
                    view[chess.square(rf, rank)] = '-'
                    view[chess.square(rt, rank)] = 'R' if side else 'r'
                children.append(encode(''.join(view)))
            for offset in range(0, len(children), 8):
                _, values, _ = predict(np.stack(children[offset:offset + 8]))
                for j, value in enumerate(values.flatten()):
                    scores[selected[offset + j]] += value
            evaluated += len(children)
        choice = int(scores.argmax())
        move = moves[choice]
        if board.piece_at(move.from_square).piece_type == chess.KING:
            rights = 0
        rights &= ~chess.BB_SQUARES[move.from_square]
        metric(event='move', seconds=time.monotonic() - move_started, evaluations=evaluated)
        print('move ' + move.uci(), flush=True)


if __name__ == '__main__':
    main()
