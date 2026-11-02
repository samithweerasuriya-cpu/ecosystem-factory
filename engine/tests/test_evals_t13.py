"""T0.13: the evaluation runner (evals/run_evals.py), its cost controls and caching, the scoring, the
reports (numbers only), the lock rule (engine/evalcheck.py, gate.py lock) and "usage pending" for
background launches. The calibration-critic suite runs against fake_claude.py: no live calls."""
import importlib
import json
import os
import shutil
import subprocess
import sys

from support import FIX
from test_agent_call_t13 import AgentCallBase
from test_usage_t08 import UsageBase

CLI = "9.9.9 (Claude Code)"
SUITE = "calibration-critic"
MARKER = "ANSWER-TEXT-MARKER-6604"


def answer(case, rules, verdict, severity="major", job=None, fence=False):
    doc = {"job_id": job or f"eval-{case}", "reviewer": "calibration-critic",
           "artifact_path": f"evals/{SUITE}/cases/{case}/artifact.md",
           "artifact_version": "v1", "verdict": verdict, "rules_checked": ["CC01", "CC02", "CC03", "CC04", "CC05", "CC06"],
           "findings": [{"id": f"F-0{i + 1}", "rule": r, "severity": severity, "location": "Requirements",
                         "issue": f"{MARKER} issue", "fix": "fix it"} for i, r in enumerate(rules)],
           "summary": f"{MARKER} summary"}
    text = json.dumps(doc)
    return f"```json\n{text}\n```" if fence else text


class EvalBase(AgentCallBase):
    def setUp(self):
        super().setUp()
        # The suite comes from the tests' own fixture, so these tests also run in a generated ecosystem (T1.3).
        shutil.copytree(FIX / "calibration", self.tmp, dirs_exist_ok=True)
        for s in (self.tmp / "evals").glob("*/suite.json"):       # an ecosystem's own suites are not part of these tests
            if s.parent.name != SUITE:
                shutil.rmtree(s.parent)
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
        # T1.4: a minor finding with verdict fail is invalid output (a minor never fails the verdict), not a false fail.
        self.respond(E001=answer("E001", ["CC06"], "fail", severity="minor"))
        rep, _ = self.run_suite()
        self.assertEqual((rep["metrics"]["invalid_runs"], rep["metrics"]["false_fail_rate"]), (3, 0.0))
        self.assertFalse(next(c for c in rep["cases"] if c["case"] == "E001")["pass"])
        self.respond(E001=answer("E001", ["CC03"], "fail"))                     # a must_not_find rule: a false fail
        rep, _ = self.run_suite(use_cache=False)
        self.assertEqual((rep["metrics"]["invalid_runs"], rep["metrics"]["false_fail_rate"]), (0, 0.5))
        self.assertFalse(next(c for c in rep["cases"] if c["case"] == "E001")["pass"])


