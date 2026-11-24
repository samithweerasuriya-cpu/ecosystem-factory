"""T2.5 (Samith, 2026-11-24): the interview guide's round limits. At the per-cycle limit, with lifetime rounds left,
an interview the interviewer reports incomplete pauses the job for a resume, which starts a new cycle; it never goes
on to the readiness score. At the lifetime limit the job escalates to the approver. Readiness never sends the job
back to an interviewer with no question round left. Every agent call uses fake_claude.py instead of the real CLI."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_intake_t24 import IntakeBase  # noqa: E402


class RoundLimitTests(IntakeBase):
    def caps(self, per_cycle, lifetime):
        f = self.tmp / "config/caps.json"
        caps = json.loads(f.read_text(encoding="utf-8"))
        caps.update(input_rounds_per_cycle=per_cycle, input_rounds=lifetime)
        f.write_text(json.dumps(caps), encoding="utf-8")

    def two_rounds_then(self, job, final):
        """Two question rounds, then the interviewer's final answer (a status)."""
        self.respond(job, self.ask(job, "How is the rota built today? [current_process]"),
                     self.ask(job, "Who signs it off? [users_and_stakeholders]"), final)
        for answer in ("By hand on paper.", "Don't know yet."):
            r = self.ac.call_job(job, self.agent["interviewer"])
            self.assertEqual(r["status"], "needs_input", r)
            self.answer(job, answer)
        r = self.ac.call_job(job, self.agent["interviewer"])
        self.assertEqual(r["status"], "done", r)

    def test_at_the_cycle_limit_an_incomplete_interview_pauses_and_a_resume_starts_a_new_cycle(self):
        self.caps(2, 5)
        j = self.new_intake()
        self.two_rounds_then(j, self.status(j, status="incomplete", playback=None))
        with self.assertRaises(self.lc.CapExceeded) as cm:
            self.lc.apply(j, "stage_done")
        self.assertIn("input_rounds_per_cycle=2 reached; a resume starts a new cycle", str(cm.exception))
        st = self.lc.load_state(j)
        self.assertEqual((st["state"], st["round_limit"], st["stage"], st["counters"]["fix_attempts"]),
                         ("ESCALATED", "cycle", "interviewer", 0))
        self.assertFalse((self.tmp / f"jobs/{j}/scripts").exists())        # readiness never ran
        st = self.lc.apply(j, "resume")
        self.assertEqual((st["state"], st["stage"], st["counters"]["cycle_input_rounds"], st["counters"]["input_rounds"]),
                         ("WORKING", "interviewer", 0, 2))
        self.assertNotIn("round_limit", st)
        self.respond(j, self.ask(j, "What is out of scope? [scope]"))
        r = self.ac.call_job(j, self.agent["interviewer"])
        self.assertEqual((r["status"], r["state"]), ("needs_input", "AWAITING_INPUT"))
        self.assertIn("ROUNDS: question rounds used 0 of 2 this cycle, 2 of 5 in the job's lifetime",
                      self.calls()[-1]["stdin"])

    def test_at_the_lifetime_limit_the_job_escalates_to_the_approver(self):
        self.caps(3, 2)
        j = self.new_intake()
        self.two_rounds_then(j, self.status(j, status="incomplete", playback=None))
        with self.assertRaises(self.lc.CapExceeded) as cm:
            self.lc.apply(j, "stage_done")
        self.assertIn("input_rounds=2 reached; the approver decides", str(cm.exception))
        st = self.lc.load_state(j)
        self.assertEqual((st["state"], st["round_limit"]), ("ESCALATED", "lifetime"))

    def test_readiness_never_sends_the_job_back_to_an_interviewer_with_no_round_left(self):
        self.caps(2, 5)
        j = self.new_intake()
        self.two_rounds_then(j, self.status(j, playback="A03", field_goal={"state": "vague", "cites": ["[A:A01]"]}))
        st = self.lc.apply(j, "stage_done")                                # complete: on to readiness
        self.assertEqual((st["state"], st["stage"]), ("WORKING", "readiness"))
        with self.assertRaises(self.lc.CapExceeded):
            self.lc.run_script(j)                                          # below threshold, no round left
        st = self.lc.load_state(j)
        self.assertEqual((st["state"], st["round_limit"], st["stage"], st["fixing"], st["counters"]["fix_attempts"]),
                         ("ESCALATED", "cycle", "interviewer", True, 0))
        st = self.lc.apply(j, "resume")
        self.assertEqual((st["state"], st["stage"], st["stage_kind"], st["fixing"]),
                         ("WORKING", "interviewer", "fix", True))

    def test_with_rounds_left_an_incomplete_interview_goes_on_to_readiness_as_before(self):
        j = self.new_intake()                                              # the factory caps: 3 a cycle, 5 in all
        self.two_rounds_then(j, self.status(j, status="incomplete", playback=None))
        st = self.lc.apply(j, "stage_done")
        self.assertEqual((st["state"], st["stage"]), ("WORKING", "readiness"))
        self.assertNotIn("round_limit", st)
        st, _ = self.lc.run_script(j)                                      # below threshold, rounds left: the fix
        self.assertEqual((st["state"], st["stage"], st["fixing"], st["counters"]["fix_attempts"]),
                         ("WORKING", "interviewer", True, 1))

    def test_an_unreadable_saved_answer_counts_as_incomplete(self):
        self.caps(2, 5)
        j = self.new_intake()
        self.two_rounds_then(j, self.status(j, status="incomplete", playback=None))
        st = self.lc.load_state(j)
        (self.tmp / st["calls"][-1]["output"]["path"]).write_text("not json", encoding="utf-8")
        with self.assertRaises(self.lc.CapExceeded):
            self.lc.apply(j, "stage_done")
        self.assertEqual(self.lc.load_state(j)["round_limit"], "cycle")
