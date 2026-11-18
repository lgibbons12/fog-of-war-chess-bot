# 0001. Step-wise, spec-driven development with human review

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** —
- **Decided by:** Team
- **Source:** `AGENTS.md` ("What this project is", "How to work"), commit `31e70ac`

## Context

Most of the code is written by coding agents (Claude Code). Agents tend to build ahead, guess at ambiguous requirements, and present untested code as working. Fog of war chess also has subtle rules, where a silent bug can leak information or make results meaningless.

## Decision

- Work proceeds in numbered steps, each with a written spec in `docs/`. The spec is the source of truth.
- An agent implements only the current step. If the spec is ambiguous or wrong, it stops and asks rather than guessing.
- Every step ends with a report: files changed, test output, the spec's "Report back" items, deviations, and open questions. Results are labeled verified, assumed, or unverified.
- A human reviews each step before the next one starts.
- Each step has a quantitative **gate**: a matchup whose pooled 95% lower bound must exceed 0.5 before the new agent replaces the arena agent.

## Alternatives considered

- **Free-form agent development:** faster at first, but hard to audit and hard to write up afterwards.
- **No gates, ship the newest agent:** risks shipping regressions, because added sophistication has repeatedly failed to help (see 0009, 0013).

## Evidence

- **verified:** the gates caught two regressions. Step 1's spec default (`safety`, count mode) scored 0.474 against baseline, and Step 2's `tracked_v2` scored 0.512 [0.484, 0.541] against `safety_v2`. Neither was shipped.

## Consequences

- Progress is slower per step, but every step's claims are backed by logged runs.
- `docs/log.md` and these ADRs together give a reproducible record for the paper.
