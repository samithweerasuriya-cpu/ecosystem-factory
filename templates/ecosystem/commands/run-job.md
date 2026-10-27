---
description: Run a job until it reaches GATE, DONE, BLOCKED or ESCALATED. Usage: /run-job <job_id>
---
Run job $ARGUMENTS using the job loop in CLAUDE.md section 3.

- `.venv\Scripts\python.exe engine\state.py activate $ARGUMENTS` first.
- Loop: status, act, record the transition. Re-read status before every step.
- Run every agent through `engine\agent_call.py job`; never as an in-session subagent.
- Validate every findings file with `engine\validate_findings.py <file>` before recording a review event; invalid: re-ask the reviewer once, then `infra_error`.
- Stop at GATE, DONE, CANCELLED, BLOCKED or ESCALATED, or on exit code 3, and report using CLAUDE.md section 6.
- Never run engine/gate.py. Never edit state or gate files.
