#!/usr/bin/env python3
"""Evaluation runner (stdlib only, T0.13). Scores an agent on its suite's cases, headless.

  python evals/run_evals.py run <suite> [--quick | --smoke] [--estimate-only] [--no-cache] [--cases E001,E002]
  python evals/run_evals.py stale          # every reason gate.py lock would refuse now (exit 1 if any)

A suite is evals/<suite>/ (suite.json, cases/<id>/, keys/<id>.json); see engine/evalcheck.py.
- Every call goes through engine/agent_call.py: a tool-less agent in a fresh empty folder, safe mode,
  the pinned model, the case inputs inline. The keys are never copied anywhere the agent can see.
- Leak check first: no key's leak terms (whole words, any case) may appear in the agent's
  instructions or in any prompt. A match stops the run before any call.
- Estimate first: tokens and minutes for the calls not already cached. Above the confirm limit in
  config/caps.json ("evals"), the approver confirms in their own terminal; the run stops at its
  token ceiling or its call cap.
- Modes: full (3 runs per case; counts for lock), smoke (the first case, 3 runs; counts only for
  framework coverage), quick (1 run per case, for drafting; never counts for lock).
- Cache: cache/evals/ (untracked), keyed by the agent file, the exact prompt (rulebook and inputs),
  the model, the CLI version and the run number. --no-cache forces new calls; smoke runs always
  make new calls (a framework change is covered only by real calls).
- Scoring (reviewers): output must be one JSON object (first character "{", last "}"), pass the
  findings schema and the severity lock, and copy the given IDs; otherwise the run is invalid. A case
  counts a rule as found, or its verdict as matched, when a majority of its runs agree
  (evals/thresholds.json). Recall per rule and per severity, false-fail rate on clean cases, verdict
  match, invalid-output rate (over runs, reported separately), variance (run agreement, tokens).
- Reports: evals/reports/<time>-<suite>-<mode>.json (tracked): IDs, rule IDs, verdicts and numbers
  only, never the agent's text (it can name local paths, T0.13 probe T13-5).
Exit codes: 0 pass, 1 fail or refused, 2 leak found, 3 stopped (cost cap, or an infrastructure error
that persisted after one retry).
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import agent_call  # noqa: E402
import evalcheck  # noqa: E402
import labcore as lc  # noqa: E402
import validate_findings as vf  # noqa: E402


class Refused(Exception):
    pass


class CapStop(Exception):
    pass


def thresholds():
    return lc.load_json(evalcheck.evals_dir() / "thresholds.json")


def eval_caps():
    return lc.caps().get("evals", {})


# ---------- suite, cases, prompts ----------

def load_suite(name):
    s = evalcheck.suites().get(name)
    if s is None:
        raise Refused(f"no suite {name!r} (evals/{name}/suite.json)")
    if s.get("kind") != "reviewer":
        raise Refused(f"suite {name}: kind {s.get('kind')!r} is not supported yet (reviewers only in T0.13)")
    s["agent_spec"] = agent_call.parse_agent(lc.ROOT / s["agent"])
    rb = lc.ROOT / s["rulebook"]
    s["rulebook_text"] = rb.read_text(encoding="utf-8")
    s["severities"] = vf.rulebook_severities(rb)
    if not s["severities"]:
        raise Refused(f"suite {name}: rulebook {s['rulebook']} has no rules")
    return s


def load_cases(s, only=None):
    out = []
    for d in sorted((s["dir"] / "cases").iterdir()):
        if not d.is_dir() or (only and d.name not in only):
            continue
        case = lc.load_json(d / "case.json")
        key_file = s["dir"] / "keys" / f"{d.name}.json"
        if not key_file.is_file():
            raise Refused(f"case {d.name}: no key {lc.rel(key_file)}")
        case.update(dir=d, key=lc.load_json(key_file))
        out.append(case)
    if not out:
        raise Refused(f"suite {s['name']}: no cases")
    return out


def ids_for(s, case):
    return {"job_id": f"eval-{case['id']}", "reviewer": s["agent_spec"]["name"], "artifact_path": case["artifact"],
            "artifact_version": "v1"}


def build_prompt(s, case):
    ids = ids_for(s, case)
    parts = [f"JOB: {ids['job_id']}", f"REVIEWER: {ids['reviewer']}", f"ARTIFACT: {ids['artifact_path']}",
             f"VERSION: {ids['artifact_version']}", "", f"RULEBOOK ({s['rulebook']}):", s["rulebook_text"].strip(), ""]
    for name in case["inputs"]:
        parts += [f"=== {name} ===", (case["dir"] / name).read_text(encoding="utf-8").strip(), ""]
    return "\n".join(parts)


def leak_check(s, cases):
    """[(case id, term, where)] for every leak term found in what the agent receives."""
    hits = []
    for c in cases:
        prompt = build_prompt(s, c)
        for term in c["key"].get("leak_terms", []):
            rx = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
            for where, text in (("agent instructions", s["agent_spec"]["body"]), ("prompt", prompt)):
                if rx.search(text):
                    hits.append((c["id"], term, where))
        if "keys/" in prompt or "keys\\" in prompt:
            hits.append((c["id"], "a path into keys/", "prompt"))
    return hits


# ---------- scoring ----------

def score(text, s, case, schema):
    """{valid, errors, found, verdict} for one run's answer."""
    t = (text or "").strip()
    if not (t.startswith("{") and t.endswith("}")):
        return {"valid": False, "errors": ["the answer is not a bare JSON object"], "found": [], "verdict": None}
    try:
        doc = json.loads(t)
    except ValueError as e:
        return {"valid": False, "errors": [f"not JSON ({e.msg})"], "found": [], "verdict": None}
    errs = vf.validate(doc, schema, s["severities"], {}, s["rulebook"]) if isinstance(doc, dict) else ["not an object"]
    if isinstance(doc, dict):
        for k, v in ids_for(s, case).items():
            if doc.get(k) != v:
                errs.append(f"$.{k}: not copied exactly")
    found = sorted({str(f.get("rule", "")).strip().upper() for f in (doc.get("findings") or [])
                    if isinstance(f, dict)}) if isinstance(doc, dict) else []
    return {"valid": not errs, "errors": errs, "found": found if not errs else [],
            "verdict": doc.get("verdict") if not errs else None}


