# Step 1 Spec: Safety Agent (first arena submission)

**Goal.** A cheap, observation-only agent that never loses to a threat it could have known about, and that minimizes exposure to threats it can't see.

It is our first submission and the baseline that every later step must beat.

**Prerequisite.** Step 0 is merged and its equivalence test passes.

**Out of scope:**
- Cross-ply history (Step 2, the possibility tracker).
- Particles.
- Stockfish.
- Time management beyond the fallback guard below.

## Verified facts this design relies on (from `referee.py`)

- **King capture happens automatically.** `outcome()` runs before every ply. If the side to move can capture the opposing king, that side wins without moving. So:
  - We never choose a king capture. If an enemy king were visible, the game would already be over.
  - **We win only when the opponent's move leaves its king capturable.** We lose only when our move leaves ours capturable (or we have no legal move).
- **Every character of the current observation is accurate at our decision time.**
  - Enemy pieces we see are really there.
  - Squares marked `-` really are empty.
  - Squares marked `?` are unknown.
- **Enemy pieces don't move between our move and the outcome check.** So the question "does our move lose immediately?" depends only on the board right after our move.

## Core idea: an observation-only possibility check

After a candidate move, build the post-move square array and scan outward from our king. Treat every `?` square as possibly holding **any** enemy piece.

This is a sound over-approximation of "our king is capturable". It can report a threat that isn't there, but it never misses a real one. Step 2 will tighten it by using history to restrict which hidden squares can hold which pieces.

## Component: `bot/safety.py`

```python
@dataclass(frozen=True)
class SafetyReport:
    known_loss: bool                 # a visible enemy piece attacks our king after the move
    exposed: frozenset[int]          # '?' squares that could hold an attacker of our king
    king_square: int

def apply_move(obs: str, move: chess.Move, side: chess.Color) -> list[str]:
    """Return the 64-char array after our move, from our perspective."""

def king_safety(cells: list[str], side: chess.Color) -> SafetyReport:
    """Scan from our king; see the rules below."""

def attackers_of(cells: list[str], square: int, side: chess.Color) -> tuple[list[int], list[int]]:
    """Return (known enemy attacker squares, possible '?' attacker squares) for any square."""
```

`king_safety` is `attackers_of` applied to our king's square.

### `apply_move` rules

Derive everything from the observation and the move; never use a board containing invented pieces.

- **Normal move:** set `from` to `-` and `to` to the moving piece. On promotion, `to` gets the promoted piece instead.
- **Castling:** the king moves two files. Also move the rook (h-file to f-file, or a-file to d-file) on our back rank.
- **En passant:** a pawn moves diagonally onto a `-` square. Also set the captured pawn's square, behind the destination, to `-`.
- **Assertions:** `from` holds our piece and `to` is not `?`. The tracker's legal moves guarantee both, but assert anyway.

### `attackers_of(cells, sq, side)` rules

- **Knight offsets:**
  - An enemy knight there is a **known** attacker.
  - A `?` there is a **possible** attacker.
- **Each of the 8 rays from `sq`, stepping outward:**
  - `-`: keep going.
  - Our piece: stop.
  - Enemy piece: it's a known attacker if its type attacks along this ray at this distance, then stop. The cases:
    - Rook or queen on an orthogonal ray, any distance.
    - Bishop or queen on a diagonal ray, any distance.
    - King at distance 1.
    - Pawn at distance 1 on a diagonal pointing toward its forward direction. White pawns attack upward, Black pawns downward.
  - `?`: a possible attacker, then stop. A queen could attack from any square along any open line, so no piece-type filtering applies yet.
- Squares are counted once each, so `exposed` is a set.

**Optional exact refinement (allowed, not required).** Pawns can't stand on rank 1 or rank 8. Only apply it if it changes a result, because it doesn't matter here: the queen case already covers those squares.

## Agent: `bot/agents/safety_agent.py`, registry name `"safety"`

For each legal move, compute a sort key and choose the minimum:

```
key(move) = (
    report.known_loss,                  # False before True
    exposure_term(report),              # see the modes below
    -material_score(move),
    rng.random(),                       # random tie-break (seeded)
)
```

- `exposure_term`, parameterized by `exposure_mode`:
  - `"count"`: `len(report.exposed)`. This is the default.
  - `"binary"`: `0 if not report.exposed else 1`.
