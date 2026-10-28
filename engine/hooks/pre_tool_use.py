#!/usr/bin/env python3
"""Claude Code PreToolUse hook: deterministic guardrails (stdlib only).

Derived from the author's earlier private lab. Registered through
pre_tool_use_launcher.py, which turns any failure here (even a syntax error) into a block.
run(raw) returns 0 = allow or 2 = block (reason on stderr); every block is logged to
logs/blocked.jsonl (private/logs/blocked.jsonl while an internal job is active or the call
touches private/).

Rules
 1. Always protected (no tool writes): jobs/*/ and private/jobs/*/ gates, state.json,
    run.log.jsonl, scripts/, inputs/, questions/; .lab/; logs/blocked.jsonl; gate-audit logs.
    Also any path outside the repo whose tail looks like one of these (another ecosystem's
    gates), and every no-write root in config/protected-paths.json (e.g. the generated
    ecosystems' folder and the source folders).
 2. Operate mode (.lab/OPERATE): framework files are protected too: .claude/, engine/,
    rules/, config/, schemas/, templates/, evals/*/cases/.
 3. Write tools: outside the repo only into the session's scratchpad, taken from the harness's
    scratchpad_dir field (never a model-supplied path) and only if it resolves outside the repo,
    the no-write roots and the source folders.
 4. Read blocks (config/protected-paths.json): subagents (input has agent_id) never read the
    subagent list (method lab, private/, docs/thin/, eval keys); in operate mode the main session
    is blocked from its own list, with private/plan/ read-only. The active job's folder under
    private/jobs/ is the one exception, and only when that job is internal.
 5. Shell (Bash, PowerShell, Monitor), fail-closed: a command that names a protected path is
    allowed only if every part of it is on the read-only allow-list (nested bash -c, sh -c,
    powershell -Command, cmd /c and wsl are checked recursively); anything the parser can't
    follow is blocked. Always blocked: executing gate.py, git push, reading secret files,
    eval / iex / Invoke-Expression / base64 decoding / encoded PowerShell commands (the one exception:
    those words inside the single literal -m message of a lone `git commit`, T1.3 H2). Commands
    matching a `shell` entry in config/gated-actions.json need that entry's conditions.
 6. MCP: blocked unless an `mcp` entry in config/gated-actions.json allows the tool; entries may
    require roles (["main"]: only the main session, keyed on the absence of agent_id), job types,
    states or a gate token.
 7. Subagent calls (Agent, Task) while a job is active (the .lab/active_job pointer names a job
    that is not DONE or CANCELLED, or can't be read): allowed only with run_in_background set
    explicitly to false. A background call returns before the subagent finishes, so the usage
    hook would see no figures; some apps run subagents in the background unless told otherwise,
    so a call that doesn't say is refused too.
Limits: this is pattern-based analysis, not a sandbox. It stops accidents and prompt drift,
not a determined attacker on your own machine: a path assembled at run time is not recognised,
and inline interpreter code is judged by what it names and by its delete calls (rmtree, remove,
unlink, rmdir, Remove-Item: always blocked), not by everything it could do (e.g. writing a file
whose name it builds at run time, or a bare "." inside code).
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labcore as lc  # noqa: E402

JOB_ALWAYS = ["gates/*", "state.json", "run.log.jsonl", "scripts/*", "inputs/*", "questions/*", "evidence/*"]
ALWAYS = ([f"jobs/*/{p}" for p in JOB_ALWAYS] + [f"private/jobs/*/{p}" for p in JOB_ALWAYS]
          + ["cache/*", ".lab/*", ".lab", "logs/blocked.jsonl", "logs/gate-audit.jsonl", "logs/usage.jsonl",
             "logs/usage-unmatched.jsonl", "private/logs/blocked.jsonl", "private/logs/gate-audit.jsonl",
             "private/logs/usage.jsonl", "private/logs/usage-unmatched.jsonl"])
# Outside the repo, these tails still mean "a job's or ecosystem's protected file".
FOREIGN_TAILS = ["*/jobs/*/gates/*", "*/jobs/*/state.json", "*/jobs/*/run.log.jsonl", "*/.lab/*", "*/.lab"]
OPERATE = [".claude/*", "engine/*", "rules/*", "config/*", "schemas/*", "templates/*", "evals/*/cases/*"]
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "LS"}
SHELL_TOOLS = {"Bash", "PowerShell", "Monitor"}
AGENT_TOOLS = {"Agent", "Task"}

SECRET_NAME = re.compile(r"^(\.env(\..*)?|master\.key)$", re.IGNORECASE)
INTERPRETERS = {"python", "python3", "py", "python.exe", "python3.exe", "py.exe", "pythonw", "ruby", "node",
                "perl", "php", "deno", "bun"}
NESTED_SH = {"bash", "sh", "zsh", "dash", "bash.exe", "sh.exe"}
NESTED_PS = {"powershell", "pwsh", "powershell.exe", "pwsh.exe"}
NESTED_CMD = {"cmd", "cmd.exe"}
NESTED_WSL = {"wsl", "wsl.exe"}
READ_ONLY = {"ls", "cat", "head", "tail", "grep", "wc", "cd", "echo", "test", "[", "pwd", "sort", "uniq", "cut",
             "true", "false",
             # PowerShell and cmd read-only spellings (matched case-insensitively)
             "get-content", "gc", "type", "select-string", "sls", "get-childitem", "gci", "dir", "test-path",
             "write-output", "set-location", "sl", "get-location", "measure-object", "measure", "select-object",
             "select", "out-null", "findstr"}
READ_ONLY_GIT = {"status", "log", "diff", "show", "ls-files", "rev-parse", "grep", "check-ignore"}
WRITE_FLAGS = {"-o", "--output", "--output-file", "-outfile", "-delete", "-exec", "-execdir", "-ok", "-fprint"}
WRITE_FLAG_PREFIXES = ("--output", "-outfile")
# git options that write files or run other programs, so a "read-only" git command is not read-only
GIT_UNSAFE = {"-o", "-O", "--open-files-in-pager", "--ext-diff", "--textconv", "--output"}
GIT_UNSAFE_PREFIXES = ("--output", "--open-files-in-pager", "-O")
GIT_GLOBAL_UNSAFE = ("-c", "--config-env")
# 3. inline interpreter code that deletes files: blocked whatever path it names
DELETE_CALL = re.compile(r"\b(rmtree|remove|unlink|rmdir|removedirs|unlinkSync|rmSync|rmdirSync|rm_rf|rm_r)\s*\(|"
                         r"\bFileUtils\.rm\b|\bfs\.rm\s*\(|\bRemove-Item\b", re.IGNORECASE)
ENGINE_TOOLS = {"engine/state.py", "engine/validate_findings.py", "engine/check_refs.py",
                "engine/check_coverage.py", "engine/run_tests.py", "engine/evidence.py", "engine/registry_check.py",
                "engine/agent_call.py", "evals/run_evals.py", "engine/doctor.py"}
HARMLESS_TARGETS = {"/dev/null", "nul", "$null", "&1", "&2", "1", "2"}
OBFUSCATION = re.compile(r"(^|[\s;&|(`])(eval|iex|invoke-expression)(\s|$|\()|frombase64string|"
                         r"\bbase64\b[^|;&]*\s(-d|--decode|-D)\b|\s-e(nc|ncodedcommand)?\s+[A-Za-z0-9+/=]{16,}",
                         re.IGNORECASE)
SUBST = re.compile(r"\$\(|`")
BARE_STRING = re.compile(r"'[^'$`]*'|\"[^\"$`]*\"")   # a quoted literal with nothing to expand
PATH_CHUNK = re.compile(r"[A-Za-z0-9_.~:/\\\-*?$%{}@+]+")


class Blocked(Exception):
    pass


class Unparseable(Exception):
    pass


# ---------- context ----------

class Ctx:
    def __init__(self, data):
        self.data = data
        self.tool = data.get("tool_name", "") or ""
        self.ti = data.get("tool_input", {}) or {}
        self.operate = (lc.LAB / "OPERATE").exists()
        self.subagent = bool(data.get("agent_id"))
        self.root = norm_abs(str(lc.ROOT))
        self.cwd = norm_abs(data.get("cwd") or str(lc.ROOT))
        cfg = protected_config()
        self.no_write_roots = [norm_abs(p) for p in cfg.get("no_write_roots", [])]
        self.source_roots = [norm_abs(p) for p in cfg.get("source_roots", [])]
        rb = cfg.get("read_blocks", {})
        self.read_blocks = rb.get("subagents", []) if self.subagent else (rb.get("operate_main", []) if self.operate else [])
        self.read_only = [] if self.subagent or not self.operate else rb.get("operate_main_read_only", [])
        self.job_folder = active_internal_job_folder()
        self.scratch = self.valid_scratch(data.get("scratchpad_dir"))
        self.touches_private = False

    def valid_scratch(self, raw):
        """The harness's scratchpad, if it is a real absolute path outside every guarded root."""
        if not raw or not isinstance(raw, str):
            return None
        p = norm_abs(raw)
        if not re.match(r"^[a-z]:/", p) and not p.startswith("/"):
            return None
        for guarded in [self.root] + self.no_write_roots + self.source_roots:
            if within(p, guarded) or within(guarded, p):
                return None
        return p

    def rel(self, abs_path):
        if abs_path == self.root:
            return ""
        return abs_path[len(self.root) + 1:] if abs_path.startswith(self.root + "/") else None


