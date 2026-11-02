"""T2.5 case writing, process-heavy part (full tier): every shipped charter case seeds a job that waits on the
charter-writer, and every shipped interview case creates its job with its brief and context files, each in its own
temporary factory copy, with no model call. The quick checks on the same cases are in test_cases_t25.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cases_t25 import CaseBase  # noqa: E402

TIER = "full"                 # each case copies the factory and drives real engine steps


class ShippedCaseRunTests(CaseBase):
    def test_every_charter_case_seeds_a_job_waiting_on_the_writer(self):
        self.copy_suites()
        suite = self.re.load_suite("charter-writer")
        for c in self.re.load_cases(suite):
            root = self.js.make_copy()
            try:
                job = self.js.seed_charter_job(root, c)
                st = self.js.load_state(root, job)
                self.assertEqual((st["state"], st["stage"]), ("WORKING", "charter-writer"), c["id"])
            finally:
                self.js.remove_copy(root)
        self.assertEqual(self.calls(), [])

    def test_every_interview_case_creates_its_job(self):
        self.copy_suites()
        suite = self.re.load_suite("interviewer")
        for c in self.re.load_cases(suite):
            root = self.js.make_copy()
            try:
                job = self.js.new_job(root, c)
                st = self.js.load_state(root, job)
                self.assertEqual((st["state"], st["stage"]), ("WORKING", "interviewer"), c["id"])
                self.assertEqual(len(st.get("context", [])), len(c.get("context", [])), c["id"])
            finally:
                self.js.remove_copy(root)
        self.assertEqual(self.calls(), [])
