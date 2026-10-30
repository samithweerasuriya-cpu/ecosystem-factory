"""T2.5 build items 3, 4, 9 and 11: the job-driven evaluation suites (evals/jobsim.py). An interview run drives a
real intake job in a temporary factory copy (no private/, vendor/, evals/ or keys/), the script persona answers by
each question's field, the per-cycle round cap gets one simulated resume (in the copy only), every round's prompt is
leak-checked; a charter run seeds the job (replay or fixture) and scores the writer, and first-pass acceptance
sends the draft once through the critic and the verifier. The runner never writes under gates/. Reviewer false
findings count on every case (item 9); recall is also reported per run (item 11). Every agent call uses
fake_claude.py (or the replay CLI)."""
import datetime
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# factory-only test (tests/): the intake agents exist only in the factory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
from support import REPO  # noqa: E402
from test_intake_t24 import INJECTED, IntakeBase  # noqa: E402

FIELDS = ["title", "slug", "goal", "success_metrics", "users_and_stakeholders", "current_process", "scope",
          "open_questions", "inputs", "glossary", "context_inventory", "data_classification", "source_policy",
          "output", "quality_rulebook", "examples", "acceptance_tests", "acceptance_criteria", "risk", "systems",
          "gates", "caps"]
SLUG = "swaps"


