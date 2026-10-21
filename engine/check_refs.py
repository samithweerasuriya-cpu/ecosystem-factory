#!/usr/bin/env python3
"""Reference check: every path and ID in a new artifact version resolves, and none points
to an older draft of the same job. Stdlib only.

labcore runs this on every artifact_ready and revised event, before any agent reviewer;
a failure goes back to the author as findings from reviewer `check-refs` (rules/check-refs.md).

  python engine/check_refs.py <job> [<artifact path>]     # exit 0 clean, 1 problems

Rules
  REF01  a repo path in the artifact does not exist
  REF02  a job ID or input ID ([A:A01]) does not resolve
  REF03  the artifact points to another draft of its own job (stale reference)
Source IDs ([S:...]) are checked by the evidence module (T0.9), not here.
"""
import json
import os
import re
import sys
from pathlib import Path

TEXT_SUFFIXES = {".md", ".json", ".txt", ".yaml", ".yml", ".csv", ".py", ".toml", ".html"}
TOP_DIRS = ("jobs", "engine", "config", "schemas", "rules", "templates", "docs", "evals", "private")
PATH_RE = re.compile(r"(?<![\w./-])((?:%s)/[A-Za-z0-9_./-]*[A-Za-z0-9_/-])" % "|".join(TOP_DIRS))
JOB_RE = re.compile(r"(?<![\w/-])(\d{8}-[a-z]+-[a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])")
INPUT_RE = re.compile(r"\[A:([A-Za-z0-9-]+)\]")


def artifact_texts(root, artifact):
    p = Path(root) / artifact
    files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file()) if p.is_dir() else []
    for f in files:
        if f.suffix.lower() in TEXT_SUFFIXES:
            yield f.relative_to(root).as_posix(), f.read_text(encoding="utf-8", errors="replace")


def check(root, job_id, artifact, input_ids):
    """Return a list of {rule, location, issue} for the artifact (file or folder)."""
    root = Path(root)
    own = next((f"{h}/{job_id}" for h in ("jobs", "private/jobs") if (root / h / job_id).is_dir()), f"jobs/{job_id}")
    problems, own_drafts = [], f"{own}/drafts/"
    artifact = Path(artifact).as_posix()
    for where, text in artifact_texts(root, artifact):
        for n, line in enumerate(text.splitlines(), 1):
            loc = f"{where}:{n}"
            stripped = line
            for m in PATH_RE.finditer(line):
                path = m.group(1).rstrip("/.")
                stripped = stripped.replace(m.group(1), " ")
                if path.startswith(own_drafts) and not (path == artifact or path.startswith(artifact + "/")
                                                        or artifact.startswith(path + "/")):
                    problems.append({"rule": "REF03", "location": loc,
                                     "issue": f"points to another draft of this job: {path} (current artifact: {artifact})"})
                elif not (root / path).exists():
                    problems.append({"rule": "REF01", "location": loc, "issue": f"path does not exist: {path}"})
            for m in JOB_RE.finditer(stripped):
                if not any((root / h / m.group(1)).is_dir() for h in ("jobs", "private/jobs")):
                    problems.append({"rule": "REF02", "location": loc, "issue": f"job ID does not resolve: {m.group(1)}"})
            for m in INPUT_RE.finditer(line):
                if m.group(1) not in input_ids:
                    problems.append({"rule": "REF02", "location": loc, "issue": f"input ID does not resolve: [A:{m.group(1)}]"})
    return problems


def findings_doc(job_id, artifact, version, problems):
    return {"job_id": job_id, "reviewer": "check-refs", "artifact_path": artifact,
            "artifact_version": version, "verdict": "fail" if problems else "pass",
            "rules_checked": ["REF01", "REF02", "REF03"],
            "findings": [{"id": f"F-{i:02d}", "rule": p["rule"], "severity": "blocker",
                          "location": p["location"], "issue": p["issue"],
                          "fix": "Point to an existing path or ID, or to the current version."}
                         for i, p in enumerate(problems, 1)],
            "summary": f"{len(problems)} unresolved reference(s)" if problems else "all references resolve"}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    root = Path(os.environ.get("LAB_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent)
    home = next((root / h / argv[0] for h in ("jobs", "private/jobs") if (root / h / argv[0]).is_dir()), root / "jobs" / argv[0])
    st = json.loads((home / "state.json").read_text(encoding="utf-8"))
    artifact = argv[1] if len(argv) > 1 else st["artifact_path"]
    problems = check(root, argv[0], artifact, {i["id"] for i in st.get("inputs", [])})
    for p in problems:
        print(f"{p['rule']}  {p['location']}  {p['issue']}")
    print("references OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
