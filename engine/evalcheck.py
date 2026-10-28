#!/usr/bin/env python3
"""Evaluation coverage (stdlib only): which evaluation reports still count, and the lock rule.

Read by evals/run_evals.py (the `stale` command) and engine/gate.py (lock). A suite is a folder
evals/<suite>/ with suite.json {"agent": <agent file>, "rulebook": <rulebook or null>, "kind":
"reviewer" | "agent"}, cases/<case>/ and keys/<case>.json. Reports are evals/reports/*.json.

A report counts for locking when it passed, ran 3 times per case ("full" or "smoke" mode, never
"quick"), its model and CLI version equal the pinned model (config/models.json) and the CLI now
installed, and it was made with the current handoff format (labcore.HANDOFF_FORMAT, T1.5; a report
without one is format 1). `gate.py lock` refuses unless:
  1. every agent file in .claude/agents/ has a suite;
  2. every suite has a counting "full" report made with the current agent and rulebook files, and,
     for an agent used by a route, that report met the minimum case counts (evals/thresholds.json);
  3. every framework file (.claude/agents/, rules/, schemas/, config/ except *.local.json) has the
     hash recorded in at least one counting report ("full" or "smoke"), so any change needs a run;
  4. at least one counting report exists (no evaluations, no lock).
A report never counts, and the lock rule does not see it, when it is on config/invalid-reports.json or when it
lists run records (T1.7) that fail the check: each run's record file exists in cache/evals/<suite>/runs/,
still has its digest, and the records' tokens add up to the report's (lesson 15: a result counts only with a
real run behind it). Reports made before T1.7 list no records and are "legacy".
"""
import hashlib
import json
import re
from pathlib import Path

import labcore as lc

FRAMEWORK_DIRS = (".claude/agents", "rules", "schemas", "config")
LOCK_MODES = ("full", "smoke")
INVALID_LIST = "config/invalid-reports.json"
REPORT_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z0-9][a-z0-9-]*$")
TREE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RECORD_ID_RE = re.compile(r"^[0-9a-f]{64}$")


def evals_dir():
    return lc.ROOT / "evals"


def framework_hashes():
    out = {}
    for d in FRAMEWORK_DIRS:
        base = lc.ROOT / d
        if base.is_dir():
            for f in sorted(base.rglob("*")):
                if f.is_file() and not f.name.endswith(".local.json") and "__pycache__" not in f.parts:
                    out[lc.rel(f)] = lc.sha256_path(f)
    return out


def file_hash(relpath):
    f = lc.ROOT / relpath if relpath else None
    return lc.sha256_path(f) if f and f.is_file() else None


def suites():
    """{suite name: suite.json plus its folder}, for every evals/<suite>/suite.json."""
    out = {}
    d = evals_dir()
    for f in sorted(d.glob("*/suite.json")) if d.is_dir() else []:
        s = lc.load_json(f)
        s["name"], s["dir"] = f.parent.name, f.parent
        out[s["name"]] = s
    return out


def agent_name(path):
    import agent_call
    return agent_call.parse_agent(lc.ROOT / path)["name"]


def route_agents():
    names = set()
    f = lc.CONFIG / "routes.json"
    for r in (lc.load_json(f).get("routes", {}) if f.exists() else {}).values():
        for s in r.get("stages", []):
            names.add(s.get("agent") or (s.get("fanout") or {}).get("agent"))
        names.update(rv.get("agent") for rv in r.get("reviews", []))
        names.update(r.get(k) for k in ("revise_with", "fix_with", "deliver"))
    return {n for n in names if n}


def invalid_list(root=None):
    """{report_id: entry} from config/invalid-reports.json. A missing file or a malformed entry is an error."""
    f = Path(root or lc.ROOT) / INVALID_LIST
    if not f.is_file():
        raise lc.LabError(f"{INVALID_LIST} is missing (an empty list is {{\"reports\": []}})")
    try:
        entries = lc.load_json(f)["reports"]
    except (ValueError, KeyError, TypeError) as e:
        raise lc.LabError(f"{INVALID_LIST}: unreadable ({type(e).__name__})") from None
    out = {}
    for i, e in enumerate(entries if isinstance(entries, list) else [None]):
        ok = (isinstance(e, dict) and set(e) == {"tree", "report_id", "date", "reason"}
              and all(isinstance(e[k], str) for k in e) and TREE_RE.match(e["tree"])
              and REPORT_ID_RE.match(e["report_id"]) and DATE_RE.match(e["date"]) and e["reason"].strip())
        if not ok:
            raise lc.LabError(f"{INVALID_LIST}: entry {i} needs exactly tree, report_id, date (YYYY-MM-DD) and reason")
        out[e["report_id"]] = e
    return out