class JobSimBase(IntakeBase):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.tmp / "evals"))
        self.re = importlib.import_module("run_evals")
        self.js = importlib.import_module("jobsim")
        self.job = f"{datetime.date.today():%Y%m%d}-intake-{SLUG}"
        self.js.CALL_TIMEOUT, self.js.STEP_TIMEOUT = 60, 60   # a hang fails one test with its step, well under 600 s
        self.removed = []
        real_remove = self.js.remove_copy

        def remove(root):                                   # keep what each copy held under gates/ before it goes
            self.removed.append({p.relative_to(root).as_posix(): p.read_bytes()
                                 for p in Path(root).rglob("*") if p.is_file() and "gates" in p.parts})
            real_remove(root)
        self.js.remove_copy = remove

    def tearDown(self):
        while str(self.tmp / "evals") in sys.path:
            sys.path.remove(str(self.tmp / "evals"))
        super().tearDown()

    def suite(self, name, kind, agent):
        self.dump(f"evals/{name}/suite.json", {"agent": f".claude/agents/{agent}.md", "kind": kind,
                                              "rulebook": "rules/interview-guide.md" if kind == "interview"
                                              else "schemas/charter.v1.md"})

    def case(self, suite, cid, case, key, files=None):
        d = self.tmp / f"evals/{suite}/cases/{cid}"
        d.mkdir(parents=True)
        files = {"brief.md": "Shift swap helper for a volunteer rota (synthetic).",
                 "requests.txt": f"Swap Tue for Thu.\n{INJECTED}\n", **(files or {})}
        for n, text in files.items():
            (d / n).write_text(text, encoding="utf-8")
        case = {"id": cid, "kind": "persona", "slug": SLUG, "goal": "Fewer lost shift swaps", "brief": "brief.md",
                "context": [{"file": "requests.txt", "evidence_for": "the input format"}], **case}
        (d / "case.json").write_text(json.dumps(case), encoding="utf-8")
        self.dump(f"evals/{suite}/keys/{cid}.json", key)
        return d

    def fake(self, stage, *answers):
        """The fake CLI's answers for one agent stage, in call order (the last repeats)."""
        f = self.tmp / "responses.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        old.append([f"STAGE: {stage} (", list(answers)])
        f.write_text(json.dumps(old), encoding="utf-8")
        os.environ["FAKE_CLAUDE_RESPONSES"] = str(f)

    def persona_key(self, **over):
        concrete = {f: 0 for f in FIELDS}
        concrete["current_process"] = 2                     # vague first, concrete after a probe
        key = {"canary": "zebracorn", "leak_terms": ["hidden reference"],
               "answers": {"current_process": ["People sort it out.", "The coordinator copies swaps by hand."]},
               "concrete": concrete, "reference": ["current_process", "goal"],
               "injections": [["SYSTEM NOTICE"]], "expect": {"outcome": "ready"}}
        key.update(over)
        return key

    def interview(self, cid="P1", key=None, case=None, mode="quick"):
        self.suite("interviews", "interview", "interviewer")
        self.case("interviews", cid, case or {}, key or self.persona_key())
        return self.re.run("interviews", mode, out=lambda *_: None)


class CopyTests(JobSimBase):
    def test_the_copy_holds_only_what_a_job_needs(self):
        for d in ("private/plan", "vendor/x", "evals/s/keys"):
            (self.tmp / d).mkdir(parents=True, exist_ok=True)
        root = self.js.make_copy()
        try:
            self.assertEqual(sorted(p.name for p in root.iterdir()),
                             sorted([".claude", ".eval-copy", "config", "engine", "inbox", "jobs", "rules", "schemas"]))
            self.assertEqual(sorted(p.name for p in (root / ".claude/agents").iterdir()),
                             ["charter-critic.md", "charter-verifier.md", "charter-writer.md", "interviewer.md"])
            self.assertFalse((root / "engine/tests").exists())
            (root / "rules/keys").mkdir()
            with self.assertRaises(self.js.SimError):
                self.js.check_copy(root)
            (root / "rules/keys").rmdir()
            (root / "notes").mkdir()
            with self.assertRaises(self.js.SimError):
                self.js.check_copy(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_step_that_hangs_stops_with_its_name(self):
        root = self.js.make_copy()
        try:
            self.js.STEP_TIMEOUT = 0.01
            with self.assertRaises(self.js.SimError) as cm:
                self.js.state_cli(root, "status")
            self.assertIn("state.py status: no answer after 0.01 s", str(cm.exception))
        finally:
            self.js.remove_copy(root)

    def test_the_simulated_resume_acts_only_on_this_runs_copy(self):
        other = Path(tempfile.mkdtemp())
        try:
            (other / ".eval-copy").write_text("forged", encoding="utf-8")
            for root in (self.tmp, other, REPO):
                with self.assertRaises(self.js.SimError) as cm:
                    self.js.simulated_resume(root, self.job)
                self.assertIn("simulated resume refused", str(cm.exception))
        finally:
            shutil.rmtree(other, ignore_errors=True)


class PersonaTests(JobSimBase):
    def test_answers_by_field_with_a_probe_and_counts_wasted_and_repeated(self):
        key = self.persona_key()
        key["concrete"].pop("risk")                                       # never concrete
        p = self.js.Persona(key)
        self.assertEqual(p.answer(["current_process", "risk"]),
                         f"Q1: People sort it out.\n\nQ2: {self.js.CANT}\n")
        self.assertFalse(p.has_concrete("current_process"))
        self.assertEqual(p.answer(["current_process"]), "Q1: The coordinator copies swaps by hand.\n")
        self.assertTrue(p.has_concrete("current_process"))
        p.answer(["current_process", "goal"])       # both already concrete: repeated; goal has no script: wasted
        self.assertEqual((p.questions, p.wasted, p.repeated), (5, 2, 2))
        self.assertEqual(p.answer([None]), f"Q1: {self.js.CANT}\n")       # a question without a field
        self.assertEqual((p.playback(), p.playback()), ("Confirmed", "Confirmed"))


class InterviewRunTests(JobSimBase):
    def ask(self, *fields):
        return json.dumps({"status": "needs_input", "job_id": self.job,
                           "questions": [{"field": f, "text": f"About {f}? [{f}]"} for f in fields]})

    def test_a_persona_run_reaches_readiness_and_is_scored(self):
        self.fake("interviewer", self.ask("current_process"), self.ask("current_process"),
                  self.playback(self.job), self.status(self.job, playback="A04"))
        rep, code = self.interview()
        self.assertEqual(code, 0, rep)
        c = rep["cases"][0]
        self.assertEqual((c["outcomes"], c["recall_per_run"], c["rounds"], c["resumes"]),
                         (["ready"], ["2 of 2"], [3], [0]))
        self.assertEqual((c["ready_before_cap"], c["questions"], c["repeated"]), ([True], [2], [0]))
        self.assertEqual(c["injections_flagged"], [1])
        m = rep["metrics"]
        self.assertEqual((m["field_recall"], m["invalid_output_rate"], m["agent_calls"]), (1.0, 0.0, 4))
        self.assertIn("wrong field", m["limitation"])
        recs = [json.loads((self.tmp / f"cache/evals/interviews/runs/{r}.json").read_text(encoding="utf-8"))
                for r in rep["run_records"]]
        self.assertEqual([(r["case"], r["run"]) for r in recs], [("P1", 1)])
        ev = importlib.import_module("evalcheck")
        self.assertIsNone(ev.record_problem(rep))
        self.assertEqual(self.removed, [{}])                               # no gates/ file in the copy
        self.assertFalse(any((self.tmp / "jobs").iterdir()))               # nothing in the real jobs/

    def test_a_vague_field_marked_answered_fails_the_run(self):
        key = self.persona_key()                                           # asked once: still vague
        self.fake("interviewer", self.ask("current_process"), self.playback(self.job),
                  self.status(self.job, playback="A03"))
        rep, code = self.interview(key=key)
        self.assertEqual(code, 1)
        self.assertEqual(rep["cases"][0]["vague_marked_answered"], [["current_process"]])
        self.assertEqual(rep["cases"][0]["recall_per_run"], ["1 of 2"])

    def test_the_cycle_cap_gets_one_simulated_resume_recorded_per_persona(self):
        self.fake("interviewer", self.ask("risk"), self.ask("risk"), self.ask("current_process"),
                  self.ask("current_process"), self.playback(self.job), self.status(self.job, playback="A05"))
        rep, code = self.interview()
        c = rep["cases"][0]
        self.assertEqual((c["outcomes"], c["resumes"], c["ready_before_cap"]), (["ready"], [1], [False]), c)
        self.assertEqual(rep["metrics"]["resumes_per_case"], {"P1": [1]})
        self.assertEqual(c["wasted"], [2])

    def test_past_the_lifetime_cap_the_job_escalates_with_no_second_resume(self):
        self.fake("interviewer", *[self.ask("current_process")] * 8)
        key = self.persona_key(expect={"outcome": "escalated", "open_questions": ["current_process"]})
        rep, code = self.interview(key=key)
        c = rep["cases"][0]
        self.assertEqual((c["outcomes"], c["resumes"], c["rounds"]), (["escalated"], [1], [5]))
        self.assertEqual(code, 1)                                          # no status: no open questions with owners

    def test_a_false_ready_case_is_one_call(self):
        key = self.persona_key(probe_fields=["success_metrics"], expect={"outcome": "not_ready"}, injections=[])
        self.fake("interviewer", self.ask("success_metrics"))
        rep, code = self.interview(key=key, case={"single_call": True, "kind": "false_ready"})
        self.assertEqual((code, rep["cases"][0]["outcomes"], rep["metrics"]["false_ready_rate"]),
                         (0, ["not_ready"], 0.0))
        os.environ.pop("FAKE_CLAUDE_RESPONSES")
        (self.tmp / "responses.json").unlink()
        shutil.rmtree(self.tmp / "evals/interviews")
        self.fake("interviewer", self.status(self.job, playback=None))
        rep, code = self.interview(key=key, case={"single_call": True, "kind": "false_ready"})
        self.assertEqual((code, rep["cases"][0]["outcomes"], rep["metrics"]["false_ready_rate"]),
                         (1, ["false_ready"], 1.0))

    def test_a_stage_0_stop_is_its_own_outcome(self):
        self.fake("interviewer", json.dumps({"status": "stop", "job_id": self.job, "cites": ["[S:S01]"],
                                             "reason": "Stopped at stage 0: S01 holds customer records ([S:S01])."}))
        rep, code = self.interview(key=self.persona_key(expect={"outcome": "stopped"}, injections=[]))
        self.assertEqual((code, rep["cases"][0]["outcomes"], rep["cases"][0]["rounds"]), (0, ["stopped"], [0]))

    def test_an_end_to_end_job_reaches_the_gate_and_its_charter_is_compared(self):
        ex = json.loads((REPO / "schemas/examples/charter.v1.watering-rota.json").read_text(encoding="utf-8"))
        answers = json.loads((REPO / "schemas/examples/charter.v1.watering-rota.answers.json")
                             .read_text(encoding="utf-8"))["answers"]
        # one answer round holds the example's answers A02-A13, so the example charter cites A02 for all of them
        script = {"current_process": ["\n\n".join(a["text"] for a in answers[1:])]}
        key = self.persona_key(answers=script, expect={"outcome": "gate"},
                               reference_charter={"goal": {"accept": ["every plot is watered"], "cites": ["A:A01"]}},
                               invented_markers=["moon base"])
        key["concrete"]["current_process"] = 1
        ask = json.dumps({"status": "needs_input", "job_id": self.job, "questions": [
            {"field": "current_process", "text": "How? [current_process]"}]})
        self.fake("interviewer", ask, self.playback(self.job), self.status(self.job, playback="A03"))
        charter = json.dumps({k: v for k, v in ex.items() if k != "answers_ref"})
        self.fake("charter-writer", re.sub(r"\[A:A(0[2-9]|1[0-3])", "[A:A02", charter))
        review = {"job_id": self.job, "artifact_path": f"jobs/{self.job}/drafts/v1.json", "artifact_version": "v1",
                  "verdict": "pass", "findings": []}
        self.fake("charter-critic", json.dumps({**review, "reviewer": "charter-critic", "rules_checked": ["CH01"]}))
        self.fake("charter-verifier", json.dumps({**review, "reviewer": "charter-verifier", "rules_checked": ["CV01"]}))
        files = {"brief.md": answers[0]["text"]}
        self.suite("interviews", "interview", "interviewer")
        self.case("interviews", "E1", {"end_to_end": True}, key, files)
        rep, code = self.re.run("interviews", "quick", out=lambda *_: None)
        c = rep["cases"][0]
        self.assertEqual(c["outcomes"], ["gate"], c)
        e2e = c["end_to_end"][0]
        self.assertEqual((e2e["state"], e2e["fields_ok"], e2e["fields"], e2e["invented"]), ("GATE", ["goal"], 1, 0))

    def test_a_marker_word_in_any_rounds_prompt_stops_the_run(self):
        key = self.persona_key(answers={"current_process": ["We use the zebracorn sheet."]})
        self.fake("interviewer", self.ask("current_process"), self.playback(self.job))
        out = []
        self.suite("interviews", "interview", "interviewer")
        self.case("interviews", "P1", {}, key)
        rep, code = self.re.run("interviews", "quick", out=out.append)
        self.assertEqual((rep, code), (None, 2))
        self.assertTrue(any("zebracorn" in o for o in out), out)
        self.assertEqual(len(self.calls()), 1)                             # stopped before the second call
        self.assertFalse((self.tmp / "evals/reports").exists() and any((self.tmp / "evals/reports").iterdir()))


class CharterRunTests(JobSimBase):
    def setUp(self):
        super().setUp()
        self.example = json.loads((REPO / "schemas/examples/charter.v1.watering-rota.json").read_text(encoding="utf-8"))
        self.answers = json.loads((REPO / "schemas/examples/charter.v1.watering-rota.answers.json")
                                  .read_text(encoding="utf-8"))["answers"]

    def charter_case(self, cid="W1", key=None, case=None, extra_files=None):
        self.suite("charters", "charter", "charter-writer")
        files = {"brief.md": self.answers[0]["text"]}
        files.update({f"a{i:02d}.md": a["text"] for i, a in enumerate(self.answers[1:], 2)})
        ask = {"status": "needs_input", "job_id": "{{JOB}}",
               "questions": [{"field": "current_process", "text": "How? [current_process]"}]}
        playback = {"status": "needs_input", "job_id": "{{JOB}}", "kind": "playback", "playback": "Situation (goal)."}
        files.update({"r1.json": json.dumps(ask), "r2.json": json.dumps(playback), "confirmed.md": "Confirmed",
                      "r3.json": self.status("{{JOB}}", playback="A14"), **(extra_files or {})})
        replay = [{"interviewer": "r1.json", "reply": [f"a{i:02d}.md" for i in range(2, 14)]},
                  {"interviewer": "r2.json", "reply": "confirmed.md"}, {"interviewer": "r3.json"}]
        key = key or {"canary": "zebracorn", "expect": "charter",
                      "fields": {"goal": {"accept": ["every plot is watered"], "cites": ["A:A01"]}},
                      "invented_markers": ["moon base"]}
        return self.case("charters", cid, {"kind": "clean", "seed": "replay", "replay": replay, **(case or {})},
                         key, files)

    def charter(self):
        return json.dumps({k: v for k, v in self.example.items() if k != "answers_ref"})

    def review(self, agent, verdict):
        return json.dumps({"job_id": self.job, "reviewer": agent, "artifact_path": f"jobs/{self.job}/drafts/v1.json",
                           "artifact_version": "v1", "verdict": verdict, "findings": [],
                           "rules_checked": ["CH01"] if agent == "charter-critic" else ["CV01"]})

    def test_a_writer_case_is_scored_and_the_draft_goes_once_through_both_reviewers(self):
        self.charter_case()
        self.fake("charter-writer", self.charter())
        self.fake("charter-critic", self.review("charter-critic", "pass"))
        self.fake("charter-verifier", self.review("charter-verifier", "pass"))
        out = []
        rep, code = self.re.run("charters", "quick", out=out.append)
        self.assertEqual(code, 0, out)
        c = rep["cases"][0]
        self.assertEqual((c["outcomes"], c["fields_ok"], c["recall_per_run"]), (["done"], ["goal"], ["1 of 1"]))
        fpa = c["first_pass_acceptance"]
        self.assertEqual((fpa["accepted"], fpa["state"], fpa["verdicts"]), (True, "GATE", ["pass", "pass"]), fpa)
        self.assertEqual(rep["metrics"]["invented_cases"], 0)
        self.assertIsNone(importlib.import_module("evalcheck").record_problem(rep))
        stages = [c["argv"] for c in self.calls()]
        self.assertEqual(len(stages), 3)                                     # the replay made no CLI call

    def test_a_failing_reviewer_means_not_accepted_and_invented_content_fails_the_case(self):
        key = {"canary": "zebracorn", "expect": "charter", "invented_markers": ["Every plot is watered"],
               "fields": {"goal": {"accept": ["every plot is watered"], "cites": ["A:A01"]}}}
        self.charter_case(key=key)
        self.fake("charter-writer", self.charter())
        self.fake("charter-critic", self.review("charter-critic", "fail"))
        rep, code = self.re.run("charters", "quick", out=lambda *_: None)
        c = rep["cases"][0]
        self.assertEqual((code, c["pass"], c["invented_per_run"], rep["metrics"]["invented_cases"]), (1, False, [1], 1))
        fpa = c["first_pass_acceptance"]
        self.assertEqual((fpa["accepted"], fpa["state"], fpa["verdicts"]), (False, "REVISING", ["fail"]))

    def test_a_needs_input_case_matches_the_exact_question(self):
        key = {"canary": "zebracorn", "expect": "needs_input", "question": {"accept": ["who approves a swap"]}}
        self.charter_case(key=key)
        self.fake("charter-writer", json.dumps({"status": "needs_input", "job_id": self.job,
                                                "questions": ["Who approves a swap? (users_and_stakeholders)"]}))
        rep, code = self.re.run("charters", "quick", out=lambda *_: None)
        self.assertEqual((code, rep["cases"][0]["question_ok"], rep["cases"][0]["outcomes"]),
                         (0, [True], ["needs_input"]))

    def test_a_fixture_job_is_copied_as_authored_and_the_runner_writes_nothing_under_gates(self):
        self.charter_case(cid="W0")                                        # build a fixture from a replayed job
        root = self.js.make_copy()
        case = self.re.load_cases(self.re.load_suite("charters"))[0]
        job = self.js.seed_charter_job(root, case)
        override = {"job_id": job, "reason": "Approver accepted the gap (fixture).", "by": "Test Approver",
                    "at": "2026-10-30T00:00:00+00:00", "score": 6, "threshold": 7, "failed": [2], "report": None}
        (root / f"jobs/{job}/gates").mkdir(exist_ok=True)
        (root / f"jobs/{job}/gates/readiness-override.json").write_text(json.dumps(override), encoding="utf-8")
        d = self.tmp / "evals/charters/cases/W3"
        shutil.copytree(root / f"jobs/{job}", d / "job")
        shutil.rmtree(root)
        self.js._COPIES.clear()
        shutil.rmtree(self.tmp / "evals/charters/cases/W0")
        (self.tmp / "evals/charters/keys/W0.json").unlink()
        (d / "case.json").write_text(json.dumps({"id": "W3", "kind": "planted", "seed": "fixture", "job": "job"}),
                                     encoding="utf-8")
        self.dump("evals/charters/keys/W3.json", {"canary": "zebracorn", "expect": "needs_input",
                                                  "question": {"accept": ["success"]}})
        self.fake("charter-writer", json.dumps({"status": "needs_input", "job_id": self.job,
                                                "questions": ["What number counts as success? (success_metrics)"]}))
        self.removed.clear()
        rep, code = self.re.run("charters", "quick", out=lambda *_: None)
        self.assertEqual(code, 0, rep)
        authored = {f"jobs/{job}/{p.relative_to(d / 'job').as_posix()}": p.read_bytes()
                    for p in (d / "job").rglob("*") if p.is_file() and "gates" in p.parts}
        self.assertEqual(self.removed, [authored])                          # exactly the fixture's bytes
        src = (self.tmp / "evals/jobsim.py").read_text(encoding="utf-8")
        code_lines = [ln for ln in src.splitlines() if "gates" in ln and not ln.lstrip().startswith(("#", "-"))]
        self.assertEqual([ln for ln in code_lines if "record_override" in ln or "open(" in ln], [])
        self.assertNotIn("readiness-override", src)
        self.assertNotIn("record_override", src)


class ScoringItemsTests(JobSimBase):
    def reviewer_score(self, findings, key):
        s = {"kind": "reviewer", "severities": {"TR01": "blocker", "TR15": "minor"}, "rulebook": "rules/test-rulebook.md",
             "agent_spec": {"name": "critic"}}
        case = {"id": "C1", "dir": self.tmp, "artifact": "a.md", "key": key}
        doc = {"job_id": "eval-C1", "reviewer": "critic", "artifact_path": self.lc.rel(self.tmp / "a.md"),
               "artifact_version": "v1", "findings": findings,
               "verdict": "fail" if any(f["severity"] == "blocker" for f in findings) else "pass",
               "rules_checked": ["TR01", "TR15"]}
        schema = json.loads((self.tmp / "schemas/findings.schema.json").read_text(encoding="utf-8"))
        return self.re.score(json.dumps(doc), s, case, schema)

    def finding(self, rule, sev, i=1):
        return {"id": f"F{i}", "rule": rule, "severity": sev, "location": "line 1", "issue": "x", "fix": "y"}

    def test_false_findings_count_on_clean_cases_too(self):
        sc = self.reviewer_score([self.finding("TR15", "minor")], {"must_find": [], "verdict": "pass"})
        self.assertEqual((sc["false_findings"], sc["findings"]), (1, 1))     # before: 0 (the key had no locations)
        sc = self.reviewer_score([self.finding("TR01", "blocker"), self.finding("TR15", "minor", 2)],
                                 {"must_find": ["TR01"], "verdict": "fail"})
        self.assertEqual((sc["false_findings"], sc["findings"]), (1, 2))

    def test_recall_is_also_reported_per_run(self):
        s = {"kind": "reviewer", "severities": {"TR01": "blocker"}}
        cases = [{"id": "C1", "kind": "planted", "key": {"must_find": ["TR01"], "verdict": "fail"}}]
        runs = [{"score": {"valid": True, "found": f, "verdict": "fail", "false_findings": 0, "findings": len(f)},
                 "usage": None} for f in (["TR01"], [], ["TR01"])]
        per_case, m = self.re.aggregate(s, cases, {"C1": runs}, {"case_majority": 2})
        self.assertEqual((m["recall_blocker"], m["recall_per_run"]), (1.0, 0.667))
        self.assertEqual(per_case[0]["runs_recalled"], "2 of 3")
        self.assertEqual(m["false_finding_rate"], 0.0)
