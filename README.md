# Ecosystem Factory

An agent ecosystem that builds agent ecosystems. It interviews its owner about a problem, designs a fit-for-purpose ecosystem of agents, generates it on a fixed and tested engine, and proves it works before it goes live.

```
Interview → problem charter ─G0─► blueprint ─G1─► generated ecosystem + bootstrap check ─G2─► live
```

Every step between those gates is done by agents; every gate is a person approving the exact files, in their own terminal.

## Status

**Phase 0 (foundation) is nearly complete.** The engine, its guardrails and its measurement are built and tested; the factory's own agents come in Phases 2 to 4. See [docs/roadmap.md](docs/roadmap.md).

## How it was built

Samith, an ERP product manager who does not write code, specified, reviewed and decided every step. Claude Code wrote, ran and tested all the code, one planned task at a time: plan, approval, build, a Check run in front of Samith, a build-log row, a commit. Mistakes found along the way are kept as lessons in [docs/lessons.md](docs/lessons.md). The engine and method are derived from the author's earlier private labs; the role catalogue credit is in [NOTICE.md](NOTICE.md).

## What makes it different

Five guarantees, each enforced by a script that can't be talked round, an agent where judgement is needed, and a person at a gate:

1. **Structured intake:** problems arrive as charters with a schema and a readiness score, not one-line goals.
2. **Calibrated reviewers:** every reviewer is evaluated on planted-defect and clean cases (3 runs per case, hidden answer keys, leak check) before it may be used.
3. **Claims checked against sources:** citations must resolve to pages fetched and stored by script, quotes must match verbatim, and source rank must fit the claim.
4. **Approvals tied to the exact files approved:** gate tokens bind content fingerprints and the approval chain; any later edit voids them.
5. **Evals before anything goes live:** operate mode can't be locked unless passing evaluation reports cover every agent, rule, schema and config file.

More in [docs/overview.md](docs/overview.md).

## Evidence so far

- Over 370 automated tests (unit and end-to-end), with a guard that proves no test touched the real logs or jobs.
- Live drills of every guardrail in a real Claude Code session, including fail-closed behaviour when the hook itself is broken ([docs/drills.md](docs/drills.md)).
- Live evaluation runs of a calibration reviewer: every planted defect found, no false fails, no invalid output.
- A doctor that checks the whole setup before work starts ([docs/doctor.md](docs/doctor.md)).
- A first reviewer baseline from an earlier lab ([docs/baselines.md](docs/baselines.md)).

## Running it

Requirements: Windows with Python 3.13 (via `uv`) and the `py` launcher, Git, and Claude Code on a claude.ai subscription (no API key: every agent call stays on the subscription).

```
uv venv --python 3.13 .venv
uv pip install --python .venv jsonschema
.venv\Scripts\python.exe engine\doctor.py
.venv\Scripts\python.exe engine\run_tests.py --fast
.venv\Scripts\python.exe engine\publish_check.py install
```

Then open the folder in Claude Code (manual permission mode only). Gate actions (`engine/gate.py`) run only in your own terminal.

## Licence

MIT, see [LICENSE](LICENSE).
