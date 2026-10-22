"""Deterministic core of the engine: job state machine, caps, gate tokens.

Derived from the author's earlier private lab. Stdlib only. Agents never edit state.json
directly; every change goes through apply()/new_job()/record_call()/set_fanout()/
fanout_result()/run_script(). Human-only events (approve, reject) are reachable only
through approve_gate()/reject_gate(), which engine/gate.py calls after an interactive
terminal confirmation. Routes, caps, scripts and the approver name come from config/;
no agent name is written into this file.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import schemacheck  # noqa: E402
import check_refs  # noqa: E402

ROOT = Path(os.environ.get("LAB_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or ENGINE.parent)
JOBS = ROOT / "jobs"
PRIVATE_JOBS = ROOT / "private" / "jobs"   # internal jobs live here, entirely (untracked)
LAB = ROOT / ".lab"
CONFIG = ROOT / "config"
SCHEMAS = ROOT / "schemas"

TERMINAL = {"DONE", "CANCELLED"}
PAUSED = {"BLOCKED", "ESCALATED"}
HUMAN_ONLY = {"approve", "reject", "relink", "hold"}
CHAIN_MAX_DEPTH = 8          # deeper approval chains are treated as broken
G_CITE_RE = re.compile(r"\[G:([A-Za-z0-9._-]+)\]")
SCRIPT_ONLY = {"script_fail"}
KIND_STATE = {"critic": "REVIEW", "verifier": "VERIFY"}
JOB_ID_RE = re.compile(r"^\d{8}-[a-z]+-[a-z0-9-]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
PER_CYCLE = ("critic_revisions", "verifier_revisions", "total_revisions", "fix_attempts", "infra_errors")
# Job-lifetime counters: never reset by reject, resume or anything else.
LIFETIME = ("lifetime_agent_calls", "lifetime_revisions", "lifetime_resumes", "input_rounds", "repairs")
CALL_STATES = {"WORKING", "REVIEW", "VERIFY", "REVISING", "DELIVERING"}
REPAIR_REASONS = ("invalid_output", "severity_directive")
INPUT_CLASSES = ("synthetic", "public", "internal")   # ordered: an input may not exceed its job's class
CLASS_RANK = {c: i for i, c in enumerate(INPUT_CLASSES)}
# Script argv placeholders: {job}, {job_dir}, {job_path} (repo-relative job folder: use it, not
# "jobs/{job}", so internal jobs work), {root}; an argv entry of exactly "{python}"
# becomes the interpreter running the engine (so script stages need no venv on PATH).


class LabError(Exception):
    code = 1


class CapExceeded(LabError):
    code = 3


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def now_ms():
    """Call start and end times: milliseconds, so short calls still have a measurable duration."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


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


def reviewers():
    f = CONFIG / "reviewers.json"
    return load_json(f).get("reviewers", {}) if f.exists() else {}


def approver():
    """Approver name from config/gates.json. There is no fallback: without a configured name every
    gate action is refused (the OS user name must never reach a token or the tracked audit log)."""
    f = CONFIG / "gates.json"
    name = load_json(f).get("approver") if f.exists() else None
    if not (isinstance(name, str) and name.strip()):
        raise LabError("no approver name in config/gates.json: set \"approver\" before any gate action")
    return name.strip()


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

def job_home(cls):
    """Folder that holds jobs of this class: internal jobs live entirely under private/jobs/."""
    if cls not in CLASS_RANK:
        raise LabError(f"job class must be one of {list(INPUT_CLASSES)}")
    return PRIVATE_JOBS if cls == "internal" else JOBS


def find_job(job_id):
    """The job's folder, found by its state.json (a stray folder of the same name never redirects
    the job); a job whose state exists in both homes is refused."""
    found = [home / job_id for home in (JOBS, PRIVATE_JOBS) if (home / job_id / "state.json").is_file()]
    if len(found) > 1:
        raise LabError(f"{job_id} has state in both jobs/ and private/jobs/; resolve by hand")
    return found[0] if found else None


def job_id_taken(job_id):
    return any((home / job_id).exists() for home in (JOBS, PRIVATE_JOBS))


def job_dir(job_id):
    if not JOB_ID_RE.match(job_id or ""):
        raise LabError(f"invalid job id: {job_id!r}")
    d = find_job(job_id)
    if d is None:
        raise LabError(f"job not found: {job_id}")
    return d


def is_internal(job_id):
    d = find_job(job_id)
    return d is not None and d.parent == PRIVATE_JOBS


def all_jobs():
    """State of every job, public and internal."""
    return [load_json(d / "state.json") for home in (JOBS, PRIVATE_JOBS) if home.exists()
            for d in sorted(home.iterdir()) if (d / "state.json").exists()]


def load_state(job_id):
    return load_json(job_dir(job_id) / "state.json")


def log(job_id, entry):
    entry = {"ts": now(), "job_id": job_id, **entry}
    with open(job_dir(job_id) / "run.log.jsonl", "a", encoding="utf-8") as fh:
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
    elif p.is_dir():  # deterministic: sorted relative posix paths and file contents only (no times, no modes)
        files = sorted((x.relative_to(p).as_posix(), x) for x in p.rglob("*")
                       if x.is_file() and x.name != ".DS_Store" and "__pycache__" not in x.parts)
        for name, f in files:
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            h.update(f.read_bytes())
            h.update(b"\0")
    else:
        raise LabError(f"artifact not found: {path}")
    return h.hexdigest()


# ---------- gates ----------

def gate_file(job_id, gate):
    return job_dir(job_id) / "gates" / f"{gate}.json"


GATE_MODES = {"human"}   # T0.15: the only accepted mode until Phase 5 (automatic gates need eval evidence first)


def gate_mode(gate):
    """The gate's mode from config/gates.json (its own entry, else default_mode). Anything but an
    accepted mode, including a missing one, is refused: there is no silent default."""
    cfg = load_json(CONFIG / "gates.json") if (CONFIG / "gates.json").exists() else {}
    entry = (cfg.get("gates") or {}).get(gate) or {}
    mode = entry.get("mode", cfg.get("default_mode"))
    if mode not in GATE_MODES:
        raise LabError(f"gate {gate}: mode {mode!r} is not accepted until Phase 5 (only 'human'); "
                       "set it in config/gates.json")
    return mode


