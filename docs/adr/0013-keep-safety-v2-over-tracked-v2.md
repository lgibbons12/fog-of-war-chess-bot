# 0013. Keep `safety_v2` as the arena agent; don't ship `tracked_v2`

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 2
- **Decided by:** Spec gate (pooled lower bound > 0.5 required)
- **Source:** `docs/log.md` § Step 2, "Part C experiments" and "Why the tracker didn't pass the gate"

## Context

Step 2 built the possibility tracker (0010) to make exposure informative. The question was whether tracker-based exposure produces a stronger agent.

## Decision

Keep `safety_v2` (coarse exposure) as the arena agent. `tracked_v2` is kept in the registry for experiments only.

## Alternatives considered

| Matchup (200 pairs × seeds 0–2) | Pooled [95% CI] |
|---|---|
| `tracked_v2` vs `safety_v2` (**gate**) | 0.512 [0.484, 0.541]: fails |
| `tracked_count` vs `tracked_v2` | 0.370 [0.343, 0.398] |
| `tracked_binary` vs `tracked_v2` | 0.380 [0.353, 0.408] |
| `tracked_v2` vs baseline | 0.668 [0.641, 0.694] |

Even with informative exposure, putting exposure first still loses.

## Evidence

- **verified:** the tracker improves exposure. Safe-move availability rose from 0.417 to 0.660, and flagged squares per decision fell from 1.63 to 0.93.
- **verified:** but the false-alarm rate barely moves (0.996 → 0.991), and since exposure is only a tie-break after material (0009), few decisions change. The main visible effect is longer games: 102 threefold draws against `safety_v2`.
- **verified:** losses are still dominated by hidden sliders (`tracked_v2` vs baseline: rook 123, queen 116, bishop 63).

## Consequences

- Possibility alone has hit diminishing returns. This motivates Step 3, using probability (particles) to rank risk, in line with 0008.
- Candidate follow-ups from the log: use exposure as a hard filter unless the material gain is large, or move on to particles.
