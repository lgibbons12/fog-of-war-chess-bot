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
- *Note (added in step 1):* these benchmark numbers used the original pair seeding, which step 1 found to be flawed (see step 1, issue 3). Rerunning them would give slightly different numbers. The equivalence results are unaffected.
- *Rerun with fixed seeding (step 2, Linux, seed 0):*
  - random vs baseline scored 0.065 [0.045, 0.094]: 0.090 as White, 0.040 as Black. All 400 games ended by King capturable.
  - random vs random scored 0.460 [0.412, 0.509].
  - Throughput was about 820 games/s with 22 workers and about 102 games/s with 1 worker.

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

## Step 1: Safety agent (2026-10-22)

Spec: `docs/step-1-safety.md`. Status: implemented and all tests pass, but **the gate fails**: `safety` does not beat `baseline`. Committed as `184f2cb` ("safety not working"). Not yet submitted to the arena.

### What we did

**Bot**
- `bot/safety.py`: the observation-only king-safety check.
  - `apply_move` builds the post-move squares from the observation, including castling (the rook moves too), en passant (the captured pawn disappears), and promotion.
  - `attackers_of` scans the knight squares and the 8 rays from a square. It returns visible enemy attackers as **known** and `?` squares as **possible** attackers.
  - `king_safety` runs `attackers_of` on our king's square and returns a `SafetyReport(known_loss, exposed, king_square)`.
- `bot/agents/safety_agent.py`: `SafetyAgent` picks the move with the smallest key `(known_loss, exposure, -material, rng.random())`.
  - Exposure is the number of exposed `?` squares (`"count"` mode, registry name `safety`), or just exposed vs not exposed (`"binary"` mode, `safety_binary`).
  - Material is +10 × captured value, +5 × promotion value, and −10 × the moved piece's value if a visible enemy attacks its new square.
  - After each move it stores a `last_decision` record.
- `bot/protocol.py`: fallback guard. If the agent raises an exception while choosing, the traceback goes to stderr and a random legal move is played instead.
- `bot/run.sh` now defaults to `safety`.

**Harness**
- `play_game` has a `strict` mode, on by default: agent bugs raise instead of being scored as losses.
- Replays now include agent names and a per-frame `decision` record.
- `harness/breakdown.py` reads saved replays and reports loss categories (a)/(b)/(c), draw reasons, and move-time statistics.
- The CLI now prints mean plies.

**Packaging**
- `scripts/package.sh` builds `dist/bot.zip`: `bot/`, `referee.py`, and a root `run.sh` that runs `python3 -u -m bot.protocol --agent safety`.
- `scripts/check_package.sh` unzips it to a temp folder and plays the real referee against `baseline.py` in each color.

**Tests**
- `tests/test_safety.py`: unit tests for `apply_move` (quiet, capture, 4 promotions, both castles for both colors, en passant for both colors) and `attackers_of` (every piece type attacking and blocked, pawn direction, `?` cases).
- `tests/test_soundness.py`: 200 games of `safety` against `random` and `baseline`, in both colors. At every decision it checks every legal move against the true board: a "known loss" really loses, and a move reported "safe" (no known attacker, no exposure) really is safe.
- The fallback guard test and `safety` were added to the protocol and determinism tests.

### Results (verified, Linux, 200 pairs, seed 0)

- **Tests:** 34 passed, 255 subtests (Linux). On Windows, 19 passed and 2 skipped (the referee tests).
  - The soundness test checks more than 50,000 moves. Breaking knight detection on purpose makes it fail, so it can catch real bugs.
- **Zip check:** both referee games against `baseline.py` completed, the bot won as White and as Black, and there were no protocol failures.

| Matchup | Score [95% CI] | As White | As Black | Mean plies |
|---|---|---|---|---|
| safety vs baseline (**gate**) | **0.474 [0.425, 0.523]: fails** | 0.458 | 0.490 | 49.5 |
| safety vs random | 0.998 [0.986, 1.000] | 0.995 | 1.000 | 22.7 |
| safety_binary vs baseline | 0.565 [0.516, 0.613] | 0.540 | 0.590 | 40.4 |
| safety vs safety_binary | 0.374 [0.328, 0.422] | 0.393 | 0.355 | 51.8 |

