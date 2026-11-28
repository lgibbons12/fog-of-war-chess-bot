# Filtered-state mixture-of-experts bot

Run from the repository root, with the existing requirements installed:

```sh
python3 -m moe_bot --particles 256 --depth 2 --seconds 1 --diagnostics
python3 -m moe_bot --stockfish /absolute/path/to/stockfish --seconds 3
python3 -m moe_bot --no-stockfish
python3 -m unittest test_moe_bot test_uniform_random test_transformer_bot
```

The bot discovers Stockfish from `STOCKFISH_PATH`, the executable `PATH`, or the
bundled macOS Stockfish 19 executable, in that order. `--stockfish` overrides
discovery; `--no-stockfish` selects material evaluation. If none is available,
the bot reports that it uses material. No new Python dependencies are added.
This is a repository-run bot, not a standalone submission ZIP: it imports the
root referee, observation tracker, and helpers from the transformer bot package.
The bundled universal macOS executable cannot run on the Linux arena. An arena
deployment needs a compatible Linux binary, Stockfish's GPLv3 source/license
obligations, and testing against the arena's resource limits.

## Decision pipeline

1. Start from the known initial board. Expand every possible opponent move,
   propagate its uniform move-prior mass, and retain only histories whose exact
   observation matches. Process observations before both sides' moves. Our own
   chosen moves are recorded, not inferred. Systematic resampling caps retained
   histories; repetition history, castling and en passant remain attached.
2. Run four experts on the hypothetical states:
   - **Value:** actual Stockfish UCI evaluations of orthodox-valid positions,
     converted from centipawns to bounded values via `tanh(cp / 600)`. Referee
     terminal outcomes always take precedence. Unavailable engine, insufficient
     time, engine failure, or invalid orthodox position uses material instead.
   - **Information:** average newly visible squares after a candidate move for
     state features; entropy of predicted observation groups for move scoring.
     This is an immediate information-gain proxy, not a solved decision-theoretic
     value of information or a model of the opponent's next observation.
   - **Risk:** attacked pieces/king for state features; posterior probability of
     a searched forced loss and lower-side value deviation for every root move.
   - **Time:** branching projection times an online EMA of seconds per visited
     search node. This predicts relative future effort, not a guaranteed runtime.
3. A small trainable MoE produces state probabilities. Each expert contributes
   `softmax(log(prior) + scale * feature)` over states. A contextual softmax gate
   mixes the four distributions using bias, belief entropy and available time.
   Zero-initialized scales preserve the prior until training supplies evidence.
   Good board value alone must not be interpreted as proof a state is likely.
   The posterior is used for this decision; it is not repeatedly multiplied into
   the temporal filter, which would double-count the same learned evidence.
4. Iterative-deepening alpha-beta minimax evaluates each move in each retained
   full board using FOW rules. Only complete root iterations replace the fallback.
   The first iteration uses material at nonterminal leaves so it can finish under
   tight clock budgets; deeper iterations use Stockfish where available. The
   state features still use Stockfish on valid positions.
   Utility combines posterior mean (weight 0.65), worst case (0.35), information
   gain (+0.05), loss probability (-0.3), downside deviation (-0.15), and log
   projected cost (-0.01). `--robustness` changes the mean/worst-case split.
5. Sample a move using softmax utility with `--temperature` (default 0.08; zero
   chooses the maximum). A proven win in every retained state takes priority;
   otherwise moves with detected forced losses are excluded when a move without
   one exists. This guarantee is only relative to retained states/search depth.

`--seed` controls resampling and action sampling. Wall-clock cutoffs can still
change completed depth. `--diagnostics` prints compact reports to stderr;
`Bot.report` also exposes probabilities, features and per-move component scores.
Only protocol messages go to stdout.

The move clock is allocated dynamically: the opening gets 70% of `--seconds`,
the middlegame up to 100%, and a sparse late position 55%, subject to remaining
time and increment. The filter receives a phase- and retained-state-dependent
share of that allowance; the rest is available for move search. Phase uses ply
and visible own material, so it is only a proxy for uncertainty. If a filtering
deadline expires, the bot discards the incomplete belief and uses its legal
observation-only fallback. Deadline checks cannot interrupt a single Python or
engine call, so the budget is not a hard real-time guarantee. Diagnostics show
the chosen phase, budgets and whether the filter timed out.
The default filter retains up to 256 histories; `--particles` changes that cap.
Reaching the cap depends on consistent histories and available filtering time.
A larger cap can increase deadline-triggered fallback and does not guarantee
better coverage.

