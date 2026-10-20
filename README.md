# Fog of War Chess starter kit

Choose a starter from `starters/`, edit it, and upload that folder as a ZIP.
The kit includes Python, C++, Rust and CPU neural examples, plus a referee for
local testing. Submit your bot's folder, not the entire kit.

## Quick start

1. Copy one folder from `starters/python`, `starters/cpp`, `starters/rust`, or
   `starters/neural`. The Python default, `uniform_random.py`, samples uniformly
   among all legal moves, including castling, en passant and all four promotion
   choices.
2. Edit the bot. Keep `run.sh` in the ZIP root. C++, Rust and neural examples
   include `build.sh`; the basic Python bot runs directly. The server invokes
   these with Bash, so you do not need to mark the scripts executable. Upload
   source, scripts and model weights together.
3. ZIP the contents of that folder. A single enclosing folder is also accepted.
   Leave out your virtual environment, `.git` and compiler caches. Symlinks are
   not accepted. The server runs every submission in the course runtime
   described below.
4. Open your instructor-provided team link to connect and sign in, then upload
   the ZIP on the Submit page. You can also enter your course-issued team token
   after connecting manually. Keep the link and token private; never put them
   in source code or the ZIP. Reopen your team link after reloading the page.
5. Automatic activation is checked by default: once the build and tests pass, the
   version joins the arena even if you have left the page. Uncheck it before
   uploading if you prefer to activate manually. Use **Cancel build/test** to
   stop a queued or running build or test. Open **Build & test logs** to follow
   progress.
6. To switch bots later, choose **Activate version** on any version that passed
   validation. Already assigned matches finish with their original versions.

The upload limit is **128 MiB compressed, 512 MiB expanded, and 10,000 entries**.
The compiled bundle has the same limits. There is a 30-second interval between
uploads and a limit of two pending builds per team. Team storage and version
quotas also apply.

## Versions and Elo

Your team starts at 1500 Elo. Every rated game updates that same rating with
K=8, across all versions. Switching versions does not reset your rating or remove
past results. The reference team, `baseline.py`, stays at 1000.

The Leaderboard ranks teams by Elo. Its win/draw/loss counts cover your active
version; the rating includes all versions. Matchmaking chooses the first team
uniformly at random, then favors opponents with similar Elo. Each pair plays
both colors.

Matches run until the competition deadline. Games assigned before the deadline
finish and count.

## Test your own code locally

Open a terminal in this extracted kit, then run:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python referee.py --trusted-local \
  --white '.venv/bin/python uniform_random.py --seed 1' \
  --black '.venv/bin/python uniform_random.py --seed 2' \
  --white-name 'Uniform 1' --black-name 'Uniform 2' \
  --base-time 180 --increment 2 --max-plies 1000 --output example-match.json
