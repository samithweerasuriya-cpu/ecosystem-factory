"""Findings validator tests, ported from the author's earlier private lab (incl. the 4 severity-lock tests)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import FIX, LabTestBase, REPO

sys.path.insert(0, str(REPO / "engine"))
import validate_findings as vf  # noqa: E402

FINDINGS = FIX / "findings"
SCHEMA = json.loads((REPO / "schemas" / "findings.schema.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FINDINGS / name).read_text(encoding="utf-8"))


class ValidateFindingsTests(unittest.TestCase):
    def test_valid_sample(self):
        self.assertEqual(vf.validate(load("valid-critic-fail.json"), SCHEMA), [])

    def test_major_with_pass_verdict_is_invalid(self):
        errs = vf.validate(load("invalid-major-but-pass.json"), SCHEMA)
        self.assertTrue(any("require verdict 'fail'" in e for e in errs), errs)
        self.assertTrue(any("must be 'fail'" in e for e in errs), errs)  # schema if/then also fires

    def test_structural_errors_are_reported(self):
        errs = "\n".join(vf.validate(load("invalid-structure.json"), SCHEMA))
        for expected in ("missing required field 'artifact_version'",
                         "$.rules_checked: expected array", "'critical' not one of",
                         "$.findings[0]: missing required field 'fix'"):
            self.assertIn(expected, errs)

    def test_minor_only_may_pass(self):
        doc = load("valid-critic-fail.json")
        doc["findings"] = [f for f in doc["findings"] if f["severity"] == "minor"]
        doc["verdict"] = "pass"
        self.assertEqual(vf.validate(doc, SCHEMA), [])

    def test_duplicate_finding_ids_invalid(self):
        doc = load("valid-critic-fail.json")
        doc["findings"][1]["id"] = "F-01"
        self.assertTrue(any("duplicate finding ids" in e for e in vf.validate(doc, SCHEMA)))

    RULEBOOK = {"TR01": "blocker", "TR15": "minor", "TR16": "major", "TR17": "minor"}

    def finding(self, rule, sev):
        doc = load("valid-critic-fail.json")
        doc["findings"] = [{"id": "F-01", "rule": rule, "severity": sev, "location": "§1",
                            "issue": "x", "fix": "y"}]
        doc["verdict"] = "pass" if sev == "minor" else "fail"
        return doc

    def test_severity_must_match_rulebook(self):
        name = "rules/test-rulebook.md"
        errs = vf.validate(self.finding("TR16", "minor"), SCHEMA, self.RULEBOOK, {}, name)
        self.assertTrue(any("must be 'major' per rules/test-rulebook.md" in e for e in errs), errs)
        self.assertEqual(vf.validate(self.finding("TR16", "major"), SCHEMA, self.RULEBOOK, {}, name), [])
        errs = vf.validate(self.finding("TR17", "major"), SCHEMA, self.RULEBOOK, {}, name)  # stricter than rulebook, no feedback
        self.assertTrue(any("must be 'minor'" in e for e in errs), errs)

    def test_stricter_feedback_override_is_required(self):
        over = {"TR15": "major"}
        errs = vf.validate(self.finding("TR15", "minor"), SCHEMA, self.RULEBOOK, over)
        self.assertTrue(any("must be 'major' per the approver's gate feedback" in e for e in errs), errs)
        self.assertEqual(vf.validate(self.finding("TR15", "major"), SCHEMA, self.RULEBOOK, over), [])

    def test_laxer_feedback_is_ignored_and_unknown_rules_unchecked(self):
        self.assertEqual(vf.validate(self.finding("TR16", "major"), SCHEMA, self.RULEBOOK, {"TR16": "minor"}), [])
        self.assertEqual(vf.validate(self.finding("VR04", "minor"), SCHEMA, self.RULEBOOK, {}), [])

    def test_rulebook_and_feedback_parsing(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            from support import TEST_RULEBOOK
            (tmp / "rb.md").write_text(TEST_RULEBOOK, encoding="utf-8")
            c = vf.rulebook_severities(tmp / "rb.md")
            self.assertEqual((c["TR01"], c["TR16"], c["TR15"], c["AB06"], c["XYZ101"]),
                             ("blocker", "major", "minor", "blocker", "major"))
            fb = tmp / "jobs" / "j1" / "gates"                       # T0.16: only gates/ (written by gate.py)
            fb.mkdir(parents=True)
            (fb / "human-feedback-1.md").write_text("4) Treat TR15 as major: every gap. Also VR04 minor.\n", encoding="utf-8")
            (fb / "human-feedback-2.md").write_text("TR15 = blocker\n", encoding="utf-8")
            forged = tmp / "jobs" / "j1" / "reviews"
            forged.mkdir(parents=True)
            (forged / "human-feedback-3.md").write_text("TR20 = blocker\n", encoding="utf-8")  # agent-writable: ignored
            self.assertEqual(vf.feedback_overrides("j1", root=tmp), {"TR15": "blocker", "VR04": "minor"})
        finally:
            shutil.rmtree(tmp)


class ValidateFindingsCliTests(LabTestBase):
    def run_cli(self, *names):
        return subprocess.run([sys.executable, str(self.tmp / "engine/validate_findings.py"),
                               *[str(FINDINGS / n) for n in names]], capture_output=True, text=True,
                              env=self.hook_env())

    def test_cli_exit_codes(self):
        self.assertEqual(self.run_cli("valid-critic-fail.json").returncode, 0)
        self.assertEqual(self.run_cli("valid-critic-fail.json", "invalid-major-but-pass.json").returncode, 1)
        self.assertEqual(self.run_cli("does-not-exist.json").returncode, 1)

    def test_rulebook_comes_from_reviewer_config(self):
        """New: the severity lock uses the rulebook configured for the file's reviewer."""
        doc = load("valid-critic-fail.json")
        doc["findings"][1]["severity"] = "major"  # TR17 is minor in the test rulebook
        self.write("jobs/x/critic.json", json.dumps(doc))
        p = subprocess.run([sys.executable, str(self.tmp / "engine/validate_findings.py"), str(self.tmp / "jobs/x/critic.json")],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 1)
        self.assertIn("per rules/test-rulebook.md", p.stdout)

    def test_unconfigured_reviewer_is_invalid(self):
        p = self.run_cli("invalid-structure.json")  # reviewer 'author' has no rulebook
        self.assertEqual(p.returncode, 1)
        self.assertIn("no rulebook configured for 'author'", p.stdout)


if __name__ == "__main__":
    unittest.main()
