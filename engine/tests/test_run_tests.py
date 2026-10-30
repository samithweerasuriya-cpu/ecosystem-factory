"""Self-test of the logs guard in engine/run_tests.py, against a temporary fake repo."""
import io
import json
import subprocess
import sys
import tempfile
import time
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
        own = {f.stem for f in (run_tests.REPO / "tests").glob("test_*.py")}        # the repo's own tests/ too
        self.assertLessEqual(own, modules(fast) | set(skipped), own)

    def test_job_files_are_guarded(self):
        _, changed, _ = self.run_guard(
            lambda: (self.repo / "jobs/20260101-demo-a/state.json").write_text("{}", encoding="utf-8"))
        self.assertEqual(changed, ["jobs/20260101-demo-a/state.json"])


class KeyboardInputTests(unittest.TestCase):
    """T1.3 follow-up: the runner closes keyboard input itself, for itself and every process it starts."""

    def test_nothing_waits_on_an_open_keyboard(self):
        child = ("import subprocess, sys; sys.path.insert(0, sys.argv[1]); import run_tests; run_tests.close_stdin()\n"
                 "try:\n    input()\nexcept EOFError:\n    print('EOF')\n"
                 "print(subprocess.run([sys.executable, '-c', 'import sys; print(repr(sys.stdin.read()))'],"
                 " capture_output=True, text=True).stdout.strip())")
        # stdin is a pipe this test never writes to or closes: without close_stdin both reads would wait forever
        p = subprocess.Popen([sys.executable, "-c", child, str(REPO / "engine")], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
        try:
            p.wait(timeout=60)
        finally:
            p.kill()
            p.stdin.close()
        self.assertEqual(p.stdout.read().split(), ["EOF", "''"])
        p.stdout.close()


PLANTED = {
    "pass": "import unittest\nclass Ok(unittest.TestCase):\n    def test_ok(self):\n        pass\n",
    "fail": "import unittest\nclass Bad(unittest.TestCase):\n    def test_bad(self):\n        self.fail('planted')\n",
    # starts a grandchild (pid saved next to this file), then hangs: the watchdog must stop both
    "hang": ("import subprocess, sys, time, unittest\nfrom pathlib import Path\n"
             "class Hang(unittest.TestCase):\n    def test_sleeps(self):\n"
             "        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
             "        (Path(__file__).parent / 'grandchild.pid').write_text(str(p.pid))\n"
             "        time.sleep(300)\n"),
    "slow": ("import time, unittest\nclass Slow(unittest.TestCase):\n"
             "    def test_a(self):\n        time.sleep(3)\n    def test_b(self):\n        time.sleep(3)\n"),
}


def alive(pid):
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out.split()
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class WatchdogTests(unittest.TestCase):
    """Lesson 16: a hung test is stopped, named and recorded as a failure; the runner never hangs silently.
    Full runs are recorded in logs/tests-last.json only, fast runs in logs/tests-last-fast.json only."""

    FULL_BEFORE = '{"tier": "full", "earlier": true}\n'

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        (self.repo / "logs").mkdir()
        (self.repo / "logs/tests-last.json").write_text(self.FULL_BEFORE, encoding="utf-8")
        self.tests = Path(tempfile.mkdtemp())

    def tearDown(self):
        force_rmtree(self.repo)
        force_rmtree(self.tests)

    def supervise(self, kind, **kw):
        (self.tests / f"test_planted_{kind}.py").write_text(PLANTED[kind], encoding="utf-8")
        lines = []
        kw.setdefault("test_timeout", 60)
        kw.setdefault("run_timeout", 120)
        code, rec = run_tests.supervise(repo=self.repo, start_dirs=[self.tests], out=lines.append,
                                        child_output=subprocess.DEVNULL, **kw)
        return code, rec, "\n".join(lines)

    def last(self, tier):
        p = self.repo / "logs" / run_tests.LAST[tier]
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def test_hung_test_is_stopped_named_and_recorded_fast_tier(self):
        start = time.time()
        code, rec, out = self.supervise("hang", fast=True, test_timeout=3)
        self.assertLess(time.time() - start, 60)
        self.assertEqual(code, 2)
        self.assertEqual(rec["timed_out"], {"kind": "test", "test": "test_planted_hang.Hang.test_sleeps", "limit_s": 3})
        self.assertIn("TIMEOUT: test_planted_hang.Hang.test_sleeps", out)
        self.assertEqual(self.last("fast"), rec)
        self.assertEqual((rec["tier"], rec["failures"], rec["tests"]), ("fast", 1, 1))
        self.assertEqual((self.repo / "logs/tests-last.json").read_text(encoding="utf-8"), self.FULL_BEFORE)
        pid = int((self.tests / "grandchild.pid").read_text())
        self.assertFalse(alive(pid), "the hung test's own child process was left running")

    def test_full_tier_timeout_overwrites_the_full_record_as_failed(self):
        code, rec, _ = self.supervise("hang", test_timeout=3)
        self.assertEqual(code, 2)
        self.assertEqual(self.last("full"), rec)
        self.assertEqual((rec["tier"], rec["failures"], rec["timed_out"]["kind"]), ("full", 1, "test"))
        self.assertIsNone(self.last("fast"))

    def test_whole_run_limit(self):
        code, rec, out = self.supervise("slow", fast=True, test_timeout=60, run_timeout=4)
        self.assertEqual(code, 2)
        self.assertEqual(rec["timed_out"]["kind"], "run")
        self.assertTrue(rec["timed_out"]["test"].startswith("test_planted_slow.Slow."))
        self.assertIn("run ran over 4 s", out)

    def test_normal_runs_are_recorded_by_tier(self):
        code, rec, _ = self.supervise("pass", fast=True)
        self.assertEqual(code, 0)
        self.assertEqual((rec["tier"], rec["tests"], rec["failures"], rec["guard_ok"]), ("fast", 1, 0, True))
        self.assertNotIn("timed_out", rec)
        self.assertEqual((self.repo / "logs/tests-last.json").read_text(encoding="utf-8"), self.FULL_BEFORE)
        code, rec, _ = self.supervise("pass")
        self.assertEqual((code, self.last("full")), (0, rec))
        self.assertEqual(rec["tier"], "full")

    def test_failing_test_fails_the_run(self):
        code, rec, _ = self.supervise("fail", fast=True)
        self.assertEqual((code, rec["failures"]), (1, 1))

    def test_limits_must_be_positive_numbers(self):
        for argv in (["--timeout", "x"], ["--test-timeout", "0"], ["--timeout"]):
            with self.assertRaises(SystemExit):
                run_tests._seconds(argv, argv[0], 1)
        self.assertEqual(run_tests._seconds(["--timeout", "90"], "--timeout", 1), 90)



if __name__ == "__main__":
    unittest.main()
