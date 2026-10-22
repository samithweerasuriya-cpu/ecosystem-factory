"""Self-test of the logs guard in engine/run_tests.py, against a temporary fake repo."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO, force_rmtree

sys.path.insert(0, str(REPO / "engine"))
import run_tests  # noqa: E402


def suite_of(fn):
    case = type("Planted", (unittest.TestCase,), {"test_planted": lambda self: fn()})
    return unittest.defaultTestLoader.loadTestsFromTestCase(case)


class GuardSelfTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        for rel in ("logs/gate-audit.jsonl", "jobs/20260101-demo-a/state.json", ".lab/OPERATE"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("original\n", encoding="utf-8")
        (self.repo / "notes.txt").write_text("outside the guarded folders\n", encoding="utf-8")

    def tearDown(self):
        force_rmtree(self.repo)

    def run_guard(self, fn):
        return run_tests.guarded_run(suite_of(fn), repo=self.repo, stream=io.StringIO())

    def test_clean_run_reports_nothing(self):
        result, changed, n = self.run_guard(lambda: None)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual((changed, n), ([], 3))

    def test_planted_writes_are_caught(self):
        def leak():
            (self.repo / "logs/gate-audit.jsonl").write_text("tampered\n", encoding="utf-8")   # changed
            (self.repo / "logs/blocked.jsonl").write_text("new\n", encoding="utf-8")           # added
            (self.repo / ".lab/OPERATE").unlink()                                              # removed
        result, changed, _ = self.run_guard(leak)
        self.assertTrue(result.wasSuccessful())  # the planted test passes; only the guard notices
        self.assertEqual(changed, [".lab/OPERATE", "logs/blocked.jsonl", "logs/gate-audit.jsonl"])

    def test_writes_outside_guarded_folders_are_ignored(self):
        result, changed, _ = self.run_guard(
            lambda: (self.repo / "notes.txt").write_text("edited\n", encoding="utf-8"))
        self.assertEqual(changed, [])

    def test_fast_tier_skips_only_full_tier_modules(self):
        fast, skipped = run_tests.collect(fast=True)
        full, none_skipped = run_tests.collect(fast=False)
        modules = lambda s: {type(t).__module__ for t in run_tests._walk(s)}
        self.assertIn("test_delivery_t10", skipped)
        self.assertNotIn("test_delivery_t10", modules(fast))
        self.assertIn("test_delivery_t10", modules(full))
        self.assertEqual(none_skipped, [])
        self.assertEqual(modules(full) - modules(fast), set(skipped))
        self.assertIn("test_check_coverage", modules(fast))                            # the repo's own tests/ too

    def test_job_files_are_guarded(self):
        _, changed, _ = self.run_guard(
            lambda: (self.repo / "jobs/20260101-demo-a/state.json").write_text("{}", encoding="utf-8"))
        self.assertEqual(changed, ["jobs/20260101-demo-a/state.json"])


if __name__ == "__main__":
    unittest.main()
