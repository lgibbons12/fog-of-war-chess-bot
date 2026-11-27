# 0017. Particle agent fallbacks: the time guard and errors switch particles off for the game; depletion substitutes exposure

- **Status:** Proposed
- **Date:** 2026-11-22
- **Step:** 3 (Part B)
- **Decided by:** Claude Code (resolving a spec ambiguity)
- **Source:** `docs/step-3-particles.md` § Choosing `n` (time guard) and § Agents; `bot/agents/particle_agent.py`

## Context

The spec names two fallbacks and words them differently.

- **§ Choosing `n`:** "If `remaining < 20 s`, skip particle work for this decision and rank as `safety_v2` does."
- **§ Agents:** "If particles are unavailable (depletion or the time guard), `p_loss` is replaced by `exposure_count > 0`."

For the EV keys these are not the same ranking. With λ = 300, substituting `exposure > 0` charges every exposed move 300 units, which is binary risk-first rather than `safety_v2`'s material-first order.

"Skip particle work for this decision" is also underspecified. Almost all particle time is in the updates, which run in `observe()`, where the clock is not known. Skipping only the scoring saves little. Skipping updates for a few plies would leave the particle history broken.

The arena runs non-strict, and an exception inside the particle code must not cost the game (ADR 0007).

## Decision

`ParticleAgent` runs in one of four modes. The decision record stores the mode as `particle_mode`.

| Mode | When | Ranking |
|---|---|---|
| `particles` | Particles available | The agent's own key with the particle `p_loss` |
| `unavailable` | Depletion with no successful recovery | Same key, with `p_loss = float(exposure_count > 0)` (§ Agents) |
| `time_guard` | `remaining < 20 s` at a decision | `safety_v2`'s key `(known_loss, -material, exposure, rng)` (§ Choosing `n`). The particle tracker is dropped for the rest of the game. |
| `error` | Particle code raised (non-strict only) | As `time_guard`, and the traceback goes to stderr. In strict mode (harness, tests) the exception propagates. |

The `rng.random()` tie-break is drawn once per legal move in every mode. The tracker's own `random.Random` is seeded from the agent RNG once, at construction.

## Alternatives considered

- **Read § Agents literally for the time guard** (substitute exposure). Rejected: § Choosing `n` names `safety_v2` explicitly, and the binary substitution changes the ranking most exactly when we can least afford a bad move.
- **Keep updating particles below 20 s and skip only scoring.** Rejected: updates are most of the cost (opponent-ply expansion), so this would not protect the clock.
- **Re-enable particles if the clock recovers** (regenerate from the possibility tracker). Not done. Below 20 s the 2 s increment barely covers a particle move, and regenerated particles carry no history. Revisit if arena logs show the guard firing.

## Evidence

- **Verified:** `tests/test_particle_agent.py` covers each mode, the strict/non-strict split, and the one-call-per-move RNG rule.
- **Verified:** `tests/test_determinism.py` asserts that no harness game reaches `time_guard` or `error`. The harness clock never runs low, since think times are well under the 2 s increment.
- **Assumed:** the guard is rarely or never reached in the arena. The Part B timing run gives a median per-move time far below the 2 s increment (see `docs/results/2026-11-22-step3-timing/`).

## Consequences

- Harness results are unaffected: the guard never fires there.
- Arena games that do hit the guard play like `safety_v2` from then on, which is the shipped agent and a known quantity.
