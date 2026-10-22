# AGENTS.md — Fog of War Chess Bot (MIT 6.7980, Fall 2026)

Context for coding agents working in this repo. Read this file in full before changing anything.

## What this project is

- We are building a bot for the MIT 6.7980 Fog of War Chess Challenge, a course project. Our team is AJ Sachwitz, Liam Gibbons, and JJ Detweiler.
- Work proceeds in **numbered steps**. Each step has a spec in `docs/specs/`.
- **Implement only the current step's spec.** Don't add strategy, optimizations, or features from later steps.
- A human reviews every step before the next one starts.

## Planned architecture (for orientation only; do not build ahead)

0. Agent interface and in-process harness. **Current step:** `docs/specs/step0-harness.md`.
1. Safety agent: greedy captures plus possibility-based king safety.
2. Possibility tracker: per-enemy-piece, history-consistent reachable squares.
3. Particle tracker: weighted full boards, filtered with the referee's `observation()`.
4. Stockfish integration and throughput benchmarks.
5. Decision experiments.

Design principle: **possibility (worst case) decides king safety; probability (particles) ranks moves among the safe ones.**

## Game rules that matter for code (verified from `referee.py` and the official Rules page)

- **Observation.** A 64-character string in a1, b1, …, h8 order. Uppercase is White, lowercase is Black, `-` is a visible empty square, `?` is hidden.
  - We see our own pieces plus every destination of our pseudo-legal moves.
  - The opponent's move is never announced.
- **Observations arrive before every ply, to both players.** That includes right after our own move. `observe()` must tolerate several calls between moves.
- **No check or checkmate.** A move that leaves the mover's king capturable loses immediately. Castling through or into attack is legal. Having no legal moves is a loss. There is no stalemate draw and no insufficient-material draw.
- **Draws.** Threefold repetition, the 50-move rule, and the 1,000-ply arena cap. The local referee's default cap is 10,000; our harness uses 1,000.
- **Castling rights and en passant are not in observations.** The bot tracks them itself. `uniform_random.ObservationTracker` already does this correctly.
- **Protocol.**
  - Input: `fow`, then `w|b <base> <inc>`.
  - Reply `ready` within 15 s.
  - Observation lines and clock lines arrive; reply to a clock line with `move <uci>`.
  - **Any other stdout line forfeits the game.** Diagnostics go to stderr only.
- **Resources.** 180 s + 2 s per move, on 2 cores and 4 GiB. The whole process tree is paused off-turn. Nothing persists between games.

## Hard invariants (violations are blocking bugs)

1. **No information leakage.**
   - Code under `bot/` receives only observation strings and clock floats.
   - It must never import `harness/` or read true boards.
   - `bot/` may import the referee's *rule functions* (`FowBoard`, `fow_moves`, `observation`), because later steps apply them to hypothetical boards.
2. **Reuse the referee; don't reimplement rules.**
   - Import `FowBoard`, `fow_moves`, `observation`, `outcome`, and `position_key` from `referee.py`.
   - If behavior seems to need a rule reimplementation, stop and ask.
3. **Don't modify the starter files at the repo root:** `referee.py`, `baseline.py`, `uniform_random.py`, `test_uniform_random.py`, and everything in `starters/`. They are the reference implementation.
4. **Determinism.**
   - All randomness comes from `random.Random(seed)` instances that are passed in explicitly.
   - Never use the global `random` module, time-based seeds, or set/dict iteration order that affects choices.
   - Ports of the starter bots must make exactly the same RNG calls in the same order.
5. **The harness is faithful to the referee.**
   - The in-process harness must follow `referee.run_match`'s loop order exactly.
   - The equivalence test (harness vs subprocess referee, frame by frame) must always pass.
6. **Submission compatibility.**
   - Everything under `bot/`, plus `referee.py`, must run with only the standard library and `chess==1.11.2`.
   - Don't add runtime dependencies without asking.
   - Dev-only tools such as pytest go in `requirements-dev.txt`.

