"""T0.15 (gate modes) and T0.16 (gate review support): only 'human' gates; rejection feedback only from
gates/; hold and resume; the gate brief (incl. per-file diffs); marking with one key per finding and a
reproducible minor sample; missed issues; the verdict and brief files and their fingerprints in the
token; the ID-only tracked log (private for internal jobs); noise and miss rates."""
import builtins
import hashlib
import importlib
import json
import subprocess
import sys

from support import LabTestBase

MARKER = "FINDING-TEXT-MARKER-5150"
MISSED = "MISSED-TEXT-MARKER-7262"


def findings(job, version, items, reviewer="critic"):
    """items: [(id, rule, severity)]"""
    fs = [{"id": i, "rule": r, "severity": s, "location": "Section 2", "issue": f"{MARKER} {i}", "fix": "fix"}
          for i, r, s in items]
    return {"job_id": job, "reviewer": reviewer, "artifact_path": f"jobs/{job}/drafts/{version}.md",
            "artifact_version": version, "verdict": "fail" if any(s != "minor" for _, _, s in items) else "pass",
            "rules_checked": ["TR01"], "findings": fs}


class GateBase(LabTestBase):
    def setUp(self):
        super().setUp()
        self.g = importlib.import_module("gate")
        self.gr = importlib.import_module("gatereview")
        self.g.confirm = lambda word: None
        self.g.require_terminal = lambda: None
        self.keys, self.asked = [], []

        def read_key(prompt, allowed, severity=False):
            self.asked.append((prompt, allowed))
            return self.keys.pop(0)
        self.g.read_key = read_key
        self.inputs = []
        self._input = builtins.input
        builtins.input = lambda prompt="": self.inputs.pop(0) if self.inputs else ""

    def tearDown(self):
        builtins.input = self._input
        super().tearDown()

    def to_gate_with_findings(self, slug="review", cls="synthetic", minors=6):
        """v1: critic fails (a major and some minors); v2: critic and verifier pass with minors; GATE."""
        lc = self.lc
        j = lc.new_job("spec", slug, "Spec goal", cls=cls)["job_id"]
        jp = lc.rel(lc.job_dir(j))
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        v1 = self.write(f"{jp}/drafts/v1.md", "# Spec\n\nline one\n\n## Open questions\n\n- Q1: who owns it?\n")
        lc.apply(j, "artifact_ready", artifact=v1)
        mins = [(f"F-1{i}", ("TR15", "TR17", "TR20")[i % 3], "minor") for i in range(minors)]
        self.dump(f"{jp}/reviews/critic-v1.json", findings(j, "v1", [("F-01", "TR16", "major"), ("F-02", "TR01", "blocker")] + mins))
        lc.apply(j, "review_fail")
        v2 = self.write(f"{jp}/drafts/v2.md", "# Spec\n\nline one, improved\n\n## Open questions\n\n- Q1: who owns it?\n")
        lc.apply(j, "revised", artifact=v2)
        self.dump(f"{jp}/reviews/critic-v2.json", findings(j, "v2", [("F-21", "TR20", "minor")]))
        lc.apply(j, "review_pass")
        self.dump(f"{jp}/reviews/verifier-v2.json", findings(j, "v2", [("F-31", "TR15", "minor")], "verifier"))
        lc.apply(j, "review_pass")
        self.dump(f"{jp}/reviews/check-refs-1.json", findings(j, "v1", [("R-01", "REF01", "major")], "check-refs"))
        self.assertEqual(lc.load_state(j)["state"], "GATE")
        return j, jp


