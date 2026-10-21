#!/usr/bin/env python3
"""Validate reviewer findings files against schemas/findings.schema.json (stdlib only).

Derived from the author's earlier private lab. Schema checks via engine/schemacheck.py, plus
explicit checks with clear messages: blocker/major => verdict fail, unique finding ids.
Severity lock: each reviewer's rulebook is named in config/reviewers.json. A finding's severity
must equal the rulebook severity for its rule ID, unless the approver's gate feedback for that
job (jobs/<job>/reviews/human-feedback-*.md, e.g. "Treat AB16 as major") sets a stricter one,
which is then required. Laxer feedback is ignored. Rule IDs with no rulebook severity and no
feedback override are not checked. A reviewer with no configured rulebook is an error.
The Orchestrator runs this on every review file before recording a review event.
  python engine/validate_findings.py jobs/<job>/reviews/<reviewer>-v1.json [more files...]
Exit 0 = all valid, 1 = any invalid or unreadable.
"""
import json
import os
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import schemacheck  # noqa: E402

ROOT = Path(os.environ.get("LAB_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or ENGINE.parent)
SCHEMA = ROOT / "schemas" / "findings.schema.json"
REVIEWERS = ROOT / "config" / "reviewers.json"
RANK = {"minor": 0, "major": 1, "blocker": 2}
RULE_ID = r"[A-Z]{1,4}\d{2,3}"
ROW_ID = re.compile(rf"^\|\s*({RULE_ID})\s*\|")
FEEDBACK_SEV = re.compile(rf"\b({RULE_ID})\b[^.;\n]{{0,25}}?\b(blocker|major|minor)\b", re.IGNORECASE)


def rulebook_severities(path):
    """{rule_id: severity} from a rulebook's tables: the first cell is the ID, the first
    cell equal to blocker/major/minor is its severity."""
    out = {}
    path = Path(path)
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW_ID.match(line)
        if not m:
            continue
        cells = [c.strip().lower() for c in line.strip().strip("|").split("|")]
        sev = next((c for c in cells[1:] if c in RANK), None)
        if sev:
            out[m.group(1)] = sev
    return out


def reviewer_rulebook(reviewer, root=ROOT):
    """Path of the rulebook configured for this reviewer, or None."""
    f = root / "config" / "reviewers.json"
    cfg = json.loads(f.read_text(encoding="utf-8")).get("reviewers", {}) if f.is_file() else {}
    entry = cfg.get(reviewer)
    return root / entry["rulebook"] if entry and entry.get("rulebook") else None


def feedback_overrides(job_id, root=ROOT):
    """{rule_id: strictest severity} set in the approver's gate feedback files for this job."""
    out = {}
    for fb in sorted((root / "jobs" / str(job_id) / "reviews").glob("human-feedback-*.md")):
        for rule, sev in FEEDBACK_SEV.findall(fb.read_text(encoding="utf-8")):
            rule, sev = rule.upper(), sev.lower()
            if RANK[sev] > RANK.get(out.get(rule), -1):
                out[rule] = sev
    return out


def required_severity(rule, rulebook, overrides, rulebook_name="the rulebook"):
    base, fb = rulebook.get(rule), overrides.get(rule)
    if fb and (base is None or RANK[fb] > RANK[base]):
        return fb, "the approver's gate feedback"
    return (base, rulebook_name) if base else (None, None)


def severity_errors(doc, rulebook, overrides, rulebook_name="the rulebook"):
    errs = []
    for i, f in enumerate(doc.get("findings") or []):
        if not isinstance(f, dict):
            continue
        want, why = required_severity(str(f.get("rule", "")).strip().upper(), rulebook, overrides, rulebook_name)
        if want and f.get("severity") != want:
            errs.append(f"$.findings[{i}] ({f.get('id', '?')}, {f.get('rule')}): severity "
                        f"{f.get('severity')!r} must be {want!r} per {why}")
    return errs


def semantic(doc):
    """Explicit rule checks, so the Orchestrator gets a readable reason."""
    errs = []
    findings = doc.get("findings") if isinstance(doc.get("findings"), list) else []
    serious = [f.get("id", "?") for f in findings
               if isinstance(f, dict) and f.get("severity") in ("blocker", "major")]
    if serious and doc.get("verdict") != "fail":
        errs.append(f"$.verdict: blocker/major findings {serious} require verdict 'fail'")
    ids = [f.get("id") for f in findings if isinstance(f, dict)]
    dupes = sorted({i for i in ids if i is not None and ids.count(i) > 1})
    if dupes:
        errs.append(f"$.findings: duplicate finding ids {dupes}")
    return errs


def validate(doc, schema, rulebook=None, overrides=None, rulebook_name="the rulebook"):
    """Schema + semantic checks; the severity lock runs when a rulebook (and optional overrides) is given."""
    errs = schemacheck.check(doc, schema)
    if isinstance(doc, dict):
        errs += [e for e in semantic(doc) if e not in errs]
        if rulebook is not None:
            errs += severity_errors(doc, rulebook, overrides or {}, rulebook_name)
    return errs


def validate_file(name, schema, root=ROOT):
    try:
        doc = json.loads(Path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, [f"cannot read JSON ({e})"]
    if not isinstance(doc, dict):
        return doc, schemacheck.check(doc, schema)
    rb_path = reviewer_rulebook(doc.get("reviewer"), root)
    if rb_path is None:
        return doc, validate(doc, schema) + [f"$.reviewer: no rulebook configured for {doc.get('reviewer')!r} in config/reviewers.json"]
    if not rb_path.is_file():
        return doc, validate(doc, schema) + [f"$.reviewer: rulebook {rb_path.relative_to(root).as_posix()} not found"]
    errs = validate(doc, schema, rulebook_severities(rb_path), feedback_overrides(doc.get("job_id"), root),
                    rb_path.relative_to(root).as_posix())
    return doc, errs


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = 0
    for name in argv:
        doc, errs = validate_file(name, schema)
        if errs:
            bad += 1
            print(f"INVALID {name}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"valid   {name}  (verdict={doc['verdict']}, findings={len(doc['findings'])})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
