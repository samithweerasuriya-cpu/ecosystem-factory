"""T2.3: the interview guide's question bank maps one-to-one to charter v1 with the brief's labels; stage 0 qualifies
against config/data-classes.json; the round limit comes from config/caps.json; every probe has its five parts; the
question rules cover contradictions and instruction-like text; complete criteria feed the readiness score; SCQA
playback."""
import json
import re
import unittest

from support import REPO

GUIDE = REPO / "rules/interview-guide.md"
BRIEF = REPO / "templates/intake/problem-brief.md"
LABEL_WORDS = r"you must answer|answer if you know|defaults offered"


def text():
    return GUIDE.read_text(encoding="utf-8")


def section(heading):
    """Body of the '## heading' section, up to the next '## '."""
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text(), flags=re.M | re.S)
    assert match, heading
    return match.group(1)


def bank_rows():
    """[(field, label)] from the question-bank tables."""
    return re.findall(rf"^\| `(\w+)` \| ({LABEL_WORDS}) \|", section("Staged question bank"), flags=re.M)


def brief_labels():
    brief = BRIEF.read_text(encoding="utf-8")
    parts = re.split(r"^## .*?<!-- field: (\w+) -->\s*$", brief, flags=re.M)
    return {f: re.search(r"^\*\*Label:\*\* (.+)$", body, flags=re.M).group(1)
            for f, body in zip(parts[1::2], parts[2::2])}


class InterviewGuideTests(unittest.TestCase):
    def test_bank_is_one_to_one_with_charter_v1(self):
        schema = json.loads((REPO / "schemas/charter.v1.schema.json").read_text(encoding="utf-8"))
        fields = [f for f, _ in bank_rows()]
        self.assertEqual(len(fields), len(set(fields)), "a field is in the bank twice")
        self.assertEqual(set(fields), set(schema["required"]) - {"schema_version"})

    def test_bank_labels_match_the_brief(self):
        self.assertEqual(dict(bank_rows()), brief_labels())

    def test_stages_zero_to_seven_in_order(self):
        stages = [int(n) for n in re.findall(r"^#{2,3} Stage (\d):", text(), flags=re.M)]
        self.assertEqual(stages, list(range(8)))

    def test_stage_zero_qualifies_on_the_data_class_config_and_scope(self):
        body = section("Stage 0: qualify first")
        self.assertIn("config/data-classes.json", body)
        for cls in json.loads((REPO / "config/data-classes.json").read_text(encoding="utf-8"))["allowed"]:
            self.assertIn(cls, body)
        for words in ("stops the interview", "reason", "internal", "confidential", "in scope"):
            self.assertIn(words, body.lower())
        self.assertLess(text().index("## Stage 0"), text().index("### Stage 1"))

    def test_round_limit_is_stated_from_the_caps(self):
        caps = json.loads((REPO / "config/caps.json").read_text(encoding="utf-8"))
        body = section("Round limit")
        self.assertIn("config/caps.json", body)
        for key in ("input_rounds_per_cycle", "input_rounds"):
            self.assertRegex(body, rf"`{key}` \({caps[key]}\b")
        for words in ("open question with an owner", "escalates"):
            self.assertIn(words, body)

    def test_question_rules_cover_contradictions_and_instruction_like_text(self):
        body = section("Question rules")
        for words in ("At most 3 questions", "300 characters", "quotes both versions", "citations",
                      "Never resolve one silently", "DR07", "never followed"):
            self.assertIn(words, body)

    def test_every_probe_has_five_parts_and_the_pattern_probes_exist(self):
        probes = re.split(r"^### (P\d\d: .+)$", section("Probes library"), flags=re.M)
        named = dict(zip(probes[1::2], probes[2::2]))
        self.assertGreaterEqual(len(named), 8)
        for name, body in named.items():
            for part in ("**Signal:**", "**Ask:**", "**A complete answer gives:**", "**Lands in:**",
                         "**Worked example (meeting notes):**"):
                self.assertEqual(body.count(part), 1, f"{name}: {part}")
        titles = " ".join(named).lower()
        for pattern in ("identity", "missing attribute", "conflicting sources"):
            self.assertIn(pattern, titles)
        conflict = next(b for n, b in named.items() if "Conflicting" in n)
        self.assertIn("quote both versions with their citations", conflict)
        self.assertRegex(conflict, r"(?s)\[A:A\d+\].*\[S:S\d+")

    def test_complete_criteria_feed_the_readiness_score(self):
        body = section("When the interview is complete")
        self.assertIn("engine/readiness.py", body)
        self.assertIn("playback is confirmed", body)

    def test_playback_is_scqa_within_500_words(self):
        body = section("Playback (SCQA)")
        for part in ("**Situation:**", "**Complication:**", "**Question:**", "**Answer:**"):
            self.assertIn(part, body)
        self.assertIn("500 words", body)
        example = "\n".join(l for l in body.splitlines() if l.startswith(">"))
        self.assertLessEqual(len(example.split()), 500)


if __name__ == "__main__":
    unittest.main()
