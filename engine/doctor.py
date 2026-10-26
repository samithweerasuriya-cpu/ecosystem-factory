#!/usr/bin/env python3
"""Doctor (stdlib only, T0.14): checks that this folder is safe and ready to work in. Changes nothing.

  python engine/doctor.py                 # every fast check (no Claude calls)
  python engine/doctor.py --json          # the same, as JSON (used by the T4.2 bootstrapper)
  python engine/doctor.py --wsl           # also check WSL (report only)
  python engine/doctor.py --deep [--yes]  # also one live headless call; shows its cost and asks first
  python engine/doctor.py ack <check>     # acknowledge a warning (approver, own terminal)

Each check is OK, WARN (worth knowing, work can go on), FAIL (with a Fix line) or INFO. An
acknowledged warning (config/doctor.local.json, untracked) shows as INFO "acknowledged" until its
details change. Exit code 1 if any check fails. engine/gate.py lock refuses on any FAIL.

Privacy: the doctor prints the home folder as "~", never the OS user name, an email address or an
organisation name (`claude auth status` prints both; only "logged in" and the login type are read),
and for settings and env sections only key names, never values.
The checks that only apply to the factory (vendor/, the source folders, C:\\ecosystems) run only where
those exist, so the same file works inside a generated ecosystem.
"""
import argparse
import getpass
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import labcore as lc  # noqa: E402

OK, WARN, FAIL, INFO = "OK", "WARN", "FAIL", "INFO"
HOOK_FILES = ("pre_tool_use_launcher.py", "pre_tool_use.py", "post_tool_use_launcher.py", "post_tool_use.py")
LAYOUT = ("engine", "engine/hooks", "config", "schemas", "rules", ".claude/settings.json", "engine/VERSION",
          ".gitattributes", ".gitignore")
GITATTR = ("jobs/** -text", "engine/** -text", "config/** -text", "schemas/** -text", "rules/** -text",
           "templates/** -text", ".claude/** -text", "evals/** -text")
GITIGNORE = ("cache/", "config/*.local.json", ".env*", ".claude/settings.local.json")


