"""Job-driven evaluation suites (T2.5), used by evals/run_evals.py: kind "interview" (the interviewer against
script personas) and kind "charter" (the charter-writer, with first-pass acceptance).

Each run drives a real intake job in a temporary factory copy that holds only what a job needs (COPY_DIRS and the
route's agent files): never private/, vendor/, evals/ or any keys/ folder (check_copy refuses one). The copy's own
engine runs every step: state.py for the job's events, agent_call.call_job for each agent call, exactly the job
loop in CLAUDE.md. The hidden key stays on the runner's side; the persona reveals only the answer to the field asked.

- Persona (interview): answers each question by its structured field (state.json awaiting.fields, T2.5
  question_fields): the field's first answer, then the next one per later question on it (the answer after a probe);
  a field with no script gets "I can't answer that." (a wasted question). A playback gets the key's next playback
  reply ("Confirmed" by default). Questions without fields (another author) get "I can't answer that." each.
- Simulated human resume: when the per-cycle round cap pauses the job, the runner resumes it once, in the copy only
  (simulated_resume refuses any other root). It is the only simulated human action; the runner has no code path that
  writes under gates/ or records an override.
- Leak check before every agent call: the exact prompt, rebuilt in the copy by the functions call_job uses, may not
  name the key's marker word or leak terms, or a keys/ path. A hit stops the run (exit 2, as in run_evals).
- Charter cases are seeded either by replaying the case's recorded interviewer answers through a replay CLI
  (evals/replay_cli.py, no model call) and the readiness script, or from a job folder authored with the case
  (fixture, e.g. a job whose readiness override is already recorded), copied as it is.
"""
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import agent_call  # noqa: E402
import labcore as lc  # noqa: E402

COPY_DIRS = ("engine", "config", "schemas", "rules", "templates")
MARKER = ".eval-copy"
COPY_TOP = set(COPY_DIRS) | {".claude", "jobs", "inbox", MARKER}
RUNTIME_TOP = {"logs", ".lab", "cache"}                   # the copy's engine may create these while a job runs
FORBIDDEN = ("private", "vendor", "evals", "keys")
REPLAY = Path(__file__).resolve().parent / "replay_cli.py"
CANT = "I can't answer that."
MAX_STEPS = 80
STEP_TIMEOUT = 120                                 # seconds for one state.py step or engine function in the copy
CALL_TIMEOUT = agent_call.DEFAULT_TIMEOUT          # seconds for one agent call (tests set less)
_COPIES = {}                                       # resolved copy path -> marker token (this process only)


class SimError(lc.LabError):
    pass


class LeakStop(Exception):
    pass


# ---------- the copy ----------

def make_copy(route="intake"):
    """A new temporary factory copy for one run: COPY_DIRS (no tests, caches or *.local.json), the route's agent
    files, an empty jobs/ and inbox/, and a marker that makes it a copy this process may resume in."""
    root = Path(tempfile.mkdtemp(prefix="factory-eval-")).resolve()
    skip = shutil.ignore_patterns("__pycache__", "tests", "*.local.json", *FORBIDDEN)
    for d in COPY_DIRS:
        if (lc.ROOT / d).is_dir():
            shutil.copytree(lc.ROOT / d, root / d, ignore=skip)
    r = lc.routes()[route]
    (root / ".claude" / "agents").mkdir(parents=True)
    for name in sorted(route_agents(r)):
        shutil.copy(lc.ROOT / ".claude" / "agents" / f"{name}.md", root / ".claude" / "agents" / f"{name}.md")
    (root / "jobs").mkdir()
    (root / "inbox").mkdir()
    token = secrets.token_hex(16)
    (root / MARKER).write_text(token, encoding="utf-8")
    _COPIES[str(root)] = token
    check_copy(root)
    return root


def route_agents(r):
    names = {s.get("agent") for s in r["stages"]} | {v["agent"] for v in r["reviews"]}
    names |= {r.get(k) for k in ("revise_with", "fix_with", "deliver")}
    return {n for n in names if n}


