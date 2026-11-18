# 0010. Factored per-piece possibility tracker with independent expansion

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 2
- **Decided by:** Team (spec); details by Claude Code
- **Source:** `docs/step-2-possibility.md` Part B; `docs/log.md` § Step 2 issues 3–5; `bot/possibility.py`

## Context

Step 1's diagnosis was that without history, every hidden square on an open line counts as a possible queen. We needed history-consistent knowledge of where each enemy piece could be, while staying sound and fitting a 2 s per move budget in pure Python.

## Decision

- Track one hypothesis per real enemy piece, a `(possible types, bitboard of possible squares)` pair. Hypotheses track **identities**, not types.
- **Our capture:** remove the captured piece's hypothesis. With k > 1 candidates, merge them into k−1 hypotheses with unioned types and squares.
- **Enemy quiet ply:** every hypothesis expands by one move *independently*, with castling as a joint king+rook update and promotion adding N, B, R, Q to the types.
- **Enemy capture ply:** only hypotheses that could have captured on the lost square expand, including en passant.
- **Filter:** each observation removes squares seen empty or ours, and matches visible enemies to hypotheses until nothing changes.
- **Precision refinement beyond the spec (Claude Code):** in quiet-ply expansion, squares occupied before the move are excluded from every piece's reach, not only used to stop slides. It remains sound.

## Alternatives considered

- **Full joint enumeration of boards:** exact but exponential. This is deferred to Step 3 as sampled particles.
- **Per-square type sets without identities:** cheaper, but can't express "this pawn and that queen can't both have moved".

## Evidence

- **verified:** soundness property test over 204 games and 9,190 observations: a bipartite matching from true pieces to hypotheses always exists, and `certainly_occupied` ⊆ truth.
- **verified:** update time median 0.054 ms, max 12.2 ms (budget 20 / 200 ms).
- **verified:** precision decays with game length. Mean support per hypothesis grows from 8.9 squares (plies 0–19) to 41.1 (plies 100–119), because each hypothesis expands as though it alone had moved.

## Consequences

- The over-expansion is the known limitation that Step 3's particles are meant to address.
- The tracker is a sound filter that a particle or learned belief model can be checked against.
