"""Job-level classification: set at creation; inputs may not exceed it; internal jobs live
entirely under private/jobs/ and write nothing Git could track (and the leak check proves it)."""
import importlib
import json
import shutil
import subprocess
import sys
import unittest

from support import REPO, LabTestBase


class JobClassTests(LabTestBase):
    def answer(self, j, cls, text=b"answer\n"):
        return self.lc.record_input(j, "-", cls, data=text)

    def test_helpers_refuse_short_test_slugs(self):
        with self.assertRaises(AssertionError) as cm:
            self.lc.new_job("spec", "ab", "x")
        self.assertIn("too short", str(cm.exception))

    def test_cli_new_requires_a_class(self):
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "new", "spec", "noclass", "x"],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 2)
        self.assertIn("--class", p.stderr)

    def test_inputs_cannot_exceed_the_job_class(self):
        lc = self.lc
        syn = lc.new_job("spec", "syn", "x", cls="synthetic")["job_id"]
        pub = lc.new_job("spec", "pub", "x", cls="public")["job_id"]
        intl = lc.new_job("spec", "intl", "x", cls="internal")["job_id"]
        self.answer(syn, "synthetic")
        for job, cls in ((syn, "public"), (syn, "internal"), (pub, "internal")):
            with self.assertRaises(lc.LabError) as cm:
                self.answer(job, cls)
            if cls == "internal":
                self.assertIn("--continue-from", str(cm.exception))
        self.answer(pub, "public"); self.answer(pub, "synthetic")
        for cls in ("synthetic", "public", "internal"):
            self.answer(intl, cls)
        self.assertEqual(len(lc.load_state(intl)["inputs"]), 3)

    def test_a_stray_public_folder_never_redirects_an_internal_job(self):
        """Found by the leak test: lookup used to take any jobs/<id>/ folder first."""
        lc = self.lc
        j = lc.new_job("spec", "stray", "x", cls="internal")["job_id"]
        self.write(f"jobs/{j}/notes.md", "stray")
        self.assertEqual(lc.job_dir(j), self.tmp / "private/jobs" / j)
        lc.apply(j, "dispatch")                                                           # writes go to private
        self.assertFalse((self.tmp / "jobs" / j / "state.json").exists())
        self.write(f"jobs/{j}/state.json", "{}")                                          # state in both homes
        with self.assertRaises(lc.LabError):
            lc.load_state(j)

    def test_a_child_job_cannot_drop_below_its_parent_class(self):
        lc = self.lc
        parent = lc.new_job("spec", "parent", "x", cls="internal")["job_id"]
        lc.apply(parent, "dispatch"); lc.apply(parent, "stage_done")
        lc.apply(parent, "artifact_ready", artifact=self.write(f"private/jobs/{parent}/drafts/v1.md", "v1"))
        lc.apply(parent, "review_pass"); lc.apply(parent, "review_pass"); lc.approve_gate(parent)
        with self.assertRaises(lc.LabError):
            lc.new_job("tickets", "child", "x", parent=parent, cls="public")
        self.assertEqual(lc.new_job("tickets", "child", "x", parent=parent, cls="internal")["state"], "PLANNED")


