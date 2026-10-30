#!/usr/bin/env python3
"""Run every engine test, then prove the run left the real repo's logs, jobs and mode untouched.

  python engine/run_tests.py [-v]            # FULL: before every commit and in every Check
  python engine/run_tests.py --fast [-v]     # FAST: during work (skips modules with TIER = "full")
  options: --test-timeout SECONDS (default 600)   --timeout SECONDS (default 3600, the whole run)

Tests run against temporary copies (LAB_ROOT). This runner fingerprints every file under
logs/, jobs/ and .lab/ of the real repo before and after the suite and fails if anything
was added, changed or removed. The guard itself is tested against a fake repo
(engine/tests/test_run_tests.py). Exit 0 = all tests passed and nothing changed.
Keyboard input is closed first (T1.3 follow-up): the runner and every process a test starts read an empty
input, so no test can wait on the keyboard in a real terminal (it behaves as with `$null |` piped in).
Watchdog (T2.2 prelude, lesson 16): the suite runs in a child process that writes the test it is on to a
heartbeat file; this process only watches. When one test runs past --test-timeout, or the whole run past
--timeout, it stops the child and every process it started, names the test, still runs the guard, records
a failed result and exits 2. It never hangs silently. Full suites run in the foreground only.
After a run the counts are written for engine/report.py (T1.7): a full run to logs/tests-last.json, a
fast run to logs/tests-last-fast.json (so a fast run never replaces the full record the export reads):
engine version, tier, tests, failures, skipped, guard result, the UTC time and, after a timeout,
timed_out (kind, test, limit). Both are written after the guard's second fingerprint, so they never fail
the guard; both are untracked.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
REPO = ENGINE.parent
GUARDED = ("logs", "jobs", ".lab")
TEST_TIMEOUT = 600   # seconds one test may run (the slowest end-to-end test is far below this)
RUN_TIMEOUT = 3600   # seconds the whole run may take (the longest full run so far: 22.6 min)
POLL = 0.5
LAST = {"full": "tests-last.json", "fast": "tests-last-fast.json"}


def fingerprint(repo=REPO):
    out = {}
    for top in GUARDED:
        base = Path(repo) / top
        if base.exists():
            for f in sorted(p for p in base.rglob("*") if p.is_file()):
                out[f.relative_to(repo).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def guarded(fn, repo=REPO):
    """Call fn(); return (its value, changed paths, number of files fingerprinted)."""
    before = fingerprint(repo)
    value = fn()
    after = fingerprint(repo)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    return value, changed, len(before)


def guarded_run(suite, repo=REPO, verbosity=1, stream=None):
    """Run suite in this process; return (result, changed paths, number of files fingerprinted)."""
    return guarded(lambda: unittest.TextTestRunner(verbosity=verbosity, stream=stream or sys.stderr).run(suite), repo)


def _walk(suite):
    for t in suite:
        yield from (_walk(t) if isinstance(t, unittest.TestSuite) else [t])


def collect(fast=False, folders=None):
    """(suite, skipped full-tier module names). Engine tests, plus the repo's own tests/ if present.
    --fast skips modules that declare TIER = "full" (the slow end-to-end suites)."""
    suites = []
    for folder in folders or (ENGINE / "tests", REPO / "tests"):
        folder = Path(folder)
        if folder.is_dir():
            sys.path.insert(0, str(folder))
            suites.append(unittest.defaultTestLoader.discover(str(folder), top_level_dir=str(folder)))
    tests, skipped = [], set()
    for t in _walk(unittest.TestSuite(suites)):
        module = sys.modules.get(type(t).__module__)
        if fast and getattr(module, "TIER", "fast") == "full":
            skipped.add(type(t).__module__)
            continue
        tests.append(t)
    return unittest.TestSuite(tests), sorted(skipped)


def _write_json(path, rec):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_last(counts, changed, repo=REPO, tier="full", timed_out=None):
    """Record a run's counts: full runs in logs/tests-last.json (engine/report.py reads it), fast runs in
    logs/tests-last-fast.json. counts: tests, failures, skipped."""
    rec = {"engine_version": (ENGINE / "VERSION").read_text(encoding="utf-8").strip(), "tier": tier,
           "tests": counts["tests"], "failures": counts["failures"], "skipped": counts["skipped"],
           "guard_ok": not changed, "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if timed_out:
        rec["timed_out"] = timed_out
    d = Path(repo) / "logs"
    d.mkdir(exist_ok=True)
    _write_json(d / LAST[tier], rec)
    return rec


def close_stdin():
    """Point standard input (file descriptor 0, inherited by child processes) at the null device."""
    fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(fd, 0)
    os.close(fd)
    sys.stdin = open(os.devnull, encoding="utf-8")


# ---------- child: runs the suite and reports where it is ----------

class HeartbeatResult(unittest.TextTestResult):
    """Writes the test it is starting, and the counts so far, to the heartbeat file."""
    heartbeat = None

    def startTest(self, test):
        try:
            _write_json(self.heartbeat, {"test": test.id(), "started": time.time(), "done": self.testsRun,
                                         "failures": len(self.failures) + len(self.errors)
                                         + len(self.unexpectedSuccesses), "skipped": len(self.skipped)})
        except OSError:
            pass  # the watcher is reading it; the next test writes again, and the run limit still applies
        super().startTest(test)


def child(argv):
    """--child HEARTBEAT RESULTS [--fast] [-v] [--start-dir DIR ...]: run the suite, write counts to RESULTS."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    close_stdin()
    heartbeat, results = Path(argv[argv.index("--child") + 1]), Path(argv[argv.index("--child") + 2])
    folders = [argv[i + 1] for i, a in enumerate(argv) if a == "--start-dir"] or None
    suite, skipped = collect("--fast" in argv, folders)
    HeartbeatResult.heartbeat = heartbeat
    result = unittest.TextTestRunner(verbosity=2 if "-v" in argv else 1, stream=sys.stderr,
                                     resultclass=HeartbeatResult).run(suite)
    _write_json(results, {"tests": result.testsRun, "skipped": len(result.skipped), "skipped_modules": skipped,
                          "failures": len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)})
    return 0


