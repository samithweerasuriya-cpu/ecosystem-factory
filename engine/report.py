#!/usr/bin/env python3
"""Status export for the progress dashboard (T1.7, stdlib only).

  python engine/report.py --json [--root DIR ...] [--out FILE]

Reads one or more trees (the factory by default; a generated ecosystem or an archived one with --root) and
writes one JSON file, private/reports/export-<UTC time>.json, that matches schemas/report-export.schema.json:
engine version and test counts (logs/tests-last.json, written by a full run_tests.py run), jobs, the event
timeline, usage per call and per job and agent, and evaluation results per report and case (k of n).

IDs, counts and numbers only. Every field is copied on purpose (an allowlist) and every text value must match
an ID pattern; notes, answers, questions, paths and actor names never leave the logs (an actor becomes a role).
Internal jobs (private/jobs/) are left out and only counted. Timestamps are UTC with a trailing Z.

Fails closed (lesson 6): a missing root, or a missing or unreadable state, log, report, VERSION or test-result
file is an error naming the file, and nothing is written. Lesson 15: a call counts only when its job's call
record and logs/usage.jsonl agree (otherwise it is "unbacked" and left out of the totals); an evaluation report
on config/invalid-reports.json, or one whose run records fail engine/evalcheck.py's check, has backing
"invalid": it is listed in eval_runs but its cases are not in eval_cases, so it is never counted or charted.
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import labcore as lc  # noqa: E402
import evalcheck  # noqa: E402
import schemacheck  # noqa: E402

SCHEMA = "schemas/report-export.schema.json"
EXPORT_VERSION = 1
PATTERNS = {
    "label": evalcheck.TREE_RE,
    "job_id": lc.JOB_ID_RE,
    "call_id": re.compile(r"^C\d{3,}$"),
    "name": re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"),
    "event": re.compile(r"^[a-z][a-z_]*$"),
    "state": re.compile(r"^[A-Z][A-Z_]*$"),
    "model": re.compile(r"^[a-z0-9][a-z0-9.-]*$"),
    "source": re.compile(r"^[a-z][a-z_]*$"),
    "version": re.compile(r"^\d+\.\d+\.\d+$"),
    "cli_version": re.compile(r"^\d+\.\d+\.\d+( \(Claude Code\))?$"),
    "report_id": evalcheck.REPORT_ID_RE,
    "case_id": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"),
    "kind": re.compile(r"^[a-z][a-z-]*$"),
    "mode": re.compile(r"^[a-z]+(-partial)?$"),
}
# Who wrote a log line, as a role. Any other actor is a person and is allowed only on a human-only event.
MACHINE_ACTORS = {"orchestrator": "orchestrator", "manual": "orchestrator", "script": "script",
                  "headless": "script", "post_tool_use": "script", "test": "script"}
HUMAN_EVENTS = {"approve", "reject", "hold", "relink", "ceiling", "resume"}
TOKEN_KEYS = ("input", "output", "cache_read", "cache_write", "total")


class ExportError(lc.LabError):
    pass


class Tree:
    def __init__(self, path, home):
        self.path = Path(path).resolve()
        self.label = self.path.name
        self.home = home

    def fail(self, rel, why):
        raise ExportError(f"{self.label}: {rel}: {why}")

    def ident(self, kind, value, rel):
        """The value if it is a valid ID of this kind; otherwise an error that never quotes the value."""
        if isinstance(value, str) and PATTERNS[kind].fullmatch(value):
            return value
        self.fail(rel, f"a {kind} value is not a valid ID")

    def opt(self, kind, value, rel):
        return None if value is None else self.ident(kind, value, rel)

    def count(self, value, rel, what):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        self.fail(rel, f"{what} is not a whole number")

    def number(self, value, rel, what, allow_none=False):
        if value is None and allow_none:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return value
        self.fail(rel, f"{what} is not a number")

    def utc(self, value, rel):
        try:
            t = datetime.datetime.fromisoformat(value)
        except (TypeError, ValueError):
            self.fail(rel, "a timestamp is not ISO 8601")
        if t.tzinfo is None:
            self.fail(rel, "a timestamp has no time zone")
        return z(t)

    def read_json(self, rel):
        f = self.path / rel
        if not f.is_file():
            self.fail(rel, "missing")
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            self.fail(rel, f"unreadable ({type(e).__name__})")

    def read_jsonl(self, rel):
        f = self.path / rel
        if not f.is_file():
            self.fail(rel, "missing")
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            self.fail(rel, f"unreadable ({type(e).__name__})")
        out = []
        for n, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                self.fail(rel, f"line {n} is not JSON")
            if not isinstance(entry, dict):
                self.fail(rel, f"line {n} is not an object")
            out.append((n, entry))
        return out

    def version(self):
        f = self.path / "engine" / "VERSION"
        try:
            v = f.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            self.fail("engine/VERSION", "missing or unreadable")
        return self.ident("version", v, "engine/VERSION")


def z(t):
    t = t.astimezone(datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S") + (f".{t.microsecond // 1000:03d}" if t.microsecond else "") + "Z"


def tests_meta(home, version):
    rel = "logs/tests-last.json"
    t = home.read_json(rel)
    if not isinstance(t, dict):
        home.fail(rel, "not an object")
    if t.get("engine_version") != version:
        home.fail(rel, f"made with another engine version; run the full suite (engine/run_tests.py) on {version}")
    if t.get("tier") != "full":
        home.fail(rel, "not from a full run")
    if not isinstance(t.get("guard_ok"), bool):
        home.fail(rel, "guard_ok is not true or false")
    return {"count": home.count(t.get("tests"), rel, "tests"), "failed": home.count(t.get("failures"), rel, "failures"),
            "skipped": home.count(t.get("skipped"), rel, "skipped"), "tier": "full", "guard_ok": t["guard_ok"],
            "at": home.utc(t.get("at"), rel)}


def actor_role(tree, entry, rel):
    actor, event = entry.get("actor"), entry.get("event")
    if actor in MACHINE_ACTORS:
        return MACHINE_ACTORS[actor]
    if isinstance(actor, str) and actor.strip() and event in HUMAN_EVENTS:
        return "human"
    tree.fail(rel, "an actor is neither a known role nor a person on a human-only event")


def job_data(tree, folder, out):
    """Rows for one public job: its job row, its events and its calls (unbacked ones counted, not exported)."""
    rel_state, rel_log = f"jobs/{folder.name}/state.json", f"jobs/{folder.name}/run.log.jsonl"
    st = tree.read_json(rel_state)
    if not isinstance(st, dict):
        tree.fail(rel_state, "not an object")
    jid = tree.ident("job_id", st.get("job_id"), rel_state)
    if jid != folder.name:
        tree.fail(rel_state, "its job_id is not its folder name")
    for n, e in tree.read_jsonl(rel_log):
        where = f"{rel_log} line {n}"
        if e.get("job_id") != jid:
            tree.fail(where, "belongs to another job")
        out["events"].append({
            "root": tree.label, "job_id": jid, "seq": n, "ts": tree.utc(e.get("ts"), where),
            "event": tree.ident("event", e.get("event"), where),
            "state_from": tree.opt("state", e.get("from"), where), "state_to": tree.opt("state", e.get("to"), where),
            "call_id": tree.opt("call_id", e.get("call"), where), "actor_role": actor_role(tree, e, where)})
    calls = st.get("calls")
    if not isinstance(calls, list):
        tree.fail(rel_state, "calls is not a list")
    return st, jid, calls


def usage_index(tree, public_ids, need):
    """{(job, call): [usage lines]} from logs/usage.jsonl, and the number of lines for no public job's call."""
    rel = "logs/usage.jsonl"
    if not (tree.path / rel).is_file():
        if need:
            tree.fail(rel, "missing, but jobs have closed calls")
        return {}, 0
    idx, orphans = {}, 0
    for n, e in tree.read_jsonl(rel):
        if e.get("job_id") in public_ids:
            idx.setdefault((e["job_id"], e.get("call")), []).append((n, e))
        else:
            orphans += 1
    return idx, orphans