- **Loss breakdown (safety vs baseline):** all 210 losses are type (b). Every non-losing move was exposed, and the hidden attacker was real (rook 76, queen 54, bishop 53, knight 21, pawn 7). There were 0 type (a) and 0 type (c) losses.
- **Draws:** almost none. There were 1–7 threefold repetitions per matchup, and no 50-move or ply-cap draws.
- **Move time:** median 0.30 ms, max 12 ms, against a 2 s increment.
- **Seed check:**
  - `safety` vs baseline: 0.474, 0.445, 0.401 for seeds 0, 1, 2.
  - `safety_binary` vs baseline: 0.565, 0.552, 0.507. It passes the gate on seeds 0 and 1 but fails on seed 2, so it is borderline.

### Why `safety` loses

The safety check can't see hidden pieces, so it treats every unseen square on a line to our king as a possible attacker, and almost every midgame move counts as exposed. Count mode ranks exposure count above material, so material only breaks exact ties: the agent spends its moves shrinking a number that rarely reaches zero and almost never captures. Meanwhile baseline grabs material every turn until a hidden rook or queen reaches our king. Binary mode does better because once every move is exposed, material decides.

### Exploratory result (not in the repo)

A variant ranking moves by `(known_loss, exposed or not, -material, exposure count, rng)` scored 0.645, 0.629 and 0.634 against baseline over seeds 0–2, with a lowest lower bound of 0.580. It also beat `safety_binary` 0.608. This is the leading candidate for the first submission, but adopting it changes the spec, so it is waiting on a team decision.

### Issues found and resolutions

1. **The gate fails (resolved in step 2, Part A).** The spec's default agent, `safety` in count mode, does not beat baseline. See "Why `safety` loses" above. Step 2 adopted `safety_v2` (material before exposure count) as the arena agent.
   - *Options:* adopt the exploratory variant as the submission (recommended); ship `safety_binary`, which is borderline; or wait for step 2's possibility tracker to make exposure less coarse.
   - Until this is decided, `scripts/package.sh` still packages `safety`.
2. **The loss breakdown says little at this stage.** With exposure this coarse, every loss is type (b), so the (a)/(b)/(c) split will only become informative once step 2 tightens exposure.
3. **Step 0 seeding bug (fixed).** Pair seeds came from `Random(base_seed + i)`, which is what the step 0 spec literally says.
   - That meant pair *i* of `--seed s` was identical to pair *i+1* of `--seed s+1`, so runs with nearby seeds shared 199 of 200 pairs. It showed up as identical W/D/L when checking seed noise.
   - *Resolution:* `harness/match.py` now seeds each pair from `"{base_seed}:{i}"`, which is deterministic and doesn't overlap between seeds. All step 1 numbers above use the fixed seeding.
4. **Spec details we had to resolve.**
   - **Trade check after a promotion:** it uses the promoted piece's value, since that is what would be lost. The king counts as 0, because walking into a known attack is already a known loss.
   - **Decision record:** it also stores `min_safe_exposure`, the smallest exposure among non-losing moves. The (a)/(b)/(c) breakdown needs it, because a move that's a known loss can still have zero exposure.
5. **Strict mode vs the referee.** `strict=True` (the default) makes agent bugs raise, but the referee would record a crashing bot as a "Bot exited" loss.
   - *Resolution:* the equivalence test runs with `strict=False` so it still mirrors the referee.
6. **The package check found the system Python.** The first version used `realpath`, which followed the venv's symlink out to the system Python, which has no `chess`.
   - *Resolution:* the script now makes the path absolute without resolving symlinks.
7. **Soundness test design.** It rebuilds each game's tracker state from the replay instead of adding a test-only hook to the harness. It checks every legal move, not just the chosen one, and also checks that count mode never picks an exposed move when a safe one exists.

## Step 2: Ship the Step 1 result and build the possibility tracker (2026-10-22)

