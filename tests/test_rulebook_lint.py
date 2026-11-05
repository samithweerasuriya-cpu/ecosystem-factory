"""Rulebook lint (T2.5, critic rounds 2 and 3): a reviewer never sees the config files, so a rulebook that names one
(config/...) must write the values it relies on into the rulebook itself. Every rulebook in config/reviewers.json is
linted. A config file the lint doesn't know fails closed: add it to CHECKS (or, if no rule checks any of its values,
to NAMES_ONLY with the reason). Factory-only (tests/)."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
from support import REPO  # noqa: E402
sys.path.insert(0, str(REPO / "engine"))
from designcheck import CAP_KEYS  # noqa: E402  (the caps a charter sets, as the design check compares them)

CONFIG_REF = re.compile(r"config/[\w./-]+\.json")
# a definition line names its source as (`config/x.json`) or (`config/x.json`, field `name`)
SOURCE = re.compile(r"\(`(config/[\w./-]+\.json)`(?:, field `([\w.]+)`)?\)")
TICKED = re.compile(r"`([^`]+)`")
PAIR = re.compile(r"`([\w.]+)` (\d[\d,]*)")


def ticked(block, ref, field):
    """The backticked values in writing order (the file name and field name left out)."""
    return [v for v in TICKED.findall(block) if v not in (ref, field)]


def pairs(block, ref, field):
    return {k: int(v.replace(",", "")) for k, v in PAIR.findall(block)}


def factory_caps(cfg):
    caps = {k: cfg[k] for k in CAP_KEYS}
    caps.update({f"usage_ceiling.{k}": cfg["usage_ceiling"][k] for k in ("tokens", "agent_minutes")})
    return caps


# config file -> {field named on the definition line (None: the file alone): (how to read the line, what the file holds)}
CHECKS = {
    "config/data-classes.json": {"allowed": (ticked, lambda cfg: cfg["allowed"]),
                                 "order": (ticked, lambda cfg: cfg["order"])},
    "config/caps.json": {None: (pairs, factory_caps)},
}
# config files a rulebook may name without values: no rule checks any value in them
NAMES_ONLY = {"config/gates.json": "names where the approver's name is set; no rule checks the name"}


def lint(text, read_config):
    """Problems with one rulebook's config references (empty: clean). For each config file in CHECKS, every check
    needs a definition line ("- ...") naming the file (and field) that writes out exactly what the file holds now,
    in the file's order."""
    problems, all_lines = [], text.splitlines()
    for ref in sorted(set(CONFIG_REF.findall(text))):
        if ref in NAMES_ONLY:
            continue
        if ref not in CHECKS:
            problems.append(f"{ref}: unknown to the lint; write its values into the rulebook and add it to CHECKS")
            continue
        cfg, seen = read_config(ref), set()
        for i, l in enumerate(all_lines):
            if not (l.lstrip().startswith("- ") and ref in l):
                continue
            block = [l]
            for x in all_lines[i + 1:]:                              # a definition may wrap onto indented lines
                if not x.startswith("  ") or x.lstrip().startswith("- "):
                    break
                block.append(x)
            block = " ".join(block)
            fields = [f for r, f in SOURCE.findall(block) if r == ref]
            field = (fields[0] or None) if fields else "?"
            if field not in CHECKS[ref]:
                problems.append(f"{ref}: a definition line names no known field ({field})")
                continue
            seen.add(field)
            read, want = CHECKS[ref][field]
            got, want = read(block, ref, field), want(cfg)
            if got != want:
                problems.append(f"{ref} {field or ''}: the rulebook lists {got}, the file holds {want}")
        problems += [f"{ref}: no definition line lists {f or 'its values'}" for f in CHECKS[ref] if f not in seen]
    return problems


def read_repo_config(ref):
    return json.loads((REPO / ref).read_text(encoding="utf-8"))


CLASSES = {"allowed": ["synthetic", "public"], "order": ["synthetic", "public", "internal"]}
CLASS_LINES = ("- Allowed data classes (`config/data-classes.json`, field `allowed`): `synthetic`, `public`.\n"
               "- Class order (`config/data-classes.json`, field `order`), lowest first: `synthetic`, `public`, "
               "`internal`.\n")


class RulebookLintTests(unittest.TestCase):
    def test_every_reviewer_rulebook_writes_out_the_config_values_it_relies_on(self):
        for rb in rulebooks():
            self.assertEqual(lint((REPO / rb).read_text(encoding="utf-8"), read_repo_config), [], rb)

    def test_both_charter_rulebooks_are_linted(self):
        self.assertTrue({"rules/charter-checklist.md", "rules/charter-verifier.md"} <= set(rulebooks()))

    def test_the_critic_rulebook_states_the_classes_their_order_and_the_caps(self):
        text = (REPO / "rules/charter-checklist.md").read_text(encoding="utf-8")
        for ref in ("config/data-classes.json", "config/caps.json"):
            self.assertIn(ref, text)
        self.assertIn("field `order`", text)
        self.assertEqual(lint(text, read_repo_config), [])

    def test_a_disagreement_either_way_fails(self):
        self.assertEqual(lint(CLASS_LINES, lambda ref: CLASSES), [])
        self.assertTrue(lint(CLASS_LINES, lambda ref: {**CLASSES, "allowed": ["synthetic"]}))           # narrowed
        self.assertTrue(lint(CLASS_LINES, lambda ref: {**CLASSES, "allowed": ["synthetic", "public", "internal"]}))

    def test_the_class_order_must_match_in_order(self):
        self.assertTrue(lint(CLASS_LINES, lambda ref: {**CLASSES, "order": ["public", "synthetic", "internal"]}))
        self.assertTrue(lint(CLASS_LINES.splitlines()[0] + "\n", lambda ref: CLASSES))                 # order missing

    def test_the_caps_must_match_the_file(self):
        cfg = {k: 3 for k in CAP_KEYS} | {"usage_ceiling": {"tokens": 350000, "agent_minutes": 20}}
        line = ("- Factory caps (`config/caps.json`): " + ", ".join(f"`{k}` 3" for k in CAP_KEYS)
                + ", `usage_ceiling.tokens` 350,000, `usage_ceiling.agent_minutes` 20.\n")
        self.assertEqual(lint(line, lambda ref: cfg), [])
        self.assertTrue(lint(line, lambda ref: cfg | {CAP_KEYS[0]: 4}))
        self.assertTrue(lint(line, lambda ref: cfg | {"usage_ceiling": {"tokens": 300000, "agent_minutes": 20}}))

    def test_a_named_config_without_values_fails(self):
        self.assertTrue(lint("| CH07 | allowed by `config/data-classes.json` | blocker |\n", lambda ref: CLASSES))

    def test_a_definition_line_with_an_unknown_field_fails(self):
        self.assertTrue(lint(CLASS_LINES + "- Other (`config/data-classes.json`, field `extra`): `x`.\n",
                             lambda ref: CLASSES))

    def test_an_unknown_config_file_fails_closed(self):
        self.assertTrue(lint("- Thresholds (`config/evals.json`): `5`.\n", lambda ref: {}))


def rulebooks():
    doc = json.loads((REPO / "config/reviewers.json").read_text(encoding="utf-8"))
    return sorted({r["rulebook"] for r in doc["reviewers"].values()})


if __name__ == "__main__":
    unittest.main()
