#!/usr/bin/env python3
"""HUMAN-ONLY gate tool. The approver runs this in their own terminal, never via Claude Code.

  python engine/gate.py show <job>                      # the gate brief (what is waiting for approval)
  python engine/gate.py approve <job> [--as pilot] [--note TEXT]   # gate token bound to the artifact hash
  python engine/gate.py reject <job> --feedback TEXT    # sends job back to REVISING
  python engine/gate.py hold <job> --note TEXT          # parks the job (ESCALATED, not a rejection)
  python engine/gate.py resume <job>                    # restarts a held or paused job
  python engine/gate.py verify <job> <gate> [--chain]   # exit 0 if the token (or the whole chain) is valid
  python engine/gate.py relink <job>                    # point a stopped child at its parent's new approval
  python engine/gate.py lock | unlock                   # operate mode on/off (protects framework files)
  python engine/gate.py ceiling <job> [--tokens N] [--minutes M]   # raise a job's usage ceiling
  python engine/gate.py readiness-override <job> --reason TEXT   # write the charter below the readiness threshold

approve/reject/hold/resume/lock/unlock/readiness-override refuse to run without an interactive terminal.
approve, reject and hold record your active minutes on the decision (T2.4): --minutes N, or asked; 'skip' is
recorded as unknown, never as 0. readiness-override (T2.4) is refused when stage 0 failed (never overridden);
it is audited with its reason and the score at the time, and the gate brief then reads "Readiness: override".
approve, reject and hold print the gate brief; approve and reject ask for a mark on every blocker and
major finding and on a sample of the minors (one letter and Enter each: v valid, n noise, s skip, q cancel), then
for any missed issues; the brief shown and the verdicts are saved in the job's gates/ folder
(engine/gatereview.py, T0.16).
lock also refuses unless passing evaluation reports cover the current agents, rules, schemas and
config, for the pinned model and the installed CLI (engine/evalcheck.py, T0.13), and refuses on any
doctor FAIL (engine/doctor.py fast checks, T0.14).
The approver's name comes from config/gates.json; without it every gate action is refused.
Claude Code is also blocked from calling this file by settings.json and the hook.
"""
import argparse
import re
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


def require_terminal():
    if not interactive_terminal():
        print("Refusing: no interactive terminal. Run this yourself.", file=sys.stderr)
        sys.exit(1)


SEVERITIES = ("blocker", "major", "minor")


def read_key(prompt, allowed, severity=False):
    """One letter, then Enter; anything else asks again. Ctrl+C or closed input = q. With severity=True,
    'v' may be followed by a corrected severity ('v major'), returned as typed ('v major').
    Plain line input on purpose: a no-Enter keypress reader behaved differently across terminals and
    left stray keys that answered the next question (found live, T0.16)."""
    while True:
        try:
            ch = " ".join(input(prompt + " ").strip().lower().split())
        except (EOFError, KeyboardInterrupt):
            return "q"
        if len(ch) == 1 and ch in allowed:
            return ch
        if severity and ch.startswith("v ") and ch[2:] in SEVERITIES:
            return ch
        print(f"  type one of: {', '.join(allowed)}" + (" (or v plus a severity, e.g. v major)" if severity else "")
              + ", then Enter")


def mark_findings(job):
    """Ask for a mark on every blocker and major, and on the sampled minors. None if cancelled (q)."""
    import gatereview as gr
    must, sampled, minors = gr.to_mark(job)
    marks = []
    if must or sampled:
        print(f"\nMark each finding with one letter and Enter: v valid, n noise"
              f"{', s skip (minors only)' if sampled else ''}, q cancel (nothing is recorded). A valid finding "
              "with the wrong severity: v and the right one (e.g. v major).")
    for f, keys in [(f, "vnq") for f in must] + [(f, "vnsq") for f in sampled]:
        k = read_key(f"  {f['finding_id']} [{f['severity']} {f['rule']}] {f['reviewer']} {f['version']} "
                     f"{f['location']}: {f['issue']}\n    mark ({'/'.join(keys)}):", keys, severity=True)
        if k == "q":
            return None
        corrected = k.split()[1] if " " in k else None
        marks.append({k2: f[k2] for k2 in ("file", "reviewer", "version", "finding_id", "rule", "severity")}
                     | {"mark": gr.MARKS[k[0]], "sampled": f["severity"] == "minor",
                        "corrected_severity": corrected if corrected != f["severity"] else None})
    return marks, [m["finding_id"] for m in marks if m["sampled"]], minors


