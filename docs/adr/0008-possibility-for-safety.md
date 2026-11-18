# 0008. Worst-case possibility decides king safety; probability ranks safe moves

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 1 (principle governs Steps 1–5)
- **Decided by:** Team
- **Source:** `AGENTS.md` ("Planned architecture"), `docs/step-1-safety.md`

## Context

There is no check in this variant, and leaving the king capturable loses on the spot. Every baseline loss we observed ended by king capture. Since we can't see the opponent, any safety judgment must be made under uncertainty about hidden pieces.

## Decision

The architecture splits responsibilities:

- **Possibility (worst case)** decides king safety. A move counts as a **known loss** if a visible enemy piece can capture the king. It counts as **exposed** if some hidden square could hold an attacker. This analysis must be **sound**: it may over-flag, but it must never call an unsafe move safe.
- **Probability** (particles, Step 3) ranks moves among those the possibility layer allows.

## Alternatives considered

- **Probability only (e.g. pick the move with the lowest estimated king-capture probability):** gives up the guarantee. A rare but real capture ends the game outright.
- **Possibility only:** Steps 1–2 showed that worst-case exposure is too coarse to rank moves (see 0009, 0013).

## Evidence

- **verified:** soundness tests check every legal move at every decision against the true board, more than 50,000 (decision, move) pairs per suite run, with zero violations.
- **verified:** about 99% of flagged hidden squares hold no real attacker (false-alarm rate 0.996 coarse, 0.991 tracked). Possibility alone is sound but uninformative, which motivates the probability layer.

## Consequences

- Each step adds precision to one layer without weakening the other's guarantee.
- **Open for the transformer work:** a learned policy or belief model fits naturally in the *probability* layer. Whether to keep the possibility filter as a hard safety veto over a learned policy should be its own ADR.
