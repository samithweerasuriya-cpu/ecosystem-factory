# Engine changelog

## 0.14.0 (2026-10-28)

First real job (T1.4): evaluations to thresholds, a weaker-model check, then one job through the gate.

- Job handoffs carry the rules inline: a tool-less agent got its rulebook only as a path it could not open, so the first real critic reviewed without it. `agent_call.inline_inputs` now pastes every RULES file; a missing one stops the call, and a reviewer call whose handoff lacks its rulebook is refused. The author's draft and revise steps get the route's reviewer rulebooks too, as in its evaluations (`labcore.author_rules`).
- Reserved rule DR07 (instruction-like text in the material under review, minor) from `rules/default-agent-rules.md`, added to every generated rulebook; blueprint rule IDs starting `DR` are refused; every injection case expects DR07 and no other case may. A reviewer's verdict is fail if and only if it has a blocker or major finding (`validate_findings`).
- The generator writes the blueprint's rulebook `definitions` under the rule table and a "Severity by rule" line into every reviewer; it sets each new ecosystem's Git identity from the factory's repo-local noreply address (refused without one).
- `tools: []` counts only on the CLI version it was verified on (`config/doctor.json` `empty_tools_verified_cli`; still null: the T1.4 probe failed); the generator refuses tool-less agents on another version and the doctor warns.
- `run_evals.py --discrimination`: one run per case on `config/models.json` `discrimination_model`, after a check call proves the CLI runs exactly that model; the lock rule never reads these reports. Reports are never overwritten.
- Usage ceiling set from the job's measured figures (factory 350,000 tokens, 20 agent minutes, 20,000 per call).

## 0.13.0 (2026-10-27)

Headless answers saved and checked by script (T1.3 follow-up; pulled forward from T1.5).

- `agent_call.call_job`: the answer must be one bare JSON object (first character `{`, last `}`), not empty or cut off, valid against the agent's schema in the new `config/outputs.json` (reviewers: also the severity lock and the verdict rule), with the job ID (reviewers: reviewer, artifact path and version) copied exactly. A valid answer is saved as a new file (drafts: the next version after the one in state.json; reviews: `<agent>-<version>-<call>.json`; never over an existing file) and its sha256 goes on the call record. An invalid one is kept in `<job>/rejected/` (audit only), recorded as a repair and asked again once with only sanitized problems (path, rule, value cut to 40 characters, control characters removed); invalid again is an infra_error, as is any CLI failure (the script records the event itself; the ecosystem's CLAUDE.md template says so). A `STATUS: needs_input` answer is an infra_error at once (until T1.5). An agent without an output schema is never called.
- `labcore.verify_outputs`: every saved answer is re-hashed before `artifact_ready`, every handoff, the gate brief (`gate.py show`, approve, reject, hold) and the gate approval; a changed or missing file is refused.
- Headless handoffs end "Reply with only the JSON object"; in-session ones keep the STATUS block.
- `schemacheck.details`: the same errors as `check`, as (path, rule, value, message).
- `run_tests.py` closes keyboard input for itself and every process it starts.
- The generator renders `config/outputs.json` from the blueprint.

## 0.12.0 (2026-10-27)

Generator v0 (T1.3).

- `engine/generate.py generate <blueprint> <target> [--dry-run] | verify <target> | lint <target>`: copies `engine/` (except `check_coverage.py` and `designcheck.py`), the evaluation runner, the engine's schemas, rulebooks and config byte for byte; fixed templates from `templates/ecosystem/` (settings with `disableClaudeAiConnectors: true` and the Agent and Task tools denied, commands, `.gitignore`); renders config, the rulebook, `CLAUDE.md` and every agent file's front matter from the blueprint; `rules/default-agent-rules.md` word for word in `CLAUDE.md` and every agent; `generation.json` holds the manifest, the exclusions, every agent's headless call line and the venv's versions; then the ecosystem's `.venv` (uv, jsonschema at the factory's version) and `git init`. Lint: allowed front matter keys, explicit tool lists (`[]` for none, never empty or unreadable), no Agent or Task, `maxTurns` 1–20, the guard hook block, the default rules byte for byte; `tools: []` needs the in-session deny until T1.4 verifies it.
- Hook tuning H1–H3 (`docs/lessons.md`): a bare PowerShell string separator is read-only; "eval" inside the single literal `-m` message of a lone `git commit`; only the file name `gate.py` itself is human-only. Pins updated.
- Tests: `test_design_t12` moved to the factory's `tests/`; `test_evals_t13` uses its own calibration fixture (`engine/tests/fixtures/calibration/`), so the engine's tests pass inside a generated ecosystem.

