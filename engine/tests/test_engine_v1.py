"""Tests for what is new in engine 0.1.0: route format v1, fan-out, script stages,
approver from config, the file-lock retry and stdlib-only imports."""
import copy
import importlib
import json
import subprocess
import sys
import unittest
from unittest import mock

from support import LabTestBase, REPO, TEST_ROUTES, TEST_SCRIPTS


class RouteFormatTests(LabTestBase):
    def errors(self, mutate):
        data = copy.deepcopy(TEST_ROUTES)
        mutate(data["routes"])
        return self.lc.route_errors(data, allowed_scripts=TEST_SCRIPTS["scripts"])

    def test_test_routes_and_shipped_demo_route_are_valid(self):
        self.assertEqual(self.lc.route_errors(copy.deepcopy(TEST_ROUTES), allowed_scripts=TEST_SCRIPTS["scripts"]), [])
        shipped = json.loads((REPO / "config/routes.json").read_text(encoding="utf-8"))
        self.assertEqual(self.lc.route_errors(shipped, allowed_scripts={}), [])

    def test_fanout_without_merge_stage_is_invalid(self):
        errs = self.errors(lambda r: r["survey"]["stages"].pop())
        self.assertTrue(any("followed by an agent (merge) stage" in e for e in errs), errs)

    def test_fanout_over_cap_is_invalid(self):
        errs = self.errors(lambda r: r["survey"]["stages"][1]["fanout"].update(max=9))
        self.assertTrue(any("exceeds caps.fanout_max" in e for e in errs), errs)

    def test_unknown_script_is_invalid(self):
        errs = self.errors(lambda r: r["build"]["stages"].__setitem__(1, {"script": "rm-everything"}))
        self.assertTrue(any("not in config/scripts.json" in e for e in errs), errs)

    def test_script_stage_needs_fix_with(self):
        errs = self.errors(lambda r: r["build"].pop("fix_with"))
        self.assertTrue(any("need fix_with" in e for e in errs), errs)

    def test_reviewer_cannot_author(self):
        errs = self.errors(lambda r: r["spec"].update(revise_with="critic"))
        self.assertTrue(any("critic reviews work it authors" in e for e in errs), errs)

    def test_delivery_needs_gate(self):
        errs = self.errors(lambda r: r["report"].update(deliver="reporter"))
        self.assertTrue(any("delivery needs a gate" in e for e in errs), errs)

    def test_schema_rejects_bad_shapes(self):
        for mutate in (lambda r: r["spec"].update(reviews=[]),                              # no review
                       lambda r: r["spec"]["reviews"][0].update(kind="judge"),              # unknown kind
                       lambda r: r["spec"].update(gate="approve-me"),                       # bad gate id
                       lambda r: r["spec"]["stages"].append({"agent": "Bad Name"}),          # agent name
                       lambda r: r["spec"]["stages"].append({"agent": "a", "script": "check"}),  # two kinds
                       lambda r: r["spec"].update(extra=True)):                              # unknown key
            self.assertTrue(self.errors(mutate), mutate)

    def test_invalid_routes_file_refuses_new_jobs(self):
        data = copy.deepcopy(TEST_ROUTES)
        data["routes"]["survey"]["stages"].pop()
        self.dump("config/routes.json", data)
        with self.assertRaises(self.lc.LabError):
            self.lc.new_job("spec", "xyz", "x")

    def test_bad_script_spec_is_invalid(self):
        bad = {"check": {"argv": "python -c 1", "timeout": 0}}
        errs = self.lc.route_errors(copy.deepcopy(TEST_ROUTES), allowed_scripts={**TEST_SCRIPTS["scripts"], **bad})
        self.assertTrue(any("argv must be" in e for e in errs) and any("timeout must be" in e for e in errs), errs)

    def test_schemacheck_agrees_with_jsonschema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed (engine itself never needs it)")
        schema = json.loads((REPO / "schemas/route.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        good = copy.deepcopy(TEST_ROUTES)
        bad = copy.deepcopy(TEST_ROUTES)
        bad["routes"]["spec"]["stages"].append({"agent": "a", "script": "check"})
        for doc in (good, bad):
            ours = not self.lc.schemacheck.check(doc, schema)
            theirs = jsonschema.Draft202012Validator(schema).is_valid(doc)
            self.assertEqual(ours, theirs)


class FanoutTests(LabTestBase):
    def to_fanout(self):
        lc = self.lc
        j = lc.new_job("survey", "groups", "x")["job_id"]
        lc.apply(j, "dispatch")
        lc.record_call(j, "planner")
        lc.apply(j, "stage_done")
        self.assertEqual(lc.load_state(j)["stage_kind"], "fanout")
        return j

    def test_item_list_fixed_once_and_within_max(self):
        lc = self.lc
        j = self.to_fanout()
        with self.assertRaises(lc.LabError):
            lc.set_fanout(j, ["a", "b", "c", "d"])  # over max 3
        with self.assertRaises(lc.LabError):
            lc.set_fanout(j, ["a", "a"])            # duplicate
        with self.assertRaises(lc.LabError):
            lc.set_fanout(j, [])
        lc.set_fanout(j, ["a", "b"])
        with self.assertRaises(lc.LabError):
            lc.set_fanout(j, ["a", "b", "c"])       # already fixed

    def test_calls_need_a_fixed_list_and_a_pending_item(self):
        lc = self.lc
        j = self.to_fanout()
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="a")  # list not fixed yet
        lc.set_fanout(j, ["a", "b"])
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher")             # no item
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "planner", item="a")      # wrong agent
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="z")   # unknown item
        lc.record_call(j, "researcher", item="a")
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="a")   # same item twice

    def test_each_item_reports_separately_and_merge_waits_for_all(self):
        lc = self.lc
        j = self.to_fanout()
        lc.set_fanout(j, ["a", "b", "c"])
        for i in "abc":
            lc.record_call(j, "researcher", item=i)
        with self.assertRaises(lc.LabError):
            lc.fanout_result(j, "a", "maybe")
        lc.fanout_result(j, "a", "done")
        with self.assertRaises(lc.LabError):
            lc.fanout_result(j, "a", "failed")          # already returned
        lc.fanout_result(j, "b", "failed", note="source unreachable")
        with self.assertRaises(lc.LabError):
            lc.apply(j, "stage_done")                   # c still running
        lc.fanout_result(j, "c", "done")
        st = lc.apply(j, "stage_done")
        self.assertEqual((st["stage"], st["stage_kind"]), ("merger", "agent"))
        log = [json.loads(l) for l in (self.tmp / "jobs" / j / "run.log.jsonl").read_text().splitlines()]
        results = [(e["item"], e["status"]) for e in log if e["event"] == "fanout_result"]
        self.assertEqual(results, [("a", "done"), ("b", "failed"), ("c", "done")])

    def test_result_needs_a_dispatched_item(self):
        lc = self.lc
        j = self.to_fanout()
        lc.set_fanout(j, ["a"])
        with self.assertRaises(lc.LabError):
            lc.fanout_result(j, "a", "done")            # never called

    def test_item_calls_count_against_the_job_cap(self):
        lc = self.lc
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        caps["agent_calls_per_job"] = 3
        self.dump("config/caps.json", caps)
        j = self.to_fanout()                            # 1 call (planner)
        lc.set_fanout(j, ["a", "b", "c"])
        lc.record_call(j, "researcher", item="a")
        lc.record_call(j, "researcher", item="b")       # 3 calls
        with self.assertRaises(lc.CapExceeded):
            lc.record_call(j, "researcher", item="c")
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")

    def test_item_outside_fanout_is_refused(self):
        lc = self.lc
        j = lc.new_job("spec", "no-fanout", "x")["job_id"]
        lc.apply(j, "dispatch")
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="a")