def version_tuple(s):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", s or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def run_cmd(argv, timeout=60, cwd=None):
    """(exit code, stdout, stderr); exit code None if the program could not start or timed out."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, cwd=cwd, env=env)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return None, "", str(e)


class Ctx:
    """Where to look. Every field can be replaced in tests."""

    def __init__(self, root=None, home=None, env=None, localappdata=None, tempdir=None, ecosystems=None,
                 platform=None, run=None, user=None, cli=None):
        self.root = Path(root or lc.ROOT)
        self.home = Path(home or Path.home())
        self.env = dict(os.environ if env is None else env)
        self.localappdata = Path(localappdata) if localappdata else (
            Path(self.env["LOCALAPPDATA"]) if self.env.get("LOCALAPPDATA") else None)
        self.tempdir = Path(tempdir or tempfile.gettempdir())
        self.platform = platform or sys.platform
        self.run = run or run_cmd
        self.user = user if user is not None else getpass.getuser()
        self.cli = cli
        if ecosystems is not None:
            self.ecosystems = Path(ecosystems)
        else:
            roots = [p for p in protected_roots(self.root) if Path(p).name.lower() == "ecosystems"]
            self.ecosystems = Path(roots[0]) if roots else None

    def claude(self):
        if self.cli:
            return list(self.cli)
        f = self.root / "config" / "models.json"
        cmd = load(f).get("claude_command") if f.exists() else None
        return cmd if isinstance(cmd, list) and cmd else ["claude"]


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def protected_roots(root):
    out = []
    for name in ("protected-paths.json", "protected-paths.local.json"):
        out += load(Path(root) / "config" / name).get("no_write_roots", []) or []
    return out


def result(cid, group, status, message, fix=None, details=None):
    return {"id": cid, "group": group, "status": status, "message": message, "fix": fix, "details": details}


# ---------- 1. tools ----------

def check_venv(ctx):
    py = ctx.root / ".venv" / ("Scripts/python.exe" if ctx.platform == "win32" else "bin/python")
    if not py.exists():
        return result("venv", "tools", FAIL, "no virtual environment (.venv)",
                      "create it: uv venv --python 3.13 .venv, then uv pip install --python .venv jsonschema")
    code, out, err = ctx.run([str(py), "-c", "import sys, jsonschema; print('%d.%d' % sys.version_info[:2])"])
    if code != 0:
        return result("venv", "tools", FAIL, "the venv's Python can't import jsonschema",
                      "install it: uv pip install --python .venv jsonschema")
    need = load(ctx.root / "config" / "doctor.json").get("min_python", "3.13")
    if version_tuple(out) < version_tuple(need):
        return result("venv", "tools", FAIL, f"the venv runs Python {out.strip()}, below {need}",
                      f"recreate it: uv venv --python {need} .venv")
    return result("venv", "tools", OK, f"venv Python {out.strip()} with jsonschema")


def check_hook_python(ctx):
    argv = ["py", "-3", "--version"] if ctx.platform == "win32" else ["python3", "--version"]
    code, out, err = ctx.run(argv)
    if code != 0:
        return result("hook_python", "tools", FAIL, f"{' '.join(argv[:-1])} does not run: the guard hooks can't start "
                      "(Claude Code would block every tool call)",
                      "install Python from python.org with the 'py' launcher ticked" if ctx.platform == "win32"
                      else "install python3")
    return result("hook_python", "tools", OK, f"hooks run with {' '.join(argv[:-1])} ({(out or err).strip()})")


def check_git(ctx):
    out = []
    code, v, _ = ctx.run(["git", "--version"])
    if code != 0:
        return [result("git", "tools", FAIL, "Git is not installed or not on PATH", "install Git for Windows")]
    code, top, _ = ctx.run(["git", "-C", str(ctx.root), "rev-parse", "--show-toplevel"])
    if code != 0:
        out.append(result("git", "tools", FAIL, "this folder is not a Git repository", "git init, then commit"))
    else:
        out.append(result("git", "tools", OK, v.strip()))
    code, email, _ = ctx.run(["git", "-C", str(ctx.root), "config", "user.email"])
    if code != 0 or not email.strip():
        out.append(result("git_identity", "tools", WARN, "no commit email set for this repository",
                          "set the GitHub noreply address: git config user.email <id>+<name>@users.noreply.github.com",
                          {"set": False}))
    elif not email.strip().lower().endswith("@users.noreply.github.com"):
        out.append(result("git_identity", "tools", WARN, "the commit email is not a GitHub noreply address "
                          "(public history would show it)", "git config user.email <id>+<name>@users.noreply.github.com",
                          {"noreply": False}))
    else:
        out.append(result("git_identity", "tools", OK, "commits use a GitHub noreply address"))
    code, remotes, _ = ctx.run(["git", "-C", str(ctx.root), "remote"])
    names = sorted(remotes.split()) if code == 0 else []
    out.append(result("git_remote", "tools", WARN, f"remote(s) configured: {', '.join(names)} (publishing is the "
                      "approver's step, at a publish gate)", None, {"remotes": names}) if names
               else result("git_remote", "tools", OK, "no remote (nothing can be pushed by accident)"))
    return out


def desktop_cli_versions(ctx):
    """Versions of the Claude Code copies the desktop app keeps (newest last)."""
    if not ctx.localappdata:
        return []
    found = []
    for d in glob.glob(str(ctx.localappdata / "Claude-Data" / "claude_*" / "claude-code" / "*")):
        v = version_tuple(Path(d).name)
        if v and Path(d).is_dir():
            found.append(v)
    return sorted(found)


def check_cli(ctx):
    out = []
    need = load(ctx.root / "config" / "doctor.json").get("min_cli", "2.1.295")
    code, v, _ = ctx.run([*ctx.claude(), "--version"])
    path_v = version_tuple(v) if code == 0 else None
    if path_v is None:
        out.append(result("cli_path", "tools", FAIL, "the claude CLI on PATH does not run",
                          "install Claude Code (native installer) and open a new terminal"))
    elif path_v < version_tuple(need):
        out.append(result("cli_path", "tools", FAIL, f"PATH claude is {'.'.join(map(str, path_v))}, below {need}",
                          "update it: claude update"))
    else:
        out.append(result("cli_path", "tools", OK, f"PATH claude {'.'.join(map(str, path_v))} (minimum {need})"))
    app = ctx.env.get("CLAUDE_CODE_DESKTOP_APP_VERSION")
    desk = desktop_cli_versions(ctx)
    if not desk:
        out.append(result("cli_desktop", "tools", INFO, "no desktop app copy of Claude Code found"
                          + (f" (desktop app {app})" if app else "")))
    else:
        dv = desk[-1]
        label = ".".join(map(str, dv))
        if dv < version_tuple(need):
            out.append(result("cli_desktop", "tools", FAIL, f"the desktop app's Claude Code is {label}, below {need}",
                              "update the desktop app (Help > Check for updates) and restart it"))
        else:
            out.append(result("cli_desktop", "tools", OK, f"desktop app's Claude Code {label}"
                              + (f" (desktop app {app})" if app else "")))
        if path_v and dv != path_v:
            out.append(result("cli_match", "tools", WARN, f"the desktop app runs Claude Code {label}, PATH claude is "
                              f"{'.'.join(map(str, path_v))}; evaluations and headless calls use PATH claude",
                              None, {"desktop": label, "path": ".".join(map(str, path_v))}))
    return out


def check_auth(ctx):
    code, out, _ = ctx.run([*ctx.claude(), "auth", "status", "--json"])
    try:
        d = json.loads(out) if code == 0 else {}
    except ValueError:
        d = {}
    logged, method = d.get("loggedIn") is True, d.get("authMethod")     # nothing else is read
    if not logged:
        return result("auth", "tools", FAIL, "the CLI is not logged in", "run: claude auth login (claude.ai account)")
    if method != "claude.ai":
        return result("auth", "tools", FAIL, f"the CLI uses a {method or 'unknown'} login, not a claude.ai login "
                      "(usage would not stay on the subscription)", "claude auth logout, then claude auth login")
    return result("auth", "tools", OK, "logged in with a claude.ai login")


def settings_files(ctx):
    return [("user settings", ctx.home / ".claude" / "settings.json"),
            ("user local settings", ctx.home / ".claude" / "settings.local.json"),
            ("project settings", ctx.root / ".claude" / "settings.json"),
            ("project local settings", ctx.root / ".claude" / "settings.local.json")]


def read_settings(f):
    """(settings dict, None) or ({}, reason). A file that exists but can't be read is never treated as empty."""
    if not f.exists():
        return {}, None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return {}, "not UTF-8 text"
    except ValueError as e:
        return {}, f"not valid JSON (line {getattr(e, 'lineno', '?')}, column {getattr(e, 'colno', '?')})"
    except OSError as e:
        return {}, f"unreadable ({type(e).__name__})"
    return (d, None) if isinstance(d, dict) else ({}, "not a JSON object")