```

The referee saves the game data to `example-match.json` for analysis. Replace either
bot command with your own executable. The local runner executes programs on
your machine without a sandbox: use it only for code you trust. The course
server runs submissions in isolated sandboxes.

Compile the C++ or Rust starter by running `bash build.sh` inside its language
folder. The resulting `bot` executable can be supplied to the local referee.
The server compiles your source for Linux amd64; do not upload a Mac executable.

## Stdin / stdout protocol

Each bot is one persistent process. It first receives:

```text
fow
w 180 2
```

The second line gives your color (`w` or `b`), base time in seconds and increment
in seconds. After reading both lines, initialize your bot, write `ready` followed
by a newline, and flush `stdout` within **15 seconds**. For example, in Python:

```python
print("ready", flush=True)
```

Initialization is outside the game clock. Both the local referee and the arena
require this response. The referee sends no observations until both bots are
ready; a missing or late response loses the game.

Before **every ply** (one player's move), both players receive a 64-character
observation in a1, b1, …, h8 order. Uppercase pieces are White, lowercase pieces
are Black, `-` is a visible empty square, and `?` is unseen. For example, White
initially sees:

```text
RNBQKBNRPPPPPPPP----------------????????????????????????????????
```

Only the moving player then receives its remaining time as a numeric line.
Reply with `move`, a space, and a move in UCI notation, such as:

```text
move e2e4
```

End the line with a newline and flush `stdout`. For promotion, append `q`, `r`,
`b` or `n` to the move; for example, `move e7e8q` promotes to a queen.
Never send a move before receiving a clock prompt, including during the
opponent's turn. Any other `stdout` line, including a blank line or repeated
`ready`, forfeits the game and stops the bot;
use `stderr` for diagnostics. `stdout` is limited to 4 KiB per line, 1 MiB per game
and 256 queued lines. Illegal moves, expired clocks, malformed responses,
premature exit and excessive `stdout` lose the game. Excessive `stderr` produces
a warning; see [Debug output and private logs](#debug-output-and-private-logs).

During play, your bot receives only its observations and clock prompts. It
receives no final king-capture prompt or final observation when the game ends.
Afterward, the downloadable replay includes the full board and both players'
observations.

Games use **180 seconds + 2 seconds per move**. Your bot's entire process,
including child processes and threads, is paused after `ready` and after each
move. It resumes on its next turn, with memory preserved and any queued
observations waiting on `stdin`. It cannot compute during the opponent's turn.
Time spent paused, or pausing and resuming, is not charged to the game clock.

## Rules used by the referee

`referee.py` uses the same board rules as the arena. See the
[Rules tab](https://www.mit.edu/~6.7980/fow/?tab=rules) for the full explanation
and examples of unusual situations. The main differences from ordinary chess are:

- There is no check or checkmate restriction. A move that leaves the moving
  player's king capturable loses immediately. Merely threatening the opponent's
  king gives that opponent its normal next turn to escape.
- Castling may start, cross or finish on attacked squares. The king and rook
  must have their castling rights, with no pieces between them. Castling into
  attack is legal but loses after the move.
- Movement, captures, promotion and en passant otherwise follow ordinary chess.
- You see your pieces and the destinations of all moves allowed by these rules,
  even moves that would expose your king. An opposing piece blocking a pawn's
  forward move stays hidden; a pawn capturable en passant
  is visible even when the capture would be pinned in orthodox chess.
- Threefold repetition or 100 plies without a capture or pawn move draw
  automatically. There is no insufficient-material draw. Having no legal moves
  means a loss.
- Games that reach 1,000 plies end as rated draws.

The Python starter uses only its own observations and remembered castling rights.
It infers en passant from consecutive observations. With no `--seed`, it uses
operating-system entropy; supply a seed for repeatable development games.
The separate `baseline.py` prefers captures and omits en passant inference.
The smaller C++ and Rust examples omit both castling and en passant inference.
They are starting points for your own strategy.

## Runtime and resource limits

The course runtime provides the following software. No GPUs are available.

| Software | Version | Notes |
| --- | --- | --- |
| Python | 3.14.8 | Standard CPython |
| NumPy | 2.3.5 | |
| python-chess | 1.999 | Includes chess 1.11.2 |
| PyTorch | 2.10.0+cpu | CPU only |
| JAX | 0.11.2 | CPU only |
| jaxlib | 0.11.2 | CPU only |
| ONNX Runtime | 1.24.2 | Python package and native C/C++ CPU SDK |
| ONNX | 1.20.1 | |
| C++ compiler (`g++`) | 12.2.0 | C++20 supported |
| Rust compiler (`rustc`) | 1.85.1 | Starters use the 2021 edition |

The native ONNX Runtime C/C++ SDK is at `/opt/onnxruntime`; see
the C++ guide at `starters/cpp/README.md` inside the starter ZIP for the include,
linker and runtime-library flags.
Existing versions keep their original runtime; submit a new version to use an
added runtime dependency.

JAX runs on CPU. Import libraries and compile any JIT functions you need before
printing `ready`; this initialization must fit within the 15-second allowance.
Each game starts a fresh process, so an in-memory JIT cache does not carry over
from the build or another game.

Python dependency installation and Cargo/network downloads are unavailable in
student builds and games. Include additional dependencies inside your ZIP
and build Rust packages with `cargo build --release --offline` when using Cargo.

Builds and games run in a gVisor sandbox with these limits:

| Resource | Limit |
| --- | --- |
| CPU | 2 physical cores / 4 hardware threads |
| Memory | 4 GiB per bot |
| Processes | 64 |
| Writable workspace | 768 MiB, stored in RAM |
| `/tmp` | 128 MiB, stored in RAM |
| Build time | 5 minutes |
| Bot initialization | 15 seconds, before the game clock starts |
| Network | Unavailable |

The runtime filesystem is read-only except for the workspace and `/tmp`.
Both writable areas count toward the memory limit, along with model weights
and working memory. No changes to memory or files survive into the next game.
Sandbox setup has a separate 10-second limit before your bot receives its
protocol headers.

Both bots in a game share the same cores. Your opponent is paused on your turn;
other matches use separate cores. The runtime defaults OpenMP, OpenBLAS and MKL
to one thread. To use more, configure the library's thread count explicitly.
Benchmark one, two and four threads: four hardware threads still share two
physical cores.

## Validation

Validation runs a full game against the baseline in both colors under the same
180+2 time control and resource limits. Winning, drawing or losing normally all
pass validation. A timeout or confirmed out-of-memory kill during play produces
a warning, and testing continues in the other color. Other crashes,
initialization failures, illegal moves and malformed protocol output fail
validation. The runtime must confirm an OOM kill; exit code 137 or a printed
OOM message alone is not enough.

Validation games do not count toward Elo. Timeouts and OOM in rated games are
losses.

## Neural starter

`starters/neural` demonstrates a feedforward policy, a recurrent policy and
one-ply value search. Train on your own computer and submit the source and
weights. If you do not supply trained weights, the build generates untrained
weights so you can test loading and inference.

The build exports PyTorch weights to ONNX for fast startup within the
15-second initialization limit. Its `build.sh` preserves a supplied `policy.pt`.
The starter uses two intra-op threads and one inter-op thread for inference.
Load the model once and keep it, along with any recurrent state, for the game.
Use evaluation mode with gradients disabled. The preinstalled libraries do not
count toward ZIP limits.

## Debug output and private logs

Write debug logs to `stderr`. The arena saves only the last 16 KiB per bot.
A `stderr` line over 4 KiB or more than 1 MiB total produces a warning in
validation and game reports, without causing a forfeit.
Printing still consumes your bot's CPU and clock budget. `stdout` protocol limits
remain enforced.

For a completed game, open the **Games** tab, choose **Log** in its row, then
**Private stderr**, and enter your team token. You can read or download your
bot's log. The token stays in memory only and is cleared when the dialog closes.
Server details are redacted; logs flagged as possibly containing secrets are
withheld for staff review. Missing or expired logs are shown as unavailable.