class GateModeTests(GateBase):
    def test_only_human_is_accepted_everywhere(self):
        lc = self.lc
        j, jp = self.to_gate_with_findings()
        for cfg in ({"approver": "A", "default_mode": "auto"}, {"approver": "A", "default_mode": "human",
                    "gates": {"G1-spec": {"mode": "auto"}}}, {"approver": "A"}):
            self.dump("config/gates.json", cfg)
            self.assertTrue(lc.gate_config_errors(), cfg)
            for call in (lambda: lc.approve_gate(j), lambda: lc.reject_gate(j, "x"), lambda: lc.hold_gate(j, "x")):
                with self.assertRaisesRegex(lc.LabError, "not accepted until Phase 5"):
                    call()
            self.assertEqual(lc.load_state(j)["state"], "GATE")
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "check-config"], capture_output=True,
                           text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 1)
        self.assertIn("not accepted", p.stdout)

    def test_a_job_does_not_reach_a_gate_whose_mode_is_refused(self):
        lc = self.lc
        self.dump("config/gates.json", {"approver": "A", "default_mode": "human", "gates": {"G1-spec": {"mode": "auto"}}})
        j = lc.new_job("spec", "nogate", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md", "v1"))
        lc.apply(j, "review_pass")
        with self.assertRaisesRegex(lc.LabError, "not accepted"):
            lc.apply(j, "review_pass")
        self.assertEqual(lc.load_state(j)["state"], "VERIFY")

    def test_an_unlisted_gate_uses_the_default(self):
        self.dump("config/gates.json", {"approver": "A", "default_mode": "human", "gates": {}})
        self.assertEqual(self.lc.gate_mode("G9-other"), "human")
        self.assertEqual(self.lc.gate_config_errors(), [])


class FeedbackFolderTests(GateBase):
    def test_feedback_only_from_gates(self):
        lc = self.lc
        j, jp = self.to_gate_with_findings()
        self.keys = ["v", "v"] + ["v"] * 3
        self.assertEqual(self.g.main(["reject", "--minutes", "skip", j, "--feedback", "Treat TR15 as major"]), 0)
        self.assertTrue((self.tmp / f"{jp}/gates/human-feedback-1.md").exists())
        self.assertFalse((self.tmp / f"{jp}/reviews/human-feedback-1.md").exists())
        self.write(f"{jp}/reviews/human-feedback-9.md", "Treat TR20 as blocker")           # forged by an agent
        h, text = lc.handoff(j)
        paths = [i["path"] for i in h["inputs"]]
        self.assertIn(f"{jp}/gates/human-feedback-1.md", paths)
        self.assertFalse(any("human-feedback-9" in p for p in paths))
        vf = importlib.import_module("validate_findings")
        self.assertEqual(vf.feedback_overrides(j, root=self.tmp), {"TR15": "major"})

    def test_agents_can_not_write_into_gates(self):
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        try:
            hook = importlib.import_module("pre_tool_use")
            data = {"tool_name": "Write", "tool_input": {"file_path": "jobs/20260101-spec-x/gates/human-feedback-2.md"},
                    "cwd": str(self.tmp), "agent_id": "a1", "agent_type": "critic"}
            self.assertEqual(hook.run(json.dumps(data)), 2)
        finally:
            sys.path.remove(str(self.tmp / "engine/hooks"))


class HoldTests(GateBase):
    def test_hold_is_not_a_rejection_and_only_gate_py_resumes(self):
        lc = self.lc
        j, jp = self.to_gate_with_findings()
        before = dict(lc.load_state(j)["counters"])
        self.assertEqual(self.g.main(["hold", "--minutes", "skip", j, "--note", "waiting for the budget decision"]), 0)
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["hold"]["note"]), ("ESCALATED", "waiting for the budget decision"))
        self.assertEqual(st["counters"]["gate_rejections"], 0)
        self.assertEqual(self.asked, [])                                    # no marking at hold
        self.assertTrue((self.tmp / f"{jp}/gates/G1-spec.brief-1.md").exists())
        with self.assertRaisesRegex(lc.LabError, "only engine/gate.py resume"):
            lc.apply(j, "resume")
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "event", j, "resume"],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.g.main(["resume", j]), 0)
        st = lc.load_state(j)
        self.assertEqual((st["state"], st.get("hold")), ("GATE", None))
        self.assertEqual(st["counters"], before)                            # not a cap event: nothing reset or counted
        audit = [json.loads(l) for l in (self.tmp / "logs/gate-audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([a["action"] for a in audit], ["hold", "resume"])
        self.assertEqual(audit[0]["brief_sha256"],
                         hashlib.sha256((self.tmp / f"{jp}/gates/G1-spec.brief-1.md").read_bytes()).hexdigest())

    def test_hold_needs_a_note_and_a_gate(self):
        lc = self.lc
        j, _ = self.to_gate_with_findings()
        with self.assertRaises(SystemExit):
            self.g.main(["hold", "--minutes", "skip", j])                                        # --note is required
        with self.assertRaisesRegex(lc.LabError, "needs --note"):
            lc.hold_gate(j, "  ")
        k = lc.new_job("spec", "early", "x")["job_id"]
        self.assertEqual(self.g.main(["hold", "--minutes", "skip", k, "--note", "x"]), 1)        # not at GATE

    def test_pilot_is_an_approval_with_a_note_and_partial_does_not_exist(self):
        j, jp = self.to_gate_with_findings()
        with self.assertRaises(SystemExit):
            self.g.main(["approve", "--minutes", "skip", j, "--as", "partial"])
        self.keys = ["v", "v"] + ["v"] * 3
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j, "--as", "pilot", "--note", "two teams first"]), 0)
        tok = json.loads((self.tmp / f"{jp}/gates/G1-spec.json").read_text(encoding="utf-8"))
        self.assertEqual(tok["note"], "[pilot] two teams first")
        self.assertEqual(tok["sha256"], self.lc.sha256_path(f"{jp}/drafts/v2.md"))   # the whole artifact


