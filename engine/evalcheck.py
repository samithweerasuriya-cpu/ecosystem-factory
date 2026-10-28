#!/usr/bin/env python3
"""Evaluation coverage (stdlib only): which evaluation reports still count, and the lock rule.

Read by evals/run_evals.py (the `stale` command) and engine/gate.py (lock). A suite is a folder
evals/<suite>/ with suite.json {"agent": <agent file>, "rulebook": <rulebook or null>, "kind":
"reviewer" | "agent"}, cases/<case>/ and keys/<case>.json. Reports are evals/reports/*.json.

A report counts for locking when it passed, ran 3 times per case ("full" or "smoke" mode, never
"quick"), and its model and CLI version equal the pinned model (config/models.json) and the CLI now
installed. `gate.py lock` refuses unless:
  1. every agent file in .claude/agents/ has a suite;
  2. every suite has a counting "full" report made with the current agent and rulebook files, and,
     for an agent used by a route, that report met the minimum case counts (evals/thresholds.json);
  3. every framework file (.claude/agents/, rules/, schemas/, config/ except *.local.json) has the
     hash recorded in at least one counting report ("full" or "smoke"), so any change needs a run;
  4. at least one counting report exists (no evaluations, no lock).
"""
import hashlib

import labcore as lc

FRAMEWORK_DIRS = (".claude/agents", "rules", "schemas", "config")
LOCK_MODES = ("full", "smoke")


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


def reports(suite=None):
    """Every report except discrimination runs (T1.4): those never count for lock and never make another
    report stale or current, so the lock rule does not see them at all."""
    d = evals_dir() / "reports"
    out = [lc.load_json(f) for f in sorted(d.glob("*.json"))] if d.is_dir() else []
    return sorted((r for r in out if (suite is None or r.get("suite") == suite) and not str(r.get("mode") or "").startswith("discrimination")),
                  key=lambda r: r.get("ts", ""))


def fingerprint(cli=None):
    """The pinned model and the installed CLI version (None if the CLI can't run)."""
    import agent_call
    return {"model": agent_call.pinned_model(), "cli_version": cli if cli is not None else agent_call.cli_version()}


def counts(report, fp):
    return (report.get("pass") is True and report.get("mode") in LOCK_MODES
            and report.get("model") == fp["model"] and report.get("cli_version") == fp["cli_version"])


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
