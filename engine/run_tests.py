#!/usr/bin/env python3
"""Run every engine test, then prove the run left the real repo's logs, jobs and mode untouched.

  python engine/run_tests.py [-v]

Tests run against temporary copies (LAB_ROOT). This runner fingerprints every file under
logs/, jobs/ and .lab/ of the real repo before and after the suite and fails if anything
was added, changed or removed. The guard itself is tested against a fake repo
(engine/tests/test_run_tests.py). Exit 0 = all tests passed and nothing changed.
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


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.pop("LAB_ROOT", None)  # a stray LAB_ROOT must not redirect the guard
    tests = ENGINE / "tests"
    sys.path.insert(0, str(tests))
    suite = unittest.defaultTestLoader.discover(str(tests), top_level_dir=str(tests))
    result, changed, n = guarded_run(suite, verbosity=2 if "-v" in argv else 1)
    print(f"\nGuard: {n} file(s) under {', '.join(GUARDED)} fingerprinted before and after the run.")
    if changed:
        print("FAIL: the test run changed real repo files:")
        for c in changed:
            print(f"  - {c}")
    else:
        print("Guard OK: no real log, job or mode file changed.")
    return 0 if result.wasSuccessful() and not changed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