class ScriptStageTests(LabTestBase):
    def to_script(self, route="build"):
        lc = self.lc
        j = lc.new_job(route, "script-run", "x")["job_id"]
        lc.apply(j, "dispatch")
        lc.apply(j, "stage_done")
        self.assertEqual(lc.load_state(j)["stage_kind"], "script")
        return j

    def outputs(self, j):
        return sorted((self.tmp / "jobs" / j / "scripts").glob("*.json"))

    def test_pass_saves_output_and_moves_on(self):
        lc = self.lc
        j = self.to_script()
        self.write(f"jobs/{j}/ok", "")
        st, rec = lc.run_script(j)
        self.assertEqual((rec["exit_code"], rec["timed_out"]), (0, False))
        self.assertEqual(st["stage"], "summariser")
        saved = json.loads(self.outputs(j)[0].read_text())
        self.assertEqual((saved["script"], saved["exit_code"]), ("check", 0))
        self.assertIn("stdout", saved)
        self.assertIn("argv", saved)

    def test_failure_goes_to_fix_with_then_back_to_the_script(self):
        lc = self.lc
        j = self.to_script()
        st, rec = lc.run_script(j)
        self.assertEqual(rec["exit_code"], 1)
        self.assertEqual((st["state"], st["stage"], st["fixing"]), ("WORKING", "builder", True))
        with self.assertRaises(lc.LabError):
            lc.run_script(j)                            # fixing, not at the script
        st = lc.apply(j, "fixed")
        self.assertEqual((st["stage"], st["stage_kind"]), ("check", "script"))
        self.write(f"jobs/{j}/ok", "")
        st, _ = lc.run_script(j)
        self.assertEqual(st["stage"], "summariser")
        self.assertEqual(len(self.outputs(j)), 2)       # every attempt is kept

    def test_timeout_is_a_failure(self):
        lc = self.lc
        j = self.to_script("slowbuild")
        st, rec = lc.run_script(j)
        self.assertTrue(rec["timed_out"])
        self.assertLess(rec["duration_s"], 8)
        self.assertEqual(st["stage"], "builder")

    def test_script_stage_cannot_be_completed_by_hand(self):
        lc = self.lc
        j = self.to_script()
        with self.assertRaises(lc.LabError):
            lc.apply(j, "stage_done")
        with self.assertRaises(lc.LabError):
            lc.apply(j, "script_fail")

    def test_final_script_stage_produces_the_artifact(self):
        lc = self.lc
        j = lc.new_job("package", "pkg", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        st, rec = lc.run_script(j)
        self.assertEqual(rec["exit_code"], 0)
        self.assertEqual((st["state"], st["artifact_path"]), ("REVIEW", f"jobs/{j}/delivery/pkg.txt"))

    def test_state_cli_run_exit_codes(self):
        j = self.to_script()
        cli = lambda: subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "run", j],
                                     capture_output=True, text=True, env=self.hook_env())
        p = cli()
        self.assertEqual(p.returncode, 4, p.stderr)
        self.assertIn("FAILED", p.stdout)


