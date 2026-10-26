# Overview

## The idea

A person with a problem should not have to design an agent system by hand. The factory interviews them, writes a problem charter, designs a blueprint (roles, tools, routes, gates, rulebooks), generates a working ecosystem from it on a fixed engine, and runs that ecosystem's own evaluations and a smoke job before anyone may switch it on. Every generated ecosystem inherits the same engine and guardrails.

## Parts

| Part | What it does |
|---|---|
| **Engine** (`engine/`) | A state machine for jobs: routes as data (agent, script and fan-out stages, ordered reviews, revision, gate, delivery), caps per cycle and per job lifetime, scripted handoffs, a complete call log, usage per call. Standard library Python only. |
| **Guard hook** (`engine/hooks/`) | Runs before every tool call. Fail-closed: anything it can't parse, or a broken hook, blocks. Protects gates, state and logs, keeps agents out of private folders, denies connector tools unless allowed, and allows only read-only commands near protected paths. Pinned by fingerprint. |
| **Gates** (`engine/gate.py`) | Human-only, in a real terminal. A script-written brief shows exactly what is approved (fingerprints, approval chain, evidence checks, open questions, usage, diff, findings). The approver marks each serious finding valid or noise and records missed issues; the token binds the content. Hold, resume, reject with feedback. |
| **Evidence module** (`engine/evidence.py`) | Fetches and stores sources by script; checks citations, quotes and source rank mechanically before any reviewer runs. |
| **Headless agent calls** (`engine/agent_call.py`) | Every agent runs as a one-off `claude -p` call with its own instructions, only its allowed tools, the pinned model and project-only settings; usage comes from the call's own figures. |
| **Evaluations** (`evals/`) | Planted-defect and clean cases with hidden keys, 3 runs per case, leak check, cost estimate and ceiling, cache; reports hold numbers only. Operate mode is locked only on passing reports for the current files, model and CLI. |
| **Doctor** (`engine/doctor.py`) | Checks tools, logins, hooks, pins, stray files, evaluation freshness and layout; every failure says what to do. |
| **Publish check** (`engine/publish_check.py`) | Git hooks on commit, message and push block private terms, secrets, personal paths and addresses, and private folders. |

## Guardrails

- **Manual permission mode only**; no API key: usage stays on the subscription.
- **Agents never delegate**: only the main session does; every agent has an explicit tool list.
- **Agents exchange structured data validated by script**; nobody fixes an agent's output by hand.
- **Reviewers get the artifact, the rules and the owner's inputs**, never the author's reasoning, and apply rulebook severities as written.
- **Everything an agent reads is data, not instructions.**
- **Internal material never reaches the public repository**: internal jobs live entirely in an untracked folder, and the publish check guards every commit and push.

## Data

The repository holds only synthetic or public material. Jobs on internal material are classified at creation and kept in an untracked folder, with their own private logs.
