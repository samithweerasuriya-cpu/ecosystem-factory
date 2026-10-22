"""T0.10: delivery path test. The shipped demo route runs from NEW to DONE with stand-in agents,
driven through the command-line tools and the real hooks, with automatic call results switched off
(every result comes from the post hook or state.py result). Plus: rejection, AWAITING_INPUT, a
reference and an evidence failure, delivery refused after an edit, every cap (exit code 3) and resume,
forged writes at GATE, and the main path as an internal job ending in state.py check-private."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from support import REPO, LabTestBase

TIER = "full"  # end-to-end, slow: skipped by run_tests.py --fast
import demo_support as ds

MAIN_TRAIL = [("new", "PLANNED", None), ("dispatch", "WORKING", "demo-planner"),
              ("stage_done", "WORKING", "demo-researcher"), ("fanout", "WORKING", "demo-researcher"),
              ("stage_done", "WORKING", "demo-writer"), ("needs_input", "AWAITING_INPUT", "demo-writer"),
              ("answered", "WORKING", "demo-writer"), ("artifact_ready", "REVIEW", "demo-critic"),
              ("review_fail", "REVISING", "demo-writer"), ("revised", "REVIEW", "demo-critic"),
              ("review_pass", "VERIFY", "demo-verifier"), ("review_pass", "GATE", None)]


class DeliveryBase(LabTestBase):
    auto_result = False

    @classmethod
    def setUpClass(cls):
        cls.server, cls.base = ds.start_pages()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        super().setUp()
        for name in ("routes.json", "reviewers.json", "scripts.json"):           # the shipped demo config
            shutil.copy2(REPO / "config" / name, self.tmp / "config" / name)
        ds.prepare_root(self.tmp)
        self.d = ds.Driver(self.tmp, self.base)

    def set_caps(self, **kw):
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        for k, v in kw.items():
            if isinstance(v, dict):
                caps[k].update(v)
            else:
                caps[k] = v
        self.dump("config/caps.json", caps)

    def approve(self, job=None):
        """The human path, in-process: the engine's approval, then the audit line gate.py writes."""
        job = job or self.d.job
        self.lc.approve_gate(job, "approved in test")
        self.lc.gate_audit("approve", job, note="approved in test")
        self.d.note("approve")

    def runlog(self, job=None):
        return [json.loads(l) for l in (self.lc.job_dir(job or self.d.job) / "run.log.jsonl").read_text(encoding="utf-8").splitlines()]


class MainPathTests(DeliveryBase):
    def test_new_to_done_with_parallel_fanout_question_revision_gate_and_delivery(self):
        d, lc = self.d, self.lc
        d.new()
        ds.main_path_to_gate(d)
        self.assertEqual(d.trail, MAIN_TRAIL)
        # the human path: gate.py without a terminal is refused; the test approves in-process
        code, _, err = d.run("gate.py", "approve", d.job)
        self.assertEqual((code, d.status()["state"]), (1, "GATE"))
        self.assertIn("no interactive terminal", err)
        self.approve()
        ds.deliver_and_finish(d)
        st = d.status()
        self.assertEqual(st["state"], "DONE")
        self.assertEqual([t[0] for t in d.trail[-3:]], ["approve", "deliver", "complete"])
        self.assertTrue(lc.verify_gate(d.job, "G1-demo")[0])                       # still valid at the end
        self.assertEqual([t[1] for t in d.trail[-3:]], ["APPROVED", "DELIVERING", "DONE"])
        # every call closed by the post hook, linked to its own handoff, usage adding up
        self.assertTrue(all(c["status"] == "done" and c["usage_source"] == "post_tool_use" for c in st["calls"]))
        self.assertEqual(len({c["handoff"] for c in st["calls"]}), len(st["calls"]))
        expected = sum(ds.TOKENS[c["agent"]] for c in st["calls"])
        self.assertEqual(lc.usage_totals(st)["tokens"]["total"], expected)
        _, out, _ = d.state("usage", d.job)
        self.assertIn(f"total {expected}", out)
        self.assertEqual([c["item"] for c in st["calls"] if c["item"]], ["north", "south", "east"])
        # three sources stored by the fetch script; the draft's quote checked against S01
        _, out, _ = d.run("evidence.py", "list", d.job)
        self.assertEqual(out.count(" stored "), 3)
        # a second delivery after DONE is refused
        code, _, err = d.event("deliver", expect=1)
        self.assertIn("terminal", err)

    def test_closing_calls_with_state_py_result_instead_of_the_hook(self):
        d = self.d
        d.new(slug="headless")
        d.event("dispatch")
        d.stand_in("demo-planner", {"plan.md": "plan\n"})
        call = d.status()["calls"][-1]
        result = d.root / "scratch-result.json"
        result.write_text(json.dumps({"type": "result", "duration_ms": 900, "total_cost_usd": 0.01,
                                      "usage": {"input_tokens": 10, "output_tokens": 90, "cache_read_input_tokens": 800,
                                                "cache_creation_input_tokens": 100}, "modelUsage": {"x": {}}}))
        d.state("result", d.job, call["id"], "done", "--usage-json", str(result))
        c = d.status()["calls"][-1]
        self.assertEqual((c["status"], c["usage_source"], c["usage"]["total"]), ("done", "headless", 1000))
        d.event("stage_done")
        self.assertEqual(d.status()["stage"], "demo-researcher")