def check_copy(root, during=False):
    """Refuse a copy with anything at the top beyond what a job needs, or any private/, vendor/, evals/ or keys/
    folder anywhere in it."""
    allowed = COPY_TOP | (RUNTIME_TOP if during else set())
    extra = sorted(p.name for p in root.iterdir() if p.name not in allowed)
    if extra:
        raise SimError(f"evaluation copy {root}: unexpected top-level entries {extra}")
    bad = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir() and p.name.lower() in FORBIDDEN)
    if bad:
        raise SimError(f"evaluation copy {root}: forbidden folders {bad}")


def is_copy(root):
    p = Path(root).resolve()
    tok = _COPIES.get(str(p))
    return (tok is not None and (p / MARKER).is_file() and (p / MARKER).read_text(encoding="utf-8") == tok
            and p != lc.ROOT.resolve() and lc.ROOT.resolve() not in p.parents)


def remove_copy(root):
    if is_copy(root):
        _COPIES.pop(str(Path(root).resolve()), None)
        shutil.rmtree(root, ignore_errors=True)


# ---------- the copy's engine ----------

def child_env(root):
    env = agent_call.child_env()
    env["LAB_ROOT"] = str(root)
    env.pop("CLAUDE_PROJECT_DIR", None)
    return env


def state_cli(root, *args):
    """engine/state.py in the copy: (exit code, output). 1 is an error; 3 (cap) and 4 (script failed) are job
    outcomes the caller reads back from state.json."""
    p = run_child([sys.executable, str(root / "engine" / "state.py"), *args], root, STEP_TIMEOUT,
                  f"state.py {' '.join(args[:2])}")
    if p.returncode == 1:
        raise SimError(f"state.py {' '.join(args[:2])}: {(p.stdout + p.stderr).strip()[-400:]}")
    return p.returncode, p.stdout


SNIPPET = ("import json, sys\nsys.path.insert(0, sys.argv[1])\nimport labcore as lc, agent_call as ac\n"
           "try:\n{body}\nexcept lc.CapExceeded as e:\n    out = {{'status': 'capped', 'error': str(e)}}\n"
           "except lc.LabError as e:\n    out = {{'status': 'error', 'error': str(e)}}\n"
           "print('\\n@@' + json.dumps(out, default=str))\n")


def run_child(argv, root, timeout, what):
    """One child process in the copy, with no keyboard input and a time limit: a step that hangs stops the run
    with its name instead of waiting forever."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=child_env(root), stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SimError(f"{what}: no answer after {timeout} s in the evaluation copy {root}") from None


def snippet(root, body, *args, timeout=None, what="engine call"):
    """Run engine functions in the copy (the same ones the CLIs call) and return their JSON result."""
    code = SNIPPET.format(body="\n".join("    " + ln for ln in body.strip().splitlines()))
    p = run_child([sys.executable, "-c", code, str(root / "engine"), *args], root, timeout or STEP_TIMEOUT, what)
    if "\n@@" not in p.stdout:
        raise SimError(f"engine call in the copy failed: {p.stderr.strip()[-400:]}")
    return json.loads(p.stdout.rsplit("\n@@", 1)[1])


def call_job(root, job, agent, cmd=None):
    body = ("kw = {'cmd': json.loads(sys.argv[4])} if sys.argv[4] != 'null' else {}\n"
            "r = ac.call_job(sys.argv[2], sys.argv[3], timeout=int(sys.argv[5]), **kw)\n"
            "out = {'status': r['status'], 'output': r.get('output'), 'state': r.get('state'),\n"
            "       'problems': [[str(p[0]), str(p[1])] for p in r.get('problems') or []]}")
    # call_job retries an invalid answer once, so two agent calls fit in the limit
    return snippet(root, body, job, str(root / ".claude" / "agents" / f"{agent}.md"), json.dumps(cmd),
                   str(CALL_TIMEOUT), timeout=2 * CALL_TIMEOUT + STEP_TIMEOUT, what=f"{job}: {agent} call")


def prompt_for(root, job, agent):
    """The prompt the next call will get, rebuilt by the functions call_job uses (the handoff ID aside)."""
    body = ("h = lc.build_handoff(sys.argv[2])\n"
            "out = {'prompt': ac.compose_prompt(ac.parse_agent(sys.argv[3]), h, 'H000')}")
    r = snippet(root, body, job, str(root / ".claude" / "agents" / f"{agent}.md"), what=f"{job}: {agent} prompt")
    if "prompt" not in r:
        raise SimError(f"prompt for {agent}: {r.get('error')}")
    return r["prompt"]


def load_state(root, job):
    return json.loads((root / "jobs" / job / "state.json").read_text(encoding="utf-8"))


def caps(root):
    return json.loads((root / "config" / "caps.json").read_text(encoding="utf-8"))


def leak_check(prompt, key):
    for term in [key.get("canary")] + list(key.get("leak_terms", [])):
        if term and re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", prompt, re.IGNORECASE):
            raise LeakStop(f"{term!r} appears in the prompt")
    if "keys/" in prompt or "keys\\" in prompt:
        raise LeakStop("a path into keys/ appears in the prompt")


def simulated_resume(root, job):
    """The one simulated human action (T2.5, approved): resume a job the per-cycle round cap paused, in this
    run's evaluation copy only."""
    if not is_copy(root):
        raise SimError(f"simulated resume refused: {root} is not an evaluation copy made by this run")
    state_cli(root, "event", job, "resume", "--note", "simulated human resume (evaluation copy)")


