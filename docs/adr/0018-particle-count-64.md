# 0018. Particle agents use n = 64, the largest count that meets the per-move budget

- **Status:** Accepted
- **Date:** 2026-11-22
- **Step:** 3 (Part B)
- **Decided by:** Liam (choosing among options Claude Code presented), following the spec's rule
- **Source:** `docs/step-3-particles.md` § Performance budget and § Choosing `n`; `docs/results/2026-11-22-step3-timing/`
- **Supersedes:** the particle count in [0016](0016-particle-tracker-configuration.md). The rest of 0016 stands: uniform model, resample above `n`, re-expand on depletion.

## Context

ADR 0016 chose n = 256 from a timing run on *replayed `tracked_v2` games*, and asked for the timing to be re-measured with the particle agent. The spec's rule is to choose the largest `n` with a median per-move particle time under 0.4 s and a maximum under 1.5 s.

## Decision

`ParticleAgent` defaults to `n = 64`. The other counts stay registered as `particle_ev300_n{32,128,256,512}` for the "does more compute help?" experiment.

## Alternatives considered

- **Keep n = 256, relaxing the max:** the arena gives a 180 s bank, so rare spikes are survivable. Rejected for now: the budget was set to leave room for a 2× slower arena machine, and n = 256 exceeded 1.5 s on 16 of 691 moves.
- **n = 128:** max 3.3 s on 2 of 686 moves. Same objection.
- **Optimize first** (cap re-expansion, cheaper scoring): the spec requires asking before optimizing. Left open as a follow-up.

## Evidence

**Verified**, from `docs/results/2026-11-22-step3-timing/`: 20 games of `particle_ev300` against `safety_v2` per `n`, single worker (five runs in parallel on a 22-core machine).

| n | Median s | p95 s | Max s | Moves > 1.5 s |
|---|---|---|---|---|
| 32 | 0.058 | 0.218 | 0.771 | 0 / 628 |
| 64 | 0.071 | 0.401 | 1.462 | 0 / 691 |
| 128 | 0.101 | 0.776 | 3.341 | 2 / 686 |
| 256 | 0.145 | 1.113 | 5.309 | 16 / 691 |
| 512 | 0.178 | 1.919 | 3.973 | 59 / 685 |

- **Two sources of slow moves:**
  - Depletion recovery: a single re-expansion or regeneration update took 5.3 s at n = 256.
  - Full-`n` opponent-ply expansion plus scoring every legal move: up to about 2.2 s at n = 256 and 3.9 s at n = 512.
- **The replay-based estimate was optimistic.** ADR 0016 measured a 1.30 s max at n = 256 on `tracked_v2` replays. The particle agent's own games differ.

## Consequences

- **Lower resolution and truth coverage.** n = 64 gives coarser `p_loss` (median ESS about 29) and keeps the true board less often than n = 256 would (ADR 0016's matrix measured +0.108 coverage going from 128 to 256).
- **The n ablation tests whether this costs strength.** It measures the cost of the budget, not arena safety.
- **The 1.46 s max sits right at the limit.** Arena timing should be checked when packaging.
