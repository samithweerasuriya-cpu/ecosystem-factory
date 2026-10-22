"""Engine core tests, ported from the author's earlier private lab and made generic.

Run all engine tests (with the logs-unchanged guard): python engine/run_tests.py
"""
import importlib
import json
import unittest

from support import LabTestBase


class StateMachineTests(LabTestBase):
    def test_happy_path_to_done(self):
        j, _ = self.spec_to_gate()
        self.assertEqual(self.lc.load_state(j)["state"], "GATE")
        self.lc.approve_gate(j, "ok")
        self.assertTrue(self.lc.verify_gate(j, "G1-spec")[0])
        self.lc.apply(j, "complete")
        self.assertEqual(self.lc.load_state(j)["state"], "DONE")

    def test_human_only_events_blocked(self):
        j, _ = self.spec_to_gate()
        with self.assertRaises(self.lc.LabError):
            self.lc.apply(j, "approve")

    def test_cannot_skip_review(self):
        j = self.lc.new_job("spec", "skip", "x")["job_id"]
        self.lc.apply(j, "dispatch")
        with self.assertRaises(self.lc.LabError):
            self.lc.apply(j, "review_pass")

    def test_artifact_ready_requires_last_stage(self):
        j = self.lc.new_job("spec", "early", "x")["job_id"]
        self.lc.apply(j, "dispatch")
        art = self.write(f"jobs/{j}/drafts/v1.md")
        with self.assertRaises(self.lc.LabError):
            self.lc.apply(j, "artifact_ready", artifact=art)

    def test_critic_cap_escalates(self):
        lc = self.lc
        j = lc.new_job("spec", "critic-cap", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        for i in range(2):
            lc.apply(j, "review_fail")
            lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v{i+2}.md", str(i)))
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "review_fail")
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["resume_to"], st["last_failed_by"]), ("ESCALATED", "REVISING", "critic"))
        lc.apply(j, "resume")
        self.assertEqual(lc.load_state(j)["state"], "REVISING")

    def test_total_revision_cap(self):
        lc = self.lc
        j = lc.new_job("spec", "total-cap", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        n = 2
        for _ in range(2):
            lc.apply(j, "review_fail"); lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v{n}.md", str(n))); n += 1
        lc.apply(j, "review_pass")
        self.assertEqual(lc.load_state(j)["state"], "VERIFY")
        lc.apply(j, "review_fail")
        lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v{n}.md", "z"))
        lc.apply(j, "review_pass")
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "review_fail")

    def test_gate_token_void_after_change(self):
        j, art = self.spec_to_gate()
        self.lc.approve_gate(j)
        (self.tmp / art).write_text("edited after approval")
        ok, why = self.lc.verify_gate(j, "G1-spec")
        self.assertFalse(ok)
        self.assertIn("void", why)

    def test_gate_rejection_cap(self):
        lc = self.lc
        j, _ = self.spec_to_gate()
        for i in range(3):
            lc.reject_gate(j, f"fix {i}")
            lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/r{i}.md", str(i)))
            lc.apply(j, "review_pass"); lc.apply(j, "review_pass")
        with self.assertRaises(lc.CapExceeded):
            lc.reject_gate(j, "again")

    def test_child_job_needs_approved_parent(self):
        j, _ = self.spec_to_gate()
        with self.assertRaises(self.lc.LabError):
            self.lc.new_job("tickets", "tk1", "x", parent=j)
        self.lc.approve_gate(j)
        st = self.lc.new_job("tickets", "tk1", "x", parent=j)
        self.assertEqual(st["state"], "PLANNED")

    def test_infra_errors_block_and_resume(self):
        lc = self.lc
        j = lc.new_job("report", "infra", "x")["job_id"]
        lc.apply(j, "dispatch")
        lc.apply(j, "infra_error"); lc.apply(j, "infra_error")
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "infra_error")
        self.assertEqual(lc.load_state(j)["state"], "BLOCKED")
        lc.apply(j, "resume")
        self.assertEqual(lc.load_state(j)["state"], "WORKING")

    def test_agent_call_cap(self):
        """Changed in T0.6: repeated calls in one step are now refused (fix c), so the cap is reached
        with one call per step instead of 25 calls to the same agent."""
        lc = self.lc
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        caps["agent_calls_per_job"] = 3
        self.dump("config/caps.json", caps)
        j = lc.new_job("report", "calls", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.record_call(j, "researcher")
        lc.apply(j, "stage_done"); lc.record_call(j, "reporter")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        lc.record_call(j, "verifier")                       # 3 calls
        lc.apply(j, "review_fail")
        with self.assertRaises(lc.CapExceeded):
            lc.record_call(j, "reporter")
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")

    def test_route_without_gate_ends_done(self):
        lc = self.lc
        j = lc.new_job("report", "standup", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md"))
        self.assertEqual(lc.load_state(j)["state"], "VERIFY")
        lc.apply(j, "review_pass")
        self.assertEqual(lc.load_state(j)["state"], "DONE")

    def test_script_fail_cap(self):
        """Ported from the connector test-fail cap: a failing script stage goes to fix_with, capped."""
        lc = self.lc
        j = lc.new_job("build", "fail-cap", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.run_script(j)
        self.assertEqual(lc.load_state(j)["stage"], "builder")
        lc.apply(j, "fixed"); lc.run_script(j)
        lc.apply(j, "fixed")
        with self.assertRaises(lc.CapExceeded):
            lc.run_script(j)
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["resume_to"]), ("ESCALATED", "WORKING"))


class HookTests(LabTestBase):
    def bash(self, cmd, tool="Bash"):
        return self.run_hook({"tool_name": tool, "tool_input": {"command": cmd}})

    def test_malformed_input_fails_closed(self):
        self.assertEqual(self.run_hook(None, raw="not json"), 2)

    def test_normal_write_allowed(self):
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": str(self.tmp / "jobs/x/drafts/v1.md")}}), 0)

    def test_gate_write_blocked(self):
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": str(self.tmp / "jobs/20260101-spec-a/gates/G1-spec.json")}}), 2)

    def test_state_edit_blocked(self):
        self.assertEqual(self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": "jobs/20260101-spec-a/state.json"}}), 2)

    def test_outside_repo_blocked(self):
        outside = self.tmp.parent / "elsewhere.txt"
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": str(outside)}}), 2)

    def test_gate_py_blocked(self):
        self.assertEqual(self.bash("python engine/gate.py approve x"), 2)

    def test_shell_write_to_gate_blocked(self):
        self.assertEqual(self.bash("echo {} > jobs/20260101-spec-a/gates/G1-spec.json"), 2)

    def test_state_py_allowed(self):
        for cmd in ("python engine/state.py event 20260101-spec-a dispatch",
                    ".venv/Scripts/python.exe engine/state.py status",
                    "py -3 engine/state.py run 20260101-build-a"):
            self.assertEqual(self.bash(cmd), 0, cmd)

    def test_secret_read_blocked(self):
        self.assertEqual(self.bash("cat .env"), 2)

    def test_git_push_blocked(self):
        self.assertEqual(self.bash("git push origin main"), 2)

    def test_gate_audit_write_blocked(self):
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": str(self.tmp / "logs/gate-audit.jsonl")}}), 2)
        self.assertEqual(self.bash("echo {} >> logs/gate-audit.jsonl"), 2)

    WSL = 'wsl -d Ubuntu -- bash -lc "cd /mnt/c/lab/tools/deploy && {}"'

    def test_wsl_gated_shell_needs_gate(self):
        j = self.lc.new_job("build", "wsl", "x")["job_id"]
        self.lc.set_active(j)
        self.assertEqual(self.bash(self.WSL.format("deploytool push --folder 1")), 2)

    def test_wsl_secret_reads_blocked(self):
        for cmd in ("wsl -d Ubuntu -- cat /mnt/c/lab/.env",
                    self.WSL.format("cat master.key"),
                    self.WSL.format("grep TOKEN ../../../.env")):
            self.assertEqual(self.bash(cmd), 2, cmd)

    def test_wsl_protected_write_and_gate_blocked(self):
        for cmd in ('wsl -d Ubuntu -- bash -lc "echo {} > /mnt/c/lab/jobs/20260101-spec-a/gates/G1-spec.json"',
                    'wsl -d Ubuntu -- bash -lc "rm /mnt/c/lab/jobs/20260101-spec-a/state.json"',
                    'wsl -d Ubuntu -- python3 /mnt/c/lab/engine/gate.py approve x'):
            self.assertEqual(self.bash(cmd), 2, cmd)

    def test_wsl_normal_test_run_allowed(self):
        self.assertEqual(self.bash(self.WSL.format("make test")), 0)

    def test_powershell_gate_py_blocked(self):
        self.assertEqual(self.bash("py -3 engine\\gate.py approve x", tool="PowerShell"), 2)

    def test_powershell_write_to_gate_blocked(self):
        self.assertEqual(self.bash("Set-Content jobs\\20260101-spec-a\\gates\\G1-spec.json '{}'", tool="PowerShell"), 2)

    def test_monitor_secret_read_blocked(self):
        self.assertEqual(self.run_hook({"tool_name": "Monitor", "tool_input": {"command": "tail -f .env", "description": "x"}}), 2)

    def test_operate_mode_locks_rules(self):
        p = {"tool_name": "Edit", "tool_input": {"file_path": "rules/test-rulebook.md"}}
        self.assertEqual(self.run_hook(p), 0)
        (self.tmp / ".lab").mkdir(exist_ok=True)
        (self.tmp / ".lab/OPERATE").write_text("on")
        self.assertEqual(self.run_hook(p), 2)
        for path in ("engine/labcore.py", "config/scripts.json"):
            self.assertEqual(self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": path}}), 2, path)

    def test_unlisted_mcp_tool_blocked(self):
        """Ported from 'non-allowed MCP write blocked': now any MCP tool not in config is blocked."""
        self.assertEqual(self.run_hook({"tool_name": "mcp__whiteboard__board_create", "tool_input": {}}), 2)

    def test_listed_mcp_tool_allowed(self):
        self.assertEqual(self.run_hook({"tool_name": "mcp__docs__search_pages", "tool_input": {}}), 0)

    def test_gated_mcp_tool_needs_gate_and_state(self):
        lc = self.lc
        p = {"tool_name": "mcp__tracker__save_issue", "tool_input": {"title": "x"}}
        parent, _ = self.spec_to_gate()
        lc.approve_gate(parent)
        t = lc.new_job("tickets", "tk1", "x", parent=parent)["job_id"]
        lc.set_active(t)
        self.assertEqual(self.run_hook(p), 2)
        lc.apply(t, "dispatch")
        art = self.write(f"jobs/{t}/delivery/tickets.json", "[]")
        lc.apply(t, "artifact_ready", artifact=art)
        lc.apply(t, "review_pass")
        lc.approve_gate(t)
        self.assertEqual(self.run_hook(p), 2)  # approved but not yet DELIVERING
        lc.apply(t, "deliver")
        self.assertEqual(self.run_hook(p), 0)

    def test_gated_shell_needs_gate(self):
        j = self.lc.new_job("build", "push", "x")["job_id"]
        self.lc.set_active(j)
        self.assertEqual(self.bash("deploytool push --folder 1"), 2)

    def test_unlisted_mcp_read_tool_also_blocked(self):
        """New: no read/write guessing by tool name; a 'list' tool is blocked unless configured."""
        self.assertEqual(self.run_hook({"tool_name": "mcp__tracker__list_issues", "tool_input": {}}), 2)

    def test_script_outputs_protected(self):
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": "jobs/20260101-build-a/scripts/01-check-1.json"}}), 2)


class GateAuditTests(LabTestBase):
    def gate_cli(self):
        g = importlib.import_module("gate")
        g.confirm = lambda word: None  # tests have no tty; confirmation is covered by gate.confirm itself
        return g

    def audit(self):
        p = self.tmp / "logs" / "gate-audit.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_all_four_actions_are_audited(self):
        g = self.gate_cli()
        self.assertEqual(g.main(["lock"]), 0)
        self.assertEqual(g.main(["unlock"]), 0)
        j, art = self.spec_to_gate()
        self.assertEqual(g.main(["reject", j, "--feedback", "Treat TR16 as blocker"]), 0)
        self.lc.apply(j, "revised", artifact=art)
        self.lc.apply(j, "review_pass"); self.lc.apply(j, "review_pass")
        self.assertEqual(g.main(["approve", j, "--note", "ok"]), 0)
        recs = self.audit()
        self.assertEqual([r["action"] for r in recs], ["lock", "unlock", "reject", "approve"])
        rej, app = recs[2], recs[3]
        self.assertEqual(rej["feedback"], "Treat TR16 as blocker")
        self.assertEqual((rej["job_id"], rej["gate"], rej["state"]), (j, "G1-spec", "REVISING"))
        self.assertEqual((app["state"], app["note"]), ("APPROVED", "ok"))
        self.assertEqual(app["sha256"], self.lc.sha256_path(art))
        self.assertTrue(all(r["ts"] and r["approver"] and "os_user" not in r for r in recs))

    def test_failed_action_is_not_audited(self):
        g = self.gate_cli()
        j = self.lc.new_job("spec", "not-at-gate", "x")["job_id"]
        self.assertEqual(g.main(["approve", j]), 1)  # not at GATE
        self.assertEqual(self.audit(), [])


if __name__ == "__main__":
    unittest.main()
