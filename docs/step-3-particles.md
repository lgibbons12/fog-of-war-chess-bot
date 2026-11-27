# Step 3 Spec: Particle Tracker and Risk-Ranked Moves

> **Status: Approved** by Liam on 2026-11-22 (drafted by Claude Code on 2026-11-17). Design rationale is in ADR 0014; Part A configuration in ADRs 0015 and 0016 (all Accepted).

**Goal.**
- Keep a weighted set of **full boards** (particles) that are consistent with every observation so far.
- Use them to estimate, for each candidate move, the **probability that our king is capturable** after it.
- Rank moves with that probability, while the Step 2 possibility check stays the sound worst-case layer (ADR 0008).

**Parts.**
- **A.** Particle tracker (`bot/particles.py`). The core of this step.
- **B.** Risk estimates and particle agents.
- **C.** Experiments and gate.

**Out of scope.**
- Stockfish or any search beyond one ply (Step 4).
- The transformer or any learned model. It is a **parallel track** (see "Decisions so far"); Part A only defines the `OpponentModel` interface it could plug into later.
- Offense or king hunting.
- Clock-adaptive particle counts.

## Step 2 results this builds on

- **Arena agent:** `safety_v2`, key `(known_loss, -material, exposure_count, rng)`. It scores 0.675 [0.648, 0.701] against `baseline`.
- **The gate failed:** `tracked_v2` scored 0.512 [0.484, 0.541] against `safety_v2`.
- **Exposure is sound but uninformative.** About 99% of flagged hidden squares hold no attacker (false-alarm rate 0.991). Exposure only breaks ties after material, so sharper exposure changed few decisions.
- **Losses still come from hidden sliders.** `tracked_v2` vs baseline: rook 123, queen 116, bishop 63.
- **The possibility tracker loses precision as games go on.** Mean support per hypothesis grows from 8.9 to 41 squares, because each hypothesis expands independently.
- **Diagnosis.** We need to know *how likely* an attacker is, not just whether one is possible. That requires joint boards, not per-piece supports.

## Facts this step relies on (verified from `referee.py`)

- **The game starts from a known position.** At ply 0 the true board is the standard start, so the particle set starts exact and only spreads out as hidden moves accumulate.
- **Surviving is evidence.** `outcome()` ends the game as soon as the side to move can capture the other king. It also ends the game at the 50-move rule and when the side to move has no moves. So every observation we receive implies the true board at that moment had `outcome(board, Counter()) is None`, ignoring repetition. Any particle that fails this check is impossible.
- **Our move set is a function of the observation.** Each of our pseudo-legal moves has a visible destination, so every particle that matches the observation gives us the same move set. If a particle's `fow_moves` disagree with `ObservationTracker.legal_moves()`, that's a bug, not a modeling choice.
- **Measured cost** (Windows dev machine, Python 3.11, **verified**):
  - `observation()`: about 73 µs.
  - `fow_moves()`: about 27 µs.
  - Copying a board, generating moves, pushing one, and computing the observation: about 117 µs.
  - The arena machine is unknown; assume it's up to 2× slower.

---

## Part A: Particle tracker (`bot/particles.py`)

### Representation

```python
@dataclass
class Particle:
    board: FowBoard          # full board: castling rights, ep square, halfmove clock, turn
    weight: float            # unnormalized

class OpponentModel(Protocol):
    def weights(self, board: FowBoard, moves: list[chess.Move]) -> list[float]: ...
        # nonnegative weight per move; need not be normalized. Must be deterministic.

class ParticleTracker:
    def __init__(self, side: chess.Color, n: int, model: OpponentModel,
                 rng: random.Random, strict: bool = True): ...   # one particle: the start position
    def on_observation(self, obs: str, ply: int, our_last_move: chess.Move | None,
                       possibility: PossibilityTracker) -> None: ...
    def particles(self) -> list[Particle]: ...
    def loss_probability(self, move: chess.Move) -> float: ...
    def stats(self) -> dict: ...    # distinct count, ESS, depletions, regenerations, timings
```

