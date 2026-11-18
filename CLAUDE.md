@AGENTS.md

## Claude Code specifics

- Read the current step spec in `docs/specs/` before writing code, and restate its acceptance tests in a todo list.
- Run the full test suite (`.venv/bin/python -m pytest` plus the starter tests) before declaring a step done.
- Record every non-trivial decision you make or propose as an ADR in `docs/adr/` (rules in `AGENTS.md` § Decision records). Default to `Status: Proposed`, `Decided by: Claude Code`.
- Don't commit unless asked. When asked, use small commits, one logical change each.