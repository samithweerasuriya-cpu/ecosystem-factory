#!/usr/bin/env python3
"""Evaluation runner (stdlib only, T0.13). Scores an agent on its suite's cases, headless.

  python evals/run_evals.py run <suite> [--quick | --smoke | --discrimination] [--estimate-only] [--no-cache]
                                [--cases E001,E002]
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
  framework coverage), quick (1 run per case, for drafting; never counts for lock), discrimination (T1.4:
  1 run per case on config/models.json "discrimination_model", after one check call proves the CLI runs
  exactly that model; "too easy" when every case passes, suite design rule 5; engine/evalcheck.py never
  reads these reports, so they never count for lock and never make other reports stale or current).
- Cache: cache/evals/ (untracked), keyed by the agent file, the exact prompt (rulebook and inputs),
  the model, the CLI version and the run number. --no-cache forces new calls; smoke runs always
  make new calls (a framework change is covered only by real calls).
- Run records (T1.7, lesson 15): every run in a report, new or cached, is also saved as its own file
  cache/evals/<suite>/runs/<record id>.json (the ID is a digest of the record; never overwritten), and the
  report lists the IDs in "run_records". engine/evalcheck.py refuses a report whose records are missing,
  changed, miscounted or do not add up to its tokens.
- Scoring (reviewers): output must be one JSON object (first character "{", last "}"), pass the
  findings schema and the severity lock, and copy the given IDs; otherwise the run is invalid. A case
  counts a rule as found, or its verdict as matched, when a majority of its runs agree
  (evals/thresholds.json). Recall per rule and per severity, false-fail rate on clean cases, verdict
  match, invalid-output rate (over runs, reported separately), variance (run agreement, tokens).
  When a key has "locations" ({rule: [words]}), a finding counts for its rule only if its location or
  issue names one of the words (whole word, any case); every other finding is a false finding (reported).
- Scoring (agents, T1.2): suite.json names the output schema, the list field, the quote field and the
  fields to check. Output must be one JSON object that passes the output schema and copies the job ID.
  Each listed item matches a key's expected item when its quote appears in the inputs and is part of
  (or contains) one of the expected item's accepted sentences; an item matching nothing is invented, a
  second item matching the same expected item is a duplicate. Expected-item recall, field accuracy on
  matched items, cases with invented or duplicate items (majority of runs), invalid-output rate.
- Reports: evals/reports/<time>-<suite>-<mode>.json (tracked; "-2", "-3" ... when that name exists, so a
  report is never overwritten): IDs, rule IDs, verdicts and numbers
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
import schemacheck  # noqa: E402
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
    if s.get("kind") not in ("reviewer", "agent"):
        raise Refused(f"suite {name}: kind {s.get('kind')!r} is not supported (reviewer or agent)")
    if s["kind"] == "agent":
        missing = [k for k in ("output_schema", "items_field", "quote_field", "check_fields") if not s.get(k)]
        if missing:
            raise Refused(f"suite {name}: an agent suite needs {', '.join(missing)} in suite.json")
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
    if s["kind"] == "agent":
        return {"job_id": f"eval-{case['id']}"}
    return {"job_id": f"eval-{case['id']}", "reviewer": s["agent_spec"]["name"],
            "artifact_path": lc.rel(case["dir"] / case["artifact"]), "artifact_version": "v1"}


EVAL_HANDOFF = "H001"
EVAL_TYPE = "eval"
EVAL_OUTPUT_DIR = "(kept by the evaluation runner)"


CASE_ROLES = ("answer", "context", "earlier", "questions", "evidence", "feedback")
ROLE_LABELS = {"earlier": "earlier stage output", "questions": "your earlier questions", "feedback": "gate feedback"}


def case_inputs(case):
    """[(file name, role, class)] for a case's inputs. An input is a file name (an approver's answer) or
    {"file", "as": one of CASE_ROLES, "class"}: the part of a job's handoff it stands for (T2.5)."""
    out = []
    for n in case["inputs"]:
        e = n if isinstance(n, dict) else {"file": n}
        if not isinstance(e.get("file"), str) or e.get("as", "answer") not in CASE_ROLES:
            raise Refused(f"case {case['id']}: input {n!r} needs a file name and a role in {CASE_ROLES}")
        out.append((e["file"], e.get("as", "answer"), e.get("class", "synthetic")))
    return out


