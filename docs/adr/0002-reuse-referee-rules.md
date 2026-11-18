# 0002. Reuse the referee's rule functions; never reimplement rules

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 0
- **Decided by:** Team
- **Source:** `AGENTS.md` (hard invariants 1–3)

## Context

The variant differs from standard chess in ways that are easy to get wrong: there is no check, a move that leaves your king capturable loses, castling through attack is legal, and observations follow specific visibility rules. A reimplementation that disagrees with `referee.py` would make both harness results and the bot's reasoning wrong without any visible error.

## Decision

- `bot/` and `harness/` import `FowBoard`, `fow_moves`, `observation`, `outcome`, and `position_key` (plus `make_frame` in the harness) from `referee.py` rather than reimplementing them.
- Starter files (`referee.py`, `baseline.py`, `uniform_random.py`, their tests, and `starters/`) are never edited.
- `bot/` may apply referee rule functions to *hypothetical* boards, but never sees a true board (no information leakage).

## Alternatives considered

- **Our own rules engine:** could be faster, but correctness risk is high and it isn't needed at the current think times (median about 0.5 ms per move against a 2 s increment).

## Evidence

- **verified:** `tests/test_leakage.py` checks imports by AST scan and checks that every value passed into an agent is an observation string or a clock float.
- **verified:** `bot/tracker.py` is copied from `uniform_random.py` with a script, and its source identity is tested (see 0005).

## Consequences

- If later steps (particles, Stockfish) need faster rule evaluation, revisit this ADR with measurements rather than quietly replacing referee calls.