def gate_config_errors():
    cfg = load_json(CONFIG / "gates.json") if (CONFIG / "gates.json").exists() else {}
    errs = []
    if cfg.get("default_mode") not in GATE_MODES:
        errs.append(f"config/gates.json: default_mode {cfg.get('default_mode')!r} is not accepted (only 'human')")
    gates = cfg.get("gates") or {}
    if not isinstance(gates, dict):
        return errs + ["config/gates.json: gates must be an object of gate name to settings"]
    for g, entry in gates.items():
        mode = (entry or {}).get("mode") if isinstance(entry, dict) else None
        if mode not in GATE_MODES:
            errs.append(f"config/gates.json: gate {g}: mode {mode!r} is not accepted until Phase 5 (only 'human')")
    return errs


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


def _token(job_id, gate):
    f = gate_file(job_id, gate)
    return load_json(f) if f.exists() else None


def _approved(job_id):
    """(gate, token) of a job's approval, or (gate, None)."""
    st = load_state(job_id)
    gate = st["route"].get("gate")
    return gate, (_token(job_id, gate) if gate else None)


def cited_jobs(artifact):
    """Job ids an artifact cites as approved artifacts ([G:<job>])."""
    import check_refs
    return sorted({m for _, text in check_refs.artifact_texts(ROOT, artifact) for m in G_CITE_RE.findall(text)})


def built_from(st):
    """What this job's artifact is built from: upstream approvals (by approved artifact content) and
    the inputs present now. Raises LabError if an upstream approval is missing or broken."""
    links = []
    if st.get("parent_link"):
        links.append({**st["parent_link"], "kind": "parent"})
    if st.get("continued_link"):
        links.append({**st["continued_link"], "kind": "continued"})
    for cited in cited_jobs(st["artifact_path"]) if st.get("artifact_path") else []:
        gate, tok = _approved(cited)
        if tok is None:
            raise LabError(f"cites [G:{cited}], which has no approval")
        links.append({"job": cited, "gate": gate, "artifact_sha256": tok["sha256"], "kind": "cited"})
    for link in links:
        ok, chain = verify_chain(link["job"], link["gate"])
        if not ok:
            raise LabError(f"upstream approval {link['job']}/{link['gate']} is not valid: " +
                           "; ".join(f"{c['job']}: {c['status']}" for c in chain if c["status"] != "ok"))
        if _token(link["job"], link["gate"])["sha256"] != link["artifact_sha256"]:
            raise LabError(f"upstream {link['job']} was approved with different content since this job was built on it; "
                           f"the approver runs engine/gate.py relink {st['job_id']}")
    inputs = [{"id": i["id"], "path": i["path"], "sha256": i["sha256"]} for i in st.get("inputs", [])]
    return {"links": links, "inputs": inputs}


def verify_chain(job_id, gate=None, _depth=0, _seen=()):
    """(ok, links) for a job's approval and everything it was built from, recursively.
    Each link: {level, job, gate, kind, path, recorded, current, status}. A link is broken when the
    approved artifact changed, a recorded input changed or disappeared, an upstream approval is missing
    or has different content, the chain is deeper than CHAIN_MAX_DEPTH, or it loops."""
    out = []

    def walk(job, gate, depth, seen, kind):
        entry = {"level": depth, "job": job, "gate": gate, "kind": kind, "path": None, "recorded": None,
                 "current": None, "status": "ok"}
        out.append(entry)
        if depth > CHAIN_MAX_DEPTH:
            entry["status"] = f"chain deeper than {CHAIN_MAX_DEPTH}: treated as broken"
            return
        if job in seen:
            entry["status"] = "cycle: treated as broken"
            return
        try:
            gate = gate or load_state(job)["route"].get("gate")
            entry["gate"] = gate
            tok = _token(job, gate) if gate else None
        except LabError as e:
            entry["status"] = str(e)
            return
        if tok is None:
            entry["status"] = f"no {gate} token"
            return
        entry.update(path=tok["artifact_path"], recorded=tok["sha256"])
        try:
            entry["current"] = sha256_path(tok["artifact_path"])
        except LabError as e:
            entry["status"] = str(e)
            return
        if entry["current"] != tok["sha256"]:
            entry["status"] = "token void: artifact changed after approval"
        bf = tok.get("built_from") or {"links": [], "inputs": []}
        for i in bf["inputs"]:
            ie = {"level": depth, "job": job, "gate": gate, "kind": f"input {i['id']}", "path": i["path"],
                  "recorded": i["sha256"], "current": None, "status": "ok"}
            out.append(ie)
            f = ROOT / i["path"]
            if not f.is_file():
                ie["status"] = "token void: recorded input missing"
                continue
            ie["current"] = hashlib.sha256(f.read_bytes()).hexdigest()
            if ie["current"] != i["sha256"]:
                ie["status"] = "token void: recorded input changed"
        for link in bf["links"]:
            le = {"level": depth + 1, "job": link["job"], "gate": link["gate"], "kind": f"{link['kind']} content",
                  "path": None, "recorded": link["artifact_sha256"], "current": None, "status": "ok"}
            out.append(le)
            try:
                up = _token(link["job"], link["gate"])
            except LabError as e:
                le["status"] = str(e)
                continue
            le["current"] = up["sha256"] if up else None
            if up is None:
                le["status"] = "upstream approval missing"
            elif up["sha256"] != link["artifact_sha256"]:
                le["status"] = "upstream approved with different content"
            walk(link["job"], link["gate"], depth + 1, seen | {job}, link["kind"])

    walk(job_id, gate, _depth, frozenset(_seen), "self")
    return all(e["status"] == "ok" for e in out), out


def approve_gate(job_id, note="", actor=None, review=None):
    """Write the gate token and approve. review (T0.16): the verdict file and saved brief, with their
    fingerprints and the marking counts, recorded in the token."""
    actor = actor or approver()
    st = load_state(job_id)
    if st["state"] != "GATE":
        raise LabError(f"{job_id} is {st['state']}, not GATE")
    gate = st["route"]["gate"]
    gate_mode(gate)
    token = {"gate": gate, "job_id": job_id, "artifact_path": st["artifact_path"],
             "sha256": sha256_path(st["artifact_path"]), "approved_by": actor,
             "approved_at": now(), "note": note, "built_from": built_from(st)}
    if review is not None:
        token["review"] = review
    save_json(gate_file(job_id, gate), token)
    return apply(job_id, "approve", note=note, actor=actor, _human=True)


