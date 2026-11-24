# Local verification results

Verified November 9, 2026 using the existing Python 3.9.6 virtual environment
and NumPy 1.26.4. These are local functional checks, not arena certification
or a statistically meaningful playing-strength evaluation.

## Full games

All games used the default bot settings, the baseline opponent, 180 seconds
plus 2 seconds per move, and a 1,000-ply limit. All ended naturally because a
king was capturable. No game had a failedSide field or referee warnings.

| Mode | Bot color | Result for bot | Plies | Startup | Longest move response |
| --- | --- | --- | ---: | ---: | ---: |
| Material fallback | White | Loss | 41 | 0.241 s | 0.544 s |
| Material fallback | Black | Loss | 34 | 0.219 s | 0.571 s |
| Neural checkpoint | White | Loss | 13 | 2.233 s | 0.589 s |
| Neural checkpoint | Black | Loss | 8 | 2.273 s | 0.520 s |

Startup is measured from the protocol's `fow` input to `ready`. Move response
is measured from clock prompt to move output. These are local wall-clock
measurements, including scheduling overhead; they do not predict arena timing.
Both colors were run concurrently on the development machine.

Replays: [material White](material-white.json), [material Black](material-black.json),
[neural White](neural-white.json), [neural Black](neural-black.json).

## Training and checkpoint loading

Ran from the repository root:

```sh
.venv/bin/python -m transformer_bot.train verification/material-white.json verification/material-black.json --epochs 2 --batch-size 16 --output verification/smoke-transformer.pt
```

| Epoch | Training loss | Validation loss |
| --- | ---: | ---: |
| 1 | 4.1913 | 5.3772 |
| 2 | 3.4668 | 6.1759 |

The trainer saved the first epoch, which had the better validation loss.
[smoke-transformer.pt](smoke-transformer.pt) is a roughly 5.9 MiB pipeline-test
checkpoint trained from only two games, with one game used for training and
the other for validation. It is not a competitive trained model. Both neural
games successfully loaded it and produced legal protocol responses.

The existing 21 unit tests passed earlier, including forward/backward neural
computation, and pip reported no dependency conflicts. No source changes were
required for these subsequent game and training checks.

## Remaining issues

Every game logged belief exhaustion and switched to policy/capture fallback.
The bounded particle filter needs recovery/rejuvenation or a stronger belief
representation before search can contribute reliably throughout a game.
Training needs a substantially larger, more diverse dataset and independent
playing-strength evaluation. Arena packaging and benchmarking in the actual
course runtime are still outstanding.
