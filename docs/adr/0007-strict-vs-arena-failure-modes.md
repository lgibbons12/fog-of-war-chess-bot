# 0007. Strict mode in the harness, fail-soft in the arena

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 1–2
- **Decided by:** Spec (tracker inconsistency handling) + Claude Code (harness strict flag, equivalence exception)
- **Source:** `docs/log.md` § Step 1 issue 5, § Step 2 Part B; `bot/protocol.py:28`; `bot/possibility.py:149`

## Context

In experiments we want bugs to surface loudly. In the arena, a crash or a stray stdout line forfeits the game, so the bot should keep playing even when something goes wrong.

## Decision

- **Harness and tests (`strict=True`):** agent exceptions raise instead of being scored as losses, and a tracker inconsistency raises `TrackerInconsistency`.
- **Arena (`strict=False`):**
  - If the agent raises while choosing, `bot/protocol.py` logs the traceback to stderr and plays a uniformly random legal move.
  - A tracker inconsistency is logged, and the tracker resets to a coarse but sound state: every enemy piece may be any type on any hidden or visible-enemy square.
- The equivalence test runs with `strict=False`, because the referee scores a crash as a "Bot exited" loss.

## Alternatives considered

- **One mode everywhere:** strict would forfeit arena games over recoverable bugs, and fail-soft would hide bugs in experiments.

## Evidence

- **verified:** soundness tests over 9,190 observations recorded zero inconsistencies and zero resets in harness games.
- **verified:** a protocol test covers the fallback path.

## Consequences

- Resets are counted in `last_decision`. Any nonzero count in harness games is a bug to investigate.
