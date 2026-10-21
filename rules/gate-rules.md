# Gate rules

A gate is a human decision by the approver, recorded as a token file bound to the exact artifact they reviewed. Think of it as a release strategy: nothing moves past the gate until the named person releases it, and the release covers only the exact version they saw.

## Gates
Each route in `config/routes.json` names its gate (`G<n>-<name>`) or `null` (the job ends DONE after its reviews pass). A route may require a parent job's gate (`requires_parent_gate`) before a child job can be created. Delivery (`deliver`) runs only after approval, so a route with a delivery stage must have a gate.

## Token
`jobs/<job>/gates/<gate>.json` = `{gate, job_id, artifact_path, sha256, approved_by, approved_at, note}`.
- Created only by `python engine/gate.py approve <job>`, run by the approver in their own terminal (an interactive terminal is required).
- `approved_by` is the approver named in `config/gates.json`; if none is set, the OS user name.
- Valid only while the artifact's SHA-256 still matches. Any edit after approval voids it.

## Enforcement layers
1. `engine/labcore.py`: approve/reject events are unreachable except through `gate.py`; `script_fail` is recorded only by `state.py run`; caps pause the job.
2. `.claude/settings.json`: deny rules for `gate.py`, `git push` and secret files.
3. `engine/hooks/pre_tool_use.py`: blocks writes to gates, state, run logs and script outputs; blocks every MCP tool not allowed in `config/gated-actions.json`; gates the shell commands listed there; locks framework files in operate mode. It fails closed: bad input or errors exit 2, and `onFailure: block` in settings blocks actions if the hook can't start.
4. Unit tests (`engine/tests/`) prove each rule. Run them after any change to the engine or config.

## Script stages
A script stage runs a command from `config/scripts.json` through `python engine/state.py run <job>`: no shell, a timeout per command, and the command, output and exit code saved to `jobs/<job>/scripts/`. A failure (non-zero exit or timeout) hands the job to the route's `fix_with` agent, capped by `fix_attempts`.

**The allow-list in `config/scripts.json` is the real control for script stages.** A route can only name scripts on that list, and whatever is on the list runs with the engine's permissions. The list is a framework file: it is locked in operate mode, and any change to it needs the same review and eval run as other config changes before operate mode is re-locked.

## Before approving, the approver checks
- Every review verdict is pass, and the findings were read.
- Open questions are acceptable for this stage (a draft approved with open questions says so in the note).
- For a gate before delivery: the delivery target and scope are right, and nothing was written to an external system before approval.

## Rejection
`python engine/gate.py reject <job> --feedback "..."` writes `reviews/human-feedback-<n>.md` and sends the job to REVISING. Three rejections → ESCALATED (re-scope the job).

## Residual risk (be honest)
This is a local guardrail, not a security boundary. Shell detection is pattern-based. It stops accidents and prompt drift, not someone deliberately bypassing it on the same machine.