## Repo layout

```
referee.py, baseline.py, uniform_random.py   # starter reference code (do not edit)
starters/                                    # starter kit (do not edit)
bot/          # submitted code (see "Submission zip layout" below)
harness/      # local experiments only, never submitted
tests/        # our tests
docs/specs/   # step specs (source of truth for what to build)
replays/      # generated output, gitignored
```

### Submission zip layout

Code under `bot/` imports itself as `bot.*`, so the zip keeps `bot/` as a folder:

```
run.sh        # top-level entry: cd "$(dirname "$0")" && exec python3 -u -m bot.protocol --agent <name>
referee.py    # copied from the repo root
bot/          # the bot/ package as-is (bot/run.sh is for running from inside the repo)
```

## Commands

`referee.run_match` is POSIX-only: it uses `select` on pipes, `os.killpg`, and process groups. Tests that start the subprocess referee skip on Windows: `tests/test_equivalence.py`, the referee half of `tests/test_protocol.py`, and two starter tests in `test_uniform_random.py`. A step is done only when the full suite passes on Linux or macOS.

### Linux / macOS

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests test_uniform_random.py     # full suite: ours + starter tests
.venv/bin/python -m harness.cli random baseline --pairs 200 --seed 0
```

Running the official referee locally:

```sh
.venv/bin/python referee.py --trusted-local --white '<cmd>' --black '<cmd>' --max-plies 1000 --output replays/x.json
```

### Windows (WSL for the full suite)

The repo's `.venv` on Windows is a uv-managed Windows venv (`.venv/Scripts/`). It is fine for the harness and non-referee tests:

```sh
uv pip install -r requirements.txt -r requirements-dev.txt --python .venv/Scripts/python.exe
.venv/Scripts/python.exe -m pytest tests          # referee-based tests skip here
.venv/Scripts/python.exe -m harness.cli random baseline --pairs 200 --seed 0
```

Run the full suite inside WSL (Ubuntu), using a separate Linux venv kept outside the repo so it doesn't clash with the Windows `.venv`:

```sh
# one-time setup, inside WSL
python3 -m venv ~/.venvs/fow
~/.venvs/fow/bin/pip install -r requirements.txt -r requirements-dev.txt

# from the repo checkout under /mnt/c/...
~/.venvs/fow/bin/python -m pytest tests test_uniform_random.py
```

From a Windows shell, the same suite runs as a one-liner:

```sh
wsl.exe -d Ubuntu -- bash -lc 'cd "<repo path under /mnt/c>" && ~/.venvs/fow/bin/python -m pytest tests test_uniform_random.py -p no:cacheprovider'
```

`bot/run.sh` and the zip's `run.sh` call `python3` from `PATH`, which has no `chess` unless a venv is active. Tests therefore launch the bot with `sys.executable` (see `tests/test_protocol.py`) rather than via `run.sh`.

## Conventions

- **Python ≥ 3.10**, type hints on public functions, `from __future__ import annotations`.
- Prefer explicit, boring code over clever abstractions. Small pure functions, no metaprogramming.
- Tests use `unittest.TestCase`-compatible style so both pytest and unittest can run them.
- Every non-trivial function gets a docstring stating its invariants.
- Don't commit replays, virtualenvs, or large generated files.

## How to work

- **The spec is the source of truth.** If it is ambiguous, contradicts the code, or seems wrong, **stop and ask**. Don't guess. List the ambiguity and your proposed resolution.
- Don't present untested code as working. Run the tests and include the output.
- When reporting results, distinguish:
  - **verified**: you ran it;
  - **assumed**: you inferred it from reading code;
  - **unverified**: a hypothesis.
- At the end of a step, report:
  1. Files changed.
  2. Test output.
  3. The "Report back" items listed in the spec.
  4. Any deviations from the spec, and why.
  5. Open questions.
- Ask before any destructive change: deleting files, rewriting history, or editing starter files.