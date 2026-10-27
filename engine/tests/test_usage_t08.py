"""T0.8: usage log and ceiling. Calls stay open until their result is recorded (by the post hook,
matched on the HANDOFF id in the subagent prompt), except parallel fan-out items; usage is logged
by script with input, output, cache-read and cache-write tokens separately; a provisional
per-job ceiling pauses the job, and only the approver can raise it."""
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import unittest

from support import REPO, LabTestBase

POST_LAUNCHER_SHA256 = "a3399b40c52174ab98ad3791769b1097e3d30b5e48479c894a3542c33aca8f76"
USAGE = {"input_tokens": 5, "output_tokens": 300, "cache_read_input_tokens": 11000, "cache_creation_input_tokens": 465}


class UsageBase(LabTestBase):
    auto_result = False

    def set_ceiling_caps(self, **kw):
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        caps["usage_ceiling"].update(kw)
        self.dump("config/caps.json", caps)

    def spec_at_review(self, slug="usage", cls="synthetic"):
        lc = self.lc
        j = lc.new_job("spec", slug, "x", cls=cls)["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"{lc.rel(lc.job_dir(j))}/drafts/v1.md", "v1"))
        return j

    def post(self, prompt, agent="critic", total=11770, status="completed", usage=USAGE):
        payload = {"tool_name": "Agent", "tool_use_id": "toolu_1",
                   "tool_input": {"subagent_type": agent, "description": "d", "prompt": prompt},
                   "tool_response": {"status": status, "totalTokens": total, "totalDurationMs": 7769,
                                     "resolvedModel": "claude-opus-5-5", "usage": usage}}
        p = subprocess.run([sys.executable, str(self.tmp / "engine/hooks/post_tool_use_launcher.py")],
                           input=json.dumps(payload), capture_output=True, text=True, env=self.hook_env())
        return p.returncode, p.stderr

    def lines(self, rel):
        f = self.tmp / rel
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def call_with_handoff(self, j, agent, item=None):
        _, text = self.lc.handoff(j, item)
        st = self.lc.record_call(j, agent, item=item)
        return st["calls"][-1], text


class OpenCallTests(UsageBase):
    def test_an_open_call_blocks_the_next_call_until_its_result(self):
        lc = self.lc
        j = self.spec_at_review()
        call, _ = self.call_with_handoff(j, "critic")
        self.assertEqual(call["status"], "open")
        lc.apply(j, "review_pass")
        lc.handoff(j)
        with self.assertRaises(lc.LabError) as cm:
            lc.record_call(j, "verifier")
        self.assertIn("still open", str(cm.exception))
        lc.record_result(j, call["id"], "done")
        self.assertEqual(lc.record_call(j, "verifier")["calls"][-1]["status"], "open")

    def test_three_parallel_fanout_items(self):
        lc = self.lc
        j = lc.new_job("survey", "parallel", "x")["job_id"]
        lc.apply(j, "dispatch")
        planner, _ = self.call_with_handoff(j, "planner")
        lc.record_result(j, planner["id"], "done")
        lc.apply(j, "stage_done")
        lc.set_fanout(j, ["north", "south", "east"])
        texts = {i: lc.handoff(j, i)[1] for i in ("north", "south", "east")}   # all three built first
        calls = {i: lc.record_call(j, "researcher", item=i)["calls"][-1] for i in ("north", "south", "east")}
        self.assertEqual([c["status"] for c in calls.values()], ["open"] * 3)    # three open at once
        self.assertEqual(len({c["handoff"] for c in calls.values()}), 3)          # each linked to its own handoff
        for item in ("south", "east", "north"):                                   # results arrive in any order
            code, err = self.post(texts[item], agent="researcher")
            self.assertEqual(code, 0, err)
        st = lc.load_state(j)
        by_item = {c["item"]: c for c in st["calls"] if c["item"]}
        self.assertTrue(all(c["status"] == "done" and c["usage"]["total"] == 11770 for c in by_item.values()))
        self.assertEqual({c["handoff"] for c in by_item.values()}, {calls[i]["handoff"] for i in calls})

    def test_parallel_allowance_is_only_for_the_fanout_stage(self):
        lc = self.lc
        j = lc.new_job("survey", "notparallel", "x")["job_id"]
        lc.apply(j, "dispatch")
        self.call_with_handoff(j, "planner")
        lc.apply(j, "stage_done")
        lc.set_fanout(j, ["north", "south"])
        lc.handoff(j, "north")
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="north")                       # the planner call is still open

    def test_infra_error_closes_the_open_call_as_failed_and_permits_a_retry(self):
        lc = self.lc
        j = self.spec_at_review()
        call, _ = self.call_with_handoff(j, "critic")
        lc.apply(j, "infra_error")
        st = lc.load_state(j)
        self.assertEqual((st["calls"][0]["status"], st["calls"][0]["usage_source"]), ("failed", "infra_error"))
        retry = lc.record_call(j, "critic")["calls"][-1]
        self.assertEqual((retry["retry_of"], retry["handoff"]), (call["id"], call["handoff"]))  # same handoff