def run_passes(sc, key):
    return (sc["valid"] and set(key["must_find"]) <= set(sc["found"])
            and not set(key.get("must_not_find", [])) & set(sc["found"]) and sc["verdict"] == key["verdict"])


def aggregate(s, cases, results, th):
    """Case-level and overall metrics from {case id: [run result, ...]}."""
    maj = th["case_majority"] if any(len(v) > 1 for v in results.values()) else 1
    per_case, rule_hits, rule_total = [], {}, {}
    clean = clean_ff = vm_cases = vm_hits = 0
    runs = invalid = 0
    for c in cases:
        rs, key = results[c["id"]], c["key"]
        scores = [r["score"] for r in rs]
        runs += len(rs)
        invalid += sum(1 for sc in scores if not sc["valid"])
        passed = sum(1 for sc in scores if run_passes(sc, key))
        for rule in key["must_find"]:
            hit = sum(1 for sc in scores if rule in sc["found"]) >= maj
            rule_total[rule] = rule_total.get(rule, 0) + 1
            rule_hits[rule] = rule_hits.get(rule, 0) + (1 if hit else 0)
        verdict_ok = sum(1 for sc in scores if sc["verdict"] == key["verdict"]) >= maj
        vm_cases += 1
        vm_hits += 1 if verdict_ok else 0
        if c["kind"] == "clean":
            clean += 1
            clean_ff += 1 if sum(1 for sc in scores if sc["verdict"] == "fail") >= maj else 0
        toks = [(r["usage"] or {}).get("total") for r in rs]
        known = [t for t in toks if t is not None]
        per_case.append({"case": c["id"], "kind": c["kind"], "runs": len(rs), "runs_passed": passed,
                         "pass": passed >= maj, "invalid_runs": sum(1 for sc in scores if not sc["valid"]),
                         "found": sorted({r for sc in scores for r in sc["found"]}),
                         "verdicts": [sc["verdict"] for sc in scores],
                         "agreement": round(max(passed, len(rs) - passed) / len(rs), 3),
                         "tokens": {"min": min(known), "max": max(known), "mean": round(sum(known) / len(known))}
                         if known else None,
                         "cached_runs": sum(1 for r in rs if r.get("cached"))})
    by_sev = {}
    for rule, total in rule_total.items():
        sev = s["severities"].get(rule, "unknown")
        h, t = by_sev.get(sev, (0, 0))
        by_sev[sev] = (h + rule_hits[rule], t + total)
    metrics = {
        "recall_per_rule": {r: round(rule_hits[r] / rule_total[r], 3) for r in sorted(rule_total)},
        "recall_blocker": round(by_sev["blocker"][0] / by_sev["blocker"][1], 3) if "blocker" in by_sev else None,
        "recall_major": round(by_sev["major"][0] / by_sev["major"][1], 3) if "major" in by_sev else None,
        "false_fail_rate": round(clean_ff / clean, 3) if clean else None,
        "verdict_match": round(vm_hits / vm_cases, 3) if vm_cases else None,
        "invalid_output_rate": round(invalid / runs, 3) if runs else None,
        "cases": len(cases), "clean_cases": clean, "runs": runs, "invalid_runs": invalid,
        "cases_passed": sum(1 for p in per_case if p["pass"]),
    }
    return per_case, metrics


