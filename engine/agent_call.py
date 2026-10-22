#!/usr/bin/env python3
"""Headless agent calls (stdlib only): the one way the engine runs an agent.

Used by the evaluation runner now and by the job loop from T1.5 (in-session subagents can't run while
a job is active: the hook refuses them, T0.12). One call = one `claude -p` run:

  claude -p --output-format json --no-session-persistence --strict-mcp-config
         --setting-sources project,local --model <pinned> --system-prompt-file <instructions>
         --tools=<the agent's tools>           (prompt on stdin)

- Agent file: Markdown with front matter (name, tools, model) and the instructions as the body.
  `model` absent or "inherit" means the pinned model in config/models.json ("default").
- No tools: the run folder is a fresh empty temporary folder and the run uses --safe-mode, so no
  CLAUDE.md, skill, plugin, hook or MCP server reaches the agent (T0.13 probes T13-1, T13-5).
  The inputs go inline in the prompt.
- Tools: the run folder must be given (`workspace`) and must hold .claude/settings.json with a
  PreToolUse guard hook registered; otherwise the call is refused. No safe mode (it disables hooks).
  The tools are passed to --tools and --allowedTools. Live-tested in T2.5.
- ANTHROPIC_API_KEY is removed from the child's environment, so the run stays on the subscription.
- The result: status "done" (JSON parsed, not an error), "failed" (the agent reported an error) or
  "infra_error" (no JSON, non-zero exit, timeout, could not start); the answer text; usage in the
  engine's format (lc.usage_from_tokens), taken from the JSON; the model(s) the JSON names.
Job calls (call_job): handoff built by script, call recorded, run, call closed with the JSON's usage
(usage_source "headless"); an infra_error closes the call as failed.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import labcore as lc

DEFAULT_TIMEOUT = 600
CHARS_PER_TOKEN = 4
BASE_OVERHEAD_TOKENS = 1500   # what a trivial tool-less run cost in the T0.13 probes (about 950-1550)
OUTPUT_ALLOWANCE_TOKENS = 2500


class AgentFileError(lc.LabError):
    pass


# ---------- agent files and config ----------

def parse_agent(path):
    """{name, tools: [..], model, body, path, sha256} from an agent file. Front matter is the block
    between the first two '---' lines; only simple `key: value` lines are read."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AgentFileError(f"{lc.rel(path)}: no front matter")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise AgentFileError(f"{lc.rel(path)}: front matter is not closed") from None
    meta = {}
    for ln in lines[1:end]:
        if ":" in ln and not ln.startswith((" ", "\t", "-")):
            k, v = ln.split(":", 1)
            meta[k.strip()] = v.strip()
    if not meta.get("name"):
        raise AgentFileError(f"{lc.rel(path)}: front matter has no name")
    raw = meta.get("tools", "").strip().strip("[]")
    tools = [t.strip().strip("\"'") for t in raw.split(",") if t.strip().strip("\"'")]
    if "Agent" in tools or "Task" in tools:
        raise AgentFileError(f"{lc.rel(path)}: agents may not have the Agent or Task tool (only the main session delegates)")
    body = "\n".join(lines[end + 1:]).strip() + "\n"
    return {"name": meta["name"], "tools": tools, "model": meta.get("model") or None, "body": body,
            "path": lc.rel(path), "sha256": lc.sha256_path(path)}


def models_config():
    f = lc.CONFIG / "models.json"
    return lc.load_json(f) if f.exists() else {}


def pinned_model():
    m = models_config().get("default")
    if not (isinstance(m, str) and m.strip()):
        raise lc.LabError("no pinned model: set \"default\" in config/models.json")
    return m.strip()


def agent_model(agent):
    m = agent.get("model")
    return pinned_model() if not m or m == "inherit" else m


def claude_command():
    """The CLI as an argv prefix (config/models.json "claude_command", default ["claude"])."""
    cmd = models_config().get("claude_command") or ["claude"]
    if not (isinstance(cmd, list) and cmd and all(isinstance(c, str) and c for c in cmd)):
        raise lc.LabError("config/models.json claude_command must be a non-empty list of strings")
    return cmd


