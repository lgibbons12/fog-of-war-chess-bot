# Architecture Decision Records

This folder records the significant decisions made on this project: what we chose, what we rejected, and the evidence. Each record is written so it can be lifted into the final paper with little editing: the "Context" section becomes motivation, "Alternatives" becomes the ablation discussion, and "Evidence" carries the numbers.

`docs/log.md` stays the chronological lab notebook. ADRs are the curated layer on top of it: one decision per file, and each one cites the log section it came from.

## When to write one

Write an ADR when a choice meets **any** of these:

- It changes what the submitted bot does (agent ordering, arena agent, tracker semantics).
- It resolves a spec ambiguity or conflict, or deviates from a spec.
- It changes how we measure things (seeding, gates, statistics, harness behavior).
- A reasonable teammate or reviewer could have chosen differently and would want to know why.

Don't write one for routine implementation details that a spec already dictates.

**Agents (Claude Code and others):** whenever you make or propose a decision like the above, add an ADR in the same change. Set `Decided by` honestly. If you made the call yourself while implementing, write `Claude Code`, and set the status to `Proposed` until a human reviews it.

## Format

File name: `NNNN-short-kebab-title.md`, numbered in order and never reused. Copy `template.md`.

**Status values:**
- `Proposed`: written, not yet reviewed by the team.
- `Accepted`: reviewed and in effect.
- `Rejected`: considered and not adopted. Keep the file, since negative results belong in the paper.
- `Superseded by NNNN`: replaced by a later ADR. Never edit an accepted ADR's decision; write a new one.

**Evidence labels** follow `AGENTS.md`: **verified** (we ran it), **assumed** (inferred from reading code), and **unverified** (a hypothesis).

## Index

| # | Title | Status | Step | Decided by |
|---|---|---|---|---|
| [0001](0001-stepwise-spec-driven-workflow.md) | Step-wise, spec-driven development with human review | Accepted | — | Team |
| [0002](0002-reuse-referee-rules.md) | Reuse the referee's rule functions; never reimplement rules | Accepted | 0 | Team |
| [0003](0003-in-process-harness-equivalence.md) | In-process harness, held to the referee by a frame-by-frame equivalence test | Accepted | 0 | Team (spec) |
| [0004](0004-submission-zip-layout.md) | Submission zip keeps `bot/` as a package | Accepted | 0 | Claude Code, agreed by team |
| [0005](0005-tracker-test-without-editing-starters.md) | Test the copied tracker by source identity instead of editing starter tests | Accepted | 0 | Claude Code |
| [0006](0006-pair-seeding.md) | Seed match pairs from `"{base_seed}:{i}"` | Accepted | 1 | Claude Code |
| [0007](0007-strict-vs-arena-failure-modes.md) | Strict mode in the harness, fail-soft in the arena | Accepted | 1–2 | Spec + Claude Code |
| [0008](0008-possibility-for-safety.md) | Worst-case possibility decides king safety; probability ranks safe moves | Accepted | 1 | Team |
| [0009](0009-material-before-exposure.md) | Rank material before exposure; ship `safety_v2` | Accepted | 1–2 | Spec gate, Claude Code evidence |
| [0010](0010-factored-possibility-tracker.md) | Factored per-piece possibility tracker with independent expansion | Accepted | 2 | Team (spec) |
| [0011](0011-rays-through-hidden-squares.md) | Rays continue only through harmless hidden squares | Accepted | 2 | Claude Code |
| [0012](0012-known-attackers-need-clear-lines.md) | A visible attacker is "known" only along a fully visible line | Accepted | 2 | Claude Code |
| [0013](0013-keep-safety-v2-over-tracked-v2.md) | Keep `safety_v2` as the arena agent; don't ship `tracked_v2` | Accepted | 2 | Spec gate |
| [0014](0014-particle-filter-design.md) | Step 3 particle filter: enumerated children, referee-only consistency, risk as expected value | Proposed | 3 | Claude Code |
| [0015](0015-resample-only-above-n.md) | Resample only when distinct boards exceed `n` | Proposed | 3 | Claude Code |
| [0016](0016-particle-tracker-configuration.md) | Particle tracker configuration: n = 256, uniform, resample above n, re-expand on depletion | Proposed | 3 | Claude Code |
