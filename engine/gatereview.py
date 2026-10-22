#!/usr/bin/env python3
"""Gate review support (stdlib only, T0.16): the gate brief, which findings the approver marks, the
verdict records and the reviewer quality figures. Used by engine/gate.py (approve, reject, hold) and
engine/state.py quality.

- Brief: plain language, built by script: what is approved (fingerprints), the approval chain, the
  evidence checks, open questions, usage, the changes since the last version (unified diff, at most
  DIFF_LINES lines per file; per file for folder artifacts) and the findings. At approve, reject and
  hold the brief shown is saved beside the verdict file in gates/ and its fingerprint recorded.
- Marking: findings from agent reviewers (not the scripted checks) in every review round since the
  last gate decision (findings marked at an earlier decision are not asked again). Every blocker and
  major is marked valid or noise; a third of the minors (rounded up), chosen with a seed taken from
  the job and the artifact version, so the same gate always picks the same minors, may also be skipped.
- Records: gates/<gate>.verdicts-<n>.json (every mark and the missed-issue descriptions; hook-protected;
  under private/ for internal jobs) and one line per mark in logs/finding-verdicts.jsonl (IDs, rule,
  severity and mark only, never text; private/logs/ for internal jobs).
- Quality: noise rate = noise / (valid + noise); miss rate = missed / (valid + missed); per reviewer
  and per rule; skipped marks are counted but excluded from both rates.
"""
import difflib
import hashlib
import json
import math
import random
import re
from pathlib import Path

import labcore as lc
import validate_findings as vf

DIFF_LINES = 80
SCRIPT_REVIEWERS = {"check-refs", "check-evidence"}
MARKS = {"v": "valid", "n": "noise", "s": "skipped"}


# ---------- findings to mark ----------