def case_files(case):
    return [n for n, _, _ in case_inputs(case)]


def route_handoff(s, case, ids, goal, place):
    """A route agent's case: the handoff the job step would get, from labcore.step_handoff (T2.5 parity). The
    case files stand in for the job's parts by role; "counters" gives the question rounds already used."""
    route_name, r, kind, idx = place
    if (kind == "review") != (s["kind"] == "reviewer"):
        raise Refused(f"suite {s['name']}: kind {s['kind']} but the agent is a route {kind} step")
    jid = ids["job_id"]
    parts = {"brief": [("brief", f"jobs/{jid}/brief.md", lc.brief_text(jid, route_name, goal))]}
    answers = contexts = 0
    for n, role, cls in case_inputs(case):
        p = lc.rel(case["dir"] / n)
        if kind == "review" and n == case.get("artifact"):
            continue
        if role == "answer":
            answers += 1
            parts.setdefault("answers", []).append(lc.answer_input(f"A{answers:02d}", cls, p))
        elif role == "context":
            contexts += 1
            parts.setdefault("context", []).append(lc.context_input(f"S{contexts:02d}", cls, p))
        elif role == "evidence":
            parts["evidence"] = p.rstrip("/") + "/"
        else:
            parts.setdefault(role, []).append((ROLE_LABELS[role], p))
    stage = s["agent_spec"]["name"]
    if kind == "review":
        inputs, rules, extra = lc.step_handoff(r, stage, kind, parts, review_index=idx,
                                               artifact=ids["artifact_path"], version=ids["artifact_version"])
    else:
        inputs, rules, extra = lc.step_handoff(r, stage, kind, parts, last=idx == len(r["stages"]) - 1,
                                               counters=case.get("counters", {}))
    return lc.make_handoff(jid, route_name, stage, kind, goal, inputs, rules, EVAL_OUTPUT_DIR,
                           r.get("template"), r.get("template_variants", {}), **extra)


def eval_handoff(s, case):
    """The handoff an evaluation case gets, built like a job step's (T1.5 parity, labcore.make_handoff). An
    agent a route uses gets exactly its route step's handoff (route_handoff). Otherwise (the calibration
    critic): a reviewer gets the artifact and the other case files as approver inputs; an author gets the
    brief and the case files as approver inputs; the rulebook goes in as the job's rules do."""
    ids = ids_for(s, case)
    jid, name = ids["job_id"], s["agent_spec"]["name"]
    goal = case.get("goal") or f"Evaluation case {case['id']}"
    place = lc.route_place(name)
    if place is not None:
        return route_handoff(s, case, ids, goal, place)
    others = [n for n in case_files(case) if s["kind"] == "agent" or n != case["artifact"]]
    human = [(f"input A{i:02d} (synthetic)", lc.rel(case["dir"] / n)) for i, n in enumerate(others, 1)]
    if s["kind"] == "agent":
        brief = ("brief", f"jobs/{jid}/brief.md", lc.brief_text(jid, EVAL_TYPE, goal))
        return lc.make_handoff(jid, EVAL_TYPE, name, "agent", goal, [brief] + human, [s["rulebook"]], EVAL_OUTPUT_DIR)
    return lc.make_handoff(jid, EVAL_TYPE, name, "review", goal, [("artifact", ids["artifact_path"])] + human,
                           [s["rulebook"]], EVAL_OUTPUT_DIR, REVIEW_KIND="critic", REVIEWER=name,
                           ARTIFACT=ids["artifact_path"], VERSION=ids["artifact_version"])


def build_prompt(s, case):
    return agent_call.compose_prompt(s["agent_spec"], eval_handoff(s, case), EVAL_HANDOFF)


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

def parse_answer(text):
    """(doc, error) for one run's answer text."""
    t = (text or "").strip()
    if not (t.startswith("{") and t.endswith("}")):
        return None, "the answer is not a bare JSON object"
    try:
        doc = json.loads(t)
    except ValueError as e:
        return None, f"not JSON ({e.msg})"
    return (doc, None) if isinstance(doc, dict) else (None, "not an object")


