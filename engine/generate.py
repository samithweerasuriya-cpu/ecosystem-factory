#!/usr/bin/env python3
"""Generate an agent ecosystem from a blueprint, then verify and lint it (stdlib only).

  python engine/generate.py generate <blueprint.json> <target folder> [--dry-run]
  python engine/generate.py verify <target folder>     # the manifest still matches the files and the factory
  python engine/generate.py lint <target folder>       # agent files, CLAUDE.md and settings

Generation (T1.3, blueprint v0):
- copied byte for byte: engine/ (except EXCLUDED), the evaluation runner, the engine's own schemas, rulebooks
  and config, .gitattributes; fixed templates from templates/ecosystem/ (settings.json, commands, .gitignore);
  the blueprint's evaluation suites and output schemas, the charter and the blueprint;
- rendered from the blueprint: config (route, gate, caps, reviewers, gated actions, protected paths, scripts, outputs),
  the rulebook, CLAUDE.md and every agent file. The script writes each agent's front matter itself: only the
  keys in AGENT_KEYS, only the blueprint's tools, never Agent. The default agent rules
  (rules/default-agent-rules.md) go word for word into CLAUDE.md and into every agent file;
- generation.json: sha256 of every file above (the manifest), the exclusions, the headless call line of every
  agent and the venv's package versions;
- then the ecosystem's own .venv (uv; jsonschema at the factory's version) and `git init` with the factory's
  repo-local name and GitHub noreply email (T1.4; refused if the factory has none).
The target must not exist or be empty. The blueprint must pass engine/designcheck.py first. --dry-run builds
and lints everything in memory and writes nothing. A generated ecosystem is never edited by hand: verify
reports any file that differs from its manifest entry, any file the manifest doesn't know and any copied
file that differs from the factory's current one.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import agent_call  # noqa: E402
import labcore as lc  # noqa: E402

GENERATOR_VERSION = "0"
MANIFEST = "generation.json"
TEMPLATES = "templates/ecosystem"
# Factory-only engine files: check_coverage reads the private plan (T0.10); designcheck checks factory designs.
EXCLUDED = ["engine/check_coverage.py", "engine/designcheck.py"]
COPY_FILES = ["evals/run_evals.py", "evals/README.md", "evals/thresholds.json",
              "schemas/findings.schema.json", "schemas/job.schema.json", "schemas/route.schema.json",
              "rules/check-refs.md", "rules/check-evidence.md", "rules/default-agent-rules.md",
              "config/doctor.json", "config/models.json", "config/evidence.json", ".gitattributes"]
TEMPLATE_FILES = {"settings.json": ".claude/settings.json", "gitignore": ".gitignore",
                  "commands/new-job.md": ".claude/commands/new-job.md",
                  "commands/run-job.md": ".claude/commands/run-job.md",
                  "commands/status.md": ".claude/commands/status.md"}
DEFAULT_RULES = "rules/default-agent-rules.md"
AGENT_KEYS = ("name", "description", "tools", "model", "maxTurns", "hooks")
ALLOWED_TOOLS = {"Read", "Grep", "Glob"}
NAME = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
# Folders a running ecosystem fills itself; verify ignores them.
RUNTIME = (".git", ".venv", "jobs", "logs", ".lab", "cache", "evals/reports", "private")
# T1.4: `tools: []` was checked live (an in-session subagent was sent an empty tool list) on one CLI version,
# recorded in config/doctor.json (null: never verified). Once a version is recorded, lint refuses a tool-less
# agent on any other installed CLI (re-run the probe first). Either way the settings must deny the Agent and
# Task tools (agents run headless only).
VERIFIED_KEY = "empty_tools_verified_cli"
NOREPLY = "@users.noreply.github.com"


def installed_cli():
    """The installed CLI's version string, or None if it can't run (tests replace this)."""
    return agent_call.cli_version()


def cli_number(s):
    m = re.search(r"\d+\.\d+\.\d+", s or "")
    return m.group(0) if m else None


def empty_tools_problem(verified, installed):
    """Why `tools: []` may not be trusted on the installed CLI, or None. Never verified (null) is allowed: the
    settings deny of the Agent and Task tools then keeps the agent headless-only (the doctor warns)."""
    if verified is None:
        return None
    v, i = cli_number(verified), cli_number(installed)
    if not v:
        return f"config/doctor.json {VERIFIED_KEY} {verified!r} is not a CLI version"
    if v != i:
        return (f"tools [] was verified on CLI {v}; the installed CLI is {i or 'unknown'}: re-run the "
                "empty-tools probe and record its version first")
    return None
HOOK_BLOCK = """hooks:
  PreToolUse:
    - matcher: "*"
      hooks:
        - type: command
          command: py
          args: ["-3", "${CLAUDE_PROJECT_DIR}/engine/hooks/pre_tool_use_launcher.py"]
          onFailure: block
          timeout: 30"""


class GenerateError(lc.LabError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def factory_file(relpath):
    return (lc.ROOT / relpath).read_bytes()


# ---------- the plan: every file of the ecosystem, in memory ----------

def engine_files():
    out = []
    for f in sorted((lc.ROOT / "engine").rglob("*")):
        r = f.relative_to(lc.ROOT).as_posix()
        if f.is_file() and "__pycache__" not in f.parts and r not in EXCLUDED:
            out.append(r)
    return out


def tree_files(src):
    return sorted(f for f in Path(src).rglob("*") if f.is_file() and "__pycache__" not in f.parts)


def gate_id(bp):
    """Route format v1 wants G<n>-<name>; the blueprint's G1 on route `actions` becomes G1-actions."""
    return f"{bp['route']['gate']}-{bp['route']['name']}"


