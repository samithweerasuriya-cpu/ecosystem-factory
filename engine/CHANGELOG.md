# Engine changelog

## 0.2.0 (2026-10-21)

Fixes from the run history of the author's earlier private lab.

- Job-lifetime caps that never reset: `lifetime_agent_calls`, `lifetime_revisions` (every review failure, reference-check failure and gate rejection), `lifetime_resumes` (a resume past the cap is refused), `input_rounds`, `repairs`.
- Scripted handoffs: `state.py handoff <job> [--item]` builds the block from state, route and recorded inputs, logs it with a hash, and links it to the next call. Critics get the artifact, rulebook, the approver's inputs and gate feedback; verifiers also get the evidence pack, source registry and source policy; neither gets the author's notes. Revisers also get the brief, evidence pack and this round's findings.
- Complete call log: every call has an id, `attempt` and `retry_of`; one call per agent (and fan-out item) per step; a repeat needs `infra_error` or `repair` (`invalid_output`, `severity_directive`; one re-ask per call, capped by `repairs`). Calls must name the agent the job is waiting on.
- Human inputs: `state.py input <job> <file|-> --class synthetic|public|internal` stores the text verbatim with an id and hash; internal inputs go to `private/jobs/<job>/inputs/` and are refused from a source Git could track. Inputs and questions are hook-protected.
- Reference check (`engine/check_refs.py`) on every new artifact version: missing paths, unresolved job or input IDs and references to older drafts of the same job send it back to the author with `check-refs` findings.
- AWAITING_INPUT: `needs_input --questions FILE` pauses the job with the questions stored verbatim; `answered` (after at least one new input) returns to the same step; not a resume.
- `state.py new ... --continue-from <job>`: a new job seeded with a finished or paused job's latest artifact and inputs, linked both ways in the run logs, with fresh counters.

## 0.1.0 (2026-10-21)

First version, derived from the author's earlier private lab.

- Kept: job state machine, hash-bound human-only gate tokens, gate audit log, fail-closed PreToolUse hook, findings validator with severity lock, Windows file-lock retry when saving state.
- Changed: routes are data in route format v1 (`schemas/route.schema.json`) with agent, script and fan-out stages, ordered reviews of kind critic or verifier, `revise_with`, `fix_with`, `gate`, `deliver`; no agent names in the engine code. Review events are `review_pass` / `review_fail`.
- Changed: MCP tools are denied unless `config/gated-actions.json` allows them; gated shell commands come from the same file.
- Changed: the severity lock reads each reviewer's rulebook from `config/reviewers.json`.
- Changed: the approver's name comes from `config/gates.json` (fallback: the OS user name).
- Added: fan-out with a fixed item list per stage, per-item results, and a merge that waits for all items; script stages with an allow-list, a timeout per command, saved output and a capped `fix_with` loop.
- Added: `engine/schemacheck.py`, a stdlib JSON Schema subset used by the validators, so the engine never needs the venv.
