"""Run the rest of Step 3 Part B in order and keep a live progress page up to date.

``python -m harness.step3_queue [--workers 20] [--page replays/progress.html]``

Queue:
1. wait for ``particle_ev30`` (started separately), then rerun ``particle_ev1000``
   (its first run was hit by a 12-hour laptop sleep that tripped the time guard);
2. pick the best EV agent by pooled score against safety_v2 (lambda in {30, 100, 300, 1000});
3. ablations of the best: capture model, n in {32, 128, 256}, vs baseline, vs random;
4. particle metrics (calibration, truth coverage, log loss) on the best agent's gate replays.

Every game is deterministic, so a step that is interrupted can simply be rerun.
The page refreshes itself every 10 s and turns red when updates stop.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

GATE = Path("docs/results/2026-11-22-step3-gate")
ABLATE = Path("docs/results/2026-11-27-step3-ablations")
PAIRS, SEEDS = 200, (0, 1, 2)
GAMES = 2 * PAIRS * len(SEEDS)
SCORE = re.compile(r"(?:Pooled|Score) \(A\): ([0-9.]+)\s+95% CI \[([0-9.]+), ([0-9.]+)\]")


class Step:
    def __init__(self, key: str, title: str, kind: str, agent: str = "", opponent: str = "safety_v2",
                 out: Path = GATE, replays: str = "", external: bool = False):
        self.key, self.title, self.kind = key, title, kind
        self.agent, self.opponent, self.out = agent, opponent, out
        self.replays = Path(replays or f"replays/{'gate' if out == GATE else 'ablations'}/{agent}")
        self.external = external
        self.status = "queued"
        self.started: float | None = None
        self.finished: float | None = None
        self.note = ""

    @property
    def cli_file(self) -> Path:
        return self.out / f"cli_{self.agent}{'' if self.opponent == 'safety_v2' else '_vs_' + self.opponent}.txt"

    def games_done(self) -> int:
        if self.kind != "match" or not self.replays.exists():
            return 0
        return sum(1 for _ in self.replays.rglob("pair*.json"))

    def score(self):
        if self.kind != "match" or not self.cli_file.exists():
            return None
        match = SCORE.search(self.cli_file.read_text(errors="replace"))
        return tuple(float(x) for x in match.groups()) if match else None


def run(cmd: list[str], stdout: Path | None = None) -> None:
    with open(stdout, "w") if stdout else open(os.devnull, "w") as out:
        subprocess.run(cmd, stdout=out, stderr=subprocess.DEVNULL, check=True)


def run_match(step: Step, py: str, workers: int) -> None:
    if step.replays.exists():
        shutil.rmtree(step.replays)
    step.out.mkdir(parents=True, exist_ok=True)
    run([py, "-m", "harness.cli", step.agent, step.opponent, "--pairs", str(PAIRS), "--seed",
         *map(str, SEEDS), "--workers", str(workers), "--save-replays", str(step.replays),
         "--summary", str(step.out / "summaries")], step.cli_file)
    suffix = "" if step.opponent == "safety_v2" else "_vs_" + step.opponent
    run([py, "-m", "harness.breakdown", str(step.replays), "--agent", step.agent],
        step.out / f"breakdown_{step.agent}{suffix}.txt")


def time_guard_games(replays: Path) -> int:
    count = 0
    for path in replays.rglob("pair*.json"):
        frames = json.loads(path.read_text())["frames"][1:]
        count += any(f["decision"] and f["decision"].get("particle_mode") == "time_guard" for f in frames)
    return count


# ----- page --------------------------------------------------------------------

CSS = """
:root { --bg:#f7f7f5; --card:#fff; --text:#1d1d1b; --muted:#6b6b66; --line:#e3e3de; --bar:#e9e9e4;
  --run:#2f6fde; --done:#1f8a4c; --warn:#b3261e; --queued:#9a9a93; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --card:#1f1f1d; --text:#ecece8; --muted:#9a9a93;
  --line:#33332f; --bar:#2b2b28; --run:#6b9bff; --done:#4cc27e; --warn:#ff7a70; --queued:#77776f; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:860px; margin:0 auto; padding:28px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--muted); margin:0 0 20px; }
.banner { padding:10px 14px; border-radius:8px; margin-bottom:16px; font-weight:600; display:none; }
.banner.stale { display:block; background:color-mix(in srgb,var(--warn) 15%,transparent); color:var(--warn); }
.overall { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; }
.overall .big { font-size:28px; font-weight:700; font-variant-numeric:tabular-nums; }
.bar { height:8px; background:var(--bar); border-radius:4px; overflow:hidden; margin-top:8px; }
.bar > div { height:100%; background:var(--run); } .bar.done > div { background:var(--done); }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
th, td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); font-weight:600; }
tr:last-child td { border-bottom:none; }
td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
.pill { display:inline-block; font-size:12px; font-weight:600; padding:2px 8px; border-radius:999px; color:#fff; }
.pill.queued { background:var(--queued); } .pill.running { background:var(--run); } .pill.done { background:var(--done); }
.pill.failed { background:var(--warn); } .pill.skipped { background:var(--queued); }
.note { color:var(--muted); font-size:13px; } .best { font-weight:700; }
.scroll { overflow-x:auto; }
@media (max-width:600px) { th:nth-child(4), td:nth-child(4) { display:none; } }
"""


def fmt_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h {rest // 60:02d}m" if hours else f"{rest // 60}m {rest % 60:02d}s"


def render(steps: list[Step], best: str | None, path: Path, finished: bool) -> None:
    now = time.time()
    rows, done_units, total_units = [], 0.0, 0.0
    for step in steps:
        weight = 1.0
        total_units += weight
        progress = 0.0
        detail = ""
        if step.kind == "match":
            games = min(step.games_done(), GAMES) if step.status != "queued" else 0
            progress = 1.0 if step.status in ("done", "skipped") else games / GAMES
            detail = f"{games if step.status != 'done' else GAMES} / {GAMES} games"
            if step.status == "running" and step.started and games and not step.external:
                rate = games / (now - step.started)
                detail += f" · ETA {fmt_duration((GAMES - games) / rate)}"
        elif step.status in ("done", "skipped"):
            progress = 1.0
        done_units += weight * progress
        score = step.score() if step.kind == "match" and step.status == "done" else None
        score_text = f"{score[0]:.3f} <span class='note'>[{score[1]:.3f}, {score[2]:.3f}]</span>" if score else "—"
        if step.status == "done" and step.started and step.finished:
            detail += f" · took {fmt_duration(step.finished - step.started)}"
        name = html.escape(step.title)
        if best and step.agent == best and step.out == GATE:
            name = f"<span class='best'>{name} ★ best</span>"
        bar = (f"<div class='bar{' done' if progress >= 1 else ''}'><div style='width:{100 * progress:.1f}%'></div></div>"
               if step.kind == "match" else "")
        note = f"<div class='note'>{html.escape(step.note)}</div>" if step.note else ""
        rows.append(f"<tr><td>{name}{note}</td><td><span class='pill {step.status}'>{step.status}</span></td>"
                    f"<td class='num'>{score_text}</td><td class='num'>{detail}{bar}</td></tr>")
    overall = 100 * done_units / max(total_units, 1)
    headline = "All Step 3 Part B experiments finished." if finished else \
        f"Running: {next((s.title for s in steps if s.status == 'running'), 'between steps')}"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{'' if finished else '<meta http-equiv="refresh" content="10">'}
<title>Step 3 Progress</title><style>{CSS}</style></head><body><main>
<h1>Step 3 Part B: experiment progress</h1>
<p class="sub">Particle agents vs <code>safety_v2</code> unless noted · 200 pairs × seeds 0–2 = {GAMES} games per run ·
score is the particle agent's, with a 95% CI; above 0.5 means it is winning.</p>
<div id="stale" class="banner">No update for over a minute: the queue may have stopped or the laptop may be asleep.</div>
<div class="overall"><div class="big">{overall:.0f}%</div><div>{html.escape(headline)}</div>
<div class="bar{' done' if finished else ''}"><div style="width:{overall:.1f}%"></div></div>
<p class="note">Last updated {datetime.fromtimestamp(now).strftime('%a %H:%M:%S')}
{'' if finished else '· refreshes every 10 s'}</p></div>
<div class="scroll"><table><thead><tr><th>Run</th><th>Status</th><th>Score</th><th>Progress</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</main><script>
var updated = {int(now * 1000)}, finished = {str(finished).lower()};
function check() {{ if (!finished && Date.now() - updated > 60000) document.getElementById('stale').className = 'banner stale'; }}
check(); setInterval(check, 5000);
</script></body></html>"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    os.replace(tmp, path)


# ----- queue -------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--page", type=Path, default=Path("replays/progress.html"))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    py = args.python
    args.page.parent.mkdir(parents=True, exist_ok=True)

    gate = [Step(a, a, "match", a) for a in ("particle_v2", "particle_ev100", "particle_ev300")]
    for step in gate:
        step.status = "done" if step.score() else "failed"
    ev30 = Step("particle_ev30", "particle_ev30 (λ grid extension)", "match", "particle_ev30", external=True)
    ev1000 = Step("particle_ev1000", "particle_ev1000 (rerun after laptop sleep)", "match", "particle_ev1000")
    steps = gate + [ev30, ev1000]
    ablations = [Step(f"abl{i}", t, "match", "", opp, ABLATE) for i, (t, opp) in enumerate([
        ("best · capture opponent model", "safety_v2"), ("best · n = 32", "safety_v2"),
        ("best · n = 128", "safety_v2"), ("best · n = 256", "safety_v2"),
        ("best vs baseline", "baseline"), ("best vs random", "random")])]
    metrics = Step("metrics", "Particle metrics on the best agent (calibration, truth coverage)", "metrics")
    steps += ablations + [metrics]
    state = {"best": None, "finished": False}
    stop = threading.Event()

    def painter():
        while not stop.is_set():
            try:
                render(steps, state["best"], args.page, state["finished"])
            except Exception as error:  # never let the page kill the queue
                print(f"page: {error}", file=sys.stderr)
            stop.wait(5)

    threading.Thread(target=painter, daemon=True).start()
    print(f"progress page: {args.page.resolve()}", flush=True)

    def attempt(step: Step, action) -> bool:
        step.status, step.started = "running", time.time()
        try:
            action()
            step.status = "done"
            return True
        except Exception as error:
            step.status, step.note = "failed", str(error)[:200]
            return False
        finally:
            step.finished = time.time()

    # 1. ev30 is running in another process: wait for its breakdown, which run.sh writes last.
    ev30.status, ev30.started = "running", time.time()
    breakdown30 = GATE / "breakdown_particle_ev30.txt"
    while not (breakdown30.exists() and breakdown30.stat().st_size > 0 and ev30.score()):
        time.sleep(5)
    ev30.status, ev30.finished = "done", time.time()
    guard = time_guard_games(ev30.replays)
    ev30.note = f"time-guard games: {guard}" + (" (contaminated; rerun needed)" if guard else " (clean)")

    def rerun_1000():
        run_match(ev1000, py, args.workers)
        guard = time_guard_games(ev1000.replays)
        ev1000.note = f"time-guard games: {guard}" + (" (contaminated!)" if guard else " (clean)")
    attempt(ev1000, rerun_1000)

    # 2. best EV agent by pooled score
    candidates = {s.agent: s.score() for s in steps if s.agent.startswith("particle_ev") and s.score()}
    best = max(candidates, key=lambda a: candidates[a][0])
    state["best"] = best
    lam = best.removeprefix("particle_ev")
    for step, agent in zip(ablations, [f"{best}_capture", f"{best}_n32", f"{best}_n128", f"{best}_n256",
                                       best, best]):
        step.agent = agent
        step.replays = Path(f"replays/ablations/{agent}{'' if step.opponent == 'safety_v2' else '_vs_' + step.opponent}")
        step.title = step.title.replace("best", f"λ={lam}")

    # 3. ablations
    for step in ablations:
        attempt(step, lambda step=step: run_match(step, py, args.workers))

    # 4. metrics on the best agent's gate replays
    attempt(metrics, lambda: run([py, "-m", "harness.particle_metrics", f"replays/gate/{best}", "--agent", best,
                                  "--out", str(ABLATE / "metrics"), "--workers", str(args.workers)]))
    state["finished"] = True
    stop.set()
    render(steps, best, args.page, True)
    print("queue finished", flush=True)


if __name__ == "__main__":
    main()