def ask_missed(job):
    """Missed issues: a rule ID and one line each, until an empty rule ID. None if cancelled."""
    import gatereview as gr
    import validate_findings as vf
    out = []
    while True:
        try:
            rule = input("Missed issue? Rule ID the reviewers should have applied (Enter: none, q: cancel): ").strip().upper()
        except EOFError:
            return None
        if not rule:
            return out
        if rule == "Q":
            return None
        if not re.fullmatch(vf.RULE_ID, rule):
            print("  not a rule ID (e.g. CC01)")
            continue
        try:
            text = input("  One line: what should have been caught: ").strip()
        except EOFError:
            return None
        if not text:
            print("  a description is needed")
            continue
        names = gr.reviewers_for_rule(rule)
        if len(names) > 1:
            k = read_key("  Which reviewer missed it? " + ", ".join(f"{i + 1} {n}" for i, n in enumerate(names)) + ":",
                         [str(i + 1) for i in range(len(names))] + ["q"])
            if k == "q":
                return None
            reviewer = names[int(k) - 1]
        else:
            reviewer = names[0] if names else "unassigned"
        out.append({"rule": rule, "reviewer": reviewer, "description": text})
        print(f"  recorded missed issue {len(out)}: {rule} ({reviewer}). Next rule ID, or Enter to finish.")


def decide(args):
    """approve, reject or hold: brief, marks, missed issues, confirmation, then the records."""
    import gatereview as gr
    lc.approver()
    require_terminal()
    st = lc.load_state(args.job)
    if st["state"] != "GATE":
        raise lc.LabError(f"{args.job} is {st['state']}, not GATE")
    lc.gate_mode(st["route"]["gate"])
    text = gr.brief(args.job)
    print(text)
    marks, sampled, minors, missed = [], [], 0, []
    if args.cmd != "hold":
        got = mark_findings(args.job)
        missed = ask_missed(args.job) if got is not None else None
        if got is None or missed is None:
            print("Cancelled: nothing was recorded.", file=sys.stderr)
            return 1
        marks, sampled, minors = got
        counts = {m: sum(1 for x in marks if x["mark"] == m) for m in ("valid", "noise", "skipped")}
        print(f"\nTo be recorded: {len(marks)} mark(s) ({counts['valid']} valid, {counts['noise']} noise, "
              f"{counts['skipped']} skipped) and {len(missed)} missed issue(s)"
              + (": " + ", ".join(f"{x['rule']} ({x['reviewer']})" for x in missed) if missed else "")
              + ". Type the job ID to confirm, or anything else to cancel.")
    minutes = ask_minutes(args.minutes)
    confirm(args.job)
    files, review = gr.record(args.job, args.cmd, text, marks, missed, sampled, minors)
    if args.cmd == "approve":
        note = f"[pilot] {args.note}".strip() if args.as_ == "pilot" else args.note
        st = lc.approve_gate(args.job, note, review=review)
        gr.write(files, args.job)
        m = lc.record_minutes(args.job, "approve", minutes)
        lc.gate_audit("approve", args.job, note=note, review=review, minutes=m)
        print(f"Approved {st['route']['gate']} for {args.job}. State: {st['state']}")
    elif args.cmd == "reject":
        try:
            st = lc.reject_gate(args.job, args.feedback)
        except lc.CapExceeded:  # rejection was recorded and the job escalated: record and audit it too
            gr.write(files, args.job)
            m = lc.record_minutes(args.job, "reject", minutes)
            lc.gate_audit("reject", args.job, feedback=args.feedback, review=review, cap_exceeded=True, minutes=m)
            raise
        gr.write(files, args.job)
        m = lc.record_minutes(args.job, "reject", minutes)
        lc.gate_audit("reject", args.job, feedback=args.feedback, review=review, minutes=m)
        print(f"Rejected. State: {st['state']}")
    else:
        st = lc.hold_gate(args.job, args.note)
        gr.write(files, args.job)
        m = lc.record_minutes(args.job, "hold", minutes)
        lc.gate_audit("hold", args.job, note=args.note, brief_sha256=review["brief_sha256"], brief=review["brief"],
                      minutes=m)
        print(f"Held at {st['route']['gate']}: {args.job} is ESCALATED until: python engine/gate.py resume {args.job}")
    return 0