def gate_audit(action, job_id=None, **detail):
    """Append one human gate action to logs/gate-audit.jsonl (hook-protected; written only by gate.py)."""
    rec = {"ts": now(), "action": action, "job_id": job_id, "approver": approver()}
    if job_id:
        try:
            st = load_state(job_id)
            rec.update(gate=st["route"]["gate"], state=st["state"], artifact_path=st["artifact_path"],
                       sha256=sha256_path(st["artifact_path"]) if st["artifact_path"] else None)
        except LabError as e:
            rec["state_error"] = str(e)
    rec.update(detail)
    # Internal jobs are audited under private/logs/: the tracked audit log must never hold their content.
    logs = ROOT / "private" / "logs" if job_id and is_internal(job_id) else ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with open(logs / "gate-audit.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def reject_gate(job_id, feedback, actor=None):
    actor = actor or approver()
    st = load_state(job_id)
    if st["state"] != "GATE":
        raise LabError(f"{job_id} is {st['state']}, not GATE")
    gate_mode(st["route"]["gate"])
    n = st["counters"]["gate_rejections"] + 1
    fb = job_dir(job_id) / "gates" / f"human-feedback-{n}.md"    # hook-protected: only gate.py writes here
    fb.parent.mkdir(parents=True, exist_ok=True)
    fb.write_text(f"# Human feedback {n} ({now()})\n\n{feedback}\n", encoding="utf-8")
    return apply(job_id, "reject", note=rel(fb), actor=actor, _human=True)


def hold_gate(job_id, note, actor=None):
    """Human-only (T0.16): park a job at its gate. ESCALATED, not a rejection; only gate.py resume restarts it."""
    actor = actor or approver()
    st = load_state(job_id)
    if st["state"] != "GATE":
        raise LabError(f"{job_id} is {st['state']}, not GATE: hold is a gate decision")
    if not (note or "").strip():
        raise LabError("hold needs --note (why the job is held)")
    gate_mode(st["route"]["gate"])
    return apply(job_id, "hold", note=note, actor=actor, _human=True)


# ---------- jobs ----------

def _fresh_state(job_id, jtype, goal, parent, r, cls):
    return {"job_id": job_id, "type": jtype, "class": cls, "goal": goal, "parent": parent,
            "route": r, "state": "NEW", "stage": None, "stage_kind": None, "stage_index": 0,
            "review_index": 0, "fanout": None, "fixing": False,
            "artifact_path": None, "resume_to": None, "last_failed_by": None,
            "visit": 0, "calls": [], "retry": None, "last_handoff": None, "handoffs": 0, "handoff_log": [],
            "ceiling": None,
            "inputs": [], "awaiting": None, "continued_from": None, "seed": [],
            "counters": {k: 0 for k in PER_CYCLE + LIFETIME + ("gate_rejections", "agent_calls")},
            "created": now(), "updated": now()}


def new_job(jtype, slug, goal, parent=None, continue_from=None, cls="synthetic"):
    all_routes = routes()
    r = all_routes.get(jtype)
    if r is None:
        raise LabError(f"unknown job type: {jtype}; valid: {sorted(all_routes)}")
    if not SLUG_RE.match(slug or ""):
        raise LabError("slug must be lowercase letters, digits, hyphens")
    if r.get("requires_parent_gate"):
        if not parent:
            raise LabError(f"{jtype} jobs need --parent with {r['requires_parent_gate']}")
        ok, chain = verify_chain(parent, r["requires_parent_gate"])
        if not ok:
            raise LabError("parent not approved: " + "; ".join(f"{c['job']} {c['kind']}: {c['status']}"
                                                              for c in chain if c["status"] != "ok"))
    job_home(cls)
    if parent:
        pcls = load_state(parent).get("class", "synthetic")
        if CLASS_RANK[cls] < CLASS_RANK[pcls]:
            raise LabError(f"a {cls} job cannot build on a {pcls} parent")
    old = None
    if continue_from:
        old = load_state(continue_from)
        if old["state"] not in TERMINAL | PAUSED:
            raise LabError(f"{continue_from} is {old['state']}; continue only from a finished or paused job")
        ocls = old.get("class", "synthetic")
        if CLASS_RANK[cls] < CLASS_RANK[ocls]:
            raise LabError(f"cannot continue a {ocls} job as a {cls} job (class can only stay or rise)")
    base = f"{datetime.date.today():%Y%m%d}-{jtype}-{slug}"
    job_id, i = base, 2
    while job_id_taken(job_id):
        job_id, i = f"{base}-{i}", i + 1
    d = job_home(cls) / job_id
    for sub in ("research", "drafts", "reviews", "gates", "delivery", "evidence"):
        (d / sub).mkdir(parents=True)
    cont = f"Continued from: {continue_from}\n" if continue_from else ""
    (d / "brief.md").write_text(f"# Brief: {job_id}\n\nType: {jtype}\nParent: {parent or '-'}\n{cont}\n## Goal\n{goal}\n", encoding="utf-8")
    st = _fresh_state(job_id, jtype, goal, parent, r, cls)
    if parent and r.get("requires_parent_gate"):
        st["parent_link"] = {"job": parent, "gate": r["requires_parent_gate"],
                             "artifact_sha256": _token(parent, r["requires_parent_gate"])["sha256"]}
    if old:
        st["continued_from"] = continue_from
        ogate, otok = _approved(continue_from)
        if otok is not None and verify_chain(continue_from, ogate)[0]:
            st["continued_link"] = {"job": continue_from, "gate": ogate, "artifact_sha256": otok["sha256"]}
        if old["artifact_path"]:
            src = ROOT / old["artifact_path"]
            dst = d / "drafts" / f"seed-{src.name}"
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            st["seed"].append(rel(dst))
        for inp in old["inputs"]:
            dest = d / "inputs" / Path(inp["path"]).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / inp["path"], dest)
            st["inputs"].append({**inp, "path": rel(dest), "copied_from": continue_from})
    save_json(d / "state.json", st)
    log(job_id, {"event": "created", "from": None, "to": "NEW", "actor": "orchestrator",
                 "continued_from": continue_from, "seed": st["seed"]})
    if old:
        log(continue_from, {"event": "continued_as", "job": job_id, "actor": "orchestrator"})
    return apply(job_id, "plan")


def _save(job_id, st, entry):
    st["updated"] = now()
    save_json(job_dir(job_id) / "state.json", st)
    log(job_id, {**entry, "counters": st["counters"]})


