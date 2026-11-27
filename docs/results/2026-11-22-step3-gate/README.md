# Step 3 Part B gate: particle agents vs safety_v2

**What:** the spec's gate (§ Experiments and gate). Each particle agent plays the shipped `safety_v2`, 200 pairs × seeds 0–2 = 1,200 games, n = 64 (ADR 0018), uniform model, re-expansion recovery. λ = 30 extends the grid one step, because the best of {100, 300, 1000} was at its edge. Used by [ADR 0019](../../adr/0019-ship-particle-ev100.md) and `docs/log.md` § Step 3 Part B.

**Machine:** Windows 11 dev machine, 22 logical cores, 20 workers, Python 3.11.

**Commands** (repo root):

```sh
bash docs/results/2026-11-22-step3-gate/run.sh .venv/Scripts/python.exe 20              # v2, ev100, ev300, ev1000
AGENTS=particle_ev30 bash docs/results/2026-11-22-step3-gate/run.sh .venv/Scripts/python.exe 20
python -m harness.step3_queue --workers 20     # reran particle_ev1000 (see below), then the ablations
```

**Files:**
- `cli_<agent>.txt`: per-seed and pooled scores, termination reasons and think times.
- `breakdown_<agent>.txt`: loss classes (a/b/c) and hidden-attacker types.
- `summaries/`: per-game JSONL, input to `harness.paired_compare`.
- `*_slept*`: the first `particle_ev1000` run, kept as a record (see below).

## Results (verified)

| Agent | Seed 0 | Seed 1 | Seed 2 | Pooled [95% CI] | W/D/L | Loss classes (a/b/c) |
|---|---|---|---|---|---|---|
| `particle_v2` (`p_loss` as tie-break) | 0.599 | 0.593 | 0.586 | 0.593 [0.564, 0.620] | 632/158/410 | 45 / 365 / 0 |
| `particle_ev30` | 0.616 | 0.606 | 0.610 | 0.611 [0.583, 0.638] | 651/164/385 | 18 / 367 / 0 |
| **`particle_ev100`** | 0.611 | 0.625 | 0.614 | **0.617 [0.589, 0.644]** | 662/156/382 | 9 / 373 / 0 |
| `particle_ev300` | 0.610 | 0.621 | 0.594 | 0.608 [0.580, 0.636] | 653/154/393 | 4 / 389 / 0 |
| `particle_ev1000` | 0.594 | 0.594 | 0.588 | 0.592 [0.564, 0.619] | 632/156/412 | 3 / 409 / 0 |

- **The gate passes.** The best agent's pooled lower bound is 0.589, above 0.5. Every variant beats `safety_v2` on every seed.
- **λ = 100 is the best value, and it lies inside the grid** once λ = 30 is included. Paired differences against `particle_ev100` (`../2026-11-27-step3-ablations/paired_vs_ev100.txt`):
  - λ = 30 and λ = 300 are ties: −0.006 [−0.015, +0.003] and −0.008 [−0.021, +0.005].
  - λ = 1000 is worse: −0.025 [−0.043, −0.007].
  - `particle_v2` is worse: −0.024 [−0.036, −0.012]. Risk as an expected-value term beats risk as a tie-break.
- **The loss classes show the trade λ controls.** Higher λ means fewer (a) losses, where a safe move existed but we chose an exposed one, and more (b) losses, where every move was exposed and the threat was real. Cautious play costs material, and that leads to more forced exposure later.
- **No losses other than king capture.** All draws are threefold repetition, except one by the 50-move rule.
- **Think times here are contended** (20 workers). The time budget is judged on `../2026-11-22-step3-timing/`.

## The `particle_ev1000` rerun (verified)

- **The laptop slept for about 12 hours** during the first `particle_ev1000` run. The harness charges wall-clock time to the bot's clock, so games in flight came back with near-zero clocks. That tripped the time guard (ADR 0017) in 29 games and 593 decisions, which then played like `safety_v2`.
- **The run was repeated** after `harness.step3_queue` had checked every replay for time-guard decisions. The rerun had none, and neither did any other run in this folder.
- **The first run's outputs are kept** as `cli_particle_ev1000_slept.txt`, `breakdown_particle_ev1000_slept.txt` and `summaries_slept/`. Seeds 0 and 1 reproduced exactly (0.594, 0.594). Seed 2 changed from 0.599 to 0.588.