def models(tree, value, rel):
    """The model IDs a call reported: the engine stores them joined by ", " (the CLI can report more than one)."""
    return [] if value is None else [tree.ident("model", m.strip(), rel) for m in str(value).split(",")]


def backed(call, lines):
    """True when exactly one usage line agrees with the call record on agent, status and tokens."""
    if call.get("status") not in ("done", "failed") or len(lines) != 1:
        return False
    e = lines[0][1]
    total = (call.get("usage") or {}).get("total")
    logged = (e.get("tokens") or {}).get("total") if isinstance(e.get("tokens"), dict) else e.get("tokens")
    return (e.get("agent") == call.get("agent") and e.get("status") == call.get("status")
            and e.get("attempt") == call.get("attempt") and logged == total)


def jobs_and_usage(tree, out):
    jobs_dir, meta = tree.path / "jobs", {"jobs": 0, "internal": 0, "orphans": 0}
    folders = sorted(d for d in jobs_dir.iterdir() if d.is_dir()) if jobs_dir.is_dir() else []
    private_jobs = tree.path / "private" / "jobs"
    meta["internal"] = sum(1 for d in private_jobs.iterdir() if (d / "state.json").is_file()) if private_jobs.is_dir() else 0
    loaded = [job_data(tree, f, out) for f in folders]
    public_ids = {jid for _, jid, _ in loaded}
    need = any(c.get("status") in ("done", "failed") for _, _, calls in loaded for c in calls if isinstance(c, dict))
    idx, meta["orphans"] = usage_index(tree, public_ids, need)
    known = {(jid, c.get("id")) for _, jid, calls in loaded for c in calls if isinstance(c, dict)}
    meta["orphans"] += sum(len(v) for k, v in idx.items() if k not in known)
    for st, jid, calls in loaded:
        rel = f"jobs/{jid}/state.json"
        if st.get("class") == "internal":
            meta["internal"] += 1               # never exported, even if it sits under jobs/
            continue
        meta["jobs"] += 1
        counted, agents = [], {}
        for c in calls:
            if not isinstance(c, dict):
                tree.fail(rel, "a call is not an object")
            cid = tree.ident("call_id", c.get("id"), rel)
            if not backed(c, idx.get((jid, cid), [])):
                continue
            u = c.get("usage") or {}
            row = {"root": tree.label, "job_id": jid, "call_id": cid, "agent": tree.ident("name", c.get("agent"), rel),
                   "attempt": tree.count(c.get("attempt"), rel, "attempt"), "status": c["status"],
                   "source": tree.ident("source", c.get("usage_source"), rel),
                   "started_at": tree.utc(c.get("ts"), rel), "ended_at": tree.utc(c.get("ended"), rel),
                   **{f"tokens_{k}": tree.number(u.get(k), rel, f"usage {k}", allow_none=True) for k in TOKEN_KEYS},
                   "duration_s": tree.number(u.get("duration_s"), rel, "duration", allow_none=True),
                   "models": models(tree, u.get("model"), rel)}
            if row["tokens_total"] is None:
                for k in TOKEN_KEYS:
                    row[f"tokens_{k}"] = None
            elif any(not isinstance(row[f"tokens_{k}"], int) for k in TOKEN_KEYS):
                tree.fail(rel, "a token count is not a whole number")
            counted.append(row)
            a = agents.setdefault(row["agent"], {"root": tree.label, "job_id": jid, "agent": row["agent"], "calls": 0,
                                                 "retries": 0, "failed": 0, "unknown_calls": 0,
                                                 **{f"tokens_{k}": 0 for k in TOKEN_KEYS}, "minutes": 0.0})
            a["calls"] += 1
            a["retries"] += 1 if c.get("retry_of") else 0
            a["failed"] += 1 if row["status"] == "failed" else 0
            a["unknown_calls"] += 1 if row["tokens_total"] is None else 0
            for k in TOKEN_KEYS:
                a[f"tokens_{k}"] += row[f"tokens_{k}"] or 0
            a["minutes"] += (row["duration_s"] or 0) / 60
        closed = sum(1 for c in calls if c.get("status") in ("done", "failed"))
        known_tokens = [r["tokens_total"] for r in counted if r["tokens_total"] is not None]
        out["jobs"].append({
            "root": tree.label, "job_id": jid, "type": tree.ident("name", st.get("type"), rel),
            "state": tree.ident("state", st.get("state"), rel), "created_at": tree.utc(st.get("created"), rel),
            "updated_at": tree.utc(st.get("updated"), rel), "calls": len(calls), "calls_counted": len(counted),
            "unbacked_calls": closed - len(counted), "tokens_total": sum(known_tokens) if known_tokens else None,
            "agent_minutes": round(sum((r["duration_s"] or 0) for r in counted) / 60, 4)})
        out["usage_calls"] += counted
        for a in agents.values():
            a["minutes"] = round(a["minutes"], 4)
            out["usage_by_job_agent"].append(a)
    return meta


