"""Coverage check: build plan <-> coverage matrix <-> reuse map <-> vendor/.

Fails when:
  1. the matrix cites a task or section that does not exist in the plan;
  2. a cited task or section does not name the matrix row's ID in its own text;
  3. a matrix row has no cited task or section that names its ID;
  4. the plan cites an ID (e.g. [S08]) that is not in the matrix;
  5. a source path in the reuse map does not exist in vendor/.

Standard library only.

    python engine/check_coverage.py [--plan P] [--matrix M] [--reuse R] [--vendor V]
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^[A-Z]\d{2}$")
PLAN_ID_RE = re.compile(r"^[CALSPRDO]\d{2}$")
TASK_RE = re.compile(r"^T\d+\.\d+$")
# Matrix citations that point at plan sections instead of tasks.
SECTION_CITES = {'"In every phase"': "In every phase", '"Parallel work" section': "Parallel work"}
# Citations that are references, not plan text: they never count as naming an ID.
REFERENCE_CITES = {"CLAUDE.md"}


def table_rows(text):
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|[\s|:-]+\|$", line):
            yield [c.strip() for c in line.strip().strip("|").split("|")]


def plan_tasks(plan):
    return {cells[0]: " | ".join(cells) for cells in table_rows(plan) if TASK_RE.match(cells[0])}


def plan_sections(plan):
    sections, current = {}, None
    for line in plan.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current:
            sections[current] += line + "\n"
    return sections


def names(text, fid):
    return re.search(rf"\b{fid}\b", text) is not None


def check_matrix(plan, matrix):
    errors, tasks, sections = [], plan_tasks(plan), plan_sections(plan)
    matrix_ids = set()
    for cells in table_rows(matrix):
        fid = cells[0]
        if not ID_RE.match(fid):
            continue
        if fid in matrix_ids:
            errors.append(f"{fid}: duplicate row in matrix")
        matrix_ids.add(fid)
        named_somewhere = False
        for cite in (c.strip() for c in cells[-1].split(",")):
            if cite in REFERENCE_CITES:
                continue
            if TASK_RE.match(cite):
                if cite not in tasks:
                    errors.append(f"{fid}: cites {cite}, which is not a task in the plan")
                elif not names(tasks[cite], fid):
                    errors.append(f"{fid}: cites {cite}, but {cite} does not name {fid}")
                else:
                    named_somewhere = True
            elif cite in SECTION_CITES:
                title = next((t for t in sections if t.startswith(SECTION_CITES[cite])), None)
                if title is None:
                    errors.append(f"{fid}: cites section {cite}, not found in the plan")
                elif not names(title + "\n" + sections[title], fid):
                    errors.append(f"{fid}: cites section {cite}, which does not name {fid}")
                else:
                    named_somewhere = True
            else:
                errors.append(f"{fid}: unrecognised citation {cite!r}")
        if not named_somewhere:
            errors.append(f"{fid}: no cited task or section names it")
    plan_ids = set()
    for group in re.findall(r"\[([^\]]+)\]", plan):
        plan_ids |= {x.strip() for x in group.split(",") if PLAN_ID_RE.match(x.strip())}
    for fid in sorted(plan_ids - matrix_ids):
        errors.append(f"{fid}: cited in the plan but not in the matrix")
    return errors


def reuse_paths(reuse):
    """Yield (vendor subfolder, source path) for every backticked path in a mapped section."""
    vendor_dir = None
    for line in reuse.splitlines():
        if line.startswith("## "):
            m = re.search(r"`vendor/([^`/]+)/?`", line)
            vendor_dir = m.group(1) if m else None
            continue
        if vendor_dir is None or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] in ("Source", "") or set(cells[0]) <= set("-: "):
            continue
        for token in re.findall(r"`([^`]+)`", cells[0]):
            if "/" in token or re.search(r"\.\w+$", token):
                yield vendor_dir, token


def check_reuse(reuse, vendor):
    errors = []
    for sub, path in reuse_paths(reuse):
        pattern = "/".join("_claude" if p == ".claude" else p for p in path.rstrip("/").split("/"))
        base = vendor / sub
        if any(ch in pattern for ch in "*?["):
            found = any(base.glob(pattern))
        else:
            found = (base / pattern).exists()
        if not found:
            errors.append(f"reuse map: vendor/{sub}/{path} not found")
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", type=Path, default=ROOT / "private/plan/BUILD_PLAN.md")
    ap.add_argument("--matrix", type=Path, default=ROOT / "private/plan/coverage-matrix.md")
    ap.add_argument("--reuse", type=Path, default=ROOT / "private/plan/reuse-map.md")
    ap.add_argument("--vendor", type=Path, default=ROOT / "vendor")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console is cp1252
    read = lambda p: p.read_text(encoding="utf-8")
    errors = check_matrix(read(a.plan), read(a.matrix)) + check_reuse(read(a.reuse), a.vendor)
    for e in errors:
        print("FAIL:", e)
    print(f"RESULT: {'FAIL' if errors else 'PASS'} ({len(errors)} problems)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