def check_settings_json(ctx):
    bad = [f"{show(ctx, f)}: {why}" for _, f in settings_files(ctx) for why in [read_settings(f)[1]] if why]
    if bad:
        return result("settings_json", "tools", FAIL, "settings file(s) can't be read: " + "; ".join(bad)
                      + " (Claude Code may ignore them, and the doctor can't check them)",
                      "fix the JSON (a missing comma between entries is the usual cause), then run the doctor again")
    return result("settings_json", "tools", OK, "every settings file is valid JSON")


def check_api_key(ctx):
    where = []
    if ctx.env.get("ANTHROPIC_API_KEY"):
        where.append("the environment")
    for label, f in settings_files(ctx):
        d, why = read_settings(f)
        if why:
            where.append(f"{label} can't be checked ({why})")
        if "ANTHROPIC_API_KEY" in (d.get("env") or {}):
            where.append(f"{label} env")
        if "apiKeyHelper" in d:
            where.append(f"{label} apiKeyHelper")
    if where:
        return result("api_key", "tools", FAIL, f"an API key may be configured ({', '.join(where)}): calls would be "
                      "billed to an API account, not the subscription",
                      "remove it (setx ANTHROPIC_API_KEY \"\" and delete the settings entry), then open a new terminal")
    return result("api_key", "tools", OK, "ANTHROPIC_API_KEY is not set")