def render_caps(bp):
    caps = json.loads(factory_file("config/caps.json"))
    for k, v in bp["caps"].items():
        if k == "usage_ceiling":
            caps["usage_ceiling"].update(v)
        else:
            caps[k] = v
    u = caps["usage_ceiling"]
    u["per_call_warning_tokens"] = min(u.get("per_call_warning_tokens", u["tokens"]), u["tokens"])
    u["_provisional"] = "PROVISIONAL: from the blueprint (T1.4: set from the first real job's figures); recalibrate as jobs are measured."
    return caps


def reserved_rules(rules_text=None):
    """[{id, rule, severity}] from the reserved-rule table in rules/default-agent-rules.md (T1.4: DR07)."""
    text = (rules_text if rules_text is not None else factory_file(DEFAULT_RULES)).decode("utf-8")
    out = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*(DR\d{2})\s*\|\s*(.+?)\s*\|\s*(blocker|major|minor)\s*\|\s*$", line)
        if m:
            out.append({"id": m.group(1), "rule": m.group(2), "severity": m.group(3)})
    if not out:
        raise GenerateError(f"{DEFAULT_RULES} has no reserved rule rows (| DRnn | rule | severity |)")
    return out


def rulebook_rows(bp):
    """The blueprint's rules followed by the reserved rules: every rule the reviewers apply."""
    return [*bp["rulebook"]["rules"], *({**r, "charter_rule": "default rule 7"} for r in reserved_rules())]


def render_rulebook(bp):
    rb = bp["rulebook"]
    lines = [f"# Rulebook: {rb['name']}", "",
             "Rendered from the blueprint. Rulebook format: one table row per rule, the first cell is the rule ID, and "
             "one cell holds its severity. Severity: **blocker** (cannot pass) · **major** (fail) · **minor** (note only). "
             "Verdict fails on any blocker or major, and only then. Rules starting DR are reserved rules from "
             f"{DEFAULT_RULES}, added to every rulebook.", "",
             "| ID | Rule | Sev | Charter rule |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['rule']} | {r['severity']} | {r['charter_rule']} |" for r in rulebook_rows(bp)]
    if rb.get("definitions"):
        lines += ["", "## Definitions", ""] + [f"- {d}" for d in rb["definitions"]]
    return ("\n".join(lines) + "\n").encode("utf-8")


def severity_line(bp):
    """One generic instruction for every reviewer: each rule's severity, read from the rulebook table."""
    return ("Severity by rule (from the rulebook table; every finding on a rule takes exactly this severity): "
            + ", ".join(f"{r['id']} {r['severity']}" for r in rulebook_rows(bp)) + ".")


def schema_source(bp_path, relpath):
    local = Path(bp_path).parent / relpath
    return local if local.is_file() else lc.ROOT / relpath


