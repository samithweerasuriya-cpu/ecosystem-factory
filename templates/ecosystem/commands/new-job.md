---
description: Create a new job. Usage: /new-job <slug> <goal...>
---
Create a job from: $ARGUMENTS

1. Parse the slug (lowercase-hyphens) and the goal. The job type is this ecosystem's route (`.venv\Scripts\python.exe engine\state.py routes`).
2. Run: `.venv\Scripts\python.exe engine\state.py new <route> <slug> "<goal>"`
3. Open `jobs/<job_id>/brief.md` and show it to the approver along with the route.
4. Ask at most one clarifying question if the goal is ambiguous. Do NOT edit brief.md yourself.
5. Stop. The approver starts the run with `/run-job <job_id>`.