def _visit_calls(st):
    return [c for c in st["calls"] if c["visit"] == st["visit"]]


def _version(artifact):
    m = re.search(r"(v\d+)", Path(artifact).name)
    return m.group(1) if m else Path(artifact).name


def apply(job_id, event, artifact=None, note=None, actor="orchestrator", _human=False, _script=False,
          reason=None, questions=None):
    if event in HUMAN_ONLY and not _human:
        raise LabError(f"'{event}' is human-only; the approver runs engine/gate.py in their own terminal")
    if event in SCRIPT_ONLY and not _script:
        raise LabError(f"'{event}' is recorded only by 'state.py run'")
    st = load_state(job_id)
    cur, r, c = st["state"], st["route"], caps()
    if cur in TERMINAL:
        raise LabError(f"{job_id} is terminal ({cur})")
    work, reviews = r["stages"], r["reviews"]
    new, capmsg, extra = None, None, {}

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

    def revision(kind_counter=None, kind_cap=None):
        """One more revision: per-kind cap (reviews only), cycle total, job lifetime."""
        return ((cap(kind_counter, kind_cap, "REVISING") if kind_counter else None)
                or cap("total_revisions", "total_revisions_before_gate", "REVISING")
                or cap("lifetime_revisions", "lifetime_revisions", "REVISING")
                or "REVISING")

    def new_artifact():
        """Set the new version, run the reference check, then hand it to the first reviewer."""
        st["artifact_path"] = rel(artifact)
        sha256_path(st["artifact_path"])
        version = _version(st["artifact_path"])
        problems = check_refs.check(ROOT, job_id, st["artifact_path"], {i["id"] for i in st["inputs"]})
        checker, build = "check-refs", check_refs.findings_doc
        if not problems and (CONFIG / "evidence.json").exists():
            import evidence  # the evidence check runs second, before any agent reviewer
            if evidence.enabled():
                problems = evidence.record_check(job_id, st["artifact_path"], version)
                checker, build = "check-evidence", evidence.findings_doc
        if not problems:
            return enter_review(0)
        doc = build(job_id, st["artifact_path"], version, problems)
        n = len(list((job_dir(job_id) / "reviews").glob(f"{checker}-*.json"))) + 1
        out = job_dir(job_id) / "reviews" / f"{checker}-{n}.json"
        save_json(out, doc)
        extra[checker.replace("-", "_")] = rel(out)
        st["last_failed_by"] = checker
        st["stage_kind"], st["stage"] = "revise", r["revise_with"]
        return revision()

    def script_stage():
        return cur == "WORKING" and st["stage_kind"] == "script" and not st["fixing"]

    if event in ("block", "escalate", "cancel"):
        if event == "cancel":
            new = "CANCELLED"
        else:
            if cur not in PAUSED:
                st["resume_to"] = cur
            new = "BLOCKED" if event == "block" else "ESCALATED"
    elif event == "hold":
        st["resume_to"] = cur
        st["hold"] = {"note": note, "at": now(), "by": actor}
        new = "ESCALATED"
    elif event == "resume" and st.get("hold"):
        # A held job: only the approver restarts it (gate.py resume); not a cap event, so no counter changes.
        if not _human:
            raise LabError(f"{job_id} is held by the approver ({st['hold']['note']}); only engine/gate.py resume "
                           "restarts it")
        new, st["resume_to"] = st["resume_to"], None
        extra["held"] = st.pop("hold")
    elif event == "resume":
        if cur not in PAUSED:
            raise LabError(f"resume only from BLOCKED/ESCALATED, not {cur}")
        if st["counters"]["lifetime_resumes"] >= c["lifetime_resumes"]:
            raise CapExceeded(f"{job_id}: cap exceeded: lifetime_resumes={c['lifetime_resumes']}; "
                              f"resume refused (cancel, or start a new job with --continue-from)")
        over = ceiling_exceeded(st)
        if over:
            raise CapExceeded(f"{job_id}: {over}; resume refused until the approver raises it "
                              f"(engine/gate.py ceiling {job_id} ...)")
        st["counters"]["lifetime_resumes"] += 1
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
        new = new_artifact()
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
    elif cur in CALL_STATES and event == "infra_error":
        new = cap("infra_errors", "infra_retries", cur, paused="BLOCKED") or cur
        last = _visit_calls(st)
        if last:
            _close_open(job_id, st, last[-1], "failed", "infra_error")
        if new == cur:
            st["retry"] = {"of": last[-1]["id"], "reason": "infra_error"} if last else None
    elif cur in CALL_STATES and event == "repair":
        if reason not in REPAIR_REASONS:
            raise LabError(f"repair needs --reason, one of {list(REPAIR_REASONS)}")
        last = _visit_calls(st)
        if not last:
            raise LabError("repair: no agent call to repair in this step")
        if last[-1]["reason"] in REPAIR_REASONS:
            raise LabError(f"{last[-1]['id']} is already a repair; still invalid -> record infra_error")
        new = cap("repairs", "repairs", cur) or cur
        _close_open(job_id, st, last[-1], "done", "repair")
        if new == cur:
            st["retry"] = {"of": last[-1]["id"], "reason": reason}
        extra["reason"] = reason
    elif cur in CALL_STATES and event == "needs_input":
        if not questions:
            raise LabError("needs_input needs --questions <file> (the agent's questions, verbatim)")
        text = Path(questions).read_text(encoding="utf-8")
        new = cap("input_rounds", "input_rounds", cur) or "AWAITING_INPUT"
        if new == "AWAITING_INPUT":
            qd = job_dir(job_id) / "questions"
            qd.mkdir(exist_ok=True)
            qf = qd / f"q-{st['counters']['input_rounds']}.md"
            qf.write_text(text, encoding="utf-8")
            st["awaiting"] = {"state": cur, "stage": st["stage"], "stage_kind": st["stage_kind"],
                              "questions": rel(qf), "inputs_before": len(st["inputs"]), "asked": now()}
            extra["questions"] = rel(qf)
    elif (cur, event) == ("AWAITING_INPUT", "answered"):
        aw = st["awaiting"]
        if len(st["inputs"]) <= aw["inputs_before"]:
            raise LabError("answered: record the answers first with 'state.py input <job> <file> --class ...'")
        new, st["stage"], st["stage_kind"] = aw["state"], aw["stage"], aw["stage_kind"]
        extra["answers"] = [i["id"] for i in st["inputs"][aw["inputs_before"]:]]
        st["awaiting"] = None
    elif cur in ("REVIEW", "VERIFY") and event == "review_pass":
        if st["review_index"] < len(reviews) - 1:
            new = enter_review(st["review_index"] + 1)
        else:
            if r["gate"]:
                gate_mode(r["gate"])                      # T0.15: refuse a gate whose mode isn't accepted
            new = "GATE" if r["gate"] else "DONE"
            st["stage_kind"], st["stage"] = None, None
    elif cur in ("REVIEW", "VERIFY") and event == "review_fail":
        rv = reviews[st["review_index"]]
        st["last_failed_by"] = rv["agent"]
        kind = rv["kind"]
        new = revision(f"{kind}_revisions", f"{kind}_revisions")
        st["stage_kind"], st["stage"] = "revise", r["revise_with"]
    elif (cur, event) == ("REVISING", "revised"):
        if not artifact:
            raise LabError("revised needs --artifact (the new version)")
        new = new_artifact()
    elif event == "relink":
        new = enter_review(0) if st["artifact_path"] else cur
        extra["relinked_to"] = st.get("parent_link")
    elif (cur, event) == ("GATE", "approve"):
        new = "APPROVED"
    elif (cur, event) == ("GATE", "reject"):
        for k in ("critic_revisions", "verifier_revisions", "total_revisions"):
            st["counters"][k] = 0
        new = (cap("gate_rejections", "gate_rejections", "REVISING")
               or cap("lifetime_revisions", "lifetime_revisions", "REVISING") or "REVISING")
        st["stage_kind"], st["stage"] = "revise", r["revise_with"]
    elif (cur, event) == ("APPROVED", "deliver"):
        if not r.get("deliver"):
            raise LabError("route has no delivery stage; use complete")
        ok, chain = verify_chain(job_id, r["gate"])   # an edit anywhere in the chain blocks delivery
        if not ok:
            raise LabError("delivery refused: " + _broken(chain))
        new = "DELIVERING"
        st["stage_kind"], st["stage"] = "deliver", r["deliver"]
    elif cur in ("APPROVED", "DELIVERING") and event == "complete":
        if r.get("gate"):
            ok, chain = verify_chain(job_id, r["gate"])   # DONE only on what was approved, chain intact
            if not ok:
                raise LabError("complete refused: " + _broken(chain))
        new = "DONE"
        st["stage_kind"], st["stage"] = None, None
    else:
        raise LabError(f"invalid transition: {cur} --{event}-->")

    if event not in ("infra_error", "repair"):
        st["visit"] += 1  # a new step: every agent may be called once again
        st["retry"] = None
    st["state"] = new
    _save(job_id, st, {"event": event, "from": cur, "to": new, "stage": st["stage"], "actor": actor,
                       "artifact": st["artifact_path"], "note": note or capmsg, **extra})
    if capmsg:
        raise CapExceeded(f"{job_id}: {capmsg} -> {new}")
    return st