def protected_config():
    out = {}
    for name in ("protected-paths.json", "protected-paths.local.json"):
        f = lc.CONFIG / name
        if f.exists():
            for k, v in lc.load_json(f).items():
                if isinstance(v, list):
                    out[k] = out.get(k, []) + v
                elif isinstance(v, dict):
                    merged = dict(out.get(k, {}))
                    for kk, vv in v.items():
                        merged[kk] = merged.get(kk, []) + vv
                    out[k] = merged
    return out


def active_internal_job_folder():
    job = lc.active_job()
    try:
        if job and lc.is_internal(job):
            return lc.rel(lc.job_dir(job)).casefold()
    except lc.LabError:
        pass
    return None


# ---------- paths ----------

def norm_abs(p):
    """Absolute, forward-slash, case-folded path; Git Bash /c/ and WSL /mnt/c/ become c:/."""
    p = p.replace("\\", "/")
    m = re.match(r"^/mnt/([a-zA-Z])(/|$)(.*)", p) or re.match(r"^/([a-zA-Z])(/|$)(.*)", p)
    if m:
        p = f"{m.group(1)}:/{m.group(3)}"
    if p.startswith("~"):
        p = str(Path.home()).replace("\\", "/") + p[1:]
    if re.match(r"^[a-zA-Z]:/", p):
        p = os.path.realpath(p)  # long names for 8.3 short names; follows junctions
    p = os.path.normpath(p).replace("\\", "/")
    return p.casefold().rstrip("/") or "/"


