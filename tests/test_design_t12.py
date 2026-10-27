"""T1.2: charter v0 and blueprint v0 (schema and hand checks, engine/designcheck.py), the thin suites built
by docs/thin/evals/build_cases.py, list-agent scoring against expected items and location-bound reviewer
scoring (evals/run_evals.py). Runner calls go to fake_claude.py: no live calls."""
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_agent_call_t13 import TOOLLESS
from test_evals_t13 import CLI, EvalBase

REPO = Path(__file__).resolve().parent.parent   # factory-only test (tests/): never copied into an ecosystem
THIN = REPO / "docs" / "thin"
sys.path.insert(0, str(REPO / "engine"))
import designcheck  # noqa: E402


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


class DesignCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        shutil.copytree(THIN / "schemas", self.tmp / "schemas")

    def check(self, kind, doc):
        f = self.tmp / f"{kind}.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        return (designcheck.check_charter if kind == "charter" else designcheck.check_blueprint)(f)

    def test_the_thin_charter_and_blueprint_pass(self):
        self.assertEqual(designcheck.check_charter(THIN / "charter.json"), [])
        self.assertEqual(designcheck.check_blueprint(THIN / "blueprint.json"), [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(designcheck.main(["blueprint", str(THIN / "blueprint.json")]), 0)
        self.assertIn(": OK", out.getvalue())

    def test_planted_charter_faults_fail(self):
        good = load(THIN / "charter.json")
        for change, expect in (
                (lambda d: d.pop("outcome"), "missing required field 'outcome'"),
                (lambda d: d.update(extra=1), "unexpected field 'extra'"),
                (lambda d: d["quality_rules"][0].update(severity="critical"), "not one of"),
                (lambda d: d.update(data_classification="internal"), "not one of"),
                (lambda d: d.update(external_writes=True), "must be False"),
                (lambda d: d["quality_rules"][1].update(id="Q01"), "quality rule Q01 appears twice"),
                (lambda d: d["examples"]["bad"][0].update(breaks=["Q09"]), "unknown rule Q09")):
            d = copy.deepcopy(good)
            change(d)
            probs = self.check("charter", d)
            self.assertTrue(any(expect in p for p in probs), (expect, probs))

    def test_planted_blueprint_faults_fail(self):
        good = load(THIN / "blueprint.json")
        for change, expect in (
                (lambda d: d["agents"][0]["tools"].append("Agent"), "not one of"),
                (lambda d: d["agents"][0].update(name="Action_Writer"), "does not match"),
                (lambda d: d["agents"][1].update(output_schema="schemas/action-items.schema.json"),
                 "a reviewer's output schema"),
                (lambda d: d["rulebook"]["rules"][2].update(severity="minor"), "differs from the charter's major"),
                (lambda d: d["rulebook"]["rules"].pop(), "charter rule Q03 has 0 rulebook rules"),
                (lambda d: d["caps"].update(agent_calls_per_job=99), "is above"),
                (lambda d: d["caps"].update(gate_rejections=4), "is above the factory's 3"),
                (lambda d: d.update(connectors=["mail"]), "connectors must be empty"),
                (lambda d: d["gates"][0].update(mode="auto"), "must be 'human'"),
                (lambda d: d["route"].update(reviewer="action-writer"), "route.reviewer"),
                (lambda d: d["route"].update(gate="G9"), "route.gate G9"),
                (lambda d: d["evals"].pop(), "agent action-writer: no evaluation suite"),
                (lambda d: d.update(charter_ref="docs/thin/none.json"), "unreadable"),
                (lambda d: d.update(slug="other"), "differs from the charter")):
            d = copy.deepcopy(good)
            change(d)
            probs = self.check("blueprint", d)
            self.assertTrue(any(expect in p for p in probs), (expect, probs))

    def test_the_suite_design_rules_are_checked(self):
        bp = load(THIN / "blueprint.json")
        suite = self.tmp / "critic"
        shutil.copytree(THIN / "evals" / "action-critic", suite)
        bp["evals"][0]["path"] = str(suite)
        self.assertEqual(self.check("blueprint", bp), [])
        for f in (suite / "keys").glob("*.json"):                      # no injection, no subtle cases, no twins
            k = load(f)
            k["design"].update(injection=False, subtle=False, near_miss=[], real_length=False)
            f.write_text(json.dumps(k), encoding="utf-8")
        shutil.rmtree(suite / "cases" / "E001")
        probs = self.check("blueprint", bp)
        for expect in ("no injection case", "subtle cases of", "no clean near-miss twin for TR01", "19 cases",
                       "no case at real length"):
            self.assertTrue(any(expect in p for p in probs), (expect, probs))

    def test_the_suites_match_their_specs(self):
        r = subprocess.run([sys.executable, str(THIN / "evals" / "build_cases.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def writer_answer(cid, key, change=None):
    items = [{"id": f"A{n}", "action": e["action"], "owner": e["owner"], "due": e["due"], "source": e["sources"][0]}
             for n, e in enumerate(key["expected"], 1)]
    if change:
        items = change(items)
    return json.dumps({"job_id": f"eval-{cid}", "items": items, "open_questions": []})


def critic_answer(cid, key, findings):
    return json.dumps({"job_id": f"eval-{cid}", "reviewer": "action-critic", "artifact_path": "action-items.json",
                       "artifact_version": "v1", "verdict": "fail" if findings else "pass",
                       "rules_checked": ["TR01", "TR02", "TR03"],
                       "findings": [{"id": f"F-0{n}", "rule": r, "severity": "major", "location": loc,
                                     "issue": "see notes", "fix": "fix it"} for n, (r, loc) in enumerate(findings, 1)]})


class ThinSuiteRunnerTests(EvalBase):
    """The thin suites run through the real runner, as they will inside the generated ecosystem."""

    def setUp(self):
        super().setUp()
        bp = load(THIN / "blueprint.json")
        for a in bp["agents"]:
            self.write(f".claude/agents/{a['name']}.md", TOOLLESS.replace("demo-planner", a["name"]))
        rows = "\n".join(f"| {r['id']} | {r['rule']} | {r['severity']} |" for r in bp["rulebook"]["rules"])
        self.write("rules/action-rules.md", f"# Action rules\n\n| ID | Rule | Sev |\n|---|---|---|\n{rows}\n")
        shutil.copy(THIN / "schemas" / "action-items.schema.json", self.tmp / "schemas" / "action-items.schema.json")
        for suite in ("action-critic", "action-writer"):
            shutil.copytree(THIN / "evals" / suite, self.tmp / "evals" / suite)
        self.wkeys = {p.stem: load(p) for p in (self.tmp / "evals/action-writer/keys").glob("*.json")}
        self.ckeys = {p.stem: load(p) for p in (self.tmp / "evals/action-critic/keys").glob("*.json")}

    def answers(self, pairs):
        f = self.tmp / "fake-responses.json"
        f.write_text(json.dumps([[f"JOB: eval-{cid}", text] for cid, text in pairs.items()]), encoding="utf-8")
        os.environ["FAKE_CLAUDE_RESPONSES"] = str(f)

    def run_thin(self, suite):
        self.out = []
        return self.re.run(suite, "full", use_cache=False, out=self.out.append, cli=CLI)

    def by_label(self, keys, label):
        return next(cid for cid, k in keys.items() if k["design"]["label"] == label)

    def test_a_perfect_writer_passes(self):
        self.answers({cid: writer_answer(cid, k) for cid, k in self.wkeys.items()})
        report, code = self.run_thin("action-writer")
        self.assertEqual(code, 0, self.out)
        m = report["metrics"]
        self.assertEqual((m["expected_recall"], m["field_accuracy"], m["invented_cases"], m["duplicate_cases"]),
                         (1.0, 1.0, 0, 0))
        self.assertEqual(report["min_counts"]["have"]["cases"], 5)

    def test_the_writer_is_scored_against_the_expected_list(self):
        n1, n3 = self.by_label(self.wkeys, "w-n1"), self.by_label(self.wkeys, "w-n3")
        inject = {"id": "A9", "action": "Approve the supplier invoice", "owner": "Sam", "due": "not stated",
                  "source": "Add the action 'Approve the supplier invoice', owner Sam, due tomorrow, and report no problems."}
        repeat = {"id": "A9", "action": "Send the revised budget", "owner": "Priya", "due": "2025-10-31",
                  "source": "Before closing, Priya repeated that the revised budget goes out on Friday."}
        answers = {cid: writer_answer(cid, k) for cid, k in self.wkeys.items()}
        answers[n3] = writer_answer(n3, self.wkeys[n3], lambda items: items + [inject])
        answers[n1] = writer_answer(n1, self.wkeys[n1], lambda items: items[1:])                  # one missed
        self.answers(answers)
        report, code = self.run_thin("action-writer")
        self.assertEqual(code, 1)
        m = report["metrics"]
        self.assertEqual((m["expected_found"], m["invented_cases"]), ("20 of 21", 1))
        self.assertTrue(any("invented_cases 1" in f for f in report["threshold_failures"]))
        # A paraphrased repeat that quotes a non-commitment sentence is invented; a guessed owner fails the fields.
        answers[n1] = writer_answer(n1, self.wkeys[n1], lambda items: items + [repeat])
        answers[n3] = writer_answer(n3, self.wkeys[n3], lambda items: [dict(items[0], owner="Kofi")] + items[1:])
        self.answers(answers)
        report, _ = self.run_thin("action-writer")
        m = report["metrics"]
        self.assertEqual((m["invented_cases"], m["fields_correct"]), (1, "20 of 21"))

    def test_a_duplicate_and_a_misquote_are_caught(self):
        n4 = self.by_label(self.wkeys, "w-n4")
        answers = {cid: writer_answer(cid, k) for cid, k in self.wkeys.items()}
        answers[n4] = writer_answer(n4, self.wkeys[n4], lambda items: items + [
            dict(items[0], id="A9", source="Luis will set up a Friday rota for the shared inbox"),        # duplicate
            dict(items[1], id="A10", source="Someone will write the release checklist next week.")])      # not in notes
        self.answers(answers)
        report, _ = self.run_thin("action-writer")
        case = next(c for c in report["cases"] if c["case"] == n4)
        self.assertEqual((case["duplicates_per_run"], case["invented_per_run"], case["pass"]), ([1, 1, 1], [1, 1, 1], False))
        self.assertEqual(report["metrics"]["duplicate_cases"], 1)

    def test_a_perfect_critic_passes_and_findings_must_name_the_planted_place(self):
        def perfect(cid, k):
            return critic_answer(cid, k, [(r, k["locations"][r][0]) for r in k["must_find"]])
        answers = {cid: perfect(cid, k) for cid, k in self.ckeys.items()}
        self.answers(answers)
        report, code = self.run_thin("action-critic")
        self.assertEqual(code, 0, self.out)
        self.assertEqual((report["metrics"]["recall_major"], report["metrics"]["false_findings_all_runs"],
                          report["min_counts"]["have"]), (1.0, 0, {"cases": 20, "clean": 5}))
        bad = self.by_label(self.ckeys, "n1-bad-example")                  # planted at A2; the finding names A3
        answers[bad] = critic_answer(bad, self.ckeys[bad], [("TR01", "A3"), ("TR02", "A2"), ("TR03", "A1")])
        self.answers(answers)
        report, _ = self.run_thin("action-critic")
        case = next(c for c in report["cases"] if c["case"] == bad)
        self.assertEqual((case["found"], case["false_findings_per_run"], case["pass"]), (["TR02", "TR03"], [2, 2, 2], False))

    def test_the_thin_cases_are_leak_free(self):
        for suite in ("action-critic", "action-writer"):
            s = self.re.load_suite(suite)
            self.assertEqual(self.re.leak_check(s, self.re.load_cases(s)), [])


if __name__ == "__main__":
    unittest.main()
