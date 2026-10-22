"""T0.13: engine/agent_call.py, the headless agent call shared by the evaluation runner and (from
T1.5) the job loop. Every test uses fake_claude.py instead of the real CLI."""
import importlib
import json
import os
import sys
from pathlib import Path

from support import LabTestBase

FAKE = Path(__file__).resolve().parent / "fake_claude.py"
TOOLLESS = """---
name: demo-planner
description: test planner
tools:
model: inherit
---

# Role
Plan the work. Output only JSON.
"""


class AgentCallBase(LabTestBase):
    def setUp(self):
        super().setUp()
        self.log = self.tmp / "fake-claude.jsonl"
        self._fake_env = {k: os.environ.get(k) for k in ("FAKE_CLAUDE_LOG", "FAKE_CLAUDE_MODE", "FAKE_CLAUDE_RESPONSES",
                                                          "FAKE_CLAUDE_VERSION", "ANTHROPIC_API_KEY")}
        os.environ["FAKE_CLAUDE_LOG"] = str(self.log)
        for k in ("FAKE_CLAUDE_MODE", "FAKE_CLAUDE_RESPONSES", "FAKE_CLAUDE_VERSION"):
            os.environ.pop(k, None)
        models = json.loads((self.tmp / "config/models.json").read_text(encoding="utf-8"))
        models["claude_command"] = [sys.executable, str(FAKE)]
        self.dump("config/models.json", models)
        self.ac = importlib.import_module("agent_call")

    def tearDown(self):
        for k, v in self._fake_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def calls(self):
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def agent_file(self, text=TOOLLESS, name="demo-planner"):
        return self.write(f".claude/agents/{name}.md", text)


class AgentFileTests(AgentCallBase):
    def test_front_matter_and_pinned_model(self):
        a = self.ac.parse_agent(self.tmp / self.agent_file())
        self.assertEqual((a["name"], a["tools"]), ("demo-planner", []))
        self.assertTrue(a["body"].startswith("# Role"))
        self.assertEqual(self.ac.agent_model(a), "claude-opus-5-5")         # inherit -> config/models.json
        b = self.ac.parse_agent(self.tmp / self.agent_file(TOOLLESS.replace("model: inherit", "model: other-model")
                                                           .replace("tools:", "tools: Read, Grep"), "x-reader"))
        self.assertEqual((b["tools"], self.ac.agent_model(b)), (["Read", "Grep"], "other-model"))

    def test_bad_agent_files_are_refused(self):
        for text, why in (("# no front matter\n", "no front matter"), ("---\nname: x\n", "not closed"),
                          ("---\ntools: Read\n---\nbody\n", "no name"),
                          ("---\nname: boss\ntools: Read, Agent\n---\nbody\n", "Agent or Task")):
            with self.assertRaisesRegex(self.lc.LabError, why):
                self.ac.parse_agent(self.tmp / self.write("bad/agent.md", text))

    def test_no_pinned_model_is_refused(self):
        self.dump("config/models.json", {"claude_command": [sys.executable, str(FAKE)]})
        a = self.ac.parse_agent(self.tmp / self.agent_file())
        with self.assertRaisesRegex(self.lc.LabError, "no pinned model"):
            self.ac.call(a, "hello")


