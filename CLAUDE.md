@AGENTS.md

## Claude Code specifics

- Read the current step spec in `docs/specs/` before writing code, and restate its acceptance tests in a todo list.
- Run the full test suite (`.venv/bin/python -m pytest` plus the starter tests) before declaring a step done.
- Don't commit unless asked. When asked, use small commits, one logical change each.