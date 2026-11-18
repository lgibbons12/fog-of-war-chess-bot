# 0006. Seed match pairs from `"{base_seed}:{i}"`

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 1
- **Decided by:** Claude Code (bug found while checking seed noise); confirmed by Step 2 spec
- **Source:** `docs/log.md` § Step 1, issue 3; `harness/match.py:33`

## Context

Step 0 seeded pair *i* with `random.Random(base_seed + i)`, as the spec literally said. So pair *i* of `--seed s` was identical to pair *i+1* of `--seed s+1`: runs with nearby seeds shared 199 of 200 pairs. Multi-seed experiments looked far more stable than they were.

## Decision

Seed each pair with `random.Random(f"{base_seed}:{i}")`. String seeding of `random.Random` is deterministic across processes (unlike `hash()` of a `str`, which is randomized). `tests/test_determinism.py` asserts identical summaries for `workers=1` and `workers=4`.

## Alternatives considered

- **`hash((base_seed, i))`:** stable for integer tuples, but easy to break by accident if a `str` sneaks in.
- **Integer mixing (e.g. `base_seed * 1_000_003 + i`):** fine too; the string form was chosen for readability.

## Evidence

- **verified:** the bug showed up as identical W/D/L across seeds 0 and 1 before the fix.
- **verified:** after the fix, `safety_v2` vs baseline varies 0.640–0.703 across seeds 0–2, which is the expected sampling noise.

## Consequences

- All Step 0 benchmark numbers were rerun under the new seeding. The paper should only cite post-fix numbers.
- Experiments report per-seed and pooled scores over seeds 0–2 (600 pairs, 1,200 games).
