"""Stand-in for the Claude Code CLI in tests (no live calls).

Records each call (argv, stdin, working folder and its files, the system prompt file's text, whether
ANTHROPIC_API_KEY was visible) to FAKE_CLAUDE_LOG, then answers like `claude -p --output-format json`.
FAKE_CLAUDE_MODE: ok (default) | error | nojson | exit3 | sleep | subagent.
FAKE_CLAUDE_RESPONSES: a JSON file of [[substring, result text or list of texts], ...]; the first
substring found in the prompt picks the answer (default "{}"); a list answers the first, second ...
call with that substring in turn (the last entry repeats).
FAKE_CLAUDE_STOP_REASON: the stop_reason the JSON reports (default end_turn), e.g. max_tokens.
FAKE_CLAUDE_MODEL_REPORTED: the model the JSON reports instead of the requested one.
"""
import json
import os
import sys
import time
from pathlib import Path

argv = sys.argv[1:]
if argv == ["--version"]:
    print(os.environ.get("FAKE_CLAUDE_VERSION", "9.9.9 (Claude Code)"))
    sys.exit(0)
prompt = sys.stdin.read()
sp = argv[argv.index("--system-prompt-file") + 1] if "--system-prompt-file" in argv else None
cwd = Path.cwd()
log = os.environ.get("FAKE_CLAUDE_LOG")
earlier = [json.loads(l)["stdin"] for l in Path(log).read_text(encoding="utf-8").splitlines()] \
    if log and Path(log).exists() else []
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"argv": argv, "stdin": prompt, "cwd": str(cwd),
                             "cwd_files": sorted(p.name for p in cwd.iterdir()),
                             "system_prompt": Path(sp).read_text(encoding="utf-8") if sp else None,
                             "api_key_visible": "ANTHROPIC_API_KEY" in os.environ}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if mode == "sleep":
    time.sleep(30)
if mode == "nojson":
    print("something went wrong")
    sys.exit(0)
text = "{}"
rf = os.environ.get("FAKE_CLAUDE_RESPONSES")
if rf:
    for needle, answer in json.loads(Path(rf).read_text(encoding="utf-8")):
        if needle in prompt:   # a list gives one answer per earlier call with the same needle (run 1, 2, 3)
            n = sum(1 for e in earlier if needle in e)
            text = answer[min(n, len(answer) - 1)] if isinstance(answer, list) else answer
            break
model = argv[argv.index("--model") + 1] if "--model" in argv else "unknown"
model = os.environ.get("FAKE_CLAUDE_MODEL_REPORTED", model)    # T1.4: a CLI that aliases the requested model
print(json.dumps({"type": "result", "subtype": "error_during_execution" if mode == "error" else "success",
                  "is_error": mode == "error", "result": text, "num_turns": 1, "duration_ms": 4953,
                  "stop_reason": os.environ.get("FAKE_CLAUDE_STOP_REASON", "end_turn"),
                  "total_cost_usd": 0.0114,
                  "usage": {"input_tokens": 2, "output_tokens": 325, "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 617},
                  "modelUsage": {model: {"inputTokens": 2, "outputTokens": 325}},
                  "subagent_stats": {"spawned": 1 if mode == "subagent" else 0}}))
sys.exit(3 if mode == "exit3" else 0)
