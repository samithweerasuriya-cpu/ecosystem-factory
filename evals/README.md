# Evaluations

Evaluations prove that an agent does its job before operate mode is locked: reviewers must catch planted problems and pass clean work. Built in T0.13; the case format and thresholds table are ported from the author's earlier private lab.

## Layout

```
evals/
  agents/<agent>.md               evaluation-only agents (not used by any route), e.g. the calibration critic
  <suite>/suite.json              {"agent": <agent file>, "rulebook": <rulebook>, "kind": "reviewer"}
  <suite>/cases/<id>/case.json    {"id", "kind": "planted" | "clean", "inputs": [...], "artifact": ...}
  <suite>/cases/<id>/<inputs>     what the agent reviews (synthetic)
  <suite>/keys/<id>.json          the answer: must_find, must_not_find, verdict, leak_terms (never shown to agents)
  thresholds.json                 thresholds and minimum case counts (machine-readable)
  reports/<time>-<suite>-<mode>.json   one report per run (tracked; numbers and IDs only)
  run_evals.py                    the runner
```

Case IDs are opaque (`E001`, ...), so an ID never hints at the answer.

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

**Minimum case counts** apply only to agents used by a route (`config/routes.json`): a reviewer needs at least 20 cases, 5 of them clean; another agent at least 5. The calibration critic is used by no route: its 7 cases prove the mechanics (runner, leak check, scoring, lock rule), not a factory agent.

## Suite design rules

Every suite for an agent used by a route (T2.5, T3.5, and the suites the generator writes in T4.1) follows these rules. The calibration critic's 7 cases predate them: they prove the runner, not reviewer quality.

1. **Difficulty mix:** at least a third of the cases are subtle (the defect is easy to read past), and some cases carry 2 or 3 defects at once.
2. **Boundary pairs:** for each rule, a planted case and a near-miss clean twin that comes close to breaking the rule but doesn't.
3. **Scoring is bound to the defect:** a finding counts only if it targets the planted location; extra findings on a planted case count as false findings; near-miss twins carry `must_not_find` for their rule.
4. **Real length:** some cases are at the length of a real document, not a short excerpt.
5. **Discrimination check:** a new suite also runs once on a weaker model. If that model also scores 100%, the suite is too easy and gets harder cases before it can count.
6. **Evidence shown:** reports show k of n beside every rate, and mark any rule backed by fewer than 3 cases as "insufficient evidence".
7. **Gate misses become cases:** every missed issue or severity error marked at a gate becomes a new, neutral eval case for that reviewer's suite.
8. **Hard cases included:** injection cases (instructions hidden in the material under review) and context-dependent severity cases (the same defect is minor in one setting and major in another).

## Lock rule

`engine/gate.py lock` refuses unless (see `engine/evalcheck.py`):

1. every agent file in `.claude/agents/` has a suite;
2. every suite has a passing full report made with its current agent and rulebook files, the pinned model and the installed CLI version (a new model or CLI makes every report stale: recalibrate by re-running), and, for an agent used by a route, the report met the minimum case counts;
3. every framework file (`.claude/agents/`, `rules/`, `schemas/`, `config/`) has the hash recorded in a passing full or smoke report for the current model and CLI;
4. at least one such report exists.

A relock after a change re-runs the changed agents' suites in full and a smoke run for the rest. Quick runs and runs limited to some cases (`--cases`) never count.

## Regression rule

Any change to `.claude/agents/*`, `rules/*`, `config/*` or `schemas/*` needs a passing evaluation run before operate mode is re-locked. Never lower a threshold to make a run pass: report the failure instead.
