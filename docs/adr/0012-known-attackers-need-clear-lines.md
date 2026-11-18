# 0012. A visible attacker is "known" only along a fully visible line

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 2
- **Decided by:** Claude Code (bug fix found by the property test)
- **Source:** `docs/log.md` § Step 2, issue 2

## Context

After 0011 let rays continue through harmless `?` squares, a *visible* enemy rook beyond such a square was reported as a **known** attacker. But the `?` might hold a piece that blocks it. The soundness property test caught a move flagged as a known loss that was actually safe.

## Decision

A visible enemy piece counts as a known attacker only if every square between it and our king is `-`. If the line passes through any `?`, it is reported as a *possible* attacker, and its square appears in `exposed`, listed with its visible type in the decision record.

## Alternatives considered

- **Keep "known" and accept occasional false known-losses:** this discards safe moves and violates the step's soundness contract in the conservative direction.

## Evidence

- **verified:** a regression unit test was added, and the property test passes with zero violations afterwards.

## Consequences

- This is a worked example for the paper of the property-based soundness test catching a bug that unit tests missed.
