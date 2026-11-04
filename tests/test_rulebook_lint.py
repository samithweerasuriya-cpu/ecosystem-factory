"""Rulebook lint (T2.5, critic round 2): a reviewer never sees the config files, so a rulebook that names one
(config/...) must write the values it relies on into the rulebook itself. Every rulebook in config/reviewers.json is
linted. A config file the lint doesn't know fails closed: add it to VALUES (or, if no rule checks any of its values,
to NAMES_ONLY with the reason). Factory-only (tests/)."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
from support import REPO  # noqa: E402

CONFIG_REF = re.compile(r"config/[\w./-]+\.json")
TICKED = re.compile(r"`([^`]+)`")
# config file -> the values a rulebook relies on, read from the file itself
VALUES = {"config/data-classes.json": lambda cfg: set(cfg["allowed"])}
# config files a rulebook may name without values: no rule checks any value in them
NAMES_ONLY = {"config/gates.json": "names where the approver's name is set; no rule checks the name"}


def rulebooks():
    doc = json.loads((REPO / "config/reviewers.json").read_text(encoding="utf-8"))
    return sorted({r["rulebook"] for r in doc["reviewers"].values()})


def lint(text, read_config):
    """Problems with one rulebook's config references (empty: clean). For each config file in VALUES, some
    definition line ("- ...") must name the file and list, in backticks, exactly the values the file holds now."""
    problems = []
    for ref in sorted(set(CONFIG_REF.findall(text))):
        if ref in NAMES_ONLY:
            continue
        if ref not in VALUES:
            problems.append(f"{ref}: unknown to the lint; write its values into the rulebook and add it to VALUES")
            continue
        want = VALUES[ref](read_config(ref))
        lines = [l for l in text.splitlines() if l.lstrip().startswith("- ") and ref in l]
        if not lines:
            problems.append(f"{ref}: no definition line lists its values")
            continue
        for l in lines:
            i = text.splitlines().index(l)                     # a definition may wrap onto indented lines
            block = [l] + [x for x in text.splitlines()[i + 1:i + 4] if x.startswith("  ") and not x.lstrip().startswith("- ")]
            got = {v for v in TICKED.findall(" ".join(block)) if v != ref}
            if got != want:
                problems.append(f"{ref}: the rulebook lists {sorted(got)}, the file holds {sorted(want)}")
    return problems


def read_repo_config(ref):
    return json.loads((REPO / ref).read_text(encoding="utf-8"))


class RulebookLintTests(unittest.TestCase):
    def test_every_reviewer_rulebook_writes_out_the_config_values_it_relies_on(self):
        for rb in rulebooks():
            self.assertEqual(lint((REPO / rb).read_text(encoding="utf-8"), read_repo_config), [], rb)

    def test_both_charter_rulebooks_are_linted(self):
        self.assertTrue({"rules/charter-checklist.md", "rules/charter-verifier.md"} <= set(rulebooks()))

    def test_the_critic_rulebook_states_the_allowed_classes(self):
        text = (REPO / "rules/charter-checklist.md").read_text(encoding="utf-8")
        self.assertIn("config/data-classes.json", text)
        self.assertEqual(lint(text, read_repo_config), [])

    def test_a_disagreement_either_way_fails(self):
        text = "- Allowed data classes (`config/data-classes.json`): `synthetic`, `public`.\n"
        self.assertEqual(lint(text, lambda ref: {"allowed": ["synthetic", "public"]}), [])
        self.assertTrue(lint(text, lambda ref: {"allowed": ["synthetic"]}))                  # config narrowed
        self.assertTrue(lint(text, lambda ref: {"allowed": ["synthetic", "public", "internal"]}))  # config widened

    def test_a_named_config_without_values_fails(self):
        self.assertTrue(lint("| CH07 | allowed by `config/data-classes.json` | blocker |\n",
                             lambda ref: {"allowed": ["synthetic"]}))

    def test_an_unknown_config_file_fails_closed(self):
        self.assertTrue(lint("- Caps come from `config/caps.json`: `5`.\n", lambda ref: {}))


if __name__ == "__main__":
    unittest.main()
