#!/usr/bin/env python3
"""Publish check (stdlib only, T0.19): nothing private may reach a commit or a push.

  python engine/publish_check.py                 # every tracked file (working copy), paths and contents
  python engine/publish_check.py --staged        # what is staged (pre-commit hook)
  python engine/publish_check.py --message FILE  # a commit message (commit-msg hook)
  python engine/publish_check.py --push          # every commit being pushed (pre-push hook; refs on stdin)
  python engine/publish_check.py --history       # every line ever added and every commit message
  python engine/publish_check.py install         # install the three Git hooks

Checks file contents, file paths and names, and commit messages for:
- denylist terms (private/denylist.txt, untracked, written by the approver): one term per line, whole
  word and any case by default; "case: Term" for an exact-case match; "#" starts a comment;
- secrets (key formats, private-key blocks, long values assigned to key/token/password names);
- the source folders' absolute paths (config/protected-paths.local.json) and any home-folder path;
- email addresses outside the allowed domains (config/publish.json);
- tracked paths that must never be published (vendor/, private/, cache/, .env*, *.local.json).
Fails closed: a missing or unreadable denylist, zero files scanned (tree and history), or a Git error is a
failure. Findings name the place and the kind; secret values are never printed in full. Exit 0 clean, 1 not.
"""
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
ZERO = "0" * 40

SECRETS = [
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("assigned secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b[\"']?\s*[:=]\s*[\"']?"
                                   r"[A-Za-z0-9_\-/+=]{20,}")),
]
HOME_PATH = re.compile(r"(?i)\b[a-z]:[\\/]+(?:\\\\)?users[\\/]+(?:\\\\)?(?!public\b|default\b)[a-z0-9][^\\/\s'\"`<>|]*"
                       r"|/(?:mnt/)?c/users/(?!public\b)[a-z0-9][^/\s'\"`<>|]*")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")


class Fail(Exception):
    pass


def git(*args, root=None, check=True):
    p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(root or ROOT), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise Fail(f"git {' '.join(args[:2])} failed: {p.stderr.strip()[:200]}")
    return p.stdout


def git_bytes(*args, root=None):
    p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(root or ROOT), *args], capture_output=True)
    if p.returncode != 0:
        raise Fail(f"git {' '.join(args[:2])} failed: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return p.stdout


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else {}


# ---------- rules ----------

class Rules:
    def __init__(self, root=None):
        self.root = Path(root or ROOT)
        cfg = load_json(self.root / "config" / "publish.json")
        dl = self.root / cfg.get("denylist", "private/denylist.txt")
        try:
            text = dl.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise Fail(f"denylist {cfg.get('denylist', 'private/denylist.txt')} missing or unreadable "
                       f"({type(e).__name__}): the approver writes it; nothing is checked without it") from None
        self.terms = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            exact = line.lower().startswith("case:")
            term = line[5:].strip() if exact else line
            if term:
                rx = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
                self.terms.append((term, re.compile(rx) if exact else re.compile(rx, re.IGNORECASE)))
        if not self.terms:
            raise Fail("the denylist has no terms: nothing would be checked")
        self.allowed_domains = [d.lower() for d in cfg.get("allowed_email_domains", [])]
        self.forbidden_dirs = cfg.get("forbidden_dirs", ["vendor/", "private/", "cache/"])
        self.forbidden_names = cfg.get("forbidden_names", [".env*", "*.local.json"])
        local = load_json(self.root / "config" / "protected-paths.local.json")
        self.source_roots = [r for r in local.get("source_roots", []) if r]

    def email_ok(self, domain):
        d = domain.lower()
        return any(d == a or d.endswith("." + a) for a in self.allowed_domains)

    def text_findings(self, text, where):
        out = []
        for term, rx in self.terms:
            if rx.search(text):
                out.append((where, "denylist term", term))
        for label, rx in SECRETS:
            m = rx.search(text)
            if m:
                out.append((where, "secret", f"{label} ({m.group(0)[:6]}...)"))
        low = text.lower().replace("\\\\", "\\")
        for r in self.source_roots:
            for form in {r.lower(), r.lower().replace("/", "\\"), r.lower().replace("\\", "/")}:
                if form in low:
                    out.append((where, "source folder path", "a source folder's absolute path"))
                    break
        if HOME_PATH.search(text):
            out.append((where, "home-folder path", HOME_PATH.search(text).group(0)[:40]))
        for m in EMAIL.finditer(text):
            if not self.email_ok(m.group(1)):
                out.append((where, "email address", f"...@{m.group(1)}"))
                break
        return out

    def path_findings(self, path):
        out = [(path, *f[1:]) for f in self.text_findings(path, path)]
        if any(path == d.rstrip("/") or path.startswith(d) for d in self.forbidden_dirs):
            out.append((path, "forbidden path", "this folder is never published"))
        name = path.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(name, g) for g in self.forbidden_names):
            out.append((path, "forbidden file", "this kind of file is never published"))
        return out


