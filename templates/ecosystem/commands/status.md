---
description: Show job status. Usage: /status [job_id]
---
Run `.venv\Scripts\python.exe engine\state.py status $ARGUMENTS`. Summarise per job: state, stage, artifact, revision count,
agent calls, usage against the ceiling, and what the approver needs to do next (if anything). If logs/blocked.jsonl has
entries from today, list them.
