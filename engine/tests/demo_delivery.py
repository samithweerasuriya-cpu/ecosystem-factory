#!/usr/bin/env python3
"""Watch one demo job go from NEW to DONE with stand-in agents (T0.10), in a temporary copy of the repo.

  python engine/tests/demo_delivery.py

Nothing in the real repo is touched. The approval is done in-process here, the way a test does it;
on a real job the approver runs engine/gate.py approve <job> in their own terminal.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent.parent


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tmp = Path(tempfile.mkdtemp(prefix="demo-delivery-"))
    try:
        for d in ("engine", "config", "schemas", "rules"):
            shutil.copytree(REPO / d, tmp / d, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.local.json"))
        os.environ["LAB_ROOT"] = str(tmp)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        sys.path[:0] = [str(TESTS), str(tmp / "engine")]
        import demo_support as ds
        import labcore as lc
        ds.prepare_root(tmp)
        server, base = ds.start_pages()
        d = ds.Driver(tmp, base)
        d.new()
        ds.main_path_to_gate(d)
        lc.approve_gate(d.job, "demo")
        d.note("approve (in-process)")
        ds.deliver_and_finish(d)
        server.shutdown()
        print(f"Demo job {d.job}\n")
        print(f"{'step':<22}{'state':<16}stage")
        for what, state, stage in d.trail:
            print(f"{what:<22}{state:<16}{stage or '-'}")
        print()
        print("\n".join(lc.usage_summary(d.job)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
