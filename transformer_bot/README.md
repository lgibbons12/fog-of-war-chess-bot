# History-transformer fog chess bot

Experimental local bot: observation tokens → spatial/temporal transformer →
policy/value → alpha-beta search over sampled possible boards. No trained
checkpoint is included, and playing strength has not been established.

## Tokenization choice

The default is the last **four observations**, including opponent-turn
observations, using the existing a1..h8 string. Each square gets one of 14
symbol IDs: 12 colored pieces, visible empty, or hidden. A separate padding
ID represents absent history. Learned embeddings encode square, relative
history position, observer color, and side to move. Spatial attention encodes
each board; temporal attention combines the boards. Both encoders have two
layers, four heads, and width 64. The history window is configurable at training.

There is no BPE/text tokenizer: the small, exact alphabet preserves board
geometry and avoids variable token boundaries. Questions still worth deciding:

- How much history helps relative to CPU cost? Compare 1, 4, 8, and 16 frames.
- Should black's view rotate and swap colors for symmetry? This version keeps
  absolute coordinates, simplifying move labels and debugging.
- Should own actions, castling rights, en passant, and clocks be explicit neural
  features? This version tracks rights/EP for legal moves but does not encode
  them or own action tokens in the network. Longer history alone cannot always
  recover information forgotten outside the window.

The policy has 64 × 64 × 5 actions (ordinary move plus four promotions), masked
to legal moves when training or playing. Value predicts game outcome in [-1,1]
from the observing player's perspective. Transformer weights are learned model
parameters, not one permanent scalar assigned to each board string.

## Run and train

Use a working Python installation with the root requirements installed; add
PyTorch for training or neural inference. Run these commands from the repo root.

```sh
python -m unittest test_uniform_random test_transformer_bot

# Works without PyTorch or a checkpoint; uses material search and captures.
python referee.py --trusted-local \
  --white 'python -m transformer_bot' \
  --black 'python uniform_random.py --seed 1' \
  --max-plies 200 --output game1.json

python referee.py --trusted-local \
  --white 'python uniform_random.py --seed 2' \
  --black 'python -m transformer_bot' \
  --max-plies 200 --output game2.json

python -m transformer_bot.train game1.json game2.json --output transformer.pt

python referee.py --trusted-local \
  --white 'python -m transformer_bot --weights transformer.pt' \
  --black 'python baseline.py' --output evaluation.json
```

Two games only demonstrate the pipeline; they are nowhere near sufficient for
learning a strong policy. The trainer splits entire games (roughly 80/20), uses
cross-entropy for played actions and MSE for final outcomes, and saves the best
validation checkpoint. It rejects unfinished games and protocol failures.
Only the player's observation history enters the network: full replay boards,
opponent observations, and future frames are never input features. All played
actions, including losing ones, are imitation targets by default. Use
`--winners-only` to imitate only winning sides while fitting values to every
outcome. Poor demonstrators can still produce a poor policy. The full dataset
is currently held in memory.

For iterative self-play, generate new replays with the current model plus
search, then train on a mixture of new and older games using `--resume
transformer.pt --output next.pt`. This resumes model weights with a fresh
optimizer. The trainer currently distills the chosen move and realized game
outcome; it does not differentiate through minimax or use search-score targets.
Keep an independent evaluation pool that is never used for checkpoint selection.
For actual reward-based policy learning rather than imitation, use the
[staged training workflow](TRAINING.md).

## Search and its limits

The belief starts at the known initial board. Each observation filters possible
boards; known own moves are applied exactly and unknown opponent moves are
expanded. A reserve retains up to `--reserve` histories (default 32), from which
`--particles` boards (default four) are sampled for search. On exhaustion,
bounded randomized replay from the initial board attempts to reconstruct
histories consistent with every observation and known own move. The default
recovery allowance is 0.2 seconds per observation; `--recovery-seconds` changes
it. Partial replay results are never accepted as current boards.
Board transitions and terminal results use the project's fog rules, including
immediate loss for leaving a capturable king, repetition, and the 50-move rule.
The bot never reads a replay or hidden actual board during play.

Iterative deepening searches each possible board with alpha-beta pruning and
capture ordering, averages scores across boards at the root, and uses the
policy to order root moves. Leaf values use simulated observations of the root
player; without weights, they use material on each hypothesized board. All root
moves are evaluated before adopting an iteration. Defaults are depth two and a
0.5-second search budget. A timeout retains the last completed iteration, or
the highest-scoring legal policy move if no iteration finished.

Important limitations:

- **Strategy fusion:** each search assumes future decisions can exploit its
  particular hidden board. Real players cannot distinguish all those states.
  The opponent is also modeled as knowing that complete board. Averaging these
  searches does not yield a Nash equilibrium or an optimal fog strategy.
- **Particle depletion:** bounded sampling can discard the true history.
  Reconstruction may fail within its time allowance, especially later in a
  game. The legal policy/capture fallback remains active until recovery works.
  More observations trigger fresh attempts; success is not guaranteed.
- **Approximate beliefs:** uniform expansion/resampling is not a calibrated
  posterior against a strategic opponent; retained histories can share boards.
- **CPU cost:** neural evaluation at every leaf is expensive. A short budget
  may finish no full iteration. Filtering, root prediction, and any individual
  inference call are outside or can overrun the cooperative search deadline.
  This is not a hard real-time guarantee. Benchmark before arena submission.
- **Information gathering:** ordinary determinization poorly values scouting,
  concealment, and decisions contingent on future observations. Information-set
  MCTS, belief-aware planning, or regret-minimization methods are better long-term
  directions if those weaknesses dominate.
- **Training bias:** sparse outcomes, weak opponents, correlated self-play games,
  short history, and distribution shift can all dominate architecture gains.
  Fixed-opponent and held-out-opening win rates matter more than training loss.

This is a local research implementation, not yet a standalone arena ZIP. It
imports the root move generator and referee, uses PyTorch directly when weights
are provided, and needs startup/runtime benchmarking against the 15-second
initialization limit. The existing neural starter's ONNX export is a useful
next deployment step. Alpha-beta is one ingredient shared with Stockfish;
this is not a Stockfish-strength engine or a reproduction of its search.

## Recommended training data

1. Generate or collect **actual games under these exact fog rules**, with each
   player's observation at every ply, chosen moves, and final results. Mix
   baseline, random, current search, older checkpoints, and stronger available
   fog bots. Balance colors and retain diverse games.
2. Use full replay boards only as optional privileged supervision for a future
   hidden-piece belief head, never as observation-policy inputs. Evaluate belief
   calibration separately. Preserve histories and only use information available
   at each decision point.
3. Add targeted tactical games for hidden attacks, king exposure, castling,
   en passant, promotions, and safe information gathering. Test against both
   strong and unfamiliar opponents.
4. Ordinary chess PGNs/Stockfish positions can help pretrain piece geometry or
   tactics after applying fog masks. They are a weaker source for final policy:
   orthodox check/checkmate, move legality, opponent information, and objectives
   differ. A full-board Stockfish teacher can recommend moves based on facts
   unavailable to the learner, creating contradictory labels.

Start with thousands of diverse games and learning curves, then scale based on
held-out playing strength. Split by game, preferably also by opponent/version
and opening family, rather than randomly splitting neighboring positions.
