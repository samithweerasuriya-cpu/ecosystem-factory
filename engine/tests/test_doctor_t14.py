"""T0.14: engine/doctor.py. Every machine fact is simulated: a fake home folder, a fake command runner
(venv, py, git, claude), fake desktop app folders. One healthy setup, then each failure the plan names,
the privacy rules (home as ~, no user name, email or organisation, key names only), acknowledged
warnings, --deep, and gate.py lock refusing on a doctor FAIL."""
import hashlib
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

from support import REPO, LabTestBase

USER = "pat.example"
EMAIL = "pat.example@example.org"
ORG = "Example Organisation Ltd"
VALUE = "VALUE-MARKER-3317"
FAKE = Path(__file__).resolve().parent / "fake_claude.py"


class FakeRunner:
    def __init__(self):
        self.answers = {
            "venv": (0, "3.13\n", ""), "py": (0, "Python 3.15.0\n", ""), "git --version": (0, "git version 2.56.0\n", ""),
            "rev-parse": (0, "/repo\n", ""), "user.email": (0, "123+pat@users.noreply.github.com\n", ""),
            "remote": (0, "", ""), "claude --version": (0, "2.1.308 (Claude Code)\n", ""),
            "auth": (0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": EMAIL, "orgName": ORG,
                                    "configDirectory": f"C:\\Users\\{USER}\\.claude"}), ""),
            "wsl": (0, "Default Distribution: Ubuntu\n", ""),
        }
        self.calls = []

    def key(self, argv):
        s = " ".join(argv)
        if "-c" in argv and "jsonschema" in s:
            return "venv"
        for k in ("auth", "rev-parse", "user.email", "remote", "wsl"):
            if k in argv or (k == "auth" and "auth" in s):
                return k
        if argv[:1] == ["py"] or argv[:1] == ["python3"]:
            return "py"
        if argv[:2] == ["git", "--version"]:
            return "git --version"
        if argv[-1] == "--version":
            return "claude --version"
        return s

    def __call__(self, argv, timeout=60, cwd=None):
        self.calls.append(argv)
        return self.answers.get(self.key(argv), (None, "", "not found"))


class DoctorBase(LabTestBase):
    def setUp(self):
        super().setUp()
        for f in (".claude/settings.json", ".gitattributes", ".gitignore"):
            (self.tmp / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / f, self.tmp / f)
        (self.tmp / ".venv/Scripts").mkdir(parents=True)
        (self.tmp / ".venv/Scripts/python.exe").write_text("", encoding="utf-8")
        (self.tmp / ".venv/bin").mkdir(parents=True)
        (self.tmp / ".venv/bin/python").write_text("", encoding="utf-8")
        self.home = self.tmp / "Users" / USER
        self.local = self.home / "AppData" / "Local"
        self.tempdir = self.local / "Temp"
        self.tempdir.mkdir(parents=True)
        (self.local / "Claude-Data/claude_abc123/claude-code/2.1.308/deadbeef").mkdir(parents=True)
        self.eco = self.tmp / "ecosystems"
        (self.eco / "probe").mkdir(parents=True)
        self.runner = FakeRunner()
        self.env = {"LOCALAPPDATA": str(self.local), "DISABLE_AUTOUPDATER": "1"}
        sys.modules.pop("doctor", None)
        self.doc = importlib.import_module("doctor")

    def ctx(self, **kw):
        args = dict(root=self.tmp, home=self.home, env=self.env, localappdata=self.local, tempdir=self.tempdir,
                    ecosystems=self.eco, platform="win32", run=self.runner, user=USER)
        args.update(kw)
        return self.doc.Ctx(**args)

    def results(self, **kw):
        return {r["id"]: r for r in self.doc.fast_checks(self.ctx(**kw))}

    def status(self, cid, **kw):
        return self.results(**kw)[cid]["status"]

    def output(self, argv=(), **kw):
        lines = []
        code = self.doc.main(list(argv), ctx=self.ctx(**kw), out=lines.append)
        return code, "\n".join(lines)

    def user_file(self, rel, text):
        f = self.home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return f