def _broken(chain):
    return "; ".join(f"{c['job']} {c['kind']}: {c['status']}" for c in chain if c["status"] != "ok")


def relink(job_id, actor=None):
    """Human-only (engine/gate.py relink): point a child at its parent's current approval, void the
    child's own approval if any, and send it back to its first review."""
    st = load_state(job_id)
    link = st.get("parent_link")
    if not link:
        raise LabError(f"{job_id} has no parent approval to relink")
    ok, chain = verify_chain(link["job"], link["gate"])
    if not ok:
        raise LabError("the parent's approval is not valid: " + _broken(chain))
    new_sha = _token(link["job"], link["gate"])["sha256"]
    st["parent_link"] = {**link, "artifact_sha256": new_sha}
    gate = st["route"].get("gate")
    old = gate_file(job_id, gate) if gate else None
    if old and old.exists():
        n = len(list(old.parent.glob(f"{gate}.void-*.json"))) + 1
        old.replace(old.parent / f"{gate}.void-{n}.json")
    save_json(job_dir(job_id) / "state.json", st)
    return apply(job_id, "relink", note=f"parent {link['job']} now at {new_sha[:12]}", actor=actor or approver(), _human=True)


# ---------- human inputs ----------

def input_dir(job_id, cls):
    """Inputs live in the job's own folder; an input may not exceed the job's class."""
    if cls not in INPUT_CLASSES:
        raise LabError(f"input class must be one of {list(INPUT_CLASSES)}")
    job_cls = load_state(job_id).get("class", "synthetic")
    if CLASS_RANK[cls] > CLASS_RANK[job_cls]:
        hint = " (start an internal job with --continue-from)" if cls == "internal" else ""
        raise LabError(f"a {cls} input cannot go into a {job_cls} job{hint}")
    return job_dir(job_id) / "inputs"


