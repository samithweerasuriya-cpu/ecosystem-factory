"""Deterministic core of the engine: job state machine, caps, gate tokens.

Derived from the author's earlier private lab. Stdlib only. Agents never edit state.json
directly; every change goes through apply()/new_job()/record_call()/set_fanout()/
fanout_result()/run_script(). Human-only events (approve, reject) are reachable only
through approve_gate()/reject_gate(), which engine/gate.py calls after an interactive
terminal confirmation. Routes, caps, scripts and the approver name come from config/;
no agent name is written into this file.
"""
import datetime
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import schemacheck  # noqa: E402

ROOT = Path(os.environ.get("LAB_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or ENGINE.parent)
JOBS = ROOT / "jobs"
LAB = ROOT / ".lab"
CONFIG = ROOT / "config"
SCHEMAS = ROOT / "schemas"

TERMINAL = {"DONE", "CANCELLED"}
PAUSED = {"BLOCKED", "ESCALATED"}
HUMAN_ONLY = {"approve", "reject"}
SCRIPT_ONLY = {"script_fail"}
KIND_STATE = {"critic": "REVIEW", "verifier": "VERIFY"}
JOB_ID_RE = re.compile(r"^\d{8}-[a-z]+-[a-z0-9-]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PER_CYCLE = ("critic_revisions", "verifier_revisions", "total_revisions", "fix_attempts", "infra_errors")
# Script argv placeholders: {job}, {job_dir}, {root}; an argv entry of exactly "{python}"
# becomes the interpreter running the engine (so script stages need no venv on PATH).


class LabError(Exception):
    code = 1


class CapExceeded(LabError):
    code = 3


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    # Windows: replace fails while another process (antivirus, indexer) briefly holds the target open.
    for attempt in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


# ---------- config ----------

def caps():
    return load_json(CONFIG / "caps.json")


def scripts():
    f = CONFIG / "scripts.json"
    return load_json(f).get("scripts", {}) if f.exists() else {}


def approver():
    """Approver name from config/gates.json; falls back to the OS user name."""
    f = CONFIG / "gates.json"
    name = load_json(f).get("approver") if f.exists() else None
    return name or getpass.getuser()


def stage_kind(stage):
    return "fanout" if "fanout" in stage else "script" if "script" in stage else "agent"


def stage_name(stage):
    k = stage_kind(stage)
    return stage["fanout"]["agent"] if k == "fanout" else stage[k]


def route_errors(data, cap=None, allowed_scripts=None):
    """Schema plus semantic checks for config/routes.json. Returns a list of messages."""
    schema = load_json(SCHEMAS / "route.schema.json")
    errs = schemacheck.check(data, schema)
    if errs:
        return errs
    cap = caps() if cap is None else cap
    allowed_scripts = scripts() if allowed_scripts is None else allowed_scripts
    for sname, spec in allowed_scripts.items():
        argv, timeout = spec.get("argv"), spec.get("timeout")
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            errs.append(f"scripts.{sname}: argv must be a non-empty list of strings")
        if not (isinstance(timeout, int) and not isinstance(timeout, bool) and 1 <= timeout <= 3600):
            errs.append(f"scripts.{sname}: timeout must be whole seconds, 1-3600")
    for name, r in data["routes"].items():
        where = f"routes.{name}"
        stages = r["stages"]
        authors = ({stage_name(s) for s in stages if stage_kind(s) != "script"}
                   | {r["revise_with"]} | ({r["fix_with"]} if r.get("fix_with") else set()))
        if r.get("deliver") and not r.get("gate"):
            errs.append(f"{where}: delivery needs a gate (deliver runs only after approval)")
        for i, s in enumerate(stages):
            k = stage_kind(s)
            if k == "fanout":
                if s["fanout"]["max"] > cap["fanout_max"]:
                    errs.append(f"{where}.stages[{i}]: fanout max {s['fanout']['max']} exceeds caps.fanout_max {cap['fanout_max']}")
                if i == len(stages) - 1 or stage_kind(stages[i + 1]) != "agent":
                    errs.append(f"{where}.stages[{i}]: a fanout stage must be followed by an agent (merge) stage")
            if k == "script":
                if s["script"] not in allowed_scripts:
                    errs.append(f"{where}.stages[{i}]: script {s['script']!r} is not in config/scripts.json")
                elif i == len(stages) - 1 and not allowed_scripts[s["script"]].get("artifact"):
                    errs.append(f"{where}.stages[{i}]: a final script stage needs an 'artifact' in config/scripts.json")
                if not r.get("fix_with"):
                    errs.append(f"{where}: routes with a script stage need fix_with")
        for rv in r["reviews"]:
            if rv["agent"] in authors:
                errs.append(f"{where}: {rv['agent']} reviews work it authors")
    return errs


def routes():
    data = load_json(CONFIG / "routes.json")
    errs = route_errors(data)
    if errs:
        raise LabError("config/routes.json is invalid: " + "; ".join(errs))
    return data["routes"]


# ---------- jobs: paths and hashing ----------

def job_dir(job_id):
    if not JOB_ID_RE.match(job_id or ""):
        raise LabError(f"invalid job id: {job_id!r}")
    d = JOBS / job_id
    if not d.exists():
        raise LabError(f"job not found: {job_id}")
    return d


def load_state(job_id):
    return load_json(job_dir(job_id) / "state.json")


def log(job_id, entry):
    entry = {"ts": now(), "job_id": job_id, **entry}
    with open(JOBS / job_id / "run.log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def rel(path):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    try:
        return p.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        raise LabError(f"path outside repo: {path}")


def sha256_path(path):
    p = ROOT / path
    h = hashlib.sha256()
    if p.is_file():
        h.update(p.read_bytes())
    elif p.is_dir():
        for f in sorted(x for x in p.rglob("*") if x.is_file() and x.name != ".DS_Store"):
            h.update(f.relative_to(p).as_posix().encode())
            h.update(b"\0")
            h.update(f.read_bytes())
    else:
        raise LabError(f"artifact not found: {path}")
    return h.hexdigest()


# ---------- gates ----------

def gate_file(job_id, gate):
    return JOBS / job_id / "gates" / f"{gate}.json"


def verify_gate(job_id, gate):
    """Return (ok, reason). Token must exist and match the artifact's current hash."""
    try:
        job_dir(job_id)
    except LabError as e:
        return False, str(e)
    gf = gate_file(job_id, gate)
    if not gf.exists():
        return False, f"no {gate} token for {job_id}"
    tok = load_json(gf)
    try:
        current = sha256_path(tok["artifact_path"])
    except LabError as e:
        return False, str(e)
    if current != tok["sha256"]:
        return False, f"{gate} token void: artifact changed after approval"
    return True, "ok"


def approve_gate(job_id, note="", actor=None):
    actor = actor or approver()
    st = load_state(job_id)
    if st["state"] != "GATE":
        raise LabError(f"{job_id} is {st['state']}, not GATE")
    gate = st["route"]["gate"]
    token = {"gate": gate, "job_id": job_id, "artifact_path": st["artifact_path"],
             "sha256": sha256_path(st["artifact_path"]), "approved_by": actor,
             "approved_at": now(), "note": note}
    save_json(gate_file(job_id, gate), token)
    return apply(job_id, "approve", note=note, actor=actor, _human=True)


def gate_audit(action, job_id=None, **detail):
    """Append one human gate action to logs/gate-audit.jsonl (hook-protected; written only by gate.py)."""
    rec = {"ts": now(), "action": action, "job_id": job_id, "approver": approver(), "os_user": getpass.getuser()}
    if job_id:
        try:
            st = load_state(job_id)
            rec.update(gate=st["route"]["gate"], state=st["state"], artifact_path=st["artifact_path"],
                       sha256=sha256_path(st["artifact_path"]) if st["artifact_path"] else None)
        except LabError as e:
            rec["state_error"] = str(e)
    rec.update(detail)
    (ROOT / "logs").mkdir(exist_ok=True)
    with open(ROOT / "logs" / "gate-audit.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def reject_gate(job_id, feedback, actor=None):
    actor = actor or approver()
    st = load_state(job_id)
    if st["state"] != "GATE":
        raise LabError(f"{job_id} is {st['state']}, not GATE")
    n = st["counters"]["gate_rejections"] + 1
    fb = JOBS / job_id / "reviews" / f"human-feedback-{n}.md"
    fb.write_text(f"# Human feedback {n} ({now()})\n\n{feedback}\n", encoding="utf-8")
    return apply(job_id, "reject", note=rel(fb), actor=actor, _human=True)


# ---------- jobs ----------

def new_job(jtype, slug, goal, parent=None):
    all_routes = routes()
    r = all_routes.get(jtype)
    if r is None:
        raise LabError(f"unknown job type: {jtype}; valid: {sorted(all_routes)}")
    if not SLUG_RE.match(slug or ""):
        raise LabError("slug must be lowercase letters, digits, hyphens")
    if r.get("requires_parent_gate"):
        if not parent:
            raise LabError(f"{jtype} jobs need --parent with {r['requires_parent_gate']}")
        ok, why = verify_gate(parent, r["requires_parent_gate"])
        if not ok:
            raise LabError(f"parent not approved: {why}")
    base = f"{datetime.date.today():%Y%m%d}-{jtype}-{slug}"
    job_id, i = base, 2
    while (JOBS / job_id).exists():
        job_id, i = f"{base}-{i}", i + 1
    d = JOBS / job_id
    for sub in ("research", "drafts", "reviews", "gates", "delivery"):
        (d / sub).mkdir(parents=True)
    (d / "brief.md").write_text(f"# Brief: {job_id}\n\nType: {jtype}\nParent: {parent or '-'}\n\n## Goal\n{goal}\n", encoding="utf-8")
    st = {"job_id": job_id, "type": jtype, "goal": goal, "parent": parent,
          "route": r, "state": "NEW", "stage": None, "stage_kind": None, "stage_index": 0,
          "review_index": 0, "fanout": None, "fixing": False,
          "artifact_path": None, "resume_to": None, "last_failed_by": None,
          "counters": {k: 0 for k in PER_CYCLE + ("gate_rejections", "agent_calls")},
          "created": now(), "updated": now()}
    save_json(d / "state.json", st)
    log(job_id, {"event": "created", "from": None, "to": "NEW", "actor": "orchestrator"})
    return apply(job_id, "plan")


def _save(job_id, st, entry):
    st["updated"] = now()
    save_json(JOBS / job_id / "state.json", st)
    log(job_id, {**entry, "counters": st["counters"]})


def apply(job_id, event, artifact=None, note=None, actor="orchestrator", _human=False, _script=False):
    if event in HUMAN_ONLY and not _human:
        raise LabError(f"'{event}' is human-only; the approver runs engine/gate.py in their own terminal")
    if event in SCRIPT_ONLY and not _script:
        raise LabError(f"'{event}' is recorded only by 'state.py run'")
    st = load_state(job_id)
    cur, r, c = st["state"], st["route"], caps()
    if cur in TERMINAL:
        raise LabError(f"{job_id} is terminal ({cur})")
    work, reviews = r["stages"], r["reviews"]
    new, capmsg = None, None

    def enter_stage(i):
        st["stage_index"], st["fanout"], st["fixing"] = i, None, False
        st["stage_kind"], st["stage"] = stage_kind(work[i]), stage_name(work[i])
        return "WORKING"

    def enter_review(i):
        st["review_index"], st["stage_kind"], st["stage"] = i, "review", reviews[i]["agent"]
        return KIND_STATE[reviews[i]["kind"]]

    def cap(counter, cap_name, resume_to, paused="ESCALATED"):
        nonlocal capmsg
        st["counters"][counter] += 1
        if st["counters"][counter] > c[cap_name]:
            capmsg = f"cap exceeded: {cap_name}={c[cap_name]}"
            st["resume_to"] = resume_to
            return paused
        return None

    def script_stage():
        return cur == "WORKING" and st["stage_kind"] == "script" and not st["fixing"]

    if event in ("block", "escalate", "cancel"):
        if event == "cancel":
            new = "CANCELLED"
        else:
            if cur not in PAUSED:
                st["resume_to"] = cur
            new = "BLOCKED" if event == "block" else "ESCALATED"
    elif event == "resume":
        if cur not in PAUSED:
            raise LabError(f"resume only from BLOCKED/ESCALATED, not {cur}")
        new = st["resume_to"]
        for k in PER_CYCLE:
            st["counters"][k] = 0
        st["counters"]["agent_calls"] = 0
        st["resume_to"] = None
    elif (cur, event) == ("NEW", "plan"):
        new = "PLANNED"
    elif (cur, event) == ("PLANNED", "dispatch"):
        new = enter_stage(0)
    elif (cur, event) == ("WORKING", "stage_done"):
        if st["fixing"]:
            raise LabError("fix in progress: record 'fixed' when the fix agent is done")
        if script_stage() and not _script:
            raise LabError("script stages complete only through 'state.py run'")
        if st["stage_kind"] == "fanout":
            fo = st["fanout"]
            if not fo:
                raise LabError("fanout stage: set the item list first ('state.py fanout')")
            open_items = [k for k, v in fo["items"].items() if v["status"] not in ("done", "failed")]
            if open_items:
                raise LabError(f"fanout items not yet returned: {open_items}")
        if st["stage_index"] >= len(work) - 1:
            raise LabError("last work stage: use artifact_ready")
        new = enter_stage(st["stage_index"] + 1)
        st["counters"]["infra_errors"] = 0
    elif (cur, event) == ("WORKING", "artifact_ready"):
        if st["stage_index"] != len(work) - 1 or st["fixing"]:
            raise LabError(f"work stages remain; current stage {st['stage']}")
        if script_stage() and not _script:
            raise LabError("script stages complete only through 'state.py run'")
        if not artifact:
            raise LabError("artifact_ready needs --artifact")
        st["artifact_path"] = rel(artifact)
        sha256_path(st["artifact_path"])
        new = enter_review(0)
    elif (cur, event) == ("WORKING", "script_fail"):
        if not script_stage():
            raise LabError("script_fail only on a script stage")
        new = cap("fix_attempts", "fix_attempts", "WORKING") or "WORKING"
        if new == "WORKING":
            st["fixing"], st["stage_kind"], st["stage"] = True, "fix", r["fix_with"]
    elif (cur, event) == ("WORKING", "fixed"):
        if not st["fixing"]:
            raise LabError("no fix in progress")
        new = enter_stage(st["stage_index"])
    elif cur in ("WORKING", "REVIEW", "VERIFY", "REVISING", "DELIVERING") and event == "infra_error":
        new = cap("infra_errors", "infra_retries", cur, paused="BLOCKED") or cur
    elif cur in ("REVIEW", "VERIFY") and event == "review_pass":
        if st["review_index"] < len(reviews) - 1:
            new = enter_review(st["review_index"] + 1)
        else:
            new = "GATE" if r["gate"] else "DONE"
            st["stage_kind"], st["stage"] = None, None
    elif cur in ("REVIEW", "VERIFY") and event == "review_fail":
        rv = reviews[st["review_index"]]
        st["last_failed_by"] = rv["agent"]
        kind = rv["kind"]
        new = (cap(f"{kind}_revisions", f"{kind}_revisions", "REVISING")
               or cap("total_revisions", "total_revisions_before_gate", "REVISING")
               or "REVISING")
        st["stage_kind"], st["stage"] = "revise", r["revise_with"]
    elif (cur, event) == ("REVISING", "revised"):
        if not artifact:
            raise LabError("revised needs --artifact (the new version)")
        st["artifact_path"] = rel(artifact)
        sha256_path(st["artifact_path"])
        new = enter_review(0)
    elif (cur, event) == ("GATE", "approve"):
        new = "APPROVED"
    elif (cur, event) == ("GATE", "reject"):
        for k in ("critic_revisions", "verifier_revisions", "total_revisions"):
            st["counters"][k] = 0
        new = cap("gate_rejections", "gate_rejections", "REVISING") or "REVISING"
        st["stage_kind"], st["stage"] = "revise", r["revise_with"]
    elif (cur, event) == ("APPROVED", "deliver"):
        if not r.get("deliver"):
            raise LabError("route has no delivery stage; use complete")
        new = "DELIVERING"
        st["stage_kind"], st["stage"] = "deliver", r["deliver"]
    elif cur in ("APPROVED", "DELIVERING") and event == "complete":
        new = "DONE"
        st["stage_kind"], st["stage"] = None, None
    else:
        raise LabError(f"invalid transition: {cur} --{event}-->")

    st["state"] = new
    _save(job_id, st, {"event": event, "from": cur, "to": new, "stage": st["stage"], "actor": actor,
                       "artifact": st["artifact_path"], "note": note or capmsg})
    if capmsg:
        raise CapExceeded(f"{job_id}: {capmsg} -> {new}")
    return st


# ---------- fan-out ----------

def set_fanout(job_id, items):
    """Fix the item list of the current fanout stage (once per stage visit)."""
    st = load_state(job_id)
    if st["state"] != "WORKING" or st["stage_kind"] != "fanout":
        raise LabError(f"{job_id} is not at a fanout stage")
    if st["fanout"]:
        raise LabError("fanout item list is already fixed for this stage")
    stage = st["route"]["stages"][st["stage_index"]]["fanout"]
    limit = min(stage["max"], caps()["fanout_max"])
    if not items:
        raise LabError("fanout needs at least one item")
    if len(items) != len(set(items)):
        raise LabError("fanout item ids must be unique")
    if len(items) > limit:
        raise LabError(f"fanout of {len(items)} items exceeds max {limit}")
    bad = [i for i in items if not ITEM_RE.match(i)]
    if bad:
        raise LabError(f"invalid fanout item ids: {bad}")
    st["fanout"] = {"agent": stage["agent"], "split_by": stage["split_by"],
                    "items": {i: {"status": "pending", "calls": 0, "note": None} for i in items}}
    _save(job_id, st, {"event": "fanout", "items": items, "actor": "orchestrator"})
    return st


def fanout_result(job_id, item, status, note=None):
    if status not in ("done", "failed"):
        raise LabError("fanout result must be done or failed")
    st = load_state(job_id)
    fo = st.get("fanout")
    if st["state"] != "WORKING" or not fo:
        raise LabError(f"{job_id} has no active fanout")
    if item not in fo["items"]:
        raise LabError(f"unknown fanout item: {item}")
    if fo["items"][item]["status"] != "running":
        raise LabError(f"fanout item {item} is {fo['items'][item]['status']}, not running")
    fo["items"][item].update(status=status, note=note)
    _save(job_id, st, {"event": "fanout_result", "item": item, "status": status, "note": note,
                       "actor": "orchestrator"})
    return st


# ---------- agent calls ----------

def record_call(job_id, agent, item=None):
    st = load_state(job_id)
    if st["state"] in TERMINAL | PAUSED:
        raise LabError(f"{job_id} is {st['state']}; no agent calls allowed")
    fo = st.get("fanout")
    if st["state"] == "WORKING" and st["stage_kind"] == "fanout":
        if not fo:
            raise LabError("fanout stage: set the item list before calling agents")
        if agent != fo["agent"]:
            raise LabError(f"fanout stage runs {fo['agent']}, not {agent}")
        if item not in fo["items"]:
            raise LabError(f"fanout call needs --item, one of {sorted(fo['items'])}")
        if fo["items"][item]["status"] != "pending":
            raise LabError(f"fanout item {item} was already dispatched ({fo['items'][item]['status']})")
        fo["items"][item].update(status="running", calls=fo["items"][item]["calls"] + 1)
    elif item is not None:
        raise LabError("--item is only valid at a fanout stage")
    st["counters"]["agent_calls"] += 1
    _save(job_id, st, {"event": "agent_call", "agent": agent, "item": item, "actor": "orchestrator"})
    if st["counters"]["agent_calls"] > caps()["agent_calls_per_job"]:
        apply(job_id, "escalate", note="cap exceeded: agent_calls_per_job")
        raise CapExceeded(f"{job_id}: cap exceeded: agent_calls_per_job -> ESCALATED")
    return st


# ---------- script stages ----------

def run_script(job_id):
    """Run the current script stage's allow-listed command and record the result.

    Returns (state, record). The command, its output and exit code are saved to
    jobs/<job>/scripts/. Exit 0 completes the stage; anything else (including a
    timeout) is script_fail, which hands the job to the route's fix_with agent.
    """
    st = load_state(job_id)
    if st["state"] != "WORKING" or st["stage_kind"] != "script" or st["fixing"]:
        raise LabError(f"{job_id} is not at a script stage")
    name = st["stage"]
    spec = scripts().get(name)
    if spec is None:
        raise LabError(f"script {name!r} is not in config/scripts.json")
    d = job_dir(job_id)
    subst = {"{job}": job_id, "{job_dir}": str(d), "{root}": str(ROOT)}
    argv = []
    for a in spec["argv"]:
        for k, v in subst.items():
            a = a.replace(k, v)
        argv.append(sys.executable if a == "{python}" else a)
    out_dir = d / "scripts"
    out_dir.mkdir(exist_ok=True)
    attempt = len(list(out_dir.glob(f"{st['stage_index']:02d}-{name}-*.json"))) + 1
    rec = {"script": name, "argv": argv, "timeout_s": spec["timeout"], "started": now()}
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=spec["timeout"])
        rec.update(exit_code=p.returncode, timed_out=False, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired as e:
        rec.update(exit_code=None, timed_out=True,
                   stdout=(e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                   stderr=(e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))
    except OSError as e:
        rec.update(exit_code=None, timed_out=False, stdout="", stderr=f"could not start: {e}")
    rec["duration_s"] = round(time.monotonic() - t0, 3)
    out = out_dir / f"{st['stage_index']:02d}-{name}-{attempt}.json"
    save_json(out, rec)
    note = rel(out)
    if rec["exit_code"] == 0:
        if st["stage_index"] == len(st["route"]["stages"]) - 1:
            art = spec["artifact"].replace("{job}", job_id)
            return apply(job_id, "artifact_ready", artifact=art, note=note, actor="script", _script=True), rec
        return apply(job_id, "stage_done", note=note, actor="script", _script=True), rec
    return apply(job_id, "script_fail", note=note, actor="script", _script=True), rec


def set_active(job_id):
    job_dir(job_id)
    LAB.mkdir(exist_ok=True)
    (LAB / "active_job").write_text(job_id, encoding="utf-8")


def active_job():
    f = LAB / "active_job"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None