class ApproverTests(LabTestBase):
    def test_approver_comes_from_config(self):
        self.dump("config/gates.json", {"approver": "Test Approver"})
        j, _ = self.spec_to_gate()
        self.lc.approve_gate(j)
        tok = json.loads((self.tmp / "jobs" / j / "gates/G1-spec.json").read_text())
        self.assertEqual(tok["approved_by"], "Test Approver")

    def test_fallback_is_the_os_user_removed(self):
        """Changed in T0.12: no OS user fallback. Without an approver name every gate action is refused."""
        import getpass
        os_user = getpass.getuser()
        j, _ = self.spec_to_gate()
        for cfg in ({"approver": ""}, {}):
            self.dump("config/gates.json", cfg)
            with self.assertRaises(self.lc.LabError) as cm:
                self.lc.approve_gate(j)
            self.assertIn("no approver name", str(cm.exception))
        self.assertFalse((self.tmp / f"jobs/{j}/gates/G1-spec.json").exists())
        self.assertEqual(self.lc.load_state(j)["state"], "GATE")
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        g.eval_lock_problems = lambda: []                                              # T0.13 rule tested in test_evals_t13
        self.assertEqual(g.main(["lock"]), 1)                                          # refused, not audited
        self.assertFalse((self.tmp / "logs/gate-audit.jsonl").exists())
        self.assertFalse((self.tmp / ".lab/OPERATE").exists())                         # and nothing changed
        self.dump("config/gates.json", {"approver": "Test Approver"})                 # with the config value
        self.lc.approve_gate(j)
        self.lc.gate_audit("approve", j)
        self.assertEqual(g.main(["lock"]), 0)
        audit = (self.tmp / "logs/gate-audit.jsonl").read_text(encoding="utf-8")
        token = (self.tmp / f"jobs/{j}/gates/G1-spec.json").read_text(encoding="utf-8")
        self.assertNotIn(os_user, audit)
        self.assertNotIn(os_user, token)
        self.assertNotIn("os_user", audit)

