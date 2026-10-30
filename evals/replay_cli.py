#!/usr/bin/env python3
"""Replay CLI for charter evaluation cases (T2.5; evals/jobsim.py): stands in for `claude -p --output-format json`
for one recorded interviewer answer, so a charter case's job reaches the charter-writer with no model call.

  python evals/replay_cli.py <answer file> <the CLI arguments agent_call adds>

Prints the answer file's text as the result, with {{JOB}} replaced by the JOB line of the prompt (a case is
authored before its job ID exists) and zero tokens. It reads no other file and calls nothing.
"""
import json
import re
import sys
from pathlib import Path

if __name__ == "__main__":
    prompt = sys.stdin.read()
    m = re.search(r"(?m)^JOB: (\S+)", prompt)
    text = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
    if m:
        text = text.replace("{{JOB}}", m.group(1))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": text, "num_turns": 1,
                      "duration_ms": 0, "stop_reason": "end_turn", "total_cost_usd": 0.0,
                      "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                                "cache_creation_input_tokens": 0},
                      "modelUsage": {"replay": {"inputTokens": 0, "outputTokens": 0}}}))
