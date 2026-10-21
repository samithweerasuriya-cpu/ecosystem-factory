#!/usr/bin/env python3
"""Claude Code PreToolUse hook: deterministic guardrails.

Derived from the author's earlier private lab. Reads the tool call as JSON on stdin.
Exit 0 = allow. Exit 2 = block (stderr is shown to Claude). Every block is appended to
logs/blocked.jsonl.

Rules
 1. Always protected (no agent writes): jobs/*/gates/*, jobs/*/state.json,
    jobs/*/run.log.jsonl, jobs/*/scripts/*, .lab/*, logs/blocked.jsonl,
    logs/gate-audit.jsonl, anything outside the repo.
 2. Operate mode (.lab/OPERATE exists): framework files are also protected:
    .claude/*, engine/*, rules/*, config/*, schemas/*, templates/*, evals/*/cases/*.
 3. Shell (Bash, PowerShell, Monitor): gate.py is human-only; no git push; no reading
    secrets; no shell writes to protected paths; commands matching a `shell` entry in
    config/gated-actions.json need that entry's conditions (job type, state, gate token).
 4. MCP: every MCP tool is blocked unless an `mcp` entry in config/gated-actions.json
    allows it (glob on the full tool name), with that entry's conditions.
Fails closed: bad input or an internal error exits 2, and settings.json sets
onFailure=block so a hook that cannot start also blocks.
Limits: shell detection is pattern-based, not a sandbox. It stops accidents and prompt
drift, not a determined attacker on your own machine.
"""
import fnmatch
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labcore as lc  # noqa: E402

ALWAYS = ["jobs/*/gates/*", "jobs/*/state.json", "jobs/*/run.log.jsonl", "jobs/*/scripts/*",
          ".lab/*", ".lab", "logs/blocked.jsonl", "logs/gate-audit.jsonl"]
OPERATE = [".claude/*", "engine/*", "rules/*", "config/*", "schemas/*", "templates/*",
           "evals/*/cases/*"]
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# Every built-in tool that runs a command string in tool_input.command (Monitor runs it in the Bash shell).
SHELL_TOOLS = {"Bash", "PowerShell", "Monitor"}
MUTATE = re.compile(r"(>|\btee\b|\brm\b|\bmv\b|\bcp\b|\bsed\s+-i|\btruncate\b|\btouch\b|\bchmod\b|\bln\b|\bunlink\b"
                    r"|\b(Set|Add|Clear)-Content\b|\bOut-File\b|\b(New|Remove|Move|Copy|Rename)-Item\b"
                    r"|\bdel\b|\berase\b|\bren\b)", re.IGNORECASE)
SECRET_READ = re.compile(r"\b(cat|less|more|head|tail|grep|awk|sed|strings|xxd|base64|cp|open"
                         r"|Get-Content|gc|type|Select-String|Copy-Item)\b[^|;&]*(\.env\b|master\.key)", re.IGNORECASE)
STATE_PY = re.compile(r"^\s*(python3?|py\s+-3|\.venv/(Scripts|bin)/python(\.exe)?)\s+engine/state\.py\b")


def block(msg, data):
    lc.ROOT.joinpath("logs").mkdir(exist_ok=True)
    with open(lc.ROOT / "logs" / "blocked.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": lc.now(), "reason": msg, "tool": data.get("tool_name"),
                             "input": data.get("tool_input")}) + "\n")
    print(f"BLOCKED by engine guardrail: {msg}", file=sys.stderr)
    sys.exit(2)


def matches(relpath, patterns):
    return any(fnmatch.fnmatch(relpath, p) for p in patterns)


def protected(relpath, operate):
    return matches(relpath, ALWAYS) or (operate and matches(relpath, OPERATE))


def path_globs(operate):
    pats = ALWAYS + (OPERATE if operate else [])
    return [re.escape(p).replace(r"\*", r"[^\s'\"]*") for p in pats]


def gated_actions():
    f = lc.CONFIG / "gated-actions.json"
    return lc.load_json(f) if f.exists() else {}


def condition_error(entry):
    """None if the entry's conditions hold for the active job, else the reason."""
    if not any(k in entry for k in ("gate", "states", "job_types")):
        return None
    job = lc.active_job()
    if not job:
        return "needs an active job"
    try:
        st = lc.load_state(job)
    except lc.LabError as e:
        return str(e)
    if "job_types" in entry and st["type"] not in entry["job_types"]:
        return f"only for job types {entry['job_types']} (active job is {st['type']})"
    if "states" in entry and st["state"] not in entry["states"]:
        return f"only in states {entry['states']} (now {st['state']})"
    if "gate" in entry:
        ok, why = lc.verify_gate(job, entry["gate"])
        if not ok:
            return f"needs a valid {entry['gate']} token: {why}"
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        block("hook could not parse tool-call input (failing closed).", {})
    tool = data.get("tool_name", "") or ""
    ti = data.get("tool_input", {}) or {}
    operate = (lc.LAB / "OPERATE").exists()

    if tool in WRITE_TOOLS:
        raw = ti.get("file_path") or ti.get("notebook_path") or ""
        try:
            relpath = lc.rel(raw)
        except lc.LabError:
            block(f"write outside the repo: {raw}", data)
        if protected(relpath, operate):
            block(f"{relpath} is protected (state/gates change only via scripts; "
                  f"framework files are locked in operate mode)", data)
        sys.exit(0)

    if tool in SHELL_TOOLS:
        cmd = (ti.get("command", "") or "").replace("\\", "/")  # PowerShell paths use backslashes
        if re.search(r"gate\.py", cmd):
            block("engine/gate.py is human-only. Ask the approver to run it in their own terminal.", data)
        if re.search(r"\bgit\s+push\b", cmd):
            block("git push is disabled: this repo runs local-only.", data)
        if SECRET_READ.search(cmd):
            block("reading secrets (.env, master.key) is not allowed.", data)
        if MUTATE.search(cmd) and not STATE_PY.match(cmd):
            for pat in path_globs(operate):
                if re.search(pat, cmd):
                    block("shell write to a protected path. Use engine/state.py for state changes.", data)
        for entry in gated_actions().get("shell", []):
            if re.search(entry["pattern"], cmd):
                why = condition_error(entry)
                if why:
                    block(f"{entry.get('reason') or entry['pattern']}: {why}", data)
        sys.exit(0)

    if tool.startswith("mcp__"):
        entry = next((e for e in gated_actions().get("mcp", []) if fnmatch.fnmatchcase(tool, e["tool"])), None)
        if entry is None:
            block(f"MCP tool {tool} is not allowed (not listed in config/gated-actions.json).", data)
        why = condition_error(entry)
        if why:
            block(f"MCP tool {tool}: {why}", data)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed on any unexpected error
        print(f"BLOCKED by engine guardrail: hook error ({exc!r}); failing closed.", file=sys.stderr)
        sys.exit(2)