def names_word(text, word):
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.IGNORECASE) is not None


def invalid(errors):
    return {"valid": False, "errors": errors, "found": [], "verdict": None, "false_findings": 0,
            "invented": 0, "duplicates": 0, "fields_ok": []}


def score(text, s, case, schema):
    """{valid, errors, found, verdict, ...} for one run's answer."""
    if s["kind"] == "agent":
        return score_agent(text, s, case, schema)
    doc, err = parse_answer(text)
    if err:
        return invalid([err])
    errs = vf.validate(doc, schema, s["severities"], {}, s["rulebook"])
    for k, v in ids_for(s, case).items():
        if doc.get(k) != v:
            errs.append(f"$.{k}: not copied exactly")
    if errs:
        return invalid(errs)
    locations = case["key"].get("locations", {})
    must = set(case["key"].get("must_find", []))
    found, false_findings = set(), 0
    for f in doc.get("findings") or []:
        rule = str(f.get("rule", "")).strip().upper()
        where = f"{f.get('location', '')} {f.get('issue', '')}"
        if rule in locations and not any(names_word(where, w) for w in locations[rule]):
            false_findings += 1                                        # right rule, wrong place
            continue
        found.add(rule)
        if locations and rule not in must:
            false_findings += 1
    return {"valid": True, "errors": [], "found": sorted(found), "verdict": doc.get("verdict"),
            "false_findings": false_findings, "invented": 0, "duplicates": 0, "fields_ok": []}


def norm(text):
    t = str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(t.split()).strip(" \"'").lower()


def score_agent(text, s, case, schema):
    """Match the listed items against the key's expected items (see the module docstring)."""
    doc, err = parse_answer(text)
    if err:
        return invalid([err])
    errs = schemacheck.check(doc, schema)
    for k, v in ids_for(s, case).items():
        if doc.get(k) != v:
            errs.append(f"$.{k}: not copied exactly")
    if errs:
        return invalid(errs)
    inputs = norm(" ".join((case["dir"] / n).read_text(encoding="utf-8") for n in case_files(case)))
    expected = case["key"]["expected"]
    matched, invented = {}, 0
    for it in doc.get(s["items_field"]) or []:
        q = norm(it.get(s["quote_field"], "")).rstrip(".")
        hit = None
        if len(q.split()) >= 4 and q in inputs:
            hit = next((e for e in expected if any(q in norm(src) or norm(src).rstrip(".") in q
                                                   for src in e["sources"])), None)
        if hit is None:
            invented += 1
        else:
            matched.setdefault(hit["id"], []).append(it)
    fields_ok = sorted(e["id"] for e in expected if e["id"] in matched and all(
        norm(matched[e["id"]][0].get(f, "")) == norm(e[f]) for f in s["check_fields"]))
    return {"valid": True, "errors": [], "found": sorted(matched), "verdict": None, "false_findings": 0,
            "invented": invented, "duplicates": sum(len(v) - 1 for v in matched.values()), "fields_ok": fields_ok}


def run_passes(sc, key):
    if "expected" in key:
        ids = {e["id"] for e in key["expected"]}
        return (sc["valid"] and set(sc["found"]) == ids and set(sc["fields_ok"]) == ids
                and sc["invented"] == 0 and sc["duplicates"] == 0)
    return (sc["valid"] and set(key["must_find"]) <= set(sc["found"])
            and not set(key.get("must_not_find", [])) & set(sc["found"]) and sc["verdict"] == key["verdict"])


def case_tokens(rs):
    known = [t for t in ((r["usage"] or {}).get("total") for r in rs) if t is not None]
    return {"min": min(known), "max": max(known), "mean": round(sum(known) / len(known))} if known else None


