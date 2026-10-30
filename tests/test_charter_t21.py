"""T2.1: charter v1 (schemas/charter.v1.*, engine/designcheck.py). Every example passes; every planted fault is
caught with its own message (faults planted on in-memory copies, written to a temp folder). No live calls."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent   # factory-only test (tests/): never copied into an ecosystem
EXAMPLES = REPO / "schemas" / "examples"
sys.path.insert(0, str(REPO / "engine"))
import designcheck  # noqa: E402


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def charters():
    return sorted(p for p in EXAMPLES.glob("charter.v1.*.json") if not p.name.endswith(".answers.json"))


class CharterV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.good = load(EXAMPLES / "charter.v1.action-items.json")
        self.answers = load(EXAMPLES / self.good["answers_ref"])

    def check(self, doc, answers=None):
        (self.tmp / doc.get("answers_ref", self.good["answers_ref"])).write_text(json.dumps(answers or self.answers), encoding="utf-8")
        f = self.tmp / "charter.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        return designcheck.check_charter(f)

    def test_every_example_passes(self):
        self.assertGreaterEqual(len(charters()), 1)
        for p in charters():
            self.assertEqual(designcheck.check_charter(p), [], p.name)
            self.assertIn("answers_ref", load(p), p.name)   # examples carry their answers

    def test_planted_faults_are_caught(self):
        g = self.good
        faults = (
            # schema
            (lambda d: d.pop("goal"), "missing required field 'goal'"),
            (lambda d: d.update(extra=1), "unexpected field 'extra'"),
            (lambda d: d["quality_rulebook"]["rules"][0].pop("severity"), "missing required field 'severity'"),
            (lambda d: d["quality_rulebook"]["rules"][0].update(severity="critical"), "not one of"),
            (lambda d: d["quality_rulebook"]["rules"][0].update(id="DR07"), "does not match"),
            (lambda d: d["data_classification"].update({"class": "confidential"}), "not one of"),
            (lambda d: d["data_classification"].update({"class": "customer"}), "not one of"),
            (lambda d: d["examples"]["bad"].pop(), "needs at least 2"),
            (lambda d: d["examples"]["good"].pop(), "needs at least 2"),
            (lambda d: d["goal"].update(cites=[]), "needs at least 1"),
            (lambda d: d["goal"].update(cites=["[G:some-job]"]), "does not match"),
            (lambda d: d["open_questions"][0].pop("owner"), "missing required field 'owner'"),
            # hand checks
            (lambda d: d["quality_rulebook"]["rules"][1].update(id="Q01"), "quality rule Q01 appears twice"),
            (lambda d: d["examples"]["bad"][0].update(breaks=["Q09"]), "breaks unknown rule Q09"),
            (lambda d: d["goal"].update(cites=["[A:A01"]), "is not well formed"),
            (lambda d: d["goal"].update(cites=["[S:S09 §top]"]), "[S:S09] is not in the context inventory"),
            (lambda d: d["goal"].update(cites=["[A:A99]"]), "[A:A99] is not an answer"),
            (lambda d: d["goal"].update(cites=['[A:A01 "Turn two meetings"]']), "not word for word in answer A01"),
            (lambda d: d["goal"].update(cites=['[A:A01 "' + " ".join(["word"] * 26) + '"]']), "longer than 25 words"),
            (lambda d: d["acceptance_tests"][0].update(cites=["[A:A08]"]), "words are not quoted from an answer"),
            (lambda d: d["inputs"]["samples"][0].update(source="S02"), "input sample S02 is not in the context inventory"),
            (lambda d: d["data_classification"].update({"class": "internal"}), "data classification internal is not allowed"),
            (lambda d: d["context_inventory"][0].update(classification="internal"), "classification internal is not allowed"),
            (lambda d: d["context_inventory"][0].update(classification="public"), "above the charter's synthetic"),
            (lambda d: d["source_policy"]["ranks"][4].update(rank=4), "must be exactly 1 to 5"),
            (lambda d: d["source_policy"]["official_sources"]["files"].update({"inputs/context/other.txt": 2}),
             "other.txt is not in the context inventory"),
            (lambda d: d["users_and_stakeholders"].pop(1), "users_and_stakeholders has no approver"),
            (lambda d: d["open_questions"][0].update(owner="mayor"), "owner mayor is not a role"),
            (lambda d: d["gates"][0].update(before_write=["rota-sheet"]), "rota-sheet, which is not a write system"),
            (lambda d: d["gates"][0].update(mode="auto"), "mode must be 'human' until Phase 5"),
            (lambda d: d["caps"].update(agent_calls_per_job=99), "caps.agent_calls_per_job 99 is above the factory's"),
            (lambda d: d["caps"]["usage_ceiling"].update(tokens=10 ** 9), "caps.usage_ceiling.tokens is above"),
            (lambda d: d["caps"].update(critic_revisions=3, total_revisions_before_gate=2),
             "critic_revisions is above caps.total_revisions_before_gate"),
            (lambda d: d["scope"]["out"].append("TBD"), "'TBD' is not allowed; make it an open question"),
            (lambda d: d["output"].update(format="To be decided"), "is not allowed; make it an open question"),
            (lambda d: d["risk"].update(notes="We don't know yet."), "is not allowed; make it an open question"),
        )
        for change, expect in faults:
            d = copy.deepcopy(g)
            change(d)
            probs = self.check(d)
            self.assertTrue(any(expect in p for p in probs), (expect, probs))

    def test_every_write_has_a_gate_placed_before_it(self):
        """The rota example: a gate on review only does not cover the write to the rota sheet."""
        rota = load(EXAMPLES / "charter.v1.watering-rota.json")
        answers = load(EXAMPLES / rota["answers_ref"])
        board = {"id": "notice-board", "description": "A second sheet (fictional).", "access": "write", "cites": ["[A:A10]"]}
        for change in (lambda d: d["gates"][1].update(before_write=[]),         # review gate kept, write ungated
                       lambda d: d["gates"].pop(1),                             # only the review gate left
                       lambda d: d["systems"].append(board)):                   # a second write, no gate before it
            d = copy.deepcopy(rota)
            change(d)
            probs = self.check(d, answers)
            self.assertTrue(any("no gate is placed before this write" in p for p in probs), probs)
        self.assertEqual(self.check(rota, answers), [])

    def test_unknowns_as_open_questions_and_quotes_pass(self):
        d = copy.deepcopy(self.good)
        d["open_questions"].append({"id": "OQ02", "question": "TBD: who keeps the archive? We don't know yet.",
                                    "owner": "treasurer"})
        self.assertEqual(self.check(d), [])

    def test_bad_answers_file_fails_closed(self):
        self.assertTrue(any("answers_ref" in p for p in self.check(self.good, {"answers": [{"id": "B1"}]})))
        d = copy.deepcopy(self.good)
        d["answers_ref"] = "missing.json"
        f = self.tmp / "no-answers.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        self.assertTrue(any("unreadable" in p for p in designcheck.check_charter(f)))

    def test_allowed_classes_come_from_config(self):
        cfg = load(REPO / "config" / "data-classes.json")
        self.assertEqual(cfg["allowed"], ["synthetic", "public"])
        schema = load(REPO / "schemas" / "charter.v1.schema.json")
        self.assertEqual(schema["$defs"]["data_class"]["enum"], ["synthetic", "public", "internal"])

    def test_blueprint_v0_refuses_a_v1_charter(self):
        bp = load(REPO / "docs" / "thin" / "blueprint.json")
        bp["charter_ref"] = "schemas/examples/charter.v1.action-items.json"
        f = self.tmp / "bp.json"
        f.write_text(json.dumps(bp), encoding="utf-8")
        self.assertTrue(any("blueprint v0 needs a charter v0" in p for p in designcheck.check_blueprint(f)))


if __name__ == "__main__":
    unittest.main()