def evals(tree, invalid, out):
    d = tree.path / "evals" / "reports"
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    try:
        own = evalcheck.invalid_list(tree.path) if (tree.path / evalcheck.INVALID_LIST).is_file() else {}
    except lc.LabError as e:
        tree.fail(evalcheck.INVALID_LIST, str(e).split(": ", 1)[-1])
    listed = {**own, **invalid}
    for f in files:
        rel = f"evals/reports/{f.name}"
        rep = tree.read_json(rel)
        if not isinstance(rep, dict):
            tree.fail(rel, "not an object")
        rid = tree.ident("report_id", f.stem, rel)
        m, usage, cases, agent = rep.get("metrics"), rep.get("usage"), rep.get("cases"), rep.get("agent")
        if not (isinstance(m, dict) and isinstance(usage, dict) and isinstance(cases, list) and isinstance(agent, dict)):
            tree.fail(rel, "metrics, usage, cases or agent is missing")
        if not isinstance(rep.get("pass"), bool):
            tree.fail(rel, "pass is not true or false")
        hf = rep.get("handoff_format")
        b, why = evalcheck.backing(rid, rep, listed, root=tree.path)
        rows = []
        for c in cases:
            if not isinstance(c, dict) or not isinstance(c.get("pass"), bool):
                tree.fail(rel, "a case is not an object with pass")
            rows.append({"root": tree.label, "report_id": rid, "case_id": tree.ident("case_id", c.get("case"), rel),
                         "kind": tree.ident("kind", c.get("kind"), rel), "runs": tree.count(c.get("runs"), rel, "runs"),
                         "runs_passed": tree.count(c.get("runs_passed"), rel, "runs_passed"), "pass": c["pass"]})
        mode = tree.ident("mode", rep.get("mode"), rel)
        out["eval_runs"].append({
            "root": tree.label, "report_id": rid, "suite": tree.ident("name", rep.get("suite"), rel),
            "agent": tree.ident("name", Path(str(agent.get("path"))).stem, rel), "mode": mode,
            "discrimination": mode.startswith("discrimination"), "ts": tree.utc(rep.get("ts"), rel), "pass": rep["pass"],
            "model": tree.ident("model", rep.get("model"), rel),
            "cli_version": tree.ident("cli_version", rep.get("cli_version"), rel),
            "handoff_format": None if hf is None else tree.count(hf, rel, "handoff_format"),
            "cases": tree.count(m.get("cases"), rel, "cases"), "cases_passed": tree.count(m.get("cases_passed"), rel, "cases_passed"),
            "runs": tree.count(m.get("runs"), rel, "runs"), "runs_passed": sum(r["runs_passed"] for r in rows),
            "invalid_runs": tree.count(m.get("invalid_runs"), rel, "invalid_runs"),
            "tokens_all": tree.count(usage.get("tokens_all"), rel, "tokens_all"),
            "tokens_new": tree.count(usage.get("tokens_new"), rel, "tokens_new"),
            "backing": b, "backing_reason": why})
        if b != "invalid":                       # an invalid report is listed, never counted or charted
            out["eval_cases"] += rows
    return len(files)


