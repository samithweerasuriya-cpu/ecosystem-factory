"""Stand-in agents for the demo route (T0.10), shared by the delivery tests and demo_delivery.py.

A stand-in plays one subagent call the way the Orchestrator will run a real one: build the scripted
handoff (state.py handoff), open the call (state.py call), write a prepared output into the handoff's
OUTPUT_DIR (the Write is first put to the PreToolUse hook as a subagent call), fetch sources through
the evidence module if asked, and hand back app-style usage figures, which the real PostToolUse hook
records. Everything goes through the command-line tools and the hook launchers; nothing writes
state directly."""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

PAGES = {
    "north": "The north region ships 120 orders per day on average.",
    "south": "The south region ships 80 orders per day on average.",
    "east": "The east region ships 95 orders per day on average.",
}
FILLER = " Background notes on regional order handling and seasonal patterns." * 12
TOKENS = {"demo-planner": 1000, "demo-researcher": 2000, "demo-writer": 3000, "demo-critic": 1500,
          "demo-verifier": 1500, "demo-publisher": 500}


class _Pages(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        key = self.path.strip("/")
        if key not in PAGES:
            self.send_response(404); self.end_headers(); return
        body = f"<html><head><title>{key} region</title></head><body><p>{PAGES[key]}</p><p>{FILLER}</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):
        pass


def start_pages():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Pages)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def prepare_root(root):
    """Test-only evidence settings: the local page server is allowed and ranked 2."""
    f = Path(root) / "config/evidence.json"
    cfg = json.loads(f.read_text(encoding="utf-8"))
    cfg.update(domains={"127.0.0.1": 2}, allow_private_hosts=True, polite_pause_s=0.0)
    f.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


