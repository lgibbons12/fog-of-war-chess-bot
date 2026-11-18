# 0009. Rank material before exposure; ship `safety_v2`

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 1–2 (found in Step 1, adopted in Step 2 Part A)
- **Decided by:** Spec's selection rule; Claude Code found the ordering in a Step 1 exploratory run
- **Source:** `docs/log.md` § Step 1 "Why `safety` loses" and "Exploratory result"; § Step 2 Part A; commit `96942a6`

## Context

The Step 1 spec's agent ranked moves by `(known_loss, exposure_count, -material, rng)`. It failed its gate against baseline. Without history, nearly every midgame move was exposed, so the agent spent its moves shrinking a number that rarely reached zero, and almost never captured.

## Decision

Rank moves by `(known_loss, -material, exposure_count, rng)` (registry name `safety_v2`), and make it the arena agent. All safety variants are sort-key `functools.partial` entries over one `SafetyAgent` class.

## Alternatives considered

| Agent | Key | vs baseline (pooled, seeds 0–2) |
|---|---|---|
| `safety` (Step 1 spec) | `(loss, exposure, -material)` | 0.474 / 0.445 / 0.401 per seed: **fails** |
| `safety_binary` | `(loss, exposed?, -material)` | 0.565 / 0.552 / 0.507 per seed: borderline |
| `safe_material` (control) | `(loss, -material)` | 0.492 [0.464, 0.521] |
| **`safety_v2`** | `(loss, -material, exposure)` | **0.675 [0.648, 0.701]** |

The spec's rule was to ship the simpler `safe_material` unless `safety_v2` beat it with a lower bound above 0.5.

## Evidence

- **verified:** `safety_v2` vs `safe_material` scored 0.659 [0.631, 0.685] (200 pairs × 3 seeds). So exposure helps as a **tie-breaker** but hurts as the primary criterion.
- **verified:** `check_package.sh` passed with `safety_v2`.

## Consequences

- Material-first agents can take an exposed capture over a safe quiet move, by design. That is where type (a) losses come from (see `docs/log.md` Step 2 loss breakdowns).
- Improving exposure precision only changes tie-breaks, which limits how much the Step 2 tracker could help (see 0013).