- `material_score(move)`, in integers: P=1, N=3, B=3, R=5, Q=9.
  - Plus `10 × value(captured)`.
  - Plus `5 × value(promotion)`, the same weight `baseline.py` uses.
  - Minus `10 × value(moving piece)` if `attackers_of(post_cells, move.to_square, side)` returns any **known** attacker. This is a crude trade check that only uses visible pieces.
- **Registry entries:** `"safety"` uses `"count"` mode and `"safety_binary"` uses `"binary"` mode.

**Decision record.** After each choice, store `self.last_decision` as a small dict with:
- the chosen move;
- its `SafetyReport`;
- the number of legal moves;
- the number of moves with `known_loss=False`;
- the minimum exposure across all moves.

The harness may read this; it's data flowing out of the agent, so it's no leak. Add a per-frame `decision` field to harness replays.

**Fallback guard (protocol only).**
- `bot/protocol.py` wraps `choose_move` in a try/except.
- On an exception, it logs the traceback to stderr and plays the random agent's choice from the same tracker.
- The harness runs in `strict=True` mode, where exceptions propagate so bugs fail tests loudly.

## Tests

1. **`apply_move` unit tests.** Use FEN positions with `observation(board, side)` and check:
   - a quiet move;
   - a capture;
   - each of the 4 promotions;
   - kingside castling and queenside castling, for each color;
   - en passant, for each color.
2. **`attackers_of` unit tests.** Hand-built positions covering:
   - each piece type as a known attacker;
   - each piece type as a blocked non-attacker;
   - the pawn direction, both colors;
   - a `?` on an open ray;
   - a `?` behind one of our blockers, which should *not* count;
   - a `?` at a knight square.
3. **Soundness property test (the key one).**
   - Play 200 harness games of `safety` vs `random` and `safety` vs `baseline`, both colors.
   - At **every** decision, for **every** legal move (not just the chosen one), push the move on a copy of the true board.
   - Assert that if `report.known_loss` is False and `report.exposed` is empty, our king is not attacked on the true board (`board.is_attacked_by(not side, king_sq)`).
   - Also assert that if `known_loss` is True, the king really is attacked.

   These two checks validate the over-approximation exactly. This test is allowed to use the true board; the agent is not.
4. **Starter, Step 0, and leakage tests still pass.**

## Experiments and gate

Run with `harness.cli`, 200 pairs each, seed 0:

| Matchup | Purpose |
|---|---|
| `safety` vs `baseline` | **Gate.** The lower Wilson bound must be > 0.5. |
| `safety` vs `random` | Sanity check. Should be near 100%. |
| `safety_binary` vs `baseline` | Ablation: does counting exposure beat a yes/no flag? |
| `safety` vs `safety_binary` | Direct comparison. |

## Report back

- Test output.
- For each matchup:
  - the score with its CI, per color;
  - the reason histogram;
  - mean plies per game.
- **Loss breakdown** for `safety`, using replay `decision` records plus true boards. Split king-capture losses into three groups:
  - (a) A safe move (`known_loss=False`, exposure 0) existed, but we chose an exposed move. This should be impossible in `count` mode.
  - (b) Every move was exposed, and the hidden threat was real.
  - (c) Every move was a known loss.
- **Draw breakdown:** repetition vs. 50-move vs. ply cap. A defensive bot may draw a lot; that number decides what Step 1.5 or Step 2 should address.
- Median and maximum `choose_move` time.

## Packaging for the arena

- Add `scripts/package.sh`. It builds `dist/bot.zip` containing `bot/`, `referee.py`, and a root `run.sh` that runs `exec python3 -u -m bot.protocol --agent safety`.
- **Don't include** `harness/`, `tests/`, replays, or `.venv`.
- Before uploading, unzip into a temp directory and run one local `referee.py` game in each color against `baseline.py` from there.

## Known limitations (deliberate; later steps address them)

- **Exposure is very coarse.** Every `?` on an open line counts, so most midgame moves will be exposed. Step 2 adds history, piece counts, and reachability to shrink this.
- **No offensive plan.** We win only on opponent blunders. Attacking hidden squares where the enemy king is likely to be needs Step 2's tracking.
- **No own-king visibility penalty yet.** We can't estimate what the opponent sees without a belief over their pieces.