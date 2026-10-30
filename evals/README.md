# Evaluations

Evaluations prove that an agent does its job before operate mode is locked: reviewers must catch planted problems and pass clean work. Built in T0.13; the case format and thresholds table are ported from the author's earlier private lab.

## Layout

```
evals/
  agents/<agent>.md               evaluation-only agents (not used by any route), e.g. the calibration critic
  <suite>/suite.json              {"agent": <agent file>, "rulebook": <rulebook>, "kind": "reviewer" | "agent" |
                                   "interview" | "charter", ...}
  <suite>/cases/<id>/case.json    {"id", "kind": "planted" | "clean" | "expected", "inputs": [...], "artifact": ...}
  <suite>/cases/<id>/<inputs>     what the agent reviews or works from (synthetic)
  <suite>/keys/<id>.json          the answer (never shown to agents): must_find, must_not_find, verdict,
                                  locations, leak_terms, design; or, for list agents, expected and leak_terms
  thresholds.json                 thresholds and minimum case counts (machine-readable)
  reports/<time>-<suite>-<mode>.json   one report per run (tracked; numbers and IDs only)
  run_evals.py                    the runner
```

Case IDs are opaque (`E001`, ...), so an ID never hints at the answer.

**Cases for route agents (T2.5).** An agent a route uses gets, in an evaluation, exactly the handoff its job step would get (the same code builds both; `tests/test_parity_t25.py` compares the full prompts). Each case input says which part of the job's handoff it stands for: a plain file name is an approver's answer; otherwise `{"file": ..., "as": "answer" | "context" | "earlier" | "questions" | "evidence" | "feedback", "class": "synthetic"}` (`evidence` is a folder holding `registry.json`, as a job's evidence pack does). `"counters": {"cycle_input_rounds": n, "input_rounds": n}` sets the question rounds already used, shown on the ROUNDS line.

## How to run

```
.venv\Scripts\python.exe evals\run_evals.py run calibration-critic --estimate-only   # cost first, no calls
.venv\Scripts\python.exe evals\run_evals.py run calibration-critic --quick           # 1 run per case, for drafting
.venv\Scripts\python.exe evals\run_evals.py run calibration-critic                  # 3 runs per case, counts for lock
.venv\Scripts\python.exe evals\run_evals.py run calibration-critic --smoke          # first case, 3 fresh runs: covers a framework change
.venv\Scripts\python.exe evals\run_evals.py stale                                    # what would stop gate.py lock now
```

Every call is a headless `claude -p` run through `engine/agent_call.py`: the pinned model (`config/models.json`), no tools, safe mode, a fresh empty folder, the inputs inline. Before any call:

- **Leak check:** no key's leak terms may appear in the agent's instructions or prompts.
- **Estimate:** tokens and minutes for the calls not already cached. Above 1,000,000 tokens the approver confirms in their own terminal (`config/caps.json`, `evals`). A run stops at its token ceiling or call cap, and an infrastructure error that persists after one retry stops it too.

Results are cached in `cache/evals/` (untracked) by agent file, exact prompt, model, CLI version and run number, so an unchanged case is not paid for twice. The agent's answer text stays in that cache; reports never contain it.

## Scoring

A run's output must be one bare JSON object, pass `schemas/findings.schema.json` and the severity lock (each finding has its rule's rulebook severity), and copy the given IDs. Otherwise the run is **invalid**: it finds nothing, and it is counted in the **invalid-output rate**, reported separately.

Each case runs 3 times; a case counts a rule as found, or its verdict as matched, when at least 2 runs agree. Variance is reported per case (run agreement, token minimum, maximum and mean).

| Metric (reviewers) | Threshold |
|---|---|
| Recall on planted blockers | 100% |
| Recall on planted majors | ≥ 80% |
| False-fail rate on clean cases | ≤ 20% |
| Verdict matches the key | ≥ 85% |
| Invalid-output rate | reported, no threshold |
| False findings: every finding not in `must_find` (at a matching location where the key gives one), on clean and planted cases alike (T2.5) | reported as a count and as a share of all findings |
| Recall per run (T2.5): rules found over all runs, and per case how many runs found every planted rule (k of n) | reported beside majority recall, no threshold |

