# Step 3 Part B timing run: particle agent per-move time vs n

**What:** the spec's timing run (§ Choosing `n`). 20 games of `particle_ev300` (n = 256, registered at the time as the default) or `particle_ev300_n{32,64,128,512}` against `safety_v2`, single worker per n. Used by [ADR 0018](../../adr/0018-particle-count-64.md).

**Machine:** Windows 11 dev machine (22 logical cores), Python 3.11 (uv venv). The five n values ran as five parallel single-worker processes, alongside one pytest process, so there was light contention.

**Command** (repo root, at the commit that adds this folder, with `DEFAULT_N = 256`):

```sh
for n in 32 64 128 256 512; do
  name=particle_ev300_n$n; [ $n = 256 ] && name=particle_ev300
  .venv/Scripts/python.exe -m harness.cli $name safety_v2 --pairs 10 --seed 0 --workers 1 \
    --save-replays replays/timing/n$n --summary replays/timing > cli_n$n.txt &
done; wait
.venv/Scripts/python.exe -m harness.particle_timing replays/timing/n{32,64,128,256,512} --json timing.json
```

**Files:**
- `cli_n*.txt`: match output, including scores. These are 20 games each, too few to compare strength.
- `timing.md` / `timing.json`: per-move time, set health and decision modes.

Time per move is the particle updates since the previous decision plus the decision itself (`p_loss` for every legal move), as recorded by the agent.

## Findings

| n | Median s | p95 s | p99 s | Max s | Moves > 1.5 s | Median distinct | Median ESS | Depletions/game |
|---|---|---|---|---|---|---|---|---|
| 32 | 0.058 | 0.218 | 0.470 | 0.771 | 0 | 25 | 22.9 | 3.30 |
| 64 | 0.071 | 0.401 | 0.690 | 1.462 | 0 | 34 | 29.1 | 1.90 |
| 128 | 0.101 | 0.776 | 1.006 | 3.341 | 2 | 41.5 | 29.0 | 1.90 |
| 256 | 0.145 | 1.113 | 1.737 | 5.309 | 16 | 67 | 42.2 | 0.75 |
| 512 | 0.178 | 1.919 | 3.328 | 3.973 | 59 | 84 | 49.6 | 0.35 |

- **Verified:** only n ≤ 64 meets the budget (median < 0.4 s, max < 1.5 s). n = 64 is chosen (ADR 0018).
- **Verified:** the slowest moves at n ∈ {64, 128, 256} are depletion recoveries (re-expansion or regeneration in one update). At n ≥ 256, steady-state moves with a full set also exceed 1.5 s.
- **Verified:** the time guard and error fallbacks never fired. One n = 64 decision ran in `unavailable` mode.
- **Not measured:** the spec's "surviving candidates per particle" distribution. The tracker doesn't record it, and the timing table above was enough for the decision.