def check_auto_updates(ctx):
    """WARN while automatic CLI updates are on: an update makes every evaluation report stale."""
    off = []
    for var in ("DISABLE_AUTOUPDATER", "DISABLE_UPDATES"):      # documented in code.claude.com/docs/en/setup
        if ctx.env.get(var) not in (None, "", "0"):
            off.append(f"{var} in the environment")
        for label, f in settings_files(ctx):
            d = read_settings(f)[0]
            if str((d.get("env") or {}).get(var, "")) not in ("", "0"):
                off.append(f"{var} in {label} env")
    if off:
        return result("auto_updates", "tools", OK, "automatic CLI updates are off (" + "; ".join(off) + "); the "
                      "desktop app still updates its own copy")
    return result("auto_updates", "tools", WARN, "automatic CLI updates are on: an update makes every evaluation "
                  "report stale, so the next lock needs every suite re-run",
                  "add \"env\": {\"DISABLE_AUTOUPDATER\": \"1\"} to ~/.claude/settings.json yourself (the doctor never "
                  "changes it); see docs/doctor.md", {"on": True})


# ---------- 2. hooks ----------

def check_hooks(ctx):
    out, hooks = [], ctx.root / "engine" / "hooks"
    pins = load(hooks / "PINS.json")
    missing = [f for f in HOOK_FILES if not (hooks / f).is_file()]
    if missing:
        out.append(result("hook_files", "hooks", FAIL, f"hook file(s) missing: {', '.join(missing)}",
                          "restore them: git checkout -- engine/hooks"))
    else:
        bad = []
        for f in HOOK_FILES:
            try:
                compile((hooks / f).read_text(encoding="utf-8"), str(hooks / f), "exec")
            except (SyntaxError, ValueError, UnicodeDecodeError) as e:
                bad.append(f"{f} ({type(e).__name__}, line {getattr(e, 'lineno', '?')})")
        out.append(result("hook_files", "hooks", FAIL, f"hook file(s) don't compile: {', '.join(bad)}",
                          "fix or restore them (git checkout -- engine/hooks); until then every tool call is blocked")
                   if bad else result("hook_files", "hooks", OK, "both launchers and both hooks present and compile"))
        changed = [f for f in HOOK_FILES if hashlib.sha256((hooks / f).read_bytes()).hexdigest() != pins.get(f)]
        out.append(result("hook_pins", "hooks", FAIL, f"hook file(s) differ from engine/hooks/PINS.json: "
                          f"{', '.join(changed)}", "restore the file (git checkout -- engine/hooks), or, for a "
                          "reviewed hook change in build mode, update its pin in the same commit")
                   if changed else result("hook_pins", "hooks", OK, "hook files match their pinned fingerprints"))
    d = load(ctx.root / ".claude" / "settings.json")
    problems = []
    for event, matcher_ok, launcher in (("PreToolUse", lambda m: m == "*", "pre_tool_use_launcher.py"),
                                        ("PostToolUse", lambda m: {"Agent", "Task"} <= set((m or "").split("|")),
                                         "post_tool_use_launcher.py")):
        entries = [h for e in (d.get("hooks") or {}).get(event, []) if matcher_ok(e.get("matcher"))
                   for h in e.get("hooks", []) if launcher in " ".join([str(h.get("command", ""))] + list(map(str, h.get("args", []))))]
        if not entries:
            problems.append(f"{event}: {launcher} not registered with the right matcher")
        elif not all(h.get("onFailure") == "block" for h in entries):
            problems.append(f"{event}: {launcher} without onFailure: block")
    out.append(result("hook_settings", "hooks", FAIL, "; ".join(problems),
                      "restore .claude/settings.json (git checkout -- .claude/settings.json), then restart Claude Code")
               if problems else result("hook_settings", "hooks", OK,
                                       "both hooks registered in .claude/settings.json with onFailure: block"))
    return out


# ---------- 3. user-level and stray files ----------

def names(d, pattern="*"):
    return sorted(p.stem if p.is_file() else p.name for p in Path(d).glob(pattern)) if Path(d).is_dir() else []