class HealthyTests(DoctorBase):
    def test_a_healthy_setup_has_no_failure(self):
        res = self.results()
        fails = [r for r in res.values() if r["status"] == "FAIL"]
        self.assertEqual(fails, [], fails)
        code, text = self.output()
        self.assertEqual(code, 0)
        self.assertIn("-> ready", text)
        for cid in ("venv", "hook_python", "git", "cli_path", "cli_desktop", "auth", "api_key", "hook_files",
                    "hook_pins", "hook_settings", "layout"):
            self.assertEqual(res[cid]["status"], "OK", cid)

    def test_no_claude_call_by_default(self):
        self.doc.fast_checks(self.ctx())
        self.assertFalse(any("-p" in c for c in self.runner.calls))
        self.assertFalse(any(Path(str(c[0])).name == "fake_claude.py" for c in self.runner.calls))


class PrivacyTests(DoctorBase):
    def test_no_user_name_email_or_organisation_in_any_output(self):
        self.user_file(".claude/CLAUDE.md", "x")
        self.user_file(".claude/settings.json", json.dumps({"env": {"SOME_TOKEN": VALUE}, "model": VALUE}))
        (self.tempdir / "CLAUDE.md").write_text("x", encoding="utf-8")
        for argv in ([], ["--json"], ["--wsl"]):
            _, text = self.output(argv)
            for secret in (USER, EMAIL, ORG, VALUE, str(self.home)):
                self.assertNotIn(secret.lower(), text.lower(), (argv, secret))
        _, text = self.output()
        self.assertIn("~", text)                                            # home shown as ~
        self.assertIn("SOME_TOKEN", text)                                   # key names only
        data = json.loads(self.output(["--json"])[1])
        self.assertIn("results", data)

    def test_scrub_catches_every_spelling_of_the_home_folder(self):
        ctx = self.ctx()
        for s in (str(self.home), str(self.home).replace("\\", "/"), str(self.home).upper(),
                  json.dumps(str(self.home))):
            self.assertNotIn(USER, self.doc.scrub(ctx, f"at {s}/x").lower())

    def test_a_crashing_check_is_a_failure_not_a_traceback(self):
        def boom(ctx):
            raise RuntimeError(f"broken near {self.home}")
        real = self.doc.check_layout
        self.doc.check_layout = boom
        try:
            code, text = self.output()
        finally:
            self.doc.check_layout = real
        self.assertEqual(code, 1)
        self.assertIn("the check itself failed", text)
        self.assertNotIn(USER, text)


