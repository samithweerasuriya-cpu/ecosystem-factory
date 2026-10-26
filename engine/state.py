#!/usr/bin/env python3
"""Orchestrator CLI for job state. The ONLY way agents change job state.

  python engine/state.py new <type> <slug> "<goal>" --class synthetic|public|internal [--parent JOB] [--continue-from JOB]
  python engine/state.py event <job> <event> [--artifact PATH] [--note TEXT] [--reason R] [--questions FILE]
  python engine/state.py handoff <job> [--item ID] [--json]  # build the handoff for the next agent call
  python engine/state.py call <job> <agent> [--item ID]   # count an agent invocation (opens it)
  python engine/state.py result <job> <call> done|failed [--usage-json FILE] [--note TEXT]
                                                           # close a call (in-session: the post hook does it)
  python engine/state.py usage <job>                       # usage per job and agent
  python engine/state.py input <job> <file|-> --class synthetic|public|internal [--note TEXT]
  python engine/state.py fanout <job> <item> [<item> ...]  # fix the fan-out item list (once per stage)
  python engine/state.py fanout-result <job> <item> done|failed [--note TEXT]
  python engine/state.py run <job>                         # run the current script stage
  python engine/state.py activate <job>                    # set active job (used by the hook)
  python engine/state.py status [<job>]
  python engine/state.py routes                            # print routes (validated)
  python engine/state.py check-config                      # validate routes, caps, scripts and gate modes
  python engine/state.py quality [--reviewer R] [--rule ID]  # noise and miss rates from gate marks
  python engine/state.py stage-record <job>                # stage one job's folder and log lines (publish-checked)
  python engine/state.py check-private <job>               # internal job: nothing of it can reach a commit

Events: dispatch, stage_done, artifact_ready, fixed, infra_error, repair (--reason invalid_output|
severity_directive), needs_input (--questions FILE), answered, review_pass, review_fail, revised,
deliver, complete, block, escalate, cancel, resume.
Every job has a class, set at creation. Synthetic and public jobs live in jobs/<job>/; internal
jobs live entirely in private/jobs/<job>/ (untracked). Inputs are stored verbatim in the job's own
inputs/ folder and may not exceed the job's class.
(approve/reject are human-only: engine/gate.py; script_fail is recorded only by 'run'.)
Exit codes: 0 ok, 1 error, 3 cap exceeded (job paused; tell the approver), 4 script stage failed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labcore as lc  # noqa: E402


def summary(st):
    c = st["counters"]
    return (f"{st['job_id']}  state={st['state']}  stage={st['stage']}  "
            f"artifact={st['artifact_path']}  revisions={c['total_revisions']}  "
            f"calls={c['agent_calls']}  gate={st['route']['gate']}")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("type"); n.add_argument("slug"); n.add_argument("goal"); n.add_argument("--parent"); n.add_argument("--continue-from")
    n.add_argument("--class", dest="cls", required=True, choices=["synthetic", "public", "internal"])
    e = sub.add_parser("event"); e.add_argument("job"); e.add_argument("event"); e.add_argument("--artifact"); e.add_argument("--note")
    e.add_argument("--reason"); e.add_argument("--questions")
    h = sub.add_parser("handoff"); h.add_argument("job"); h.add_argument("--item"); h.add_argument("--json", action="store_true")
    i = sub.add_parser("input"); i.add_argument("job"); i.add_argument("file")
    i.add_argument("--class", dest="cls", required=True, choices=["synthetic", "public", "internal"]); i.add_argument("--note")
    c = sub.add_parser("call"); c.add_argument("job"); c.add_argument("agent"); c.add_argument("--item")
    f = sub.add_parser("fanout"); f.add_argument("job"); f.add_argument("items", nargs="+")
    fr = sub.add_parser("fanout-result"); fr.add_argument("job"); fr.add_argument("item")
    fr.add_argument("status", choices=["done", "failed"]); fr.add_argument("--note")
    r = sub.add_parser("run"); r.add_argument("job")
    rs = sub.add_parser("result"); rs.add_argument("job"); rs.add_argument("call")
    rs.add_argument("status", choices=["done", "failed"]); rs.add_argument("--usage-json"); rs.add_argument("--note")
    us = sub.add_parser("usage"); us.add_argument("job")
    qu = sub.add_parser("quality"); qu.add_argument("--reviewer"); qu.add_argument("--rule")
    sr = sub.add_parser("stage-record"); sr.add_argument("job")
    a = sub.add_parser("activate"); a.add_argument("job")
    s = sub.add_parser("status"); s.add_argument("job", nargs="?")
    sub.add_parser("routes"); sub.add_parser("check-config")
    cp = sub.add_parser("check-private"); cp.add_argument("job")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "new":
            st = lc.new_job(args.type, args.slug, args.goal, args.parent, continue_from=args.continue_from, cls=args.cls)
            lc.set_active(st["job_id"])
            print(summary(st))
        elif args.cmd == "event":
            print(summary(lc.apply(args.job, args.event, artifact=args.artifact, note=args.note,
                                   reason=args.reason, questions=args.questions)))
        elif args.cmd == "handoff":
            h, text = lc.handoff(args.job, args.item)
            print(json.dumps(h, indent=2) if args.json else text.rstrip("\n"))
        elif args.cmd == "input":
            data = sys.stdin.buffer.read() if args.file == "-" else None
            st, rec = lc.record_input(args.job, args.file, args.cls, args.note, data=data)
            print(f"recorded {rec['id']} ({rec['class']}): {rec['path']}")
        elif args.cmd == "call":
            print(summary(lc.record_call(args.job, args.agent, item=args.item)))
        elif args.cmd == "fanout":
            print(summary(lc.set_fanout(args.job, args.items)))
        elif args.cmd == "fanout-result":
            print(summary(lc.fanout_result(args.job, args.item, args.status, args.note)))
        elif args.cmd == "run":
            st, rec = lc.run_script(args.job)
            ok = rec["exit_code"] == 0
            print(f"script {rec['script']}: {'passed' if ok else 'FAILED'} (exit={rec['exit_code']}, "
                  f"timed_out={rec['timed_out']}, {rec['duration_s']}s)")
            print(summary(st))
            return 0 if ok else 4
        elif args.cmd == "result":
            usage = None
            if args.usage_json:  # a headless `claude -p --output-format json` result
                d = lc.load_json(args.usage_json)
                models = list((d.get("modelUsage") or {}).keys())
                usage = lc.usage_from_tokens(d.get("usage"), duration_ms=d.get("duration_ms"),
                                             model=models[0] if len(models) == 1 else (", ".join(models) or None),
                                             cost_usd=d.get("total_cost_usd"))
            st, over = lc.record_result(args.job, args.call, args.status, usage=usage,
                                        source="headless" if usage else "manual", note=args.note)
            print(f"recorded {args.call}: {args.status}" + ("" if usage else " (usage unknown)"))
            if over:
                print(f"PAUSED: {over}", file=sys.stderr)
                return 3
        elif args.cmd == "usage":
            print("\n".join(lc.usage_summary(args.job)))
        elif args.cmd == "stage-record":   # T0.19: one job's folder and log lines, after the publish check
            import stagerecord
            files, logs = stagerecord.stage(args.job)
            print(f"staged {len(files)} file(s) of {args.job}"
                  + "".join(f"; {n} line(s) of {p}" for p, n in logs.items()) + " (commit when ready)")
        elif args.cmd == "quality":   # T0.16: reviewer noise and miss rates from the approver's marks
            import gatereview
            print(gatereview.quality_text(args.reviewer, args.rule))
        elif args.cmd == "activate":
            lc.set_active(args.job); print(f"active job: {args.job}")
        elif args.cmd == "status":
            if args.job:
                print(json.dumps(lc.load_state(args.job), indent=2))
            else:
                for st in lc.all_jobs():
                    print(summary(st))
                print(f"active: {lc.active_job()}")
        elif args.cmd == "routes":
            print(json.dumps(lc.routes(), indent=2))
        elif args.cmd == "check-private":
            leaks = lc.private_leaks(args.job)
            for leak in leaks:
                print(f"LEAK {leak}")
            print("private OK: nothing of this job can reach a commit" if not leaks else f"{len(leaks)} leak(s)")
            return 1 if leaks else 0
        elif args.cmd == "check-config":
            errs = lc.route_errors(lc.load_json(lc.CONFIG / "routes.json")) + lc.gate_config_errors()
            for err in errs:
                print(f"INVALID {err}")
            print("config OK" if not errs else f"{len(errs)} problem(s)")
            return 1 if errs else 0
    except lc.CapExceeded as ex:
        print(f"PAUSED: {ex}", file=sys.stderr)
        return ex.code
    except lc.LabError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return ex.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