def render_agent(a, schema_text, rules_text, severities=None):
    tools = "[]" if not a["tools"] else ", ".join(a["tools"])
    front = ["---", f"name: {a['name']}", f"description: {a['purpose']}", f"tools: {tools}", "model: inherit",
             f"maxTurns: {a['max_turns']}", HOOK_BLOCK, "---"]
    body = ["", "# Role", a["purpose"], "", "# Instructions"] + [f"- {i}" for i in a["instructions"]]
    if severities:                                                     # reviewers (T1.4)
        body += [f"- {severities}"]
    if not a["tools"]:
        body += ["- You have no tools: everything you need is in the message."]
    body += ["", "# Output",
             f"One JSON object that validates against `{a['output_schema']}`:", "", schema_text.rstrip("\n"), ""]
    return ("\n".join(front + body) + "\n").encode("utf-8") + rules_text


def render_claude_md(bp, rules_text, blueprint_sha):
    t = factory_file(f"{TEMPLATES}/CLAUDE.md").decode("utf-8")
    agents = ", ".join(f"`.claude/agents/{a['name']}.md` ({a['role']})" for a in bp["agents"])
    values = {"slug": bp["slug"], "purpose": bp["purpose"], "blueprint_sha256": blueprint_sha[:12],
              "engine_version": factory_file("engine/VERSION").decode().strip(), "route": bp["route"]["name"],
              "gate": gate_id(bp), "rulebook": f"rules/{bp['rulebook']['name']}.md", "agents": agents,
              "default_agent_rules": rules_text.decode("utf-8").rstrip("\n")}
    for k, v in values.items():
        t = t.replace("{{" + k + "}}", v)
    if "{{" in t:
        raise GenerateError(f"CLAUDE.md template has an unknown placeholder: {re.search(r'{{[^}]*}}', t).group(0)}")
    return t.encode("utf-8")