def forbidden(trees):
    """Text that must never appear in an export: every tree's path and approver name, and the OS user name."""
    out = set()
    for t in trees:
        out |= {str(t.path), t.path.as_posix(), str(t.path).replace("\\", "\\\\")}
        f = t.path / "config" / "gates.json"
        try:
            name = json.loads(f.read_text(encoding="utf-8")).get("approver") if f.is_file() else None
        except (OSError, ValueError):
            t.fail("config/gates.json", "unreadable")
        if isinstance(name, str) and len(name.strip()) >= 3:
            out.add(name.strip())
    for k in ("USERNAME", "USER"):
        if len(os.environ.get(k) or "") >= 3:
            out.add(os.environ[k])
    return out


def build(roots=None):
    """The export as a dict. Raises ExportError (naming the file) on anything missing or unreadable."""
    home = Tree(lc.ROOT, None)
    trees = [Tree(r, home) for r in (roots or [lc.ROOT])]
    labels = [t.label for t in trees]
    for t in trees:
        if not t.path.is_dir():
            raise ExportError(f"root not found: {t.label}")
        if not PATTERNS["label"].fullmatch(t.label):
            raise ExportError("a root's folder name is not a valid label")
    if len(set(labels)) != len(labels):
        raise ExportError("two roots have the same folder name")
    try:
        invalid = evalcheck.invalid_list(home.path)
    except lc.LabError as e:
        raise ExportError(f"{home.label}: {e}") from None
    version = home.version()
    out = {"meta": {"export_version": EXPORT_VERSION, "generated_at": z(datetime.datetime.now(datetime.timezone.utc)),
                    "engine_version": version, "tests": tests_meta(home, version), "roots": [],
                    "invalid_list": [{"tree": e["tree"], "report_id": e["report_id"], "date": e["date"]}
                                     for e in invalid.values()]},
           "jobs": [], "events": [], "usage_calls": [], "usage_by_job_agent": [], "eval_runs": [], "eval_cases": []}
    for t in trees:
        v = t.version()
        jm = jobs_and_usage(t, out)
        n = evals(t, invalid, out)
        out["meta"]["roots"].append({"label": t.label, "engine_version": v, "jobs": jm["jobs"],
                                     "internal_jobs_excluded": jm["internal"], "orphan_usage_lines": jm["orphans"],
                                     "eval_reports": n})
    schema = home.read_json(SCHEMA)
    errs = schemacheck.details(out, schema)
    if errs:
        raise ExportError(f"{home.label}: the export does not match {SCHEMA} at {errs[0][0]} ({errs[0][1]})")
    text = json.dumps(out)
    if any(s in text for s in forbidden(trees)):
        raise ExportError(f"{home.label}: the export would contain a path or a user name; nothing written")
    return out