def cli_version(cmd=None):
    """`claude --version` output, e.g. '2.1.308 (Claude Code)', or None if it can't run."""
    try:
        p = subprocess.run([*(cmd or claude_command()), "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, env=child_env())
        return (p.stdout.strip() or None) if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def child_env():
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def estimate(agent, prompt):
    """Rough token and time estimate for one call (before running it)."""
    tokens = (len(agent["body"]) + len(prompt)) // CHARS_PER_TOKEN + BASE_OVERHEAD_TOKENS + OUTPUT_ALLOWANCE_TOKENS
    return {"tokens": tokens, "seconds": 20 + tokens // 200}


# ---------- one call ----------

def guarded_workspace(workspace):
    """True if the folder's .claude/settings.json registers a PreToolUse command hook."""
    f = Path(workspace) / ".claude" / "settings.json"
    try:
        hooks = lc.load_json(f).get("hooks", {}).get("PreToolUse", [])
    except (OSError, ValueError, AttributeError):
        return False
    return any(h.get("type") == "command" and h.get("command") for entry in hooks if isinstance(entry, dict)
               for h in entry.get("hooks", []) if isinstance(h, dict))


def build_argv(agent, model, prompt_file_dir, cmd=None):
    sp = Path(prompt_file_dir) / "instructions.md"
    sp.write_text(agent["body"], encoding="utf-8")
    argv = [*(cmd or claude_command()), "-p", "--output-format", "json", "--no-session-persistence",
            "--strict-mcp-config", "--setting-sources", "project,local", "--model", model,
            "--system-prompt-file", str(sp), "--tools=" + ",".join(agent["tools"])]
    if agent["tools"]:
        argv += ["--allowedTools", ",".join(agent["tools"])]
    else:
        argv.append("--safe-mode")
    return argv


def parse_output(stdout):
    """The headless JSON result, or None."""
    s = (stdout or "").strip()
    if not s:
        return None
    try:
        d = json.loads(s)
    except ValueError:
        start = s.rfind("\n{")
        try:
            d = json.loads(s[start + 1:]) if start >= 0 else None
        except ValueError:
            return None
    return d if isinstance(d, dict) and d.get("type") == "result" else None


def call(agent, prompt, workspace=None, timeout=DEFAULT_TIMEOUT, cmd=None):
    """Run one agent once. `agent` is parse_agent()'s dict. Returns a result dict (see module doc)."""
    if agent["tools"]:
        if workspace is None or not guarded_workspace(workspace):
            raise lc.LabError(f"agent {agent['name']} has tools {agent['tools']}: it runs only in a workspace "
                              "whose .claude/settings.json registers the guard hook")
    model = agent_model(agent)
    with tempfile.TemporaryDirectory(prefix="agentcall-") as tmp:
        tmp = Path(tmp)
        (tmp / "prompt").mkdir()
        run_dir = Path(workspace) if agent["tools"] else tmp / "run"
        run_dir.mkdir(exist_ok=True)
        argv = build_argv(agent, model, tmp / "prompt", cmd)
        base = {"agent": agent["name"], "agent_sha256": agent["sha256"], "model_requested": model}
        try:
            p = subprocess.run(argv, input=prompt, cwd=run_dir, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, env=child_env())
        except subprocess.TimeoutExpired:
            return {**base, "status": "infra_error", "error": f"timed out after {timeout}s", "text": None,
                    "usage": None, "models": []}
        except OSError as e:
            return {**base, "status": "infra_error", "error": f"could not start the CLI ({e})", "text": None,
                    "usage": None, "models": []}
    d = parse_output(p.stdout)
    if d is None or p.returncode != 0:
        why = "no JSON result" if d is None else f"exit code {p.returncode}"
        return {**base, "status": "infra_error", "error": why + (f": {p.stderr.strip()[:300]}" if p.stderr.strip() else ""),
                "text": (d or {}).get("result"), "usage": usage_of(d) if d else None, "models": models_of(d) if d else []}
    status = "failed" if d.get("is_error") else "done"
    stats = d.get("subagent_stats") or {}
    out = {**base, "status": status, "error": d.get("subtype") if status == "failed" else None,
           "text": d.get("result"), "usage": usage_of(d), "models": models_of(d), "turns": d.get("num_turns"),
           "subagents_spawned": stats.get("spawned", 0)}
    if out["subagents_spawned"]:
        out.update(status="failed", error=f"the agent started {out['subagents_spawned']} subagent(s)")
    return out


def models_of(d):
    return sorted((d.get("modelUsage") or {}).keys())


def usage_of(d):
    models = models_of(d)
    return lc.usage_from_tokens(d.get("usage"), duration_ms=d.get("duration_ms"),
                                model=models[0] if len(models) == 1 else (", ".join(models) or None),
                                cost_usd=d.get("total_cost_usd"))


# ---------- job calls ----------

def inline_inputs(h):
    """The handoff's input files, appended for an agent without tools (it can't open paths)."""
    parts = []
    for i in h["inputs"]:
        p = lc.ROOT / i["path"]
        files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else ([p] if p.is_file() else [])
        for f in files:
            parts.append(f"=== {i['label']}: {lc.rel(f)} ===\n{f.read_text(encoding='utf-8', errors='replace')}")
        if not files:
            parts.append(f"=== {i['label']}: {i['path']} === (missing)")
    return "\n\n".join(parts)


def call_job(job_id, agent_file, item=None, workspace=None, timeout=DEFAULT_TIMEOUT, cmd=None):
    """One job step: handoff, record the call, run headless, close the call with the JSON's usage."""
    agent = parse_agent(agent_file)
    h, text = lc.handoff(job_id, item)
    if h["stage"] != agent["name"]:
        raise lc.LabError(f"{job_id} is waiting on {h['stage']!r}, not {agent['name']!r}")
    prompt = text if agent["tools"] else text + "\nINPUT FILE CONTENTS (you have no tools; everything is here):\n\n" + inline_inputs(h)
    st = lc.record_call(job_id, agent["name"], item)
    cid = st["calls"][-1]["id"]
    res = call(agent, prompt, workspace=workspace, timeout=timeout, cmd=cmd)
    closed = "done" if res["status"] == "done" else "failed"
    _, over = lc.record_result(job_id, cid, closed, usage=res["usage"], source="headless" if res["usage"] else "manual",
                               note=res.get("error"))
    return {**res, "call": cid, "handoff": h, "ceiling": over}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Run one agent headless (evaluation runs and job steps).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("job", help="run the job's current agent step")
    j.add_argument("job")
    j.add_argument("agent_file")
    j.add_argument("--item")
    sub.add_parser("version", help="print the pinned model and the CLI version")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "version":
            print(f"model {pinned_model()}  cli {cli_version()}")
            return 0
        r = call_job(args.job, args.agent_file, item=args.item)
        u = r["usage"] or {}
        print(f"{r['call']}: {r['status']}  tokens={u.get('total')}  model={', '.join(r['models']) or '?'}"
              + (f"  ({r['error']})" if r.get("error") else ""))
        return 0 if r["status"] == "done" else 1
    except lc.LabError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
