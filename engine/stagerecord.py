#!/usr/bin/env python3
"""state.py stage-record <job> (stdlib only, T0.19): stage one job's record for a commit, and nothing else.

Stages the job's folder (new, changed and removed files) and, in the committed logs, only the lines whose
job_id is this job: other jobs' lines stay unstaged. Refuses:
- an internal job (its record never goes to Git) and an unknown job;
- while any internal job would leak (check-private over every internal job);
- a log whose staged version is not the start of the file (logs are append-only: something rewrote it);
- an unreadable log line;
- any publish-check finding in what it would stage (paths, file contents, the new log lines).
"""
import json
import subprocess

import labcore as lc
import publish_check as pc

LOGS = ("logs/gate-audit.jsonl", "logs/usage.jsonl", "logs/usage-unmatched.jsonl", "logs/finding-verdicts.jsonl")


def _git(*args, data=None):
    p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(lc.ROOT), *args], input=data,
                       capture_output=True)
    if p.returncode != 0:
        raise lc.LabError(f"git {' '.join(args[:2])} failed: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return p.stdout


def _index_text(path):
    listed = _git("ls-files", "--cached", "--", path).decode().strip()
    return _git("show", f":{path}").decode("utf-8", "replace") if listed else ""


def plan(job_id):
    """(files to stage, {log: (new index text, number of new lines)}). Raises LabError on any refusal."""
    if lc.find_job(job_id) is None:
        raise lc.LabError(f"job not found: {job_id}")
    if lc.is_internal(job_id):
        raise lc.LabError(f"{job_id} is an internal job: its record never goes to Git")
    pj = lc.ROOT / "private" / "jobs"
    for st in sorted(pj.glob("*/state.json")) if pj.is_dir() else []:
        leaks = lc.private_leaks(st.parent.name)
        if leaks:
            raise lc.LabError(f"internal job {st.parent.name} would leak ({len(leaks)} place(s)); "
                              "run state.py check-private on it first")
    jd = lc.rel(lc.job_dir(job_id))
    files = sorted(set(f for f in _git("ls-files", "--others", "--modified", "--exclude-standard", "-z", "--",
                                       jd).decode("utf-8", "replace").split("\0") if f))
    logs = {}
    for path in LOGS:
        f = lc.ROOT / path
        if not f.is_file():
            continue
        work, idx = f.read_text(encoding="utf-8"), _index_text(path)
        if not work.startswith(idx):
            raise lc.LabError(f"{path}: the staged version is not the start of the file (logs are append-only)")
        new = []
        for line in work[len(idx):].splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                raise lc.LabError(f"{path}: a line can't be read; refusing to stage around it") from None
            if rec.get("job_id") == job_id:
                new.append(line)
        if new:
            logs[path] = (idx + "".join(l + "\n" for l in new), len(new))
    rules = pc.Rules(lc.ROOT)
    findings = []
    for rel in files:
        findings += rules.path_findings(rel)
        p = lc.ROOT / rel
        if p.is_file():
            findings += pc.content_findings(rules, rel, p.read_bytes())
    for path, (text, n) in logs.items():
        findings += rules.text_findings("\n".join(text.splitlines()[-n:]), f"{path} (new lines)")
    if findings:
        raise lc.LabError("publish check: " + "; ".join(f"{w}: {k} ({d})" for w, k, d in findings[:10]))
    return files, logs


def stage(job_id):
    files, logs = plan(job_id)
    if files:
        _git("add", "-A", "--", lc.rel(lc.job_dir(job_id)))
    for path, (text, _) in logs.items():
        sha = _git("hash-object", "-w", "--stdin", data=text.encode("utf-8")).decode().strip()
        _git("update-index", "--add", "--cacheinfo", f"100644,{sha},{path}")
    return files, {p: n for p, (_, n) in logs.items()}