def write(export, out=None):
    """Write the export under private/ (never overwriting a file); returns the path."""
    private = (lc.ROOT / "private").resolve()
    if out:
        path = Path(out).resolve()
        if private not in path.parents:
            raise ExportError("--out must be a file under private/ (the export is never tracked)")
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = private / "reports" / f"export-{stamp}.json"
    base, n = path, 1
    while path.exists():
        n += 1
        path = base.with_name(f"{base.stem}-{n}{base.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    lc.save_json(path, export)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Status export for the progress dashboard (IDs, counts and numbers only).")
    ap.add_argument("--json", action="store_true", required=True, help="write the JSON export (the only output)")
    ap.add_argument("--root", action="append", help="a tree to read (repeatable; default: this repo)")
    ap.add_argument("--out", help="output file under private/ (default: private/reports/export-<UTC time>.json)")
    args = ap.parse_args(argv)
    try:
        export = build(args.root)
        path = write(export, args.out)
    except lc.LabError as e:
        print(f"REPORT FAILED: {e}")
        return 1
    bad = sum(1 for r in export["eval_runs"] if r["backing"] == "invalid")
    print(f"wrote {lc.rel(path)}: {len(export['meta']['roots'])} root(s), {len(export['jobs'])} job(s), "
          f"{len(export['events'])} event(s), {len(export['usage_calls'])} counted call(s), "
          f"{len(export['eval_runs'])} evaluation report(s) ({bad} invalid)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
