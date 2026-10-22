# Project log

## Step 0: Agent interface + in-process harness (2026-10-22)

Spec: `docs/step-0-spec.md`. Status: implemented, all acceptance tests passing on Linux (WSL Ubuntu). Not yet committed.

### What we did

**Bot (`bot/`, submitted code)**
- `tracker.py`: `OBSERVATION_CHARACTERS`, `infer_en_passant`, `candidates`, and `ObservationTracker`, copied verbatim from `uniform_random.py` with a script (not retyped).
- `agent.py`: `Agent` base class and `NoLegalMoves`. `choose_move` calls the subclass's `_select`, then `tracker.record_move`, so subclasses never forget to update castling rights. Each agent owns one `random.Random(seed)`.
- `agents/random_agent.py`: port of `uniform_random.py`, making one `rng.choice` per move.
- `agents/baseline_agent.py`: port of `baseline.py`.
  - Its `candidates` and scoring are copied verbatim, including the missing en passant.
  - Castling rights come from the shared tracker, whose update rules are identical to baseline's.
  - `seed=None` means 1, matching baseline's CLI default.
- `agents/__init__.py`: `REGISTRY = {"random": ..., "baseline": ...}`.
- `protocol.py`: port of `uniform_random.main()` with `--agent` and `--seed`. stdout only ever carries `ready` and `move <uci>`. With no legal moves the bot exits, as the starters do.
- `run.sh`: runs `protocol.py --agent baseline`, and passes extra arguments through.

**Harness (`harness/`, never submitted)**
- `game.py`: `play_game()` mirrors `referee.run_match` step for step.
  - Order per ply: `outcome` → ply cap → observation to White, then Black → mover's `choose_move` → format and legality check → push → repetition count.
  - Frames come from the referee's own `make_frame`, with `clocks` replaced by `thinkSeconds`.
  - Agent failures map to the referee's reason text: exceptions and `NoLegalMoves` become "Bot exited", a bad move becomes "Illegal move: <uci>", and a bad move string becomes "Malformed move response".
  - The clock is simulated (180 s − think time + 2 s per move) and never forfeits.
- `match.py`: `run_match_pairs()` plays color-swapped pairs.
  - Each pair's seeds come from `random.Random(base_seed + i)`.
  - Games run on a `multiprocessing.Pool` with registry names as tasks; `imap` keeps results in task order.
  - Output is `GameSummary` rows written as JSONL, plus optional per-game replay files.
- `stats.py`: W/D/L and score from A's perspective, Wilson 95% CI (overall and per color), termination-reason histogram.
- `cli.py`: `python -m harness.cli A B --pairs N --seed S [--workers N] [--max-plies N] [--save-replays DIR] [--summary PATH]`.

**Tests (`tests/`)**
- `test_equivalence.py`: seeds 0–9 × (random vs random, random vs baseline). The subprocess referee with the starter scripts must equal `play_game` on result, reason, and every frame's board, white, black, and move.
- `test_leakage.py`: an AST import scan of `bot/` (only stdlib, `chess`, `referee`, and `bot.*`; no `harness`), plus a spy agent that checks every argument is a valid 64-character observation string or a float clock.
- `test_protocol.py`:
  - A transcript test that runs on any OS: the output is exactly `ready` plus one legal move.
  - `run_match` with the `run.sh`-equivalent argv for random and baseline, both colors: no `failedSide`.
- `test_determinism.py`: `run_match_pairs` with `workers=1`, `workers=4`, and `workers=1` again gives identical summaries, ignoring timing.
- `test_tracker.py`: `bot.tracker`'s source is identical to `uniform_random.py`'s.

**Other files:** `requirements-dev.txt` (pytest), `.gitignore`, `.gitattributes` (LF line endings for `*.sh`). `AGENTS.md` now documents the submission zip layout and the Windows/WSL test workflow.

### Results (verified)

- **Full suite on WSL Ubuntu (Python 3.12):** 20 passed, 30 subtests passed (our tests plus the 13 starter tests).
- **Native Windows (Python 3.11):** 5 passed, 2 skipped (the referee-based tests).
- **Mismatched-seed control:** off-by-one seeds make the harness and referee games differ, so the equivalence test can fail.
- **Broader equivalence sweep (one-off, not in the suite):** 600 games (150 seeds × 4 matchup orientations) gave 0 mismatches. One game included an en passant capture.
- **random vs baseline, 200 pairs, seed 0:**

  | | Score for random | 95% CI |
  |---|---|---|
  | Overall (W/D/L 23/0/377) | 0.058 | [0.039, 0.085] |
  | As White | 0.055 | |
  | As Black | 0.060 | |

  All 400 games ended by King capturable.
- **Throughput, random vs random:** about 965 games/s with 22 workers and about 106 games/s with 1 worker (Linux). Think time averages about 0.15 ms per move.

### Issues found and resolutions

1. **The referee is POSIX-only.** `referee.run_match` uses `select` on pipes, `os.killpg`, and `start_new_session`, so the equivalence and protocol tests can't run on native Windows.
   - *Resolution:* those tests skip on non-POSIX systems with an explicit reason. The full suite runs in WSL Ubuntu from a separate Linux venv (`~/.venvs/fow`). This is documented in `AGENTS.md`.
2. **The spec and AGENTS.md conflicted about the tracker test.** The spec says to point `test_uniform_random.py` at `bot.tracker`, but AGENTS.md forbids editing starter files.
   - *Resolution:* we left the starter test untouched and added `tests/test_tracker.py`, which asserts the copied tracker's source is identical to the starter's. The starter tests therefore cover our tracker's logic too.
3. **Zip layout vs package imports.** The original plan, "zip = `bot/` contents + `referee.py`", breaks `bot.*` imports.
   - *Resolution (agreed):* the zip keeps `bot/` as a folder, next to `referee.py` and a top-level `run.sh` that runs `python3 -u -m bot.protocol`.
   - When run as a script, `protocol.py` adds its parent directory to the import path, so `bot/run.sh` works from the repo.
   - Checked by building that layout in a temp folder and running a transcript through it. There's no build script for the zip yet.
4. **Line endings could break `run.sh`.** Git's `core.autocrlf=true` could convert `run.sh` to CRLF, which bash rejects.
   - *Resolution:* `.gitattributes` forces `*.sh` to LF.
5. **`run.sh` uses `python3` from `PATH`.** In tests that interpreter has no `chess` installed.
   - *Resolution:* tests launch the bot with `sys.executable` and the same arguments as `run.sh`.
6. **Scaffold file name mismatch.** The scaffold had an empty `bot/agents/baseline.py`, but the spec names the file `baseline_agent.py`.
   - *Resolution:* we followed the spec and removed the empty placeholder.
7. **Interface gaps in the spec.**
   - `play_game`'s signature has no time control. *Resolution:* it uses fixed 180 s + 2 s and simulated, unenforced clocks.
   - Summaries need think times and ply counts even when frames aren't recorded. *Resolution:* `play_game` also returns `plies`, per-side `thinkSeconds` lists, and, on failure, `failedSide` and an `error` traceback.
   - *Resolution:* we reuse the referee's `make_frame`, which isn't on AGENTS.md's import list but is a referee function.
8. **Coverage gap (open).** Every game seen so far, 620 across the suite and the sweep, ended by king capture within 124 plies, because neither starter guards its king. The equivalence test has never exercised threefold repetition, the 50-move rule, or the ply cap.
   - The harness uses the referee's own `outcome()` and repetition counting, so we expect these to match, but that is unverified. Revisit once the step 1 safety agent produces longer games.
