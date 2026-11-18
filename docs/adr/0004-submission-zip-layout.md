# 0004. Submission zip keeps `bot/` as a package

- **Status:** Accepted
- **Date:** 2026-10-22
- **Step:** 0
- **Decided by:** Claude Code, agreed by team
- **Source:** `docs/log.md` § Step 0, issue 3; `scripts/package.sh`

## Context

The original plan was to zip `bot/`'s *contents* plus `referee.py`. Code under `bot/` imports itself as `bot.*`, so flattening the folder breaks every import.

## Decision

The zip contains a top-level `run.sh` (`cd "$(dirname "$0")" && exec python3 -u -m bot.protocol --agent <name>`), `referee.py`, and `bot/` as a folder. `scripts/package.sh [agent]` builds it, and `scripts/check_package.sh` unzips it and plays the real referee against `baseline.py` in both colors.

## Alternatives considered

- **Flatten and use relative or bare imports:** would break running from the repo, or require two import styles.

## Evidence

- **verified:** `check_package.sh` passed for `safety_v2` (13 files), winning as White and as Black with no protocol failures.

## Consequences

- The arena agent is chosen at package time by registry name, so the same zip build serves any agent.
- `.gitattributes` forces LF line endings on `*.sh`, because a CRLF `run.sh` fails under bash.
