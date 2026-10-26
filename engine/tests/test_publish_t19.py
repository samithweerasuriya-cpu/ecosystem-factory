"""T0.19: engine/publish_check.py (denylist, secrets, paths, emails, forbidden files; tree, staged, message,
history and push modes; the three Git hooks, run for real in a temporary repository) and state.py
stage-record. Every denylist term here is made up."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from support import LabTestBase, force_rmtree

TERMS = "# test denylist\nAcme Corp\ncase: Zed\nxyzzy-lab\n"


class PublishBase(LabTestBase):
    def setUp(self):
        super().setUp()
        self.pc = importlib.import_module("publish_check")
        self.write("private/denylist.txt", TERMS)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.org")
        self.git("config", "user.name", "Test")
        self.git("config", "core.autocrlf", "false")
        (self.tmp / ".gitignore").write_text("private/\ncache/\n", encoding="utf-8")

    def git(self, *args, check=True, cwd=None, env=None):
        p = subprocess.run(["git", "-C", str(cwd or self.tmp), *args], capture_output=True, text=True,
                           env=env or {**os.environ, "LAB_ROOT": str(self.tmp)})
        if check and p.returncode != 0:
            raise AssertionError(f"git {args}: {p.stderr}")
        return p

    def commit(self, rel, text, msg="add", verify=True):
        self.write(rel, text)
        self.git("add", "-f", rel)
        return self.git("commit", "-q", "-m", msg, *([] if verify else ["--no-verify"]), check=False)

    def run_pc(self, *argv, stdin=None):
        lines = []
        code = self.pc.main(list(argv), root=self.tmp, out=lines.append, stdin=stdin)
        return code, "\n".join(lines)

    def rules(self):
        return self.pc.Rules(self.tmp)


class RuleTests(PublishBase):
    def test_the_denylist_fails_closed(self):
        (self.tmp / "private/denylist.txt").unlink()
        code, out = self.run_pc()
        self.assertEqual(code, 1)
        self.assertIn("missing or unreadable", out)
        self.write("private/denylist.txt", "# only comments\n\n")
        self.assertIn("no terms", self.run_pc()[1])

    def test_whole_word_any_case_and_exact_case(self):
        r = self.rules()
        hit = lambda t: [f[2] for f in r.text_findings(t, "x") if f[1] == "denylist term"]
        self.assertEqual(hit("we met acme corp today"), ["Acme Corp"])
        self.assertEqual(hit("acmecorporation"), [])                  # whole word only
        self.assertEqual(hit("Ask Zed."), ["Zed"])
        self.assertEqual(hit("zed and ZED"), [])                      # exact case
        self.assertEqual(hit("see xyzzy-lab/notes"), ["xyzzy-lab"])

    def test_secrets_are_found_and_never_printed_in_full(self):
        key = "sk-ant-" + "a1B2c3D4e5F6g7H8i9J0"
        # fixtures are assembled at run time, so this file itself passes the publish check
        for text in (f"key = {key}", "token: ghp_" + "A" * 30, "AKIA" + "ABCDEFGHIJKLMNOP",
                     "-----BEGIN RSA " + "PRIVATE KEY-----", 'password = "' + "x" * 24 + '"'):
            self.assertTrue(any(f[1] == "secret" for f in self.rules().text_findings(text, "f")), text)
        self.commit("notes.txt", f"key = {key}\n", verify=False)
        code, out = self.run_pc()
        self.assertEqual(code, 1)
        self.assertNotIn(key, out)

    def test_home_paths_emails_and_source_folders(self):
        r = self.rules()
        kinds = lambda t: {f[1] for f in r.text_findings(t, "x")}
        users = "Us" + "ers"                                            # assembled: see above
        self.assertIn("home-folder path", kinds("C:\\" + users + "\\pat.example\\AppData\\x"))
        self.assertIn("home-folder path", kinds("/c/" + users + "/pat.example/x"))
        self.assertNotIn("home-folder path", kinds(r"C:\Users\{USER}\x and ~/AppData and C:\Users\Public"))
        self.assertIn("email address", kinds("mail pat" + "@" + "corp-mail.net"))
        self.assertEqual(kinds("t@example.org 1+x@users.noreply.github.com noreply@anthropic.com a@work.example"), set())
        self.dump("config/protected-paths.local.json", {"source_roots": [r"D:\old-labs\secret-lab"]})
        self.assertIn("source folder path", {f[1] for f in self.rules().text_findings("copied from D:/old-labs/secret-lab/x", "x")})

    def test_paths_and_names_are_checked_too(self):
        self.commit("docs/xyzzy-lab-notes.md", "clean\n", verify=False)
        self.commit("vendor/copy.txt", "clean\n", verify=False)
        self.commit("config/x.local.json", "{}\n", verify=False)
        self.commit("deploy/.env.prod", "A=1\n", verify=False)
        code, out = self.run_pc()
        self.assertEqual(code, 1)
        for what in ("denylist term: docs/xyzzy-lab-notes.md", "forbidden path: vendor/copy.txt",
                     "forbidden file: config/x.local.json", "forbidden file: deploy/.env.prod"):
            self.assertIn(what, out)


class ModeTests(PublishBase):
    def test_tree_mode_needs_files(self):
        code, out = self.run_pc()
        self.assertEqual(code, 1)
        self.assertIn("zero files", out)

    def test_staged_mode_reads_the_index_not_the_working_copy(self):
        self.write("a.md", "clean\n")
        self.git("add", "a.md")
        self.write("a.md", "now mentions Acme Corp\n")                # working copy only
        self.assertEqual(self.run_pc("--staged")[0], 0)
        self.git("add", "a.md")
        code, out = self.run_pc("--staged")
        self.assertEqual(code, 1)
        self.assertIn("denylist term: a.md: Acme Corp", out)

    def test_message_and_history(self):
        f = self.tmp / "msg.txt"
        f.write_text("Fix Zed's report\n# Zed in a comment line is ignored\n", encoding="utf-8")
        self.assertEqual(self.run_pc("--message", str(f))[0], 1)
        f.write_text("Fix the report\n# Zed in a comment line is ignored\n", encoding="utf-8")
        self.assertEqual(self.run_pc("--message", str(f))[0], 0)
        self.commit("a.md", "talks about Acme Corp\n", verify=False)
        self.commit("a.md", "clean now\n", msg="for Zed", verify=False)
        self.assertEqual(self.run_pc()[0], 0)                          # the tree is clean...
        code, out = self.run_pc("--history")                             # ...but the history is not
        self.assertEqual(code, 1)
        self.assertIn("Acme Corp", out)
        self.assertIn("message: Zed", out)


class HookTests(PublishBase):
    def test_the_three_hooks_block_for_real(self):
        lines = []
        self.assertEqual(self.pc.main(["install"], root=self.tmp, out=lines.append), 0)
        self.assertEqual(len(lines), 3)
        self.assertEqual(self.commit("ok.md", "clean\n").returncode, 0)
        bad = self.commit("bad.md", "Acme Corp internal\n")
        self.assertNotEqual(bad.returncode, 0)                           # pre-commit
        self.assertIn("BLOCKED", bad.stdout + bad.stderr)
        self.git("reset", "-q", "HEAD", "bad.md")
        self.assertNotEqual(self.commit("ok2.md", "clean\n", msg="ask Zed").returncode, 0)   # commit-msg
        self.assertEqual(self.git("log", "--oneline").stdout.count("\n"), 1)
        remote = Path(tempfile.mkdtemp())
        try:
            self.git("init", "-q", "--bare", str(remote), cwd=remote.parent)
            self.git("remote", "add", "origin", str(remote))
            self.assertEqual(self.git("push", "-q", "origin", "main", check=False).returncode, 0)
            self.git("reset", "-q", "HEAD")
            self.commit("planted.md", "xyzzy-lab material\n", verify=False)   # planted past the commit hooks
            p = self.git("push", "-q", "origin", "main", check=False)        # pre-push
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("xyzzy-lab", p.stdout + p.stderr)
        finally:
            force_rmtree(remote)

    def test_install_never_overwrites_a_foreign_hook(self):
        hooks = self.tmp / ".git/hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-push").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        code, out = self.run_pc("install")
        self.assertEqual(code, 1)
        self.assertIn("merge it by hand", out)


class StageRecordTests(PublishBase):
    def setUp(self):
        super().setUp()
        self.sr = importlib.import_module("stagerecord")

    def logs(self, a, b):
        for name in ("gate-audit", "usage"):
            self.write(f"logs/{name}.jsonl", "".join(json.dumps({"job_id": j, "n": i}) + "\n"
                                                     for i, j in enumerate([a, b, a])))

    def staged(self, path):
        return self.git("show", f":{path}", check=False).stdout

    def test_one_job_folder_and_only_its_log_lines(self):
        lc = self.lc
        a = lc.new_job("spec", "alpha", "x")["job_id"]
        b = lc.new_job("spec", "beta", "x")["job_id"]
        self.logs(a, b)
        files, logs = self.sr.stage(a)
        self.assertTrue(files and all(f.startswith(f"jobs/{a}/") for f in files))
        self.assertEqual(logs, {"logs/gate-audit.jsonl": 2, "logs/usage.jsonl": 2})
        staged = self.staged("logs/usage.jsonl")
        self.assertEqual(staged.count(a), 2)
        self.assertNotIn(b, staged)                                      # the other job's line stays unstaged
        names = self.git("diff", "--cached", "--name-only").stdout
        self.assertNotIn(b, names)

    def test_refusals(self):
        lc = self.lc
        a = lc.new_job("spec", "alpha", "x")["job_id"]
        inside = lc.new_job("spec", "inside", "x", cls="internal")["job_id"]
        with self.assertRaisesRegex(lc.LabError, "internal job"):
            self.sr.stage(inside)
        self.write("notes.md", f"see {inside}\n")                        # an internal job leaking elsewhere
        with self.assertRaisesRegex(lc.LabError, "would leak"):
            self.sr.stage(a)
        (self.tmp / "notes.md").unlink()
        self.write(f"jobs/{a}/drafts/v1.md", "for Acme Corp\n")
        with self.assertRaisesRegex(lc.LabError, "publish check"):
            self.sr.stage(a)
        self.write(f"jobs/{a}/drafts/v1.md", "clean\n")
        self.logs(a, a)
        self.sr.stage(a)
        self.write("logs/usage.jsonl", json.dumps({"job_id": a}) + "\n")   # rewritten, not appended
        with self.assertRaisesRegex(lc.LabError, "append-only"):
            self.sr.stage(a)
        self.write("logs/usage.jsonl", self.staged("logs/usage.jsonl") + "not json\n")
        with self.assertRaisesRegex(lc.LabError, "can't be read"):
            self.sr.stage(a)
        with self.assertRaisesRegex(lc.LabError, "job not found"):
            self.sr.stage("20260101-spec-nothere")

    def test_the_cli(self):
        a = self.lc.new_job("spec", "clijob", "x")["job_id"]
        p = subprocess.run([sys.executable, str(self.tmp / "engine/state.py"), "stage-record", a],
                           capture_output=True, text=True, env=self.hook_env(), cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(f"of {a}", p.stdout)


class DoctorHookTests(PublishBase):
    def test_doctor_reports_missing_hooks_and_a_missing_denylist(self):
        doc = importlib.import_module("doctor")
        ctx = doc.Ctx(root=self.tmp, run=lambda *a, **k: (0, "", ""))
        self.assertEqual(doc.check_publish_hooks(ctx)["status"], "FAIL")     # factory: private/ exists
        self.run_pc("install")
        self.assertEqual(doc.check_publish_hooks(ctx)["status"], "OK")
        (self.tmp / "private/denylist.txt").unlink()
        r = doc.check_publish_hooks(ctx)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("can't check anything", r["message"])