class RejectionAndFailureTests(DeliveryBase):
    def test_gate_rejection_then_approval(self):
        d, lc = self.d, self.lc
        d.new(slug="rejected")
        ds.main_path_to_gate(d)
        lc.reject_gate(d.job, "Treat DM04 as major: tighten the wording.")
        self.assertEqual((d.status()["state"], d.status()["stage"]), ("REVISING", "demo-writer"))
        v3 = (self.tmp / f"jobs/{d.job}/drafts/v2.md").read_text().replace("North leads", "North is first")
        d.agent("demo-writer", {"v3.md": v3})
        d.event("revised", "--artifact", f"jobs/{d.job}/drafts/v3.md")
        d.review("demo-critic", "pass")
        d.review("demo-verifier", "pass")
        self.assertEqual(d.status()["state"], "GATE")
        self.approve()
        self.assertEqual(d.status()["state"], "APPROVED")

    def test_altered_quote_and_stale_reference_go_back_and_count_as_revisions(self):
        d = self.d
        d.new(slug="faulty")
        altered = '# Order volumes\nNorth leads [S:S01 §1 "The north region ships 150 orders per day"].\n'
        with self.assertRaises(AssertionError):                                     # the run stops at REVISING
            ds.main_path_to_gate(d, writer_v1=altered)
        st = d.status()
        self.assertEqual((st["state"], st["last_failed_by"]), ("REVISING", "check-evidence"))
        quote = ds.PAGES["north"].split(" on average")[0]
        stale = f'# Order volumes\nNorth leads [S:S01 §1 "{quote}"]. See jobs/{d.job}/drafts/v1.md for the old table.\n'
        d.agent("demo-writer", {"v2.md": stale})
        d.event("revised", "--artifact", f"jobs/{d.job}/drafts/v2.md")
        st = d.status()
        self.assertEqual((st["state"], st["last_failed_by"]), ("REVISING", "check-refs"))
        clean = f'# Order volumes\nNorth leads [S:S01 §1 "{quote}"].\n'
        d.agent("demo-writer", {"v3.md": clean})
        d.event("revised", "--artifact", f"jobs/{d.job}/drafts/v3.md")
        st = d.status()
        self.assertEqual(st["state"], "REVIEW")
        self.assertEqual((st["counters"]["total_revisions"], st["counters"]["lifetime_revisions"]), (2, 2))

    def test_an_edit_after_approval_voids_the_token_and_blocks_delivery(self):
        d = self.d
        d.new(slug="edited")
        ds.main_path_to_gate(d)
        self.approve()
        art = self.tmp / d.status()["artifact_path"]
        art.write_text(art.read_text() + "\nA late edit.\n")
        code, _, err = d.event("deliver", expect=1)
        self.assertIn("token void", err)
        self.assertEqual(d.status()["state"], "APPROVED")


class GateSafetyTests(DeliveryBase):
    def test_gate_py_ignores_lab_variables_without_a_terminal(self):
        d = self.d
        d.new(slug="envtry")
        ds.main_path_to_gate(d)
        env = {**d.env, "LAB_SKIP_TTY": "1", "LAB_FORCE": "1", "LAB_YES": "1", "LAB_APPROVE": "1", "LAB_NONINTERACTIVE": "1"}
        for cmd in (["approve", d.job], ["reject", d.job, "--feedback", "x"], ["lock"], ["ceiling", d.job, "--tokens", "9"]):
            p = subprocess.run([sys.executable, str(self.tmp / "engine/gate.py"), *cmd], capture_output=True, text=True,
                               env=env, stdin=subprocess.DEVNULL)
            self.assertEqual(p.returncode, 1, cmd)
            self.assertIn("no interactive terminal", p.stderr)
        self.assertEqual(d.status()["state"], "GATE")
        self.assertFalse((self.tmp / ".lab/OPERATE").exists())
        self.assertNotIn("environ", (REPO / "engine/gate.py").read_text(encoding="utf-8"))  # no switch to read

    def test_forged_writes_at_gate_are_blocked(self):
        d = self.d
        d.new(slug="forger")
        ds.main_path_to_gate(d)
        for path in (f"jobs/{d.job}/gates/G1-demo.json", "logs/usage.jsonl", f"jobs/{d.job}/evidence/registry.json",
                     f"jobs/{d.job}/state.json", "cache/evidence/forged.txt"):
            code, err = d.hook("pre_tool_use_launcher.py", {"tool_name": "Write", "tool_input": {"file_path": path},
                                                            "cwd": str(self.tmp), "agent_id": "stand-in",
                                                            "agent_type": "demo-writer"})
            self.assertEqual(code, 2, path)
        self.assertFalse((self.tmp / f"jobs/{d.job}/gates/G1-demo.json").exists())


