# Staged training workflow

Run from the repository root using a Python environment with python-chess and
PyTorch. On the development machine, use `.venv/bin/python`. Nothing here
uploads or activates a model in the arena. Training outputs are candidates;
evaluation never automatically promotes them.

## 1. Belief recovery

The protocol bot keeps a reserve of 32 observation-consistent histories and
samples four for search. If depleted, it retries randomized reconstruction
from the initial board using all received observations and known own moves.
Only complete reconstructions are accepted. The default 0.2-second recovery
budget is cooperative, and the rest of filtering/inference also costs time.
This improves resilience but does not guarantee recovery or eliminate the
imperfect-information limitations of determinization.

```sh
.venv/bin/python -m unittest test_uniform_random test_transformer_bot test_transformer_training
```

## 2. Public-data pretraining

```sh
.venv/bin/python -m transformer_bot.download_replays --count 100 --pages 3 --output data/public-training
.venv/bin/python -m transformer_bot.dataset data/public-training/manifest.json --output data/public-training/splits.json
.venv/bin/python -u -m transformer_bot.train --dataset data/public-training/splits.json --winners-only --epochs 2 --batch-size 16 --output data/public-training/pretrained.pt
```

The downloader uses the [documented public API](https://www.mit.edu/~6.7980/fow/api.html),
no credentials, cached replays, cursor pagination, one request per second,
bounded retries, and normal chess terminations only. It does not rank historical
players by current Elo. The dataset builder checks moves, observation streams,
and outcomes against local rules, removes duplicate move sequences, groups
games by unordered opponent pair, and saves content hashes with fixed splits.
The trainer verifies hashes and split disjointness. Test games are never used
by training or validation checkpoint selection. Team pairs are disjoint, but
individual teams and similar openings can occur across splits.

`--winners-only` masks losing/drawn action-imitation losses; their value targets
remain active. Winning actions are a bootstrap heuristic, not optimal-move
labels. Without this option, all actions are imitated. For a fresh experiment,
use a new output directory to preserve data and split manifests.

## 3. On-policy self-play

```sh
.venv/bin/python -u -m transformer_bot.selfplay --initial data/public-training/pretrained.pt --output experiments/rl-pilot --iterations 2 --games-per-iteration 6 --max-plies 200
```

This is Monte Carlo actor-critic: reward is +1/-1/0 for a terminal win/loss/draw,
the advantage is reward minus the detached value estimate, and a small entropy
bonus encourages exploration. The value head fits outcomes. A single gradient
update follows each batch of newly sampled games; old rollouts are not reused
as though they were on-policy. Dropout is disabled for collection and gradient
computation to keep action distributions consistent. Gradients are clipped,
and nonfinite losses/gradients fail explicitly.

Opponents include random and capture policies, the frozen initial checkpoint,
and a bounded pool of later snapshots. `--opponents old.pt ...` adds archived
models. Each selected opponent plays against the learner in both colors.
The full board is used by the environment to apply rules and compute terminal
outcomes, while agents receive only their observation history and legal mask.

Search is excluded from these rollouts: replacing a sampled action with a
minimax choice would invalidate its policy-gradient probability. Search can
still be used during deployment and separately evaluated. Rollouts reaching
the training ply cap without a terminal result are saved as unfinished and
excluded from updates, not labeled draws. This exclusion biases training toward
shorter games; increase the cap and monitor truncation rates for serious runs.
The pilot uses uniform weighting of observed decision steps and gamma=1.

The output directory must be new. Each iteration saves a checkpoint, full
replays, and metrics. `--initial` loads weights only; it starts a fresh optimizer
and opponent pool. This is not a complete optimizer/RNG-state resume facility.

## 4. Independent evaluation

```sh
.venv/bin/python -u -m transformer_bot.evaluate --candidate experiments/rl-pilot/checkpoint-001.pt --reference data/public-training/pretrained.pt --output experiments/eval-pilot --seeds 101 --dataset data/public-training/splits.json
```

The runner uses the actual subprocess protocol/referee at 180+2, both colors,
and a 1,000-ply limit against random, baseline, and the reference checkpoint.
It saves each replay, results, failure flags, warnings, and checkpoint hashes.
Optional held-out metrics report value MSE and NLL of all recorded actions;
these are not directly comparable to the winners-only training objective.
Policy-only evaluation is the default. Add `--search` in a separate output
directory to evaluate search and belief recovery as deployed.

One seed is a smoke test, not evidence of improvement. Use many fixed seeds,
both colors, archived opponents, and additional diverse openings before
selecting a model. Keep a final untouched test set for final decisions: repeatedly
tuning to this report effectively turns its test set into validation data.
Compare both playing strength and protocol/time reliability. The script does
not infer statistical significance or overwrite an active model.

Large downloads and long training runs are explicit CLI choices. The initial
run is deliberately limited to 100 games, two supervised epochs, and a short
RL pilot so cost and failure modes can be inspected before scaling.

## Controlled learning-rate comparisons

`selfplay` now accepts `--learning-rate`, `--fixed-opponents`, and
`--stationary-pool`. The latter freezes the opponent set instead of appending
learner snapshots, so candidates can be compared under the same curriculum.
For example, run each rate (1e-5, 1e-4, 3e-4) into a distinct output directory:

```sh
.venv/bin/python -u -m transformer_bot.selfplay --initial experiments/rl-pilot/checkpoint-001.pt --opponents data/public-training/pretrained.pt --output experiments/example-lr-run --iterations 8 --games-per-iteration 12 --max-plies 300 --seed 9011 --learning-rate 1e-4 --stationary-pool --fixed-opponents capture tactical search
```

The tactical opponent performs one-ply evaluation of the visible-piece board,
penalizes king exposure and attacked destination pieces, and rewards captures
and promotions. Unknown squares are placeholders, so unseen blockers can cause
conservative threat estimates. It never receives hidden ground truth. The
search opponent adds bounded depth-two minimax over observation-consistent
beliefs, with tactical fallback. Its default search budget is 0.03 seconds,
two search particles, eight reserve histories, and no recovery. Clock cutoffs
make search behavior sensitive to scheduling and hardware.

Use `evaluate --tactical-opponents` to include both opponents in the existing
both-color protocol suite. Always evaluate the unchanged starting checkpoint
on the same seeds. Common seeds and a stationary pool do not produce identical
trajectories once policies differ. They control initialization and opponent
selection, not every source of variability. Greedy neural-reference matches
are deterministic, so repeated seeds do not make independent games against
that reference. Small sweeps select candidates for further testing, not proven
best learning rates. No evaluated model is automatically activated.