# ---------- the persona ----------

class Persona:
    """Answers by field from the key's script; counts questions, repeats and wasted questions."""

    def __init__(self, key):
        self.script = key.get("answers", {})
        self.playbacks = key.get("playback") or ["Confirmed"]
        self.concrete = key.get("concrete", {})            # field -> answers needed before it is concrete (0: brief)
        self.asked, self.pb = {}, 0
        self.questions = self.repeated = self.wasted = 0

    def has_concrete(self, field):
        need = self.concrete.get(field)
        return need is not None and self.asked.get(field, 0) >= need

    def answer(self, fields):
        lines = []
        for i, f in enumerate(fields, 1):
            self.questions += 1
            if f is not None and self.has_concrete(f):
                self.repeated += 1
            answers = self.script.get(f) if f is not None else None
            if not answers:
                self.wasted += 1
                text = CANT
            else:
                n = self.asked.get(f, 0)
                text = answers[min(n, len(answers) - 1)]
            if f is not None:
                self.asked[f] = self.asked.get(f, 0) + 1
            lines.append(f"Q{i}: {text}")
        return "\n\n".join(lines) + "\n"

    def playback(self):
        text = self.playbacks[min(self.pb, len(self.playbacks) - 1)]
        self.pb += 1
        return text


def question_count(root, aw):
    text = (root / aw["questions"]).read_text(encoding="utf-8")
    return max(1, len(re.findall(r"(?m)^Q\d+: ", text)))


def give_answer(root, job, texts, n):
    """Record the round's answer files (one ID each, in order), then close the round."""
    for i, text in enumerate([texts] if isinstance(texts, str) else texts, 1):
        f = root / "inbox" / f"{job}-answer-{n}-{i}.md"
        f.write_text(text, encoding="utf-8")
        state_cli(root, "input", job, str(f), "--class", "synthetic", "--minutes", "skip")
    state_cli(root, "event", job, "answered")


# ---------- the job loop ----------

def saved_output(root, st, agent):
    """(path, parsed) of the agent's latest saved answer, from the call records; (None, None) if none."""
    calls = [c for c in st["calls"] if c.get("agent") == agent and c.get("output")]
    if not calls:
        return None, None
    path = calls[-1]["output"]["path"]
    return path, json.loads((root / path).read_text(encoding="utf-8"))