- **Rule calls come from the referee only:** `FowBoard`, `fow_moves`, `observation`, `outcome`, and `position_key`. No rule logic of our own (invariant 2).
- **The RNG is passed in.** The agent passes its own `random.Random`. Particle code makes RNG calls in a fixed, documented order, and only during resampling and regeneration.
- **Deterministic deduplication.** Particles are merged by the key `(board.board_fen(), board.turn, board.clean_castling_rights(), board.ep_square, board.halfmove_clock)`. Use a `dict`, whose insertion order is deterministic. Iteration order must never depend on `set` or hash order (invariant 4).

### Ply bookkeeping

This is the same as Step 2: observation `p` arrives before ply `p`, and ply `p-1` determines the update.

- **`p == 0`:** filter only.
- **Ply `p-1` was ours:** apply our move, then filter.
- **Ply `p-1` was the opponent's:** expand, then filter.

### Our move (ply `p-1` was ours)

For each particle:

1. **Strict check:** `our_last_move ∈ fow_moves(board)`. If not, that's a bug, so raise in strict mode. In non-strict mode, drop the particle and count it.
2. Push the move.

Then filter (see below). Every particle where the opponent can now capture our king fails the `outcome()` check and is dropped. That is the "we're still alive" evidence.

### Opponent ply (ply `p-1` was the opponent's)

For each particle `(board, w)`:

1. Let `moves = fow_moves(board)` and `q = model.weights(board, moves)`, normalized to sum to 1 over **all** of `moves`.
2. **Cheap prefilter.** These are necessary conditions read off the observations, not rule logic. Skip a move unless:
   - **A piece of ours vanished on square `c`:** the move captures on `c`, or it's an en passant capture whose captured pawn is on `c`.
   - **Nothing of ours vanished:** the move is not a capture of our piece.
   - **Destination:** `obs[to_square]` is `?` or the moving piece's symbol, including the promoted piece for promotions.
3. For each surviving move `m`: copy the board and push `m`. Keep the child only if `observation(child, side) == obs` **and** `outcome(child, Counter()) is None`.
4. Each kept child gets weight `w · q[m]`.

Collect all children, deduplicate by key (summing weights), and then resample (below). This is sequential importance sampling with the exact proposal. Children are enumerated rather than sampled, so a consistent child is never missed for lack of samples.

### Filter (every observation)

- Drop any particle where `observation(board, side) != obs`, or where `outcome(board, Counter()) is not None`.
- After an opponent-ply expansion, the children already passed these checks, so filtering is a no-op there. It matters after our move and at `p == 0`.

### Resampling

- Normalize weights.
- If the number of distinct particles exceeds `n`, **or** the effective sample size `1 / Σ w̄²` falls below `n / 2`, run **systematic resampling** down to `n` draws. Use one `rng.random()` call per resampling. Then deduplicate, summing the counts as weights.
- Otherwise keep the set as is.

### Depletion and regeneration

Resampling can drop the true board, so an empty set is possible even without bugs. Depletion is **not** an inconsistency and does not raise in strict mode.

1. **Regenerate** from the possibility tracker, by rejection sampling:
   - For each hypothesis, in tracker order, choose a square uniformly from its squares that aren't already taken, and a type uniformly from its types. Reject the draw if it doesn't give exactly one enemy king.
   - Build a `FowBoard` from our visible pieces, visible enemies, and the drawn pieces.
   - Enemy castling rights: allowed exactly where the king and rook stand on their start squares (an over-approximation). Our castling rights come from `ObservationTracker`. No ep square. Turn = the side to move. Halfmove clock 0.
   - Keep the board if it passes the filter. Stop after `n` accepted boards or `20 · n` attempts.
   - Accepted boards get equal weight.
2. **If regeneration fails**, the tracker reports `available = False`, and the agent ranks moves without particles (see Part B). Try regenerating again at the next observation.
3. Count depletions, regenerations, and observations with particles unavailable in `stats()`.

Regenerated particles are an approximation, not a posterior. Their purpose is to recover, not to be exact.

### Opponent models

