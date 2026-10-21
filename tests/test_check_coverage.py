"""Planted-fault tests for engine/check_coverage.py. Standard library only.

    python -m unittest tests.test_check_coverage
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
import check_coverage as cc  # noqa: E402

PLAN = """# Plan
## Phase 0
| Task | Owner | Do | Check | Est. |
|---|---|---|---|---|
| T0.1 | CC | Set up [C01, S02]. | ok | 1 |
| T0.2 | CC | Build it [S02]. | ok | 1 |

## In every phase [P01]
| Practice | How |
|---|---|
| Reuse | Always |
"""

MATRIX = """# Matrix
| ID | Finding | Handled by |
|---|---|---|
| C01 | Pace | T0.1 |
| S02 | Gates | T0.1, T0.2, CLAUDE.md |
| P01 | Reuse | "In every phase" |
"""

REUSE = """# Reuse
## From the lab (`vendor/lab/`)
| Source | Component | How | Task |
|---|---|---|---|
| `scripts/core.py`, `.claude/agents/x.md` | Core | port | T0.1 |
| `runs/*calibration*/key.md` | Evals | port | T0.1 |

## New (nothing suitable to reuse)
| Component | Why new | Task |
|---|---|---|
| `generate.py` | none | T0.2 |
"""


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vendor = Path(self.tmp.name)
        for rel in ["lab/scripts/core.py", "lab/_claude/agents/x.md", "lab/runs/r1-calibration/key.md"]:
            (self.vendor / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.vendor / rel).write_text("x", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, plan=PLAN, matrix=MATRIX, reuse=REUSE):
        return cc.check_matrix(plan, matrix) + cc.check_reuse(reuse, self.vendor)

    def test_clean_fixture_passes(self):
        self.assertEqual(self.errors(), [])

    def test_cited_task_missing(self):
        errs = self.errors(matrix=MATRIX.replace("| C01 | Pace | T0.1 |", "| C01 | Pace | T0.1, T9.9 |"))
        self.assertTrue(any("T9.9, which is not a task" in e for e in errs), errs)

    def test_cited_task_does_not_name_id(self):
        errs = self.errors(plan=PLAN.replace("Build it [S02].", "Build it."))
        self.assertTrue(any("T0.2 does not name S02" in e for e in errs), errs)

    def test_row_with_only_reference_citation(self):
        errs = self.errors(matrix=MATRIX.replace("T0.1, T0.2, CLAUDE.md", "CLAUDE.md"))
        self.assertTrue(any("S02: no cited task or section names it" in e for e in errs), errs)

    def test_section_does_not_name_id(self):
        errs = self.errors(plan=PLAN.replace("## In every phase [P01]", "## In every phase"))
        self.assertTrue(any("P01: cites section" in e for e in errs), errs)

    def test_unknown_id_in_plan(self):
        errs = self.errors(plan=PLAN.replace("[C01, S02]", "[C01, S02, R99]"))
        self.assertTrue(any("R99: cited in the plan but not in the matrix" in e for e in errs), errs)

    def test_unrecognised_citation(self):
        errs = self.errors(matrix=MATRIX.replace("| C01 | Pace | T0.1 |", "| C01 | Pace | T0.1, somewhere |"))
        self.assertTrue(any("unrecognised citation" in e for e in errs), errs)

    def test_missing_vendor_path(self):
        (self.vendor / "lab/scripts/core.py").unlink()
        errs = self.errors()
        self.assertTrue(any("vendor/lab/scripts/core.py not found" in e for e in errs), errs)

    def test_glob_with_no_match(self):
        (self.vendor / "lab/runs/r1-calibration/key.md").unlink()
        errs = self.errors()
        self.assertTrue(any("*calibration*" in e for e in errs), errs)

    def test_dot_claude_is_not_accepted_in_vendor(self):
        # A vendor copy that kept .claude (not renamed) must not satisfy the map.
        src = self.vendor / "lab/_claude"
        src.rename(self.vendor / "lab/.claude")
        errs = self.errors()
        self.assertTrue(any(".claude/agents/x.md not found" in e for e in errs), errs)

    def test_new_and_unmapped_sections_are_ignored(self):
        self.assertNotIn(("lab", "generate.py"), list(cc.reuse_paths(REUSE)))


if __name__ == "__main__":
    unittest.main()