def aggregate_agent(cases, results, maj):
    per_case, hits, total, fields, inv_cases, dup_cases, inv_items, runs, invalid_runs = [], 0, 0, 0, 0, 0, 0, 0, 0
    for c in cases:
        rs, key = results[c["id"]], c["key"]
        scores = [r["score"] for r in rs]
        runs += len(rs)
        invalid_runs += sum(1 for sc in scores if not sc["valid"])
        inv_items += sum(sc["invented"] for sc in scores)
        passed = sum(1 for sc in scores if run_passes(sc, key))
        found = [e["id"] for e in key["expected"] if sum(1 for sc in scores if e["id"] in sc["found"]) >= maj]
        ok = [e for e in found if sum(1 for sc in scores if e in sc["fields_ok"]) >= maj]
        invented = sum(1 for sc in scores if sc["invented"]) >= maj
        duplicated = sum(1 for sc in scores if sc["duplicates"]) >= maj
        total += len(key["expected"])
        hits += len(found)
        fields += len(ok)
        inv_cases += 1 if invented else 0
        dup_cases += 1 if duplicated else 0
        per_case.append({"case": c["id"], "kind": c["kind"], "runs": len(rs), "runs_passed": passed,
                         "pass": passed >= maj, "invalid_runs": sum(1 for sc in scores if not sc["valid"]),
                         "expected": len(key["expected"]), "found": found, "fields_ok": ok,
                         "invented_per_run": [sc["invented"] for sc in scores],
                         "duplicates_per_run": [sc["duplicates"] for sc in scores],
                         "agreement": round(max(passed, len(rs) - passed) / len(rs), 3),
                         "tokens": case_tokens(rs), "cached_runs": sum(1 for r in rs if r.get("cached"))})
    metrics = {
        "expected_recall": round(hits / total, 3) if total else None, "expected_found": f"{hits} of {total}",
        "field_accuracy": round(fields / hits, 3) if hits else None, "fields_correct": f"{fields} of {hits}",
        "invented_cases": inv_cases, "duplicate_cases": dup_cases, "invented_items_all_runs": inv_items,
        "invalid_output_rate": round(invalid_runs / runs, 3) if runs else None,
        "cases": len(cases), "clean_cases": 0, "runs": runs, "invalid_runs": invalid_runs,
        "cases_passed": sum(1 for p in per_case if p["pass"]),
    }
    return per_case, metrics


def aggregate(s, cases, results, th):
    """Case-level and overall metrics from {case id: [run result, ...]}."""
    maj = th["case_majority"] if any(len(v) > 1 for v in results.values()) else 1
    if s["kind"] == "agent":
        return aggregate_agent(cases, results, maj)
    per_case, rule_hits, rule_total = [], {}, {}
    clean = clean_ff = vm_cases = vm_hits = 0
    runs = invalid = false_findings = 0
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
        false_findings += sum(sc.get("false_findings", 0) for sc in scores)
        per_case.append({"case": c["id"], "kind": c["kind"], "runs": len(rs), "runs_passed": passed,
                         "pass": passed >= maj, "invalid_runs": sum(1 for sc in scores if not sc["valid"]),
                         "found": sorted({r for sc in scores for r in sc["found"]}),
                         "verdicts": [sc["verdict"] for sc in scores],
                         "false_findings_per_run": [sc.get("false_findings", 0) for sc in scores],
                         "agreement": round(max(passed, len(rs) - passed) / len(rs), 3),
                         "tokens": case_tokens(rs), "cached_runs": sum(1 for r in rs if r.get("cached"))})
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
        "false_findings_all_runs": false_findings,
        "cases": len(cases), "clean_cases": clean, "runs": runs, "invalid_runs": invalid,
        "cases_passed": sum(1 for p in per_case if p["pass"]),
    }
    return per_case, metrics


CHECKS = {
    "reviewer": (("recall_blocker", "recall_blocker_min", lambda v, x: v >= x),
                 ("recall_major", "recall_major_min", lambda v, x: v >= x),
                 ("false_fail_rate", "false_fail_rate_max", lambda v, x: v <= x),
                 ("verdict_match", "verdict_match_min", lambda v, x: v >= x)),
    "agent": (("expected_recall", "expected_recall_min", lambda v, x: v >= x),
              ("field_accuracy", "field_accuracy_min", lambda v, x: v >= x),
              ("invented_cases", "invented_cases_max", lambda v, x: v <= x),
              ("duplicate_cases", "duplicate_cases_max", lambda v, x: v <= x)),
}


def check_thresholds(metrics, th, kind="reviewer"):
    t, fails = th[kind], []
    for name, key, ok in CHECKS[kind]:
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