def check_user_level(ctx):
    out, u = [], ctx.home / ".claude"
    for cid, label, items in (("user_agents", "user-level agents", names(u / "agents", "*.md")),
                              ("user_skills", "user-level skills", names(u / "skills")),
                              ("user_commands", "user-level commands", names(u / "commands", "*.md"))):
        out.append(result(cid, "user", WARN, f"{label} in ~/.claude: {', '.join(items)} (they can load in this "
                          "project's interactive sessions)", "move them aside if they are not needed here",
                          {"names": items}) if items else result(cid, "user", OK, f"no {label}"))
    if (u / "agents.off").is_dir():
        out.append(result("user_agents_off", "user", INFO, "~/.claude/agents.off is parked aside (not loaded)"))
    md = [p for p in (u / "CLAUDE.md", ctx.home / "CLAUDE.md") if p.is_file()]
    out.append(result("user_claude_md", "user", WARN, f"user-level CLAUDE.md: {', '.join(show(ctx, p) for p in md)} "
                      "(loaded into sessions and into headless agents with tools)", "move it aside while working here",
                      {"files": [show(ctx, p) for p in md]}) if md else result("user_claude_md", "user", OK,
                                                                               "no user-level CLAUDE.md"))
    for label, f in settings_files(ctx)[:2]:
        d, why = read_settings(f)
        if f.exists() and not why:                                     # unreadable files: settings_json fails
            keys = sorted(d)
            env_keys = sorted((d.get("env") or {}).keys())
            risky = [k for k in ("hooks", "permissions", "env", "apiKeyHelper", "enabledPlugins") if k in d]
            out.append(result("user_settings" if "local" not in label else "user_local_settings", "user", WARN,
                              f"{label} exist (keys: {', '.join(keys) or 'none'}"
                              + (f"; env keys: {', '.join(env_keys)}" if env_keys else "") + ")"
                              + (f"; these apply to this project too: {', '.join(risky)}" if risky else ""),
                              "check nothing there widens access or changes models for this project",
                              {"keys": keys, "env_keys": env_keys}))
    cmds = set(names(ctx.root / ".claude" / "commands", "*.md")) | set(names(ctx.root / ".claude" / "skills"))
    clash = sorted(cmds & set(names(u / "skills")))
    out.append(result("skill_collisions", "user", WARN, f"user skills with the same name as project commands or "
                      f"skills: {', '.join(clash)} (a personal skill overrides the project's)",
                      "rename or remove the user-level skill", {"names": clash}) if clash
               else result("skill_collisions", "user", OK, "no user skill shadows a project command or skill"))
    return out


def parents(p):
    p = Path(p)
    return [p] + list(p.parents)


def check_stray_claude_md(ctx):
    places = set(parents(ctx.tempdir)) | set(parents(ctx.root)[1:])   # run folders sit in the temp folder
    places.add(Path(ctx.root.anchor))
    if ctx.ecosystems and ctx.ecosystems.is_dir():
        places |= set(parents(ctx.ecosystems))
    places.discard(ctx.home)                                          # reported by user_claude_md
    found = sorted({show(ctx, d / "CLAUDE.md") for d in places if (d / "CLAUDE.md").is_file()})
    if found:
        return result("stray_claude_md", "user", WARN, f"CLAUDE.md file(s) above the run folders: {', '.join(found)} "
                      "(they load into every headless agent that has tools)", "move them aside",
                      {"files": found})
    return result("stray_claude_md", "user", OK, "no CLAUDE.md above the run folders, the repo or the ecosystems folder")


# ---------- 4. local config ----------