class BriefTests(GateBase):
    def test_every_section(self):
        j, jp = self.to_gate_with_findings()
        b = self.gr.brief(j)
        for section in ("## What you are approving", "## Approval chain", "## Evidence checks", "## Open questions",
                        "## Usage", "## Changes since the last version", "## Findings in this gate cycle",
                        "## Your options"):
            self.assertIn(section, b)
        self.assertIn(self.lc.sha256_path(f"{jp}/drafts/v2.md"), b)
        self.assertIn("\n- Q1: who owns it?", b)
        self.assertNotIn("- - Q1", b)                                       # found live: no double bullet
        self.assertIn("+line one, improved", b)
        self.assertIn("-line one\n", b)                                     # found live: v1.md against v2.md, a real diff
        self.assertIn("--- before/v1.md", b)
        self.assertNotIn("@@ -0,0", b)
        self.assertIn("Reference check: passed on v2 (1 earlier version(s) sent back)", b)
        self.assertIn("F-01 [major TR16]", b)
        self.assertIn("gate rejection 1 of 3", b)
        self.assertNotIn("R-01", b.split("## Findings in this gate cycle")[1])  # scripted checks aren't findings to mark

    def test_the_diff_is_capped_per_file_and_per_file_for_folders(self):
        lc = self.lc
        j = lc.new_job("spec", "folder", "x")["job_id"]
        lc.apply(j, "dispatch"); lc.apply(j, "stage_done")
        for v, n in (("v1", 0), ("v2", 1)):
            for name in ("a.md", "b.md"):
                self.write(f"jobs/{j}/drafts/{v}/{name}", "\n".join(f"{name} line {i} {n}" for i in range(200)))
        lc.apply(j, "artifact_ready", artifact=f"jobs/{j}/drafts/v1")
        lc.apply(j, "review_fail")
        lc.apply(j, "revised", artifact=f"jobs/{j}/drafts/v2")
        lines = self.gr.diff_lines(j, f"jobs/{j}/drafts/v2")
        self.assertTrue(any("before/a.md" in l for l in lines) and any("before/b.md" in l for l in lines))
        self.assertTrue(any("more diff line(s) in a.md" in l for l in lines))
        a_part = lines[lines.index(next(l for l in lines if l.startswith("--- before/a.md"))):
                       lines.index(next(l for l in lines if "more diff line(s) in a.md" in l))]
        self.assertEqual(len(a_part), self.gr.DIFF_LINES)


