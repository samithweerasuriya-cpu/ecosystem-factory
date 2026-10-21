#!/usr/bin/env python3
"""Claude Code PostToolUse hook for subagent calls: records usage by script (stdlib only).

Registered through post_tool_use_launcher.py for the Agent tool. The subagent's prompt is the
scripted handoff, so it carries "JOB: <job>" and "HANDOFF: H<nnn>". The hook finds the open call
that used that handoff and closes it with the app's own figures from tool_response: status,
totalTokens, the token breakdown (input, output, cache read, cache write), totalDurationMs and
the model. A call it cannot match (no handoff in the prompt, unknown job, no open call) is
written to logs/usage-unmatched.jsonl (numbers and the reason only), never dropped.
run(raw) returns 0, or 2 to tell the session that usage could not be recorded.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labcore as lc  # noqa: E402

AGENT_TOOLS = {"Agent", "Task"}
JOB_RE = re.compile(r"^JOB:\s*(\d{8}-[a-z]+-[a-z0-9-]+)\b", re.MULTILINE)
HANDOFF_RE = re.compile(r"\bHANDOFF:\s*(H\d{3,})\b")


def unmatched(reason, data, usage, job_id=None):
    internal = bool(job_id) and lc.find_job(job_id) is not None and lc.is_internal(job_id)
    d = lc.ROOT / "private" / "logs" if internal else lc.ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    ti = data.get("tool_input") or {}
    with open(d / "usage-unmatched.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": lc.now(), "reason": reason, "job_id": job_id,
                             "subagent_type": ti.get("subagent_type"), "tool_use_id": data.get("tool_use_id"),
                             "tokens": usage}) + "\n")


def run(raw):
    data = json.loads(raw)
    if data.get("tool_name") not in AGENT_TOOLS:
        return 0
    ti, tr = data.get("tool_input") or {}, data.get("tool_response") or {}
    tr = tr if isinstance(tr, dict) else {}
    usage = lc.usage_from_tokens(tr.get("usage"), total=tr.get("totalTokens"), duration_ms=tr.get("totalDurationMs"),
                                 model=tr.get("resolvedModel"))
    prompt = str(ti.get("prompt") or "")
    job_m, hid_m = JOB_RE.search(prompt), HANDOFF_RE.search(prompt)
    if not (job_m and hid_m):
        unmatched("no JOB/HANDOFF lines in the subagent prompt", data, usage)
        return 0
    job_id, hid = job_m.group(1), hid_m.group(1)
    if lc.find_job(job_id) is None:
        unmatched(f"job {job_id} not found", data, usage, None)
        return 0
    call = lc.find_call_by_handoff(job_id, hid)
    if call is None:
        unmatched(f"no open call for handoff {hid}", data, usage, job_id)
        return 0
    status = "done" if str(tr.get("status", "completed")).lower() in ("completed", "done", "success") else "failed"
    _, over = lc.record_result(job_id, call["id"], status, usage=usage, source="post_tool_use")
    if over:
        print(f"Usage recorded for {call['id']}; {over}: the job is paused (ESCALATED).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.stdin.buffer.read().decode("utf-8", errors="replace")))
    except SystemExit:
        raise
    except BaseException as exc:
        print(f"usage hook error ({exc!r}); usage not recorded.", file=sys.stderr)
        sys.exit(2)
