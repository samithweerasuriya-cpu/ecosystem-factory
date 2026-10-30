"""T2.5 (before any live call): handoff parity for every route agent. An evaluation case and the job step it
stands for get the same prompt, compared as full text (rendered handoff and every inlined file) apart from the
IDs and the paths that carry them: the same rules, input labels and order, ROUNDS line, review line and output
format. Lesson 13 recurred in T2.4: the interviewer's evaluation handoff had no ROUNDS line, and the old parity
test compared one critic only. Every agent call uses fake_claude.py instead of the real CLI."""
import importlib
import json
import shutil
import sys

from support import REPO
from test_intake_t24 import IntakeBase

SUITE = "parity-check"


class RouteAgentParityTests(IntakeBase):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.tmp / "evals"))
        self.re = importlib.import_module("run_evals")
        self.covered = set()

    def tearDown(self):
        while str(self.tmp / "evals") in sys.path:
            sys.path.remove(str(self.tmp / "evals"))
        super().tearDown()

    def case_from_job(self, job, agent, case_id):
        """An evaluation case built from the job's own files, each tagged with the role a case author gives it."""
        h = self.lc.build_handoff(job)
        st = self.lc.load_state(job)
        d = self.tmp / f"evals/{SUITE}/cases/{case_id}"
        d.mkdir(parents=True)
        inputs, pairs, artifact = [], [], None
        for n, i in enumerate(h["inputs"]):
            label, src = i["label"], self.tmp / i["path"]
            if label in ("brief", "source registry"):              # built from the goal; found in the evidence pack
                continue
            if label == "evidence pack":
                name = "evidence"
                shutil.copytree(src, d / name)
                inputs.append({"file": name, "as": "evidence"})
                pairs.append((i["path"], f"{self.lc.rel(d / name)}/"))
                continue
            name = f"{n:02d}-{src.name}"
            shutil.copy(src, d / name)
            role = {"artifact": None, "earlier stage output": "earlier", "your earlier questions": "questions",
                    "gate feedback": "feedback"}.get(label, "context" if label.startswith("context ") else "answer")
            if role is None:
                artifact = name
                inputs.append(name)
            else:
                inputs.append({"file": name, "as": role})
            pairs.append((i["path"], self.lc.rel(d / name)))
        case = {"id": case_id, "dir": d, "inputs": inputs, "goal": st["goal"], "counters": st["counters"]}
        if artifact:
            case["artifact"] = artifact
        spec = self.ac.parse_agent(self.agent[agent])
        s = {"name": SUITE, "kind": "reviewer" if st["stage_kind"] == "review" else "agent", "agent_spec": spec,
             "rulebook": "rules/default-agent-rules.md"}
        return h, s, case, pairs

    def assert_parity(self, job, agent, case_id):
        h, s, case, pairs = self.case_from_job(job, agent, case_id)
        job_prompt = self.ac.compose_prompt(self.ac.parse_agent(self.agent[agent]), h, "H001")
        eval_h = self.re.eval_handoff(s, case)
        eval_prompt = self.re.build_prompt(s, case)
        self.assertEqual([i["label"] for i in eval_h["inputs"]], [i["label"] for i in h["inputs"]], agent)
        self.assertEqual((eval_h["rules"], eval_h.get("rounds"), eval_h.get("review_kind")),
                         (h["rules"], h.get("rounds"), h.get("review_kind")), agent)
        subs = [(a, f"<IN{n}>") for n, (a, _) in enumerate(pairs)] + [(b, f"<IN{n}>") for n, (_, b) in enumerate(pairs)]
        subs += [(h["output_dir"], "<OUT>"), (self.re.EVAL_OUTPUT_DIR, "<OUT>"), (job, "<JOB>"),
                 (f"eval-{case_id}", "<JOB>")]

        def norm(text):
            for a, b in sorted(subs, key=lambda p: -len(p[0])):
                text = text.replace(a, b)
            return text

        self.assertEqual(norm(eval_prompt), norm(job_prompt), agent)
        self.covered.add(agent)
        return eval_prompt

    def test_every_route_agent_gets_its_job_handoff_in_an_evaluation(self):
        j = self.new_intake()
        self.respond(j, self.ask(j, "How is the rota built today? [current_process]"), self.playback(j), self.status(j))
        self.ac.call_job(j, self.agent["interviewer"])
        self.answer(j, "By hand on paper.")
        p = self.assert_parity(j, "interviewer", "E001")                   # mid-interview: rounds used, questions
        self.assertIn("ROUNDS: question rounds used 1 of 3 this cycle, 1 of 5 in the job's lifetime", p)

        self.ac.call_job(j, self.agent["interviewer"])
        self.answer(j, "Confirmed.")
        self.ac.call_job(j, self.agent["interviewer"])
        self.lc.apply(j, "stage_done")
        self.lc.run_script(j)
        p = self.assert_parity(j, "charter-writer", "E002")                # rules: charter schema + both rulebooks
        self.assertIn("ROUNDS: question rounds used 2 of 3 this cycle", p)
        self.assertIn("=== rules: rules/charter-verifier.md", p)

        art = self.write(f"jobs/{j}/drafts/v1.json", "{}")
        self.lc.apply(j, "artifact_ready", artifact=art)
        p = self.assert_parity(j, "charter-critic", "E003")
        self.assertIn("REVIEW: critic", p)
        self.assertNotIn("ROUNDS:", p)
        self.lc.apply(j, "review_pass")
        p = self.assert_parity(j, "charter-verifier", "E004")              # evidence pack, registry, context
        self.assertIn("REVIEW: verifier", p)
        self.assertIn("source registry", p)

        routes = json.loads((REPO / "config/routes.json").read_text(encoding="utf-8"))["routes"]
        on_routes = {x["agent"] for r in routes.values() if not r.get("stand_in_agents")
                     for x in r["stages"] + r["reviews"] + [{"agent": r.get("deliver")}]
                     if x.get("agent") and (REPO / f".claude/agents/{x['agent']}.md").is_file()}
        self.assertEqual(on_routes - self.covered, set(), "a route agent with no parity check")

    def test_a_case_role_outside_the_list_is_refused(self):
        with self.assertRaises(self.re.Refused):
            self.re.case_inputs({"id": "E009", "inputs": [{"file": "a.md", "as": "instructions"}]})
