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
Job calls (call_job): handoff built by script (ending "Reply with only the JSON object"), call recorded,
run, call closed with the JSON's usage (usage_source "headless"); an infra_error closes the call as failed and
the script records the infra_error event itself.
The answer (T1.3 follow-up) is checked before any state event: one bare JSON object (first character {,
last }), not empty or cut off, valid against the agent's schema in config/outputs.json (reviewers: also the
severity lock and the verdict rule), with the job ID (reviewers: also reviewer, artifact path and version)
copied exactly from the handoff. A valid answer is saved by the script as a new file in the stage's output
folder (drafts: the next version after the one in state.json; never overwritten) and its sha256 goes on the
call record; labcore.verify_outputs re-checks it before every later use. An invalid answer is kept in
<job>/rejected/<call>.txt (audit only, never a handoff input), recorded as a repair (invalid_output) and
asked again once, with only the sanitized problem list (path, rule, value cut to 40 characters, control
characters removed). Invalid again: infra_error. A STATUS: needs_input answer is an infra_error at once
(not supported headless until T1.5). The main session never repairs an answer.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import labcore as lc
import schemacheck
import validate_findings as vf

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
           "stop_reason": d.get("stop_reason"), "subagents_spawned": stats.get("spawned", 0)}
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


NEEDS_INPUT = re.compile(r"(?mi)^\s*STATUS:\s*needs_input\b")
NEEDS_INPUT_NOTE = "needs_input not supported headless until T1.5"
# control and invisible formatting characters (bidi overrides, zero-width) never reach a re-ask prompt
CONTROL = re.compile("[\x00-\x1f\x7f-\x9f​-‏ -‮⁠-⁯﻿]")
VALUE_CHARS = 40
PATH_CHARS = 80
TRUNCATED = ("max_tokens",)


def output_spec(agent_name):
    """The agent's entry in config/outputs.json with its schema loaded (and, for reviewers, the rulebook path).
    Refused before any call when anything is missing."""
    spec = lc.outputs().get(agent_name)
    if not spec or not spec.get("schema"):
        raise lc.LabError(f"no output schema for {agent_name!r} in config/outputs.json: it is never called headless")
    p = lc.ROOT / spec["schema"]
    try:
        schema = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise lc.LabError(f"output schema {spec['schema']} for {agent_name} is unreadable ({e})") from None
    out = {"schema_path": spec["schema"], "schema": schema, "findings": bool(spec.get("findings")), "rulebook": None}
    if out["findings"]:
        rb = vf.reviewer_rulebook(agent_name, lc.ROOT)
        if rb is None or not rb.is_file():
            raise lc.LabError(f"reviewer {agent_name} has no readable rulebook in config/reviewers.json")
        out["rulebook"] = rb
    return out


def clean(value, limit):
    """A value or path as plain text: control characters removed, cut to `limit` characters."""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = CONTROL.sub("", s)
    return s if len(s) <= limit else s[:limit] + " [cut]"


def check_answer(text, stop_reason, spec, job_id, st, agent_name):
    """(parsed object or None, problems). A problem is (path, rule, value); the value is the agent's own
    data and is only ever shown cleaned (reask_text)."""
    if not isinstance(text, str) or not text.strip():
        return None, [("$", "empty or unreadable answer", None)]
    if stop_reason in TRUNCATED:
        return None, [("$", "answer cut off (stop reason " + str(stop_reason) + ")", None)]
    t = text.strip()
    if not (t.startswith("{") and t.endswith("}")):
        return None, [("$", "not one bare JSON object: the first character must be { and the last }", None)]
    try:
        doc = json.loads(t)
    except ValueError:
        return None, [("$", "not valid JSON (unreadable or cut off)", None)]
    if not isinstance(doc, dict):
        return None, [("$", "not a JSON object", None)]
    problems = [(p, rule, v) for p, rule, v, _ in schemacheck.details(doc, spec["schema"])]
    expect = {"job_id": job_id}
    if spec["findings"]:
        expect.update(reviewer=agent_name, artifact_path=st["artifact_path"],
                      artifact_version=lc._version(st["artifact_path"]) if st["artifact_path"] else None)
    for k, want in expect.items():
        if k in doc and doc[k] != want:
            problems.append((f"$.{k}", f"must be copied exactly from the handoff: {want}", doc[k]))
    if spec["findings"]:
        findings = doc.get("findings") if isinstance(doc.get("findings"), list) else []
        rulebook = vf.rulebook_severities(spec["rulebook"])
        overrides = vf.feedback_overrides(job_id, lc.ROOT)
        serious = False
        ids = []
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                continue
            want, why = vf.required_severity(str(f.get("rule", "")).strip().upper(), rulebook, overrides,
                                             lc.rel(spec["rulebook"]))
            if want and f.get("severity") != want:
                problems.append((f"$.findings[{i}].severity", f"severity lock: must be {want} per {why}",
                                 f.get("severity")))
            serious = serious or (want or f.get("severity")) in ("blocker", "major")
            ids.append(f.get("id"))
        if serious and doc.get("verdict") != "fail":
            problems.append(("$.verdict", "must be fail: there is a blocker or major finding", doc.get("verdict")))
        if any(i is not None and ids.count(i) > 1 for i in ids):
            problems.append(("$.findings", "finding ids must be unique", None))
    return doc, problems