def record_input(job_id, source, cls, note=None, data=None):
    """Store the approver's text verbatim (bytes copied unchanged) and register it with an ID."""
    st = load_state(job_id)
    if st["state"] in TERMINAL:
        raise LabError(f"{job_id} is terminal ({st['state']})")
    d = input_dir(job_id, cls)
    if cls == "internal" and data is None:
        src = Path(source).resolve()
        inside = src.is_relative_to(ROOT.resolve())
        if inside and not src.is_relative_to((ROOT / "private").resolve()):
            raise LabError("internal input source is inside the repo outside private/, where Git could track it; "
                           "pipe it on stdin ('-') or keep the source under private/")
    raw = data if data is not None else Path(source).read_bytes()
    n = len(st["inputs"]) + 1
    iid = f"A{n:02d}"
    name = Path(source).name if source and source != "-" else "answer.md"
    dest = d / f"{iid}-{name}"
    d.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    rec = {"id": iid, "class": cls, "path": rel(dest), "sha256": hashlib.sha256(raw).hexdigest(),
           "note": note, "recorded": now()}
    st["inputs"].append(rec)
    _save(job_id, st, {"event": "input", "input": iid, "class": cls, "path": rec["path"], "actor": "orchestrator"})
    return st, rec


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
    """Count one agent call. Each step (visit) allows one call per agent (and fan-out item); a second
    call needs a retry permit from infra_error or repair, and is linked to the call it repeats."""
    st = load_state(job_id)
    if st["state"] not in CALL_STATES:
        raise LabError(f"{job_id} is {st['state']}; no agent calls allowed")
    if agent != st["stage"]:
        raise LabError(f"{job_id} is at {st['stage']!r} ({st['stage_kind']}); not calling {agent!r}")
    fo = st.get("fanout")
    at_fanout = st["state"] == "WORKING" and st["stage_kind"] == "fanout"
    if at_fanout:
        if not fo:
            raise LabError("fanout stage: set the item list before calling agents")
        if item not in fo["items"]:
            raise LabError(f"fanout call needs --item, one of {sorted(fo['items'])}")
    elif item is not None:
        raise LabError("--item is only valid at a fanout stage")
    open_calls = [x for x in st["calls"] if x.get("status") == "open"]
    if open_calls:
        limit = min(st["route"]["stages"][st["stage_index"]]["fanout"]["max"], caps()["fanout_max"]) if at_fanout else 0
        parallel_ok = at_fanout and len(open_calls) < limit and all(
            x["visit"] == st["visit"] and x["agent"] == agent and x["item"] is not None for x in open_calls)
        if not parallel_ok:
            raise LabError(f"call {open_calls[0]['id']} ({open_calls[0]['agent']}) is still open: record its result "
                           f"first (the post hook does this when the subagent returns; otherwise state.py result)")
    over = ceiling_exceeded(st)
    if over:
        apply(job_id, "escalate", note=over)
        raise CapExceeded(f"{job_id}: {over} -> ESCALATED")
    prior = [x for x in _visit_calls(st) if x["agent"] == agent and x["item"] == item]
    attempt, retry_of, why = 1, None, None
    if prior:
        permit = st["retry"]
        if not permit or permit["of"] != prior[-1]["id"]:
            raise LabError(f"second call to {agent}{' item ' + item if item else ''} in this step "
                           f"({prior[-1]['id']} already made) without an infra_error or repair")
        attempt, retry_of, why = prior[-1]["attempt"] + 1, prior[-1]["id"], permit["reason"]
        st["retry"] = None
    elif at_fanout and fo["items"][item]["status"] != "pending":
        raise LabError(f"fanout item {item} was already dispatched ({fo['items'][item]['status']})")
    if at_fanout:
        fo["items"][item].update(status="running", calls=fo["items"][item]["calls"] + 1)
    # the newest unused handoff built for this agent and item; a retry without a fresh handoff
    # repeats its original's
    h = next((x for x in reversed(st["handoff_log"]) if x["agent"] == agent and x["item"] == item
              and x["used_by"] is None), None)
    hid = h["id"] if h else (next(x["handoff"] for x in st["calls"] if x["id"] == retry_of) if retry_of else None)
    call = {"id": f"C{len(st['calls']) + 1:03d}", "agent": agent, "item": item, "visit": st["visit"],
            "state": st["state"], "attempt": attempt, "retry_of": retry_of, "reason": why,
            "handoff": hid, "ts": now_ms(), "status": "open", "ended": None, "usage": None, "usage_source": None}
    for x in st["handoff_log"]:
        if x["id"] == hid and x["used_by"] is None:
            x["used_by"] = call["id"]
    c = caps()
    for counter, cap_name in (("agent_calls", "agent_calls_per_job"), ("lifetime_agent_calls", "lifetime_agent_calls")):
        if st["counters"][counter] + 1 > c[cap_name]:  # refuse before recording: no phantom open call
            apply(job_id, "escalate", note=f"cap exceeded: {cap_name}")
            raise CapExceeded(f"{job_id}: cap exceeded: {cap_name} -> ESCALATED")
    st["calls"].append(call)
    st["counters"]["agent_calls"] += 1
    st["counters"]["lifetime_agent_calls"] += 1
    _save(job_id, st, {"event": "agent_call", **{k: v for k, v in call.items() if k != "ts"},
                       "call": call["id"], "actor": "orchestrator"})
    return st


# ---------- handoffs ----------

def _files(d):
    d = Path(d)
    return [rel(f) for f in sorted(d.rglob("*")) if f.is_file()] if d.exists() else []


def build_handoff(job_id, item=None):
    """The handoff for the agent the job is waiting on, built from state, route and recorded inputs."""
    st = load_state(job_id)
    if st["state"] not in CALL_STATES:
        raise LabError(f"{job_id} is {st['state']}; no handoff to build")
    r, kind, d = st["route"], st["stage_kind"], job_dir(job_id)
    if kind == "script":
        raise LabError("script stage: no agent handoff; run it with 'state.py run'")
    j = rel(d)
    inputs, rules = [], []
    human = [(f"input {i['id']} ({i['class']})", i["path"]) for i in st["inputs"]]
    # gate feedback only from gates/ (written by gate.py, hook-protected); one found anywhere else is never passed on
    feedback = [("gate feedback", p) for p in _files(d / "gates") if Path(p).name.startswith("human-feedback-")]
    brief = [("brief", f"{j}/brief.md")]
    evidence = [("evidence pack", f"{j}/evidence/")]
    out = {"agent": f"{j}/research/", "fanout": f"{j}/research/", "review": f"{j}/reviews/",
           "revise": f"{j}/drafts/", "fix": f"{j}/drafts/", "deliver": f"{j}/delivery/"}[kind]
    extra = {}
    if kind == "agent":
        last = st["stage_index"] == len(r["stages"]) - 1
        out = f"{j}/drafts/" if last else out
        inputs = brief + [("seed (from " + st["continued_from"] + ")", s) for s in st["seed"]] \
            + [("earlier stage output", p) for p in _files(d / "research")] + human
    elif kind == "fanout":
        if not st["fanout"] or item not in st["fanout"]["items"]:
            raise LabError(f"fanout handoff needs --item, one of {sorted((st['fanout'] or {}).get('items', {}))}")
        extra = {"ITEM": item, "SPLIT_BY": st["fanout"]["split_by"]}
        inputs = brief + human
    elif kind == "review":
        rv = r["reviews"][st["review_index"]]
        cfg = reviewers().get(rv["agent"], {})
        rules = [cfg["rulebook"]] if cfg.get("rulebook") else []
        inputs = [("artifact", st["artifact_path"])]
        if rv["kind"] == "verifier":
            inputs += evidence + [("source registry", f"{j}/evidence/registry.json")]
            if cfg.get("source_policy"):
                rules.append(cfg["source_policy"])
        inputs += human + feedback
        extra = {"REVIEW_KIND": rv["kind"]}
    elif kind == "revise":
        findings = []
        for p in _files(d / "reviews"):
            if p.endswith(".json"):
                try:
                    if load_json(ROOT / p).get("artifact_path") == st["artifact_path"]:
                        findings.append(("findings to address", p))
                except ValueError:
                    pass
        inputs = [("artifact", st["artifact_path"])] + brief + evidence + findings + feedback + human
    elif kind == "fix":
        runs = _files(d / "scripts")
        inputs = brief + ([("failed script run", runs[-1])] if runs else []) + human
    elif kind == "deliver":
        inputs = [("approved artifact", st["artifact_path"]), ("gate token", f"{j}/gates/{r['gate']}.json")] + human
    template = r.get("template")
    return {"job": job_id, "type": st["type"], "stage": st["stage"], "kind": kind,
            "goal": st["goal"], "template": template, "template_variants": r.get("template_variants", {}),
            **{k.lower(): v for k, v in extra.items()},
            "inputs": [{"label": a, "path": b} for a, b in inputs], "rules": rules, "output_dir": out}