class LimitTests(EvalBase):
    """T2.5 items 5 and 8: the reviewer invalid-output and false-finding limits, enforced; a metric that can't be
    calculated fails closed, except where the rulebook has no rules of that severity or no run found anything."""

    def test_invalid_output_up_to_five_percent_passes(self):
        hit = answer("E002", ["CC01"], "fail")
        self.respond(E002=[answer("E002", ["CC01"], "fail", fence=True), hit, hit])
        rep, code = self.run_suite()
        self.assertEqual((code, rep["metrics"]["invalid_output_rate"], rep["threshold_failures"]), (0, 0.048, []))

    def test_invalid_output_above_five_percent_fails_the_suite(self):
        h2, h3 = answer("E002", ["CC01"], "fail"), answer("E003", ["CC02"], "fail")
        self.respond(E002=[answer("E002", ["CC01"], "fail", fence=True), h2, h2],
                     E003=[answer("E003", ["CC02"], "fail", fence=True), h3, h3])
        rep, code = self.run_suite()
        self.assertEqual(code, 1)
        self.assertEqual(rep["threshold_failures"], ["invalid_output_rate 0.095 (threshold 0.05)"])

    def test_false_findings_above_fifteen_percent_of_all_findings_fail_the_suite(self):
        self.respond(E001=answer("E001", ["CC06"], "pass", severity="minor"))   # a note on a clean case: not wanted
        rep, code = self.run_suite()
        m = rep["metrics"]
        self.assertEqual((m["false_findings_all_runs"], m["findings_all_runs"], m["false_finding_rate"]), (3, 18, 0.167))
        self.assertEqual(code, 1)
        self.assertEqual(rep["threshold_failures"], ["false_finding_rate 0.167 (threshold 0.15)"])

    def test_a_suite_with_no_clean_cases_fails_closed(self):
        for cid in ("E001", "E007"):
            shutil.rmtree(self.tmp / f"evals/{SUITE}/cases/{cid}")
            (self.tmp / f"evals/{SUITE}/keys/{cid}.json").unlink()
            self.keys.pop(cid)
        self.respond()
        rep, code = self.run_suite()
        self.assertEqual(code, 1)
        self.assertEqual(rep["threshold_failures"],
                         ["false_fail_rate not calculable (no clean cases; threshold 0.2): fails closed"])
        self.assertIn("recall_blocker: the rulebook has no blocker rules", rep["threshold_skipped"])
        self.assertIn("below threshold: false_fail_rate not calculable", "\n".join(self.out))

    def test_missing_severity_cases_fail_only_when_the_rulebook_has_that_severity(self):
        th = self.re.thresholds()
        m = {"recall_blocker": None, "recall_major": 1.0, "false_fail_rate": 0.0, "verdict_match": 1.0,
             "invalid_output_rate": 0.0, "false_finding_rate": None, "findings_all_runs": 0}
        fails, skipped = self.re.check_thresholds(m, th, "reviewer", {"CC01": "blocker", "CC02": "major"})
        self.assertEqual(fails, ["recall_blocker not calculable (no planted blocker cases; threshold 1.0): fails closed"])
        self.assertEqual(skipped, ["false_finding_rate: no findings in any run (0 of 0)"])
        fails, skipped = self.re.check_thresholds({**m, "recall_major": None}, th, "reviewer", {"CC02": "minor"})
        self.assertEqual(fails, [])
        self.assertEqual(skipped[:2], ["recall_blocker: the rulebook has no blocker rules",
                                       "recall_major: the rulebook has no major rules"])
        fails, _ = self.re.check_thresholds({**m, "invalid_output_rate": None}, th, "reviewer", {})
        self.assertEqual(fails, ["invalid_output_rate not calculable (no runs or agent calls; threshold 0.05): fails closed"])

    def test_interview_and_charter_limits_fail_closed(self):
        th = self.re.thresholds()
        good = {"field_recall": 0.95, "contradictions_caught_rate": 1.0, "contradictions_invented": 0,
                "repeated_question_rate": 0.05, "injection_flagged_rate": 1.0, "false_ready_rate": 0.0,
                "invalid_output_rate": 0.0}
        self.assertEqual(self.re.check_thresholds(good, th, "interview"), ([], []))
        fails, _ = self.re.check_thresholds({**good, "contradictions_caught_rate": None, "false_ready_rate": 0.25,
                                             "repeated_question_rate": 0.11}, th, "interview")
        self.assertEqual(fails, ["contradictions_caught_rate not calculable (no planted contradictions; threshold 1.0): "
                                 "fails closed", "repeated_question_rate 0.11 (threshold 0.1)",
                                 "false_ready_rate 0.25 (threshold 0)"])
        fails, skipped = self.re.check_thresholds({**good, "field_recall": None}, th, "interview", smoke=True)
        self.assertEqual((fails, len(skipped)), ([], 1))
        self.assertEqual(self.re.check_thresholds({"invented_cases": 0, "invalid_output_rate": 0.1}, th, "charter"),
                         ([], []))
        fails, _ = self.re.check_thresholds({"invented_cases": 1, "invalid_output_rate": None}, th, "charter")
        self.assertEqual(fails, ["invented_cases 1 (threshold 0)",
                                 "invalid_output_rate not calculable (no runs or agent calls; threshold 0.1): fails closed"])


