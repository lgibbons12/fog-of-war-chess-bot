# Step 2 Spec: Finalize the Safety Agent + Possibility Tracker

**Goal.**
- Ship the Step 1 result.
- Build a **history-based, sound possibility tracker** over enemy pieces.
- Use it to make king-safety exposure informative.

**Parts.**
- **A.** Finalize and submit the Step 1 agent. Small; do it first.
- **B.** Possibility tracker. The core of this step.
- **C.** Tracker-based safety, plus experiments.

**Out of scope.** Probabilities and particles (Step 3), Stockfish, and offense or king hunting.

## Step 1 results this builds on

- Count-mode exposure scored 0.474 against `baseline`; binary mode scored 0.565.
- Reordering to (known loss, material, exposure) scored 0.645, 0.629, and 0.634 over three seeds.
- **Every** loss was type (b): all non-losing moves were exposed, and the hidden attacker was real. Most attackers were sliders: rook 76, queen 54, bishop 53.
- **Diagnosis.** Without history, every `?` on an open line counts as a possible queen, so exposure carries almost no information.

---

## Part A: Finalize the Step 1 agent

1. **Commit Step 1 as is,** in logical commits:
   - the seed fix;
   - `safety.py` plus its tests;
   - the agents;
   - the harness and breakdown additions;
   - packaging.
2. **Seed check.** Pair seeds must be deterministic across processes. Use integer arithmetic or `random.Random(f"{base_seed}:{i}")`, **never** `hash()` of a `str`. Add a test that runs `run_match_pairs` with `workers=1` and `workers=4` and asserts identical summaries. Re-run the Step 0 numbers in `docs/log.md`.
3. **Registry additions.** Each is a sort-key variant, not a new class.

   | Name | Key |
   |---|---|
   | `safety_v2` | `(known_loss, -material, exposure_count, rng)` |
   | `safe_material` | `(known_loss, -material, rng)` (control: no exposure term) |

4. **Run this batch** (200 pairs, seeds 0–2): `safety_v2` vs `baseline`, `safe_material` vs `baseline`, and `safety_v2` vs `safe_material`.
5. **Submit the simpler agent unless the other is clearly better.** Submit `safe_material` unless `safety_v2` beats it with a lower confidence bound above 0.5. Run `scripts/check_package.sh` first.
6. **Update `AGENTS.md`:** the current step is Step 2, and the arena agent is `<name>`. Log the results in `docs/log.md`.

---

## Part B: Possibility tracker (`bot/possibility.py`)

### What it must guarantee

**Soundness (blocking).** At every observation, there is a one-to-one assignment of the true enemy pieces to tracker hypotheses such that each true piece's square is in its hypothesis's `squares` and its type is in its hypothesis's `types`.

The tracker may be imprecise. It may **never** exclude the truth.

### Representation

```python
@dataclass
class EnemyPiece:
    types: frozenset[str]     # subset of {"P","N","B","R","Q","K"}
    squares: int              # bitboard (python int, chess.BB_* convention)

class PossibilityTracker:
    def __init__(self, side: chess.Color): ...        # 16 exact hypotheses at the start squares
    def on_observation(self, obs: str, ply: int, our_last_move: chess.Move | None,
                       prev_obs: str | None) -> None: ...
    def possible_types_at(self, sq: int) -> frozenset[str]: ...
    def certainly_occupied(self) -> int: ...          # bitboard of squares definitely holding an enemy piece
    def pieces(self) -> list[EnemyPiece]: ...
```

- Track **identities**, not types. The precision depends on it: "this pawn" moving and "that queen" moving can't both happen in one ply.
- Bishop color needs no special case. A bishop's reach only covers squares of its own color.

### Ply bookkeeping (verified protocol facts)

- Exactly one observation arrives before every ply, and observation `p` comes before ply `p`.
- Ply `p` is ours iff `(p % 2 == 0) == (side == WHITE)`.
- The agent counts observations to get `p`. Assert that `choose_move` is only ever called on our plies.
- When observation `p` arrives:
  - `p == 0`: filter only.
  - Ply `p-1` was **ours**: apply our move (see "Our move"), then filter.
  - Ply `p-1` was the **opponent's**: expand (see "Opponent ply"), then filter.
  - Black's first observation (`p = 0`) comes before White's first move, so Black's second observation is an opponent-ply update.

### Our move (ply `p-1` was ours)

