# 0015. Resample only when distinct boards exceed `n`

- **Status:** Accepted
- **Date:** 2026-11-17
- **Step:** 3 (Part A)
- **Decided by:** Claude Code (deviation from the draft spec), accepted by Liam 2026-11-22
- **Source:** `docs/step-3-particles.md` § Resampling; `bot/particles.py` `_resample`; `docs/log.md` § Step 3 Part A

## Context

The draft spec resamples when the number of distinct particles exceeds `n` **or** the effective sample size falls below `n/2`. But our particles are *merged*: duplicate boards are combined and their weights summed. With merging, ESS ≤ the number of distinct particles. So the ESS trigger fires whenever fewer than `n/2` distinct boards exist, which is most of the time early in a game.

## Decision

Resample (systematic, one `rng.random()` call) **only** when the number of distinct boards exceeds `n`. With `n` or fewer distinct boards, keep the weighted set exactly.

## Alternatives considered

- **Spec as written (distinct > n or ESS < n/2):** resampling a small merged set can only throw away low-weight boards, including the truth, without freeing any capacity. Classic ESS resampling exists to fight weight degeneracy in *unmerged* particle sets, where many copies carry negligible weight. That problem doesn't arise here.

## Evidence

- **verified:** with resampling disabled (`n` large), the true board is among the particles at every one of 95 checked observations (`test_unlimited_particles_never_lose_the_truth`). So any truth loss comes from resampling, and resampling less often can only help.
- **verified** (decision matrix, `docs/results/2026-11-17-step3-tracker-matrix/`): averaged over 40 paired configurations, `above_n` beats `ess` on every metric:
  - truth coverage 0.455 vs 0.422;
  - Brier ×100 0.702 vs 0.749;
  - missed losses 0.018 vs 0.029.

  At n = 256 alone, the paired differences are in the same direction but within noise: Brier −0.064 [−0.172, +0.044], truth coverage +0.033 [−0.041, +0.110].

## Consequences

- Below `n`, the particle set is the exact posterior over histories, under the opponent model.
- Truth loss still happens whenever the exact support exceeds `n`, which is common. See the depletion finding in `docs/log.md` § Step 3 Part A.