def reask_text(problems):
    """The problem list for the second prompt: path, rule and a cleaned value only, never a message text
    (schema messages quote the agent's value in full)."""
    lines = []
    for path, rule, value in problems:
        line = f"  - {clean(path, PATH_CHARS)}: {clean(rule, 200)}"
        if value is not None:
            line += f" (value: {json.dumps(clean(value, VALUE_CHARS), ensure_ascii=False)})"
        lines.append(line)
    return ("\nYOUR PREVIOUS ANSWER WAS REJECTED BY THE SCRIPT. Problems (path: rule (value)):\n" + "\n".join(lines)
            + "\nAnswer again: only the JSON object, every problem fixed.\n")


def output_target(job_id, h, st, agent_name, item, call_id):
    """Where a valid answer is saved: a new file in the stage's output folder. Drafts take the next version
    after the artifact in state.json (default rule 2: never from listing the folder)."""
    out = h["output_dir"]
    if out.endswith("/drafts/"):
        n = 0
        if st["artifact_path"]:
            m = re.fullmatch(r"v(\d+)", lc._version(st["artifact_path"]))
            if not m:
                raise lc.LabError(f"no version number in {st['artifact_path']}: cannot name the next draft")
            n = int(m.group(1))
        name = f"v{n + 1}.json"
    elif h["kind"] == "review":
        name = f"{agent_name}-{lc._version(st['artifact_path'])}-{call_id}.json"
    else:
        name = f"{agent_name}{'-' + item if item else ''}-{call_id}.json"
    target = out + name
    if (lc.ROOT / target).exists():
        raise lc.LabError(f"{target} already exists: an answer is never saved over an existing file")
    return target


def save_rejected(job_id, call_id, text):
    """The invalid answer as received, for audit only (no handoff lists rejected/)."""
    p = lc.job_dir(job_id) / "rejected" / f"{call_id}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "x", encoding="utf-8", newline="") as fh:
        fh.write(text if isinstance(text, str) else "(no answer text)")
    return lc.rel(p)


def call_job(job_id, agent_file, item=None, workspace=None, timeout=DEFAULT_TIMEOUT, cmd=None):
    """One job step: handoff, record the call, run headless, check and save the answer, close the call
    with the JSON's usage and the answer's sha256. One re-ask for an invalid answer (see module doc)."""
    agent = parse_agent(agent_file)
    stage = lc.load_state(job_id)["stage"]
    if stage != agent["name"]:
        raise lc.LabError(f"{job_id} is waiting on {stage!r}, not {agent['name']!r}")
    spec = output_spec(agent["name"])
    h, text = lc.handoff(job_id, item, headless=True)
    base = text if agent["tools"] else text + "\nINPUT FILE CONTENTS (you have no tools; everything is here):\n\n" + inline_inputs(h)
    prompt = base
    for attempt in (1, 2):
        st = lc.load_state(job_id)
        target = output_target(job_id, h, st, agent["name"], item, f"C{len(st['calls']) + 1:03d}")
        st = lc.record_call(job_id, agent["name"], item)
        cid = st["calls"][-1]["id"]
        res = call(agent, prompt, workspace=workspace, timeout=timeout, cmd=cmd)
        source = "headless" if res["usage"] else "manual"
        result = {**res, "call": cid, "handoff": h, "ceiling": None, "output": None}
        if res["status"] != "done":
            _, result["ceiling"] = lc.record_result(job_id, cid, "failed", usage=res["usage"], source=source,
                                                    note=res.get("error"))
            if not result["ceiling"]:
                lc.apply(job_id, "infra_error", note=res.get("error"), actor="script")
            return result
        if isinstance(res["text"], str) and NEEDS_INPUT.search(res["text"]):
            _, result["ceiling"] = lc.record_result(job_id, cid, "failed", usage=res["usage"], source=source,
                                                    note=NEEDS_INPUT_NOTE, rejected=save_rejected(job_id, cid, res["text"]))
            if not result["ceiling"]:
                lc.apply(job_id, "infra_error", note=NEEDS_INPUT_NOTE, actor="script")
            return {**result, "status": "infra_error", "error": NEEDS_INPUT_NOTE}
        _, problems = check_answer(res["text"], res.get("stop_reason"), spec, job_id, st, agent["name"])
        if not problems:
            data = res["text"].strip().encode("utf-8")
            p = lc.ROOT / target
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(p, "xb") as fh:
                    fh.write(data)
            except FileExistsError:
                raise lc.LabError(f"{target} appeared during the call: not saved over it") from None
            output = {"path": target, "sha256": hashlib.sha256(data).hexdigest()}
            _, result["ceiling"] = lc.record_result(job_id, cid, "done", usage=res["usage"], source=source,
                                                    output=output)
            return {**result, "output": output}
        note = f"invalid output ({len(problems)} problem(s)), attempt {attempt}"
        _, result["ceiling"] = lc.record_result(job_id, cid, "failed", usage=res["usage"], source=source, note=note,
                                                rejected=save_rejected(job_id, cid, res["text"]))
        result.update(status="invalid_output", error=note, problems=problems)
        if result["ceiling"]:
            return result
        if attempt == 2:
            lc.apply(job_id, "infra_error", note="invalid output after one re-ask", actor="script")
            return {**result, "status": "infra_error", "error": "invalid output after one re-ask"}
        lc.apply(job_id, "repair", reason="invalid_output", note=note, actor="script")  # CapExceeded at the repairs cap
        prompt = base + reask_text(problems)


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
        if r.get("output"):
            print(f"saved {r['output']['path']}  sha256 {r['output']['sha256']}")
        for path, rule, value in r.get("problems") or []:
            print(f"  - {clean(path, PATH_CHARS)}: {clean(rule, 200)}")
        return 0 if r["status"] == "done" else 1
    except lc.LabError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