def render_handoff(h, hid):
    lines = [f"JOB: {h['job']}    TYPE: {h['type']}    STAGE: {h['stage']} ({h['kind']})    HANDOFF: {hid}",
             f"GOAL: {h['goal']}"]
    if h["template"]:
        variants = ", ".join(f"{k}: {v}" for k, v in h["template_variants"].items())
        lines.append(f"TEMPLATE: {h['template']}" + (f"    VARIANTS: {variants}" if variants else ""))
    if h.get("item"):
        lines.append(f"ITEM: {h['item']}    SPLIT_BY: {h['split_by']}")
    if h.get("review_kind"):
        lines.append(f"REVIEW: {h['review_kind']}")
    lines.append("INPUTS:")
    lines += [f"  - {i['label']}: {i['path']}" for i in h["inputs"]] or ["  - none"]
    lines.append("RULES:")
    lines += [f"  - {p}" for p in h["rules"]] or ["  - none"]
    if h["kind"] in ("agent", "fanout", "revise") and (CONFIG / "evidence.json").exists():
        lines.append(f"FETCH: python engine/evidence.py fetch {h['job']} <url> --handoff {hid}"
                     "    (WebFetch is for discovery only; cite only sources stored this way)")
    lines += [f"OUTPUT_DIR: {h['output_dir']}",
              "End your reply with the STATUS block: STATUS, OUTPUTS, OPEN_ITEMS, VERDICT (reviewers), SUMMARY."]
    return "\n".join(lines) + "\n"