class PostHookTests(UsageBase):
    def test_result_matched_by_handoff_with_separate_token_fields(self):
        lc = self.lc
        j = self.spec_at_review()
        call, text = self.call_with_handoff(j, "critic")
        code, err = self.post(text)
        self.assertEqual(code, 0, err)
        c = lc.load_state(j)["calls"][0]
        self.assertEqual((c["status"], c["usage_source"]), ("done", "post_tool_use"))
        self.assertEqual({k: c["usage"][k] for k in ("input", "output", "cache_read", "cache_write", "total")},
                         {"input": 5, "output": 300, "cache_read": 11000, "cache_write": 465, "total": 11770})
        self.assertEqual((c["usage"]["duration_s"], c["usage"]["model"]), (7.769, "claude-opus-5-5"))
        line = self.lines("logs/usage.jsonl")[-1]
        self.assertEqual(line["tokens"], {"input": 5, "output": 300, "cache_read": 11000, "cache_write": 465, "total": 11770})
        self.assertEqual((line["call"], line["agent"], line["source"]), (call["id"], "critic", "post_tool_use"))
        self.assertNotIn("prompt", json.dumps(line))                                # numbers only, no content

    def test_a_failed_subagent_closes_its_call_as_failed(self):
        j = self.spec_at_review()
        _, text = self.call_with_handoff(j, "critic")
        self.post(text, status="error")
        self.assertEqual(self.lc.load_state(j)["calls"][0]["status"], "failed")

    def test_unmatched_calls_are_logged_never_dropped(self):
        lc = self.lc
        j = self.spec_at_review()
        _, text = self.call_with_handoff(j, "critic")
        self.post("Please review this.", agent="critic")                            # no JOB/HANDOFF lines
        self.post(text.replace(j, "20250101-spec-gone"), agent="critic")            # unknown job
        self.post(text)                                                             # matched: closes the call
        self.post(text)                                                             # again: no open call left
        reasons = [e["reason"] for e in self.lines("logs/usage-unmatched.jsonl")]
        self.assertEqual(len(reasons), 3, reasons)
        self.assertIn("no JOB/HANDOFF lines in the subagent prompt", reasons[0])
        self.assertIn("not found", reasons[1])
        self.assertIn("no open call", reasons[2])
        self.assertTrue(all(e["tokens"]["total"] == 11770 for e in self.lines("logs/usage-unmatched.jsonl")))

    def test_internal_job_usage_is_logged_privately(self):
        j = self.spec_at_review(slug="intusage", cls="internal")
        _, text = self.call_with_handoff(j, "critic")
        self.assertEqual(self.post(text)[0], 0)
        self.assertEqual(self.lines("logs/usage.jsonl"), [])
        self.assertEqual(self.lines("private/logs/usage.jsonl")[-1]["job_id"], j)

    def test_non_agent_tools_are_ignored(self):
        payload = {"tool_name": "Read", "tool_input": {"file_path": "x"}, "tool_response": {}}
        p = subprocess.run([sys.executable, str(self.tmp / "engine/hooks/post_tool_use_launcher.py")],
                           input=json.dumps(payload), capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0)
        self.assertFalse((self.tmp / "logs/usage-unmatched.jsonl").exists())

    def test_launcher_fails_closed_and_is_pinned(self):
        (self.tmp / "engine/hooks/post_tool_use.py").write_text("def run(raw:\n", encoding="utf-8")
        code, err = self.post("JOB: x\nHANDOFF: H001")
        self.assertEqual(code, 2)
        self.assertIn("usage not recorded", err)
        digest = hashlib.sha256((REPO / "engine/hooks/post_tool_use_launcher.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        self.assertEqual(digest, POST_LAUNCHER_SHA256, "the post launcher changed: it must never be edited")

    def test_usage_logs_are_protected_from_agent_writes(self):
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        try:
            hook = importlib.import_module("pre_tool_use")
            for path in ("logs/usage.jsonl", "logs/usage-unmatched.jsonl", "private/logs/usage.jsonl"):
                code = hook.run(json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": str(self.tmp)}))
                self.assertEqual(code, 2, path)
        finally:
            sys.path.remove(str(self.tmp / "engine/hooks"))


class CeilingTests(UsageBase):
    def test_token_ceiling_pauses_the_job_and_only_the_approver_raises_it(self):
        lc = self.lc
        self.set_ceiling_caps(tokens=20000)
        j = self.spec_at_review()
        _, text = self.call_with_handoff(j, "critic")
        self.assertEqual(self.post(text)[0], 0)                                      # 11,770 tokens
        lc.apply(j, "review_fail")
        _, text = self.call_with_handoff(j, "writer")
        code, err = self.post(text, agent="writer")                                  # 23,540 >= 20,000
        self.assertEqual(code, 2)
        self.assertIn("usage ceiling reached", err)
        st = lc.load_state(j)
        self.assertEqual(st["state"], "ESCALATED")
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "resume")
        with self.assertRaises(lc.LabError):
            lc.set_ceiling(j, tokens=50000)                                          # not human
        p = subprocess.run([sys.executable, str(self.tmp / "engine/gate.py"), "ceiling", j, "--tokens", "50000"],
                           capture_output=True, text=True, env=self.hook_env(), stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 1)                                             # no terminal: refused
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        self.assertEqual(g.main(["ceiling", j, "--tokens", "50000"]), 0)
        audit = self.lines("logs/gate-audit.jsonl")[-1]
        self.assertEqual((audit["action"], audit["ceiling"]["tokens"]), ("ceiling", 50000))
        self.assertEqual(lc.apply(j, "resume")["state"], "REVISING")

    def test_minutes_fallback_when_no_tokens_are_known(self):
        lc = self.lc
        self.set_ceiling_caps(agent_minutes=0.00001)
        j = self.spec_at_review()
        call, _ = self.call_with_handoff(j, "critic")
        import time
        time.sleep(0.05)                                                             # a measurable call
        st, over = lc.record_result(j, call["id"], "done")                           # manual: usage unknown
        self.assertIn("agent minutes", over)
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")

    def test_ceiling_is_checked_before_a_call(self):
        lc = self.lc
        j = self.spec_at_review()
        call, _ = self.call_with_handoff(j, "critic")
        lc.record_result(j, call["id"], "done", usage=lc.usage_from_tokens(USAGE, total=11770, duration_ms=1000))
        lc.apply(j, "review_pass")
        self.set_ceiling_caps(tokens=10000)                                          # lowered after the fact
        lc.handoff(j)
        with self.assertRaises(lc.CapExceeded):
            lc.record_call(j, "verifier")
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")

    def test_per_call_warning_flags_without_stopping(self):
        lc = self.lc
        self.set_ceiling_caps(per_call_warning_tokens=10000)
        j = self.spec_at_review()
        _, text = self.call_with_handoff(j, "critic")
        self.assertEqual(self.post(text)[0], 0)
        st = lc.load_state(j)
        self.assertTrue(st["calls"][0]["warning"])
        self.assertEqual(st["state"], "REVIEW")
        summary = "\n".join(lc.usage_summary(j))
        self.assertIn("WARNING: 1 call(s) over the per-call threshold", summary)


class SummaryAndCliTests(UsageBase):
    def test_summary_totals_and_main_session_note(self):
        lc = self.lc
        j = self.spec_at_review()
        _, text = self.call_with_handoff(j, "critic")
        self.post(text)
        lc.apply(j, "review_fail")
        call, _ = self.call_with_handoff(j, "writer")
        lc.record_result(j, call["id"], "done")                                       # usage unknown
        out = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "usage", j],
                             capture_output=True, text=True, env=self.hook_env()).stdout
        self.assertIn("calls 2 (closed 2, with token figures 1)", out)
        self.assertIn("input 5, output 300, cache_read 11000, cache_write 465, total 11770", out)
        self.assertIn("critic: calls 1", out)
        self.assertIn("writer: calls 1, retries 0, failed 0, tokens 0", out)
        self.assertIn("usage unknown 1", out)
        self.assertIn("Not included: the Orchestrator's own main-session tokens (until the headless runner, T5.2).", out)

    def test_headless_result_from_a_claude_json_file(self):
        lc = self.lc
        j = self.spec_at_review()
        call, _ = self.call_with_handoff(j, "critic")
        self.dump("scratch/result.json", {"type": "result", "duration_ms": 4200, "total_cost_usd": 0.12,
                                          "usage": USAGE, "modelUsage": {"claude-opus-5-5": {}}})
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "result", j, call["id"], "done",
                            "--usage-json", str(self.tmp / "scratch/result.json")],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        c = lc.load_state(j)["calls"][0]
        self.assertEqual((c["usage_source"], c["usage"]["total"], c["usage"]["cost_usd_estimate"], c["usage"]["model"]),
                         ("headless", 11770, 0.12, "claude-opus-5-5"))


class PostHookRegistrationTests(unittest.TestCase):
    def test_settings_register_the_post_launcher(self):
        s = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
        entries = s["hooks"]["PostToolUse"]
        self.assertEqual([e["matcher"] for e in entries], ["Agent|Task"])
        h = entries[0]["hooks"][0]
        self.assertEqual((h["type"], h.get("onFailure")), ("command", "block"))
        self.assertTrue(h["args"][-1].endswith("engine/hooks/post_tool_use_launcher.py"), h["args"])
        self.assertTrue(shutil.which(h["command"]))


if __name__ == "__main__":
    unittest.main()