class EngineRobustnessTests(LabTestBase):
    def test_save_json_retries_a_briefly_locked_file(self):
        """New (the retry existed in the source without a test): two 'in use' errors, then success."""
        target = self.tmp / "state-test.json"
        real_replace = type(target).replace
        calls = {"n": 0}

        def flaky(self_path, dst):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError("file in use")
            return real_replace(self_path, dst)

        with mock.patch.object(type(target), "replace", flaky), mock.patch.object(self.lc.time, "sleep"):
            self.lc.save_json(target, {"ok": True})
        self.assertEqual(json.loads(target.read_text()), {"ok": True})
        self.assertEqual(calls["n"], 3)

    def test_save_json_gives_up_after_five_attempts(self):
        target = self.tmp / "state-test.json"
        with mock.patch.object(type(target), "replace", side_effect=PermissionError("locked")), \
                mock.patch.object(self.lc.time, "sleep"):
            with self.assertRaises(PermissionError):
                self.lc.save_json(target, {"ok": True})

    def test_engine_imports_without_venv_or_site_packages(self):
        """The hook, labcore and validators are stdlib only: import them with -I -S (no site-packages)."""
        code = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/hooks');"
                "import labcore, schemacheck, state, gate, validate_findings, pre_tool_use;"
                "assert not any('site-packages' in p for p in sys.path), sys.path; print('ok')")
        p = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(self.tmp / "engine")],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ok", p.stdout)

    def test_infra_error_allowed_during_review(self):
        """New: a reviewer whose output stays invalid is recorded as infra_error (the source refused it in REVIEW)."""
        lc = self.lc
        j = lc.new_job("spec", "review-infra", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        st = lc.apply(j, "infra_error")
        self.assertEqual((st["state"], st["counters"]["infra_errors"]), ("REVIEW", 1))

    def test_review_infra_errors_hit_the_retry_cap_and_block_without_resetting_review_counters(self):
        lc = self.lc
        j = lc.new_job("spec", "review-cap", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        lc.apply(j, "review_fail")                                   # critic_revisions 1, total 1
        lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v2.md", "v2"))
        lc.apply(j, "review_pass")                                   # now VERIFY
        before = dict(lc.load_state(j)["counters"])
        lc.apply(j, "infra_error"); lc.apply(j, "infra_error")       # caps.infra_retries = 2
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "infra_error")
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["resume_to"]), ("BLOCKED", "VERIFY"))
        self.assertEqual(st["counters"]["infra_errors"], 3)
        for k in ("critic_revisions", "verifier_revisions", "total_revisions", "gate_rejections"):
            self.assertEqual(st["counters"][k], before[k], k)
        self.assertEqual((before["critic_revisions"], before["total_revisions"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