def handoff(job_id, item=None):
    """Build, record and return (handoff dict, rendered text). The next agent call links to it."""
    h = build_handoff(job_id, item)
    st = load_state(job_id)
    st["handoffs"] += 1
    hid = f"H{st['handoffs']:03d}"
    text = render_handoff(h, hid)
    st["last_handoff"] = hid
    st["handoff_log"].append({"id": hid, "agent": h["stage"], "item": item, "used_by": None})
    _save(job_id, st, {"event": "handoff", "handoff": hid, "agent": h["stage"], "item": item,
                       "sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "inputs": [i["path"] for i in h["inputs"]], "actor": "script"})
    return h, text


# ---------- usage ----------

USAGE_KEYS = ("input", "output", "cache_read", "cache_write")


def usage_from_tokens(usage, total=None, duration_ms=None, model=None, cost_usd=None):
    """Normalise an API-style usage object into the engine's usage record."""
    u = usage or {}
    rec = {"input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
           "cache_read": int(u.get("cache_read_input_tokens") or 0),
           "cache_write": int(u.get("cache_creation_input_tokens") or 0)}
    rec["total"] = int(total) if total is not None else sum(rec[k] for k in USAGE_KEYS)
    rec["duration_s"] = round(duration_ms / 1000, 3) if duration_ms is not None else None
    rec["model"] = model
    rec["cost_usd_estimate"] = cost_usd
    return rec


def _usage_log(job_id, entry):
    d = ROOT / "private" / "logs" if is_internal(job_id) else ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "usage.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now(), "job_id": job_id, **entry}) + "\n")


def _close_open(job_id, st, call, status, source):
    """Close a still-open call with unknown usage (tool failure, repair, manual close)."""
    if call.get("status") != "open":
        return
    ended = now_ms()
    start = datetime.datetime.fromisoformat(call["ts"])
    call.update(status=status, ended=ended, usage_source=source,
                usage={"total": None, "duration_s": round((datetime.datetime.fromisoformat(ended) - start).total_seconds(), 3)})
    _usage_log(job_id, {"call": call["id"], "agent": call["agent"], "item": call["item"], "attempt": call["attempt"],
                        "status": status, "source": source, "tokens": None,
                        "duration_s": call["usage"]["duration_s"], "model": None})


def usage_totals(st):
    calls = [c for c in st["calls"] if c.get("status") in ("done", "failed")]
    known = [c for c in calls if c.get("usage") and c["usage"].get("total") is not None]
    tokens = {k: sum(c["usage"].get(k, 0) for c in known) for k in USAGE_KEYS + ("total",)}
    minutes = sum((c["usage"] or {}).get("duration_s") or 0 for c in calls) / 60
    return {"calls": len(st["calls"]), "closed": len(calls), "with_tokens": len(known), "tokens": tokens,
            "agent_minutes": minutes}  # unrounded: the ceiling compares this; round only for display


def effective_ceiling(st):
    base = dict(caps().get("usage_ceiling", {}))
    base.update({k: v for k, v in (st.get("ceiling") or {}).items() if v is not None})
    return base


def ceiling_exceeded(st):
    """Reason string if the job is at or over its usage ceiling, else None. Tokens count when any
    call reported them; agent minutes always count (the fallback when no tokens are known)."""
    c, u = effective_ceiling(st), usage_totals(st)
    if u["with_tokens"] and c.get("tokens") and u["tokens"]["total"] >= c["tokens"]:
        return f"usage ceiling reached: {u['tokens']['total']} tokens >= {c['tokens']}"
    if c.get("agent_minutes") and u["agent_minutes"] >= c["agent_minutes"]:
        return f"usage ceiling reached: {round(u['agent_minutes'], 4)} agent minutes >= {c['agent_minutes']}"
    return None


def record_result(job_id, call_id, status, usage=None, source="manual", note=None):
    """Close an open call with its outcome and usage; log the numbers; pause the job if it has now
    reached its usage ceiling. Returns (state, ceiling message or None)."""
    if status not in ("done", "failed"):
        raise LabError("result status must be done or failed")
    st = load_state(job_id)
    call = next((x for x in st["calls"] if x["id"] == call_id), None)
    if call is None:
        raise LabError(f"no call {call_id} in {job_id}")
    if call.get("status") != "open":
        raise LabError(f"call {call_id} is already closed ({call.get('status')})")
    ended = now_ms()
    if usage is None:
        start = datetime.datetime.fromisoformat(call["ts"])
        usage = {"total": None, "duration_s": round((datetime.datetime.fromisoformat(ended) - start).total_seconds(), 3)}
    elif usage.get("duration_s") is None:
        start = datetime.datetime.fromisoformat(call["ts"])
        usage["duration_s"] = round((datetime.datetime.fromisoformat(ended) - start).total_seconds(), 3)
    warn = caps().get("usage_ceiling", {}).get("per_call_warning_tokens")
    call.update(status=status, ended=ended, usage=usage, usage_source=source,
                warning=bool(warn and usage.get("total") and usage["total"] >= warn))
    _save(job_id, st, {"event": "call_result", "call": call_id, "status": status, "source": source,
                       "tokens": usage.get("total"), "note": note, "actor": source})
    _usage_log(job_id, {"call": call_id, "agent": call["agent"], "item": call["item"], "attempt": call["attempt"],
                        "status": status, "source": source,
                        "tokens": {k: usage.get(k) for k in USAGE_KEYS + ("total",)} if usage.get("total") is not None else None,
                        "duration_s": usage.get("duration_s"), "model": usage.get("model"),
                        "cost_usd_estimate": usage.get("cost_usd_estimate"), "warning": call["warning"]})
    over = ceiling_exceeded(st)
    if over and st["state"] in CALL_STATES:
        apply(job_id, "escalate", note=over)
        return load_state(job_id), over
    return st, over


def find_call_by_handoff(job_id, hid):
    st = load_state(job_id)
    return next((x for x in reversed(st["calls"]) if x["handoff"] == hid and x.get("status") == "open"), None)


def set_ceiling(job_id, tokens=None, agent_minutes=None, _human=False):
    """Raise (or set) this job's usage ceiling. Human-only: called by engine/gate.py."""
    if not _human:
        raise LabError("changing a usage ceiling is human-only; the approver runs engine/gate.py ceiling")
    st = load_state(job_id)
    cur = st.get("ceiling") or {}
    if tokens is not None:
        cur["tokens"] = int(tokens)
    if agent_minutes is not None:
        cur["agent_minutes"] = float(agent_minutes)
    st["ceiling"] = cur
    _save(job_id, st, {"event": "ceiling", "ceiling": cur, "actor": approver()})
    return st


def usage_summary(job_id):
    """Lines of text: totals and per-agent figures for one job."""
    st = load_state(job_id)
    u, c = usage_totals(st), effective_ceiling(st)
    lines = [f"Usage for {job_id} ({st['state']})",
             f"  calls {u['calls']} (closed {u['closed']}, with token figures {u['with_tokens']}); "
             f"agent minutes {round(u['agent_minutes'], 2)}",
             "  tokens: " + ", ".join(f"{k} {u['tokens'][k]}" for k in USAGE_KEYS + ("total",)),
             f"  ceiling (provisional): tokens {c.get('tokens')}, agent minutes {c.get('agent_minutes')}; "
             f"per-call warning at {c.get('per_call_warning_tokens')} tokens"]
    agents = {}
    for x in st["calls"]:
        a = agents.setdefault(x["agent"], {"calls": 0, "retries": 0, "failed": 0, "tokens": 0, "minutes": 0.0,
                                           "unknown": 0, "warnings": 0})
        a["calls"] += 1
        a["retries"] += 1 if x["retry_of"] else 0
        a["failed"] += 1 if x.get("status") == "failed" else 0
        us = x.get("usage") or {}
        a["tokens"] += us.get("total") or 0
        a["minutes"] += (us.get("duration_s") or 0) / 60
        a["unknown"] += 1 if x.get("status") in ("done", "failed") and us.get("total") is None else 0
        a["warnings"] += 1 if x.get("warning") else 0
    for name, a in sorted(agents.items()):
        flag = f"  WARNING: {a['warnings']} call(s) over the per-call threshold" if a["warnings"] else ""
        lines.append(f"  {name}: calls {a['calls']}, retries {a['retries']}, failed {a['failed']}, tokens {a['tokens']}, "
                     f"minutes {round(a['minutes'], 2)}, usage unknown {a['unknown']}{flag}")
    lines.append("  Not included: the Orchestrator's own main-session tokens (until the headless runner, T5.2).")
    return lines


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
    subst = {"{job}": job_id, "{job_dir}": str(d), "{job_path}": rel(d), "{root}": str(ROOT)}
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
            art = spec["artifact"].replace("{job_path}", rel(d)).replace("{job}", job_id)
            return apply(job_id, "artifact_ready", artifact=art, note=note, actor="script", _script=True), rec
        return apply(job_id, "stage_done", note=note, actor="script", _script=True), rec
    return apply(job_id, "script_fail", note=note, actor="script", _script=True), rec


# ---------- private-job leak check ----------

def private_leaks(job_id, root=None):
    """For an internal job: every file Git would track (tracked, or untracked and not ignored)
    whose path or text names the job, plus the job folder itself if Git does not ignore it.
    Returns a list of messages; empty = nothing of this job can reach a commit."""
    root = Path(root or ROOT)
    if not is_internal(job_id):
        raise LabError(f"{job_id} is not an internal job")
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        raise LabError("not a Git repository: cannot check what Git would track")
    leaks = []
    if git("check-ignore", "-q", rel(job_dir(job_id) / "state.json")).returncode != 0:
        leaks.append(f"{rel(job_dir(job_id))} is not ignored by Git")
    listed = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").stdout.split("\0")
    for f in filter(None, listed):
        p = root / f
        if job_id in f:
            leaks.append(f"{f}: path names the internal job")
        elif p.is_file() and p.stat().st_size < 5_000_000 and job_id.encode() in p.read_bytes():
            leaks.append(f"{f}: content names the internal job")
    return leaks


def set_active(job_id):
    job_dir(job_id)
    LAB.mkdir(exist_ok=True)
    (LAB / "active_job").write_text(job_id, encoding="utf-8")


def active_job():
    f = LAB / "active_job"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None
