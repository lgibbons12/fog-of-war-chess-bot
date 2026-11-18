# 0003. In-process harness, held to the referee by a frame-by-frame equivalence test

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 0
- **Decided by:** Team (spec)
- **Source:** `docs/step-0-spec.md`; `docs/log.md` § Step 0

## Context

The official `referee.py` runs each bot as a subprocess. That is too slow for the thousands of games each experiment needs, and it is POSIX-only. A faster harness is only useful if its results are the referee's results.

## Decision

- `harness/game.py:play_game` mirrors `referee.run_match`'s loop order exactly: outcome check, ply cap, observation to White then Black, the mover's choice, legality check, push, repetition count.
- `tests/test_equivalence.py` plays seeds 0–9 through both the subprocess referee and `play_game`, and requires identical result, reason, and every frame. This test must always pass.
- Clocks are simulated (180 s + 2 s per move) and never forfeit. The ply cap is 1,000, matching the arena rather than the referee's local default of 10,000.
- Matches are color-swapped pairs, scored with Wilson 95% intervals.

## Alternatives considered

- **Use the referee directly for experiments:** correct by construction, but about 100× slower and unusable on Windows.

## Evidence

- **verified:** 600-game one-off sweep (150 seeds × 4 matchup orientations), 0 mismatches, including an en passant capture.
- **verified:** shifting seeds by one makes the test fail, so it can detect divergence.
- **verified:** about 820 games/s with 22 workers (random vs random, Linux).
- **unverified (open):** threefold repetition, the 50-move rule, and the ply cap have not been exercised in the equivalence test, because starter-vs-starter games all end by king capture.

## Consequences

- Every experiment number in the log comes from the harness, and its validity depends on this test.
- The coverage gap above should be closed with longer games, e.g. `safety_v2` vs `safety_v2`, which draws by repetition.
