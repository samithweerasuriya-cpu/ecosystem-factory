"""T2.5 (before any live call): handoff parity for every route agent. An evaluation case and the job step it
stands for get the same prompt, compared as full text (rendered handoff and every inlined file) apart from the
IDs and the paths that carry them: the same rules, input labels and order, ROUNDS line, review line and output
format. Lesson 13 recurred in T2.4: the interviewer's evaluation handoff had no ROUNDS line, and the old parity
test compared one critic only. Covered: the factory's intake route and the thin ecosystem's actions route
(action-writer, action-critic), rendered from docs/thin/blueprint.json into the test copy. Factory-only test
(tests/): engine/tests is copied into every generated ecosystem. Every agent call uses fake_claude.py."""
import importlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
from support import REPO  # noqa: E402
from test_agent_call_t13 import AgentCallBase  # noqa: E402
from test_intake_t24 import IntakeBase  # noqa: E402

SUITE = "parity-check"
ROLES = {"artifact": None, "earlier stage output": "earlier", "your earlier questions": "questions",
         "gate feedback": "feedback"}


class ParityMixin:
    """Builds an evaluation case from a job's own files, each tagged with the role a case author gives it, and
    compares the two prompts. Needs self.agent ({name: agent file}) and the runner imported as self.re."""

    def import_runner(self):
        sys.path.insert(0, str(self.tmp / "evals"))
        self.re = importlib.import_module("run_evals")
        self.covered = set()

    def drop_runner_path(self):
        while str(self.tmp / "evals") in sys.path:
            sys.path.remove(str(self.tmp / "evals"))

    def case_from_job(self, job, agent, case_id):
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
                shutil.copytree(src, d / "evidence")
                inputs.append({"file": "evidence", "as": "evidence"})
                pairs.append((i["path"], f"{self.lc.rel(d / 'evidence')}/"))
                continue
            name = f"{n:02d}-{src.name}"
            shutil.copy(src, d / name)
            role = ROLES.get(label, "context" if label.startswith("context ") else "answer")
            if role is None:
                artifact = name
                inputs.append(name)
            else:
                inputs.append({"file": name, "as": role})
            pairs.append((i["path"], self.lc.rel(d / name)))
        case = {"id": case_id, "dir": d, "inputs": inputs, "goal": st["goal"], "counters": st["counters"]}
        if artifact:
            case["artifact"] = artifact
        s = {"name": SUITE, "kind": "reviewer" if st["stage_kind"] == "review" else "agent",
             "agent_spec": self.ac.parse_agent(self.agent[agent]), "rulebook": "rules/default-agent-rules.md"}
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

    def assert_every_route_agent_covered(self, routes, agent_dir):
        on_routes = {x["agent"] for r in routes.values() if not r.get("stand_in_agents")
                     for x in r["stages"] + r["reviews"] + [{"agent": r.get("deliver")}]
                     if x.get("agent") and (agent_dir / f"{x['agent']}.md").is_file()}
        self.assertTrue(on_routes)
        self.assertEqual(on_routes - self.covered, set(), "a route agent with no parity check")


class RouteAgentParityTests(ParityMixin, IntakeBase):
    def setUp(self):
        super().setUp()
        self.import_runner()

    def tearDown(self):
        self.drop_runner_path()
        super().tearDown()

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
        self.assert_every_route_agent_covered(routes, REPO / ".claude/agents")

    def test_a_case_role_outside_the_list_is_refused(self):
        with self.assertRaises(self.re.Refused):
            self.re.case_inputs({"id": "E009", "inputs": [{"file": "a.md", "as": "instructions"}]})


class ThinRouteParityTests(ParityMixin, AgentCallBase):
    """The thin ecosystem's route, rendered by the generator (in memory) from docs/thin/blueprint.json into this
    test's copy, so the action agents are checked with the files a generated ecosystem gets. Nothing is
    written to C:\\ecosystems."""
    auto_result = False

    def setUp(self):
        super().setUp()
        for d in ("docs/thin", "templates"):
            shutil.copytree(REPO / d, self.tmp / d, dirs_exist_ok=True)
        shutil.copy(REPO / ".gitattributes", self.tmp / ".gitattributes")     # the generator copies it
        gen = importlib.import_module("generate")
        _, plan = gen.build(self.tmp / "docs/thin/blueprint.json")
        for rel, f in plan.items():
            if rel.startswith(("config/", "rules/", "schemas/", ".claude/agents/")):
                p = self.tmp / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(f["data"])
        self.routes = json.loads((self.tmp / "config/routes.json").read_text(encoding="utf-8"))["routes"]
        self.agent = {p.stem: p for p in (self.tmp / ".claude/agents").glob("*.md")}
        self.import_runner()

    def tearDown(self):
        self.drop_runner_path()
        super().tearDown()

    def test_the_action_agents_get_their_job_handoff_in_an_evaluation(self):
        (route_name, r), = self.routes.items()
        j = self.lc.new_job(route_name, "standup", "Action items from the standup notes")["job_id"]
        notes = self.tmp / "inbox/notes.md"
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text("The chair will send the agenda by Friday.\n", encoding="utf-8")
        self.lc.record_input(j, str(notes), "synthetic")
        self.lc.apply(j, "dispatch")
        writer, critic = r["stages"][0]["agent"], r["reviews"][0]["agent"]
        self.assert_parity(j, writer, "E001")
        art = self.write(f"jobs/{j}/drafts/v1.json", "{}")
        self.lc.apply(j, "artifact_ready", artifact=art)
        p = self.assert_parity(j, critic, "E002")
        self.assertIn("REVIEW: critic", p)
        self.assertEqual((writer, critic), ("action-writer", "action-critic"))
        self.assert_every_route_agent_covered(self.routes, self.tmp / ".claude/agents")