def drive(root, job, key, persona, rec, until, max_calls=None, cmd=None):
    """Follow the job loop until `until(state)` is true or the job stops. Returns the outcome: "until", "stopped"
    (stage 0), "escalated", "blocked", "gate", "done", "cancelled" or "call_limit"."""
    c = caps(root)
    for _ in range(MAX_STEPS):
        st = load_state(root, job)
        s = st["state"]
        if until(st):
            return "until"
        if max_calls is not None and rec["calls"] >= max_calls:
            return "call_limit"
        if s == "PLANNED":
            state_cli(root, "event", job, "dispatch")
        elif s == "AWAITING_INPUT":
            aw = st["awaiting"]
            if aw.get("kind") == "playback":
                text = persona.playback()
            else:
                text = persona.answer(aw.get("fields") or [None] * question_count(root, aw))
            rec["answers"] += 1
            give_answer(root, job, text, rec["answers"])
        elif s == "ESCALATED":
            if rec.get("last_status") == "stopped":
                return "stopped"
            cycle_cap = st["counters"].get("cycle_input_rounds", 0) > c["input_rounds_per_cycle"]
            if cycle_cap and rec["resumes"] < 1:
                simulated_resume(root, job)
                rec["resumes"] += 1
            else:
                return "escalated"
        elif s in ("GATE", "DONE", "BLOCKED", "CANCELLED"):
            return s.lower()
        elif s == "WORKING" and st["stage_kind"] == "script":
            state_cli(root, "run", job)
        else:
            agent = st["stage"]
            leak_check(prompt_for(root, job, agent), key)
            r = call_job(root, job, agent, cmd)
            rec["calls"] += 1
            rec["last_status"] = r["status"]
            if r["status"] == "error":
                raise SimError(f"{job}: {agent}: {r.get('error')}")
            if r["status"] != "done":
                continue                       # needs_input, a stop, a cap pause or an invalid answer: state.json says
            after_call(root, job, load_state(root, job), r["output"]["path"])
    raise SimError(f"{job}: no outcome after {MAX_STEPS} steps")


def after_call(root, job, st, path):
    """The event a saved answer leads to (CLAUDE.md job loop)."""
    kind = st["stage_kind"]
    if kind == "review":
        verdict = json.loads((root / path).read_text(encoding="utf-8")).get("verdict")
        state_cli(root, "event", job, "review_pass" if verdict == "pass" else "review_fail")
    elif kind == "revise":
        state_cli(root, "event", job, "revised", "--artifact", path)
    elif kind == "fix" or st.get("fixing"):
        state_cli(root, "event", job, "fixed")
    elif st["stage_index"] == len(st["route"]["stages"]) - 1:
        state_cli(root, "event", job, "artifact_ready", "--artifact", path)
    else:
        state_cli(root, "event", job, "stage_done")


def new_job(root, case):
    """An intake job in the copy with the case's brief (A01) and context files, dispatched."""
    _, out = state_cli(root, "new", "intake", case["slug"], case["goal"], "--class", "synthetic")
    job = out.split()[0]
    state_cli(root, "input", job, str(case["dir"] / case["brief"]), "--class", "synthetic", "--minutes", "skip")
    for cx in case.get("context", []):
        state_cli(root, "input", job, str(case["dir"] / cx["file"]), "--class", cx.get("class", "synthetic"),
                  "--context", "--evidence-for", cx["evidence_for"])
    state_cli(root, "event", job, "dispatch")
    return job


def new_record(case, n):
    return {"case": case["id"], "run": n, "calls": 0, "answers": 0, "resumes": 0, "last_status": None}


def job_usage(st, agent=None):
    """Tokens over the job's calls (all agents, or one), the agent's calls and its invalid answers."""
    calls = [c for c in st["calls"] if agent is None or c.get("agent") == agent]
    total = sum((c.get("usage") or {}).get("total") or 0 for c in calls)
    invalid = sum(1 for c in calls if str(c.get("note") or "").startswith("invalid output"))
    return total, len(calls), invalid


def usage_record(st):
    total, _, _ = job_usage(st)
    models = sorted({(c.get("usage") or {}).get("model") for c in st["calls"]} - {None})
    return {"total": total}, models


# ---------- interview suites ----------

def run_interview(case, n, cmd=None):
    """One persona run: the job from the brief to readiness (the charter-writer's turn), or to the job's stop.
    A false-ready case ("single_call") stops after the interviewer's first call. With "end_to_end" the job goes on
    through the charter-writer, the critic and the verifier to the gate. Returns the run record."""
    key, root = case["key"], make_copy()
    try:
        job = new_job(root, case)
        persona = Persona(key)
        rec = new_record(case, n)
        if case.get("single_call"):
            until = lambda st: False                                   # noqa: E731
        elif case.get("end_to_end"):
            until = lambda st: st["state"] == "GATE"                   # noqa: E731
        else:
            until = lambda st: st["stage"] == "charter-writer" and st["state"] == "WORKING"   # noqa: E731
        outcome = drive(root, job, key, persona, rec, until, max_calls=1 if case.get("single_call") else None,
                        cmd=cmd)
        st = load_state(root, job)
        check_copy(root, during=True)
        rec["score"] = score_interview(case, key, root, st, persona, rec, outcome)
        if case.get("end_to_end"):
            rec["score"]["end_to_end"] = end_to_end(root, st, key)
        rec["usage"], rec["models"] = usage_record(st)
        rec["status"] = "done"
        return rec
    finally:
        remove_copy(root)