class ToolFailureTests(DoctorBase):
    def test_venv(self):
        self.runner.answers["venv"] = (1, "", "No module named jsonschema")
        r = self.results()["venv"]
        self.assertEqual((r["status"], "uv pip install" in r["fix"]), ("FAIL", True))
        self.runner.answers["venv"] = (0, "3.11\n", "")
        self.assertEqual(self.status("venv"), "FAIL")
        shutil.rmtree(self.tmp / ".venv")
        self.assertIn("uv venv", self.results()["venv"]["fix"])

    def test_hook_python_and_git(self):
        self.runner.answers["py"] = (None, "", "not found")
        self.assertIn("py", self.results()["hook_python"]["fix"])
        self.runner.answers["git --version"] = (None, "", "")
        self.assertEqual(self.status("git"), "FAIL")

    def test_git_identity_and_remote_warn(self):
        self.runner.answers["user.email"] = (0, "someone@work.example\n", "")
        self.runner.answers["remote"] = (0, "origin\n", "")
        res = self.results()
        self.assertEqual((res["git_identity"]["status"], res["git_remote"]["status"]), ("WARN", "WARN"))
        self.assertNotIn("someone@work.example", self.output()[1])          # the address itself is never printed

    def test_cli_versions(self):
        self.runner.answers["claude --version"] = (0, "2.1.200 (Claude Code)\n", "")
        res = self.results()
        self.assertEqual(res["cli_path"]["status"], "FAIL")
        self.assertEqual(res["cli_match"]["status"], "WARN")
        self.runner.answers["claude --version"] = (None, "", "")
        self.assertIn("install Claude Code", self.results()["cli_path"]["fix"])
        self.runner.answers["claude --version"] = (0, "2.1.308 (Claude Code)\n", "")
        shutil.rmtree(self.local / "Claude-Data")
        (self.local / "Claude-Data/claude_abc123/claude-code/2.1.100/x").mkdir(parents=True)
        self.assertEqual(self.status("cli_desktop"), "FAIL")
        shutil.rmtree(self.local / "Claude-Data")
        self.assertEqual(self.status("cli_desktop"), "INFO")

    def test_auth(self):
        self.runner.answers["auth"] = (0, json.dumps({"loggedIn": False}), "")
        self.assertIn("claude auth login", self.results()["auth"]["fix"])
        self.runner.answers["auth"] = (0, json.dumps({"loggedIn": True, "authMethod": "console", "email": EMAIL}), "")
        r = self.results()["auth"]
        self.assertEqual(r["status"], "FAIL")
        self.assertNotIn(EMAIL, json.dumps(r))

    def test_api_key_anywhere(self):
        self.assertEqual(self.status("api_key", env={**self.env, "ANTHROPIC_API_KEY": VALUE}), "FAIL")
        self.user_file(".claude/settings.json", json.dumps({"env": {"ANTHROPIC_API_KEY": VALUE}}))
        r = self.results()["api_key"]
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("user settings env", r["message"])
        self.assertNotIn(VALUE, self.output()[1])
        self.user_file(".claude/settings.json", json.dumps({"apiKeyHelper": "get-key.cmd"}))
        self.assertIn("apiKeyHelper", self.results()["api_key"]["message"])

    def test_an_unreadable_settings_file_fails_and_is_never_treated_as_empty(self):
        """Found live in T0.14: a missing comma in the user settings made the doctor see 'no keys'."""
        self.user_file(".claude/settings.json", '{\n  "theme": "dark"\n  "env": {"ANTHROPIC_API_KEY": "' + VALUE + '"}\n}')
        res = self.results()
        self.assertEqual(res["settings_json"]["status"], "FAIL")
        self.assertIn("not valid JSON (line 3", res["settings_json"]["message"])
        self.assertIn("~", res["settings_json"]["message"])
        self.assertIn("missing comma", res["settings_json"]["fix"])
        self.assertEqual(res["api_key"]["status"], "FAIL")                  # can't prove there is no key
        self.assertIn("can't be checked", res["api_key"]["message"])
        self.assertNotIn("user_settings", res)                              # no "keys: none" to acknowledge
        self.assertNotIn(VALUE, self.output()[1])
        self.user_file(".claude/settings.json", '{"theme": "dark"}')
        self.assertEqual(self.status("settings_json"), "OK")

    def test_auto_updates(self):
        env = {k: v for k, v in self.env.items() if k != "DISABLE_AUTOUPDATER"}
        r = self.results(env=env)["auto_updates"]
        self.assertEqual(r["status"], "WARN")
        self.assertIn("DISABLE_AUTOUPDATER", r["fix"])
        self.user_file(".claude/settings.json", json.dumps({"env": {"DISABLE_AUTOUPDATER": "1"}}))
        self.assertEqual(self.status("auto_updates", env=env), "OK")
        before = self.user_file(".claude/settings.json", json.dumps({"theme": "dark"})).read_bytes()
        self.doc.fast_checks(self.ctx(env=env))
        self.assertEqual((self.home / ".claude/settings.json").read_bytes(), before)  # never changed


