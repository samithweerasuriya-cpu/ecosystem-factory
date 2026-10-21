"""T0.6: engine fixes from the run history, one test class per fix (a)-(f), plus repair and continue-from."""
import json
import shutil
import subprocess
import sys
import unittest

from support import REPO, LabTestBase


class T06Base(LabTestBase):
    def set_caps(self, **kw):
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        caps.update(kw)
        self.dump("config/caps.json", caps)

    def spec_at_review(self, slug="sample", text="draft v1", cls="synthetic"):
        lc = self.lc
        j = lc.new_job("spec", slug, "Sample goal", cls=cls)["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"{lc.rel(lc.job_dir(j))}/drafts/v1.md", text))
        return j

    def input_file(self, name="answer.md", text="My answer.\n"):
        return str(self.tmp / self.write(f"scratch/{name}", text))

    def log(self, j):
        return [json.loads(l) for l in (self.lc.job_dir(j) / "run.log.jsonl").read_text(encoding="utf-8").splitlines()]


class LifetimeCapTests(T06Base):
    """(a) lifetime_agent_calls, lifetime_revisions and lifetime_resumes never reset."""

    def test_lifetime_counters_survive_reject_and_resume(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        lc.apply(j, "review_fail")
        lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v2.md", "v2"))
        lc.apply(j, "review_pass"); lc.apply(j, "review_pass")
        lc.reject_gate(j, "redo")
        st = lc.load_state(j)["counters"]
        self.assertEqual((st["total_revisions"], st["critic_revisions"]), (0, 0))   # cycle counters reset by reject
        self.assertEqual(st["lifetime_revisions"], 2)                               # lifetime kept
        lc.record_call(j, "writer")
        lc.apply(j, "escalate"); lc.apply(j, "resume")
        st = lc.load_state(j)["counters"]
        self.assertEqual(st["agent_calls"], 0)                                       # cycle counter reset by resume
        self.assertEqual((st["lifetime_agent_calls"], st["lifetime_revisions"], st["lifetime_resumes"]), (2, 2, 1))

    def test_lifetime_revisions_cap_escalates(self):
        lc = self.lc
        self.set_caps(lifetime_revisions=2, critic_revisions=9, total_revisions_before_gate=9)
        j = self.spec_at_review()
        for n in (2, 3):
            lc.apply(j, "review_fail")
            lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v{n}.md", str(n)))
        with self.assertRaises(lc.CapExceeded) as cm:
            lc.apply(j, "review_fail")
        self.assertIn("lifetime_revisions", str(cm.exception))
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")

    def test_resume_refused_past_lifetime_resumes(self):
        lc = self.lc
        self.set_caps(lifetime_resumes=1)
        j = self.spec_at_review()
        lc.apply(j, "escalate"); lc.apply(j, "resume")
        lc.apply(j, "escalate")
        with self.assertRaises(lc.CapExceeded) as cm:
            lc.apply(j, "resume")
        self.assertIn("continue-from", str(cm.exception))
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["counters"]["lifetime_resumes"]), ("ESCALATED", 1))

    def test_lifetime_agent_calls_cap_spans_resumes(self):
        lc = self.lc
        self.set_caps(lifetime_agent_calls=2)
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        lc.apply(j, "escalate"); lc.apply(j, "resume")                              # agent_calls back to 0
        lc.record_call(j, "critic")
        lc.apply(j, "escalate"); lc.apply(j, "resume")
        with self.assertRaises(lc.CapExceeded) as cm:
            lc.record_call(j, "critic")
        self.assertIn("lifetime_agent_calls", str(cm.exception))