- Captures are visible, because our destination squares are always visible. If the move captures an enemy piece of type `t` on square `sq` (including en passant, where `sq` is the captured pawn's square), apply **capture removal**:
  - Find the candidates: hypotheses with `t ∈ types` and `sq ∈ squares`.
  - **Exactly one candidate:** delete it.
  - **k > 1 candidates:** replace them with `k-1` hypotheses. Each gets `types` = the union of the candidates' types and `squares` = the union of their squares, minus `sq`. This is sound because each survivor is one of the originals. It is imprecise, but rare.
  - **Zero candidates:** inconsistency (see below).

### Opponent ply (ply `p-1` was the opponent's)

**Inputs:**
- `prev_obs`: the observation after our move, before their ply.
- `obs`: the new observation.
- `lost`: the square where one of our pieces disappeared. Compare our pieces between `prev_obs` and `obs`; at most one can vanish per ply.

**Blockers** (squares certainly occupied *before* their move):
- our piece squares in `prev_obs`;
- visible enemy squares in `prev_obs`;
- singleton supports, meaning hypotheses whose `squares` has exactly one bit set.

**Non-capture ply** (`lost is None`). Every hypothesis `h` may have moved:
- `h.squares |= reach(h, blockers, capture_target=None)`.
- This is the only over-approximation that matters. Only one piece actually moved, but each hypothesis is expanded independently. That is sound, and exact for the question "does a single attacker exist".

**Capture ply** (`lost = c`). Exactly one enemy piece moved, and it captured on `c`:
- For each `h`: if `h` could capture on `c` from its squares, add `c` to `h.squares`. Otherwise leave it unchanged.
- **En passant case:** if `c` holds our pawn that double-pushed on our last move, a hypothesis with `"P"` in its types that could capture en passant may instead land on the square behind `c`. Add that square too.

**`reach(h, blockers, capture_target)`** is the union over `t ∈ h.types` and `s ∈ h.squares`:
- **N, K:** attack-table squares.
- **K:** also castling destinations. If `s` is the king's start square and a hypothesis with `"R"` contains the corresponding rook start square, add the king's castling destination. **The rook's hypothesis must also gain its castling square.** Implement castling as a joint update: if a K hypothesis and an R hypothesis both still contain their start squares, add g/c to the K hypothesis and f/d to the R hypothesis.
- **B, R, Q:** step along rays from `s`. Each square reached is added. Stop *after* a blocker; the capture case is handled separately. Stop at the board edge.
- **P, non-capture ply:**
  - One push forward if the target is not a blocker.
  - Two pushes from the start rank if neither square is a blocker.
  - **No diagonal moves**, because pawns only move diagonally when capturing.
- **P, capture ply:** only the diagonal onto `c`, plus the en passant case.
- **Promotion:** a pawn reaching our back rank adds `{"N","B","R","Q"}` to `h.types`. Keep `"P"` in the set; that's simpler and still sound.

### Filter with an observation

1. For every square that is `-` or holds our piece, remove it from every hypothesis.
2. For every visible enemy piece of type `t` on square `sq`, find the candidates (`t ∈ types` and `sq ∈ squares`):
   - **Exactly one:** set its `squares = {sq}` and `types = {t}`.
   - **Several:** leave the candidates alone, and remove `sq` from every non-candidate.
   - **None:** inconsistency.
3. **Optional, but cheap and exact:** repeat step 2 until nothing changes. A hypothesis collapsed in one pass can make another visible piece's candidate set unique.
4. Every hypothesis must have nonempty `squares` and `types`. Otherwise: inconsistency.

### Inconsistency handling

- **`strict=True`** (harness and tests): raise `TrackerInconsistency` with the ply and observation. Under the soundness guarantee this means a bug.
- **`strict=False`** (arena): log to stderr. Then **reset to a coarse but sound state**: one hypothesis per enemy piece, with `types` = all six and `squares` = every `?` square plus the visible enemy squares. Keep going.
- Count resets in `last_decision`. The target is zero in harness games.

### Performance budget

- Median update under 20 ms, maximum under 200 ms, on the harness machine.
- Plain Python loops over bitboards are fine at this size: 16 hypotheses × up to 64 squares × 8 rays.
- Don't optimize until it's measured.

---

## Part C: Tracker-based safety

Extend `attackers_of(cells, sq, side, tracker=None)`:

- **`tracker=None`:** exactly the Step 1 behavior. Keep it; it's the ablation.
- **With a tracker:**
  - A **known** enemy piece is handled as in Step 1.
  - A `?` square `x` counts as a **possible** attacker iff some hypothesis `h` has `x ∈ h.squares` and some `t ∈ h.types` attacks `sq` from `x` along this ray at this distance (or is a knight, for knight squares).
  - **Rays continue through `?` squares unless `x ∈ tracker.certainly_occupied()`.** This differs from Step 1 deliberately. Once types are filtered, the first `?` on a ray may be harmless (only a pawn could be there) while a later one could hold a rook.
  - Stop at our pieces, at visible enemy pieces, and at certainly occupied squares. Check the occupant of a certainly occupied square as a possible attacker first.
- **Post-move effects:**
  - Squares our move vacates are `-`.
  - The destination is ours.
  - A captured piece's hypotheses are *not* removed for the safety query. Its square is ours now, so it can't attack from there anyway. That's sound and simple.
- **Sanity check:** when tracker supports cover every `?` with all six types, the result must reduce to Step 1's. Write this as a test.

### Agents (registry)

| Name | Key | Exposure source |
|---|---|---|
| `tracked_v2` | `(known_loss, -material, exposure_count, rng)` | tracker |
| `tracked_count` | `(known_loss, exposure_count, -material, rng)` | tracker |
| `tracked_binary` | `(known_loss, exposed>0, -material, rng)` | tracker |

`tracked_count` is worth re-testing. It lost in Step 1 *because* exposure was uninformative; with the tracker, exposure-first ordering may now win.

---

## Tests

1. **Tracker soundness (the key one).**
   - Play 200 harness games: `tracked_v2` vs `random`, `baseline`, and `safety_v2`, in both colors.
   - At every observation, for **our** tracker, check that a bipartite matching exists from the true enemy pieces to hypotheses, where a piece at `sq` with type `t` can match `h` iff `sq ∈ h.squares` and `t ∈ h.types`. Use simple augmenting paths.
   - Also assert `certainly_occupied()` ⊆ the true enemy-occupied squares.
   - Zero resets and zero inconsistencies.
2. **Targeted tracker unit tests**, built from short scripted move sequences with the referee:
   - a hidden knight tour;
   - a queen sliding behind a pawn: **blocked** on ply 1, **allowed** after the pawn has had a ply to move;
   - an enemy capture of our piece, checking that all other hypotheses stay unchanged;
   - enemy en passant;
   - enemy castling in both directions;
   - promotion;
   - our capture with an ambiguous candidate set, checking the merge rule;
   - a bishop that never reaches an off-color square.
3. **Safety soundness (from Step 1, now with the tracker).** For every legal move at every decision: if `known_loss` is False and `exposed` is empty, the king is not attacked on the true board.
4. **Reduction test.** A coarse tracker gives identical `SafetyReport`s to `tracker=None` over the Step 1 replay set.
5. **All earlier tests still pass,** including the equivalence and leakage tests. The tracker may import only `chess` and `referee` rule functions.

## Metrics (new; record for both the Step 1 coarse check and the tracker)

- **Safe-move availability:** the fraction of our decisions where at least one non-losing move has zero exposure.
- **False-alarm rate:** the fraction of flagged `?` exposure squares with no real attacker on the true board, broken down by possible type.
- **Tracker precision, per ply:**
  - mean `popcount(squares)` per hypothesis;
  - the fraction of `?` squares where `"Q"` is possible;
  - plotted against ply number.
- **Update time:** median and maximum per update.

## Experiments and gate

200 pairs each over seeds 0–2. Report pooled scores and per-seed scores.

| Matchup | Purpose |
|---|---|
| `tracked_v2` vs `safety_v2` (or the submitted agent) | **Gate:** pooled lower bound > 0.5 |
| `tracked_count` vs `tracked_v2` | Does informative exposure prefer exposure-first ordering? |
| `tracked_binary` vs `tracked_v2` | Ablation |
| best tracked agent vs `baseline` | Absolute strength against the fixed reference |
| best tracked agent vs `random` | Sanity check |

If the gate passes, package and submit the best tracked agent, then update `AGENTS.md` and `docs/log.md`.

## Report back

- Part A batch results, and which agent was submitted.
- Test output, including how many observations the soundness test checked.
- The metrics above for coarse vs tracker, with a precision-vs-ply chart if easy.
- Experiment table, with the reason histogram and loss breakdown (a/b/c) per matchup.
- Hidden-attacker type counts in losses, compared with Step 1's rook 76 / queen 54 / bishop 53 / knight 21 / pawn 7.
- Deviations and open questions.

## Known limitations (deliberate)

- **Independent per-hypothesis expansion over-counts.** Over many hidden plies, every hypothesis grows as if it alone had moved. Joint constraints come in Step 3 with particles.
- **No probability.** A square where a queen is merely possible weighs the same as one where it is likely.
- **No negative information from blocked pawns.** A `?` in front of our pawn means *some* enemy piece is there, but the factored form can't use that without an assignment step. Optional refinement: if exactly one hypothesis can be on that square, collapse it. That's sound; add it if it's cheap.