Spec: `docs/step-2-possibility.md`. Status:
- **Part A is done.** The arena agent is `safety_v2`, packaged and checked, and waiting for upload.
- **Parts B and C are done**, and all tests pass.
- **The Part C gate fails:** `tracked_v2` does not beat `safety_v2`, so the arena agent stays `safety_v2`.

Not yet committed.

### What we did

**Part A: shipping the Step 1 result**
- **Commits:** Step 1 was already committed as one commit (`184f2cb`) and pushed. We did not split it into logical commits, because that would rewrite published history.
- **Seeding:** pair seeds come from `random.Random(f"{base_seed}:{i}")`. The determinism test compares `workers=1` with `workers=4` and now covers a tracked agent too.
- **New agents:** `safety_v2` (known loss, then material, then exposure count) and `safe_material` (known loss, then material only, as a control).
  - All safety variants are now `functools.partial` entries over one `SafetyAgent` class with a configurable sort key, not separate classes.
- **Packaging:** `scripts/package.sh [agent]` takes the agent name, defaulting to `safety_v2`. `bot/run.sh` defaults to `safety_v2`. `AGENTS.md` now records the current step and the arena agent.

**Part B: the possibility tracker (`bot/possibility.py`)**
- **What it tracks:** one hypothesis per enemy piece, as a (set of possible types, bitboard of possible squares) pair. Hypotheses always correspond one-to-one with the real enemy pieces.
- **Updates by ply:**
  - *Our ply:* remove whatever we captured. If several hypotheses could be the captured piece, they merge into one fewer.
  - *Their quiet ply:* every hypothesis expands independently by one move, around pieces we know are there. That includes pawn pushes, promotion, and castling, where the king and rook hypotheses update together.
  - *Their capture ply:* only hypotheses that could have captured the lost square expand, including en passant.
- **Filter:** squares we see as empty or ours are removed, and each visible enemy piece is matched to the hypotheses that could be it, repeated until nothing changes.
- **Inconsistency:** `strict=True` (harness and tests) raises `TrackerInconsistency`. `strict=False` (arena) logs to stderr and resets to a coarse but sound state. `Agent` now takes a `strict` flag, which the harness sets.
- **Base `Agent` changes:** it counts observations as plies and asserts that `choose_move` is only called on our plies. A new `record()` is also used by the protocol fallback.

**Part C: tracker-based safety**
- `attackers_of(cells, sq, side, tracker=None)`: with a tracker, a `?` counts as exposed only if a type possible there can attack along that line. Rays pass through harmless `?` squares unless they are certainly occupied.
- **New agents:** `tracked_v2`, `tracked_count`, and `tracked_binary`, the three orderings with tracker exposure.
- **Decision records** now carry the possible types on each exposed square, tracker resets, tracker precision, and update times.
- **Harness:** `harness.cli --seed` takes several seeds and prints per-seed and pooled scores. `harness.breakdown` reads replay folders recursively and reports safe-move availability, the false-alarm rate by type, tracker precision by ply, and update times.

**Tests**
- `tests/test_possibility.py`:
  - 8 scripted scenarios: knight tour, queen behind a pawn, enemy capture, enemy en passant, enemy castling both ways, promotion, our ambiguous capture, bishop color.
  - The soundness property test: 204 games of `tracked_v2` against random, baseline and `safety_v2`, in both colors. At every observation it checks for a bipartite matching and that `certainly_occupied` ⊆ truth. At every decision it checks tracked safety soundness for every legal move.
  - The reduction test: a coarse tracker gives identical `SafetyReport`s to Step 1 over 20 games.
- `tests/test_safety.py`: tracker-mode ray rules.
- `tests/test_leakage.py`: the tracker imports only stdlib, `chess` and `referee`.
- The protocol transcript test now uses a realistic one-observation transcript, and covers `tracked_v2`.

### Results (verified, Linux, 200 pairs × seeds 0–2 unless noted)

- **Tests:** 47 passed, 463 subtests (Linux). On Windows, 32 passed and 2 skipped (the referee tests).
  - The soundness test checked 9,190 observations and more than 50,000 (decision, move) safety pairs, with zero inconsistencies and zero resets.
