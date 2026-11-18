# 0014. Step 3 particle filter: enumerated children, referee-only consistency, risk as expected value

- **Status:** Proposed
- **Date:** 2026-11-17
- **Step:** 3
- **Decided by:** Claude Code (draft spec), pending team review
- **Source:** `docs/step-3-particles.md`

## Context

Step 2 showed that worst-case exposure is sound but uninformative: about 99% of flagged squares hold no attacker, and the gate failed (0013). Ranking moves needs the *probability* of king capture, which requires joint board hypotheses (0008, 0010).

## Decision (proposed)

1. **Particles are full `FowBoard`s** with weights, starting from the known start position.
2. **Consistency is decided only by the referee.** A particle survives iff `observation(board, side) == obs` and `outcome(board, Counter()) is None`. The second condition turns "the game is still going" into evidence: both kings were safe at every observation.
3. **Opponent plies enumerate every consistent child** (the exact proposal) instead of sampling one move per particle. Children are weighted by a pluggable `OpponentModel` (default uniform). Duplicates are merged, and the set is systematically resampled down to `n` when it grows too large or the ESS drops.
4. **Depletion is expected, not a bug.** Recover by rejection-sampling from the possibility tracker's supports. If that fails, fall back to possibility-only ranking.
5. **Risk enters as expected value.** The main candidates use `(known_loss, -(material - λ·p_loss), exposure, rng)`. `p_loss` as a pure tie-break (`particle_v2`) is kept as a control.

## Alternatives considered

- **Sample one opponent move per particle (bootstrap filter):** cheaper per particle, but most samples contradict the next observation, and the set depletes quickly. Since we must call `observation()` on each candidate anyway, enumerating costs little extra and never misses a consistent child.
- **Our own fast consistency check with bitboards:** faster, but reimplements visibility rules (invariant 2). Deferred unless timing forces it, and then only with a test against `observation()`.
- **`p_loss` as a tie-break only:** expected to repeat 0013's failure, since tie-breaks change few decisions. Kept as a control.
- **Risk-first ordering:** like Step 1's exposure-first agent, which lost to material-first. λ = 1000 approximates this.

## Evidence

- **verified:** benchmark on the Windows dev machine (Python 3.11):
  - `observation()` takes about 73 µs.
  - Copying a board, generating moves, pushing one, and computing the observation takes about 117 µs.
  - At about 15 surviving candidates per particle, `n = 128` costs roughly 0.2 s per opponent ply (assumed arithmetic).
- **assumed:** every particle consistent with the observation gives us the same pseudo-legal move set, because each of our move destinations is visible. Test 1 checks this.
- **unverified:** that `p_loss` is calibrated well enough to beat `safety_v2`. That is the Step 3 gate.

## Team decisions recorded (Liam, 2026-11-17)

- `n` is not fixed in advance. It's the largest value meeting the time budget in a timing run over `n ∈ {32, 64, 128, 256, 512}`, recorded in its own ADR.
- The transformer stays a parallel track, outside Step 3.
- Depletion recovery rebuilds from the possibility tracker (item 4 above).

Still open: the λ grid and the opponent-model variants. This ADR stays Proposed until the spec is accepted.

## Consequences

- The `OpponentModel` interface is where a learned model (the transformer) could plug in later.
- Calibration of `p_loss` against real losses becomes a paper-ready result, whether or not the gate passes.
- Experiments get much slower, from hundreds of games per second to an estimated 1 to 2 games per second per worker.