class CapTests(DeliveryBase):
    """Every cap, hit through the command line: exit code 3, the job paused, resumed where allowed."""

    def to_review(self, slug):
        d, lc = self.d, self.lc
        d.new(slug=slug)
        d.event("dispatch"); d.agent("demo-planner"); d.event("stage_done")
        d.state("fanout", d.job, "north")
        d.agent("demo-researcher", item="north", fetch=["north"]); d.state("fanout-result", d.job, "north", "done")
        d.event("stage_done")
        d.agent("demo-writer", {"v1.md": "# Draft\nSummary.\n"})
        d.event("artifact_ready", "--artifact", f"jobs/{d.job}/drafts/v1.md")
        return d

    def revise(self, n):
        self.d.agent("demo-writer", {f"v{n}.md": f"# Draft {n}\n"})
        self.d.event("revised", "--artifact", f"jobs/{self.d.job}/drafts/v{n}.md")

    def assertCap(self, result, name, state="ESCALATED"):
        code, _, err = result
        self.assertEqual(code, 3, err)
        self.assertIn(name, err)
        self.assertEqual(self.d.status()["state"], state)

    def test_critic_revisions(self):
        d = self.to_review("capcritic")
        for n in (2, 3):
            d.event("review_fail"); self.revise(n)
        self.assertCap(d.event("review_fail", expect=3), "critic_revisions")
        d.event("resume")
        self.assertEqual(d.status()["state"], "REVISING")

    def test_verifier_revisions(self):
        d = self.to_review("capverif")
        self.set_caps(total_revisions_before_gate=9)
        for n in (2, 3):
            d.event("review_pass"); d.event("review_fail"); self.revise(n)
        d.event("review_pass")
        self.assertCap(d.event("review_fail", expect=3), "verifier_revisions")

    def test_total_revisions_before_gate(self):
        d = self.to_review("captotal")
        for n in (2, 3):
            d.event("review_fail"); self.revise(n)
        d.event("review_pass"); d.event("review_fail"); self.revise(4)
        d.event("review_pass")
        self.assertCap(d.event("review_fail", expect=3), "total_revisions_before_gate")

    def test_gate_rejections(self):
        d, lc = self.d, self.lc
        d.new(slug="capreject")
        ds.main_path_to_gate(d)
        for n in (3, 4, 5):
            lc.reject_gate(d.job, f"again {n}")
            self.revise(n); d.event("review_pass"); d.event("review_pass")
        with self.assertRaises(lc.CapExceeded) as cm:
            lc.reject_gate(d.job, "once more")
        self.assertEqual(cm.exception.code, 3)
        self.assertEqual(d.status()["state"], "ESCALATED")

    def test_infra_retries_block_and_resume(self):
        d = self.to_review("capinfra")
        d.event("infra_error"); d.event("infra_error")
        self.assertCap(d.event("infra_error", expect=3), "infra_retries", state="BLOCKED")
        d.event("resume")
        self.assertEqual(d.status()["state"], "REVIEW")

    def test_repairs(self):
        d = self.to_review("caprepair")
        self.set_caps(repairs=1)
        d.agent("demo-critic"); d.event("repair", "--reason", "invalid_output")
        d.agent("demo-critic")
        d.event("review_pass"); d.agent("demo-verifier")
        self.assertCap(d.event("repair", "--reason", "invalid_output", expect=3), "repairs")

    def test_input_rounds(self):
        d = self.to_review("capinput")
        self.set_caps(input_rounds=1)
        q = d.root / "q.md"; q.write_text("Q?\n")
        d.event("needs_input", "--questions", str(q))
        d.state("input", d.job, "-", "--class", "synthetic", stdin="A.\n"); d.event("answered")
        self.assertCap(d.event("needs_input", "--questions", str(q), expect=3), "input_rounds")

    def test_agent_calls_per_job_and_lifetime(self):
        d = self.to_review("capcalls")
        self.set_caps(agent_calls_per_job=3)                                        # 3 calls so far
        d.state("handoff", d.job)
        self.assertCap(d.state("call", d.job, "demo-critic", expect=3), "agent_calls_per_job")
        self.assertEqual(len(d.status()["calls"]), 3)                                # the refused call was not recorded
        self.set_caps(agent_calls_per_job=25, lifetime_agent_calls=4)
        d.event("resume")                                                            # per-job counter resets
        d.agent("demo-critic")                                                       # 4 in the lifetime
        d.event("review_pass"); d.state("handoff", d.job)
        self.assertCap(d.state("call", d.job, "demo-verifier", expect=3), "lifetime_agent_calls")

    def test_lifetime_revisions_and_lifetime_resumes(self):
        d = self.to_review("caplife")
        self.set_caps(lifetime_revisions=2, critic_revisions=9, total_revisions_before_gate=9, lifetime_resumes=1)
        d.event("review_fail"); self.revise(2)
        d.event("review_fail"); self.revise(3)
        self.assertCap(d.event("review_fail", expect=3), "lifetime_revisions")
        d.event("resume")                                                            # the one allowed resume
        d.event("escalate")
        self.assertCap(d.event("resume", expect=3), "lifetime_resumes")

    def test_usage_ceiling_through_state_py_result(self):
        d = self.to_review("capusage")
        self.set_caps(usage_ceiling={"tokens": 8000})                                # 1000 + 2000 + 3000 used
        d.stand_in("demo-critic")
        call = d.status()["calls"][-1]
        result = d.root / "r.json"
        result.write_text(json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 1000,
                                                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}))
        self.assertCap(d.state("result", d.job, call["id"], "done", "--usage-json", str(result), expect=3), "usage ceiling")
        self.assertCap(d.event("resume", expect=3), "usage ceiling")                 # until the approver raises it

    def test_fix_attempts_on_a_script_stage(self):
        routes = json.loads((self.tmp / "config/routes.json").read_text())
        routes["routes"]["demobuild"] = {"stages": [{"agent": "demo-planner"}, {"script": "demo-check"}, {"agent": "demo-writer"}],
                                         "reviews": [{"agent": "demo-critic", "kind": "critic"}],
                                         "revise_with": "demo-writer", "fix_with": "demo-planner", "gate": None}
        self.dump("config/routes.json", routes)
        self.dump("config/scripts.json", {"scripts": {"demo-check": {"argv": ["{python}", "-c", "import sys; sys.exit(1)"], "timeout": 30}}})
        d = self.d
        _, out, _ = d.state("new", "demobuild", "fixcap", "x", "--class", "synthetic")
        d.job = out.split()[0]
        d.event("dispatch"); d.agent("demo-planner"); d.event("stage_done")
        for _ in range(2):
            d.state("run", d.job, expect=4)
            d.agent("demo-planner"); d.event("fixed")
        self.assertCap(d.state("run", d.job, expect=3), "fix_attempts")