def check_thresholds(metrics, th):
    t, fails = th["reviewer"], []
    for name, key, ok in (("recall_blocker", "recall_blocker_min", lambda v, x: v >= x),
                          ("recall_major", "recall_major_min", lambda v, x: v >= x),
                          ("false_fail_rate", "false_fail_rate_max", lambda v, x: v <= x),
                          ("verdict_match", "verdict_match_min", lambda v, x: v >= x)):
        v = metrics[name]
        if v is not None and not ok(v, t[key]):
            fails.append(f"{name} {v} (threshold {t[key]})")
    return fails


def min_counts(s, metrics, th):
    routed = s["agent_spec"]["name"] in evalcheck.route_agents()
    need = th["min_counts"]["reviewer" if s["kind"] == "reviewer" else "agent"]
    met = metrics["cases"] >= need["cases"] and metrics["clean_cases"] >= need.get("clean", 0)
    return {"applies": routed, "need": need, "have": {"cases": metrics["cases"], "clean": metrics["clean_cases"]},
            "met": met if routed else None}


# ---------- running ----------

def cache_dir(suite):
    return lc.ROOT / "cache" / "evals" / suite


def cache_key(s, prompt, model, cli, n):
    return evalcheck.digest(s["agent_spec"]["sha256"], prompt, model, cli, n)


def confirm_estimate(tokens):
    import gate
    if not gate.interactive_terminal():
        raise Refused(f"the estimate ({tokens:,} tokens) is above the confirm limit; the approver runs this in "
                      "their own terminal and confirms it")
    try:
        typed = input(f"Estimated {tokens:,} tokens. Type the number {tokens} to confirm: ").strip()
    except EOFError:
        raise Refused("not confirmed (input closed)") from None
    if typed != str(tokens):
        raise Refused("not confirmed")


