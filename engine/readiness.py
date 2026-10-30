#!/usr/bin/env python3
"""Readiness score (T2.4): is the interview complete enough to write the charter? Stdlib only.

  python engine/readiness.py score <job>    # the intake route's script stage (config/scripts.json "readiness")
  python engine/readiness.py show <job>     # the latest score, as the gate brief shows it

The score counts exactly the seven criteria under "When the interview is complete" in rules/interview-guide.md
(CRITERIA below); if the guide's list and CRITERIA differ, scoring refuses (fails closed). The inputs are the
interviewer's latest saved answer (schemas/interview-status.v1.schema.json, re-checked against its sha256) and
the job's own state: recorded answers, registered context files and answered question rounds. What a script can
check, it checks itself (cited IDs exist, the context pack, example counts, the confirmed playback); whether an
answer is vague stays the interviewer's call, which the charter-critic and charter-verifier review afterwards.

Threshold: config/readiness.json. Exit 0 at or above it, or with the approver's recorded override
(engine/gate.py readiness-override, gates/readiness-override.json); criterion 1 (stage 0) is never overridden.
Exit 1 below the threshold, 2 when the score cannot be computed. Either sends the job to the route's fix_with
agent (the interviewer), which gets this report as its "failed script run". The report (JSON) goes to stdout,
which engine/labcore.py run_script saves in the job's scripts/ folder.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labcore as lc  # noqa: E402
import schemacheck  # noqa: E402

GUIDE = "rules/interview-guide.md"
SCHEMA = "schemas/interview-status.v1.schema.json"
OVERRIDE = "readiness-override.json"
# The guide's "When the interview is complete" list, word for word (a test and score() both compare them).
CRITERIA = (
    "Stage 0 passed.",
    "Every \"you must answer\" field is answered and passes its \"vague if\" test.",
    "Every other field is answered, kept at its default, or an open question with an owner.",
    "At least 2 good and 2 bad examples; every bad one names the rule it breaks.",
    "Every context file has a class and an \"evidence for\".",
    "No unresolved contradiction.",
    "The playback is confirmed.",
)
NEVER_OVERRIDDEN = (1,)
CONFIRMED = re.compile(r"\s*confirmed[.!]*\s*", re.I)


class ReadinessError(lc.LabError):
    pass


def guide_criteria(root=None):
    """The numbered list under '## When the interview is complete' in the guide."""
    text = (Path(root or lc.ROOT) / GUIDE).read_text(encoding="utf-8")
    m = re.search(r"^## When the interview is complete\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if not m:
        raise ReadinessError(f"{GUIDE} has no 'When the interview is complete' section")
    return tuple(re.findall(r"^\d+\. (.+?)\s*$", m.group(1), flags=re.M))


def guide_labels(root=None):
    """{field: label} from the guide's question bank."""
    text = (Path(root or lc.ROOT) / GUIDE).read_text(encoding="utf-8")
    return dict(re.findall(r"^\| `(\w+)` \| (you must answer|answer if you know|defaults offered) \|", text, flags=re.M))