class Driver:
    def __init__(self, root, base_url):
        self.root, self.base = Path(root), base_url
        self.env = {**os.environ, "LAB_ROOT": str(self.root)}
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        self.trail = []
        self.job = None

    # ---- the command-line tools ----
    def run(self, script, *args, stdin=None):
        p = subprocess.run([sys.executable, str(self.root / "engine" / script), *args], input=stdin,
                           capture_output=True, text=True, env=self.env)
        return p.returncode, p.stdout, p.stderr

    def state(self, *args, stdin=None, expect=0):
        code, out, err = self.run("state.py", *args, stdin=stdin)
        if expect is not None and code != expect:
            raise AssertionError(f"state.py {' '.join(args)} -> {code} (expected {expect}): {err or out}")
        return code, out, err

    def status(self):
        return json.loads(self.state("status", self.job)[1])

    def event(self, name, *extra, expect=0):
        code, out, err = self.state("event", self.job, name, *extra, expect=expect)
        if code == 0:
            self.note(name)
        return code, out, err

    def note(self, what):
        st = self.status()
        self.trail.append((what, st["state"], st["stage"]))

    def hook(self, launcher, payload):
        p = subprocess.run([sys.executable, str(self.root / "engine/hooks" / launcher)], input=json.dumps(payload),
                           capture_output=True, text=True, env=self.env)
        return p.returncode, p.stderr

    def job_rel(self):
        return self.status()["artifact_path"].rsplit("/drafts/", 1)[0] if self.status()["artifact_path"] else None

    # ---- jobs ----
    def new(self, slug="walkthrough", cls="synthetic"):
        _, out, _ = self.state("new", "demo", slug, "Summarise order volumes for three regions", "--class", cls)
        self.job = out.split()[0]
        self.note("new")
        return self.job

    def stand_in(self, agent, files=None, item=None, fetch=None, tokens=None, status="completed", write_check=True):
        """One subagent call. files: {name: text} written into OUTPUT_DIR. Returns (handoff text, paths)."""
        _, text, _ = self.state("handoff", self.job, *(["--item", item] if item else []))
        out_dir = re.search(r"^OUTPUT_DIR: (.+)$", text, re.M).group(1).strip()
        hid = re.search(r"HANDOFF: (H\d+)", text).group(1)
        self.state("call", self.job, agent, *(["--item", item] if item else []))
        written = []
        for name, body in (files or {}).items():
            path = f"{out_dir}{name}"
            if write_check:  # the agent's Write goes through the guard hook first
                code, err = self.hook("pre_tool_use_launcher.py", {"tool_name": "Write", "tool_input": {"file_path": path},
                                                                    "cwd": str(self.root), "agent_id": "stand-in",
                                                                    "agent_type": agent})
                if code != 0:
                    raise AssertionError(f"hook blocked the stand-in's write to {path}: {err}")
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text(body, encoding="utf-8")
            written.append(path)
        for key in fetch or []:
            code, out, err = self.run("evidence.py", "fetch", self.job, f"{self.base}/{key}", "--handoff", hid)
            if code != 0:
                raise AssertionError(f"fetch {key} failed: {err}")
        return text, written, tokens or TOKENS[agent], status

    def finish(self, call, status=None):
        """Hand the stand-in's result to the real PostToolUse hook (as the app does when a subagent returns)."""
        text, _, tokens, st = call
        payload = {"tool_name": "Agent", "tool_use_id": "toolu_demo",
                   "tool_input": {"subagent_type": "stand-in", "prompt": text},
                   "tool_response": {"status": status or st, "totalTokens": tokens, "totalDurationMs": 1200,
                                     "resolvedModel": "stand-in",
                                     "usage": {"input_tokens": tokens // 10, "output_tokens": tokens // 10,
                                               "cache_read_input_tokens": tokens - 3 * (tokens // 10),
                                               "cache_creation_input_tokens": tokens // 10}}}
        return self.hook("post_tool_use_launcher.py", payload)

    def agent(self, agent, files=None, **kw):
        call = self.stand_in(agent, files, **kw)
        code, err = self.finish(call)
        return call, code, err

    def review(self, agent, verdict, findings=()):
        """A reviewer stand-in writes findings; they are validated by script before the review event."""
        st = self.status()
        version = Path(st["artifact_path"]).stem
        doc = {"job_id": self.job, "reviewer": agent, "artifact_path": st["artifact_path"], "artifact_version": version,
               "verdict": verdict, "rules_checked": ["DM01", "DM02", "DM03", "DM04"], "findings": list(findings)}
        call, code, err = self.agent(agent, {f"{agent}-{version}.json": json.dumps(doc, indent=2)})
        path = call[1][0]
        vcode, vout, _ = self.run("validate_findings.py", str(self.root / path))
        if vcode != 0:
            raise AssertionError(f"findings invalid: {vout}")
        return self.event("review_pass" if verdict == "pass" else "review_fail")


def main_path_to_gate(d, writer_v1=None):
    """NEW -> planner -> 3 parallel research items -> writer (asks one question) -> critic fails v1 ->
    writer v2 -> critic and verifier pass -> GATE. Returns the job id."""
    d.event("dispatch")
    d.agent("demo-planner", {"plan.md": "# Plan\nResearch three regions, then write one summary.\n"})
    d.event("stage_done")
    d.state("fanout", d.job, "north", "south", "east")
    d.note("fanout")
    calls = {i: d.stand_in("demo-researcher", {f"{i}.md": f"# {i}\nNotes for {i}.\n"}, item=i, fetch=[i])
             for i in ("north", "south", "east")}                                  # three calls open at once
    for i in ("east", "north", "south"):                                           # results arrive in any order
        code, err = d.finish(calls[i])
        if code != 0:
            raise AssertionError(err)
        d.state("fanout-result", d.job, i, "done")
    d.event("stage_done")
    d.agent("demo-writer")                                                        # first try: a question back
    q = d.root / "scratch-questions.md"
    q.write_text("1. Should the summary rank the regions?\n", encoding="utf-8")
    d.event("needs_input", "--questions", str(q))
    d.state("input", d.job, "-", "--class", d.status()["class"], stdin="Yes, rank the regions by daily orders.\n")
    d.event("answered")
    quote = PAGES["north"].split(" on average")[0]                                # a verbatim span of S01
    v1 = writer_v1 or (f'# Order volumes\nNorth leads [S:S01 §1 "{quote}"]. '
                       'We rank the regions [A:A01 "rank the regions by daily orders"].\n')
    d.agent("demo-writer", {"v1.md": v1})
    d.event("artifact_ready", "--artifact", f"{d.status_job_folder()}/drafts/v1.md")
    finding = {"id": "F-01", "rule": "DM02", "severity": "major", "location": "§1", "issue": "No ranking table.",
               "fix": "Add a table of the three regions."}
    d.review("demo-critic", "fail", [finding])
    v2 = v1 + "\n| Region | Orders per day |\n|---|---|\n| North | 120 [S:S01 §1] |\n"
    d.agent("demo-writer", {"v2.md": v2})
    d.event("revised", "--artifact", f"{d.status_job_folder()}/drafts/v2.md")
    d.review("demo-critic", "pass")
    d.review("demo-verifier", "pass")
    return d.job


def _job_folder(self):
    return ("private/jobs/" if self.status()["class"] == "internal" else "jobs/") + self.job


Driver.status_job_folder = _job_folder


def deliver_and_finish(d):
    d.event("deliver")
    d.agent("demo-publisher", {"published.md": "Published summary of the three regions.\n"})
    d.event("complete")