def within(p, base):
    return p == base or p.startswith(base.rstrip("/") + "/")


def resolve(token, cwd, ctx):
    """Absolute path for a path-like token (relative to cwd; cwd None = repo root)."""
    t = token.strip("'\"`,;()[]{}<>|")
    if "=" in t and not t.startswith("="):
        t = t.split("=", 1)[1]
    t = re.sub(r"^(\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_][A-Za-z0-9_]*%)[/\\]", "", t)  # $VAR/... -> repo-relative
    if not t or t in ("-", "--") or re.search(r"[|^\[\](){}<>\s]", t):
        return None  # regex text, a pipe, a group: not a path
    t2 = t.replace("\\", "/")
    if re.match(r"^[a-zA-Z]:/", t2) or t2.startswith("/") or t2.startswith("~"):
        return norm_abs(t2)
    return norm_abs(f"{cwd or ctx.root}/{t2}")


def gmatch(rel, pattern):
    """Glob match with ** (any depth) and * (one segment); a dir pattern 'x/**' also matches 'x'."""
    pattern = pattern.casefold()
    if pattern.endswith("/**") and (rel == pattern[:-3] or rel.startswith(pattern[:-3] + "/")):
        return True
    rx = re.escape(pattern).replace(r"\*\*/", "(.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.fullmatch(rx, rel) is not None


def block_prefixes(ctx):
    """Literal folder prefixes of the read blocks (e.g. 'private', 'vendor/method-lab')."""
    pats = list(ctx.read_blocks) + (["private/**"] if ctx.subagent else [])
    return [re.split(r"[*?\[]", p.casefold())[0].rstrip("/") for p in pats]


def above_blocked(abs_path, ctx):
    """True if a recursive search from this folder would reach a read-blocked area."""
    rel = ctx.rel(abs_path)
    if rel is None:
        return within(ctx.root, abs_path)
    return any(pre and (rel == "" or pre == rel or pre.startswith(rel + "/")) for pre in block_prefixes(ctx))


def is_ancestor(rel, pattern):
    """True if rel is a folder above (not inside) something the protected pattern matches."""
    segs, parts = pattern.casefold().split("/"), ([] if rel == "" else rel.split("/"))
    return len(parts) < len(segs) and all(fnmatch.fnmatch(a, b) for a, b in zip(parts, segs))


def classify(abs_path, ctx):
    """Flags for one absolute path: protected, holds_protected, read_blocked, read_only_area,
    private, secret."""
    flags = set()
    if SECRET_NAME.match(abs_path.rsplit("/", 1)[-1]):
        flags.add("secret")
    rel = ctx.rel(abs_path)
    if rel is None:
        roots = ctx.no_write_roots + ctx.source_roots
        if any(within(abs_path, r) for r in roots):
            flags.add("protected")
        elif any(within(r, abs_path) for r in roots + [ctx.root]):
            flags.add("holds_protected")  # a folder above the repo or a no-write root
        if any(fnmatch.fnmatch(abs_path, t) for t in FOREIGN_TAILS):
            flags.add("protected")
        return flags
    pats = ALWAYS + (OPERATE if ctx.operate else [])
    if any(fnmatch.fnmatch(rel, p.casefold()) for p in pats):
        flags.add("protected")
    elif any(is_ancestor(rel, p) for p in pats):
        flags.add("holds_protected")  # e.g. the repo root, jobs/<id>/, .lab's parent
    if rel == "private" or rel.startswith("private/"):
        flags.add("private")
    in_job = ctx.job_folder and (rel == ctx.job_folder or rel.startswith(ctx.job_folder + "/"))
    if not in_job:
        if any(gmatch(rel, p) for p in ctx.read_blocks) and not any(gmatch(rel, p) for p in ctx.read_only):
            flags.add("read_blocked")
        if any(gmatch(rel, p) for p in ctx.read_only):
            flags.add("read_only_area")
        if ctx.subagent and "private" in flags:
            flags.add("read_blocked")
    return flags


# ---------- shell analysis ----------

def tokenize(cmd, powershell=False):
    """Split into segments: [(words, redirect_targets)]. Separators (; && || | & newline) split
    only outside quotes. Raises Unparseable (unbalanced quotes and the like)."""
    try:
        lex = shlex.shlex(cmd.replace("\r", ""), posix=not powershell, punctuation_chars=";&|<>\n")
        lex.whitespace = " \t"
        lex.whitespace_split = True
        lex.commenters = ""
        toks = list(lex)
    except ValueError as e:
        raise Unparseable(str(e))
    segs, cur, reds, i = [], [], [], 0
    while i < len(toks):
        tok = toks[i]
        if tok and set(tok) <= set(";&|\n"):
            segs.append((cur, reds))
            cur, reds = [], []
        elif tok and set(tok) <= set("<>&") and (">" in tok or "<" in tok):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if ">" in tok:
                if cur and re.fullmatch(r"\d", cur[-1]):  # the fd number of "2>"
                    cur.pop()
                reds.append(nxt)
            i += 1                                          # skip the target (or heredoc delimiter)
        else:
            cur.append(tok)
        i += 1
    segs.append((cur, reds))
    return [(w, r) for w, r in segs if w or r]


def base(word):
    return word.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].casefold()


