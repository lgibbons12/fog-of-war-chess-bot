# 0016. Particle tracker configuration: n = 256, uniform model, resample above n, re-expand on depletion

- **Status:** Accepted
- **Date:** 2026-11-18
- **Step:** 3 (Part A)
- **Decided by:** Claude Code (recommendation from the decision matrix), accepted by Liam 2026-11-22
- **Source:** `docs/results/2026-11-17-step3-tracker-matrix/README.md`; `docs/log.md` § Step 3 Part A

## Context

The Step 3 draft spec left the particle count to a timing run (decided 2026-11-17) and left the opponent model open. Part A also surfaced frequent loss of the true board. That raised three more choices: the resampling trigger (ADR 0015), the recovery strategy, and diversity resampling. Liam asked for every combination to be run and compared.

## Decision

`ParticleTracker(n=256, model=UniformModel(), trigger="above_n", recovery="reexpand", diversity=False)`.

## Alternatives considered

All 80 combinations of n ∈ {32, 64, 128, 256, 512} × {uniform, capture} × {above_n, ess} × {supports, reexpand} × {sys, div}, scored on the same 60 replayed games.

- **n = 512:** better truth coverage (+0.058 [+0.020, +0.097]), but its worst-case move time (1.89–2.31 s single worker) breaks the 1.5 s budget.
- **`capture` model:** no better on Brier, and borderline worse on truth coverage (−0.039 [−0.081, −0.000]).
- **`ess` trigger:** worse on average on every metric, though not significant on its own pair (ADR 0015).
- **`supports` recovery only:** truth coverage is 0.043 lower [0.014, 0.082], but its worst-case time is smaller (0.97 s vs 1.30 s).
- **Diversity resampling:** no measurable effect, so the extra code and approximation aren't justified.

## Evidence

All **verified**; details are in the results folder.

- **Recommended configuration:**
  - truth coverage 0.575;
  - Brier ×100 0.602 and log loss 0.0222;
  - 0.72 depletions per game;
  - single-worker time per move: median 0.02 s, p95 0.68 s, max 1.30 s.
- **Possibility tracker as a predictor** (generously calibrated): Brier ×100 1.841, log loss 0.0764.

## Consequences

- Part B agents use this configuration. Re-measure the timing with the particle agent, whose games differ from the `tracked_v2` replays.
- `CaptureModel`, the `ess` trigger and diversity resampling can be removed once this is accepted, or kept as experiment-only options.
- Truth coverage stays around 55–60%, so `p_loss` still depends partly on the possibility veto (ADR 0008) for safety.