def build(bp_path):
    """{relpath: {"kind": copied|templated|rendered, "data": bytes, "source": factory path or None}}"""
    bp_path = Path(bp_path)
    bp_bytes = bp_path.read_bytes()
    bp = json.loads(bp_bytes)
    files = {}

    def put(rel, kind, data, source=None):
        if rel in files:
            raise GenerateError(f"{rel} would be written twice")
        files[rel] = {"kind": kind, "data": data, "source": source}

    for r in engine_files() + COPY_FILES:
        put(r, "copied", factory_file(r), r)
    for src, dst in TEMPLATE_FILES.items():
        put(dst, "templated", factory_file(f"{TEMPLATES}/{src}"), f"{TEMPLATES}/{src}")
    rules_text = factory_file(DEFAULT_RULES)
    put("docs/blueprint.json", "copied", bp_bytes, lc.rel(bp_path))
    put("docs/charter.json", "copied", factory_file(bp["charter_ref"]), bp["charter_ref"])
    for ev in bp["evals"]:
        src = lc.ROOT / ev["path"]
        for f in tree_files(src):
            if "reports" in f.relative_to(src).parts:
                continue
            put(f"evals/{ev['suite']}/{f.relative_to(src).as_posix()}", "copied", f.read_bytes(), lc.rel(f))
    for a in bp["agents"]:
        if a["output_schema"] not in files:
            src = schema_source(bp_path, a["output_schema"])
            put(a["output_schema"], "copied", src.read_bytes(), lc.rel(src))
        put(f".claude/agents/{a['name']}.md", "rendered",
            render_agent(a, files[a["output_schema"]]["data"].decode("utf-8"), rules_text,
                         severity_line(bp) if a["role"] == "reviewer" else None))
    route, gate = bp["route"], gate_id(bp)
    rulebook = f"rules/{bp['rulebook']['name']}.md"
    put(rulebook, "rendered", render_rulebook(bp))
    put("CLAUDE.md", "rendered", render_claude_md(bp, rules_text, sha(bp_bytes)))
    put("config/routes.json", "rendered", dump({
        "_doc": "The ecosystem's one route (route format v1, schemas/route.schema.json), rendered from the blueprint.",
        "routes": {route["name"]: {"stages": [{"agent": route["author"]}],
                                   "reviews": [{"agent": route["reviewer"], "kind": "critic"}],
                                   "revise_with": route["author"], "gate": gate, "deliver": None}}}))
    gates_cfg = json.loads(factory_file("config/gates.json"))
    put("config/gates.json", "rendered", dump({
        "_doc": gates_cfg["_doc"], "approver": gates_cfg["approver"], "default_mode": "human",
        "gates": {gate: {"mode": g["mode"]} for g in bp["gates"] if g["id"] == route["gate"]}}))
    put("config/caps.json", "rendered", dump(render_caps(bp)))
    put("config/reviewers.json", "rendered", dump({
        "_doc": "Rulebook per reviewer agent (severity lock, engine/validate_findings.py), rendered from the blueprint.",
        "reviewers": {route["reviewer"]: {"rulebook": rulebook},
                      "check-refs": {"rulebook": "rules/check-refs.md"},
                      "check-evidence": {"rulebook": "rules/check-evidence.md"}}}))
    put("config/gated-actions.json", "rendered", dump({
        "_doc": "Read by engine/hooks/pre_tool_use.py. Every MCP tool is blocked unless listed here; the blueprint "
                "allows no connectors, so only the desktop app's own task-list and next-step tools are listed, by "
                "exact name, for the main session only.",
        "mcp": [{"tool": "mcp__ccd_turn__update_plan", "roles": ["main"]},
                {"tool": "mcp__ccd_turn__wrap_up", "roles": ["main"]}],
        "shell": []}))
    put("config/protected-paths.json", "rendered", dump({
        "_doc": "Read by engine/hooks/pre_tool_use.py. no_write_roots: folders outside this ecosystem that no tool "
                "call may write (the other ecosystems; the factory's root is in the untracked "
                "config/protected-paths.local.json). read_blocks: evaluation keys, for agents and for the main "
                "session in operate mode.",
        "no_write_roots": ["C:/ecosystems"],
        "read_blocks": {"subagents": ["evals/**/keys/**", "evals/**/*-key.*"],
                        "operate_main": ["evals/**/keys/**", "evals/**/*-key.*"],
                        "operate_main_read_only": []}}))
    put("config/outputs.json", "rendered", dump({
        "_doc": "The schema each agent's headless answer must match (engine/agent_call.py call_job); findings: "
                "the answer is a reviewer's findings, also held to the severity lock. Rendered from the blueprint.",
        "agents": {a["name"]: {"schema": a["output_schema"], "findings": a["role"] == "reviewer"}
                   for a in bp["agents"]}}))
    put("config/scripts.json", "rendered", dump({
        "_doc": "Allow-list of commands that script stages may run (engine/state.py run). The blueprint has no "
                "script stages.", "scripts": {}}))
    return bp, files


# ---------- lint ----------