- **Zip:** `dist/bot.zip` (agent `safety_v2`, 13 files) passed `check_package.sh`, winning as White and as Black against `baseline.py` with no protocol failures.

**Part A batch**

| Matchup | Seeds 0 / 1 / 2 | Pooled [95% CI] | Draws |
|---|---|---|---|
| safety_v2 vs baseline | 0.682 / 0.640 / 0.703 | **0.675 [0.648, 0.701]** | 18 threefold |
| safe_material vs baseline | 0.512 / 0.465 / 0.500 | 0.492 [0.464, 0.521] | 0 |
| safety_v2 vs safe_material | 0.660 / 0.660 / 0.656 | **0.659 [0.631, 0.685]** | 23 threefold |

`safety_v2` beats `safe_material` with a lower bound above 0.5, so it is the submitted agent. Without the exposure tie-break (`safe_material`), the agent is no better than baseline.

**Part C experiments**

| Matchup | Seeds 0 / 1 / 2 | Pooled [95% CI] | Mean plies | Draws |
|---|---|---|---|---|
| tracked_v2 vs safety_v2 (**gate**) | 0.525 / 0.468 / 0.545 | **0.512 [0.484, 0.541]: fails** | 58.4 | 102 threefold |
| tracked_count vs tracked_v2 | 0.370 / 0.344 / 0.396 | 0.370 [0.343, 0.398] | 60.5 | 34 threefold |
| tracked_binary vs tracked_v2 | 0.394 / 0.343 / 0.405 | 0.380 [0.353, 0.408] | 55.7 | 25 threefold |
| tracked_v2 vs baseline | (pooled) | 0.668 [0.641, 0.694] | 48.0 | 16 threefold, 1 fifty-move |
| tracked_v2 vs random | (pooled) | 0.987 [0.978, 0.992] | 21.7 | 0 |

- **Best tracked agent:** `tracked_v2`. Putting exposure first still loses, even with the tracker.
- **Loss breakdowns** (a / b / c):

  | Matchup | a | b | c |
  |---|---|---|---|
  | tracked_v2 vs safety_v2 | 46 | 488 | 0 |
  | tracked_count vs tracked_v2 | 0 | 738 | 1 |
  | tracked_binary vs tracked_v2 | 0 | 731 | 0 |
  | tracked_v2 vs baseline | 34 | 356 | 0 |
  | tracked_v2 vs random | 15 | 1 | 0 |

  Type (a) losses are possible for material-first agents by design: they will take an exposed capture over a safe quiet move.
- **Hidden attackers in (b) losses:**
  - Step 1 `safety` vs baseline: R 76, Q 54, B 53, N 21, P 7.
  - `safety_v2` vs baseline: R 136, Q 117, B 76, N 36, P 10, K 2 (1,200 games).
  - `tracked_v2` vs baseline: R 123, Q 116, B 63, N 36, P 14, K 9.

  The losses are still dominated by sliders.

**Metrics: coarse (Step 1) vs tracker** (each agent against baseline)

| Metric | safety_v2 (coarse) | tracked_v2 (tracker) |
|---|---|---|
| Safe-move availability | 0.417 | 0.660 |
| Flagged squares per decision | 1.63 | 0.93 |
| False-alarm rate | 0.996 | 0.991 (by type: P .994, N .994, B .993, R .992, Q .990, K .994) |
| Tracker update | n/a | median 0.054 ms, max 12.2 ms (budget 20 / 200 ms) |
| choose_move | median 0.36 ms, max 11.8 ms | median 0.52 ms, max 13.0 ms |

**Tracker precision by ply** (`tracked_v2` vs `safety_v2`, mean support per hypothesis / fraction of `?` squares where a queen is possible):

| Plies | 0–19 | 20–39 | 40–59 | 60–79 | 80–99 | 100–119 |
|---|---|---|---|---|---|---|
| Mean support | 8.9 | 12.5 | 17.6 | 29.5 | 37.8 | 41.1 |
| Q possible | 0.51 | 0.29 | 0.23 | 0.42 | 0.45 | 0.35 |