def is_binary(data):
    return b"\0" in data[:8192]


def content_findings(rules, path, data):
    if is_binary(data):
        return []
    return rules.text_findings(data.decode("utf-8", errors="replace"), path)


# ---------- modes ----------

def scan_tree(rules):
    files = [f for f in git("ls-files", "-z", root=rules.root).split("\0") if f]
    findings = []
    for f in files:
        findings += rules.path_findings(f)
        p = rules.root / f
        if p.is_file():
            findings += content_findings(rules, f, p.read_bytes())
    if not files:
        raise Fail("scanned zero files: nothing is tracked, or Git could not list them")
    return len(files), findings


def scan_staged(rules):
    names = [f for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z",
                            root=rules.root).split("\0") if f]
    findings = []
    for f in names:
        findings += rules.path_findings(f)
        findings += content_findings(rules, f, git_bytes("show", f":{f}", root=rules.root))
    return len(names), findings


def scan_message(rules, text, where="commit message"):
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    return rules.text_findings(body, where)


def scan_commit(rules, sha):
    """Findings in one commit: its message, the paths it touches and every line it adds."""
    out = scan_message(rules, git("log", "-1", "--format=%B", sha, root=rules.root), f"commit {sha[:10]} message")
    raw = git_bytes("show", "--no-color", "--format=", "-p", "--no-renames", sha, root=rules.root)
    path = None
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.startswith("+++ "):
            p = line[4:]
            path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
            if path:
                out += [(f"commit {sha[:10]} {path}", *f[1:]) for f in rules.path_findings(path)]
        elif line.startswith("+") and path:
            out += rules.text_findings(line[1:], f"commit {sha[:10]} {path}")
    return out


def scan_history(rules):
    shas = [s for s in git("rev-list", "--all", root=rules.root).split() if s]
    if not shas:
        raise Fail("scanned zero commits")
    findings = []
    for s in shas:
        findings += scan_commit(rules, s)
    return len(shas), findings


def scan_push(rules, stdin_text):
    shas = []
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts
        if local_sha == ZERO:
            continue                                         # a deletion pushes no content
        rng = [local_sha, "--not", "--remotes"] if remote_sha == ZERO else [f"{remote_sha}..{local_sha}"]
        shas += [s for s in git("rev-list", *rng, root=rules.root).split() if s not in shas]
    findings = []
    for s in shas:
        findings += scan_commit(rules, s)
    return len(shas), findings


# ---------- hooks ----------

HOOKS = {"pre-commit": "--staged", "commit-msg": '--message "$1"', "pre-push": "--push"}
MARK = "# installed by engine/publish_check.py"


def install(root=None):
    root = Path(root or ROOT)
    hooks = Path(git("rev-parse", "--git-path", "hooks", root=root).strip())
    hooks = hooks if hooks.is_absolute() else root / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    py = "py -3" if sys.platform == "win32" else "python3"
    for name, arg in HOOKS.items():
        f = hooks / name
        if f.exists() and MARK not in f.read_text(encoding="utf-8", errors="replace"):
            raise Fail(f"{f.name} hook already exists and was not installed by this script; merge it by hand")
        # Fails closed: if Python can't start, the shell returns non-zero and Git refuses.
        f.write_bytes((f"#!/bin/sh\n{MARK}\nexec {py} \"$(git rev-parse --show-toplevel)/engine/publish_check.py\" "
                       f"{arg}\n").encode())
        f.chmod(0o755)
    return [hooks / n for n in HOOKS]


def hooks_installed(root=None):
    root = Path(root or ROOT)
    try:
        hooks = Path(git("rev-parse", "--git-path", "hooks", root=root).strip())
    except Fail:
        return None
    hooks = hooks if hooks.is_absolute() else root / hooks
    return {n: (hooks / n).is_file() and MARK in (hooks / n).read_text(encoding="utf-8", errors="replace")
            for n in HOOKS}


# ---------- main ----------

def report(kind, n, findings, out=print):
    for where, what, detail in findings:
        out(f"FINDING {what}: {where}: {detail}")
    out(f"publish check ({kind}): {n} scanned, {len(findings)} finding(s): {'BLOCKED' if findings else 'OK'}")
    return 1 if findings else 0


def main(argv=None, root=None, out=print, stdin=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ["install"]:
            for f in install(root):
                out(f"installed {f.name} hook")
            return 0
        rules = Rules(root)
        if "--staged" in argv:
            return report("staged", *scan_staged(rules), out=out)
        if "--message" in argv:
            f = argv[argv.index("--message") + 1]
            return report("message", 1, scan_message(rules, Path(f).read_text(encoding="utf-8", errors="replace")),
                          out=out)
        if "--push" in argv:
            return report("push", *scan_push(rules, stdin if stdin is not None else sys.stdin.read()), out=out)
        if "--history" in argv:
            return report("history", *scan_history(rules), out=out)
        return report("tracked files", *scan_tree(rules), out=out)
    except (Fail, IndexError) as e:
        out(f"publish check FAILED (closed): {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