| Name | Weights |
|---|---|
| `uniform` (default) | 1 for every move |
| `capture` | 1 for quiet moves, `1 + k · value(captured)` for captures, with `k = 1` and values P1 N3 B3 R5 Q9 |

Both are pure functions of `(board, moves)`. A learned model (e.g. the transformer) would implement the same interface, but that work is a parallel track and not part of this step.

**Why `uniform` is the default:**
- **We know nothing about arena opponents.** They are other teams' bots, and we have no game data on them. A uniform distribution over legal moves is the maximum-entropy prior: it assumes nothing beyond the rules.
- **It never zeroes a real move.** A biased model that's wrong about an opponent can push the true history's weight toward zero, and resampling then drops it. Under `uniform`, every legal move keeps weight, so being wrong costs calibration rather than depletion.
- **It's interpretable.** Under `uniform`, a particle's weight is proportional to the number of consistent move sequences leading to it, discounted at each ply by how many moves the opponent had. `p_loss` therefore means "the fraction of rules-consistent histories in which this move loses". That is easy to explain in the paper.
- **It costs nothing**, leaving the whole time budget for particles.
- **It's the reference point for any learned model.** The `capture` model and later the transformer are judged by whether they beat `uniform` on calibration and log loss under the same interface.
- **Known weakness:** real bots move with purpose. `uniform` treats a hidden rook heading for our king the same as one shuffling aimlessly, so it probably underestimates risk from purposeful attackers. The calibration metric measures this, and the `capture` model is the first ablation of it.

### Performance budget

- **`n` is chosen by a timing run before any experiment** (see "Choosing `n`" below). `n = 128` is only a working default for writing and testing the code.
- **Per move, on the harness machine:** median total particle time (both updates plus the move decision) **under 0.4 s**, maximum **under 1.5 s**. That leaves room for a 2× slower arena machine within the 2 s increment.
- Measure before optimizing. If the budget fails, report the profile and stop; don't add caching or bitboard shortcuts without asking.

### Choosing `n`

**Timing run:**
1. Play 20 games of `particle_ev300` against `safety_v2` at each `n ∈ {32, 64, 128, 256, 512}`, single worker.
2. Record median and maximum per-move particle time, the distribution of surviving candidates per particle, ESS, and depletions.
3. Choose the **largest `n` that meets the budget.** Record it, with the timing table, in a new ADR before running the experiments.

**Why 128 is the working default:**
- **Speed.** Each opponent ply costs about `n × (27 µs + k × 117 µs)`, where `k` is the number of moves per particle that survive the cheap prefilter. Guessing `k ≈ 15` (**unverified**; the timing run measures it) gives about 1.8 ms per particle. Scoring about 30 candidate moves per particle with push plus `outcome()` adds about 1 ms per particle. So each particle costs roughly 3 ms per full move, and 128 particles come to about 0.35–0.4 s, right at the median budget.
- **Resolution.** Resampling keeps the ESS at or above `n/2 = 64`, so the smallest nonzero `p_loss` that can be estimated is about 1/64 ≈ 1.5%. The standard error at `p = 5%` is about 2.7 points. That is coarse but enough to tell 2% from 20%, which is the distinction the λ grid needs. Halving `n` doubles the smallest resolvable risk, and doubling `n` blows the time budget.
- **Neither number is measured yet.** Both rest on the guess `k ≈ 15`. That's why `n` waits for the timing run.

**Time guard.** If `remaining < 20 s`, skip particle work for this decision and rank as `safety_v2` does. Record whenever this happens. Harness clocks depend on think time, so this guard must **never** trigger in harness games, or determinism breaks. Assert that it doesn't in the determinism test.

---

## Part B: Risk estimates and agents

### Loss probability

For a candidate move `m`:

```
p_loss(m) = Σ_i w̄_i · [ outcome(push(board_i, m), Counter()) reports "King capturable" against us ]
```

That is the weighted fraction of particles where `m` leaves our king capturable, which is exactly the event that loses the game on the next ply. This is computed by the referee's `outcome()`, never by our own attack code.