def run(name, mode="full", estimate_only=False, use_cache=True, only=None, out=print, cmd=None, cli=None):
    """Run a suite. Returns (report or None, exit code)."""
    th = thresholds()
    s = load_suite(name)
    cases = load_cases(s, only)
    if mode == "smoke":
        cases, use_cache = cases[:1], False                            # coverage must come from real calls
    hits = leak_check(s, cases)
    if hits:
        for cid, term, where in hits:
            out(f"LEAK: case {cid}: {term!r} appears in the {where}")
        out("Stopped before any call: remove the leak (rewrite the case or the key's leak terms).")
        return None, 2
    model = agent_call.agent_model(s["agent_spec"])
    cli = cli or agent_call.cli_version(cmd)
    if not cli:
        raise Refused("the CLI did not report its version (claude --version)")
    n_runs = 1 if mode == "quick" else th["runs_per_case"]
    framework = evalcheck.framework_hashes()
    plan, est_tokens, est_seconds = [], 0, 0
    for c in cases:
        prompt = build_prompt(s, c)
        e = agent_call.estimate(s["agent_spec"], prompt)
        for n in range(1, n_runs + 1):
            f = cache_dir(name) / f"{cache_key(s, prompt, model, cli, n)}.json"
            cached = lc.load_json(f) if use_cache and f.is_file() else None
            plan.append((c, n, prompt, f, cached))
            if cached is None:
                est_tokens += e["tokens"]
                est_seconds += e["seconds"]
    todo = sum(1 for p in plan if p[4] is None)
    caps = eval_caps()
    out(f"Suite {name} ({mode}): {len(cases)} case(s) x {n_runs} run(s) = {len(plan)} call(s), {len(plan) - todo} cached.")
    out(f"Estimate for the {todo} new call(s): about {est_tokens:,} tokens and {round(est_seconds / 60, 1)} minutes "
        f"(model {model}, CLI {cli}).")
    if estimate_only:
        return None, 0
    if todo > caps.get("max_runs_per_invocation", 120):
        raise Refused(f"{todo} calls is above max_runs_per_invocation ({caps.get('max_runs_per_invocation')}); use --cases")
    ceiling = caps.get("tokens_per_invocation", 1_000_000)
    if est_tokens > caps.get("confirm_above_tokens", 1_000_000):
        confirm_estimate(est_tokens)
        ceiling = max(ceiling, int(est_tokens * 1.5))
    schema = lc.load_json(lc.ROOT / "schemas" / "findings.schema.json")
    results, spent, stopped = {c["id"]: [] for c in cases}, 0, None
    for c, n, prompt, f, cached in plan:
        if cached is None:
            if stopped:
                continue
            res = agent_call.call(s["agent_spec"], prompt, cmd=cmd)
            if res["status"] == "infra_error":                       # one retry: the failure was not the agent's
                res = agent_call.call(s["agent_spec"], prompt, cmd=cmd)
            if res["status"] == "infra_error":
                stopped = f"infrastructure error on case {c['id']} run {n}: {res['error']}"
                continue
            rec = {"case": c["id"], "run": n, "status": res["status"], "usage": res["usage"], "models": res["models"],
                   "score": score(res["text"], s, c, schema) if res["status"] == "done" else
                   {"valid": False, "errors": [f"agent call {res['status']}: {res.get('error')}"], "found": [], "verdict": None},
                   "text": res["text"]}                                # the text stays in the untracked cache only
            f.parent.mkdir(parents=True, exist_ok=True)
            lc.save_json(f, rec)
            spent += (res["usage"] or {}).get("total") or 0
            out(f"  {c['id']} run {n}: {'valid' if rec['score']['valid'] else 'INVALID'} "
                f"found={rec['score']['found']} verdict={rec['score']['verdict']} tokens={(res['usage'] or {}).get('total')}")
            if spent >= ceiling:
                stopped = f"token ceiling reached ({spent:,} >= {ceiling:,})"
        else:
            rec = {**cached, "cached": True}
        results[c["id"]].append(rec)
    if stopped:
        out(f"STOPPED: {stopped}. No report written; cached runs are kept, so a re-run continues from here.")
        return None, 3
    per_case, metrics = aggregate(s, cases, results, th)
    fails = check_thresholds(metrics, th)
    mc = min_counts(s, metrics, th)
    usage_runs = [r for rs in results.values() for r in rs]
    if only and mode != "quick":
        mode = f"{mode}-partial"                                       # a subset of cases never counts for lock
    report = {
        "suite": name, "mode": mode, "ts": lc.now(), "model": model, "cli_version": cli,
        "models_reported": sorted({m for r in usage_runs for m in r.get("models") or []}),
        "agent": {"path": s["agent"], "sha256": s["agent_spec"]["sha256"]},
        "rulebook": {"path": s["rulebook"], "sha256": lc.sha256_path(lc.ROOT / s["rulebook"])},
        "thresholds": th["reviewer"], "threshold_failures": fails, "min_counts": mc,
        "pass": not fails and metrics["runs"] > 0, "metrics": metrics, "cases": per_case,
        "usage": {"calls": len(usage_runs), "cached": sum(1 for r in usage_runs if r.get("cached")),
                  "tokens_new": spent,
                  "tokens_all": sum((r.get("usage") or {}).get("total") or 0 for r in usage_runs),
                  "cost_usd_estimate_all": round(sum((r.get("usage") or {}).get("cost_usd_estimate") or 0
                                                     for r in usage_runs), 4),
                  "estimate_tokens": est_tokens},
        "framework": framework,
    }
    d = evalcheck.evals_dir() / "reports"
    d.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = d / f"{stamp}-{name}-{mode}.json"
    lc.save_json(path, report)
    m = metrics
    out(f"Report {lc.rel(path)}: {'PASS' if report['pass'] else 'FAIL'}")
    out(f"  recall per rule {m['recall_per_rule']}; major {m['recall_major']}; blocker {m['recall_blocker']}")
    out(f"  false-fail rate {m['false_fail_rate']}; verdict match {m['verdict_match']}; "
        f"invalid-output rate {m['invalid_output_rate']} ({m['invalid_runs']} of {m['runs']} runs)")
    out(f"  cases passed {m['cases_passed']} of {m['cases']}; tokens {report['usage']['tokens_all']:,} "
        f"({spent:,} new); minimum counts: {'met' if mc['met'] else 'not met' if mc['applies'] else 'not applicable (no route uses this agent)'}")
    for f_ in fails:
        out(f"  below threshold: {f_}")
    if mode == "quick" or mode.endswith("-partial"):
        out(f"  {mode} mode: for drafting only; never counts for lock.")
    return report, 0 if report["pass"] else 1


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("suite")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true")
    g.add_argument("--smoke", action="store_true")
    r.add_argument("--estimate-only", action="store_true")
    r.add_argument("--no-cache", action="store_true")
    r.add_argument("--cases")
    sub.add_parser("stale")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "stale":
            problems = evalcheck.lock_problems()
            for p in problems:
                print(f"- {p}")
            print("lock would be refused" if problems else "lock allowed: the evaluations cover the current files")
            return 1 if problems else 0
        mode = "quick" if args.quick else "smoke" if args.smoke else "full"
        _, code = run(args.suite, mode, args.estimate_only, not args.no_cache,
                      set(args.cases.split(",")) if args.cases else None)
        return code
    except (Refused, lc.LabError) as e:
        print(f"REFUSED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
