"""T0.13: the evaluation runner (evals/run_evals.py), its cost controls and caching, the scoring, the
reports (numbers only), the lock rule (engine/evalcheck.py, gate.py lock) and "usage pending" for
background launches. The calibration-critic suite runs against fake_claude.py: no live calls."""
import importlib
import json
import os
import subprocess
import sys

from test_agent_call_t13 import AgentCallBase
from test_usage_t08 import UsageBase

CLI = "9.9.9 (Claude Code)"
SUITE = "calibration-critic"
MARKER = "ANSWER-TEXT-MARKER-6604"


def answer(case, rules, verdict, severity="major", job=None, fence=False):
    doc = {"job_id": job or f"eval-{case}", "reviewer": "calibration-critic", "artifact_path": "artifact.md",
           "artifact_version": "v1", "verdict": verdict, "rules_checked": ["CC01", "CC02", "CC03", "CC04", "CC05", "CC06"],
           "findings": [{"id": f"F-0{i + 1}", "rule": r, "severity": severity, "location": "Requirements",
                         "issue": f"{MARKER} issue", "fix": "fix it"} for i, r in enumerate(rules)],
           "summary": f"{MARKER} summary"}
    text = json.dumps(doc)
    return f"```json\n{text}\n```" if fence else text


class EvalBase(AgentCallBase):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.tmp / "evals"))
        self.re = importlib.import_module("run_evals")
        self.ec = importlib.import_module("evalcheck")
        self.keys = {k: json.loads((self.tmp / f"evals/{SUITE}/keys/{k}.json").read_text(encoding="utf-8"))
                     for k in ("E001", "E002", "E003", "E004", "E005", "E006", "E007")}
        self.respond()
        self.out = []

    def tearDown(self):
        while str(self.tmp / "evals") in sys.path:
            sys.path.remove(str(self.tmp / "evals"))
        super().tearDown()

    def respond(self, **override):
        """Perfect answers from the keys, with per-case overrides (a text or a list of texts per run)."""
        pairs = []
        for cid, key in self.keys.items():
            pairs.append([f"JOB: eval-{cid}", override.get(cid, answer(cid, key["must_find"], key["verdict"]))])
        f = self.tmp / "fake-responses.json"
        f.write_text(json.dumps(pairs), encoding="utf-8")
        os.environ["FAKE_CLAUDE_RESPONSES"] = str(f)

    def run_suite(self, mode="full", **kw):
        self.out = []
        return self.re.run(SUITE, mode, out=self.out.append, cli=CLI, **kw)

    def reports(self):
        d = self.tmp / "evals/reports"
        return sorted(d.glob("*.json")) if d.is_dir() else []