def check_local_config(ctx):
    out = []
    if (ctx.root / "vendor").is_dir():
        f = ctx.root / "config" / "protected-paths.local.json"
        out.append(result("protected_local", "config", OK, "source folders are write-protected "
                          "(config/protected-paths.local.json)") if f.is_file() else
                   result("protected_local", "config", WARN, "vendor/ exists but config/protected-paths.local.json is "
                          "missing: the source folders are not write-protected by the hook",
                          "create it with source_roots listing the source folders", {"missing": True}))
    conv = load(ctx.root / "config" / "evidence.local.json").get("pdf_converter")
    conv = conv[0] if isinstance(conv, list) and conv else conv       # a command list: its first entry is the program
    if isinstance(conv, str) and conv and Path(conv).is_file():
        out.append(result("markitdown", "config", INFO, "markitdown found: PDFs can be stored as evidence"))
    else:
        out.append(result("markitdown", "config", INFO, "markitdown not found: PDF sources are stored as unfetchable "
                          "and can't back facts (set pdf_converter in config/evidence.local.json)"))
    return out


# ---------- 5. evaluations ----------

def check_evals(ctx, operate):
    try:
        import evalcheck
        cli = None
        code, v, _ = ctx.run([*ctx.claude(), "--version"])
        cli = v.strip() if code == 0 else None
        problems = evalcheck.lock_problems(cli=cli or "")
    except (lc.LabError, OSError, ValueError, KeyError) as e:
        problems = [f"evaluation check could not run ({e})"]
    if not problems:
        return result("evals", "evals", OK, "evaluation reports cover the current files, model and CLI")
    suites = sorted({m.group(1) for p in problems for m in [re.search(r"suite (\S+?):", p)] if m})
    msg = "evaluations are stale: " + "; ".join(problems[:4]) + (" ..." if len(problems) > 4 else "")
    fix = ("re-run: " + ", ".join(f"python evals/run_evals.py run {s}" for s in suites)) if suites else \
        "run the suites (python evals/run_evals.py run <suite>) or a smoke run"
    if operate:
        return result("evals", "evals", FAIL, "operate mode is locked on " + msg, "unlock, " + fix + ", then lock")
    return result("evals", "evals", WARN, msg + " (lock would be refused)", fix, {"problems": problems})


# ---------- 6. mode, layout, WSL ----------

def check_mode(ctx):
    operate = (ctx.root / ".lab" / "OPERATE").exists()
    f = ctx.root / ".lab" / "active_job"
    job = f.read_text(encoding="utf-8").strip() if f.exists() else None
    state = None
    if job:
        try:
            state = lc.load_state(job)["state"]
        except (lc.LabError, KeyError, ValueError, OSError):
            state = "unreadable"
    return operate, result("mode", "mode", INFO, f"{'operate' if operate else 'build'} mode"
                           + (f"; active job {job} ({state})" if job else "; no active job"))


def check_layout(ctx):
    missing = [p for p in LAYOUT if not (ctx.root / p).exists()]
    attrs = (ctx.root / ".gitattributes").read_text(encoding="utf-8") if (ctx.root / ".gitattributes").exists() else ""
    ign = (ctx.root / ".gitignore").read_text(encoding="utf-8") if (ctx.root / ".gitignore").exists() else ""
    no_attr = [a for a in GITATTR if a not in attrs.splitlines()]
    no_ign = [g for g in GITIGNORE if g not in ign.splitlines()]
    problems = ([f"missing: {', '.join(missing)}"] if missing else []) + \
        ([f".gitattributes lacks: {', '.join(no_attr)}"] if no_attr else []) + \
        ([f".gitignore lacks: {', '.join(no_ign)}"] if no_ign else [])
    if problems:
        return result("layout", "mode", FAIL, "; ".join(problems),
                      "restore the missing files and lines from Git (git checkout -- <path>)")
    return result("layout", "mode", OK, "folder layout, .gitattributes and .gitignore as the engine expects")


def check_publish_hooks(ctx):
    """T0.19: the publish-check hooks (pre-commit, commit-msg, pre-push) and the denylist they need."""
    if not (ctx.root / ".git").exists():
        return result("publish_hooks", "mode", INFO, "not a Git repository here: no publish hooks to check")
    import publish_check
    got = publish_check.hooks_installed(ctx.root) or {}
    missing = [n for n, ok in got.items() if not ok] or ([] if got else list(publish_check.HOOKS))
    factory = (ctx.root / "private").is_dir()
    if missing:
        return result("publish_hooks", "mode", FAIL if factory else WARN,
                      f"publish-check hook(s) not installed: {', '.join(missing)} (private material could be "
                      "committed or pushed)", "python engine/publish_check.py install", {"missing": missing})
    try:
        publish_check.Rules(ctx.root)
    except publish_check.Fail as e:
        return result("publish_hooks", "mode", FAIL, f"the hooks are installed but can't check anything: {e}",
                      "write the denylist (one term per line), then run the doctor again")
    return result("publish_hooks", "mode", OK, "publish-check hooks installed (commit, message, push) with a denylist")