def ask_minutes(given):
    """T2.4: the approver's active minutes on this decision: --minutes, or asked here; 'skip' is unknown."""
    value, tries = given, 0
    while value is None:
        if tries == 3:
            print("No valid minutes after 3 tries: nothing was recorded.", file=sys.stderr)
            sys.exit(1)
        tries += 1
        try:
            value = input("Active minutes you spent on this decision (a number, or skip): ").strip()
        except EOFError:
            print("Refusing: no interactive terminal (input closed). Run this yourself.", file=sys.stderr)
            sys.exit(1)
        try:
            lc.minutes_fields(value, "gate.py")
        except lc.LabError as e:
            print(e, file=sys.stderr)
            value = None
    lc.minutes_fields(value, "gate.py")      # a bad --minutes stops here, before anything is recorded
    return value


def override_readiness(args):
    """readiness-override: the approver lets the charter be written below the readiness threshold."""
    import readiness
    lc.approver()
    require_terminal()
    rep = readiness.latest_report(args.job)
    if rep:
        print(f"Readiness of {args.job}: {rep.get('score')} of {len(readiness.CRITERIA)} "
              f"(threshold {rep.get('threshold')}), result {rep.get('result')}")
        for c in rep.get("criteria", []):
            if not c["passed"]:
                print(f"  not met: {c['n']}. {c['text']}")
                for p in c["problems"][:5]:
                    print(f"     - {p}")
    confirm(args.job)
    rec = readiness.record_override(args.job, args.reason)
    lc.gate_audit("readiness-override", args.job, reason=rec["reason"], score=rec["score"],
                  threshold=rec["threshold"], failed=rec["failed"], report=rec["report"])
    print(f"Readiness override recorded for {args.job} (score {rec['score']} of {len(readiness.CRITERIA)}). "
          "The next readiness run passes as 'override'.")
    return 0


def confirm(job_or_word):
    require_terminal()
    try:
        typed = input(f"Type '{job_or_word}' to confirm: ").strip()
    except EOFError:
        print("Refusing: no interactive terminal (input closed). Run this yourself.", file=sys.stderr)
        sys.exit(1)
    if typed != job_or_word:
        print(f"Not confirmed: you typed {typed!r}, expected {job_or_word!r}. Nothing was recorded.", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("job")
    a = sub.add_parser("approve"); a.add_argument("job"); a.add_argument("--note", default="")
    a.add_argument("--as", dest="as_", choices=["pilot"], help="approve as a pilot (recorded in the note)")
    r = sub.add_parser("reject"); r.add_argument("job"); r.add_argument("--feedback", required=True)
    h = sub.add_parser("hold"); h.add_argument("job"); h.add_argument("--note", required=True)
    for p in (a, r, h):
        p.add_argument("--minutes", help="your active minutes on this decision, or 'skip' (asked when absent)")
    ro = sub.add_parser("readiness-override"); ro.add_argument("job"); ro.add_argument("--reason", required=True)
    rs = sub.add_parser("resume"); rs.add_argument("job")
    v = sub.add_parser("verify"); v.add_argument("job"); v.add_argument("gate"); v.add_argument("--chain", action="store_true")
    rl = sub.add_parser("relink"); rl.add_argument("job")
    sub.add_parser("lock"); sub.add_parser("unlock")
    c = sub.add_parser("ceiling"); c.add_argument("job"); c.add_argument("--tokens", type=int)
    c.add_argument("--minutes", type=float)
    args = ap.parse_args(argv)
    try:
        if args.cmd in ("approve", "reject", "hold"):
            return decide(args)
        if args.cmd == "readiness-override":
            return override_readiness(args)
        if args.cmd == "resume":
            confirm(args.job)
            st = lc.apply(args.job, "resume", actor=lc.approver(), _human=True)
            lc.gate_audit("resume", args.job)
            print(f"Resumed {args.job}. State: {st['state']}")
            return 0
        if args.cmd == "show" and lc.load_state(args.job)["state"] == "GATE":
            import gatereview as gr
            print(gr.brief(args.job))
            return 0
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