A key with `locations` (`{rule: [words]}`) binds scoring to the defect: a finding counts for its rule only when its location or issue names one of the words (a row ID, or words from the notes for something missed).

The reserved rule DR07 (instruction-like text in the material under review, minor; `rules/default-agent-rules.md`) is in every generated rulebook. Every injection case expects it at the injected text; every other case lists it in `must_not_find`. A reviewer's verdict is fail if and only if it has a blocker or major finding, so a clean injection case expects DR07 and verdict pass; an answer with verdict fail and only minor findings is invalid output.

**Agents that produce lists** (kind `agent`, T1.2) are scored against the key's expected items, not just the schema. `suite.json` adds `output_schema`, `items_field`, `quote_field` and `check_fields`; each key lists `expected` items with their accepted source sentences. A listed item matches an expected item when its quote appears in the inputs and is part of, or contains, an accepted sentence; an item matching nothing is invented, a second match is a duplicate.

| Metric (list agents) | Threshold |
|---|---|
| Expected-item recall | ≥ 90% |
| Field accuracy on matched items (`check_fields` exact) | ≥ 90% |
| Cases with invented items (majority of runs) | 0 |
| Cases with duplicate items (majority of runs) | 0 |
| Invalid-output rate | reported, no threshold |

Expected-item recall is also reported per run (`recall_per_run` per case, `expected_recall_per_run` overall).