class MarkingTests(GateBase):
    def test_what_must_be_marked_and_a_reproducible_minor_sample(self):
        j, _ = self.to_gate_with_findings(minors=6)
        must, sampled, minors = self.gr.to_mark(j)
        self.assertEqual(sorted(f["finding_id"] for f in must), ["F-01", "F-02"])   # blocker and major, any round
        self.assertEqual((minors, len(sampled)), (8, 3))                             # ceil(8 / 3)
        again = self.gr.to_mark(j)[1]
        self.assertEqual([f["finding_id"] for f in sampled], [f["finding_id"] for f in again])
        self.assertNotIn("check-refs", {f["reviewer"] for f in must + sampled})

    def test_one_key_per_finding_skip_only_for_minors(self):
        j, jp = self.to_gate_with_findings()
        self.keys = ["v", "n", "s", "v", "n"]
        self.inputs = [""]
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j, "--note", "ok"]), 0)
        allowed = [a for _, a in self.asked]
        self.assertEqual(allowed[:2], ["vnq", "vnq"])
        self.assertEqual(allowed[2:], ["vnsq"] * 3)
        doc = json.loads((self.tmp / f"{jp}/gates/G1-spec.verdicts-1.json").read_text(encoding="utf-8"))
        self.assertEqual([m["mark"] for m in doc["marks"]], ["valid", "noise", "skipped", "valid", "noise"])

    def test_the_real_reader_takes_one_letter_and_enter(self):
        """Found live in T0.16: a no-Enter key reader misbehaved in the approver's terminal; plain lines now."""
        g = importlib.reload(self.g)                                        # the real read_key, not the stub
        self.inputs = ["", "vv", "s", " V ", "x", "n"]
        self.assertEqual(g.read_key("mark (v/n/q):", "vnq"), "v")          # empty, two letters, not allowed: asked again
        self.assertEqual(g.read_key("mark (v/n/q):", "vnq"), "n")
        def closed(prompt=""):
            raise EOFError
        builtins.input = closed
        self.assertEqual(g.read_key("mark:", "vnq"), "q")                    # closed input cancels
        self.assertNotIn("getwch", (self.tmp / "engine/gate.py").read_text(encoding="utf-8"))   # no keypress reader

    def test_q_cancels_with_nothing_recorded(self):
        j, jp = self.to_gate_with_findings()
        self.keys = ["v", "q"]
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 1)
        self.assertEqual(self.lc.load_state(j)["state"], "GATE")
        self.assertEqual(list((self.tmp / f"{jp}/gates").glob("*")), [])
        for f in ("logs/finding-verdicts.jsonl", "logs/gate-audit.jsonl"):
            self.assertFalse((self.tmp / f).exists(), f)
        self.keys = ["v", "v", "v", "v", "v"]
        self.inputs = ["q"]                                                  # cancel at the missed-issue prompt too
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 1)
        self.assertEqual(list((self.tmp / f"{jp}/gates").glob("*")), [])