### Why the tracker didn't pass the gate

The tracker makes exposure much more informative. A move with zero exposure is available at 66% of decisions instead of 42%, and about half as many squares are flagged. But about 99% of flagged squares still hold no real attacker. In both orderings that win, material comes before exposure, so exposure only breaks ties between moves with equal material. Sharper exposure therefore changes few decisions. It mostly shows up as longer games: 102 threefold draws against `safety_v2`, compared with 18 for `safety_v2` against baseline.

Hypothesis supports also grow steadily with the ply count (8.9 → 41 squares), because each hypothesis expands independently every enemy ply. That is the limitation the spec expects Step 3's particles to address.

### Issues found and resolutions

1. **Spec conflict over rays through `?` squares (resolved).** Part C says rays continue through `?` squares unless certainly occupied, but test 4 requires a coarse tracker to give *identical* reports to Step 1, which stops at the first `?`. Both can't hold.
   - *Resolution:* rays continue only through `?` squares where **no possible type can attack** (the "only a pawn could be there" case the spec motivates). They stop at a flagged or certainly occupied `?`. This stays sound, and the reduction test holds exactly.
2. **Soundness bug found by the property test (fixed).** Continuing through a harmless `?` let a *visible* enemy rook further along be reported as a **known** attacker, but the `?` might hold a blocking piece. The test caught a move flagged as a known loss that was actually safe.
   - *Resolution:* a visible attacker counts as known only along an all-`-` line. Behind a `?` it is reported as possible, and its square appears in `exposed` (the decision record lists it with its visible type). A regression unit test was added.
3. **Precision refinement beyond the spec.** In quiet-ply expansion, squares occupied before the move are excluded from every piece's reach, not just used to stop slides, because a quiet move can't land on an occupied square. This is sound and more precise.
4. **Wording in the `our_last_move` spec.** The tracker treats `our_last_move` as our most recent move. At an opponent-ply update that is the move from two plies earlier, which is exactly what the en passant check needs.
5. **First observation.** The first observation of any tracker is filter-only. This generalizes the spec's `p == 0` so that FEN-based tests can start mid-game.
6. **Ply assertion vs an old test.** The new `choose_move` ply assertion broke the Step 0 transcript test, which sent White two observations before its first move. That can't happen in a real game, so the test now uses one.
7. **`BaselineAgent` and `strict`.** Its overridden `__init__` didn't accept `strict`. Fixed.
8. **Test threshold.** The soundness test's minimum-coverage guess (10,000 observations) was too high, since 204 games produce about 9,200. Lowered to 8,000. Every soundness check itself passed.
9. **Gate failure (open).** `tracked_v2` does not beat `safety_v2`, so the arena agent stays `safety_v2`. See "Why the tracker didn't pass the gate".
   - *Next-step candidates:* use exposure as a hard filter rather than a tie-break (for example, prefer unexposed moves unless the material gain is large), or move on to Step 3 particles to rank the remaining risk by probability.

## Step 3: Particle tracker, Part A (2026-11-17)