def nested_command(words):
    """(inner command string, is_powershell) for bash -c / powershell -Command / cmd /c / wsl, else None."""
    head = base(words[0])
    if head in NESTED_SH:
        for i, w in enumerate(words[1:], 1):
            if re.fullmatch(r"-[a-z]*c[a-z]*", w) and i + 1 < len(words):
                return words[i + 1], False
        return None
    if head in NESTED_PS:
        for i, w in enumerate(words[1:], 1):
            if w.casefold() in ("-command", "-c") and i + 1 < len(words):
                return " ".join(words[i + 1:]), True
        return None
    if head in NESTED_CMD:
        for i, w in enumerate(words[1:], 1):
            if w.casefold() in ("/c", "/k") and i + 1 < len(words):
                return " ".join(words[i + 1:]), False
        return None
    if head in NESTED_WSL:
        i = 1
        while i < len(words) and words[i].startswith("-") and words[i] != "--":
            i += 2 if words[i] in ("-d", "--distribution", "-u", "--user", "--cd") else 1
        if i < len(words) and words[i] in ("--", "-e", "--exec"):
            i += 1
        rest = words[i:]
        return (shlex.join(rest), False) if rest else None
    return None


def segment_read_only(words, reds, ctx, depth):
    if any(r.casefold() not in HARMLESS_TARGETS for r in reds):
        return False
    if not words:
        return True
    # H1 (T1.3): a bare string separator just prints itself. Top level only (inside -Command it is code),
    # and never with an & anywhere (the call operator & "x.ps1" runs the string).
    if ctx.tool == "PowerShell" and depth == 0 and "&" not in (ctx.ti.get("command") or "") \
            and len(words) == 1 and not reds and BARE_STRING.fullmatch(words[0]):
        return True
    inner = nested_command(words)
    if inner is not None:
        return command_read_only(inner[0], ctx, depth + 1, powershell=inner[1])
    head = base(words[0])
    if head in INTERPRETERS and len(words) > 1:
        if all(w.casefold() in ("--version", "-v", "-vv", "-3", "-0", "-0p") for w in words[1:]):
            return True  # version and launcher listings
        script = next((w for w in words[1:] if not w.startswith("-")), "").replace("\\", "/")
        return any(script.casefold().endswith(t) for t in ENGINE_TOOLS) and "-c" not in words
    if head == "git":
        rest, sub = words[1:], ""
        while rest:
            if rest[0] in GIT_GLOBAL_UNSAFE or rest[0].startswith("--config-env"):
                return False                     # git -c / --config-env can run any program
            if rest[0] in ("-C", "--git-dir", "--work-tree", "--namespace"):
                rest = rest[2:]
            elif rest[0].startswith("-"):
                rest = rest[1:]
            else:
                sub = rest[0]
                rest = rest[1:]
                break
        if sub.casefold() not in READ_ONLY_GIT:
            return False
        return not any(w in GIT_UNSAFE or w.startswith(GIT_UNSAFE_PREFIXES) for w in rest)
    if head in READ_ONLY:
        if any(w.casefold() in WRITE_FLAGS or w.casefold().startswith(WRITE_FLAG_PREFIXES) for w in words[1:]):
            return False
        if head == "uniq" and len([w for w in words[1:] if not w.startswith("-")]) >= 2:
            return False                         # uniq IN OUT writes OUT
        return True
    return False