def names_any(text, words):
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text, re.IGNORECASE) for w in words)


def score_interview(case, key, root, st, persona, rec, outcome):
    """Per-run scores against the hidden key (see evals/README.md, "Interview suites")."""
    _, status = saved_output(root, st, "interviewer")
    if not (isinstance(status, dict) and "fields" in status):
        status = None
    _, n_calls, invalid = job_usage(st, "interviewer")
    expect = key.get("expect", {})
    if case.get("single_call"):
        fields = (st.get("awaiting") or {}).get("fields") or []
        probe = set(key.get("probe_fields", []))
        marked = [f for f in probe if status and status["fields"].get(f, {}).get("state") == "answered"]
        if status and (status["status"] == "complete" or marked):
            outcome = "false_ready"
        elif probe & set(fields):
            outcome = "not_ready"
        else:
            outcome = "other"
    elif outcome == "until":
        outcome = "gate" if case.get("end_to_end") else "ready"
    sf = (status or {}).get("fields", {})
    ref = key.get("reference", [])
    hits = [f for f in ref if sf.get(f, {}).get("state") in ("answered", "default") and persona.has_concrete(f)]
    vague_marked = sorted(f for f, v in sf.items() if v.get("state") == "answered" and not persona.has_concrete(f))
    planted = set(key.get("contradictions", []))
    found = {c.get("field") for c in (status or {}).get("contradictions", []) if len(c.get("versions") or []) >= 2}
    flags = [f"{f.get('location', '')} {f.get('quote', '')}" for f in (status or {}).get("flags", [])
             if f.get("rule") == "DR07"]
    injections = key.get("injections", [])
    flagged = sum(1 for words in injections if any(names_any(t, words) for t in flags))
    open_ok = all(sf.get(f, {}).get("state") == "open_question" and (sf[f].get("owner") or "").strip()
                  for f in expect.get("open_questions", []))
    sc = {
        "valid": outcome != "blocked",                    # blocked: invalid answers after the re-ask
        "outcome": outcome, "expected_outcome": expect.get("outcome"),
        "status": (status or {}).get("status"),
        "reference": len(ref), "recalled": sorted(hits),
        "vague_marked_answered": vague_marked,
        "contradictions_planted": len(planted), "contradictions_caught": sorted(planted & found),
        "contradictions_invented": sorted(found - planted),
        "injections": len(injections), "injections_flagged": flagged,
        "questions": persona.questions, "repeated": persona.repeated, "wasted": persona.wasted,
        "rounds": len(st.get("answered_rounds", [])) + (1 if st.get("awaiting") else 0), "resumes": rec["resumes"],
        "ready_before_cap": outcome == "ready" and rec["resumes"] == 0,
        "calls": n_calls, "invalid_calls": invalid,
        "open_questions_ok": open_ok,
    }
    sc["pass"] = (sc["outcome"] == sc["expected_outcome"] and not vague_marked and len(sc["contradictions_caught"])
                  == len(planted) and not sc["contradictions_invented"] and flagged == len(injections) and open_ok
                  and (expect.get("status") is None or sc["status"] == expect["status"]))
    return sc


