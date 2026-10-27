#!/usr/bin/env python3
"""Run every engine test, then prove the run left the real repo's logs, jobs and mode untouched.

  python engine/run_tests.py [-v]            # FULL: before every commit and in every Check
  python engine/run_tests.py --fast [-v]     # FAST: during work (skips modules with TIER = "full")

Tests run against temporary copies (LAB_ROOT). This runner fingerprints every file under
logs/, jobs/ and .lab/ of the real repo before and after the suite and fails if anything
was added, changed or removed. The guard itself is tested against a fake repo
(engine/tests/test_run_tests.py). Exit 0 = all tests passed and nothing changed.
Keyboard input is closed first (T1.3 follow-up): the runner and every process a test starts read an empty
input, so no test can wait on the keyboard in a real terminal (it behaves as with `$null |` piped in).
"""
import hashlib
import os
import sys
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
REPO = ENGINE.parent
GUARDED = ("logs", "jobs", ".lab")


def fingerprint(repo=REPO):
    out = {}
    for top in GUARDED:
        base = Path(repo) / top
        if base.exists():
            for f in sorted(p for p in base.rglob("*") if p.is_file()):
                out[f.relative_to(repo).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def guarded_run(suite, repo=REPO, verbosity=1, stream=None):
    """Run suite; return (result, changed paths, number of files fingerprinted)."""
    before = fingerprint(repo)
    result = unittest.TextTestRunner(verbosity=verbosity, stream=stream or sys.stderr).run(suite)
    after = fingerprint(repo)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    return result, changed, len(before)


def _walk(suite):
    for t in suite:
        yield from (_walk(t) if isinstance(t, unittest.TestSuite) else [t])


def collect(fast=False):
    """(suite, skipped full-tier module names). Engine tests, plus the repo's own tests/ if present.
    --fast skips modules that declare TIER = "full" (the slow end-to-end suites)."""
    suites = []
    for folder in (ENGINE / "tests", REPO / "tests"):
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


def close_stdin():
    """Point standard input (file descriptor 0, inherited by child processes) at the null device."""
    fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(fd, 0)
    os.close(fd)
    sys.stdin = open(os.devnull, encoding="utf-8")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    close_stdin()
    os.environ.pop("LAB_ROOT", None)  # a stray LAB_ROOT must not redirect the guard
    fast = "--fast" in argv
    suite, skipped = collect(fast)
    result, changed, n = guarded_run(suite, verbosity=2 if "-v" in argv else 1)
    if fast:
        print(f"\nTier: FAST (for use during work; skipped full-tier modules: {', '.join(skipped) or 'none'}). "
              "Run the full suite before every commit and in every Check.")
    else:
        print("\nTier: FULL")
    print(f"Guard: {n} file(s) under {', '.join(GUARDED)} fingerprinted before and after the run.")
    if changed:
        print("FAIL: the test run changed real repo files:")
        for c in changed:
            print(f"  - {c}")
    else:
        print("Guard OK: no real log, job or mode file changed.")
    return 0 if result.wasSuccessful() and not changed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