def front_matter(text):
    """(keys in order, {key: raw value}, body) or raises GenerateError. Indented lines belong to the key above."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise GenerateError("no front matter")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise GenerateError("front matter is not closed") from None
    keys, values, cur = [], {}, None
    for ln in lines[1:end]:
        if ln.startswith((" ", "\t")) and cur:
            values[cur] += "\n" + ln
            continue
        m = re.fullmatch(r"([A-Za-z_][\w-]*):(.*)", ln)
        if not m:
            raise GenerateError(f"unreadable front matter line: {ln!r}")
        cur = m.group(1)
        if cur in values:
            raise GenerateError(f"key {cur} appears twice")
        keys.append(cur)
        values[cur] = m.group(2).strip()
    return keys, values, "\n".join(lines[end + 1:])


def parse_tools(raw):
    """The tool list, or None when the value could be read as "no list" (which in-session means all tools)."""
    if raw == "[]":
        return []
    if not raw or raw.startswith("[") or raw.endswith("]"):
        return None
    tools = [t.strip() for t in raw.split(",")]
    return None if any(not t for t in tools) else tools


def lint_agent(path_name, data, rules_bytes, settings, empty_tools=None):
    """Problems with one agent file (bytes)."""
    probs, where = [], f"agent {path_name}"
    try:
        keys, v, _ = front_matter(data.decode("utf-8"))
    except (GenerateError, UnicodeDecodeError) as e:
        return [f"{where}: {e}"]
    for k in keys:
        if k not in AGENT_KEYS:
            probs.append(f"{where}: front matter key {k!r} is not allowed (allowed: {', '.join(AGENT_KEYS)})")
    for k in AGENT_KEYS:
        if k != "model" and k not in v:
            probs.append(f"{where}: front matter has no {k}")
    stem = path_name[:-3] if path_name.endswith(".md") else path_name
    name = v.get("name", "")
    if not NAME.fullmatch(name):
        probs.append(f"{where}: name {name!r} is not lowercase-hyphen")
    elif name != stem:
        probs.append(f"{where}: name {name!r} differs from the file name")
    if "tools" in v:
        tools = parse_tools(v["tools"])
        if tools is None:
            probs.append(f"{where}: tools {v['tools']!r} is not an explicit list ('[]' for none; an empty or "
                         "unreadable value would give an in-session agent every tool)")
        else:
            for t in tools:
                if t in ("Agent", "Task"):
                    probs.append(f"{where}: has the {t} tool (only the main session delegates)")
                elif t not in ALLOWED_TOOLS:
                    probs.append(f"{where}: tool {t!r} is not allowed (allowed: {', '.join(sorted(ALLOWED_TOOLS))})")
            if not tools:
                deny = set((settings or {}).get("permissions", {}).get("deny", []))
                if not {"Agent", "Task"} <= deny:
                    probs.append(f"{where}: tools [] needs the settings to deny the Agent and Task tools "
                                 "(it runs headless only)")
                if empty_tools:
                    probs.append(f"{where}: {empty_tools}")
    if "model" in v and v["model"] not in ("inherit",):
        probs.append(f"{where}: model {v['model']!r}: agents use the pinned model (model: inherit)")
    if "maxTurns" in v and not (re.fullmatch(r"\d+", v["maxTurns"]) and 1 <= int(v["maxTurns"]) <= 20):
        probs.append(f"{where}: maxTurns {v['maxTurns']!r} is not a whole number from 1 to 20")
    if "hooks" in v and "hooks:\n" + v["hooks"].lstrip("\n") != HOOK_BLOCK:
        probs.append(f"{where}: hooks differ from the guard hook block")
    if rules_bytes not in data:
        probs.append(f"{where}: does not contain {DEFAULT_RULES} byte for byte")
    return probs


def lint_files(files):
    """Problems across a {relpath: bytes} view of an ecosystem."""
    probs = []
    rules = files.get(DEFAULT_RULES)
    if rules is None:
        return [f"{DEFAULT_RULES} is missing"]
    try:
        settings = json.loads(files.get(".claude/settings.json", b"{}"))
    except ValueError:
        return [".claude/settings.json is not valid JSON"]
    if settings.get("disableClaudeAiConnectors") is not True:
        probs.append(".claude/settings.json does not set disableClaudeAiConnectors: true")
    agents = sorted(r for r in files if r.startswith(".claude/agents/"))
    if not agents:
        probs.append("no agent files in .claude/agents/")
    empty_tools = None
    if any(re.search(rb"(?m)^tools: \[\]\r?$", files[r]) for r in agents):
        try:
            verified = json.loads(files.get("config/doctor.json", b"{}")).get(VERIFIED_KEY)
        except (ValueError, AttributeError):
            verified = None
        empty_tools = empty_tools_problem(verified, installed_cli())
    for r in agents:
        probs += lint_agent(r.rsplit("/", 1)[-1], files[r], rules, settings, empty_tools)
    if rules not in files.get("CLAUDE.md", b""):
        probs.append(f"CLAUDE.md does not contain {DEFAULT_RULES} byte for byte")
    return probs


def lint(target):
    target = Path(target)
    files = {}
    for r in [DEFAULT_RULES, ".claude/settings.json", "CLAUDE.md", "config/doctor.json"]:
        if (target / r).is_file():
            files[r] = (target / r).read_bytes()
    for f in sorted((target / ".claude" / "agents").glob("*")) if (target / ".claude" / "agents").is_dir() else []:
        files[f".claude/agents/{f.name}"] = f.read_bytes() if f.is_file() else b""
    return lint_files(files)


# ---------- headless call lines ----------

def call_lines(files):
    """{agent name: argv} for every agent file, from engine/agent_call.py's own argument builder."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="gen-") as tmp:
        for r in sorted(x for x in files if x.startswith(".claude/agents/")):
            _, v, body = front_matter(files[r].decode("utf-8"))
            spec = {"name": v["name"], "tools": parse_tools(v["tools"]), "model": v.get("model"), "body": body}
            argv = agent_call.build_argv(spec, agent_call.agent_model(spec), tmp, cmd=["claude"])
            out[spec["name"]] = [a if a != str(Path(tmp) / "instructions.md") else "<instructions file>" for a in argv]
    return out