class HandoffTests(T06Base):
    """(b) handoffs are built by script; reviewers never get the author's reasoning or notes."""

    def setUp(self):
        super().setUp()
        self.dump("config/reviewers.json", {"reviewers": {
            "critic": {"rulebook": "rules/test-rulebook.md"},
            "verifier": {"rulebook": "rules/test-rulebook.md", "source_policy": "rules/source-policy.md"},
            "check-refs": {"rulebook": "rules/check-refs.md"}}})
        self.write("rules/source-policy.md", "# Source policy\n")

    def at_critic_with_history(self):
        lc = self.lc
        j, art = self.spec_to_gate()
        self.write(f"jobs/{j}/research/author-notes.md", "why I wrote it this way")
        self.write(f"jobs/{j}/evidence/source-1.txt", "stored source")
        lc.record_input(j, self.input_file(), "synthetic")
        lc.reject_gate(j, "Treat TR16 as blocker")
        lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v2.md", "v2"))
        return j

    def paths(self, h):
        return {i["label"]: i["path"] for i in h["inputs"]}

    def test_critic_gets_artifact_rulebook_inputs_and_feedback_only(self):
        j = self.at_critic_with_history()
        h, text = self.lc.handoff(j)
        p = self.paths(h)
        self.assertEqual((h["stage"], h["review_kind"]), ("critic", "critic"))
        self.assertEqual(p["artifact"], f"jobs/{j}/drafts/v2.md")
        self.assertEqual(h["rules"], ["rules/test-rulebook.md"])
        self.assertIn("input A01 (synthetic)", p)
        self.assertIn("gate feedback", p)
        joined = text + json.dumps(h)
        for forbidden in ("research", "author-notes", "brief.md", "drafts/v1.md", "evidence"):
            self.assertNotIn(forbidden, joined, forbidden)

    def test_verifier_gets_evidence_registry_and_source_policy(self):
        j = self.at_critic_with_history()
        self.lc.apply(j, "review_pass")
        h, text = self.lc.handoff(j)
        p = self.paths(h)
        self.assertEqual(h["review_kind"], "verifier")
        self.assertEqual((p["evidence pack"], p["source registry"]),
                         (f"jobs/{j}/evidence/", f"jobs/{j}/evidence/registry.json"))
        self.assertEqual(h["rules"], ["rules/test-rulebook.md", "rules/source-policy.md"])
        self.assertIn("input A01 (synthetic)", p)
        self.assertIn("gate feedback", p)
        for forbidden in ("research", "author-notes", "brief.md", "drafts/v1.md"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_revise_gets_brief_evidence_findings_feedback_and_inputs(self):
        lc = self.lc
        j = self.at_critic_with_history()
        findings = {"job_id": j, "reviewer": "critic", "artifact_path": f"jobs/{j}/drafts/v2.md", "verdict": "fail",
                    "artifact_version": "v2", "rules_checked": [], "findings": []}
        self.dump(f"jobs/{j}/reviews/critic-v2.json", findings)
        self.dump(f"jobs/{j}/reviews/critic-v1.json", {**findings, "artifact_path": f"jobs/{j}/drafts/v1.md"})
        lc.apply(j, "review_fail")
        h, text = lc.handoff(j)
        labels = [i["label"] for i in h["inputs"]]
        self.assertEqual(h["kind"], "revise")
        for want in ("artifact", "brief", "evidence pack", "findings to address", "gate feedback", "input A01 (synthetic)"):
            self.assertIn(want, labels)
        self.assertIn("critic-v2.json", text)
        self.assertNotIn("critic-v1.json", text)                                    # an older round's findings
        self.assertNotIn("author-notes", text)

    def test_fanout_handoff_names_the_item(self):
        lc = self.lc
        j = lc.new_job("survey", "fan", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.set_fanout(j, ["north", "south"])
        with self.assertRaises(lc.LabError):
            lc.handoff(j)
        h, text = lc.handoff(j, item="south")
        self.assertEqual((h["item"], h["split_by"]), ("south", "group"))
        self.assertIn("ITEM: south    SPLIT_BY: group", text)

    def test_handoff_is_logged_and_linked_to_the_next_call(self):
        lc = self.lc
        j = self.spec_at_review()
        _, text = lc.handoff(j)
        st = lc.record_call(j, "critic")
        self.assertEqual(st["calls"][-1]["handoff"], "H001")
        entry = [e for e in self.log(j) if e["event"] == "handoff"][0]
        import hashlib
        self.assertEqual(entry["sha256"], hashlib.sha256(text.encode()).hexdigest())

    def test_script_stage_has_no_handoff(self):
        lc = self.lc
        j = lc.new_job("build", "noh", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        with self.assertRaises(lc.LabError):
            lc.handoff(j)


class CallLogTests(T06Base):
    """(c) every call has an id, attempt and retry_of; repeats need an infra_error or repair."""

    def test_second_call_in_the_same_step_is_refused(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        with self.assertRaises(lc.LabError) as cm:
            lc.record_call(j, "critic")
        self.assertIn("without an infra_error or repair", str(cm.exception))

    def test_infra_error_permits_exactly_one_linked_retry(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        lc.apply(j, "infra_error")
        st = lc.record_call(j, "critic")
        c = st["calls"][-1]
        self.assertEqual((c["id"], c["attempt"], c["retry_of"], c["reason"]), ("C002", 2, "C001", "infra_error"))
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "critic")

    def test_a_new_step_allows_a_fresh_call(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        lc.apply(j, "review_fail"); lc.record_call(j, "writer")
        lc.apply(j, "revised", artifact=self.write(f"jobs/{j}/drafts/v2.md", "v2"))
        c = lc.record_call(j, "critic")["calls"][-1]
        self.assertEqual((c["attempt"], c["retry_of"]), (1, None))

    def test_only_the_agent_the_job_waits_on_can_be_called(self):
        lc = self.lc
        j = self.spec_at_review()
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "verifier")

    def test_fanout_item_retry_after_infra_error(self):
        lc = self.lc
        j = lc.new_job("survey", "retry", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.set_fanout(j, ["a", "b"])
        lc.record_call(j, "researcher", item="a")
        lc.record_call(j, "researcher", item="b")
        lc.apply(j, "infra_error")                                                   # permit for the last call (item b)
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "researcher", item="a")
        c = lc.record_call(j, "researcher", item="b")["calls"][-1]
        self.assertEqual((c["item"], c["attempt"], c["retry_of"]), ("b", 2, "C002"))

    def test_every_call_is_in_the_run_log(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic"); lc.apply(j, "infra_error"); lc.record_call(j, "critic")
        calls = [e for e in self.log(j) if e["event"] == "agent_call"]
        self.assertEqual([(e["call"], e["attempt"], e["retry_of"]) for e in calls], [("C001", 1, None), ("C002", 2, "C001")])


class RepairTests(T06Base):
    """Repair: one linked retry for invalid output or a severity directive, with its own cap."""

    def test_repair_permits_one_linked_retry_with_its_reason(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        st = lc.apply(j, "repair", reason="severity_directive")
        self.assertEqual((st["state"], st["counters"]["repairs"]), ("REVIEW", 1))
        c = lc.record_call(j, "critic")["calls"][-1]
        self.assertEqual((c["attempt"], c["retry_of"], c["reason"]), (2, "C001", "severity_directive"))
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "critic")

    def test_a_repair_cannot_be_repaired_again(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        lc.apply(j, "repair", reason="invalid_output")
        lc.record_call(j, "critic")
        with self.assertRaises(lc.LabError) as cm:
            lc.apply(j, "repair", reason="invalid_output")
        self.assertIn("infra_error", str(cm.exception))

    def test_repair_needs_a_reason_and_a_call(self):
        lc = self.lc
        j = self.spec_at_review()
        with self.assertRaises(lc.LabError):
            lc.apply(j, "repair", reason="invalid_output")                         # nothing to repair yet
        lc.record_call(j, "critic")
        with self.assertRaises(lc.LabError):
            lc.apply(j, "repair", reason="because")

    def test_repair_cap(self):
        lc = self.lc
        self.set_caps(repairs=1)
        j = self.spec_at_review()
        lc.record_call(j, "critic"); lc.apply(j, "repair", reason="invalid_output"); lc.record_call(j, "critic")
        lc.apply(j, "review_pass"); lc.record_call(j, "verifier")
        with self.assertRaises(lc.CapExceeded):
            lc.apply(j, "repair", reason="invalid_output")
        self.assertEqual(lc.load_state(j)["state"], "ESCALATED")


class HumanInputTests(T06Base):
    """(d) inputs are stored verbatim with a class that may not exceed the job's class
    (internal jobs and their inputs: test_jobclass.py)."""

    def test_input_is_stored_verbatim_with_id_and_hash(self):
        lc = self.lc
        j = self.spec_at_review(cls="public")
        raw = "Line one, café — “quotes”\r\nLine two\n".encode("utf-8")
        (self.tmp / "scratch").mkdir()
        (self.tmp / "scratch/a.md").write_bytes(raw)
        _, rec = lc.record_input(j, str(self.tmp / "scratch/a.md"), "public", note="answer to Q1")
        self.assertEqual((rec["id"], rec["class"]), ("A01", "public"))
        self.assertTrue(rec["path"].startswith(f"jobs/{j}/inputs/A01-"))
        self.assertEqual((self.tmp / rec["path"]).read_bytes(), raw)
        import hashlib
        self.assertEqual(rec["sha256"], hashlib.sha256(raw).hexdigest())

    def test_class_is_required_and_checked(self):
        lc = self.lc
        j = self.spec_at_review()
        with self.assertRaises(lc.LabError):
            lc.record_input(j, self.input_file(), "confidential")
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "input", j, self.input_file()],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 2)                                            # argparse: --class required
        self.assertIn("--class", p.stderr)

    def test_inputs_are_protected_from_agent_writes(self):
        for path in ("jobs/20260101-spec-a/inputs/A01-answer.md", "private/jobs/20260101-spec-a/inputs/A01-x.md",
                     "jobs/20260101-spec-a/questions/q-1.md"):
            self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": path}}), 2, path)


class ReferenceCheckTests(T06Base):
    """(e) check_refs runs on every new artifact version, before any agent reviewer."""

    def ready(self, text, version="v1", job=None):
        lc = self.lc
        if job is None:
            job = lc.new_job("spec", "refs", "x")["job_id"]
            lc.apply(job, "dispatch"); lc.apply(job, "stage_done")
            return job, lc.apply(job, "artifact_ready", artifact=self.write(f"jobs/{job}/drafts/{version}.md", text.format(j=job)))
        return job, lc.apply(job, "revised", artifact=self.write(f"jobs/{job}/drafts/{version}.md", text.format(j=job)))

    def validate(self, path):
        return subprocess.run([sys.executable, str(self.tmp / "engine/validate_findings.py"), str(self.tmp / path)],
                              capture_output=True, text=True, env=self.hook_env())

    def test_clean_artifact_goes_to_the_first_reviewer(self):
        self.write("rules/x.md", "x")
        _, st = self.ready("See `rules/x.md` and config/caps.json.\n")
        self.assertEqual((st["state"], st["stage"]), ("REVIEW", "critic"))

    def test_missing_path_goes_back_to_the_author_with_valid_findings(self):
        j, st = self.ready("Based on jobs/{j}/research/missing.md.\n")
        self.assertEqual((st["state"], st["stage"], st["last_failed_by"]), ("REVISING", "writer", "check-refs"))
        self.assertEqual((st["counters"]["total_revisions"], st["counters"]["lifetime_revisions"]), (1, 1))
        doc = json.loads((self.tmp / "jobs" / j / "reviews/check-refs-1.json").read_text())
        self.assertEqual([f["rule"] for f in doc["findings"]], ["REF01"])
        p = self.validate(f"jobs/{j}/reviews/check-refs-1.json")
        self.assertEqual(p.returncode, 0, p.stdout)                                  # passes the findings validator

    def test_reference_to_an_older_draft_of_the_same_job(self):
        j, st = self.ready("v1\n")
        self.lc.apply(j, "review_fail")
        _, st = self.ready("Builds on jobs/{j}/drafts/v1.md.\n", version="v2", job=j)
        doc = json.loads((self.tmp / "jobs" / j / "reviews/check-refs-1.json").read_text())
        self.assertEqual([f["rule"] for f in doc["findings"]], ["REF03"])
        self.assertEqual(st["state"], "REVISING")

    def test_unknown_job_and_input_ids(self):
        j, st = self.ready("Parent 20250101-spec-nothing-here; answer [A:A07].\n")
        doc = json.loads((self.tmp / "jobs" / j / "reviews/check-refs-1.json").read_text())
        self.assertEqual(sorted(f["rule"] for f in doc["findings"]), ["REF02", "REF02"])

    def test_known_input_id_resolves(self):
        lc = self.lc
        j = lc.new_job("spec", "refok", "x")["job_id"]
        lc.record_input(j, self.input_file(), "synthetic")
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        st = lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md", f"Per [A:A01], in job {j}.\n"))
        self.assertEqual(st["state"], "REVIEW")


class AwaitingInputTests(T06Base):
    """(f) needs_input -> AWAITING_INPUT -> answered returns to the same step; own cap; not a resume."""

    def test_round_trip_returns_to_the_same_stage(self):
        lc = self.lc
        j = self.spec_at_review()
        lc.record_call(j, "critic")
        q = self.write("scratch/q.md", "1. Which market?\n2. Which year?\n")
        st = lc.apply(j, "needs_input", questions=str(self.tmp / q))
        self.assertEqual(st["state"], "AWAITING_INPUT")
        self.assertEqual((self.tmp / st["awaiting"]["questions"]).read_text(), "1. Which market?\n2. Which year?\n")
        with self.assertRaises(lc.LabError):
            lc.record_call(j, "critic")                                              # no calls while waiting
        with self.assertRaises(lc.LabError):
            lc.apply(j, "answered")                                                  # no answer recorded yet
        lc.record_input(j, self.input_file(), "synthetic")
        st = lc.apply(j, "answered")
        self.assertEqual((st["state"], st["stage"], st["stage_kind"]), ("REVIEW", "critic", "review"))
        c = lc.record_call(j, "critic")["calls"][-1]                                 # a fresh call is allowed
        self.assertEqual((c["attempt"], c["retry_of"]), (1, None))
        self.assertEqual(st["counters"]["lifetime_resumes"], 0)

    def test_input_rounds_have_their_own_cap(self):
        lc = self.lc
        self.set_caps(input_rounds=1)
        j = self.spec_at_review()
        q = str(self.tmp / self.write("scratch/q.md", "Q?\n"))
        lc.apply(j, "needs_input", questions=q)
        lc.record_input(j, self.input_file(), "synthetic")
        lc.apply(j, "answered")
        with self.assertRaises(lc.CapExceeded) as cm:
            lc.apply(j, "needs_input", questions=q)
        self.assertIn("input_rounds", str(cm.exception))
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["counters"]["lifetime_resumes"]), ("ESCALATED", 0))


class ContinueFromTests(T06Base):
    """--continue-from: a new job seeded with the old job's latest artifact and inputs, fresh counters."""

    def test_new_job_is_seeded_and_linked(self):
        lc = self.lc
        old = self.spec_at_review(slug="old", text="the old draft\n", cls="internal")
        lc.record_input(old, "-", "public", data=b"public answer\n")
        lc.record_input(old, "-", "internal", data=b"internal answer\n")
        lc.record_call(old, "critic")
        lc.apply(old, "escalate")
        with self.assertRaises(lc.LabError):
            lc.new_job("spec", "again", "Sample goal", continue_from=old, cls="public")  # class may not drop
        st = lc.new_job("spec", "again", "Sample goal", continue_from=old, cls="internal")
        new = st["job_id"]
        self.assertEqual(st["continued_from"], old)
        seed = st["seed"][0]
        self.assertEqual((self.tmp / seed).read_text(), "the old draft\n")
        self.assertEqual([(i["id"], i["class"]) for i in st["inputs"]], [("A01", "public"), ("A02", "internal")])
        self.assertTrue(all(i["path"].startswith(f"private/jobs/{new}/inputs/") for i in st["inputs"]))
        self.assertEqual((self.tmp / st["inputs"][0]["path"]).read_text(), "public answer\n")
        self.assertTrue(all(v == 0 for v in st["counters"].values()))
        self.assertEqual(st["calls"], [])
        created = [e for e in self.log(new) if e["event"] == "created"][0]
        self.assertEqual(created["continued_from"], old)
        self.assertTrue(any(e["event"] == "continued_as" and e["job"] == new for e in self.log(old)))
        lc.apply(new, "dispatch")
        h, _ = lc.handoff(new)
        self.assertIn(seed, [i["path"] for i in h["inputs"]])

    def test_cannot_continue_from_an_active_job(self):
        lc = self.lc
        old = self.spec_at_review(slug="busy")
        with self.assertRaises(lc.LabError):
            lc.new_job("spec", "again", "x", continue_from=old)


if __name__ == "__main__":
    unittest.main()
