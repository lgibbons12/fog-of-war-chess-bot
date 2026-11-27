# Experiment results

Saved outputs of experiment runs, kept for the final writeup. One folder per run: `YYYY-MM-DD-<short-name>/`.

Each folder contains:
- **`README.md`**: what was run and why, the exact command, the machine, the findings, and links to the ADRs or log sections that use it. Label each claim verified, assumed, or unverified.
- **Raw outputs** from the run (`*_raw.jsonl`, `*_summary.csv`, ...), so the tables can be regenerated.
- **`tables.md`** (optional): generated tables, e.g. from `python -m harness.matrix_report <folder>`.

Replays and large binaries do not go here (`replays/` is gitignored). Keep each folder small enough to commit, aiming for a few MB at most.

## Index

| Folder | Step | What |
|---|---|---|
| [2026-11-17-step3-tracker-matrix](2026-11-17-step3-tracker-matrix/README.md) | 3 | Particle-tracker decision matrix: n × opponent model × resampling trigger × recovery × diversity, scored on 60 replayed games |
| [2026-11-22-step3-timing](2026-11-22-step3-timing/README.md) | 3 | Particle agent per-move time vs n (20 games per n against safety_v2, single worker) |
| [2026-11-22-step3-gate](2026-11-22-step3-gate/README.md) | 3 | Part B gate: particle agents (λ ∈ {30, 100, 300, 1000} and the tie-break variant) vs safety_v2, 1,200 games each |