@unittest.skipUnless(shutil.which("git"), "git not available")
class InternalJobTests(LabTestBase):
    """An internal job writes nothing under tracked paths, and the leak check catches it if it does."""

    def setUp(self):
        super().setUp()
        shutil.copy2(REPO / ".gitignore", self.tmp / ".gitignore")       # the factory's real ignore rules
        self.git("init", "-q")

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.tmp), *a], capture_output=True, text=True)

    def full_internal_run(self):
        """Every path an internal job can take: inputs, handoffs, calls, questions, a reference-check
        failure, reviews, a gate rejection and an approval through gate.py (audited)."""
        lc = self.lc
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        g.require_terminal = lambda: None   # T0.16 prompts: tested in test_gatereview_t16
        g.ask_missed = lambda job: []
        j = lc.new_job("spec", "inside", "Internal goal", cls="internal")["job_id"]
        home = f"private/jobs/{j}"
        lc.record_input(j, "-", "internal", data=b"internal answer INTERNAL-MARKER\n")
        lc.apply(j, "dispatch")
        lc.handoff(j); lc.record_call(j, "researcher")
        lc.apply(j, "stage_done")
        lc.handoff(j); lc.record_call(j, "writer")
        q = self.write(f"{home}/drafts/questions-draft.md", "Which region?\n")
        lc.apply(j, "needs_input", questions=str(self.tmp / q))
        lc.record_input(j, "-", "internal", data=b"North.\n")
        lc.apply(j, "answered")
        lc.apply(j, "artifact_ready", artifact=self.write(f"{home}/drafts/v1.md", f"Uses {home}/research/missing.md\n"))
        lc.handoff(j); lc.record_call(j, "writer")
        lc.apply(j, "revised", artifact=self.write(f"{home}/drafts/v2.md", "INTERNAL-MARKER per [A:A01]\n"))
        lc.handoff(j); lc.record_call(j, "critic")
        lc.apply(j, "review_pass")
        lc.handoff(j); lc.record_call(j, "verifier")
        lc.apply(j, "review_pass")
        self.assertEqual(g.main(["reject", j, "--feedback", "INTERNAL-MARKER: tighten section 2"]), 0)
        lc.apply(j, "revised", artifact=self.write(f"{home}/drafts/v3.md", "INTERNAL-MARKER v3\n"))
        lc.apply(j, "review_pass"); lc.apply(j, "review_pass")
        self.assertEqual(g.main(["approve", j, "--note", "ok"]), 0)
        return j, home

    def test_internal_job_writes_nothing_under_tracked_paths(self):
        lc = self.lc
        j, home = self.full_internal_run()
        st = lc.load_state(j)
        self.assertEqual((st["state"], st["class"]), ("APPROVED", "internal"))
        self.assertTrue((self.tmp / home / "state.json").is_file())
        self.assertFalse((self.tmp / "jobs" / j).exists())
        self.assertFalse((self.tmp / "logs/gate-audit.jsonl").exists())                  # audit went private
        audit = (self.tmp / "private/logs/gate-audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("INTERNAL-MARKER", audit)
        self.assertTrue(all(p.startswith(home) for p in [st["artifact_path"]] + [i["path"] for i in st["inputs"]]))
        self.assertEqual(lc.private_leaks(j), [])
        self.git("add", "-A")
        tracked = self.git("ls-files").stdout.splitlines()
        self.assertFalse([t for t in tracked if j in t or t.startswith("private/")], tracked)
        for t in tracked:
            text = (self.tmp / t).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("INTERNAL-MARKER", text, t)
            self.assertNotIn(j, text, t)

    def test_handoffs_point_into_the_private_job_folder(self):
        lc = self.lc
        j = lc.new_job("spec", "paths", "x", cls="internal")["job_id"]
        lc.apply(j, "dispatch")
        h, text = lc.handoff(j)
        self.assertTrue(all(i["path"].startswith(f"private/jobs/{j}/") for i in h["inputs"]), h["inputs"])
        self.assertEqual(h["output_dir"], f"private/jobs/{j}/research/")
        self.assertNotIn(f" jobs/{j}", text)

    def test_leak_check_catches_planted_writes(self):
        lc = self.lc
        j, _ = self.full_internal_run()
        self.write(f"jobs/{j}/notes.md", "stray copy")                                     # path names the job
        self.write("logs/usage.jsonl", json.dumps({"job": j}) + "\n")                       # content names the job
        leaks = lc.private_leaks(j)
        self.assertEqual(len(leaks), 2, leaks)
        self.assertTrue(any(f"jobs/{j}/notes.md" in x and "path" in x for x in leaks), leaks)
        self.assertTrue(any("logs/usage.jsonl" in x and "content" in x for x in leaks), leaks)
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "check-private", j],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 1)
        self.assertIn("2 leak(s)", p.stdout)

    def test_leak_check_catches_an_unignored_private_folder(self):
        lc = self.lc
        j = lc.new_job("spec", "unignored", "x", cls="internal")["job_id"]
        (self.tmp / ".gitignore").write_text("vendor/\n", encoding="utf-8")                # private/ no longer ignored
        leaks = lc.private_leaks(j)
        self.assertTrue(any("is not ignored by Git" in x for x in leaks), leaks)

    def test_internal_source_in_a_tracked_folder_is_refused(self):
        lc = self.lc
        j = lc.new_job("spec", "src", "x", cls="internal")["job_id"]
        src = self.write("scratch/answer.md", "internal text\n")
        with self.assertRaises(lc.LabError) as cm:
            lc.record_input(j, str(self.tmp / src), "internal")
        self.assertIn("stdin", str(cm.exception))
        self.write("private/drafts/answer.md", "internal text\n")
        _, rec = lc.record_input(j, str(self.tmp / "private/drafts/answer.md"), "internal")
        self.assertTrue(rec["path"].startswith(f"private/jobs/{j}/inputs/"))

    def test_leak_check_is_only_for_internal_jobs(self):
        lc = self.lc
        j = lc.new_job("spec", "pubjob", "x", cls="public")["job_id"]
        with self.assertRaises(lc.LabError):
            lc.private_leaks(j)


if __name__ == "__main__":
    unittest.main()