def command_read_only(cmd, ctx, depth=0, powershell=False):
    if depth > 5:
        return False
    try:
        segs = tokenize(cmd, powershell)
    except Unparseable:
        return False
    return all(segment_read_only(w, r, ctx, depth) for w, r in segs)


def walk_segments(cmd, depth=0, powershell=False):
    """Yield (words, redirects) for every segment, including nested shell strings."""
    if depth > 5:
        raise Unparseable("nesting too deep")
    for words, reds in tokenize(cmd, powershell):
        yield words, reds
        if words:
            inner = nested_command(words)
            if inner is not None:
                yield from walk_segments(inner[0], depth + 1, powershell=inner[1])


def shell_paths(cmd, ctx):
    """Every path-like chunk of the command, resolved (cd is followed where it can be)."""
    out, cwd = [], ctx.cwd
    try:
        segs = list(walk_segments(cmd, powershell=ctx.tool == "PowerShell"))
    except Unparseable:
        segs = [([c for c in PATH_CHUNK.findall(cmd)], [])]
    for words, reds in segs:
        if words and base(words[0]) in ("cd", "set-location", "sl", "pushd") and len(words) > 1:
            target = words[1]
            cwd = None if re.search(r"[$%]", target) else resolve(target, cwd, ctx)
            continue
        if words and base(words[0]) == "git":
            out += git_paths(words, reds, cwd, ctx)
            continue
        known = bool(words) and base(words[0]) in READ_ONLY
        for w in words + reds:
            # Arguments of read-only commands are taken whole (a grep pattern is not a path);
            # anything else (inline code, heredoc bodies, unknown commands) is scanned chunk by chunk.
            # A bare "." or ".." inside text or code is too ambiguous to mean the repo root; as a whole
            # argument (rm -rf .) it does. Residual risk: inline code like rmtree('.') is not caught.
            pieces = [w] if known and w not in reds else [w] + [c for c in PATH_CHUNK.findall(w) if not re.fullmatch(r"[./\\]+", c)]
            for chunk in pieces:
                bare = chunk[2:] if re.match(r"^-[A-Za-z].", chunk) else ""  # -r<path>, -I<path>
                for c in {chunk, bare} - {""}:
                    p = resolve(c, cwd, ctx)  # cwd None (e.g. cd "$VAR"): resolved against the repo root
                    if p:
                        out.append(p)
    return out


GIT_PATH_OPTIONS = ("-C", "--git-dir", "--work-tree")
GIT_VALUE_OPTIONS = ("--namespace", "--exec-path", "--list-cmds", "--super-prefix")