### Cross-checks with the possibility layer

These must hold whenever particles are available:

- **Known loss ⇒ `p_loss = 1`.** A visible attacker along a fully visible line is present in every particle.
- **Not a known loss and nothing exposed (by the tracker) ⇒ `p_loss = 0`.** Every consistent particle lies inside the tracker's supports.

Neither is enforced at runtime. Both are tested (Tests 3 and 4).

### Agents (registry)

All are sort-key variants of `SafetyAgent` with `tracked=True`. They use the material term from Step 1, in units of 10 × piece value, so a queen is 90.

| Name | Key | Idea |
|---|---|---|
| `particle_v2` | `(known_loss, -material, p_loss, exposure_count, rng)` | Swap in `p_loss` as the tie-break |
| `particle_ev100` | `(known_loss, -(material - 100·p_loss), exposure_count, rng)` | Expected value; a 10% loss risk costs about a pawn |
| `particle_ev300` | same, with λ = 300 | Riskier moves cost more |
| `particle_ev1000` | same, with λ = 1000 | Close to risk-first |

**Why λ ∈ {100, 300, 1000}:**
- **λ is the price of losing the game, in material units.** Losing the king ends the game, which is at least as bad as losing all your material: 8 + 6 + 6 + 10 + 9 = 39 points, or **390 units**. That puts the natural scale of λ in the low hundreds.
- **It sets how much risk a capture can justify.** A capture gaining `G` units beats a safe quiet move iff `G > λ · Δp_loss`:

  | λ | Pawn (10) justifies | Rook (50) justifies | Queen (90) justifies |
  |---|---|---|---|
  | 100 | 10% extra risk | 50% | 90% |
  | 300 | 3.3% | 17% | 30% |
  | 1000 | 1% | 5% | 9% |

- **The grid spans the plausible range on a log scale.** 300 sits just below the material-only anchor of 390, and 100 and 1000 are about 3× either side. λ = 100 is close to `safety_v2`'s material-first behavior. λ = 1000 is near risk-first: with `p_loss` resolved only to about 1.5%, any particle in which a move loses costs at least 15 units, more than a pawn.
- **Step 2 data says the optimum is not at either extreme.** Risk-first orderings lost to material-first (0.370 for `tracked_count` vs `tracked_v2`). Pure material without the exposure tie-break was no better than baseline (0.492 for `safe_material`). So the best λ should be interior.
- **If the best λ lands at an edge of the grid, extend the grid one step** (30 or 3000) before running the gate.

- **If particles are unavailable** (depletion or the time guard), `p_loss` is replaced by `exposure_count > 0` for that decision, and the decision record says so.
- **The decision record adds:**
  - `p_loss` for the chosen move and the minimum over all moves;
  - distinct particles, ESS, depletions, regenerations, and whether particles were available;
  - update and decision times.

---

## Tests

1. **Particle consistency (property test).**
   - Play 200 harness games of `particle_ev300` against `random`, `baseline`, and `safety_v2`, in both colors, with `n = 32` to keep it fast.
   - At every observation, every particle must satisfy `observation(board, side) == obs` and `outcome(board, Counter()) is None`.
   - At every decision, every particle's `set(fow_moves(board))` must equal `set(tracker.legal_moves())`.
2. **Particles ⊆ possibility tracker.** At every observation, outside regeneration, every particle's enemy pieces must have a bipartite matching onto the tracker's hypotheses. Reuse the matcher from `tests/test_possibility.py`. This checks both trackers against each other.
3. **Known-loss cross-check:** known loss ⇒ `p_loss == 1` for every legal move at every decision in Test 1's games.
4. **Safe cross-check:** no known loss and empty tracker exposure ⇒ `p_loss == 0`, over the same games.
5. **Scripted unit tests:**
   - The start position gives exactly one distinct particle, and stays exact through each side's first observation.
   - Black's view after each of White's 20 possible first moves: the set should hold exactly the consistent first moves, with weights proportional to the model.
   - Our capture removes the captured piece in every particle.
   - An enemy capture on a known square keeps only the children that capture there, including en passant.
   - A particle where the enemy could capture our king after our move is dropped.
   - Depletion: feeding an observation from a different game regenerates particles consistent with it, or marks particles unavailable. It never raises, even in strict mode.
   - Resampling is deterministic for a given seed, and makes exactly one `rng.random()` call.
