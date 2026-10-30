# Ecosystem Factory

Verified agent-system generation: an agent ecosystem that builds agent ecosystems. It interviews its owner about a problem, designs a fit-for-purpose ecosystem of agents, generates it on a fixed and tested engine, and proves it works before it goes live.

```
Interview → problem charter ─G0─► blueprint ─G1─► generated ecosystem + bootstrap check ─G2─► live
```

Every step between those gates is done by agents; every gate is a person approving the exact files, in their own terminal.

## Status

**Phases 0 and 1 have passed; Phase 2 (intake) is in progress.** A generated ecosystem has run a real job end to end: its agents met their evaluation thresholds, one human gate approved the result, and usage was measured. Phase 2 has its charter schema (v1); the interview agents come next. 520 automated tests pass (latest full run). See [docs/roadmap.md](docs/roadmap.md).

## What this is, and what it isn't

It **is** a factory for small, purpose-built agent systems: it interviews its owner about one problem, designs a few agents with their rules and gates, generates them on a fixed engine, and proves them with evaluations before they go live.

It **isn't** a dependency-graph tool or a general agent swarm. Each generated system is small, has a fixed route and hard caps, and is approved by a person at every gate.

## Scope and non-goals

- **Scope:** one user, on one local Windows machine, running Claude Code on a Claude subscription.
- **Not** a concurrent or hosted service: one job runs at a time, for one approver.
- **Not** enterprise isolation, multi-tenant security or compliance tooling.
- **Not** a multi-repository code generator: it generates small agent ecosystems, each in its own folder.

## How it was built

Samith, a product manager who does not write code, specified, reviewed and decided every step. Claude Code wrote, ran and tested all the code, one planned task at a time: plan, approval, build, a Check run in front of Samith, a build-log row, a commit. Mistakes found along the way are kept as lessons in [docs/lessons.md](docs/lessons.md). The engine and method are derived from the author's earlier private labs; the role catalogue credit is in [NOTICE.md](NOTICE.md).

## What makes it different

Five guarantees, each enforced by a script that can't be talked round, an agent where judgement is needed, and a person at a gate:

1. **Structured intake:** problems arrive as charters with a schema and a readiness score, not one-line goals.
2. **Calibrated reviewers:** every reviewer is evaluated on planted-defect and clean cases (3 runs per case, hidden answer keys, leak check) before it may be used.
3. **Claims checked against sources:** citations must resolve to pages fetched and stored by script, quotes must match verbatim, and source rank must fit the claim.
4. **Approvals tied to the exact files approved:** gate tokens bind content fingerprints and the approval chain; any later edit voids them.
5. **Evals before anything goes live:** operate mode can't be locked unless passing evaluation reports cover every agent, rule, schema and config file.

More in [docs/overview.md](docs/overview.md).

## Evidence so far

- 520 automated tests (unit and end-to-end), with a guard that proves no test touched the real logs or jobs, and a watchdog that stops any test that hangs.
- A first generated ecosystem that ran a real job end to end: evaluations to thresholds, one human gate, measured usage.
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