def check_wsl(ctx):
    if ctx.platform != "win32":
        return result("wsl", "mode", INFO, "not Windows: WSL not applicable")
    code, out, err = ctx.run(["wsl", "--status"], timeout=30)
    return result("wsl", "mode", INFO, "WSL available" if code == 0 else "WSL not available (only needed for tools that "
                  "don't run on Windows)")


# ---------- deep ----------

DEEP_AGENT = {"name": "doctor-probe", "tools": [], "model": None, "body": "Answer with exactly one word: ready\n",
              "path": "engine/doctor.py", "sha256": "doctor"}


def deep_estimate():
    import agent_call
    return agent_call.estimate(DEEP_AGENT, "Are you ready?")


def check_deep(ctx, cmd=None):
    import agent_call
    try:
        res = agent_call.call(DEEP_AGENT, "Are you ready?", timeout=180, cmd=cmd or ctx.claude())
    except lc.LabError as e:
        return result("deep", "deep", FAIL, f"live call refused ({e})", "fix the configuration named above")
    if res["status"] != "done":
        return result("deep", "deep", FAIL, f"live headless call {res['status']}: {res.get('error')}",
                      "check the login (claude auth status) and the network, then re-run with --deep")
    pinned = agent_call.pinned_model()
    u = res["usage"] or {}
    if u.get("total") is None:
        return result("deep", "deep", FAIL, "the live call returned no usage figures", "update Claude Code")
    if pinned not in res["models"]:
        return result("deep", "deep", FAIL, f"the live call used {', '.join(res['models'])}, not the pinned {pinned}",
                      "check config/models.json and the account's model access")
    return result("deep", "deep", OK, f"live headless call answered on the subscription ({u['total']} tokens, model {pinned})")


# ---------- running ----------

def show(ctx, p):
    """A path for printing: the home folder becomes ~ (long and short Windows spellings)."""
    s = str(p)
    try:
        s = str(Path(p).resolve())
    except OSError:
        pass
    for h in home_forms(ctx):
        if s.lower().startswith(h.lower()):
            return "~" + s[len(h):]
    return s


def home_forms(ctx):
    forms = {str(ctx.home)}
    try:
        forms.add(str(ctx.home.resolve()))
    except OSError:
        pass
    return sorted(forms, key=len, reverse=True)


def scrub(ctx, text):
    """Last line of defence for anything printed: home folder to ~, the OS user name to <user>."""
    for h in home_forms(ctx):
        for form in (h, h.replace("\\", "/"), h.replace("\\", "\\\\")):
            text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    if ctx.user and len(ctx.user) >= 3:
        text = re.sub(re.escape(ctx.user), "<user>", text, flags=re.IGNORECASE)
    return text


def fingerprint(r):
    # The check's own message, not the one apply_acks annotates: a re-acknowledgement after a lapse must
    # match the next run (found in T0.20: the annotated message made re-acknowledgements never stick).
    return hashlib.sha256(json.dumps({"id": r["id"], "status": r.get("raw_status", r["status"]),
                                      "details": r["details"], "message": r.get("raw_message", r["message"])},
                                     sort_keys=True).encode()).hexdigest()


def apply_acks(ctx, results):
    acks = load(ctx.root / "config" / "doctor.local.json").get("acknowledged", {})
    for r in results:
        r["raw_message"], r["raw_status"] = r["message"], r["status"]
        if r["status"] == WARN and r["id"] in acks:
            if acks[r["id"]] == fingerprint(r):
                r["status"], r["acknowledged"] = INFO, True
                r["message"] = "acknowledged: " + r["message"]
            else:
                r["message"] += " (acknowledged earlier, but the details changed)"
    return results