def _review_docs(job_id):
    out = []
    for f in sorted((lc.job_dir(job_id) / "reviews").glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                                            # unreadable review files are listed in the brief
        if isinstance(doc, dict) and isinstance(doc.get("findings"), list) and doc.get("reviewer"):
            out.append((lc.rel(f), doc))
    return out


def unreadable_reviews(job_id):
    bad = []
    for f in sorted((lc.job_dir(job_id) / "reviews").glob("*.json")):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(lc.rel(f))
    return bad


def verdict_files(job_id, gate=None):
    d = lc.job_dir(job_id) / "gates"
    return sorted(d.glob(f"{gate or '*'}.verdicts-*.json")) if d.is_dir() else []


def already_marked(job_id):
    seen = set()
    for f in verdict_files(job_id):
        for m in lc.load_json(f).get("marks", []):
            seen.add((m["file"], m["finding_id"]))
    return seen


def cycle_findings(job_id):
    """Agent-reviewer findings not marked at an earlier gate decision, oldest first."""
    seen, out = already_marked(job_id), []
    for path, doc in _review_docs(job_id):
        if doc["reviewer"] in SCRIPT_REVIEWERS:
            continue
        for f in doc["findings"]:
            if not isinstance(f, dict) or (path, f.get("id")) in seen:
                continue
            out.append({"file": path, "reviewer": doc["reviewer"], "version": doc.get("artifact_version"),
                        "finding_id": f.get("id"), "rule": str(f.get("rule", "")).strip().upper(),
                        "severity": f.get("severity"), "location": f.get("location"), "issue": f.get("issue")})
    return out


def seed_for(job_id, version):
    return int(hashlib.sha256(f"{job_id}:{version}".encode()).hexdigest(), 16)


def to_mark(job_id):
    """(findings that must be marked, sampled minors that may be skipped, total minors)."""
    st = lc.load_state(job_id)
    version = lc._version(st["artifact_path"]) if st["artifact_path"] else "none"
    found = cycle_findings(job_id)
    must = [f for f in found if f["severity"] in ("blocker", "major")]
    minors = sorted((f for f in found if f["severity"] == "minor"), key=lambda f: (f["file"], f["finding_id"]))
    k = math.ceil(len(minors) / 3)
    sampled = random.Random(seed_for(job_id, version)).sample(minors, k) if k else []
    sampled.sort(key=lambda f: (f["file"], f["finding_id"]))
    return must, sampled, len(minors)


def reviewers_for_rule(rule):
    names = []
    for name, cfg in lc.reviewers().items():
        rb = lc.ROOT / cfg.get("rulebook", "") if cfg.get("rulebook") else None
        if rb and rb.is_file() and rule in vf.rulebook_severities(rb):
            names.append(name)
    return sorted(n for n in names if n not in SCRIPT_REVIEWERS)


# ---------- the brief ----------

def _artifact_files(path):
    p = lc.ROOT / path
    if p.is_dir():
        return {lc.rel(f)[len(path.rstrip("/")) + 1:]: f for f in sorted(p.rglob("*")) if f.is_file()}
    return {p.name: p} if p.is_file() else {}


def artifact_history(job_id):
    seen = []
    f = lc.job_dir(job_id) / "run.log.jsonl"
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        a = json.loads(line).get("artifact")
        if a and (not seen or seen[-1] != a):
            seen.append(a)
    return seen


def diff_lines(job_id, current):
    hist = [a for a in artifact_history(job_id) if a != current]
    if not hist:
        return ["(first version: nothing to compare)"]
    prev = hist[-1]
    old, new = _artifact_files(prev), _artifact_files(current)
    if not (lc.ROOT / prev).is_dir() and not (lc.ROOT / current).is_dir():
        # single files: compare the two versions themselves, whatever they are called (v1.md against v2.md)
        old, new = {"artifact": next(iter(old.values()), None)}, {"artifact": next(iter(new.values()), None)}
        old, new = {k: v for k, v in old.items() if v}, {k: v for k, v in new.items() if v}
    out = [f"Compared with {prev}:"]
    for name in sorted(set(old) | set(new)):
        a = old[name].read_text(encoding="utf-8", errors="replace").splitlines() if name in old else []
        b = new[name].read_text(encoding="utf-8", errors="replace").splitlines() if name in new else []
        labels = (f"before/{old[name].name if name in old else name}", f"now/{new[name].name if name in new else name}") \
            if name == "artifact" else (f"before/{name}", f"now/{name}")
        d = list(difflib.unified_diff(a, b, *labels, lineterm="", n=1))
        if not d:
            continue
        out += d[:DIFF_LINES]
        if len(d) > DIFF_LINES:
            out.append(f"... {len(d) - DIFF_LINES} more diff line(s) in {name} not shown")
    return out if len(out) > 1 else out + ["(no changes)"]


def open_questions(path):
    out = []
    for name, f in _artifact_files(path).items():
        if f.suffix.lower() not in (".md", ".txt"):
            continue
        lines, keep, level = f.read_text(encoding="utf-8", errors="replace").splitlines(), False, 0
        for ln in lines:
            m = re.match(r"^(#+)\s+(.*)", ln)
            if m:
                if keep and len(m.group(1)) <= level:
                    keep = False
                if re.search(r"open questions?", m.group(2), re.IGNORECASE):
                    keep, level = True, len(m.group(1))
                continue
            if keep and ln.strip():
                q = re.sub(r"^[-*+]\s+", "", ln.strip())               # the brief adds its own bullet
                out.append(f"{name}: {q}" if len(_artifact_files(path)) > 1 else q)
    return out


def brief(job_id):
    """The gate brief as text (Markdown)."""
    st = lc.load_state(job_id)
    gate, art, d = st["route"]["gate"], st["artifact_path"], lc.job_dir(job_id)
    version = lc._version(art) if art else None
    L = [f"# Gate brief: {job_id} at {gate}", "",
         f"State {st['state']}. Goal: {st['goal']}", ""]
    L += ["## What you are approving", ""]
    if art:
        L.append(f"- Artifact {art} ({version}), fingerprint {lc.sha256_path(art)}")
        files = _artifact_files(art)
        if (lc.ROOT / art).is_dir():
            L += [f"  - {n}: {lc.sha256_path(f)}" for n, f in files.items()]
    try:
        bf = lc.built_from(st)
        L += [f"- Input {i['id']} {i['path']}: {i['sha256']}" for i in bf["inputs"]] or ["- No recorded inputs"]
        links = bf["links"]
    except lc.LabError as e:
        L.append(f"- NOT APPROVABLE: {e}")
        links = []
    L += ["", "## Approval chain", ""]
    if not links:
        L.append("- Nothing upstream: this approval depends on no other approval.")
    for link in links:
        ok, _ = lc.verify_chain(link["job"], link["gate"])
        L.append(f"- {link['kind']}: {link['job']} at {link['gate']}, approved content {link['artifact_sha256']}: "
                 + ("still valid" if ok else "BROKEN (the next stage will be refused)"))
    L += ["", "## Evidence checks", ""]
    for checker, label in (("check-refs", "Reference check"), ("check-evidence", "Evidence check")):
        runs = [(p, doc) for p, doc in _review_docs(job_id) if doc["reviewer"] == checker]
        cur = [doc for _, doc in runs if doc.get("artifact_version") == version]
        if cur:
            L.append(f"- {label}: {len(cur[-1]['findings'])} problem(s) on {version}")
        else:
            L.append(f"- {label}: passed on {version}" + (f" ({len(runs)} earlier version(s) sent back)" if runs else ""))
    unc = d / "evidence" / f"uncited-{version}.json"
    if unc.exists():
        L.append(f"- Uncited sentences listed for the Verifier: {len(lc.load_json(unc).get('sentences', []))}")
    L += ["", "## Open questions", ""]
    oq = open_questions(art) if art else []
    L += [f"- {q}" for q in oq] or ["- None listed in the artifact."]
    qs = sorted((d / "questions").glob("*")) if (d / "questions").is_dir() else []
    if qs:
        L.append(f"- Questions asked during the job: {len(qs)} round(s), "
                 + ("all answered" if not st.get("awaiting") else "STILL WAITING for an answer"))
    L += ["", "## Usage", ""] + [f"- {ln.strip()}" for ln in lc.usage_summary(job_id)[1:]]
    L += ["", "## Changes since the last version", "", "```"] + (diff_lines(job_id, art) if art else ["(no artifact)"]) + ["```"]
    L += ["", "## Findings in this gate cycle", ""]
    found = cycle_findings(job_id)
    for rv in sorted({f["reviewer"] for f in found}):
        L.append(f"### {rv}")
        for f in (x for x in found if x["reviewer"] == rv):
            L.append(f"- {f['finding_id']} [{f['severity']} {f['rule']}] {f['version']} {f['location']}: {f['issue']}")
        L.append("")
    if not found:
        L.append("- No agent-reviewer findings in this cycle.")
    bad = unreadable_reviews(job_id)
    if bad:
        L.append(f"- Unreadable review file(s), not counted: {', '.join(bad)}")
    must, sampled, minors = to_mark(job_id)
    L += ["", "## Your options", "",
          f"- Approve: python engine/gate.py approve {job_id} [--as pilot] --note \"...\"",
          f"- Reject (counts as gate rejection {st['counters']['gate_rejections'] + 1} of "
          f"{lc.caps()['gate_rejections']}): python engine/gate.py reject {job_id} --feedback \"...\"",
          f"- Hold (not a rejection; restart with gate.py resume): python engine/gate.py hold {job_id} --note \"...\"",
          f"- You will mark {len(must)} blocker/major finding(s) and {len(sampled)} of {minors} minor finding(s).", ""]
    return "\n".join(L)


# ---------- records ----------

def record(job_id, action, brief_text, marks, missed, sampled_ids=(), minors_total=0):
    """Build the verdict document and the saved brief (in memory). Returns (files, review summary)."""
    st = lc.load_state(job_id)
    gate, art = st["route"]["gate"], st["artifact_path"]
    n = len(verdict_files(job_id, gate)) + 1
    d = lc.job_dir(job_id) / "gates"
    brief_path, verdict_path = d / f"{gate}.brief-{n}.md", d / f"{gate}.verdicts-{n}.json"
    brief_bytes = brief_text.encode("utf-8")
    doc = {"job_id": job_id, "gate": gate, "action": action, "n": n, "ts": lc.now(), "approver": lc.approver(),
           "artifact_path": art, "artifact_version": lc._version(art) if art else None,
           "artifact_sha256": lc.sha256_path(art) if art else None,
           "brief": lc.rel(brief_path), "brief_sha256": hashlib.sha256(brief_bytes).hexdigest(),
           "sample": {"minors_total": minors_total, "minors_sampled": len(sampled_ids),
                      "seed_from": f"{job_id}:{lc._version(art) if art else 'none'}"},
           "marks": marks, "missed": missed}
    verdict_bytes = (json.dumps(doc, indent=2) + "\n").encode("utf-8")
    counts = {m: sum(1 for x in marks if x["mark"] == m) for m in MARKS.values()}
    summary = {"verdicts": lc.rel(verdict_path), "verdicts_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
               "brief": lc.rel(brief_path), "brief_sha256": doc["brief_sha256"], "marked": counts,
               "missed": len(missed)}
    return {"brief": (brief_path, brief_bytes), "verdicts": (verdict_path, verdict_bytes), "doc": doc}, summary


def write(files, job_id):
    """Write the saved brief and verdict file, then the ID-only log lines."""
    for key in ("brief", "verdicts"):
        path, data = files[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    doc = files["doc"]
    logs = lc.ROOT / "private" / "logs" if lc.is_internal(job_id) else lc.ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base = {"ts": doc["ts"], "job_id": job_id, "gate": doc["gate"], "action": doc["action"], "n": doc["n"]}
    with open(logs / "finding-verdicts.jsonl", "a", encoding="utf-8") as fh:
        for m in doc["marks"]:                                   # IDs, rule, severity and mark only: never text
            fh.write(json.dumps({**base, "kind": "mark", "reviewer": m["reviewer"], "version": m["version"],
                                 "finding_id": m["finding_id"], "rule": m["rule"], "severity": m["severity"],
                                 "mark": m["mark"], "sampled": m["sampled"]}) + "\n")
        for x in doc["missed"]:
            fh.write(json.dumps({**base, "kind": "missed", "reviewer": x["reviewer"], "rule": x["rule"]}) + "\n")


# ---------- quality ----------

def _log_lines():
    out = []
    for f in (lc.ROOT / "logs" / "finding-verdicts.jsonl", lc.ROOT / "private" / "logs" / "finding-verdicts.jsonl"):
        if f.exists():
            out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def rates(lines, key):
    """{group: {valid, noise, skipped, missed, noise_rate, miss_rate}} grouped by 'reviewer' or 'rule'."""
    out = {}
    for x in lines:
        g = out.setdefault(x.get(key) or "unassigned", {"valid": 0, "noise": 0, "skipped": 0, "missed": 0})
        if x["kind"] == "missed":
            g["missed"] += 1
        else:
            g[x["mark"]] += 1
    for g in out.values():
        g["noise_rate"] = round(g["noise"] / (g["valid"] + g["noise"]), 3) if g["valid"] + g["noise"] else None
        g["miss_rate"] = round(g["missed"] / (g["valid"] + g["missed"]), 3) if g["valid"] + g["missed"] else None
    return out


def quality(reviewer=None, rule=None):
    lines = [x for x in _log_lines() if (reviewer is None or x.get("reviewer") == reviewer)
             and (rule is None or x.get("rule") == rule)]
    return {"by_reviewer": rates(lines, "reviewer"), "by_rule": rates(lines, "rule"), "lines": len(lines)}


def quality_text(reviewer=None, rule=None):
    q = quality(reviewer, rule)
    L = [f"Finding verdicts: {q['lines']} record(s)" + (f" for {reviewer}" if reviewer else "")
         + (f", rule {rule}" if rule else ""),
         "  noise rate = noise / (valid + noise); miss rate = missed / (valid + missed); skipped not counted"]
    for title, key in (("By reviewer", "by_reviewer"), ("By rule", "by_rule")):
        L.append(title)
        for g, v in sorted(q[key].items()):
            L.append(f"  {g:<20} valid {v['valid']}  noise {v['noise']}  skipped {v['skipped']}  missed {v['missed']}"
                     f"  noise rate {v['noise_rate']}  miss rate {v['miss_rate']}")
    return "\n".join(L)