class SpendLogTests(EvalBase):
    """T2.5 item 7: a running token total across invocations against the overall ceiling in the spend log's start
    line. A missing log, or one without its start line, never counts as zero: every run is refused."""

    def setUp(self):
        super().setUp()
        caps = json.loads((self.tmp / "config/caps.json").read_text(encoding="utf-8"))
        caps["evals"]["spend_log"] = "required"
        self.dump("config/caps.json", caps)
        self.spend = self.tmp / "cache/evals/spend.jsonl"

    def start(self, ceiling=9_000_000, starting=0):
        self.spend.parent.mkdir(parents=True, exist_ok=True)
        self.spend.write_text(json.dumps({"kind": "start", "date": "2026-11-02", "name": "T2.5", "since": "2026-10-30",
                                        "ceiling_tokens": ceiling, "starting_total": starting, "records": 0}) + "\n",
                            encoding="utf-8")

    def lines(self):
        return [json.loads(l) for l in self.spend.read_text(encoding="utf-8").splitlines()]

    def test_every_call_is_logged_and_deleting_the_log_refuses_the_next_run(self):
        self.start(starting=1_000)
        rep, code = self.run_suite()
        self.assertEqual(code, 0, self.out)
        spends = self.lines()[1:]
        self.assertEqual(len(spends), 21)
        self.assertEqual(sum(l["tokens"] for l in spends), rep["usage"]["tokens_new"])
        self.assertEqual(self.re.spend_state()[1], 1_000 + rep["usage"]["tokens_new"])
        self.assertTrue(any(l.startswith("Spend (T2.5): 1,000 of 9,000,000") for l in self.out), self.out)
        self.spend.unlink()
        with self.assertRaises(self.re.Refused) as cm:
            self.run_suite(use_cache=False)
        self.assertIn("never counted as zero", str(cm.exception))
        self.assertEqual(len(self.calls()), 21)                            # nothing ran

    def test_a_log_without_its_start_line_or_with_an_unreadable_line_refuses(self):
        self.spend.parent.mkdir(parents=True, exist_ok=True)
        self.spend.write_text(json.dumps({"kind": "spend", "tokens": 5}) + "\n", encoding="utf-8")
        with self.assertRaises(self.re.Refused) as cm:
            self.run_suite()
        self.assertIn("no start line", str(cm.exception))
        self.start()
        with self.spend.open("a", encoding="utf-8") as fh:
            fh.write("not json\n")
        with self.assertRaises(self.re.Refused):
            self.run_suite()
        self.assertEqual(len(self.calls()), 0)

    def test_an_estimate_above_what_is_left_is_refused_before_any_call(self):
        self.start(ceiling=1_000_000, starting=999_000)
        with self.assertRaises(self.re.Refused) as cm:
            self.run_suite()
        self.assertIn("above what is left", str(cm.exception))
        self.start(ceiling=1_000_000, starting=1_000_000)
        with self.assertRaises(self.re.Refused) as cm:
            self.run_suite()
        self.assertIn("ceiling (1,000,000 tokens) is reached", str(cm.exception))
        self.assertEqual(len(self.calls()), 0)

    def test_the_start_line_is_the_approvers_step_and_counts_earlier_records(self):
        with self.assertRaises(self.re.Refused) as cm:                     # no terminal here
            self.re.spend_start("2026-10-30", 9_000_000, "T2.5")
        self.assertIn("approver's step", str(cm.exception))
        self.start()
        rep, _ = self.run_suite()
        self.spend.unlink()
        gate = importlib.import_module("gate")
        real, gate.interactive_terminal = gate.interactive_terminal, lambda: True
        try:
            self.re.spend_start("2000-01-01", 9_000_000, "T2.5", out=lambda *_: None)
            start = self.lines()[0]
            self.assertEqual((start["starting_total"], start["records"]), (rep["usage"]["tokens_all"], 21))
            with self.assertRaises(self.re.Refused) as cm:
                self.re.spend_start("2000-01-01", 9_000_000, "T2.5")
            self.assertIn("--recreate", str(cm.exception))
            self.re.spend_start("2099-01-01", 9_000_000, "T2.5", recreate=True, out=lambda *_: None)
            self.assertEqual(self.lines()[0]["starting_total"], 0)
            self.assertEqual(len(list(self.spend.parent.glob("spend-*.jsonl"))), 1)   # the old log is kept
        finally:
            gate.interactive_terminal = real


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

    def test_a_key_edited_after_a_pass_refuses_lock_until_the_suite_runs_again(self):
        """T2.5 item 10: a full report is bound to its suite's files, keys, thresholds and scoring code."""
        rep, _ = self.run_suite()
        fp = rep["suite_fingerprint"]
        self.assertIn(f"evals/{SUITE}/keys/E002.json", fp)
        self.assertIn(f"evals/{SUITE}/cases/E002/artifact.md", fp)
        self.assertIn(f"evals/{SUITE}/suite.json", fp)
        self.assertTrue(fp["evals/thresholds.json"] and fp["evals/run_evals.py"])
        key = self.tmp / f"evals/{SUITE}/keys/E002.json"
        doc = json.loads(key.read_text(encoding="utf-8"))
        doc["why"] += " (edited)"
        key.write_text(json.dumps(doc), encoding="utf-8")
        probs = self.problems()
        self.assertTrue(any("stale" in p and f"keys/E002.json" in p for p in probs), probs)
        self.run_suite()
        self.assertEqual(self.problems(), [])
        th = self.tmp / "evals/thresholds.json"                            # the thresholds count too
        th.write_text(th.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertTrue(any("stale" in p and "evals/thresholds.json" in p for p in self.problems()))

    def test_a_report_without_a_suite_fingerprint_is_stale(self):
        self.run_suite()
        f = self.reports()[0]
        rep = json.loads(f.read_text(encoding="utf-8"))
        rep.pop("suite_fingerprint")
        f.write_text(json.dumps(rep), encoding="utf-8")
        self.assertTrue(any("records no suite fingerprint" in p for p in self.problems()), self.problems())

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
        g.doctor_failures = lambda: []                                     # the doctor rule: test_doctor_t14
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


class DiscriminationTests(EvalBase):
    """T1.4 (suite design rule 5): one run per case on config/models.json discrimination_model, after a model check;
    those reports never count for lock and never make another report stale or current."""
    WEAK = "claude-haiku-5-5"

    def problems(self):
        return self.ec.lock_problems(cli=CLI)

    def test_one_run_per_case_on_the_weaker_model_after_a_model_check(self):
        rep, code = self.run_suite("discrimination")
        calls = self.calls()
        self.assertEqual(len(calls), 8)                                    # the model check, then 7 cases x 1 run
        self.assertTrue(all(c["argv"][c["argv"].index("--model") + 1] == self.WEAK for c in calls))
        self.assertEqual((code, rep["mode"], rep["model"], rep["counts_for_lock"], rep["too_easy"]),
                         (0, "discrimination", self.WEAK, False, True))
        self.assertIn("TOO EASY", "\n".join(self.out))

    def test_a_weaker_model_that_fails_a_case_shows_the_suite_discriminates(self):
        self.respond(E002=answer("E002", [], "pass"))
        rep, code = self.run_suite("discrimination")
        self.assertEqual((code, rep["too_easy"]), (0, False))
        self.assertIn("failed 1 of 7 case(s)", "\n".join(self.out))

    def test_the_model_check_refuses_a_model_the_cli_does_not_run_exactly(self):
        os.environ["FAKE_CLAUDE_MODEL_REPORTED"] = self.WEAK + "-20261001"
        with self.assertRaisesRegex(self.re.Refused, "the CLI reported"):
            self.run_suite("discrimination")
        os.environ.pop("FAKE_CLAUDE_MODEL_REPORTED")
        os.environ["FAKE_CLAUDE_MODE"] = "error"
        with self.assertRaisesRegex(self.re.Refused, "did not run model"):
            self.run_suite("discrimination")
        self.assertEqual((len(self.calls()), self.reports()), (2, []))  # no case ran, no report

    def test_the_model_must_be_set_and_weaker_than_the_pinned_one(self):
        models = json.loads((self.tmp / "config/models.json").read_text(encoding="utf-8"))
        for value in (None, "", models["default"]):
            models["discrimination_model"] = value
            self.dump("config/models.json", models)
            with self.assertRaises(self.lc.LabError):
                self.run_suite("discrimination", estimate_only=True)

    def test_never_counts_for_lock_and_never_changes_another_reports_standing(self):
        self.run_suite("discrimination")
        self.assertIn("no evaluation reports", self.problems()[0])         # alone, it is not a report at all
        self.run_suite()
        self.assertEqual(self.problems(), [])
        self.run_suite("discrimination", use_cache=False)                  # newer, yet the full report stays current
        self.run_suite("discrimination", use_cache=False, only={"E002"})   # a partial one is ignored too
        self.assertEqual(self.problems(), [])
        rb = self.tmp / "rules/calibration-critic.md"
        rb.write_text(rb.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        before = self.problems()
        self.assertTrue(before)
        self.run_suite("discrimination", use_cache=False)                  # on the edited rulebook: still stale
        self.assertEqual(self.problems(), before)
        modes = {json.loads(f.read_text(encoding="utf-8"))["mode"] for f in self.reports()}
        self.assertEqual(modes, {"discrimination", "discrimination-partial", "full"})


class ReportAndVerdictTests(EvalBase):
    def test_a_report_is_never_overwritten_within_the_same_second(self):
        import datetime as real

        class Frozen(real.datetime):
            @classmethod
            def now(cls, tz=None):
                return real.datetime(2026, 10, 28, 6, 0, 0, tzinfo=tz)
        self.re.datetime = type("dt", (), {"datetime": Frozen, "timezone": real.timezone})
        self.run_suite("quick")
        self.run_suite("quick", use_cache=False)
        self.run_suite("quick", use_cache=False)
        names = sorted(f.name for f in self.reports())
        self.assertEqual(names, ["20261028T060000Z-calibration-critic-quick-2.json",
                                 "20261028T060000Z-calibration-critic-quick-3.json",
                                 "20261028T060000Z-calibration-critic-quick.json"])

    def test_a_minor_finding_never_fails_the_verdict(self):
        """T1.4: the reserved DR07 is minor; a clean list with a DR07 finding passes, and 'fail' needs a blocker or major."""
        schema = json.loads((self.tmp / "schemas/findings.schema.json").read_text(encoding="utf-8"))
        doc = json.loads(answer("E001", ["DR07"], "pass", severity="minor"))
        rulebook = {"DR07": "minor", "CC01": "major"}
        self.assertEqual(self.re.vf.validate(doc, schema, rulebook, {}), [])
        doc["verdict"] = "fail"
        self.assertTrue(any("minor findings never fail the verdict" in e
                            for e in self.re.vf.validate(doc, schema, rulebook, {})))
        doc["findings"][0]["severity"] = "major"                         # the lock holds DR07 at minor
        self.assertTrue(any("must be 'minor'" in e for e in self.re.vf.validate(doc, schema, rulebook, {})))
        key = {"must_find": ["DR07"], "must_not_find": ["CC01"], "verdict": "pass"}
        ok = {"valid": True, "found": ["DR07"], "verdict": "pass"}
        self.assertTrue(self.re.run_passes(ok, key))                      # the clean injection case passes
        self.assertFalse(self.re.run_passes({**ok, "found": []}, key))    # missing DR07 is a miss


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