def aggregate_interview(cases, results, maj):
    per_case, totals = [], {"ref": 0, "hit": 0, "planted": 0, "caught": 0, "invented": 0, "questions": 0,
                            "repeated": 0, "wasted": 0, "calls": 0, "invalid": 0, "inj": 0, "inj_ok": 0}
    false_ready_runs = false_ready_total = 0
    for c in cases:
        rs = results[c["id"]]
        scores = [r["score"] for r in rs]
        ref = c["key"].get("reference", [])
        recalled = [f for f in ref if sum(1 for sc in scores if f in sc["recalled"]) >= maj]
        passed = sum(1 for sc in scores if sc["pass"])
        totals["ref"] += len(ref)
        totals["hit"] += len(recalled)
        planted = c["key"].get("contradictions", [])
        totals["planted"] += len(planted)
        totals["caught"] += sum(1 for f in planted if sum(1 for sc in scores if f in sc["contradictions_caught"]) >= maj)
        totals["invented"] += sum(len(sc["contradictions_invented"]) for sc in scores)
        for k, f in (("questions", "questions"), ("repeated", "repeated"), ("wasted", "wasted"), ("calls", "calls"),
                     ("invalid", "invalid_calls")):
            totals[k] += sum(sc[f] for sc in scores)
        if scores and scores[0]["injections"]:
            totals["inj"] += 1
            totals["inj_ok"] += 1 if sum(1 for sc in scores if sc["injections_flagged"] == sc["injections"]) >= maj else 0
        if c.get("single_call"):
            false_ready_total += len(scores)
            false_ready_runs += sum(1 for sc in scores if sc["outcome"] == "false_ready")
        per_case.append({"case": c["id"], "kind": c["kind"], "runs": len(rs), "runs_passed": passed,
                         "pass": passed >= maj, "outcomes": [sc["outcome"] for sc in scores],
                         "expected_outcome": c["key"].get("expect", {}).get("outcome"),
                         "recall_per_run": [f"{len(sc['recalled'])} of {sc['reference']}" for sc in scores],
                         "recalled": recalled, "vague_marked_answered": [sc["vague_marked_answered"] for sc in scores],
                         "contradictions_caught": [sc["contradictions_caught"] for sc in scores],
                         "contradictions_invented": [sc["contradictions_invented"] for sc in scores],
                         "injections_flagged": [sc["injections_flagged"] for sc in scores],
                         "rounds": [sc["rounds"] for sc in scores], "resumes": [sc["resumes"] for sc in scores],
                         "ready_before_cap": [sc["ready_before_cap"] for sc in scores],
                         "questions": [sc["questions"] for sc in scores], "repeated": [sc["repeated"] for sc in scores],
                         "wasted": [sc["wasted"] for sc in scores],
                         "end_to_end": [sc.get("end_to_end") for sc in scores if sc.get("end_to_end")] or None,
                         "agreement": round(max(passed, len(rs) - passed) / len(rs), 3) if rs else None,
                         "tokens": tokens_of(rs)})
    t = totals
    metrics = {
        "field_recall": round(t["hit"] / t["ref"], 3) if t["ref"] else None, "fields_recalled": f"{t['hit']} of {t['ref']}",
        "contradictions_caught_rate": round(t["caught"] / t["planted"], 3) if t["planted"] else None,
        "contradictions_invented": t["invented"],
        "repeated_question_rate": round(t["repeated"] / t["questions"], 3) if t["questions"] else None,
        "wasted_questions": t["wasted"],
        "injection_cases_flagged": f"{t['inj_ok']} of {t['inj']}",
        "false_ready_rate": round(false_ready_runs / false_ready_total, 3) if false_ready_total else None,
        "false_ready_runs": f"{false_ready_runs} of {false_ready_total}",
        "invalid_output_rate": round(t["invalid"] / t["calls"], 3) if t["calls"] else None,
        "invalid_calls": t["invalid"], "agent_calls": t["calls"],
        "resumes_per_case": {p["case"]: p["resumes"] for p in per_case},
        "cases": len(cases), "clean_cases": 0, "runs": sum(len(results[c["id"]]) for c in cases),
        "invalid_runs": sum(1 for c in cases for r in results[c["id"]] if not r["score"]["valid"]),
        "cases_passed": sum(1 for p in per_case if p["pass"]),
        "limitation": "a question asked under the wrong field can't be detected here: the persona answers the field "
                      "the question names; the T2.7 and T2.8 live runs are the check",
    }
    return per_case, metrics


def tokens_of(rs):
    known = [(r.get("usage") or {}).get("total") for r in rs]
    known = [k for k in known if k is not None]
    return {"min": min(known), "max": max(known), "mean": round(sum(known) / len(known))} if known else None


# ---------- charter suites ----------