class HookFailureTests(DoctorBase):
    def test_a_hook_that_does_not_compile(self):
        (self.tmp / "engine/hooks/pre_tool_use.py").write_text("def run(raw:\n", encoding="utf-8")
        res = self.results()
        self.assertEqual((res["hook_files"]["status"], res["hook_pins"]["status"]), ("FAIL", "FAIL"))
        self.assertIn("pre_tool_use.py", res["hook_files"]["message"])
        self.assertIn("git checkout", res["hook_files"]["fix"])

    def test_an_edited_hook_differs_from_its_pin(self):
        f = self.tmp / "engine/hooks/post_tool_use.py"
        f.write_text(f.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
        res = self.results()
        self.assertEqual((res["hook_files"]["status"], res["hook_pins"]["status"]), ("OK", "FAIL"))
        (self.tmp / "engine/hooks/pre_tool_use_launcher.py").unlink()
        self.assertIn("missing", self.results()["hook_files"]["message"])

    def test_registration(self):
        s = json.loads((self.tmp / ".claude/settings.json").read_text(encoding="utf-8"))
        del s["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"]
        (self.tmp / ".claude/settings.json").write_text(json.dumps(s), encoding="utf-8")
        r = self.results()["hook_settings"]
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("onFailure", r["message"])
        s["hooks"].pop("PostToolUse")
        (self.tmp / ".claude/settings.json").write_text(json.dumps(s), encoding="utf-8")
        self.assertIn("post_tool_use_launcher.py not registered", self.results()["hook_settings"]["message"])

    def test_the_shipped_pins_match_the_shipped_hooks(self):
        pins = json.loads((REPO / "engine/hooks/PINS.json").read_text(encoding="utf-8"))
        for f in self.doc.HOOK_FILES:
            self.assertEqual(hashlib.sha256((REPO / "engine/hooks" / f).read_bytes()).hexdigest(), pins[f],
                             f"{f} changed: update its pin in engine/hooks/PINS.json in the same commit")


class UserLevelTests(DoctorBase):
    def test_user_level_files_warn_with_names_only(self):
        self.user_file(".claude/agents/helper.md", "x")
        self.user_file(".claude/skills/writer/SKILL.md", "x")
        self.user_file(".claude/commands/go.md", "x")
        self.user_file("CLAUDE.md", "x")
        self.user_file(".claude/settings.json", json.dumps({"hooks": {}, "env": {"MY_VAR": VALUE}}))
        res = self.results()
        for cid in ("user_agents", "user_skills", "user_commands", "user_claude_md", "user_settings"):
            self.assertEqual(res[cid]["status"], "WARN", cid)
        self.assertIn("helper", res["user_agents"]["message"])
        self.assertIn("MY_VAR", res["user_settings"]["message"])
        self.assertIn("hooks", res["user_settings"]["message"])
        self.assertNotIn(VALUE, json.dumps(list(res.values())))
        self.assertIn("~", res["user_claude_md"]["message"])

    def test_a_user_skill_shadowing_a_project_command(self):
        (self.tmp / ".claude/commands").mkdir(parents=True)
        (self.tmp / ".claude/commands/run-job.md").write_text("x", encoding="utf-8")
        self.user_file(".claude/skills/run-job/SKILL.md", "x")
        r = self.results()["skill_collisions"]
        self.assertEqual((r["status"], r["details"]), ("WARN", {"names": ["run-job"]}))

    def test_stray_claude_md_above_run_folders_and_ecosystems(self):
        self.assertEqual(self.status("stray_claude_md"), "OK")
        (self.local / "CLAUDE.md").write_text("x", encoding="utf-8")             # a parent of the temp folder
        r = self.results()["stray_claude_md"]
        self.assertEqual(r["status"], "WARN")
        self.assertIn("~", r["message"])
        (self.local / "CLAUDE.md").unlink()
        (self.eco / "CLAUDE.md").write_text("x", encoding="utf-8")
        self.assertEqual(self.status("stray_claude_md"), "WARN")
        (self.eco / "CLAUDE.md").unlink()
        (self.eco / "probe" / "CLAUDE.md").write_text("x", encoding="utf-8")     # an ecosystem's own: fine
        self.assertEqual(self.status("stray_claude_md"), "OK")

    def test_local_config(self):
        (self.tmp / "vendor").mkdir()
        self.assertEqual(self.status("protected_local"), "WARN")
        self.dump("config/protected-paths.local.json", {"source_roots": []})
        self.assertEqual(self.status("protected_local"), "OK")
        self.assertIn("not found", self.results()["markitdown"]["message"])
        conv = self.tmp / "markitdown.exe"
        conv.write_text("", encoding="utf-8")
        self.dump("config/evidence.local.json", {"pdf_converter": [str(conv)]})
        self.assertIn("markitdown found", self.results()["markitdown"]["message"])
        shutil.rmtree(self.tmp / "vendor")
        self.assertNotIn("protected_local", self.results())                    # factory-only check


class EvalAndModeTests(DoctorBase):
    def test_stale_evaluations_warn_in_build_mode_and_fail_in_operate_mode(self):
        self.assertEqual(self.status("evals"), "WARN")
        (self.tmp / ".lab").mkdir(exist_ok=True)
        (self.tmp / ".lab/OPERATE").write_text("on", encoding="utf-8")
        r = self.results()["evals"]
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("operate mode is locked", r["message"])
        self.assertIn("operate mode", self.results()["mode"]["message"])

    def test_layout(self):
        (self.tmp / ".gitattributes").write_text("jobs/** -text\n", encoding="utf-8")
        r = self.results()["layout"]
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("engine/** -text", r["message"])

    def test_wsl_only_on_request(self):
        self.assertNotIn("wsl", self.results())
        code, text = self.output(["--wsl"])
        self.assertIn("WSL available", text)


class AckTests(DoctorBase):
    def test_an_acknowledged_warning_is_info_until_its_details_change(self):
        self.user_file(".claude/skills/one/SKILL.md", "x")
        with self.assertRaisesRegex(self.lc.LabError, "own terminal"):
            self.doc.ack(self.ctx(), "user_skills", interactive=False)
        self.doc.ack(self.ctx(), "user_skills", interactive=True)
        r = self.results()["user_skills"]
        self.assertEqual((r["status"], r.get("acknowledged")), ("INFO", True))
        self.assertTrue(r["message"].startswith("acknowledged"))
        self.user_file(".claude/skills/two/SKILL.md", "x")                    # details change
        r = self.results()["user_skills"]
        self.assertEqual(r["status"], "WARN")
        self.assertIn("details changed", r["message"])
        with self.assertRaisesRegex(self.lc.LabError, "no current warning"):
            self.doc.ack(self.ctx(), "venv", interactive=True)                  # only warnings
        self.assertIn("doctor.local.json", (REPO / ".gitignore").read_text(encoding="utf-8").replace(
            "config/*.local.json", "doctor.local.json"))                       # untracked by the *.local.json rule

    def test_a_failure_can_never_be_acknowledged(self):
        self.runner.answers["auth"] = (0, json.dumps({"loggedIn": False}), "")
        with self.assertRaisesRegex(self.lc.LabError, "no current warning"):
            self.doc.ack(self.ctx(), "auth", interactive=True)


class DeepTests(DoctorBase):
    def setUp(self):
        super().setUp()
        models = json.loads((self.tmp / "config/models.json").read_text(encoding="utf-8"))
        models["claude_command"] = [sys.executable, str(FAKE)]
        self.dump("config/models.json", models)
        os.environ.pop("FAKE_CLAUDE_MODE", None)

    def test_deep_needs_confirmation_and_shows_its_cost(self):
        code, text = self.output(["--deep"])
        self.assertEqual(code, 1)
        self.assertIn("about", text)
        self.assertIn("REFUSED", text)

    def test_deep_with_yes_makes_one_live_call(self):
        code, text = self.output(["--deep", "--yes"], cli=[sys.executable, str(FAKE)])
        self.assertIn("live headless call answered", text)
        os.environ["FAKE_CLAUDE_MODE"] = "nojson"
        try:
            code, text = self.output(["--deep", "--yes"], cli=[sys.executable, str(FAKE)])
        finally:
            os.environ.pop("FAKE_CLAUDE_MODE", None)
        self.assertEqual(code, 1)
        self.assertIn("infra_error", text)


class GateLockTests(DoctorBase):
    def test_lock_refuses_on_a_doctor_failure(self):
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        g.eval_lock_problems = lambda: []
        g.doctor_failures = lambda: ["auth: the CLI is not logged in (Fix: run: claude auth login)"]
        self.assertEqual(g.main(["lock"]), 1)
        self.assertFalse((self.tmp / ".lab/OPERATE").exists())
        self.assertFalse((self.tmp / "logs/gate-audit.jsonl").exists())
        g.doctor_failures = lambda: []
        self.assertEqual(g.main(["lock"]), 0)

    def test_the_doctor_lines_gate_reads_are_the_fast_failures(self):
        self.runner.answers["auth"] = (0, json.dumps({"loggedIn": False, "email": EMAIL}), "")
        lines = self.doc.failures(self.ctx())
        self.assertTrue(any(l.startswith("auth:") and "Fix:" in l for l in lines), lines)
        self.assertFalse(any(EMAIL in l or USER in l for l in lines))
