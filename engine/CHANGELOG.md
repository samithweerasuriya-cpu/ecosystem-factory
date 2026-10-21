# Engine changelog

## 0.1.0 (2026-10-21)

First version, derived from the author's earlier private lab.

- Kept: job state machine, hash-bound human-only gate tokens, gate audit log, fail-closed PreToolUse hook, findings validator with severity lock, Windows file-lock retry when saving state.
- Changed: routes are data in route format v1 (`schemas/route.schema.json`) with agent, script and fan-out stages, ordered reviews of kind critic or verifier, `revise_with`, `fix_with`, `gate`, `deliver`; no agent names in the engine code. Review events are `review_pass` / `review_fail`.
- Changed: MCP tools are denied unless `config/gated-actions.json` allows them; gated shell commands come from the same file.
- Changed: the severity lock reads each reviewer's rulebook from `config/reviewers.json`.
- Changed: the approver's name comes from `config/gates.json` (fallback: the OS user name).
- Added: fan-out with a fixed item list per stage, per-item results, and a merge that waits for all items; script stages with an allow-list, a timeout per command, saved output and a capped `fix_with` loop.
- Added: `engine/schemacheck.py`, a stdlib JSON Schema subset used by the validators, so the engine never needs the venv.
