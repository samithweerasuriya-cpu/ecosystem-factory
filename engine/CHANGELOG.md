# Engine changelog

## 0.5.0 (2026-10-21)

Usage log and ceiling.

- A call stays open until its result is recorded; no new call while one is open, except parallel items of the current fan-out stage (up to its max). `infra_error` and `repair` close the call they retry (usage unknown).
- Each call links to the newest unused handoff built for its agent and item (a retry reuses its original's), so parallel fan-out items keep their own handoffs.
- `engine/hooks/post_tool_use.py` (registered through the never-edited, hash-pinned `post_tool_use_launcher.py`, matcher `Agent|Task`): closes the open call whose handoff ID (`JOB:` and `HANDOFF:` lines in the subagent prompt) matches, with the app's own figures; unmatched calls go to `logs/usage-unmatched.jsonl`, never dropped.
- `state.py result <job> <call> done|failed [--usage-json]` for headless results and manual closes; `state.py usage <job>`; usage lines in `logs/usage.jsonl` (internal jobs: `private/logs/`) with input, output, cache-read and cache-write tokens separately; usage logs are hook-protected.
- `usage_ceiling` in `config/caps.json` (provisional until T1.4): tokens when reported, agent minutes always; reaching it pauses the job; only `engine/gate.py ceiling` raises it (audited); a per-call warning threshold flags calls without stopping the job.
- Call start and end times are recorded to the millisecond.

## 0.4.1 (2026-10-21)

- MCP entries may carry `roles` (`["main"]`: only calls without `agent_id`); the factory allows the desktop app's two task-list tools by exact name, main session only.
- Not read-only any more: `sort -o/--output`, `uniq IN OUT`, `git grep -O/--open-files-in-pager`, `git log/diff/show --output/--ext-diff/--textconv`, any `git -c` or `--config-env`.
- Inline interpreter code (`-c`, `-e`, heredocs, `powershell -Command`, PowerShell script blocks) that calls a delete function (rmtree, remove, unlink, rmdir, Remove-Item and their Node/Ruby forms) is blocked whatever path it names.

## 0.4.0 (2026-10-21)

Hook fixes and isolation.

- Fail-closed shell analysis: a command that names a protected path (or a folder holding one) is allowed only if every part is on the read-only allow-list; nested `bash -c`, `sh -c`, `powershell -Command`, `cmd /c` and `wsl` are checked recursively; unparseable commands naming a protected path are blocked; `eval`, `iex`, `Invoke-Expression`, base64 decoding and encoded PowerShell commands are always blocked. False positives of the earlier lab fixed: harmless redirects, secret names inside regex text, `cd` followed, text mentions of `gate.py`.
- Path normalisation: absolute, `./` and `..`, quotes, backslashes, Git Bash `/c/` and WSL `/mnt/c/`, case, 8.3 short names; option-prefixed paths (`-r<path>`); another ecosystem's gate/state files anywhere.
- `config/protected-paths.json`: no-write roots (the generated ecosystems' folder; source folders in the untracked `config/protected-paths.local.json`) and read blocks: subagents (detected by `agent_id`) never read the method lab, `private/`, `docs/thin/` or eval keys, nor search from above them; in operate mode the main session is blocked from the method lab, `private/` (plan read-only) and eval keys; the active internal job's folder is the one exception.
- Writes outside the repo only into the harness's `scratchpad_dir`, and only if it lies outside the repo and every guarded root.
- Blocks touching `private/` or made while an internal job is active are logged to `private/logs/blocked.jsonl`.
- `engine/hooks/pre_tool_use_launcher.py`: never-edited, pinned by hash; any failure of the real hook (syntax, import, crash, bad return) blocks.

## 0.3.0 (2026-10-21)

- Job-level classification: `state.py new ... --class synthetic|public|internal` (required). An input may not exceed its job's class; a child or continued job may not drop below its parent's or source job's class.
- Internal jobs live entirely under `private/jobs/<job>/` (brief, state, run log, drafts, reviews, gates, delivery, inputs); their gate-audit entries go to `private/logs/gate-audit.jsonl`, never the tracked audit log.
- `state.py check-private <job>`: lists every file Git would track whose path or content names an internal job, and flags a job folder Git does not ignore.
- Jobs are found by their `state.json`, so a stray folder of the same name never redirects a job; state in both homes is refused.
- Script placeholder `{job_path}` (the repo-relative job folder), for scripts that must work for internal jobs.

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