## 0.11.0 (2026-10-27)

Thin charter and blueprint (T1.2).

- `schemas/charter.v0` and `schemas/blueprint.v0` (description + JSON Schema); `engine/designcheck.py charter|blueprint <file>`: schema plus hand checks (rulebook severities equal the charter's, caps no higher than the factory's, no connectors, suites meet minimum counts and the suite design rules).
- `evals/run_evals.py`: list agents (kind `agent`) scored against expected items (recall, field accuracy, invented and duplicate items); reviewer findings bound to the planted location when a key has `locations`, other findings reported as false findings. New `agent` thresholds in `evals/thresholds.json`.

## 0.10.1 (2026-10-26)

Phase 0 retrospective (T0.20).

- Severity-error rate: at marking, a valid finding may get a corrected severity (`v major`); it is stored with the mark (the ID-only log gets the corrected severity, never text); `state.py quality` reports under-rated and over-rated findings apart from noise and misses, and shows k of n beside every rate.
- Doctor: a warning re-acknowledged after a lapse now sticks (the fingerprint uses the check's own message).

## 0.10.0 (2026-10-26)

Gate modes, gate review support and publish readiness (T0.15, T0.16, T0.19).

- Gates accept only `human` mode until Phase 5; a missing mode is refused.
- `engine/gatereview.py` and `gate.py`: script-written gate brief, saved and fingerprinted at approve, reject and hold; one letter per finding marking with a seeded minor sample; missed issues; verdict files in `gates/`; an ID-only verdict log; `state.py quality` (noise and miss rates). Rejection feedback is read only from `gates/`. `gate.py hold` and `resume`; `approve --as pilot`.
- `engine/publish_check.py`: denylist (whole word, any case; `case:` for exact), secrets, source-folder and home paths, email domains, forbidden paths and names; tree, staged, message, push and history modes; `install` writes the pre-commit, commit-msg and pre-push hooks. Fails closed.
- `state.py stage-record <job>` (`engine/stagerecord.py`): stages one job's folder and only its log lines, after the publish check.
- Doctor: publish-hook check.

## 0.9.0 (2026-10-22)

Doctor (T0.14).

- `engine/doctor.py`: fast checks with no Claude calls (tools, logins, API key, auto-updates, hooks and their pins, registration, user-level and stray files, local config, evaluations, mode, layout), optional `--wsl`, and `--deep` (one live headless call, cost shown and confirmed first). Every failure has a Fix line. Home shown as `~`; no user name, email or organisation; settings and env key names only. Acknowledged warnings in the untracked `config/doctor.local.json` lapse when their details change.
- `engine/hooks/PINS.json`: pinned fingerprints of both launchers and both hooks; a test fails when a hook file and its pin differ.
- `gate.py lock` refuses on any doctor FAIL.
- `config/doctor.json`: minimum CLI and Python versions.

## 0.8.0 (2026-10-22)

Headless agent calls and evaluations (T0.13).

- `engine/agent_call.py`: the one way to run an agent. `claude -p` with the agent's instructions as a system prompt file, the prompt on stdin, the pinned model (`config/models.json`, unless the agent file names another), project-only settings, no MCP, usage from the JSON. A tool-less agent runs in a fresh empty folder in safe mode, so no CLAUDE.md reaches it; an agent with tools runs only in a folder whose settings register the guard hook. `ANTHROPIC_API_KEY` is removed from the child's environment. `call_job` builds the handoff, records the call and closes it with the headless usage; the job loop uses it from T1.5.
- `evals/run_evals.py`: leak check, cost estimate (the approver confirms above 1,000,000 tokens in their own terminal), token ceiling and call cap, cache by agent, prompt, model and CLI version, quick (1 run), full (3 runs) and smoke (one case, 3 fresh runs) modes, scoring by case majority, invalid-output rate reported separately, reports with numbers and IDs only.
- `engine/evalcheck.py` and `gate.py lock`: lock is refused unless passing reports cover every agent, rule, schema and config file at its current hash, for the pinned model and the installed CLI; minimum case counts for agents used by routes.
- `gate.py lock` checks the approver name before anything changes (a lock without one used to switch operate mode on, unaudited).
- The usage hook records a background subagent launch as "usage pending" and leaves its call open.
- The hook treats `engine/agent_call.py` and `evals/run_evals.py` like the other engine tools.

## 0.7.1 (2026-10-22)

Fixes from the live drills (T0.12).

- The approver's name is required in `config/gates.json`; without it every gate action is refused. There is no fallback to the operating-system user name, and the audit log no longer records it.
- Hook rule 7: while a job is active (not DONE or CANCELLED), a subagent call (Agent, Task) is refused unless it sets `run_in_background` to false. A background call returns before the subagent finishes, so the usage hook sees no figures (drill 11: 0 recorded against 46,923 used).

## 0.7.0 (2026-10-22)

Approval chain.

- A gate token records what its artifact was built from: the parent's approved artifact content (`requires_parent_gate`), the approved job a `--continue-from` seed came from, every approved artifact it cites as `[G:<job>]`, and the inputs present at approval.
- `verify_chain`: the token's own artifact, each recorded input (edited or deleted voids; a new one does not), each upstream approval by content (an identical re-approval keeps children valid; different content stops them), recursively; depth capped at 8; cycles broken. Used where it matters: child creation, approval, delivery, completion, gated actions and `[G:]` citations in the evidence check.
- `gate.py verify <job> <gate> --chain` prints every link; `gate.py show` lists what an approval would bind; `gate.py relink <job>` (human-only, terminal, audited) points a stopped child at its parent's new approval, voids the child's own approval and sends it back to its first review.
- Folder hashing is deterministic: sorted relative paths and file contents only.
- `.gitattributes`: fingerprinted folders (`jobs/`, `engine/`, `config/`, `schemas/`, `rules/`, `templates/`) never have line endings converted.

## 0.6.1 (2026-10-21)

Fixes found by the delivery path test (T0.10).

- `deliver` and `complete` re-check the gate token: an edit to the approved artifact after approval blocks delivery and completion.
- `gate.py`: the terminal check asks the Windows console directly (GetConsoleMode); `isatty()` alone is also true for the NUL device. Closed input is refused cleanly. No flag or environment variable skips the check.
- A retry call links to a freshly built handoff when there is one (so the post hook can match it), and to its original's otherwise.
- The call caps refuse a call before recording it, so a refused call never stays open.
- `engine/tests/demo_delivery.py`: watch a demo job go from NEW to DONE in a temporary copy.

## 0.6.0 (2026-10-21)

Evidence module.

- `engine/evidence.py`: `fetch` (inside an open agent call, by handoff id; http(s) only; private and local addresses refused, re-checked after every redirect; at most 5 redirects; size cap, timeout, a clear user-agent and a pause between requests to the same host; capped by `fetches_per_call` and `fetches_per_job`), `register` (files only from the job's `inputs/` or `sources/`), `list`, `check`, `refetch`, `show`.
- Page text in an untracked cache (`cache/evidence/`; internal jobs: their own `private/jobs/<job>/evidence/cache/`); the tracked registry, fetch log and quote index hold only URL, fetch time, fingerprint, rank, status and the short quotes cited. Only the script writes the store (hook-protected).
- Ranks come from the domain and file tables in `config/evidence.json` (empty by default; each ecosystem's source policy fills them); unlisted sources are rank 5.
- Pages built by JavaScript, non-text content and PDFs without the markitdown CLI are stored as unfetchable and cannot back a fact.
- Claim types: `[S:...]` backs a fact (rank 4 or better); `[A:...]` and `[G:<job>]` back a decision (the approver's answers, an approved artifact) and never a fact.
- The mechanical check (E01-E06, `rules/check-evidence.md`) runs on every new artifact version after the reference check; failures go back to the author as `check-evidence` findings. Uncited sentences with numbers, links or quotes are listed for the Verifier. `rules/verifier-default.md` holds the judgement rules.
- `engine/registry_check.py` ported over the evidence store.

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