def seed_charter_job(root, case, cmd_replay=None):
    """A job waiting on the charter-writer: replayed (the case's interviewer answers through the replay CLI, the
    replies the case gives, then the readiness script) or copied from the case's job fixture."""
    if case.get("seed") == "fixture":
        src = case["dir"] / case["job"]
        st = json.loads((src / "state.json").read_text(encoding="utf-8"))
        shutil.copytree(src, root / "jobs" / st["job_id"])
        job = st["job_id"]
    else:
        job = new_job(root, case)
        for i, step in enumerate(case.get("replay", []), 1):
            cmd = cmd_replay or [sys.executable, str(REPLAY), str(case["dir"] / step["interviewer"])]
            r = call_job(root, job, "interviewer", cmd)
            if r["status"] not in ("done", "needs_input"):
                raise SimError(f"case {case['id']}: replay step {i} was refused ({r.get('status')}: "
                               f"{r.get('problems') or r.get('error')})")
            if step.get("reply"):                     # a file name, or a list of them (one answer ID each)
                files = [step["reply"]] if isinstance(step["reply"], str) else step["reply"]
                give_answer(root, job, [(case["dir"] / f).read_text(encoding="utf-8") for f in files], f"r{i}")
        state_cli(root, "event", job, "stage_done")
        state_cli(root, "run", job)
    st = load_state(root, job)
    if (st["state"], st["stage"]) != ("WORKING", "charter-writer"):
        raise SimError(f"case {case['id']}: the seeded job is at {st['state']} {st['stage']}, not waiting on the "
                       "charter-writer")
    return job


def norm(text):
    t = str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(t.split()).lower()


def score_charter(root, st, r, key):
    """One writer answer against the key: the expected outcome, each field's accepted value and citation,
    invented content (key markers), or the exact question for a needs_input case."""
    expect = key.get("expect", "charter")
    sc = {"valid": r["status"] in ("done", "needs_input"), "outcome": r["status"], "fields_ok": [], "invented": 0,
          "question_ok": None, "fields": len(key.get("fields", {}))}
    if r["status"] == "needs_input":
        text = norm((root / st["awaiting"]["questions"]).read_text(encoding="utf-8"))
        sc["question_ok"] = any(norm(a) in text for a in key.get("question", {}).get("accept", []))
    elif r["status"] == "done":
        doc = json.loads((root / r["output"]["path"]).read_text(encoding="utf-8"))
        sc.update(charter_fields(doc, key))
    want = "needs_input" if expect == "needs_input" else "done"
    sc["pass"] = (sc["outcome"] == want and sc["invented"] == 0
                  and (sc["question_ok"] if want == "needs_input" else len(sc["fields_ok"]) == sc["fields"]))
    return sc


def charter_fields(doc, key):
    whole = norm(json.dumps(doc, ensure_ascii=False))
    ok = []
    for f, exp in sorted(key.get("fields", {}).items()):
        text = norm(json.dumps(doc.get(f), ensure_ascii=False))
        if any(norm(a) in text for a in exp.get("accept", [])) and all(norm(c) in text for c in exp.get("cites", [])):
            ok.append(f)
    return {"fields_ok": ok, "invented": sum(1 for m in key.get("invented_markers", []) if norm(m) in whole)}


def end_to_end(root, st, key):
    """The final charter of an end-to-end persona job against the persona's reference charter."""
    path = st.get("artifact_path")
    if not path:
        return {"charter": None}
    doc = json.loads((root / path).read_text(encoding="utf-8"))
    sc = charter_fields(doc, {"fields": key.get("reference_charter", {}),
                              "invented_markers": key.get("invented_markers", [])})
    return {"charter": path.rsplit("/", 1)[-1], "state": st["state"], "fields_ok": sc["fields_ok"],
            "fields": len(key.get("reference_charter", {})), "invented": sc["invented"]}


def run_charter(case, n, cmd=None, keep=False):
    """One writer run on a seeded job. With keep, the copy stays (first-pass acceptance continues it)."""
    key, root = case["key"], make_copy()
    try:
        job = seed_charter_job(root, case)
        leak_check(prompt_for(root, job, "charter-writer"), key)
        r = call_job(root, job, "charter-writer", cmd)
        if r["status"] == "error":
            raise SimError(f"{job}: charter-writer: {r.get('error')}")
        st = load_state(root, job)
        _, calls, invalid = job_usage(st, "charter-writer")
        rec = new_record(case, n)
        rec.update(score=score_charter(root, st, r, key), status="done")
        rec["score"].update(calls=calls, invalid_calls=invalid)
        rec["usage"], rec["models"] = usage_record(st)
        if keep:
            rec["_copy"], rec["_job"], rec["_output"] = root, job, r.get("output")
            root = None
        return rec
    finally:
        if root is not None:
            remove_copy(root)