def record_digest(rec):
    """The ID of one evaluation run's record: a digest of its content (the cache flag and the ID left out)."""
    body = {k: v for k, v in rec.items() if k not in ("cached", "record_id")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def runs_dir(suite, root=None):
    return Path(root or lc.ROOT) / "cache" / "evals" / suite / "runs"


def record_problem(report, root=None):
    """Why a report's run records do not back it (a short code), or None. Only for reports that list records."""
    ids = report.get("run_records")
    usage, cases = report.get("usage") or {}, report.get("cases") or []
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
        return "records_count"
    if len(ids) != usage.get("calls") or len(ids) != (report.get("metrics") or {}).get("runs"):
        return "records_count"
    per_case, seen, tokens = {c.get("case"): 0 for c in cases}, set(), 0
    for rid in ids:
        f = runs_dir(str(report.get("suite")), root) / f"{rid}.json" if isinstance(rid, str) and RECORD_ID_RE.match(rid) else None
        if f is None or not f.is_file():
            return "records_missing"
        try:
            rec = lc.load_json(f)
        except ValueError:
            return "records_changed"
        if not isinstance(rec, dict) or record_digest(rec) != rid:
            return "records_changed"
        if rec.get("case") not in per_case or (rec.get("case"), rec.get("run")) in seen:
            return "records_count"
        seen.add((rec["case"], rec.get("run")))
        per_case[rec["case"]] += 1
        tokens += (rec.get("usage") or {}).get("total") or 0
    if any(per_case[c.get("case")] != c.get("runs") for c in cases):
        return "records_count"
    if tokens != usage.get("tokens_all"):
        return "tokens_mismatch"
    return None


def backing(report_id, report, invalid, root=None):
    """(backing, reason code): ("invalid", "listed"), ("invalid", <record problem>), ("records", None) or
    ("legacy", None) for a report made before run records existed."""
    if report_id in invalid:
        return "invalid", "listed"
    if "run_records" not in report:
        return "legacy", None
    why = record_problem(report, root)
    return ("invalid", why) if why else ("records", None)


def load_reports(root=None):
    """[(report_id, report)] for every file in evals/reports/, discrimination runs and invalid ones included."""
    d = Path(root or lc.ROOT) / "evals" / "reports"
    return [(f.stem, lc.load_json(f)) for f in sorted(d.glob("*.json"))] if d.is_dir() else []


def reports(suite=None):
    """Every report the lock rule may see: not a discrimination run (T1.4: those never count for lock and
    never make another report stale or current) and not invalid (T1.7: listed, or its run records fail)."""
    invalid = invalid_list()
    out = [r for rid, r in load_reports() if backing(rid, r, invalid)[0] != "invalid"]
    return sorted((r for r in out if (suite is None or r.get("suite") == suite) and not str(r.get("mode") or "").startswith("discrimination")),
                  key=lambda r: r.get("ts", ""))


def refused_reports():
    """[(report_id, reason code)] for every report the lock rule refuses as invalid."""
    invalid = invalid_list()
    return [(rid, why) for rid, r in load_reports() for b, why in [backing(rid, r, invalid)] if b == "invalid"]


def fingerprint(cli=None):
    """The pinned model and the installed CLI version (None if the CLI can't run)."""
    import agent_call
    return {"model": agent_call.pinned_model(), "cli_version": cli if cli is not None else agent_call.cli_version()}


def counts(report, fp):
    return (report.get("pass") is True and report.get("mode") in LOCK_MODES
            and report.get("model") == fp["model"] and report.get("cli_version") == fp["cli_version"]
            and report.get("handoff_format") == lc.HANDOFF_FORMAT)


def suite_problem(s, fp, routed):
    """Why this suite has no counting full report for its current files, or None."""
    agent_sha, rb_sha = file_hash(s["agent"]), file_hash(s.get("rulebook"))
    full = [r for r in reports(s["name"]) if r.get("mode") == "full" and r.get("pass") is True]
    if not full:
        return f"suite {s['name']}: no passing full evaluation report"
    cur = [r for r in full if r["agent"]["sha256"] == agent_sha and (r.get("rulebook") or {}).get("sha256") == rb_sha]
    if not cur:
        return (f"suite {s['name']}: {s['agent']} or its rulebook changed since its last passing full report; "
                f"re-run: python evals/run_evals.py run {s['name']}")
    ok = [r for r in cur if counts(r, fp)]
    if not ok and not any(r.get("handoff_format") == lc.HANDOFF_FORMAT for r in cur):
        return (f"suite {s['name']}: its passing report was made with handoff format "
                f"{cur[-1].get('handoff_format', 1)}; now {lc.HANDOFF_FORMAT} (the prompt the agent gets changed): "
                f"re-run: python evals/run_evals.py run {s['name']}")
    if not ok:
        last = cur[-1]
        return (f"suite {s['name']}: its passing report was made with model {last.get('model')} and CLI "
                f"{last.get('cli_version')}; now {fp['model']} and CLI {fp['cli_version']} (recalibrate: re-run it)")
    if routed and not ok[-1].get("min_counts", {}).get("met"):
        return f"suite {s['name']}: the agent is used by a route and its report is below the minimum case counts"
    return None


def lock_problems(cli=None):
    """Every reason operate mode may not be locked now (empty list: lock allowed)."""
    if not reports():
        return ["no evaluation reports in evals/reports/ (run python evals/run_evals.py run <suite>)"]
    fp = fingerprint(cli)
    if not fp["cli_version"]:
        return ["the Claude Code CLI did not report its version (claude --version); evaluations can't be matched"]
    problems, all_suites = [], suites()
    by_agent = {lc.rel(lc.ROOT / s["agent"]): s for s in all_suites.values()}
    agents_dir = lc.ROOT / ".claude" / "agents"
    for f in sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []:
        if lc.rel(f) not in by_agent:
            problems.append(f"agent {lc.rel(f)} has no evaluation suite in evals/")
    routed = route_agents()
    for s in all_suites.values():
        why = suite_problem(s, fp, agent_name(s["agent"]) in routed)
        if why:
            problems.append(why)
    counting = [r for r in reports() if counts(r, fp)]
    if not counting:
        problems.append("no passing evaluation report for the current model and CLI version")
        return problems
    covered = {(p, h) for r in counting for p, h in (r.get("framework") or {}).items()}
    stale = [p for p, h in framework_hashes().items() if (p, h) not in covered]
    if stale:
        problems.append(f"{len(stale)} framework file(s) changed since the last passing evaluation run "
                        f"(run a suite, or a smoke run: python evals/run_evals.py run <suite> --smoke): "
                        + ", ".join(stale[:8]) + (" ..." if len(stale) > 8 else ""))
    return problems


def digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()
