# Step 3 Part B ablations and particle metrics for `particle_ev100`

**What:** the spec's follow-up experiments for the best gate agent, `particle_ev100` (see `../2026-11-22-step3-gate/`), plus the particle metrics. Used by [ADR 0019](../../adr/0019-ship-particle-ev100.md) and `docs/log.md` § Step 3 Part B.

- **Opponent model:** `capture` instead of `uniform`.
- **Particle count:** n ∈ {32, 128, 256} against the default 64. This deviates from the spec's {32, 128, 512}. The default moved to 64 (ADR 0018), and n = 512 is about 3× over the time budget, so 256 is the more useful upper point.
- **Absolute strength:** matches against `baseline` and `random`.
- **Particle metrics:** calibration, truth coverage, per-square log loss and set health, computed by rebuilding the agent from its 1,200 gate replays.
- **Capture confirmation:** `particle_ev100_capture` against `particle_ev100` head to head, on fresh seeds 3–5.

**Machine:** Windows 11 dev machine, 22 logical cores, 20 workers, Python 3.11.

**Commands** (repo root):

```sh
python -m harness.step3_queue --workers 20      # ablations + metrics, after the gate runs
python -m harness.cli particle_ev100_capture particle_ev100 --pairs 200 --seed 3 4 5 --workers 20 \
  --summary docs/results/2026-11-27-step3-ablations/summaries > cli_capture_vs_uniform_seeds345.txt
G=docs/results/2026-11-22-step3-gate/summaries; A=docs/results/2026-11-27-step3-ablations/summaries
python -m harness.paired_compare $G/particle_ev100_vs_safety_v2_seed{0,1,2}.jsonl \
  --vs $A/particle_ev100_n256_vs_safety_v2_seed{0,1,2}.jsonl      # one line of paired_vs_ev100.txt
```

**Files:**
- `cli_*.txt` and `breakdown_*.txt`: as in the gate folder.
- `summaries/`: per-game JSONL.
- `paired_vs_ev100.txt`: paired bootstrap of every variant against `particle_ev100`.
- `metrics/particle_metrics.{md,json}`: the particle metrics.

## Ablations against `safety_v2` (verified; 1,200 games each)

Paired differences pair games by (seed, pair). Both runs share every agent and opponent seed, so the paired CI is much tighter than comparing the two pooled CIs.

| Variant of `particle_ev100` | Pooled [95% CI] | Paired Δ vs n = 64 uniform [95% CI] | Loss classes (a/b/c) |
|---|---|---|---|
| Default (n = 64, uniform) | 0.617 [0.589, 0.644] | — | 9 / 373 / 0 |
| `capture` model | 0.638 [0.611, 0.665] | **+0.022 [+0.002, +0.041]** | 7 / 347 / 0 |
| n = 32 | 0.623 [0.596, 0.650] | +0.007 [−0.017, +0.030] | 12 / 364 / 0 |
| n = 128 | 0.632 [0.604, 0.658] | +0.015 [−0.006, +0.037] | 6 / 359 / 0 |
| n = 256 | 0.647 [0.619, 0.673] | **+0.030 [+0.008, +0.052]** | 6 / 320 / 0 |

- **More compute helps, slowly.** The effect is significant only at n = 256 (4× the particles), which breaks the per-move budget (max 5.3 s in the timing run, ADR 0018). Speeding up the tracker is therefore worth something.
- **The `capture` model wins against `safety_v2`, just barely,** but it did not hold up head to head on fresh seeds (next section).

## Capture vs uniform head to head, seeds 3–5 (verified)

`particle_ev100_capture` (A) against `particle_ev100` (B), 200 pairs × seeds 3–5, fresh seeds not used anywhere else:

| Seed 3 | Seed 4 | Seed 5 | Pooled [95% CI] | W/D/L (A) | A as White | A as Black |
|---|---|---|---|---|---|---|
| 0.486 | 0.481 | 0.485 | **0.484 [0.456, 0.512]** | 511/140/549 | 0.486 | 0.482 |

- **The capture model is no better than uniform head to head.** The interval includes 0.5, and every seed and color comes out slightly below it.
- **Its +0.022 against `safety_v2` is treated as a false positive** from multiple comparisons, or at most an effect specific to weak opponents.
- **Uniform stays the model** (ADR 0016), and `particle_ev100` is the arena candidate (ADR 0019). This matches the Part A matrix, where `capture` gave no gain in Brier score.

## Absolute strength (verified)

| Opponent | Pooled [95% CI] | W/D/L | Mean plies |
|---|---|---|---|
| `baseline` | 0.762 [0.737, 0.785] | 903/22/275 | 55.4 |
| `random` | 0.998 [0.994, 1.000] | 1198/0/2 | 21.7 |

For comparison, Step 2 recorded `safety_v2` against `baseline` at 0.675 [0.648, 0.701] over 1,200 games (`docs/log.md` § Step 2). The seeds differ, so this is not a paired comparison, but the particle agent's lower bound (0.737) is above `safety_v2`'s upper bound (0.701).

## Particle metrics for `particle_ev100` on its 1,200 gate games (verified)

**Calibration** of the chosen move's `p_loss` against whether that move actually let the opponent capture our king (40,586 decisions in `particles` mode):

| Predicted `p_loss` | Moves | Mean predicted | Actual loss rate |
|---|---|---|---|
| 0 | 35,881 | 0 | 0.0033 |
| (0, 0.01] | 38 | 0.0025 | 0 |
| (0.01, 0.05] | 2,662 | 0.0275 | 0.0368 |
| (0.05, 0.2] | 1,822 | 0.0950 | 0.0697 |
| > 0.2 | 183 | 0.345 | 0.208 |

- **Calibrated to within about 1.5×** in the middle buckets. When the bot says 3%, the actual rate is 3.7%; when it says 9.5%, the actual rate is 7.0%.
- **High risk is overestimated.** A predicted 34% comes out as an actual 21%.
- **`p_loss = 0` is not a guarantee.** 118 of 35,881 such moves (0.33%) still lost. Particles can miss the true board, and the possibility layer only vetoes known losses. This miss rate is the price of the probability layer.

**Truth coverage and per-square log loss** on `?` squares (nats per square; the baseline spreads each possibility hypothesis uniformly over its support):

| Plies | Coverage | Truth weight | Log loss, particles | Log loss, possibility |
|---|---|---|---|---|
| 0–19 | 0.544 | 0.223 | 0.410 | 0.965 |
| 20–39 | 0.265 | 0.101 | 0.593 | 0.675 |
| 40–59 | 0.187 | 0.047 | 0.450 | 0.424 |
| 60–79 | 0.215 | 0.037 | 0.345 | 0.347 |
| 80–99 | 0.276 | 0.050 | 0.324 | 0.319 |
| All | 0.325 | 0.112 | 0.440 | 0.578 |

- **Particles are much better early and break even after about ply 40.** By then the true board is in the set only about 20% of the time, and it carries little weight.
- **Coverage is lower than Part A's 0.575.** Part A used n = 256 on `tracked_v2` replays; this run uses n = 64 on the particle agent's own, longer games.

**Set health:**
- 2.5 depletions per game. 99.9% of them recovered (1,257 by re-expansion and 1,763 by regeneration), and 16 regenerations failed.
- 16 observations had no particles, and particles were never switched off.
- Median 36 distinct particles, median ESS 28.

**Time:** the metrics rebuild ran with 20 workers, so its time column (median 0.117 s, max 4.4 s) is contended and is **not** a budget measurement. The single-worker numbers are in `../2026-11-22-step3-timing/`.