def git_paths(words, reds, cwd, ctx):
    """H4 (T1.5): a git command's paths, resolved as git resolves them. Each -C changes the folder the
    following -C, --git-dir, --work-tree and path arguments are read from (a relative -C after another is
    relative to it); with --work-tree, every argument is also read against the work tree (both readings
    are classified). Redirections stay relative to the shell's folder. Fails closed: -c and --config-env
    (they can run any program), a path option without a plain value (variables, wildcards, substitution,
    a missing value, a glued -Cpath) and a relative -C from an unknown folder are blocked."""
    here, trees, out, i = cwd, [], [], 1
    while i < len(words):
        w = words[i]
        if w in GIT_GLOBAL_UNSAFE or w.startswith("--config-env") or re.match(r"^-c.", w):
            raise Blocked("git -c / --config-env can set options that run any program: not allowed.")
        opt = next((o for o in GIT_PATH_OPTIONS if w == o or (o != "-C" and w.startswith(o + "="))), None)
        if opt is None and w.startswith("-C"):
            raise Blocked(f"git option {w!r} could not be parsed (failing closed); write -C <folder>.")
        if opt:
            if "=" in w:
                val = w.split("=", 1)[1]
            elif i + 1 < len(words):
                val, i = words[i + 1], i + 1
            else:
                raise Blocked(f"git {opt} has no value (failing closed).")
            t = val.replace("\\", "/")
            absolute = re.match(r"^[a-zA-Z]:/", t) or t.startswith(("/", "~"))
            if not val or re.search(r"[$%`*?\[\]{}]", val) or (here is None and not absolute):
                raise Blocked(f"git {opt} {val!r} could not be resolved to one folder (failing closed).")
            p = resolve(val, here, ctx)
            if p is None:
                raise Blocked(f"git {opt} {val!r} could not be resolved to one folder (failing closed).")
            out.append(p)
            if opt == "-C":
                here = p
            elif opt == "--work-tree":
                trees.append(p)
        elif w in GIT_VALUE_OPTIONS:
            i += 1
        elif not w.startswith("-"):
            break                                # the subcommand
        i += 1
    for w in words[i:]:
        bare = w[2:] if re.match(r"^-[A-Za-z].", w) else ""
        for c in {w, bare} - {""}:
            for d in [here] + trees:
                p = resolve(c, d, ctx)
                if p:
                    out.append(p)
    for w in reds:
        p = resolve(w, cwd, ctx)
        if p:
            out.append(p)
    return out


def executes_gate(words):
    # H3 (T1.3): the file name must be exactly gate.py (any case, any path form); demo_gate.py is not it.
    # Bash tokenizing drops backslashes (.\gate.py becomes .gate.py), so a dot before the name counts too.
    if not words:
        return False
    is_gate = lambda w: re.search(r"(^|[\\/.])gate\.py$", w.strip("'\"").casefold()) is not None
    if is_gate(words[0]):
        return True
    if base(words[0]) in INTERPRETERS:
        return any(is_gate(w) for w in words[1:])
    return False


def commit_message_only(cmd, ps):
    """H2 (T1.3): True only if the command is one `git commit` whose obfuscation-pattern hits (e.g. the
    word "eval") all sit inside its single literal -m argument. Fails closed: substitution anywhere,
    a second segment, -F/--file, a redirection or anything unparseable gives False."""
    if "$" in cmd or "`" in cmd:
        return False
    try:
        segs = tokenize(cmd, ps)
    except Unparseable:
        return False
    if len(segs) != 1 or segs[0][1]:
        return False
    words = segs[0][0]
    if len(words) < 4 or words[0] != "git" or words[1] != "commit":
        return False
    flags = [w for w in words[2:] if w.startswith("-")]
    if any(w.startswith("--file") or (w != "-m" and re.fullmatch(r"-[A-Za-z]*[mF].*", w)) for w in flags):
        return False                             # -F, --file, -Fmsg, -am, -mmsg: only a bare -m is accepted
    m = [i for i, w in enumerate(words) if w == "-m" or w.startswith("--message")]
    if len(m) != 1 or words[m[0]] != "-m" or m[0] + 1 >= len(words):
        return False
    rest = words[:m[0]] + words[m[0] + 2:]
    return not OBFUSCATION.search(" ".join(rest))


def inline_code(segs, cmd, ps):
    """Text of inline interpreter code in the command: -c / -e / -Command arguments, heredoc bodies
    fed to an interpreter, and PowerShell script blocks."""
    code = []
    for i, (words, _) in enumerate(segs):
        if not words:
            continue
        head = base(words[0])
        if head in INTERPRETERS:
            for j, w in enumerate(words[1:], 1):
                if w in ("-c", "-e", "--eval", "-p", "--print", "-") and j + 1 < len(words):
                    code.append(" ".join(words[j + 1:]))
            if "<<" in cmd:                      # heredoc: the body follows as later segments
                code += [" ".join(w) for w, _ in segs[i + 1:]]
        if head in NESTED_PS:                    # powershell -Command "<script>"
            for j, w in enumerate(words[1:], 1):
                if w.casefold() in ("-command", "-c") and j + 1 < len(words):
                    code.append(" ".join(words[j + 1:]))
    if ps:
        code += re.findall(r"\{[^{}]*\}", cmd)  # script blocks: & { ... }, ForEach-Object { ... }
    return "\n".join(code)