def save_run_record(suite, rec):
    """Keep this run's record as its own file named by its digest; returns the record ID. A cache file can be
    overwritten by a later run with the same key, so a report points at these files, never at the cache."""
    body = {k: v for k, v in rec.items() if k != "cached"}
    rid = evalcheck.record_digest(body)
    f = evalcheck.runs_dir(suite) / f"{rid}.json"
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        lc.save_json(f, body)
    return rid


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


def confirm_model(model, cmd=None):
    """One tiny call on `model`; refused unless the CLI accepts it and reports running exactly it."""
    probe = {"name": "model-check", "tools": [], "model": model, "sha256": "-",
             "body": "Reply with exactly {} and nothing else."}
    res = agent_call.call(probe, "Reply with exactly {}.", cmd=cmd, model=model)
    if res["status"] != "done":
        raise Refused(f"the CLI did not run model {model!r} ({res['status']}: {res.get('error')}); "
                      "set the exact model ID in config/models.json discrimination_model")
    if res["models"] != [model]:
        raise Refused(f"asked for {model!r}, the CLI reported {res['models']}; set the exact model ID in "
                      "config/models.json discrimination_model")


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
    discrimination = mode == "discrimination"
    model = agent_call.discrimination_model() if discrimination else agent_call.agent_model(s["agent_spec"])
    cli = cli or agent_call.cli_version(cmd)
    if not cli:
        raise Refused("the CLI did not report its version (claude --version)")
    n_runs = 1 if mode in ("quick", "discrimination") else th["runs_per_case"]
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
    if discrimination and todo:
        confirm_model(model, cmd)
        out(f"Model check: the CLI ran exactly {model}.")
    if todo > caps.get("max_runs_per_invocation", 120):
        raise Refused(f"{todo} calls is above max_runs_per_invocation ({caps.get('max_runs_per_invocation')}); use --cases")
    ceiling = caps.get("tokens_per_invocation", 1_000_000)
    if est_tokens > caps.get("confirm_above_tokens", 1_000_000):
        confirm_estimate(est_tokens)
        ceiling = max(ceiling, int(est_tokens * 1.5))
    schema = lc.load_json(lc.ROOT / (s["output_schema"] if s["kind"] == "agent" else "schemas/findings.schema.json"))
    results, spent, stopped, run_records = {c["id"]: [] for c in cases}, 0, None, []
    for c, n, prompt, f, cached in plan:
        if cached is None:
            if stopped:
                continue
            res = agent_call.call(s["agent_spec"], prompt, cmd=cmd, model=model)
            if res["status"] == "infra_error":                       # one retry: the failure was not the agent's
                res = agent_call.call(s["agent_spec"], prompt, cmd=cmd, model=model)
            if res["status"] == "infra_error":
                stopped = f"infrastructure error on case {c['id']} run {n}: {res['error']}"
                continue
            rec = {"case": c["id"], "run": n, "status": res["status"], "usage": res["usage"], "models": res["models"],
                   "score": score(res["text"], s, c, schema) if res["status"] == "done" else
                   invalid([f"agent call {res['status']}: {res.get('error')}"]),
                   "text": res["text"]}                                # the text stays in the untracked cache only
            f.parent.mkdir(parents=True, exist_ok=True)
            lc.save_json(f, rec)
            spent += (res["usage"] or {}).get("total") or 0
            sc = rec["score"]
            detail = (f"invented={sc['invented']} duplicates={sc['duplicates']}" if s["kind"] == "agent"
                      else f"verdict={sc['verdict']}")
            out(f"  {c['id']} run {n}: {'valid' if sc['valid'] else 'INVALID'} found={sc['found']} {detail} "
                f"tokens={(res['usage'] or {}).get('total')}")
            if spent >= ceiling:
                stopped = f"token ceiling reached ({spent:,} >= {ceiling:,})"
        else:
            rec = {**cached, "cached": True}
        run_records.append(save_run_record(name, rec))
        results[c["id"]].append(rec)
    if stopped:
        out(f"STOPPED: {stopped}. No report written; cached runs are kept, so a re-run continues from here.")
        return None, 3
    per_case, metrics = aggregate(s, cases, results, th)
    fails = check_thresholds(metrics, th, s["kind"])
    mc = min_counts(s, metrics, th)
    usage_runs = [r for rs in results.values() for r in rs]
    if only and mode != "quick":
        mode = f"{mode}-partial"                                       # a subset of cases never counts for lock
    report = {
        "suite": name, "mode": mode, "ts": lc.now(), "model": model, "cli_version": cli,
        "handoff_format": lc.HANDOFF_FORMAT,
        "models_reported": sorted({m for r in usage_runs for m in r.get("models") or []}),
        "agent": {"path": s["agent"], "sha256": s["agent_spec"]["sha256"]},
        "rulebook": {"path": s["rulebook"], "sha256": lc.sha256_path(lc.ROOT / s["rulebook"])},
        "thresholds": th[s["kind"]], "threshold_failures": fails, "min_counts": mc,
        "pass": not fails and metrics["runs"] > 0, "metrics": metrics, "cases": per_case,
        "usage": {"calls": len(usage_runs), "cached": sum(1 for r in usage_runs if r.get("cached")),
                  "tokens_new": spent,
                  "tokens_all": sum((r.get("usage") or {}).get("total") or 0 for r in usage_runs),
                  "cost_usd_estimate_all": round(sum((r.get("usage") or {}).get("cost_usd_estimate") or 0
                                                     for r in usage_runs), 4),
                  "estimate_tokens": est_tokens},
        "run_records": run_records,
        "framework": framework,
    }
    if discrimination:
        report["counts_for_lock"] = False
        report["too_easy"] = metrics["cases"] > 0 and metrics["cases_passed"] == metrics["cases"]
    d = evalcheck.evals_dir() / "reports"
    d.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path, n = d / f"{stamp}-{name}-{mode}.json", 1
    while path.exists():                                               # T1.4: a report is never overwritten
        n += 1
        path = d / f"{stamp}-{name}-{mode}-{n}.json"
    lc.save_json(path, report)
    m = metrics
    out(f"Report {lc.rel(path)}: {'PASS' if report['pass'] else 'FAIL'}")
    if s["kind"] == "agent":
        out(f"  expected-item recall {m['expected_recall']} ({m['expected_found']}); field accuracy "
            f"{m['field_accuracy']} ({m['fields_correct']}); cases with invented items {m['invented_cases']}; "
            f"with duplicates {m['duplicate_cases']}")
        out(f"  invalid-output rate {m['invalid_output_rate']} ({m['invalid_runs']} of {m['runs']} runs)")
    else:
        out(f"  recall per rule {m['recall_per_rule']}; major {m['recall_major']}; blocker {m['recall_blocker']}")
        out(f"  false-fail rate {m['false_fail_rate']}; verdict match {m['verdict_match']}; "
            f"invalid-output rate {m['invalid_output_rate']} ({m['invalid_runs']} of {m['runs']} runs); "
            f"false findings {m['false_findings_all_runs']}")
    out(f"  cases passed {m['cases_passed']} of {m['cases']}; tokens {report['usage']['tokens_all']:,} "
        f"({spent:,} new); minimum counts: {'met' if mc['met'] else 'not met' if mc['applies'] else 'not applicable (no route uses this agent)'}")
    for f_ in fails:
        out(f"  below threshold: {f_}")
    if mode == "quick" or mode.endswith("-partial"):
        out(f"  {mode} mode: for drafting only; never counts for lock.")
    if discrimination:
        out(f"  discrimination only ({model}): never counts for lock. "
            + ("TOO EASY: the weaker model passed every case; the suite needs harder cases before it counts "
               "(suite design rule 5)." if report["too_easy"] else
               f"The weaker model failed {m['cases'] - m['cases_passed']} of {m['cases']} case(s): the suite discriminates."))
        return report, 0
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
    g.add_argument("--discrimination", action="store_true")
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
            for rid, why in evalcheck.refused_reports():
                print(f"  (never counts: report {rid} is invalid: {why})")
            print("lock would be refused" if problems else "lock allowed: the evaluations cover the current files")
            return 1 if problems else 0
        mode = ("quick" if args.quick else "smoke" if args.smoke else "discrimination" if args.discrimination
                else "full")
        _, code = run(args.suite, mode, args.estimate_only, not args.no_cache,
                      set(args.cases.split(",")) if args.cases else None)
        return code
    except (Refused, lc.LabError) as e:
        print(f"REFUSED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