@unittest.skipUnless(shutil.which("git"), "git not available")
class InternalMainPathTests(DeliveryBase):
    def test_main_path_as_an_internal_job_leaves_no_tracked_trace(self):
        shutil.copy2(REPO / ".gitignore", self.tmp / ".gitignore")
        subprocess.run(["git", "-C", str(self.tmp), "init", "-q"], check=True)
        d = self.d
        d.new(slug="inside", cls="internal")
        ds.main_path_to_gate(d)
        self.approve()
        ds.deliver_and_finish(d)
        self.assertEqual(d.status()["state"], "DONE")
        code, out, err = d.state("check-private", d.job)
        self.assertEqual(code, 0, out + err)
        self.assertIn("private OK", out)
        self.assertFalse((self.tmp / "logs/usage.jsonl").exists() and d.job in (self.tmp / "logs/usage.jsonl").read_text())
        self.assertFalse((self.tmp / "logs/gate-audit.jsonl").exists())
        self.assertIn(d.job, (self.tmp / "private/logs/usage.jsonl").read_text())
        self.assertIn(d.job, (self.tmp / "private/logs/gate-audit.jsonl").read_text())
        self.assertFalse(any((self.tmp / "cache/evidence").glob("*.txt")) if (self.tmp / "cache/evidence").exists() else False)


if __name__ == "__main__":
    unittest.main()