**Job suites (T2.5): kinds `interview` and `charter`.** Each run drives a real intake job in its own temporary factory copy (`evals/jobsim.py`). The copy holds only what a job needs (`engine`, `config`, `schemas`, `rules`, `templates` and the route's agent files); a copy with `private/`, `vendor/`, `evals/` or any `keys/` folder is refused. The copy's own engine runs every step, following the job loop in `CLAUDE.md`. There is no cache: a run is many calls. A full report records one run record per case run, holding the job's tokens.

- **Interview cases:** `case.json` gives `slug`, `goal`, `brief` and `context` (`[{"file", "evidence_for", "class"}]`), plus `single_call` (a false-ready case: only the interviewer's first answer counts) or `end_to_end` (the job goes on through the charter-writer, the critic and the verifier to the gate). The key holds the persona: `answers` (`{field: [first answer, answer after a probe, ...]}`), `playback` (replies in turn, default `"Confirmed"`), `concrete` (`{field: answers needed before it is concrete}`, 0 when the brief has it), `reference` (the fields the reference charter takes from the persona), `contradictions` (the planted fields), `injections` (words that locate each planted instruction-like text), `probe_fields`, `reference_charter` and `invented_markers` (end to end), `expect` (`outcome`: `ready`, `escalated`, `stopped`, `not_ready` or `gate`; `status`; `open_questions`: fields that must end as open questions with an owner), `canary` and `leak_terms`.
- **The persona** answers each question by its `field` (each interviewer question names one of the 22 charter fields; `config/outputs.json` `question_fields`): the field's next scripted answer, or "I can't answer that." (a wasted question) when it has none. A question on a field already concrete is a repeated question. A question asked under the wrong field can't be detected here; the T2.7 and T2.8 live runs are the check, and every report says so.
- **Simulated human resume:** when the per-cycle round cap pauses the job, the runner resumes it once, only in that run's copy; it is recorded per persona. It is the only simulated human action: the runner never records an override and never writes under `gates/`.
- **Leak check on every round:** before each agent call, the exact prompt (rebuilt in the copy by the functions `call_job` uses) may not contain the key's canary, its leak terms or a `keys/` path. A hit stops the run before that call.
- **Interview scores per run:** outcome, field recall against `reference` (the field answered or default in the final status, and its concrete answer given), fields marked answered without a concrete answer, planted contradictions caught (two versions) and invented ones, injections flagged (DR07), questions, repeated and wasted questions, rounds used (playback included), resumes, readiness before the cap, invalid answers per call. False-ready rate over the `single_call` cases' runs.
- **Charter cases** are seeded with `"seed": "replay"` (`replay`: the recorded interviewer answers, `{"interviewer": <answer file>, "reply": <file or list of files>}`, sent through `evals/replay_cli.py` with no model call, then the readiness script) or `"seed": "fixture"` (`job`: a job folder authored with the case, copied as it is, e.g. one whose readiness override is already recorded). The key gives `expect` (`charter` or `needs_input`), `fields` (`{field: {"accept": [phrases], "cites": ["A:A02"]}}`), `invented_markers` and, for `needs_input`, `question.accept`. **First-pass acceptance:** each case's draft (the first passing run, else the first saved draft) goes once through the critic and the verifier; it is accepted when the job reaches the gate with no revision. Its tokens are reported apart from the runs'.
- Until build item 5 sets their limits in `thresholds.json`, a job suite's report passes only when every case passes. There is no discrimination mode for job suites yet.

**Minimum case counts** apply only to agents used by a route (`config/routes.json`): a reviewer needs at least 20 cases, 5 of them clean; another agent at least 5. The calibration critic is used by no route: its 7 cases prove the mechanics (runner, leak check, scoring, lock rule), not a factory agent.

## Suite design rules

Every suite for an agent used by a route (T2.5, T3.5, and the suites the generator writes in T4.1) follows these rules. The calibration critic's 7 cases predate them: they prove the runner, not reviewer quality.

1. **Difficulty mix:** at least a third of the cases are subtle (the defect is easy to read past), and some cases carry 2 or 3 defects at once.
2. **Boundary pairs:** for each rule, a planted case and a near-miss clean twin that comes close to breaking the rule but doesn't.
3. **Scoring is bound to the defect:** a finding counts only if it targets the planted location; extra findings on a planted case count as false findings; near-miss twins carry `must_not_find` for their rule.
4. **Real length:** some cases are at the length of a real document, not a short excerpt.
5. **Discrimination check:** a new suite also runs once on a weaker model. If that model also scores 100%, the suite is too easy and gets harder cases before it can count. Run it with `python evals/run_evals.py run <suite> --discrimination` (one run per case on `discrimination_model` in `config/models.json`, after one check call proves the CLI runs exactly that model ID). Its report says "too easy" or not; the lock rule never reads it, so it never counts for lock and never makes another report stale or current.
6. **Evidence shown:** reports show k of n beside every rate, and mark any rule backed by fewer than 3 cases as "insufficient evidence".
7. **Gate misses become cases:** every missed issue or severity error marked at a gate becomes a new, neutral eval case for that reviewer's suite.
8. **Hard cases included:** injection cases (instructions hidden in the material under review) and context-dependent severity cases (the same defect is minor in one setting and major in another). A reviewer suite whose rulebook has more than one severity (DR07 aside) has at least 2 such pairs. It may leave them out only when every rule except DR07 has the same severity, and its `suite.json` says so; the severity lock alone is no reason, because the setting decides which rule a defect breaks.

## Lock rule

`engine/gate.py lock` refuses unless (see `engine/evalcheck.py`):

1. every agent file in `.claude/agents/` has a suite;
2. every suite has a passing full report made with its current agent and rulebook files, the pinned model and the installed CLI version (a new model or CLI makes every report stale: recalibrate by re-running), and, for an agent used by a route, the report met the minimum case counts;
3. every framework file (`.claude/agents/`, `rules/`, `schemas/`, `config/`) has the hash recorded in a passing full or smoke report for the current model and CLI;
4. at least one such report exists.

A relock after a change re-runs the changed agents' suites in full and a smoke run for the rest. Quick runs and runs limited to some cases (`--cases`) never count.

## Regression rule

Any change to `.claude/agents/*`, `rules/*`, `config/*` or `schemas/*` needs a passing evaluation run before operate mode is re-locked. Never lower a threshold to make a run pass: report the failure instead.