# ---------- verify ----------

def verify(target):
    """Problems: the manifest against the files, against the factory, and files the manifest doesn't know."""
    target = Path(target)
    try:
        gen = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
        manifest = gen["files"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return [f"{MANIFEST}: unreadable ({e})"]
    probs = []
    for r, e in sorted(manifest.items()):
        f = target / r
        if not f.is_file():
            probs.append(f"{r}: missing")
            continue
        if sha(f.read_bytes()) != e["sha256"]:
            probs.append(f"{r}: differs from the manifest (edited by hand?)")
        if e["kind"] in ("copied", "templated") and e["source"] in engine_files() + COPY_FILES + \
                [f"{TEMPLATES}/{s}" for s in TEMPLATE_FILES]:
            src = lc.ROOT / e["source"]
            if not src.is_file() or sha(src.read_bytes()) != e["sha256"]:
                probs.append(f"{r}: differs from the factory's {e['source']} (factory changed since generation)")
    for r in gen.get("excluded", []):
        if (target / r).exists():
            probs.append(f"{r}: excluded from ecosystems, but present")
    for f in sorted(target.rglob("*")):
        r = f.relative_to(target).as_posix()
        if not f.is_file() or "__pycache__" in f.parts or r == MANIFEST:
            continue
        if any(r == x or r.startswith(x + "/") for x in RUNTIME) or re.fullmatch(r"config/[^/]+\.local\.json", r):
            continue
        if r not in manifest:
            probs.append(f"{r}: not in the manifest")
    missing = [r for r in engine_files() + COPY_FILES if r not in manifest]
    probs += [f"{r}: in the factory but not in the manifest" for r in missing]
    return probs


# ---------- writing ----------

def venv_versions(py):
    p = subprocess.run([str(py), "-c", "import sys, importlib.metadata as m; "
                        "print('%d.%d.%d' % sys.version_info[:3], m.version('jsonschema'))"],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise GenerateError(f"{py}: can't read the Python and jsonschema versions ({p.stderr.strip()[:200]})")
    py_v, js_v = p.stdout.split()
    return py_v, js_v


def venv_python(folder):
    win = Path(folder) / "Scripts" / "python.exe"
    return win if win.exists() or sys.platform == "win32" else Path(folder) / "bin" / "python"


def make_venv(target):
    uv = shutil.which("uv")
    if not uv:
        raise GenerateError("uv is not on PATH: install it (free, open source) or add it to PATH, then generate again")
    _, js = venv_versions(venv_python(lc.ROOT / ".venv"))
    min_py = json.loads(factory_file("config/doctor.json"))["min_python"]
    for argv in ([uv, "venv", "--quiet", "--python", min_py, str(target / ".venv")],
                 [uv, "pip", "install", "--quiet", "--python", str(target / ".venv"), f"jsonschema=={js}"]):
        p = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            raise GenerateError(f"{' '.join(argv[:3])} failed: {(p.stderr or p.stdout).strip()[:300]}")
    py_v, got = venv_versions(venv_python(target / ".venv"))
    if got != js:
        raise GenerateError(f"the ecosystem venv has jsonschema {got}, the factory {js}")
    return {"python": py_v, "jsonschema": got}


def factory_identity():
    """{user.name, user.email} from the factory's own repo-local Git config. Refused unless both are set and the
    email is a GitHub noreply address: every generated ecosystem commits with it."""
    out = {}
    for k in ("user.name", "user.email"):
        p = subprocess.run(["git", "-C", str(lc.ROOT), "config", "--local", k], capture_output=True, text=True,
                           timeout=60)
        out[k] = p.stdout.strip() if p.returncode == 0 else ""
    if not out["user.name"] or not out["user.email"].lower().endswith(NOREPLY):
        raise GenerateError("the factory's repo-local Git identity is not set to a GitHub noreply address "
                            f"(git config --local user.email <id>+<name>{NOREPLY}); every ecosystem commits with it")
    return out


def generate(bp_path, target, dry_run=False, venv=True, git=True):
    """Build, lint and (unless dry_run) write the ecosystem. Returns a summary dict."""
    import designcheck  # factory-only; never copied into an ecosystem
    probs = designcheck.check_blueprint(bp_path)
    if probs:
        raise GenerateError("the blueprint does not pass its checks:\n  " + "\n  ".join(probs))
    target = Path(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise GenerateError(f"{target} exists and is not empty: an ecosystem is generated once (changes go "
                            "through a change job)")
    bp, files = build(bp_path)
    data = {r: e["data"] for r, e in files.items()}
    lint_probs = lint_files(data)
    if lint_probs:
        raise GenerateError("lint failed:\n  " + "\n  ".join(lint_probs))
    summary = {"slug": bp["slug"], "target": str(target), "files": len(files),
               "copied": sum(e["kind"] == "copied" for e in files.values()),
               "templated": sum(e["kind"] == "templated" for e in files.values()),
               "rendered": sum(e["kind"] == "rendered" for e in files.values()),
               "agents": [a["name"] for a in bp["agents"]], "headless_calls": call_lines(data), "dry_run": dry_run}
    if dry_run:
        return summary
    identity = factory_identity() if git else None
    target.mkdir(parents=True, exist_ok=True)
    for r, e in files.items():
        f = target / r
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(e["data"])
    local = {"no_write_roots": [lc.ROOT.resolve().as_posix()]}
    (target / "config/protected-paths.local.json").write_bytes(dump(local))
    versions = make_venv(target) if venv else None
    gen = {"_doc": "Written by engine/generate.py; never edit. files is the manifest: sha256 of every generated file "
                   "(kind copied or templated: byte for byte from the factory's source; rendered: from the blueprint). "
                   "verify: python engine/generate.py verify <this folder>.",
           "generator_version": GENERATOR_VERSION,
           "engine_version": factory_file("engine/VERSION").decode().strip(),
           "blueprint": {"path": lc.rel(bp_path), "sha256": sha(Path(bp_path).read_bytes())},
           "excluded": EXCLUDED, "venv": versions, "headless_calls": summary["headless_calls"],
           "files": {r: {"kind": e["kind"], "sha256": sha(e["data"]), "source": e["source"]}
                     for r, e in sorted(files.items())}}
    (target / MANIFEST).write_bytes(dump(gen))
    if git:
        p = subprocess.run(["git", "init", "-q", str(target)], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise GenerateError(f"git init failed: {p.stderr.strip()[:200]}")
        for k, v in identity.items():                                  # commits never show a personal address
            p = subprocess.run(["git", "-C", str(target), "config", "--local", k, v], capture_output=True, text=True,
                               timeout=60)
            if p.returncode != 0:
                raise GenerateError(f"git config {k} failed: {p.stderr.strip()[:200]}")
    after = verify(target) + lint(target)
    if after:
        raise GenerateError("the written ecosystem does not verify:\n  " + "\n  ".join(after))
    summary["venv"] = versions
    return summary


def main(argv=None):
    import argparse
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Generate, verify and lint an agent ecosystem.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("blueprint")
    g.add_argument("target")
    g.add_argument("--dry-run", action="store_true")
    sub.add_parser("verify").add_argument("target")
    sub.add_parser("lint").add_argument("target")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "generate":
            s = generate(args.blueprint, args.target, dry_run=args.dry_run)
            print(f"{'DRY RUN: nothing written. ' if s['dry_run'] else ''}{s['slug']} -> {s['target']}: {s['files']} files "
                  f"({s['copied']} copied, {s['templated']} templated, {s['rendered']} rendered); lint OK"
                  + ("" if s["dry_run"] else f"; verify OK; venv Python {s['venv']['python']}, "
                                             f"jsonschema {s['venv']['jsonschema']}; git init"))
            for name, line in s["headless_calls"].items():
                print(f"  {name}: {' '.join(line)}")
            return 0
        probs = verify(args.target) if args.cmd == "verify" else lint(args.target)
        for p in probs:
            print(f"  - {p}")
        print(f"{args.cmd} {args.target}: {'OK' if not probs else f'{len(probs)} problem(s)'}")
        return 1 if probs else 0
    except (lc.LabError, OSError, ValueError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