def fast_checks(ctx=None):
    """Every check that makes no Claude call. Returns a list of results (acknowledgements applied)."""
    ctx = ctx or Ctx()
    operate, mode = check_mode(ctx)
    res = []
    for check in (check_venv, check_hook_python, check_git, check_cli, check_auth, check_settings_json, check_api_key,
                  check_auto_updates,
                  check_hooks, check_user_level, check_stray_claude_md, check_local_config,
                  lambda c: check_evals(c, operate), lambda c: mode, check_layout, check_publish_hooks):
        try:
            r = check(ctx)
        except Exception as e:  # a broken check is a failure, never a traceback (it could print raw paths)
            name = getattr(check, "__name__", "check").replace("check_", "")
            r = result(name, "doctor", FAIL, f"the check itself failed ({type(e).__name__}: {e})",
                       "report this; the doctor needs fixing")
        res += r if isinstance(r, list) else [r]
    return apply_acks(ctx, res)


def failures(ctx=None):
    """The FAIL lines of the fast checks (used by gate.py lock)."""
    ctx = ctx or Ctx()
    return [scrub(ctx, f"{r['id']}: {r['message']}" + (f" (Fix: {r['fix']})" if r["fix"] else ""))
            for r in fast_checks(ctx) if r["status"] == FAIL]


def render(ctx, results):
    lines = []
    for r in results:
        lines.append(f"{r['status']:<4}  {r['id']:<18} {r['message']}")
        if r["status"] in (FAIL, WARN) and r["fix"]:
            lines.append(f"{'':24}Fix: {r['fix']}")
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (FAIL, WARN, OK, INFO)}
    lines.append(f"\n{counts[FAIL]} fail, {counts[WARN]} warn, {counts[OK]} ok, {counts[INFO]} info"
                 + ("  -> NOT READY" if counts[FAIL] else "  -> ready"))
    return scrub(ctx, "\n".join(lines))


def ack(ctx, cid, interactive=None):
    import gate
    if not (interactive if interactive is not None else gate.interactive_terminal()):
        raise lc.LabError("acknowledging a warning is the approver's step: run it in your own terminal")
    r = next((x for x in fast_checks(ctx) if x["id"] == cid), None)
    if r is None or r["status"] != WARN:
        raise lc.LabError(f"no current warning {cid!r} to acknowledge")
    f = ctx.root / "config" / "doctor.local.json"
    d = load(f)
    d.setdefault("acknowledged", {})[cid] = fingerprint(r)
    f.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
    return r


def main(argv=None, ctx=None, out=print):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Check that this folder is safe and ready to work in.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--wsl", action="store_true")
    ap.add_argument("--deep", action="store_true", help="one live headless call (shows its cost and asks first)")
    ap.add_argument("--yes", action="store_true", help="with --deep: confirm the live call without asking")
    ap.add_argument("cmd", nargs="?", choices=["ack"])
    ap.add_argument("check", nargs="?")
    args = ap.parse_args(argv)
    ctx = ctx or Ctx()
    if args.cmd == "ack":
        try:
            r = ack(ctx, args.check)
        except lc.LabError as e:
            out(f"REFUSED: {e}")
            return 1
        out(scrub(ctx, f"acknowledged {r['id']}: it shows as INFO until its details change"))
        return 0
    results = fast_checks(ctx)
    if args.wsl:
        results.append(check_wsl(ctx))
    if args.deep:
        e = deep_estimate()
        out(f"--deep makes one live headless call: about {e['tokens']:,} tokens (about USD 0.01 at list price).")
        if not args.yes:
            import gate
            if not gate.interactive_terminal():
                out("REFUSED: confirm with --yes, or run it in your own terminal")
                return 1
            if input("Type 'yes' to make the call: ").strip() != "yes":
                out("Not confirmed; skipped the live call.")
            else:
                results.append(check_deep(ctx))
        else:
            results.append(check_deep(ctx))
    if args.json:
        out(scrub(ctx, json.dumps({"results": results, "ready": not any(r["status"] == FAIL for r in results)},
                                  indent=2)))
    else:
        out(render(ctx, results))
    return 1 if any(r["status"] == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
