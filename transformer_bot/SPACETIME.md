# Space-time board attention

The `spacetime` architecture represents a visible history as a conceptual
`time × rank × file` grid, with dimensions `T × 8 × 8`. Each square observation
is a discrete token (colored piece, visible empty, or hidden). The network adds
learned file, rank, relative-time, side-to-move, and observer-color embeddings.
Padding is a separate token and padded frames are excluded as attention keys.

The grid is flattened to `64T` tokens only for the attention implementation.
Its three-dimensional coordinate information remains in the embeddings. Every
token can attend to every other observed square across the window. All supplied
frames precede the current decision, so bidirectional attention within this
history does not expose future observations. This is not an autoregressive
training objective that predicts every historical move from later frames.

Time means observations before successive plies, including opponent turns.
It does not assume that the opponent's hidden UCI move is known. Current-frame
square features feed the source/destination/promotion pair head, and their
pooled features feed the value head. Legal masking and fog-rule search remain
available through the existing protocol bot.

Compared with the old factorized architecture, history is no longer compressed
to one vector per board before temporal interaction. The default window of
four frames creates 256 tokens. Full attention cost grows quadratically in the
number of frames; longer history must be benchmarked against the CPU budget.
There is no geometric 3D renderer or convolution requirement: the three axes
are represented in token positions and attention.

## Training

From the repository root:

```sh
.venv/bin/python -m unittest test_spacetime_model test_transformer_bot test_transformer_training test_transformer_diagnostics
.venv/bin/python -u -m transformer_bot.train --dataset data/combined-tactical/splits.json --architecture spacetime --policy-head pair --window 4 --initialize-from experiments/tactical-large-v1/pair-supervised.pt --epochs 2 --learning-rate 1e-4 --tactical-weight 1 --winners-only --batch-size 16 --output experiments/spacetime-v1/supervised.pt --metrics experiments/spacetime-v1/learning-curve.json
```

`--initialize-from` transfers shape-compatible token/context embeddings, policy
and value heads, and initializes joint attention from the old spatial encoder.
Old square embeddings are approximated by additive file/rank embeddings using
row/column means. Temporal encoder weights are not reused. This is an explicit
architecture warm start, not an exact continuation of the old computation or
optimizer state. `--resume` instead loads an unchanged checkpoint architecture.

Saved checkpoint configuration selects the architecture automatically during
play and self-play. Legacy checkpoints default to `factorized` and remain
compatible. Existing self-play and evaluation CLIs accept space-time checkpoints
without a new protocol or action encoding.

Tests cover finite gradients for all three coordinate embeddings, influence
of earlier observations on current predictions, invariance to padded content,
weight transfer, checkpoint round trips, and compatibility with existing code.

Keep the factorized pair model as the control. A better input representation
is a hypothesis: tactical accuracy, full-game scores, and inference/startup
cost need to be checked before replacing it.

## Longer lookback

History length is stored in each checkpoint and automatically used by the
protocol bot, replay trainer, and self-play collector. Expanding a checkpoint
preserves the most recent learned time embeddings by age. Older slots receive
conservative linear extrapolations of the oldest learned embeddings, then are
adapted through fine-tuning. The extra positions are not pretrained memory.

```sh
.venv/bin/python -m transformer_bot.expand_history --source experiments/spacetime-v1/supervised.pt --output experiments/spacetime-window8/initialized.pt --window 8
.venv/bin/python -u -m transformer_bot.train --dataset data/combined-tactical/splits.json --resume experiments/spacetime-window8/initialized.pt --epochs 1 --learning-rate 3e-5 --tactical-weight 1 --winners-only --batch-size 8 --output experiments/spacetime-window8/finetuned.pt --metrics experiments/spacetime-window8/learning-curve.json
```

Eight frames means the current observation plus seven earlier observations
before successive plies, approximately four full moves of observations. The
first few plies are left-padded. The conceptual grid is 8 × 8 × 8 (512 tokens).
Doubling the window quadruples the number of attention score pairs; overall
runtime also depends on other layers and implementation details. Smaller
training batches reduce memory pressure but do not eliminate this scaling.
The expansion utility supports larger windows as well, but 16 or more frames
should be benchmarked before arena deployment. It refuses to overwrite files.

Using `--resume` retains the checkpoint's window; passing `--window` alone
does not resize a resumed model. Use the expansion utility or `--initialize-from`
with an explicitly configured new model to change it.
