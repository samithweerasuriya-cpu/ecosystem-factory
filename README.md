# Ecosystem Factory

An agent ecosystem that builds agent ecosystems. It interviews Samith about a problem, designs a fit-for-purpose ecosystem, generates it on a fixed and tested engine into `C:\ecosystems\<slug>`, and proves it works before go-live.

```
Interview → Problem charter ─G0─► Blueprint ─G1─► Generated ecosystem + bootstrap check ─G2─► live
```

## Status

**Draft plan for Samith's review. Nothing has been built yet.** The working plan lives in `private/plan/` and is never published; T0.19 writes the public README and docs.

## Read in this order

| File | What it holds |
|---|---|
| `private/plan/primer.md` | Purpose, architecture, where each part comes from, caveats, guardrails, decisions, open questions |
| `private/plan/BUILD_PLAN.md` | Phases 0–5, task by task, with owner, Check and estimate |
| `private/plan/reuse-map.md` | The source file in the three source folders that each factory component starts from |
| `private/plan/coverage-matrix.md` | Every finding from the Oct 21 review of the three source folders, mapped to the tasks that handle it |
| `CLAUDE.md` | Standing instructions Claude Code reads every session |
| `private/plan/build-log.md` | One row per task: result, estimate vs actual, notes |

## Getting started (after Samith approves the plan)

1. Open this folder in the Claude Code desktop app and accept the trust prompt.
2. Keep a separate terminal open: gate approvals (`gate.py`) need a real terminal.
3. Say: **"Execute private/plan/BUILD_PLAN.md from task T0.1."**