class RunnerTests(EvalBase):
    def test_a_perfect_reviewer_passes_and_the_report_holds_no_answer_text(self):
        rep, code = self.run_suite()
        self.assertEqual(code, 0, self.out)
        m = rep["metrics"]
        self.assertEqual((m["recall_major"], m["false_fail_rate"], m["verdict_match"], m["invalid_output_rate"]),
                         (1.0, 0.0, 1.0, 0.0))
        self.assertEqual((m["cases"], m["clean_cases"], m["runs"]), (7, 2, 21))
        self.assertEqual(set(m["recall_per_rule"]), {"CC01", "CC02", "CC03", "CC04", "CC05"})
        self.assertEqual(len(self.calls()), 21)
        self.assertEqual((rep["model"], rep["cli_version"], rep["mode"]), ("claude-opus-5-5", CLI, "full"))
        self.assertEqual(rep["min_counts"], {"applies": False, "need": {"cases": 20, "clean": 5},
                                             "have": {"cases": 7, "clean": 2}, "met": None})
        self.assertIn("rules/calibration-critic.md", rep["framework"])
        text = self.reports()[0].read_text(encoding="utf-8")
        self.assertNotIn(MARKER, text)                                     # never the agent's text
        cached = list((self.tmp / "cache/evals" / SUITE).glob("*.json"))
        self.assertEqual(len(cached), 21)
        self.assertIn(MARKER, cached[0].read_text(encoding="utf-8"))       # kept only in the untracked cache
        for c in self.calls():
            self.assertIn("--safe-mode", c["argv"])
            self.assertEqual(c["cwd_files"], [])
            self.assertNotIn("must_find", c["stdin"] + c["system_prompt"])  # no key content reaches the agent
            self.assertNotIn("keys", c["stdin"])

    def test_cached_runs_are_reused_and_no_cache_forces_new_calls(self):
        self.run_suite()
        rep, _ = self.run_suite()
        self.assertEqual((rep["usage"]["cached"], rep["usage"]["tokens_new"], len(self.calls())), (21, 0, 21))
        self.run_suite(use_cache=False)
        self.assertEqual(len(self.calls()), 42)
        (self.tmp / f"evals/{SUITE}/cases/E002/artifact.md").write_text("# changed\n", encoding="utf-8")
        self.run_suite()
        self.assertEqual(len(self.calls()), 45)                            # only the changed case runs again

    def test_quick_mode_runs_once_and_partial_runs_never_count(self):
        rep, _ = self.run_suite("quick")
        self.assertEqual((len(self.calls()), rep["mode"], rep["metrics"]["runs"]), (7, "quick", 7))
        self.assertIn("never counts for lock", "\n".join(self.out))
        rep, _ = self.run_suite(only={"E002"})
        self.assertEqual(rep["mode"], "full-partial")
        fp = {"model": "claude-opus-5-5", "cli_version": CLI}
        self.assertFalse(any(self.ec.counts(json.loads(f.read_text(encoding="utf-8")), fp) for f in self.reports()))

    def test_invalid_output_is_counted_and_reported_separately(self):
        self.respond(E002=answer("E002", ["CC01"], "fail", fence=True),          # fenced: not a bare object
                     E003=answer("E003", ["CC02"], "fail", severity="minor"),    # softened severity
                     E004=answer("E004", ["CC03"], "fail", job="20261022-x-y"))  # ID not copied
        rep, code = self.run_suite()
        m = rep["metrics"]
        self.assertEqual((m["invalid_runs"], m["invalid_output_rate"]), (9, round(9 / 21, 3)))
        self.assertEqual(m["recall_per_rule"]["CC01"], 0.0)                 # an invalid run finds nothing
        self.assertEqual(m["recall_major"], 0.4)
        self.assertEqual(code, 1)
        self.assertTrue(any("recall_major" in f for f in rep["threshold_failures"]))

    def test_a_case_counts_on_a_majority_of_its_runs(self):
        hit, miss = answer("E002", ["CC01"], "fail"), answer("E002", [], "pass")
        self.respond(E002=[hit, miss, hit])
        rep, _ = self.run_suite()
        self.assertEqual(rep["metrics"]["recall_per_rule"]["CC01"], 1.0)    # 2 of 3
        e002 = next(c for c in rep["cases"] if c["case"] == "E002")
        self.assertEqual((e002["runs_passed"], e002["pass"], e002["agreement"]), (2, True, 0.667))
        self.respond(E002=[hit, miss, miss])
        rep, _ = self.run_suite(use_cache=False)
        self.assertEqual(rep["metrics"]["recall_per_rule"]["CC01"], 0.0)    # 1 of 3

    def test_clean_cases_measure_false_fails(self):
        self.respond(E001=answer("E001", ["CC06"], "fail", severity="minor"))  # minor finding, yet verdict fail
        rep, _ = self.run_suite()
        self.assertEqual(rep["metrics"]["invalid_runs"], 0)
        self.assertEqual(rep["metrics"]["false_fail_rate"], 0.5)
        self.respond(E001=answer("E001", ["CC03"], "fail"))                     # a must_not_find rule
        rep, _ = self.run_suite(use_cache=False)
        self.assertFalse(next(c for c in rep["cases"] if c["case"] == "E001")["pass"])


