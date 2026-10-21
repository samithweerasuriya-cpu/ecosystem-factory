#!/usr/bin/env python3
"""Check the evidence registries against the stored copies (ported from the author's earlier
private lab, now over engine/evidence.py).

Every stored entry must have its cached copy with a matching fingerprint, and ids must be unique
(exit 1 otherwise). Cached files no entry references are reported as orphans (warning only).
  python engine/registry_check.py [<job> ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence  # noqa: E402


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    jobs = argv if argv else None
    problems, orphans = evidence.check_registry(jobs)
    print(f"problems: {len(problems)}  orphans: {len(orphans)}")
    for p in problems:
        print(p)
    for o in orphans:
        print(f"ORPHAN   {o} (no registry entry)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
