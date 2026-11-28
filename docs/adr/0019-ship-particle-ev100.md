# 0019. Ship `particle_ev100` as the arena agent; keep the uniform opponent model

- **Status:** Proposed
- **Date:** 2026-11-27
- **Step:** 3 (Part B)
- **Decided by:** Claude Code, by the spec's gate rule ("if the gate passes, package the best particle agent"); pending team review
- **Source:** `docs/results/2026-11-22-step3-gate/`, `docs/results/2026-11-27-step3-ablations/`; `docs/log.md` § Step 3 Part B
- **Supersedes:** the arena-agent choice of [0009](0009-material-before-exposure.md)/[0013](0013-keep-safety-v2-over-tracked-v2.md) (`safety_v2`)

## Context

The Step 3 gate asks whether the best particle agent's pooled lower bound against `safety_v2` exceeds 0.5. If it does, that agent is packaged and becomes the arena agent. The ablations also had to settle the opponent model and the particle count.

## Decision

- **The arena agent is `particle_ev100`:** sort key `(known_loss, -(material - 100 · p_loss), exposure, rng)`, with n = 64, the uniform opponent model, resampling above n, and re-expansion on depletion (ADRs 0016, 0018).
- **The fallbacks follow ADR 0017.**
- **Packaging:** `scripts/package.sh` now defaults to `particle_ev100`.

## Alternatives considered

- **λ ∈ {30, 300}:** statistical ties with λ = 100 (paired Δ −0.006 and −0.008, both CIs include 0). λ = 100 has the best point estimate, and it lies inside the grid.
- **λ = 1000 and `particle_v2` (`p_loss` as tie-break):** both significantly worse, at −0.025 [−0.043, −0.007] and −0.024 [−0.036, −0.012]. Rejected.
- **The `capture` opponent model:** +0.022 [+0.002, +0.041] against `safety_v2`, but head to head on fresh seeds 3–5 it scored 0.484 [0.456, 0.512] against uniform. **Rejected:** the first result was most likely a false positive among eight comparisons.
- **n = 256:** +0.030 [+0.008, +0.052], the one real gain, but its maximum move time is 5.3 s, which breaks the 1.5 s budget (ADR 0018). Rejected for now. It is the strongest argument for speeding up the tracker.
- **Keep `safety_v2`:** rejected. The particle agent beats it by a wide margin.

## Evidence

All **verified**; 200 pairs × 3 seeds = 1,200 games per row unless noted.

- **Gate:** `particle_ev100` vs `safety_v2` scored **0.617 [0.589, 0.644]**, with seeds at 0.611 / 0.625 / 0.614 and W/D/L 662/156/382.
- **Absolute strength:**
  - vs `baseline`: 0.762 [0.737, 0.785]. Step 2 measured `safety_v2` vs baseline at 0.675 [0.648, 0.701].
  - vs `random`: 0.998 [0.994, 1.000].
- **Safety:**
  - No game was lost to anything but king capture, and no move was a known loss.
  - (a)-type losses, where a safe move existed but we chose an exposed one, fell from 45 for `particle_v2` to 9.
- **Calibration:** in the middle `p_loss` buckets, the predicted risk is within about 1.5× of the observed rate (2.75% predicted vs 3.68% observed; 9.5% vs 7.0%).
- **Time:** in the single-worker timing run, median 0.071 s and max 1.462 s per move at n = 64 (ADR 0018).
- **Package check:** `scripts/check_package.sh` passed in WSL with no protocol failures. As White it lost in 7 plies, which did not recur in 26 further referee games (see `docs/log.md` § Step 3 Part B, Final checks).
- **Arena-style timing:** 20 local referee games against baseline. The referee-charged time per move was median 0.026 s and max 0.283 s over 614 moves.
- **Tests:** full suite on Linux, 69 passed.

## Consequences

- **The arena runs the particle agent once someone uploads `dist/bot.zip`.** Uploading is a human step.
- **The 1.46 s max move time is close to the budget.** Watch arena logs for `particles off` lines on stderr, which mean the time guard or an error fired.
- **Follow-ups:**
  - Speed up the tracker: n = 256 is the measured gain.
  - Use a learned opponent model in place of `uniform` (JJ's transformer track).
  - The calibration shows the high-risk bucket is overestimated (34% predicted vs 21% observed).