## Training workflow

Generate varied full-information replays with the local referee (both colors,
several opponents and random seeds). For example:

```sh
python3 referee.py --trusted-local \
  --white 'python3 -m moe_bot --seed 1' \
  --black 'python3 baseline.py --seed 2' \
  --base-time 180 --increment 2 --max-plies 200 --output game.json
python3 -m moe_bot.train collect game.json --output train.jsonl --particles 64
python3 -m moe_bot.train fit train.jsonl --output mixture.json --epochs 20
python3 -m moe_bot --weights mixture.json
```

Pass `--stockfish /absolute/path/to/stockfish` to collection to train with engine
features. Use matching engine settings and feature scales at deployment. Replay
collection reconstructs both players' observations and filters independently;
truth only supplies the supervised label. It reports how often the true history
was retained. Missing-truth cases are counted and skipped, never silently added
to the inference set. This makes coverage an essential metric alongside loss.
Collection currently assumes standard initial positions, as the referee does.

The trainer minimizes negative log probability of the true retained history,
using exact gradients for the four expert scales and contextual gate. This is a
small interpretable trainable MoE, not four pretrained neural networks. The
training command reports training NLL, not validation performance. Split whole
games and opponent identities into train/validation/test sets before collection;
never split adjacent positions from the same game across these sets.

For a reproducible larger experiment using the existing grouped split manifest:

```sh
.venv/bin/python -m moe_bot.experiment --splits data/public-training/splits.json \
  --output experiments/my-moe-run --particles 16 --max-plies 12 \
  --stockfish engines/stockfish-19/stockfish/stockfish-macos-universal
```

This example samples only early-game plies and reports coverage and validation
NLL conditional on the true history surviving. It is not a whole-game estimate.

Recommended next training stages:

- First measure true-state coverage, posterior NLL/Brier score/calibration, and
  effective sample size. Improve particle diversity and learn opponent move
  likelihoods from observation histories before scaling up the gate. No gate
  can recover a state that filtering discarded.
- Distill engine/FOW-search values into a fast value network. Train risk on
  tactical king losses and game outcomes, and the time predictor on measured
  node counts and runtimes on the actual deployment CPU. Stockfish labels are
  useful features, not ground-truth FOW game values.
- Learn information utility from paired rollouts comparing the same underlying
  state with and without an observation update. Entropy reduction alone can
  reward irrelevant information.
- Tune utility weights and temperature on held-out matches, then fine-tune the
  policy with self-play (for example PPO with legal-action masks and a privileged
  training critic). Keep hidden truth out of actor inputs and online inference.
- Evaluate against a frozen opponent pool in both colors: win rate/Elo with
  confidence intervals, illegal-move rate, flag losses, particle depletion,
  and median/p95 move latency. Include ablations removing each expert and the
  robust term; compare against uniform prior, baseline and transformer bot.

## Limits

Finite particles can lose the real board permanently. Exhaustion uses the
observation tracker's legal capture fallback; it does not fabricate a posterior.
There is no rejuvenation/replay-based recovery yet. Search is determinization:
future decisions can exploit hypothetical hidden information (strategy fusion),
so this is not an information-set equilibrium solver. Stockfish uses orthodox
rules even on valid positions and therefore remains an approximate FOW value.
Filtering and individual UCI calls are not hard-real-time cancellable; configured
search limits plus a clock reserve reduce overruns but do not guarantee them.
A costly engine with many particles may finish no full root iteration; reduce
particles/engine time or increase the move budget after profiling. The immediate
information proxy groups terminal branches by result rather than an unavailable
subsequent observation. The training collector uses a fixed initial time model;
logged deployment-time features would improve time-feature calibration.

## Local self-play batches

Use a fresh output directory for each batch:

```sh
.venv/bin/python -m moe_bot.selfplay --output data/my-selfplay --games 8 --seconds 0.5
```

The runner saves each full referee replay, per-game logs, and a manifest with
seeds, settings, results and termination reasons. Add `--stockfish` and/or
`--weights` when ready; `--no-stockfish` forces the material baseline. Games run
sequentially, with a 160-ply default limit and
a five-minute wall-clock timeout per game. Self-play generates data; it does not
update weights during the games. Use the collector and trainer above afterward.
