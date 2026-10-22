# Step 0 Spec: Agent Interface + In-Process Harness

**Goal.** One agent class that runs unchanged in the arena and in a fast local harness. The harness must be *provably* equivalent to `referee.py`.

**Out of scope.** Any strategy beyond the two ported starters, Stockfish, clock enforcement, SPRT.

## Verified facts this relies on (from the repo)

- `referee.py` exposes `FowBoard`, `fow_moves`, `observation`, `outcome`, `position_key`, `run_match`.
- Referee loop per ply: check `outcome()` → check `max_plies` → send observation to **both** sides (White first) → mover gets clock → validate move ∈ `fow_moves(board)` → push → increment repetition counter.
- Replay frames: `{ply, board, white, black, move, clocks}`.
- Arena cap is 1,000 plies; the local referee default is 10,000. **The harness defaults to 1,000.**
- `uniform_random.ObservationTracker` already handles castling rights, en passant inference, and exact legal moves.

## Layout

```
bot/                     # everything submitted (zip root = bot/ contents + referee.py)
  __init__.py
  agent.py               # Agent base class
  tracker.py             # ObservationTracker + candidates + infer_en_passant (copied verbatim from uniform_random.py)
  agents/
    __init__.py          # REGISTRY: dict[str, type[Agent]]
    random_agent.py      # port of uniform_random.py
    baseline_agent.py    # port of baseline.py (faithful, including its missing en passant)
  protocol.py            # stdin/stdout loop -> Agent calls
  run.sh                 # exec python3 -u protocol.py --agent <name>
harness/                 # never submitted
  game.py                # play_game()
  match.py               # run_match_pairs()
  stats.py
  cli.py
tests/
  test_equivalence.py
  test_leakage.py
  test_protocol.py
  test_determinism.py
```

Keep the starter files at the repo root untouched. Point `test_uniform_random.py` at `bot.tracker` only if you copy the tracker. Don't modify the tracker's logic.

## Interfaces

### `bot/agent.py`

```python
class Agent:
    def __init__(self, side: chess.Color, base: float, increment: float, seed: int | None): ...
    def observe(self, obs: str) -> None: ...                 # called before every ply, both sides
    def choose_move(self, remaining: float) -> chess.Move: ...  # called only on our turn
```

- `observe` must accept repeated calls with no move in between: each ply sends an observation to both players.
- `choose_move` must call `tracker.record_move(move)` before returning. Do it in the base class so subclasses implement only `_select(remaining) -> chess.Move`.
- If there are no legal moves, raise `NoLegalMoves`. The harness and protocol treat this as a loss, matching the referee's "No legal moves".

### `bot/protocol.py`

- Port `uniform_random.main()`: read `fow`, read the header, construct the agent, print `ready`.
- A 64-character line goes to `observe`. A numeric line goes to `choose_move`, then print `move <uci>`.
- CLI: `--agent NAME` (registry key) and `--seed INT`.
- **Nothing else may go to stdout.** All diagnostics go to stderr.

### `harness/game.py`

```python
def play_game(white: str, black: str, seed_white: int, seed_black: int,
              max_plies: int = 1000, record_frames: bool = True) -> dict
```

- Mirror `referee.run_match`'s loop order exactly, importing the referee's functions; don't reimplement rules.
- Agents receive **only** `observation(board, side)` strings and a float clock. Never pass a board.
- Time each `choose_move` with `time.perf_counter()`. Store it per frame as `thinkSeconds`. No forfeits.
- Return a dict in the referee's replay schema: `result`, `reason`, `frames` (same keys, with `clocks` replaced by `thinkSeconds`).
- Map agent errors to a loss with the same `reason` text the referee uses:
  - exception → `"Bot exited"`
  - illegal move → `"Illegal move: <uci>"`
  - `NoLegalMoves` → `"Bot exited"` (the subprocess bot returns, and the referee sees an exit)

  Never let one game crash the batch.

### `harness/match.py`

```python
def run_match_pairs(agent_a: str, agent_b: str, n_pairs: int, base_seed: int,
                    workers: int = os.cpu_count(), max_plies: int = 1000) -> list[GameSummary]
```

- Pair `i` uses seeds derived from `base_seed + i`. It plays A-White vs B-Black, then B-White vs A-Black, with the same seeds per agent.
- Use a `multiprocessing.Pool`. Pass registry **names** (strings), not objects, so tasks pickle.
- `GameSummary`: `pair, a_color, result, reason, plies, a_think_total, a_think_max`. Write it as JSONL. Save full replays only if `--save-replays` is set.

### `harness/stats.py`

- Score = (W + ½D)/N from A's perspective.
- Wilson 95% interval on the score, overall and per color.
- Report the termination-reason histogram. It tells you how games end (king capture, repetition, cap), which matters immediately.

### `harness/cli.py`

`python -m harness.cli A B --pairs 200 --seed 0 [--workers N] [--save-replays DIR]`

Prints W/D/L, score with CI, per-color scores, the reason histogram, mean/max think time, and games/sec.

## Tests (acceptance criteria)

1. **Equivalence (the key one).** For seeds 0–9, and for both `random vs random` and `random vs baseline`:
   - Run the subprocess `referee.run_match` with the starter scripts and `--seed`.
   - Run `play_game` with the ported agents and the same seeds.
   - Assert `result`, `reason`, and every frame's `board`, `white`, `black`, and `move` are identical.

   This proves the ports and the harness loop are faithful. Note that `baseline.py` defaults to `--seed 1`, so pass seeds explicitly.
2. **Leakage.**
   - (a) An AST scan of `bot/**/*.py`: imports are limited to stdlib, `chess`, `referee`, and `bot.*`. Any `harness` import fails.
   - (b) A spy agent asserts that every `observe` argument is a `str` of length 64 over `?-PNBRQKpnbrqk`, and every `choose_move` argument is a float.
3. **Protocol.** `referee.run_match` with `bot/run.sh`-equivalent argv for `random` and `baseline` completes with no `failedSide`.
4. **Determinism.** Running `run_match_pairs` twice with the same args produces identical summaries, excluding timing fields. Use `workers=1` and `workers=4` and compare.
5. Existing starter tests still pass.

## Report back when done

- Test output.
- `random vs baseline` over 200 pairs: score, CI, and reason histogram.
- Games/sec for `random vs random`.

## Gotchas

- Seed exactly as the starters do: `random.Random(seed)`, then the same call sequence (`rng.choice` vs `rng.random()` in baseline's scoring). Any extra RNG call breaks equivalence. That's the point of the test.
- `observation()` for the side **not** to move clears en passant. Call the referee's function; don't recreate this.
- Increment the repetition counter after every push, as the referee does, or threefold draws will diverge.