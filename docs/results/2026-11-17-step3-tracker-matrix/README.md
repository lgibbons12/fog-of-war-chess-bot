# Step 3 particle-tracker decision matrix (2026-11-17)

**Question.** Which particle-tracker configuration should Step 3 use? This run covers every open Part A decision at once:

- particle count `n` ∈ {32, 64, 128, 256, 512};
- opponent model: `uniform` or `capture`;
- resampling trigger: `above_n` (ADR 0015) or `ess` (draft spec);
- depletion recovery: `supports` (spec) or `reexpand` (log option c);
- resampling: plain systematic (`sys`) or king-ring diversity (`div`, log option d).

That's 80 configurations. Each is scored against the true board on the **same 60 replayed games**, plus a reference row scoring the Step 2 possibility tracker as a predictor. The λ grid needs the Part B agents, so it is not covered here.

Context: `docs/step-3-particles.md`, `docs/log.md` § Step 3 Part A, ADRs 0014, 0015 and 0016.

## Method

- **Games:** `tracked_v2` against `random`, `baseline` and `safety_v2`, both colors, seeds 0–9: 60 games in total.
  - The games are played once with `harness.game.play_game(white, black, seed, seed + 5000)` and replayed for every configuration.
  - The tracker is passive (it doesn't choose moves), so replaying is valid. But these are *not* games played by a particle agent; Part B will measure that.
- **Paired comparisons:** each game's tracker RNG is `random.Random(f"matrix:{white}:{black}:{seed}")`, identical across configurations.
- **Scoring:** at each of our 1,255 decisions, every legal move (27,509 in total) gets `p_loss` from the tracker. It is compared with whether that move really leaves our king capturable on the true board (`outcome()`): 1,177 moves (4.3%) do.
- **Metrics:**
  - **Brier score and log loss** of `p_loss` (p clipped to [1e-4, 1 − 1e-4]).
  - **Calibration buckets.**
  - **Missed losses:** the fraction of losing moves given `p_loss = 0`.
  - **Min-risk pick loses:** the fraction of decisions where the lowest-`p_loss` move loses even though a safe move existed.
  - **Truth coverage:** the fraction of observations where the true board is among the particles.
  - **Depletions per game.**
  - **Time per move:** both tracker updates since our last decision, plus scoring every legal move.
- **Possibility reference:**
  - p = 1 for known losses;
  - p = 0.051 for exposed moves (the pooled loss rate of exposed moves, fitted to this same data, which flatters the reference);
  - p = 0 otherwise.

  Its "min-risk pick" takes the lowest `(known_loss, exposure_count)` move.
- **Machine:** WSL Ubuntu, 22 cores, Python 3.12.
  - **Matrix:** 20 workers, 2,188 s. Its timings are inflated by contention, so they're kept only for relative comparison.
  - **Timing run:** one worker, `n` grid × recovery with the other options at their defaults, on the first 12 games (seeds 0–1), 333 s.

**Commands** (from the repo root, Linux venv):

```sh
python -m harness.particle_matrix --out docs/results/2026-11-17-step3-tracker-matrix --seeds 10 --workers 20
python -m harness.particle_matrix --out docs/results/2026-11-17-step3-tracker-matrix --seeds 2 --timing
python -m harness.matrix_report  docs/results/2026-11-17-step3-tracker-matrix > .../tables.md
python -m harness.matrix_compare docs/results/2026-11-17-step3-tracker-matrix > .../comparisons.md
```

**Files:**

| File | Contents |
|---|---|
| `matrix_raw.jsonl.gz`, `timing_raw.jsonl.gz` | One row per (configuration, game) |
| `*_summary.csv` | Per-configuration aggregates |
| `*_calibration.csv` | Calibration buckets |
| `*_meta.json` | Game list, command, elapsed time |
| `tables.md` | Main effects, top-10s, all configurations, timing |
| `comparisons.md` | Paired bootstrap confidence intervals |

## Findings

All of these are **verified** on this data unless marked otherwise.

### 1. Particles predict king-capture risk much better than the possibility tracker

| Predictor | Brier ×100 | Log loss | Min-risk pick loses |
|---|---|---|---|
| Possibility tracker (Step 2; calibrated in-sample) | 1.841 | 0.0764 | 8 / 1,255 |
| Particles, n = 128, spec defaults | 0.723 | 0.0291 | 4 / 1,255 |
| Particles, n = 256, uniform, above_n, reexpand | 0.602 | 0.0222 | 3 / 1,255 |

- **The Brier score falls by a factor of 2.5–3** compared with the most generous possibility baseline. This is the main Step 3 result so far.
- **The "min-risk pick" counts are too small to compare.** A move that loses despite a safe alternative almost never happens for any predictor, because the known-loss check already removes most losing moves.

**Calibration** (n = 128, spec defaults; `calibration.csv` has every configuration):

| p_loss bucket | 0 | (0, .01] | (.01, .05] | (.05, .2] | (.2, .5] | (.5, 1) | 1 |
|---|---|---|---|---|---|---|---|
| Moves | 23,563 | 593 | 1,197 | 905 | 282 | 229 | 740 |
| Actual loss rate | 0.0003 | 0.039 | 0.006 | 0.105 | 0.348 | 0.908 | 0.997 |

- Calibration is broadly right but noisy in the low buckets.
- 8 of the 23,563 moves given p = 0 actually lost. Those are moves where the true board had been resampled away.
- At n = 512 with re-expansion and diversity, no move given p = 0 lost.

### 2. Particle count: more is better, and n = 256 is the largest that fits the time budget

| n | Truth coverage | Depletions/game | Brier ×100 | Single-worker median / p95 / max s per move |
|---|---|---|---|---|
| 32 | 0.280 | 2.99 | 0.813 | 0.02 / 0.11 / 0.14–0.28 |
| 64 | 0.362 | 2.10 | 0.789 | 0.03 / 0.20 / 0.25–0.31 |
| 128 | 0.432 | 1.45 | 0.705 | 0.03 / 0.37–0.41 / 0.49–1.05 |
| 256 | 0.525 | 0.92 | 0.675 | 0.02 / 0.68–0.70 / 0.97–1.30 |
| 512 | 0.593 | 0.64 | 0.645 | 0.03–0.04 / 1.21–1.26 / 1.89–2.31 |

Coverage, depletions and Brier are averaged over the other factors. Timing ranges span the `supports` and `reexpand` recoveries.

- **Truth coverage improves significantly at every step tested.** In paired bootstraps at the recommended settings, 256 vs 128 adds +0.108 [+0.051, +0.168], and 512 vs 256 adds +0.058 [+0.020, +0.097].
- **Brier improvements between neighboring n values are within noise** on 60 games.
- **Budget** (spec: median ≤ 0.4 s and max ≤ 1.5 s per move on the harness machine): n = 256 meets it with either recovery. **n = 512 exceeds the max** (1.89–2.31 s).
- **Under the spec's rule, the timing run selects n = 256.** One caveat (**assumed**): the timing run used only 12 games, so the maximum is a rough estimate.

### 3. Resampling trigger: `above_n` is at least as good as `ess` (supports ADR 0015)

- **Averaged over 40 configuration pairs:**
  - truth coverage 0.455 vs 0.422;
  - Brier 0.702 vs 0.749;
  - missed losses 0.018 vs 0.029.
- **At n = 256 (paired bootstrap):**
  - Brier −0.064 [−0.172, +0.044];
  - truth coverage +0.033 [−0.041, +0.110].

  The direction is consistent, but the difference isn't significant on its own.
- **Re-expansion barely helps under `ess`.** ESS resampling fires on almost every ply, so the checkpoint is usually only one observation old and replaying from it repeats the step that just failed. Some `ess` × `reexpand` cells are identical to `ess` × `supports`.

### 4. Recovery: `reexpand` keeps the truth more often

- **Truth coverage at n = 256:** +0.043 [+0.014, +0.082], which is significant.
- **Brier:** −0.057 [−0.171, +0.050], not significant.
- **Depletions per game:** 1.54 vs 1.70, averaged over all configurations.
- **Cost:** it raises the worst-case move time (n = 256 max 1.30 s vs 0.97 s, single worker), because replaying from the checkpoint can be expensive. The median is unchanged.

### 5. Opponent model: `capture` is no better than `uniform`

- **At n = 256 with re-expansion:**
  - truth coverage −0.039 [−0.081, −0.000], borderline worse;
  - Brier +0.035 [−0.041, +0.147].
- This fits the spec's reasoning: a biased model that is wrong about an opponent loses the truth more often.
- **Caveat:** only one of the three opponents (`baseline`) actually plays capture-greedily.

### 6. Diversity resampling: no measurable effect

- **At n = 256 with re-expansion:**
  - Brier +0.036 [−0.063, +0.156];
  - truth coverage −0.003 [−0.046, +0.041].
- Averaged over all configurations it slightly lowers missed losses (0.019 vs 0.027), but that isn't significant per pair.
- It adds code and an extra approximation, so it isn't worth keeping on this evidence.

## Recommendation

**n = 256, `uniform`, `above_n`, `reexpand`, no diversity** (ADR 0016, Proposed).

- **Truth coverage:** 0.575.
- **Brier ×100:** 0.602, against 1.841 for the possibility reference.
- **Single-worker time per move:** median 0.02 s, p95 0.68 s, max 1.30 s, within budget.

## Caveats

- **The games were played by `tracked_v2`.** A particle agent will play differently (Part B), and so will arena opponents.
- **Sample size:** 60 games. Several differences in Brier are within noise, and the bootstrap intervals in `comparisons.md` are the honest summary.
- **Timing:** the timing run used 12 games on this machine. The arena machine is unknown; the spec assumes it is up to 2× slower.
- **Truth coverage is about 50–60% even at the recommended settings.** `p_loss` stays well calibrated despite that, because the particles that survive mostly agree with the truth near our king. That part is **unverified**: it's an explanation, not a measurement.
