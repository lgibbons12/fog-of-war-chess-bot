# 0005. Test the copied tracker by source identity instead of editing starter tests

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 0
- **Decided by:** Claude Code
- **Source:** `docs/log.md` § Step 0, issue 2

## Context

The Step 0 spec said to point `test_uniform_random.py` at `bot.tracker`. `AGENTS.md` forbids editing starter files. The two instructions conflict.

## Decision

Leave the starter test untouched. `tests/test_tracker.py` asserts that `bot/tracker.py`'s source is identical to the corresponding code in `uniform_random.py`, so the starter tests' coverage carries over to our copy.

## Alternatives considered

- **Edit the starter test as the spec said:** violates a hard invariant.
- **Import the tracker from `uniform_random` at runtime:** couples submitted code to a starter script that isn't in the zip.

## Evidence

- **verified:** the identity test passes, and the starter tests pass in the full suite.

## Consequences

- Any intentional change to the tracker will break the identity test. That change needs its own ADR.