6. **Determinism:** `run_match_pairs` with `workers=1` and `workers=4` gives identical summaries for `particle_ev300`, and the time guard never triggers.
7. **Leakage:** `bot/particles.py` imports only stdlib, `chess`, `referee`, and `bot.*`.
8. **All earlier tests still pass,** including equivalence, soundness, and protocol transcripts with a particle agent.

## Metrics (record for the best particle agent; truth comes from the harness only)

- **Calibration:** bucket `p_loss` of the chosen move (0, (0, .01], (.01, .05], (.05, .2], > .2) against the actual rate of immediate king-capture losses. This is the headline result for the paper.
- **Truth coverage:** the fraction of observations where the true board's key is among the particles, and the mean normalized weight on it, both by ply bucket.
- **Per-square accuracy:** the log loss of the particles' piece marginals on `?` squares against the truth, by ply bucket. Compare it with the possibility tracker's uniform-over-support baseline.
- **Set health:** distinct particles, ESS, depletions per game, and regeneration success rate.
- **Time:** median and maximum per update and per decision, and games per second in the harness.
- **Loss breakdown** (a / b / c), plus hidden-attacker types in losses, as in Step 2.

## Experiments and gate

200 pairs each over seeds 0–2, reporting per-seed and pooled scores. Estimated cost at `n = 128`: about 10 to 20 minutes per matchup with 22 workers (**unverified**; measure it on the first run).

| Matchup | Purpose |
|---|---|
| `particle_v2` vs `safety_v2` | Does `p_loss` help as a tie-break? |
| `particle_ev{100,300,1000}` vs `safety_v2` | **Gate:** the best one's pooled lower bound > 0.5 |
| best particle agent: `uniform` vs `capture` model | Opponent-model ablation |
| best particle agent at `n ∈ {32, 128, 512}` vs `safety_v2` | Does more compute help? |
| best particle agent vs `baseline` | Absolute strength |
| best particle agent vs `random` | Sanity check |

If the gate passes, package the best particle agent, run `scripts/check_package.sh`, and update `AGENTS.md` and `docs/log.md`. Write an ADR for the arena-agent decision either way.

## Report back

- Test output, including how many particle-observations Tests 1–4 checked.
- The experiment table with per-seed and pooled scores, termination reasons, and loss breakdowns.
- The calibration table, truth coverage, and per-square log loss against the possibility baseline.
- Timing on the harness machine against the budget, plus a profile if it fails.
- Depletion and regeneration counts.
- New ADRs, deviations, and open questions.

## Known limitations (deliberate)

- **One-ply risk only.** `p_loss` covers the opponent's immediate reply, not two-move threats or our own attacking chances. That is Step 4's job.
- **The opponent model is a guess.** `uniform` treats a strong opponent's moves as random, so `p_loss` will be miscalibrated against strong bots. The calibration metric measures how badly.
- **Truth can be lost.** Resampling can drop the true board, and regeneration is approximate. The possibility layer still provides soundness, because known losses are always ranked first.
- **Material is still read from the observation alone.** Expected material over particles is deferred.

## Decisions so far (Liam, 2026-11-17)

1. **Particle count:** chosen by the timing run (see "Choosing `n`"), not fixed in advance.
2. **The transformer:** a parallel track, outside Step 3. Its results will be compared separately. Integration (e.g. as an `OpponentModel`, subject to the stdlib-plus-`chess` constraint) gets its own ADR later.
3. **Depletion:** rebuild from the possibility tracker, as specified.

## Resolved questions (Liam, 2026-11-22)

1. **λ grid:** {100, 300, 1000} as proposed, extended one step if the best λ lands on an edge.
2. **Opponent model:** `uniform` (ADR 0016) plus the existing `capture` variant as the one ablation.
