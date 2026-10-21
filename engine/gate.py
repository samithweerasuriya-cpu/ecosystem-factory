#!/usr/bin/env python3
"""HUMAN-ONLY gate tool. The approver runs this in their own terminal, never via Claude Code.

  python engine/gate.py show <job>                      # what is waiting for approval
  python engine/gate.py approve <job> [--note TEXT]     # writes gate token bound to artifact hash
  python engine/gate.py reject <job> --feedback TEXT    # sends job back to REVISING
  python engine/gate.py verify <job> <gate>             # exit 0 if token valid
  python engine/gate.py lock | unlock                   # operate mode on/off (protects framework files)

approve/reject/lock/unlock refuse to run without an interactive terminal.
The approver's name comes from config/gates.json (fallback: the OS user name).
Claude Code is also blocked from calling this file by settings.json and the hook.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labcore as lc  # noqa: E402


def confirm(job_or_word):
    if not sys.stdin.isatty():
        print("Refusing: no interactive terminal. Run this yourself.", file=sys.stderr)
        sys.exit(1)
    typed = input(f"Type '{job_or_word}' to confirm: ").strip()
    if typed != job_or_word:
        print("Not confirmed.", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("job")
    a = sub.add_parser("approve"); a.add_argument("job"); a.add_argument("--note", default="")
    r = sub.add_parser("reject"); r.add_argument("job"); r.add_argument("--feedback", required=True)
    v = sub.add_parser("verify"); v.add_argument("job"); v.add_argument("gate")
    sub.add_parser("lock"); sub.add_parser("unlock")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "show":
            st = lc.load_state(args.job)
            d = lc.job_dir(args.job)
            print(f"Job:      {args.job}\nState:    {st['state']}\nGate:     {st['route']['gate']}")
            print(f"Artifact: {st['artifact_path']}")
            if st["artifact_path"]:
                print(f"SHA256:   {lc.sha256_path(st['artifact_path'])}")
            for f in sorted((d / "reviews").glob("*")):
                print(f"Review:   {lc.rel(f)}")
        elif args.cmd == "approve":
            confirm(args.job); st = lc.approve_gate(args.job, args.note)
            lc.gate_audit("approve", args.job, note=args.note)
            print(f"Approved {st['route']['gate']} for {args.job}. State: {st['state']}")
        elif args.cmd == "reject":
            confirm(args.job)
            try:
                st = lc.reject_gate(args.job, args.feedback)
            except lc.CapExceeded:  # rejection was recorded and the job escalated: audit it too
                lc.gate_audit("reject", args.job, feedback=args.feedback, cap_exceeded=True)
                raise
            lc.gate_audit("reject", args.job, feedback=args.feedback)
            print(f"Rejected. State: {st['state']}")
        elif args.cmd == "verify":
            ok, why = lc.verify_gate(args.job, args.gate); print(why); return 0 if ok else 1
        elif args.cmd == "lock":
            confirm("lock"); lc.LAB.mkdir(exist_ok=True); (lc.LAB / "OPERATE").write_text(lc.now())
            lc.gate_audit("lock")
            print("Operate mode ON: framework files are write-protected.")
        elif args.cmd == "unlock":
            confirm("unlock"); (lc.LAB / "OPERATE").unlink(missing_ok=True)
            lc.gate_audit("unlock")
            print("Operate mode OFF: Claude Code may edit framework files (build mode).")
    except lc.CapExceeded as ex:
        print(f"PAUSED: {ex}", file=sys.stderr); return 3
    except lc.LabError as ex:
        print(f"ERROR: {ex}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