class CostControlTests(EvalBase):
    def caps(self, **kw):
        caps = json.loads((self.tmp / "config/caps.json").read_text(encoding="utf-8"))
        caps["evals"].update(kw)
        self.dump("config/caps.json", caps)

    def test_estimate_only_makes_no_call(self):
        rep, code = self.run_suite(estimate_only=True)
        self.assertEqual((rep, code, self.calls()), (None, 0, []))
        self.assertTrue(any(l.startswith("Estimate for the 21 new call(s)") for l in self.out), self.out)

    def test_above_the_confirm_limit_the_approver_confirms_in_a_terminal(self):
        self.caps(confirm_above_tokens=1000)
        with self.assertRaisesRegex(self.re.Refused, "approver runs this in their own terminal"):
            self.run_suite()
        self.assertEqual(self.calls(), [])
        g = importlib.import_module("gate")
        g.interactive_terminal = lambda: True
        import builtins
        real_input = builtins.input
        try:
            builtins.input = lambda prompt: "123"                                  # the wrong number
            with self.assertRaisesRegex(self.re.Refused, "not confirmed"):
                self.run_suite()
            est = self.re.agent_call.estimate
            total = sum(est(self.re.load_suite(SUITE)["agent_spec"],
                            self.re.build_prompt(self.re.load_suite(SUITE), c))["tokens"] * 3
                        for c in self.re.load_cases(self.re.load_suite(SUITE)))
            builtins.input = lambda prompt: str(total)
            rep, code = self.run_suite()
            self.assertEqual(code, 0)
        finally:
            builtins.input = real_input

    def test_the_token_ceiling_and_the_call_cap_stop_a_run(self):
        self.caps(tokens_per_invocation=1500)                                      # each fake call reports 944
        rep, code = self.run_suite()
        self.assertEqual((rep, code, len(self.calls())), (None, 3, 2))
        self.assertTrue(any("token ceiling reached" in l for l in self.out))
        self.assertEqual(self.reports(), [])
        self.caps(tokens_per_invocation=1_000_000, max_runs_per_invocation=5)
        with self.assertRaisesRegex(self.re.Refused, "max_runs_per_invocation"):
            self.run_suite()

    def test_an_infrastructure_error_is_retried_once_then_stops(self):
        os.environ["FAKE_CLAUDE_MODE"] = "nojson"
        rep, code = self.run_suite()
        self.assertEqual((rep, code, len(self.calls())), (None, 3, 2))
        self.assertTrue(any("infrastructure error" in l for l in self.out))


class LeakTests(EvalBase):
    def test_a_leak_term_stops_the_run_before_any_call(self):
        art = self.tmp / f"evals/{SUITE}/cases/E002/artifact.md"
        art.write_text(art.read_text(encoding="utf-8") + "\nNote: there is a Trace Gap here.\n", encoding="utf-8")
        rep, code = self.run_suite()
        self.assertEqual((rep, code, self.calls()), (None, 2, []))
        self.assertTrue(any("LEAK: case E002: 'trace gap'" in l for l in self.out), self.out)

    def test_leak_terms_in_the_instructions_are_found_too(self):
        f = self.tmp / "evals/agents/calibration-critic.md"
        f.write_text(f.read_text(encoding="utf-8") + "\nSome cases are planted.\n", encoding="utf-8")
        _, code = self.run_suite()
        self.assertEqual(code, 2)
        self.assertTrue(any("agent instructions" in l for l in self.out))

    def test_the_shipped_cases_are_leak_free(self):
        s = self.re.load_suite(SUITE)
        self.assertEqual(self.re.leak_check(s, self.re.load_cases(s)), [])