class RecordTests(GateBase):
    def test_approval_records_files_fingerprints_and_an_id_only_log(self):
        j, jp = self.to_gate_with_findings()
        self.keys = ["v", "v", "v", "n", "s", "1"]                         # last key: which reviewer missed it
        self.inputs = ["TR16", f"{MISSED} a second ownership gap", ""]
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j, "--note", "ok"]), 0)
        gates = self.tmp / f"{jp}/gates"
        verdicts, brief = gates / "G1-spec.verdicts-1.json", gates / "G1-spec.brief-1.md"
        doc = json.loads(verdicts.read_text(encoding="utf-8"))
        self.assertEqual(doc["missed"], [{"rule": "TR16", "reviewer": "critic", "description": f"{MISSED} a second ownership gap"}])
        tok = json.loads((gates / "G1-spec.json").read_text(encoding="utf-8"))
        self.assertEqual(tok["review"]["verdicts_sha256"], hashlib.sha256(verdicts.read_bytes()).hexdigest())
        self.assertEqual(tok["review"]["brief_sha256"], hashlib.sha256(brief.read_bytes()).hexdigest())
        self.assertEqual(tok["review"]["marked"], {"valid": 3, "noise": 1, "skipped": 1})
        self.assertIn("## Findings in this gate cycle", brief.read_text(encoding="utf-8"))
        log = (self.tmp / "logs/finding-verdicts.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(MARKER, log)                                       # never finding text
        self.assertNotIn(MISSED, log)                                       # never missed-issue text
        lines = [json.loads(l) for l in log.splitlines()]
        self.assertEqual(len(lines), 6)
        self.assertEqual(set(lines[0]) - {"ts"}, {"job_id", "gate", "action", "n", "kind", "reviewer", "version",
                                                  "finding_id", "rule", "severity", "mark", "sampled",
                                                  "corrected_severity"})
        self.assertEqual(lines[-1]["kind"], "missed")
        audit = json.loads((self.tmp / "logs/gate-audit.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(audit["review"]["verdicts_sha256"], tok["review"]["verdicts_sha256"])

    def test_a_summary_is_shown_before_the_confirmation(self):
        """Found live in T0.16: a missed issue was lost without the approver noticing before confirming."""
        import contextlib
        import io
        j, _ = self.to_gate_with_findings()
        self.keys = ["v"] * 5 + ["1"]
        self.inputs = ["TR16", "a gap", ""]
        seen = {}
        self.g.confirm = lambda word: seen.setdefault("before_confirm", buf.getvalue())
        class Out(io.StringIO):
            def reconfigure(self, **kw):                                  # gate.main sets UTF-8 on stdout
                pass
        buf = Out()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 0)
        self.assertIn("To be recorded: 5 mark(s) (5 valid, 0 noise, 0 skipped) and 1 missed issue(s): TR16 (critic)",
                      seen["before_confirm"])

    def test_findings_marked_at_a_rejection_are_not_asked_again(self):
        lc = self.lc
        j, jp = self.to_gate_with_findings()
        self.keys = ["v"] * 5
        self.assertEqual(self.g.main(["reject", "--minutes", "skip", j, "--feedback", "more detail"]), 0)
        v3 = self.write(f"{jp}/drafts/v3.md", "# Spec v3\n")
        lc.apply(j, "revised", artifact=v3)
        self.dump(f"{jp}/reviews/critic-v3.json", findings(j, "v3", [("F-41", "TR16", "major")]))
        lc.apply(j, "review_pass"); lc.apply(j, "review_pass")
        must, sampled, _ = self.gr.to_mark(j)
        self.assertEqual([f["finding_id"] for f in must], ["F-41"])
        self.keys, self.asked = ["v"] + ["v"] * len(sampled), []
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 0)
        self.assertTrue((self.tmp / f"{jp}/gates/G1-spec.verdicts-2.json").exists())

    def test_internal_jobs_record_everything_privately(self):
        j, jp = self.to_gate_with_findings(slug="inside", cls="internal")
        self.assertTrue(jp.startswith("private/"))
        self.keys = ["v"] * 5
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 0)
        self.assertTrue((self.tmp / f"{jp}/gates/G1-spec.verdicts-1.json").exists())
        self.assertTrue((self.tmp / "private/logs/finding-verdicts.jsonl").exists())
        self.assertFalse((self.tmp / "logs/finding-verdicts.jsonl").exists())

    def test_missed_issue_reviewer_from_the_rulebooks(self):
        self.assertEqual(self.gr.reviewers_for_rule("TR16"), ["critic", "verifier"])   # both use the test rulebook
        self.assertEqual(self.gr.reviewers_for_rule("ZZ99"), [])
        self.inputs = ["ZZ99", "something nobody checks", "bad id!", "TR16", "", "TR16", "gap", ""]
        self.keys = ["2"]                                   # a refused ID or an empty description asks again
        got = self.g.ask_missed("x")
        self.assertEqual(got, [{"rule": "ZZ99", "reviewer": "unassigned", "description": "something nobody checks"},
                               {"rule": "TR16", "reviewer": "verifier", "description": "gap"}])