Spec: `docs/step-3-particles.md` (still a **draft**; Part A was started at Liam's request before the remaining open questions were settled). Status: Part A implemented, and all tests pass. Committed as `7e91cb2`, `2bb9fe0` and `717a2f2`; Part B follows below.

### What we did

**Bot**
- `bot/particles.py`: `Particle`, `OpponentModel` with `UniformModel` and `CaptureModel`, `ParticleTracker`, and `particle_key`.
  - **Consistency is decided only by the referee.** A board survives iff `observation(board, side) == obs` and `outcome(board, Counter()) is None`.
  - **Opponent plies enumerate every child.** Cheap necessary checks run first (capture on the lost square or no capture at all; the destination shows `?` or the moved piece), then the referee's `observation()` decides.
  - **Duplicates are merged** by `(board_fen, turn, castling rights, ep square, halfmove clock)`, after both our plies and theirs.
  - **Resampling is systematic,** and only happens when there are more than `n` distinct boards (ADR 0015).
  - **Depletion recovery:** rejection-sample boards from the possibility tracker's supports, with at most `20·n` attempts. If that fails, `available = False`.
  - `loss_probability(move)` is the weighted fraction of particles where `outcome()` reports "King capturable" after our move.
- `AGENTS.md`: the current step is now Step 3.

**Tests:** `tests/test_particles.py`.
- **Scripted units:**
  - the start position is exact for both sides;
  - Black's view after each of White's 20 first moves, under both models;
  - our capture;
  - an enemy capture on a known square;
  - enemy en passant;
  - a particle where our king becomes capturable is dropped;
  - depletion regenerates from the possibility tracker, including the truth;
  - depletion without a possibility tracker leaves particles unavailable;
  - resampling is deterministic, uses one RNG call, and keeps any board weighing at least 1/n.
- **Consistency over replayed harness games** (spec tests 1–4): 24 `tracked_v2` games against random, baseline and `safety_v2`, in both colors, at `n = 32`. Checks:
  - every particle matches the observation and passes `outcome()`;
  - particle keys are distinct, and weights sum to 1;
  - every particle's move set equals `ObservationTracker.legal_moves()`;
  - every particle fits within the possibility tracker's supports (bipartite matching), except at a regeneration observation;
  - known loss ⇒ `p_loss = 1`, and no known loss with nothing exposed ⇒ `p_loss = 0`.
- **Exactness (not in the spec):** with resampling disabled, the true board is among the particles at every observation, over 8 games and their first 16 plies.

### Results (verified)

- **Tests:**
  - **Linux (WSL Ubuntu):** 58 passed, 537 subtests.
  - **Windows:** 43 passed, 2 skipped (the referee tests).
  - **Consistency test:** 891 observations, 16,559 particle-observations and 9,805 `p_loss` checks against the possibility layer, with zero violations. There were 79 depletions, 79 regenerations and 0 regeneration failures.
  - **Exactness test:** 95 truth checks.
- **`n = 128` smoke run** (7 replayed games, Windows dev machine, Python 3.11; per observation, including `p_loss` for every legal move on our decisions):

  | Game (ours in bold) | Plies | Truth among particles | Depletions | Median / max time |
  |---|---|---|---|---|
  | **tracked_v2** vs baseline, seed 0 | 36 | 30/36 | 0 | 16 / 786 ms |
  | baseline vs **tracked_v2**, seed 0 | 72 | 3/72 | 5 | 27 / 875 ms |
  | **tracked_v2** vs baseline, seed 1 | 44 | 44/44 | 0 | 11 / 600 ms |
  | baseline vs **tracked_v2**, seed 1 | 23 | 5/23 | 2 | 18 / 583 ms |
  | **tracked_v2** vs baseline, seed 2 | 24 | 4/24 | 3 | 46 / 853 ms |
  | baseline vs **tracked_v2**, seed 2 | 55 | 37/55 | 1 | 7 / 383 ms |
  | **tracked_v2** vs random, seed 0 | 30 | 12/30 | 2 | 48 / 883 ms |

  Overall, the truth was among the particles at 135/284 observations (48%), with 13 depletions in 7 games. Timing fits the budget (0.4 s median, 1.5 s max per move), but this is not the formal timing run.

### Issues found and resolutions

1. **Duplicate particles after our move (fixed).** Boards that differ only in their halfmove clock become identical when our pawn move or capture resets it. The consistency test caught this. *Resolution:* the filter merges duplicates.
2. **Resampling trigger (deviation, ADR 0015).** The spec's ESS < n/2 trigger fires on almost every small merged set and only throws away boards. Resampling now happens only when there are more than `n` distinct boards.
3. **Interface changes from the spec.**
   - `on_observation` takes `our_rights` (our castling rights from `ObservationTracker`), which regeneration needs to build boards whose observation matches.
   - It doesn't take `prev_obs`; the tracker keeps its own.
   - The constructor takes an optional `start` board, so tests can start from a FEN.
4. **Test scope (temporary).** Spec tests 1–4 call for 200 games of `particle_ev300`. That agent is Part B, so for now the test replays 24 `tracked_v2` games at `n = 32`, to keep the suite at about 2 minutes. It switches to particle-agent games in Part B.
5. **The tracker often loses the true board (open, needs a team decision).**
   - The exact set of consistent boards swings widely: from 1 board to 138,200 and back to 272 within a few plies (baseline vs `tracked_v2`, seed 0).
   - When it exceeds `n`, resampling usually drops the truth. A later observation then rules out everything we kept, and the tracker regenerates from possibility supports, which carry no history.
   - Hence 48% truth coverage at `n = 128`, and the worst game (3/72) had the bot playing Black against baseline's greedy captures.
   - *Options:*
     - (a) Accept it, and let the calibration metric in Part C show whether `p_loss` is still useful.
     - (b) Raise `n` as far as the timing run allows.
     - (c) Better recovery: on depletion, re-expand from the last non-empty set and keep more children, instead of regenerating from supports.
     - (d) Weight the resampling toward diversity, e.g. keep boards that differ on squares near our king.
   - Each option except (a) is a spec change, so this waits for review.

### Decision matrix (2026-11-17 to 18)

At Liam's request, every open Part A choice was run as a full matrix. Results, commands and raw data are in `docs/results/2026-11-17-step3-tracker-matrix/`; the recommendation is ADR 0016 (Proposed).

- **New tracker options** (experiment knobs; the defaults are unchanged):
  - `trigger` = `above_n` | `ess`;
  - `recovery` = `supports` | `reexpand` (option c above);
  - `diversity` (option d above).

  `tests/test_particles.py` checks invariants for each option.
- **New harness tools:** `harness/particle_matrix.py` runs the matrix and the timing run, and `harness/matrix_report.py` and `harness/matrix_compare.py` produce the tables and paired bootstrap intervals.
- **Headline results** (verified; 60 replayed games, 27,509 scored moves):
  - **Particles beat the possibility tracker as a risk predictor:** Brier ×100 0.60–0.72 vs 1.84.
  - **More particles keep the truth more often:** n = 256 vs 128 adds +0.108 truth coverage [+0.051, +0.168].
  - **The timing run picks n = 256.** Its single-worker max is 0.97–1.30 s per move; n = 512 breaks the 1.5 s max. (Superseded in Part B: the real agent's timing forces n = 64, ADR 0018.)
  - **Re-expansion helps truth coverage:** +0.043 [+0.014, +0.082].
  - **No significant effect:** the `capture` model, the `ess` trigger and diversity resampling.
- **Tests:** Linux 59 passed, 557 subtests.

## Step 3: Particle agents, Part B and experiments (2026-11-22 to 27)

Spec: `docs/step-3-particles.md`, approved by Liam on 2026-11-22, along with ADRs 0014–0016. Status: done. The gate passes, and `particle_ev100` is the proposed arena agent (ADR 0019).

### What we did

- **Agents:** `bot/agents/particle_agent.py` is `ParticleAgent`, a `SafetyAgent` with a particle-estimated `p_loss`. It is registered as:
  - `particle_v2`, with `p_loss` as a tie-break after material;
  - `particle_ev{30,100,300,1000}`, with key `-(material - λ·p_loss)`;
  - for every λ, the ablation variants `_n{32,128,256}` and `_capture`.

  Each decision records `particle_mode`:
  - `particles`: normal operation;
  - `unavailable`: depleted, so `p_loss` = exposure > 0;
  - `time_guard`: under 20 s on the clock, so rank as `safety_v2` and drop the particles;
  - `error`: non-strict fallback, the same as `time_guard`.

  See ADR 0017.
- **Harness tools:**
  - `harness/particle_metrics.py` rebuilds a deterministic agent from its replay, asserting identical moves, and scores its particles against the truth. Tests use the same rebuild.
  - `harness/particle_timing.py` summarizes per-move times.
  - `harness/paired_compare.py` is a paired bootstrap by (seed, pair).
  - `harness/step3_queue.py` runs the experiment queue and writes a self-refreshing progress page.
- **Tests:**
  - `tests/test_particle_agent.py`: keys, one RNG call per move, and every fallback mode.
  - Spec tests 1–4 now check a rebuilt `particle_ev300_n32` agent's own tracker: 48 games by default, 200 with `FOW_PARTICLE_GAMES=200`.
  - The determinism test now covers `particle_ev300` and asserts that no `time_guard` or `error` decisions occur.
  - The protocol transcript and referee tests include a particle agent.

### Results (verified)

- **Full spec Test 1** (204 games, Windows):
  - 166,510 particle-observations and 100,879 `p_loss` cross-checks, with zero violations;
  - 548 depletions and 9 failed regenerations; 5 decisions ran in `unavailable` mode.
- **Timing** (`docs/results/2026-11-22-step3-timing/`): the real agent is much slower in the worst case than the Part A replays suggested. Max per move is 5.3 s at n = 256 and 1.46 s at n = 64. Liam chose n = 64 (ADR 0018).
- **Gate** (`docs/results/2026-11-22-step3-gate/`): every particle agent beats `safety_v2`. `particle_ev100` scored **0.617 [0.589, 0.644]**. λ = 30 and 300 tie with it, while λ = 1000 and `particle_v2` are significantly worse.
- **Ablations and metrics** (`docs/results/2026-11-27-step3-ablations/`):
  - n = 256 is +0.030 [+0.008, +0.052], but over budget.
  - The `capture` model's +0.022 against `safety_v2` failed its head-to-head confirmation: 0.484 [0.456, 0.512].
  - vs baseline 0.762, vs random 0.998.
  - Calibration is within about 1.5× in the middle buckets, and `p_loss = 0` still lost 0.33% of the time.
  - Truth coverage was 0.325, and per-square log loss was 0.440 for particles vs 0.578 for the possibility baseline.

### Issues found and resolutions

1. **The timing budget broke at n = 256** (ADR 0016's choice). The particle agent's own games trigger expensive depletion recoveries and full-set expansions. *Resolution:* n = 64, by the spec's rule (ADR 0018). Speeding up the tracker is the clearest follow-up.
2. **The spec words the time guard two ways.** *Resolution:* below 20 s, rank as `safety_v2` and drop the particles for the rest of the game (ADR 0017, Proposed).
3. **The laptop slept for about 12 hours during the `particle_ev1000` run.** Wall-clock think time drained the simulated clocks, and the time guard fired in 29 games. *Resolution:* reran the experiment; the first run is kept as `*_slept`. The queue now checks every run for `time_guard` decisions. Harness clocks still use wall time, so long runs must keep the machine awake.
4. **Deviations from the spec:**
   - Test 1 runs 48 games by default instead of 200 (the 200-game run was done once; see above).
   - The n ablation used {32, 128, 256} instead of {32, 128, 512}, because the default is now 64 and 512 is far over budget.
   - The "surviving candidates per particle" timing statistic was not recorded.

### Final checks (verified, 2026-11-27)

- **Full suite on Linux (WSL Ubuntu):** 69 passed, 601 subtests (`pytest tests test_uniform_random.py`). On Windows: 54 passed, 2 skipped (the referee tests).
- **Package:** `scripts/package.sh particle_ev100` builds `dist/bot.zip` (15 files). `scripts/check_package.sh` passed in WSL with no protocol failures. Its two games:
  - **As Black: a win.**
  - **As White: a loss in 7 plies.** That was surprising, since 0 of 1,200 harness games against baseline ended in a loss within 10 plies. It did not recur:
    - 6 seeded games through `bot/protocol.py` were all won;
    - 20 more games through the unzipped `run.sh` (unseeded, as in the arena) went 14 W / 2 D / 4 L, and no loss came before ply 83.

    The check deletes its replays, so the 7-ply game can't be inspected. Treated as a rare genuine early attack (**unverified**).
- **Arena-style timing:** in those 20 referee games, the referee-charged time per move was median 0.026 s and max 0.283 s, with 0 moves over 1.5 s across 614 moves. The referee buffers observations and starts the clock before sending them (`referee.py` `_move`), so this covers both particle updates plus the decision. Bot stderr showed depletions but no `particles off` lines and no tracebacks.