def threshold():
    try:
        t = json.loads((lc.CONFIG / "readiness.json").read_text(encoding="utf-8"))["threshold"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ReadinessError(f"config/readiness.json has no readable threshold ({e})") from None
    if not (isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= len(CRITERIA)):
        raise ReadinessError(f"config/readiness.json threshold must be a whole number from 1 to {len(CRITERIA)}")
    return t


def readiness_stage(st):
    """(index of the readiness script stage, the agent whose answer it scores: the work stage before it)."""
    stages = st["route"]["stages"]
    for i, s in enumerate(stages):
        if lc.stage_kind(s) == "script" and s["script"] == "readiness":
            before = [lc.stage_name(x) for x in stages[:i] if lc.stage_kind(x) == "agent"]
            if before:
                return i, before[-1]
    raise ReadinessError(f"{st['job_id']}: route {st['type']} has no readiness stage after an agent stage")


def latest_answer(job_id, st, agent):
    """The agent's latest saved answer (path, parsed), found from the call records, never by listing a folder."""
    lc.verify_outputs(job_id, st)
    calls = [c for c in st["calls"] if c.get("agent") == agent and c.get("output")]
    if not calls:
        raise ReadinessError(f"{job_id}: no saved answer from {agent} yet")
    path = calls[-1]["output"]["path"]
    try:
        return path, json.loads((lc.ROOT / path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ReadinessError(f"{path} is unreadable ({e})") from None


def override(job_id):
    f = lc.job_dir(job_id) / "gates" / OVERRIDE
    return lc.load_json(f) if f.is_file() else None


def score(job_id):
    """The readiness report for a job (dict). Raises ReadinessError when it cannot be computed."""
    from evidence import CITE_RE
    if guide_criteria() != CRITERIA:
        raise ReadinessError(f"{GUIDE} 'When the interview is complete' differs from engine/readiness.py CRITERIA: "
                             "change both together")
    st = lc.load_state(job_id)
    _, agent = readiness_stage(st)
    path, doc = latest_answer(job_id, st, agent)
    report = {"job_id": job_id, "scored": path, "threshold": threshold(), "criteria": [], "flags": [],
              "override": None}
    stopped = isinstance(doc, dict) and doc.get("status") == "stop"
    schema = json.loads((lc.ROOT / SCHEMA).read_text(encoding="utf-8"))
    bad = [] if stopped else [f"{p}: {rule}" for p, rule, _v, _m in schemacheck.details(doc, schema)]
    if bad:
        raise ReadinessError(f"{path} does not match {SCHEMA}: " + "; ".join(bad[:5]))
    answers = {i["id"]: i for i in st["inputs"]}
    context = {c["id"]: c for c in st.get("context", [])}

    def cite_problems(where, cites):
        out = []
        for c in cites:
            m = CITE_RE.fullmatch(c.strip())
            if not m:
                out.append(f"{where}: citation {c!r} is not well formed")
            elif m.group(1) == "A" and m.group(2) not in answers:
                out.append(f"{where}: [A:{m.group(2)}] is not a recorded answer")
            elif m.group(1) == "S" and m.group(2) not in context:
                out.append(f"{where}: [S:{m.group(2)}] is not a registered context file")
            elif m.group(1) == "G":
                out.append(f"{where}: [G:…] is not an interview source (answers and context files only)")
        return out

    labels = guide_labels()
    results = {n: [] for n in range(1, len(CRITERIA) + 1)}
    if stopped:
        results[1].append(f"the interview stopped at stage 0: {str(doc.get('reason'))[:300]}")
        for n in range(2, len(CRITERIA) + 1):
            results[n].append("not scored: the interview stopped at stage 0")
    else:
        if not doc["stage0"]["passed"]:
            results[1].append("stage 0 did not pass")
        results[1] += cite_problems("stage0", doc["stage0"]["cites"])
        if doc["status"] != "complete":
            results[2].append("the interviewer reports the interview incomplete")
        fields = doc["fields"]
        if set(fields) != set(labels):
            results[2].append("the field list differs from the guide's question bank")
        for f, label in sorted(labels.items()):
            v = fields.get(f)
            if v is None:
                continue
            n = 2 if label == "you must answer" else 3
            ok = ("answered",) if n == 2 else ("answered", "default", "open_question")
            if v["state"] not in ok:
                results[n].append(f"{f} is {v['state']}")
            if v["state"] == "open_question" and not (v.get("owner") or "").strip():
                results[n].append(f"{f} is an open question with no owner")
            if v["state"] in ("answered", "default") and not v["cites"]:
                results[n].append(f"{f} cites no answer or context file")
            results[n] += cite_problems(f, v["cites"])
            if v["state"] == "contradictory":
                results[6].append(f"{f} is still contradictory")
        ex = doc["examples"]
        if len(ex["good"]) < 2 or len(ex["bad"]) < 2:
            results[4].append(f"{len(ex['good'])} good and {len(ex['bad'])} bad examples; at least 2 of each")
        for e in ex["good"] + ex["bad"]:
            results[4] += cite_problems(f"example {e['id']}", e["cites"])
        results[4] += [f"bad example {e['id']} names no rule it breaks" for e in ex["bad"]
                       if not [r for r in e["breaks"] if r.strip()]]
        for c in doc["contradictions"]:
            if not c.get("resolved_by"):
                results[6].append(f"contradiction on {c['field']} is unresolved")
            elif c["resolved_by"] not in answers:
                results[6].append(f"contradiction on {c['field']}: {c['resolved_by']} is not a recorded answer")
        results[7] += playback_problems(st, doc["playback"].get("answer"), answers)
        report["flags"] = doc["flags"]
    for cid, c in sorted(context.items()):
        if not c.get("class") or not (c.get("evidence_for") or "").strip():
            results[5].append(f"context file {cid} has no class or no 'evidence for'")
    report["criteria"] = [{"n": n, "text": CRITERIA[n - 1], "passed": not results[n], "problems": results[n]}
                          for n in sorted(results)]
    report["score"] = sum(1 for c in report["criteria"] if c["passed"])
    ov = override(job_id)
    if report["score"] >= report["threshold"]:
        report["result"] = "pass"
    elif ov and all(report["criteria"][n - 1]["passed"] for n in NEVER_OVERRIDDEN):
        report["result"], report["override"] = "override", ov
    else:
        report["result"] = "below threshold"
    return report


def playback_problems(st, answer_id, answers):
    """Criterion 7: the cited answer closed a playback round, that round is the last one answered, and the
    answer is exactly "Confirmed" (any letter case, trailing . or ! allowed); anything else is a correction."""
    if not answer_id:
        return ["no playback answer is cited"]
    rounds = st.get("answered_rounds", [])
    hit = [r for r in rounds if answer_id in r["answers"]]
    if not hit:
        return [f"{answer_id} did not answer a question round"]
    if hit[-1]["kind"] != "playback":
        return [f"{answer_id} answered a question round, not a playback"]
    if hit[-1] is not rounds[-1]:
        return [f"questions were asked after the playback {answer_id} answered: a new playback is needed"]
    text = (lc.ROOT / answers[answer_id]["path"]).read_text(encoding="utf-8")
    if not CONFIRMED.fullmatch(text):
        return [f"{answer_id} is not exactly \"Confirmed\": it is a correction, and a new playback follows"]
    return []


def latest_report(job_id):
    """The latest readiness run's report from the job's scripts/ folder (saved by run_script), or None."""
    d = lc.job_dir(job_id) / "scripts"
    runs = sorted(d.glob("*-readiness-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])) if d.is_dir() else []
    for p in reversed(runs):
        try:
            return json.loads(lc.load_json(p).get("stdout") or "")
        except ValueError:
            continue
    return None


def brief_lines(job_id):
    """The gate brief's first readiness line and its flags section (T2.4); [] for a route without readiness."""
    rep = latest_report(job_id)
    if rep is None:
        return [], []
    if rep.get("result") == "error":
        head = f"Readiness: not computed ({rep.get('error')})"
    elif rep.get("result") == "override":
        ov = rep["override"]
        head = (f"Readiness: override ({ov['score']} of {len(CRITERIA)} when overridden by {ov['by']}; "
                f"reason: {ov['reason']})")
    else:
        head = f"Readiness: {rep.get('score')} of {len(CRITERIA)} (threshold {rep.get('threshold')})"
    flags = [f"- {f['rule']} at {f['location']}: \"{f['quote']}\"" for f in rep.get("flags", [])]
    return [head, ""], ["## Flags (instruction-like text, reported by the interviewer)", ""] + \
        (flags or ["- None reported."]) + [""]


def record_override(job_id, reason, actor=None):
    """Human-only (engine/gate.py readiness-override): the approver lets the charter be written below the
    threshold. Refused without a readiness run, when the latest run passed, or when stage 0 failed."""
    actor = actor or lc.approver()
    if not (reason or "").strip():
        raise ReadinessError("readiness-override needs --reason")
    st = lc.load_state(job_id)
    readiness_stage(st)
    rep = latest_report(job_id)
    if rep is None:
        raise ReadinessError(f"{job_id} has no readiness run yet: nothing to override")
    if rep.get("result") in ("pass", "override"):
        raise ReadinessError(f"{job_id}: the latest readiness run is '{rep['result']}': no override needed")
    if not all(c["passed"] for c in rep.get("criteria", []) if c["n"] in NEVER_OVERRIDDEN):
        raise ReadinessError(f"{job_id}: stage 0 did not pass; that is never overridden (cancel or revise scope)")
    rec = {"job_id": job_id, "reason": reason.strip(), "by": actor, "at": lc.now(), "score": rep.get("score"),
           "threshold": rep.get("threshold"), "failed": [c["n"] for c in rep["criteria"] if not c["passed"]],
           "report": rep.get("scored")}
    f = lc.job_dir(job_id) / "gates" / OVERRIDE
    f.parent.mkdir(parents=True, exist_ok=True)
    lc.save_json(f, rec)
    if st["state"] == "WORKING" and st["fixing"]:
        # the job waits on the interviewer's fix: hand it straight back to the readiness stage instead
        lc.apply(job_id, "fixed", note=f"readiness override by {actor}", actor=actor)
    return rec


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("score", "show"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        if argv[0] == "show":
            rep = latest_report(argv[1])
            print(json.dumps(rep, indent=2, ensure_ascii=False) if rep else f"{argv[1]}: no readiness run yet")
            return 0
        rep = score(argv[1])
    except lc.LabError as e:
        print(json.dumps({"job_id": argv[1], "result": "error", "error": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep["result"] in ("pass", "override") else 1


if __name__ == "__main__":
    sys.exit(main())
