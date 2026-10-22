#!/usr/bin/env python3
"""HUMAN-ONLY gate tool. The approver runs this in their own terminal, never via Claude Code.

  python engine/gate.py show <job>                      # what is waiting for approval
  python engine/gate.py approve <job> [--note TEXT]     # writes gate token bound to artifact hash
  python engine/gate.py reject <job> --feedback TEXT    # sends job back to REVISING
  python engine/gate.py verify <job> <gate> [--chain]   # exit 0 if the token (or the whole chain) is valid
  python engine/gate.py relink <job>                    # point a stopped child at its parent's new approval
  python engine/gate.py lock | unlock                   # operate mode on/off (protects framework files)
  python engine/gate.py ceiling <job> [--tokens N] [--minutes M]   # raise a job's usage ceiling

approve/reject/lock/unlock refuse to run without an interactive terminal.
lock also refuses unless passing evaluation reports cover the current agents, rules, schemas and
config, for the pinned model and the installed CLI (engine/evalcheck.py, T0.13), and refuses on any
doctor FAIL (engine/doctor.py fast checks, T0.14).
The approver's name comes from config/gates.json; without it every gate action is refused.
Claude Code is also blocked from calling this file by settings.json and the hook.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labcore as lc  # noqa: E402


def interactive_terminal():
    """True only for a real interactive console. On Windows, isatty() is also true for the NUL
    device, so the console itself is asked (GetConsoleMode succeeds only for console input)."""
    if not sys.stdin.isatty():
        return False
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        try:
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        except OSError:
            return False
        mode = ctypes.c_uint32()
        return bool(ctypes.windll.kernel32.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode)))
    return True


def doctor_failures():
    """The doctor's FAIL lines (engine/doctor.py fast checks, no Claude calls); empty means none."""
    import doctor
    return doctor.failures()


def eval_lock_problems():
    """Why operate mode may not be locked (engine/evalcheck.py); empty means it may."""
    import evalcheck
    return evalcheck.lock_problems()


def confirm(job_or_word):
    if not interactive_terminal():
        print("Refusing: no interactive terminal. Run this yourself.", file=sys.stderr)
        sys.exit(1)
    try:
        typed = input(f"Type '{job_or_word}' to confirm: ").strip()
    except EOFError:
        print("Refusing: no interactive terminal (input closed). Run this yourself.", file=sys.stderr)
        sys.exit(1)
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
    v = sub.add_parser("verify"); v.add_argument("job"); v.add_argument("gate"); v.add_argument("--chain", action="store_true")
    rl = sub.add_parser("relink"); rl.add_argument("job")
    sub.add_parser("lock"); sub.add_parser("unlock")
    c = sub.add_parser("ceiling"); c.add_argument("job"); c.add_argument("--tokens", type=int)
    c.add_argument("--minutes", type=float)
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
            if st["state"] == "GATE":  # exactly what an approval would bind
                try:
                    bf = lc.built_from(st)
                except lc.LabError as e:
                    print(f"Built from: NOT APPROVABLE: {e}")
                else:
                    for link in bf["links"]:
                        print(f"Built from: {link['kind']} {link['job']}/{link['gate']}  approved content {link['artifact_sha256']}")
                    for i in bf["inputs"]:
                        print(f"Input:    {i['id']} {i['path']}  {i['sha256']}")
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
            if args.chain:
                ok, chain = lc.verify_chain(args.job, args.gate)
                for c in chain:
                    print(f"{'  ' * c['level']}{c['job']} [{c['kind']}] {c['path'] or ''}  recorded {(c['recorded'] or '-')[:12]}"
                          f"  current {(c['current'] or '-')[:12]}  {c['status']}")
                print("chain OK" if ok else "chain BROKEN")
                return 0 if ok else 1
            ok, why = lc.verify_gate(args.job, args.gate); print(why); return 0 if ok else 1
        elif args.cmd == "relink":
            confirm(args.job); st = lc.relink(args.job)
            lc.gate_audit("relink", args.job, parent_link=st.get("parent_link"))
            print(f"Relinked {args.job} to its parent's current approval. State: {st['state']} ({st['stage']})")
        elif args.cmd == "ceiling":
            if args.tokens is None and args.minutes is None:
                print("ceiling needs --tokens and/or --minutes", file=sys.stderr); return 1
            confirm(args.job); st = lc.set_ceiling(args.job, args.tokens, args.minutes, _human=True)
            lc.gate_audit("ceiling", args.job, ceiling=st["ceiling"])
            print(f"Usage ceiling for {args.job}: {st['ceiling']}. Resume the job when ready.")
        elif args.cmd == "lock":
            lc.approver()  # refuse before anything changes (no unaudited lock)
            confirm("lock")
            failed = doctor_failures()
            if failed:
                print("Refusing to lock: the doctor found failures (python engine/doctor.py).", file=sys.stderr)
                for p in failed:
                    print(f"  - {p}", file=sys.stderr)
                return 1
            problems = eval_lock_problems()
            if problems:
                print("Refusing to lock: the evaluations don't cover the current framework files.", file=sys.stderr)
                for p in problems:
                    print(f"  - {p}", file=sys.stderr)
                return 1
            lc.LAB.mkdir(exist_ok=True); (lc.LAB / "OPERATE").write_text(lc.now())
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
