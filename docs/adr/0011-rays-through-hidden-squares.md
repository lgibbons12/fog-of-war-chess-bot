# 0011. Rays continue only through harmless hidden squares

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 2
- **Decided by:** Claude Code (resolving a spec conflict)
- **Source:** `docs/log.md` § Step 2, issue 1

## Context

The Step 2 spec contradicted itself:

- Part C says rays pass through `?` squares unless they are certainly occupied.
- Test 4 requires a *coarse* tracker (all types possible everywhere) to give **identical** reports to Step 1, which stops at the first `?`.

Both can't hold.

## Decision

A ray from our king continues through a `?` square only if **no possible type there could attack along that line**, the "only a pawn could be there" case the spec motivates. It stops at a flagged `?` or a certainly occupied one.

## Alternatives considered

- **Follow Part C literally:** breaks the reduction test, and flags more far-away squares behind a likely blocker.
- **Follow Step 1 (stop at every `?`):** sound, but throws away the tracker's type information.

## Evidence

- **verified:** the reduction test (coarse tracker gives identical `SafetyReport`s to `tracker=None` over 20 games) passes exactly.
- **verified:** the safety soundness test passes with zero violations.

## Consequences

- If a later spec relies on Part C's literal wording, it should cite this ADR.