class CallTests(AgentCallBase):
    def test_a_toolless_agent_runs_in_safe_mode_in_an_empty_folder(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-not-a-key"
        a = self.ac.parse_agent(self.tmp / self.agent_file())
        r = self.ac.call(a, "the whole prompt")
        self.assertEqual(r["status"], "done")
        c = self.calls()[0]
        self.assertIn("--safe-mode", c["argv"])
        self.assertIn("--tools=", c["argv"])
        self.assertNotIn("--allowedTools", c["argv"])
        for flag in ("-p", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flag, c["argv"])
        self.assertEqual(c["argv"][c["argv"].index("--setting-sources") + 1], "project,local")
        self.assertEqual(c["argv"][c["argv"].index("--model") + 1], "claude-opus-5-5")
        self.assertEqual(c["stdin"], "the whole prompt")                   # prompt on stdin, not argv
        self.assertEqual(c["system_prompt"], a["body"])
        self.assertEqual(c["cwd_files"], [])                               # fresh empty folder
        self.assertFalse(Path(c["cwd"]).resolve().is_relative_to(self.tmp.resolve()))
        self.assertFalse(c["api_key_visible"])                             # stays on the subscription
        self.assertFalse(Path(c["cwd"]).exists())                          # removed afterwards

    def test_usage_comes_from_the_json(self):
        r = self.ac.call(self.ac.parse_agent(self.tmp / self.agent_file()), "x")
        self.assertEqual((r["usage"]["input"], r["usage"]["output"], r["usage"]["cache_write"], r["usage"]["total"]),
                         (2, 325, 617, 944))
        self.assertEqual((r["usage"]["duration_s"], r["usage"]["cost_usd_estimate"]), (4.953, 0.0114))
        self.assertEqual(r["models"], ["claude-opus-5-5"])

    def test_outcomes(self):
        a = self.ac.parse_agent(self.tmp / self.agent_file())
        for mode, status in (("error", "failed"), ("nojson", "infra_error"), ("exit3", "infra_error"),
                             ("subagent", "failed")):
            os.environ["FAKE_CLAUDE_MODE"] = mode
            self.assertEqual(self.ac.call(a, "x")["status"], status, mode)
        os.environ["FAKE_CLAUDE_MODE"] = "sleep"
        r = self.ac.call(a, "x", timeout=2)
        self.assertEqual(r["status"], "infra_error")
        self.assertIn("timed out", r["error"])
        r = self.ac.call(a, "x", cmd=[str(self.tmp / "no-such-cli.exe")])
        self.assertEqual(r["status"], "infra_error")
        self.assertIn("could not start", r["error"])

    def test_an_agent_with_tools_needs_a_guarded_workspace(self):
        a = self.ac.parse_agent(self.tmp / self.agent_file(TOOLLESS.replace("tools:", "tools: Read, Grep"), "x-reader"))
        with self.assertRaisesRegex(self.lc.LabError, "guard hook"):
            self.ac.call(a, "x")                                          # no workspace
        ws = self.tmp / "ws"
        (ws / ".claude").mkdir(parents=True)
        (ws / ".claude/settings.json").write_text(json.dumps({"permissions": {}}), encoding="utf-8")
        with self.assertRaisesRegex(self.lc.LabError, "guard hook"):
            self.ac.call(a, "x", workspace=ws)                            # settings without a hook
        (ws / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": "py -3 guard.py"}]}]}}), encoding="utf-8")
        self.assertEqual(self.ac.call(a, "x", workspace=ws)["status"], "done")
        c = self.calls()[-1]
        self.assertIn("--tools=Read,Grep", c["argv"])
        self.assertEqual(c["argv"][c["argv"].index("--allowedTools") + 1], "Read,Grep")
        self.assertNotIn("--safe-mode", c["argv"])                         # safe mode would switch the hook off
        self.assertEqual(Path(c["cwd"]).resolve(), ws.resolve())

    def test_estimate_and_version(self):
        a = self.ac.parse_agent(self.tmp / self.agent_file())
        e = self.ac.estimate(a, "x" * 4000)
        self.assertGreater(e["tokens"], 1000 + self.ac.BASE_OVERHEAD_TOKENS)
        self.assertGreater(e["seconds"], 0)
        os.environ["FAKE_CLAUDE_VERSION"] = "1.2.3 (Claude Code)"
        self.assertEqual(self.ac.cli_version(), "1.2.3 (Claude Code)")
        self.assertIsNone(self.ac.cli_version(cmd=[str(self.tmp / "no-such-cli.exe")]))


class JobCallTests(AgentCallBase):
    auto_result = False

    def survey_at_planner(self):
        j = self.lc.new_job("survey", "headless", "Plan a survey")["job_id"]
        self.write(f"jobs/{j}/brief.md", "BRIEF-TEXT-4471")
        self.lc.apply(j, "dispatch")
        return j

    def test_a_job_step_records_and_closes_its_call_with_headless_usage(self):
        j = self.survey_at_planner()
        r = self.ac.call_job(j, self.tmp / self.agent_file(TOOLLESS.replace("demo-planner", "planner"), "planner"))
        self.assertEqual((r["status"], r["call"]), ("done", "C001"))
        call = self.lc.load_state(j)["calls"][0]
        self.assertEqual((call["status"], call["usage_source"], call["usage"]["total"], call["handoff"]),
                         ("done", "headless", 944, "H001"))
        prompt = self.calls()[0]["stdin"]
        self.assertIn(f"JOB: {j}", prompt)
        self.assertIn("HANDOFF: H001", prompt)
        self.assertIn("BRIEF-TEXT-4471", prompt)                           # inputs inline: the agent has no tools
        usage = [json.loads(l) for l in (self.tmp / "logs/usage.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual((usage[-1]["source"], usage[-1]["tokens"]["total"]), ("headless", 944))

    def test_an_infra_error_closes_the_call_as_failed(self):
        j = self.survey_at_planner()
        os.environ["FAKE_CLAUDE_MODE"] = "nojson"
        r = self.ac.call_job(j, self.tmp / self.agent_file(TOOLLESS.replace("demo-planner", "planner"), "planner"))
        self.assertEqual(r["status"], "infra_error")
        call = self.lc.load_state(j)["calls"][0]
        self.assertEqual((call["status"], call["usage_source"]), ("failed", "manual"))

    def test_the_wrong_agent_for_the_step_is_refused(self):
        j = self.survey_at_planner()
        with self.assertRaisesRegex(self.lc.LabError, "waiting on 'planner'"):
            self.ac.call_job(j, self.tmp / self.agent_file())
        self.assertEqual(self.calls(), [])