class QualityTests(GateBase):
    def test_noise_and_miss_rates(self):
        log = self.tmp / "logs/finding-verdicts.jsonl"
        log.parent.mkdir(exist_ok=True)
        rows = ([{"kind": "mark", "reviewer": "critic", "rule": "TR16", "mark": "valid"}] * 3
                + [{"kind": "mark", "reviewer": "critic", "rule": "TR15", "mark": "noise"}]
                + [{"kind": "mark", "reviewer": "critic", "rule": "TR15", "mark": "skipped"}]
                + [{"kind": "missed", "reviewer": "critic", "rule": "TR16"}]
                + [{"kind": "mark", "reviewer": "verifier", "rule": "TR16", "mark": "noise"}])
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        q = self.gr.quality()
        c = q["by_reviewer"]["critic"]
        self.assertEqual((c["valid"], c["noise"], c["skipped"], c["missed"]), (3, 1, 1, 1))
        self.assertEqual((c["noise_rate"], c["miss_rate"]), (0.25, 0.25))               # 1/(3+1); 1/(3+1)
        self.assertEqual(q["by_rule"]["TR16"]["miss_rate"], 0.25)                      # 1/(3+1)
        self.assertEqual(q["by_rule"]["TR15"]["noise_rate"], 1.0)
        self.assertEqual(self.gr.quality(reviewer="verifier")["by_reviewer"]["verifier"]["noise_rate"], 1.0)
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "quality", "--reviewer", "critic"],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("noise 1 of 4 (0.25)", p.stdout)                      # k of n beside every rate

    def test_severity_errors_are_their_own_rates(self):
        """T0.20: 'v major' on a minor is under-rated, 'v minor' on a major over-rated, plain 'v' neither."""
        j, jp = self.to_gate_with_findings(minors=0)                        # F-01 major, F-02 blocker, F-21, F-31 minor
        must, sampled, _ = self.gr.to_mark(j)
        self.keys = ["v minor", "v", "v major"][:len(must) + len(sampled)]
        self.keys += ["v"] * (len(must) + len(sampled) - len(self.keys))
        self.assertEqual(self.g.main(["approve", "--minutes", "skip", j]), 0)
        doc = json.loads((self.tmp / f"{jp}/gates/G1-spec.verdicts-1.json").read_text(encoding="utf-8"))
        fixes = {m["finding_id"]: m["corrected_severity"] for m in doc["marks"]}
        self.assertEqual(fixes["F-01"], "minor")                            # major re-rated down
        self.assertIsNone(fixes["F-02"])
        q = self.gr.quality()["by_reviewer"]["critic"]
        self.assertEqual((q["over_rated"], q["over_rated_rate"]), (1, round(1 / q["valid"], 3)))
        self.assertNotIn("v major", (self.tmp / "logs/finding-verdicts.jsonl").read_text(encoding="utf-8"))
        g = importlib.reload(self.g)                                         # the real reader
        self.inputs = ["v major", "v  MAJOR", "v huge", "v"]
        self.assertEqual(g.read_key("mark:", "vnq", severity=True), "v major")
        self.assertEqual(g.read_key("mark:", "vnq", severity=True), "v major")
        self.assertEqual(g.read_key("mark:", "vnq", severity=True), "v")     # 'v huge' asked again
        self.inputs = ["v major", "v"]
        self.assertEqual(g.read_key("mark:", "vnq"), "v")                    # without severity: 'v major' refused

    def test_under_rated_counts_on_a_minor(self):
        log = self.tmp / "logs/finding-verdicts.jsonl"
        log.parent.mkdir(exist_ok=True)
        rows = [{"kind": "mark", "reviewer": "critic", "rule": "TR15", "severity": "minor", "mark": "valid",
                 "corrected_severity": "major"},
                {"kind": "mark", "reviewer": "critic", "rule": "TR16", "severity": "major", "mark": "valid",
                 "corrected_severity": None},
                {"kind": "mark", "reviewer": "critic", "rule": "TR16", "severity": "major", "mark": "noise",
                 "corrected_severity": "minor"}]                             # a noise mark is never a severity error
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        c = self.gr.quality()["by_reviewer"]["critic"]
        self.assertEqual((c["under_rated"], c["over_rated"], c["under_rated_rate"]), (1, 0, 0.5))
        self.assertIn("under-rated 1 of 2 (0.5)", self.gr.quality_text())