def check_shell(ctx):
    cmd = ctx.ti.get("command", "") or ""
    ps = ctx.tool == "PowerShell"
    if OBFUSCATION.search(cmd) and not commit_message_only(cmd, ps):
        raise Blocked("eval / iex / Invoke-Expression / base64 decoding and encoded commands are not allowed.")
    try:
        segs = list(walk_segments(cmd, powershell=ps))
        parsed = True
    except Unparseable:
        segs, parsed = [], False
    if not parsed:
        if re.search(r"(?<![\w-])gate\.py", cmd, re.IGNORECASE):
            raise Blocked("engine/gate.py is human-only (command could not be parsed; failing closed).")
        if re.search(r"\bgit\b.*\bpush\b", cmd):
            raise Blocked("git push is disabled (command could not be parsed; failing closed).")
        if re.search(r"\bgit\b", cmd) and re.search(r"(^|\s)(-C|-c|--git-dir|--work-tree|--config-env)(\s|=|$)", cmd):
            raise Blocked("a git command with -C, -c, --git-dir or --work-tree could not be parsed (H4, failing closed).")
    code = inline_code(segs, cmd, ps)
    if code and DELETE_CALL.search(code):
        raise Blocked("inline interpreter code that deletes files is not allowed, whatever path it names.")
    # Bash tokenizing turns C:\x\gate.py into C:xgate.py, so interpreter commands are also checked on the raw text.
    runs_code = any(words and base(words[0]) in INTERPRETERS for words, _ in segs)
    for words, _ in segs:
        if executes_gate(words) or (runs_code and re.search(r"(?<![\w-])gate\.py", cmd, re.IGNORECASE)):
            raise Blocked("engine/gate.py is human-only. Ask the approver to run it in their own terminal.")
        if words and base(words[0]) == "git" and "push" in [w.casefold() for w in words[1:]]:
            raise Blocked("git push is disabled: this repo runs local-only.")
        if any(SECRET_NAME.match(base(w)) for w in words[1:]):
            raise Blocked("reading secrets (.env, master.key) is not allowed.")
    flags = set()
    for p in shell_paths(cmd, ctx):
        flags |= classify(p, ctx)
    ctx.touches_private = "private" in flags
    if "secret" in flags and not parsed:
        raise Blocked("reading secrets (.env, master.key) is not allowed.")
    if "read_blocked" in flags:
        raise Blocked("this command names a path you may not read (role read block).")
    if ctx.read_blocks or ctx.subagent:
        recursive = re.compile(r"^(-[a-z]*r[a-z]*|-R|--recursive|-recurse|/s)$", re.IGNORECASE)
        for words, _ in segs:
            if words and base(words[0]) in ("grep", "rg", "findstr", "select-string", "sls", "get-childitem", "gci", "ls", "dir", "find", "cat", "get-content", "gc") \
                    and (base(words[0]) in ("rg", "find") or any(recursive.match(w) for w in words[1:])):
                targets = [resolve(w, ctx.cwd, ctx) for w in words[1:] if not w.startswith("-") and not w.startswith("/")] or [ctx.cwd]
                if any(p and above_blocked(p, ctx) for p in targets):
                    raise Blocked("recursive search from a folder that contains a read-blocked area; search a narrower path")
    if flags & {"protected", "holds_protected", "read_only_area"}:
        if SUBST.search(cmd):
            raise Blocked("command substitution in a command that names a protected path (failing closed).")
        if not parsed or not command_read_only(cmd, ctx, powershell=ps):
            raise Blocked("this command names a protected path and is not entirely read-only. "
                          "Use engine/state.py for state changes; framework files are locked in operate mode.")
    for entry in gated_actions().get("shell", []):
        if re.search(entry["pattern"], cmd.replace("\\", "/")):
            why = condition_error(entry, ctx)
            if why:
                raise Blocked(f"{entry.get('reason') or entry['pattern']}: {why}")


# ---------- tools ----------

def tool_paths(ctx):
    ti = ctx.ti
    raw = [ti.get(k) for k in ("file_path", "notebook_path", "path") if isinstance(ti.get(k), str) and ti.get(k)]
    if ctx.tool == "Glob" and isinstance(ti.get("pattern"), str):
        raw.append(f"{ti.get('path') or ''}/{ti['pattern']}".lstrip("/") if not re.match(r"^([a-zA-Z]:|/)", ti["pattern"]) else ti["pattern"])
    return [resolve(r, ctx.cwd, ctx) for r in raw if resolve(r, ctx.cwd, ctx)]