# ---------- watcher: starts the child, enforces the limits ----------

def kill_tree(proc):
    """Stop the child and every process it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def supervise(repo=REPO, fast=False, verbose=False, test_timeout=TEST_TIMEOUT, run_timeout=RUN_TIMEOUT,
              start_dirs=None, out=print, child_output=None):
    """Run the suite in a child under the guard and the limits; return (exit code, record written).
    child_output: where the child's test output goes (default: this terminal)."""
    tmp = Path(tempfile.mkdtemp(prefix="run-tests-"))
    heartbeat, results = tmp / "heartbeat.json", tmp / "results.json"
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child", str(heartbeat), str(results)]
    cmd += ["--fast"] * fast + ["-v"] * verbose
    for d in start_dirs or ():
        cmd += ["--start-dir", str(d)]
    timed_out, hb = None, None

    def run():
        nonlocal timed_out, hb
        start = time.time()
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=child_output, stderr=child_output,
                                start_new_session=os.name != "nt")
        while proc.poll() is None:
            time.sleep(POLL)
            hb = _read(heartbeat) or hb
            now = time.time()
            if now - start > run_timeout:
                timed_out = {"kind": "run", "test": (hb or {}).get("test"), "limit_s": run_timeout}
            elif hb and now - hb["started"] > test_timeout:
                timed_out = {"kind": "test", "test": hb["test"], "limit_s": test_timeout}
            if timed_out:
                kill_tree(proc)
                break
        return proc.returncode

    code, changed, n = guarded(run, repo)
    res = None if timed_out else _read(results)
    shutil.rmtree(tmp, ignore_errors=True)
    tier = "fast" if fast else "full"
    if timed_out:
        out(f"\nTIMEOUT: {timed_out['test'] or 'no test had started'} - the "
            + ("test ran" if timed_out["kind"] == "test" else "run ran")
            + f" over {timed_out['limit_s']} s. Stopped it and every process it started.")
        hb = hb or {}
        counts = {"tests": hb.get("done", 0) + (1 if hb.get("test") else 0),
                  "failures": hb.get("failures", 0) + 1, "skipped": hb.get("skipped", 0)}
    elif res is None or code != 0:
        out(f"\nFAIL: the test process ended without a result (exit code {code}).")
        counts = {"tests": 0, "failures": 1, "skipped": 0}
    else:
        counts = res
    if fast:
        out(f"\nTier: FAST (for use during work; skipped full-tier modules: {', '.join((res or {}).get('skipped_modules') or []) or 'none'}). "
            "Run the full suite before every commit and in every Check.")
    else:
        out("\nTier: FULL")
    out(f"Guard: {n} file(s) under {', '.join(GUARDED)} fingerprinted before and after the run.")
    if changed:
        out("FAIL: the test run changed real repo files:")
        for c in changed:
            out(f"  - {c}")
    else:
        out("Guard OK: no real log, job or mode file changed.")
    rec = write_last(counts, changed, repo, tier, timed_out)
    if timed_out:
        return 2, rec
    return (0 if counts["failures"] == 0 and not changed else 1), rec


def _seconds(argv, flag, default):
    if flag not in argv:
        return default
    try:
        value = float(argv[argv.index(flag) + 1])
    except (IndexError, ValueError):
        raise SystemExit(f"{flag} needs a number of seconds")
    if value <= 0:
        raise SystemExit(f"{flag} must be more than 0")
    return value


def main(argv):
    if "--child" in argv:
        return child(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    close_stdin()
    os.environ.pop("LAB_ROOT", None)  # a stray LAB_ROOT must not redirect the guard
    code, _ = supervise(fast="--fast" in argv, verbose="-v" in argv,
                        test_timeout=_seconds(argv, "--test-timeout", TEST_TIMEOUT),
                        run_timeout=_seconds(argv, "--timeout", RUN_TIMEOUT))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