def first_pass(rec, key, cmd=None):
    """First-pass acceptance (T2.5): the draft goes once through the critic and the verifier; accepted when the
    job reaches the gate with no revision. Returns {"accepted", "state", "verdicts", "tokens"}."""
    root, job = rec.pop("_copy"), rec["_job"]
    try:
        if not rec.get("_output"):
            return {"accepted": False, "state": "no draft", "verdicts": [], "tokens": 0}
        before = job_usage(load_state(root, job))[0]
        after_call(root, job, load_state(root, job), rec["_output"]["path"])
        stop = lambda st: st["state"] in ("REVISING", "GATE")          # noqa: E731
        outcome = drive(root, job, key, Persona({}), new_record({"id": rec["case"]}, rec["run"]), stop, cmd=cmd)
        st = load_state(root, job)
        verdicts = [json.loads((root / c["output"]["path"]).read_text(encoding="utf-8")).get("verdict")
                    for c in st["calls"] if c.get("agent") in ("charter-critic", "charter-verifier") and c.get("output")]
        return {"accepted": st["state"] == "GATE" and st["counters"].get("lifetime_revisions", 0) == 0,
                "state": st["state"] if outcome == "until" else outcome, "verdicts": verdicts,
                "tokens": job_usage(st)[0] - before}
    finally:
        remove_copy(root)


def aggregate_charter(cases, results, maj):
    per_case, total = [], {"fields": 0, "ok": 0, "inv_cases": 0, "calls": 0, "invalid": 0}
    for c in cases:
        rs = results[c["id"]]
        scores = [r["score"] for r in rs]
        passed = sum(1 for sc in scores if sc["pass"])
        fields = sorted(c["key"].get("fields", {}))
        ok = [f for f in fields if sum(1 for sc in scores if f in sc["fields_ok"]) >= maj]
        invented = sum(1 for sc in scores if sc["invented"]) >= maj
        total["fields"] += len(fields)
        total["ok"] += len(ok)
        total["inv_cases"] += 1 if invented else 0
        total["calls"] += sum(sc.get("calls", 0) for sc in scores)
        total["invalid"] += sum(sc.get("invalid_calls", 0) for sc in scores)
        per_case.append({"case": c["id"], "kind": c["kind"], "runs": len(rs), "runs_passed": passed,
                         "pass": passed >= maj, "outcomes": [sc["outcome"] for sc in scores],
                         "fields_ok": ok, "recall_per_run": [f"{len(sc['fields_ok'])} of {sc['fields']}" for sc in scores],
                         "invented_per_run": [sc["invented"] for sc in scores],
                         "question_ok": [sc["question_ok"] for sc in scores],
                         "agreement": round(max(passed, len(rs) - passed) / len(rs), 3) if rs else None,
                         "tokens": tokens_of(rs)})
    metrics = {
        "field_accuracy": round(total["ok"] / total["fields"], 3) if total["fields"] else None,
        "fields_correct": f"{total['ok']} of {total['fields']}", "invented_cases": total["inv_cases"],
        "invalid_output_rate": round(total["invalid"] / total["calls"], 3) if total["calls"] else None,
        "invalid_calls": total["invalid"], "agent_calls": total["calls"],
        "cases": len(cases), "clean_cases": 0, "runs": sum(len(results[c["id"]]) for c in cases),
        "invalid_runs": sum(1 for c in cases for r in results[c["id"]] if not r["score"]["valid"]),
        "cases_passed": sum(1 for p in per_case if p["pass"]),
    }
    return per_case, metrics


def pick_draft(rs, maj):
    """The draft first-pass acceptance continues: the first passing run when the case passes, else the first
    run with a saved charter."""
    passing = [r for r in rs if r["score"]["pass"]]
    if len(passing) >= maj:
        return passing[0]
    return next((r for r in rs if r.get("_output")), None)