class LockRuleTests(EvalBase):
    def problems(self, cli=CLI):
        return self.ec.lock_problems(cli=cli)

    def test_no_reports_no_lock(self):
        self.assertIn("no evaluation reports", self.problems()[0])

    def test_a_passing_full_run_allows_lock(self):
        self.run_suite()
        self.assertEqual(self.problems(), [])

    def test_a_rule_edit_refuses_lock_until_that_suite_runs_again(self):
        self.run_suite()
        rb = self.tmp / "rules/calibration-critic.md"
        rb.write_text(rb.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        probs = self.problems()
        self.assertTrue(any("suite calibration-critic" in p and "changed" in p for p in probs), probs)
        self.run_suite()
        self.assertEqual(self.problems(), [])

    def test_a_config_edit_needs_a_smoke_run(self):
        self.run_suite()
        caps = json.loads((self.tmp / "config/caps.json").read_text(encoding="utf-8"))
        caps["infra_retries"] = 3
        self.dump("config/caps.json", caps)
        probs = self.problems()
        self.assertTrue(any("config/caps.json" in p for p in probs), probs)
        self.run_suite("smoke")
        self.assertEqual(len(self.calls()), 24)                            # one case, 3 runs
        self.assertEqual(self.problems(), [])

    def test_a_model_or_cli_change_makes_reports_stale(self):
        self.run_suite()
        self.assertTrue(any("recalibrate" in p for p in self.problems(cli="10.0.0 (Claude Code)")))
        models = json.loads((self.tmp / "config/models.json").read_text(encoding="utf-8"))
        models["default"] = "some-newer-model"
        self.dump("config/models.json", models)
        probs = self.problems()
        self.assertTrue(any("recalibrate" in p for p in probs), probs)
        self.assertTrue(any("no passing evaluation report for the current model" in p for p in probs), probs)

    def test_quick_runs_never_allow_lock(self):
        self.run_suite("quick")
        self.assertTrue(self.problems())

    def test_every_agent_file_needs_a_suite(self):
        self.agent_file()
        self.run_suite()
        self.assertTrue(any("agent .claude/agents/demo-planner.md has no evaluation suite" in p for p in self.problems()))

    def test_minimum_counts_apply_only_to_agents_used_by_routes(self):
        routes = json.loads((self.tmp / "config/routes.json").read_text(encoding="utf-8"))
        routes["routes"]["spec"]["reviews"][0]["agent"] = "calibration-critic"
        self.dump("config/routes.json", routes)
        rep, _ = self.run_suite()
        self.assertEqual((rep["min_counts"]["applies"], rep["min_counts"]["met"]), (True, False))
        self.assertTrue(any("below the minimum case counts" in p for p in self.problems()))

    def test_gate_lock_uses_the_rule(self):
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        os.environ["FAKE_CLAUDE_VERSION"] = CLI
        self.assertEqual(g.main(["lock"]), 1)
        self.assertFalse((self.tmp / ".lab/OPERATE").exists())
        self.assertFalse((self.tmp / "logs/gate-audit.jsonl").exists())
        self.run_suite()
        self.assertEqual(g.main(["lock"]), 0)
        self.assertTrue((self.tmp / ".lab/OPERATE").exists())

    def test_stale_command(self):
        os.environ["FAKE_CLAUDE_VERSION"] = CLI
        self.assertEqual(self.re.main(["stale"]), 1)
        self.run_suite()
        self.assertEqual(self.re.main(["stale"]), 0)


class UsagePendingTests(UsageBase):
    def test_a_background_launch_leaves_the_call_open_with_usage_pending(self):
        j = self.spec_at_review()
        call, text = self.call_with_handoff(j, "critic")
        payload = {"tool_name": "Agent", "tool_use_id": "toolu_bg",
                   "tool_input": {"subagent_type": "critic", "description": "d", "prompt": text},
                   "tool_response": {"isAsync": True, "status": "async_launched", "agentId": "a1"}}
        p = subprocess.run([sys.executable, str(self.tmp / "engine/hooks/post_tool_use_launcher.py")],
                           input=json.dumps(payload), capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        st = self.lc.load_state(j)
        self.assertEqual(st["calls"][-1]["status"], "open")                # not failed, not 0 tokens
        rec = self.lines("logs/usage-unmatched.jsonl")[-1]
        self.assertEqual((rec["job_id"], rec["tokens"]), (j, None))
        self.assertIn("usage pending", rec["reason"])
        self.assertEqual(self.lines("logs/usage.jsonl"), [])
