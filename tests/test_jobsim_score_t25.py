"""T2.5 sample review (Samith, 2026-11-02): the job suites' scoring reads the parsed charter, not its JSON text.
Invented-content rules (invented_entries) match list entries by field, whatever the key order; text markers search
the free text only. The persona's playback reply is keyword-triggered: a playback missing a required point gets the
scripted correction, and corrections are counted. Pure functions: no copy, no engine step, no model call."""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
from support import LabTestBase  # noqa: E402

RULES = {"invented_entries": [
    {"field": "users_and_stakeholders", "match": {"role": "shift.?lead", "relation": "^approver$"}},
    {"field": "users_and_stakeholders", "match": {"relation": "^approver$", "role": "^(?!.*volunteer.?coordinator)"}}],
    "invented_markers": ["notice period"]}


def charter(*entries, extra=None):
    """A charter fragment whose user entries are given as (key, value) pairs, in the order written."""
    doc = {"users_and_stakeholders": [dict(e) for e in entries], "quality_rulebook": {"rules": []}}
    doc.update(extra or {})
    return json.loads(json.dumps(doc))                    # parsed back, as the scorer reads a saved draft


class JobsimBase(LabTestBase):
    """jobsim from this test's copy (the base purges every evals module first), never from the real repo."""

    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.tmp / "evals"))
        self.js = importlib.import_module("jobsim")

    def tearDown(self):
        while str(self.tmp / "evals") in sys.path:
            sys.path.remove(str(self.tmp / "evals"))
        super().tearDown()


class InventedEntryTests(JobsimBase):
    def test_an_invented_approver_is_found_in_either_key_order(self):
        role_first = charter([("role", "shift-lead"), ("relation", "approver"), ("interest", "Signs off.")])
        relation_first = charter([("relation", "approver"), ("interest", "Signs off."), ("role", "Shift lead")])
        for doc in (role_first, relation_first):
            got = self.js.charter_fields(doc, RULES)
            self.assertEqual(got["invented_entries"], ["users_and_stakeholders[0]", "users_and_stakeholders[0]"])
            self.assertEqual(got["invented"], 2)

    def test_the_settled_approver_and_other_relations_are_not_invented(self):
        doc = charter([("relation", "approver"), ("role", "volunteer-coordinator")],
                      [("role", "shift-lead"), ("relation", "stakeholder")],
                      [("role", "walking-volunteers"), ("relation", "user")])
        self.assertEqual(self.js.charter_fields(doc, RULES), {"fields_ok": [], "invented": 0, "invented_entries": []})

    def test_text_markers_search_only_the_free_text(self):
        clean = charter([("role", "volunteer-coordinator"), ("relation", "approver")])
        self.assertEqual(self.js.charter_fields(clean, {"invented_markers": ["relation"]})["invented"], 0)   # a key name
        noted = charter([("role", "volunteer-coordinator"), ("relation", "approver")],
                        extra={"glossary": [{"term": "swap", "meaning": "Asked with a 24-hour Notice  Period."}]})
        self.assertEqual(self.js.charter_fields(noted, RULES)["invented"], 1)

    def test_a_missing_or_odd_field_path_finds_nothing(self):
        rules = {"invented_entries": [{"field": "quality_rulebook.rules", "match": {"statement": "notice"}},
                                      {"field": "no_such_field.items", "match": {"x": "y"}}]}
        self.assertEqual(self.js.charter_fields(charter(), rules)["invented_entries"], [])
        doc = charter(extra={"quality_rulebook": {"rules": [{"id": "Q09", "statement": "Give 2 days' notice."}]}})
        self.assertEqual(self.js.charter_fields(doc, rules)["invented_entries"], ["quality_rulebook.rules[0]"])


class PlaybackCheckTests(JobsimBase):
    CHECK = {"must_contain": [["hall coordinator", "hall-coordinator"], ["weekly bookings are out", "only one-off"]],
             "correction": "Not quite: the hall coordinator approves, and weekly bookings are out."}

    def test_a_playback_missing_a_point_gets_the_correction_each_time(self):
        p = self.js.Persona({"playback_check": self.CHECK})
        self.assertEqual(p.playback("The committee chair approves; weekly bookings are out."), self.CHECK["correction"])
        self.assertEqual(p.playback("The hall coordinator approves."), self.CHECK["correction"])
        self.assertEqual(p.corrections, 2)

    def test_a_playback_with_every_point_is_confirmed_in_any_case_and_spacing(self):
        p = self.js.Persona({"playback_check": self.CHECK})
        self.assertEqual(p.playback("The Hall\nCoordinator approves. ONLY one-off requests."), "Confirmed")
        self.assertEqual(p.corrections, 0)

    def test_without_a_check_the_scripted_replies_are_used_in_turn(self):
        p = self.js.Persona({"playback": ["Fix the scope.", "Confirmed"]})
        self.assertEqual([p.playback("x"), p.playback("y"), p.playback("z")], ["Fix the scope.", "Confirmed", "Confirmed"])
        self.assertEqual(p.corrections, 0)