def check_write(ctx):
    paths = tool_paths(ctx)
    if not paths:
        raise Blocked("write with no target path (failing closed).")
    for p in paths:
        rel = ctx.rel(p)
        if rel is None:
            if ctx.scratch and within(p, ctx.scratch):
                continue
            raise Blocked(f"write outside the repo: {p}")
        flags = classify(p, ctx)
        ctx.touches_private |= "private" in flags
        if "protected" in flags:
            raise Blocked(f"{rel} is protected (state/gates change only via scripts; framework files are locked in operate mode)")
        if flags & {"read_blocked", "read_only_area"}:
            raise Blocked(f"{rel} may not be written by this session or agent (role read/write block)")


def check_read(ctx):
    paths = tool_paths(ctx)
    if ctx.tool == "Grep" and (ctx.read_blocks or ctx.subagent):
        targets = paths or [ctx.cwd]                     # Grep with no path searches the working folder
        if any(above_blocked(p, ctx) for p in targets):
            raise Blocked("content search from a folder that contains a read-blocked area; search a narrower path")
    for p in paths:
        flags = classify(p, ctx)
        ctx.touches_private |= "private" in flags
        if "secret" in flags:
            raise Blocked("reading secrets (.env, master.key) is not allowed.")
        if "read_blocked" in flags:
            raise Blocked(f"{ctx.rel(p) or p} may not be read by this session or agent (role read block)")


def gated_actions():
    f = lc.CONFIG / "gated-actions.json"
    return lc.load_json(f) if f.exists() else {}


def condition_error(entry, ctx=None):
    """None if the entry's conditions hold (caller role, active job), else the reason."""
    if "roles" in entry:
        role = "subagent" if ctx is not None and ctx.subagent else "main"
        if role not in entry["roles"]:
            return f"only for {entry['roles']} (this call is from a {role})"
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
        ok, chain = lc.verify_chain(job, entry["gate"])
        if not ok:
            return f"needs a valid {entry['gate']} approval chain: " + lc._broken(chain)
    return None


def check_mcp(ctx):
    entry = next((e for e in gated_actions().get("mcp", []) if fnmatch.fnmatchcase(ctx.tool, e["tool"])), None)
    if entry is None:
        raise Blocked(f"MCP tool {ctx.tool} is not allowed (not listed in config/gated-actions.json).")
    why = condition_error(entry, ctx)
    if why:
        raise Blocked(f"MCP tool {ctx.tool}: {why}")


def check_agent(ctx):
    job = lc.active_job()
    if not job:
        return
    try:
        if lc.load_state(job)["state"] in lc.TERMINAL:
            return
    except (lc.LabError, KeyError, ValueError, OSError):
        pass                                                    # unreadable job: treat as active
    if ctx.ti.get("run_in_background") is not False:
        raise Blocked(f"job {job} is active: subagent calls must run in the foreground so their usage is "
                      "recorded; set run_in_background to false (a call that doesn't say may run in the background).")


def decide(data):
    ctx = Ctx(data)
    try:
        if ctx.tool in AGENT_TOOLS:
            check_agent(ctx)
        elif ctx.tool in WRITE_TOOLS:
            check_write(ctx)
        elif ctx.tool in READ_TOOLS:
            check_read(ctx)
        elif ctx.tool in SHELL_TOOLS:
            check_shell(ctx)
        elif ctx.tool.startswith("mcp__"):
            check_mcp(ctx)
        return None, ctx
    except Blocked as b:
        return str(b), ctx


def log_block(msg, data, ctx=None):
    private = (ctx is not None and (ctx.touches_private or ctx.job_folder)) or active_internal_job_folder()
    d = lc.ROOT / "private" / "logs" if private else lc.ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "blocked.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": lc.now(), "reason": msg, "tool": data.get("tool_name"),
                             "agent": data.get("agent_type"), "input": data.get("tool_input")}) + "\n")


def run(raw):
    """Decide one tool call. Returns 0 (allow) or 2 (block)."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except ValueError:
        log_block("hook could not parse tool-call input (failing closed).", {})
        print("BLOCKED by engine guardrail: hook could not parse tool-call input (failing closed).", file=sys.stderr)
        return 2
    msg, ctx = decide(data)
    if msg is None:
        return 0
    log_block(msg, data, ctx)
    print(f"BLOCKED by engine guardrail: {msg}", file=sys.stderr)
    return 2


def main():
    sys.exit(run(sys.stdin.buffer.read().decode("utf-8", errors="replace")))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as exc:  # fail closed on any unexpected error
        print(f"BLOCKED by engine guardrail: hook error ({exc!r}); failing closed.", file=sys.stderr)
        sys.exit(2)
