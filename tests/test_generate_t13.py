"""T1.3: engine/generate.py. The thin blueprint generates, verifies and lints; the manifest catches hand edits,
unknown files and factory drift; lint holds every agent file to the rendered front matter and the default rules;
headless call lines carry the blueprint's exact tool list. Factory-only (tests/): it needs templates/, docs/thin/
and engine/designcheck.py, none of which is copied into an ecosystem. No venv is made here (no network)."""
import importlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from support import REPO, LabTestBase

TIER = "full"
BP = "docs/thin/blueprint.json"


class GenBase(LabTestBase):
    def setUp(self):
        super().setUp()
        for d in ("templates", "docs/thin"):
            shutil.copytree(REPO / d, self.tmp / d, ignore=shutil.ignore_patterns("__pycache__", "reports"))
        shutil.copy2(REPO / ".gitattributes", self.tmp / ".gitattributes")
        self.gen = importlib.import_module("generate")
        self.out = self.tmp / "eco"

    def make(self, bp=BP, **kw):
        return self.gen.generate(self.tmp / bp, self.out, venv=False, **kw)

    def manifest(self):
        return json.loads((self.out / "generation.json").read_text(encoding="utf-8"))

    def files(self):
        """The ecosystem as {relpath: bytes}, for lint_files with planted faults."""
        return {f.relative_to(self.out).as_posix(): f.read_bytes() for f in self.out.rglob("*")
                if f.is_file() and ".git" not in f.relative_to(self.out).parts}


class GenerateTests(GenBase):
    def test_the_thin_blueprint_generates_verifies_and_lints(self):
        s = self.make()
        self.assertEqual((s["slug"], s["agents"]), ("thin-v0", ["action-writer", "action-critic"]))
        self.assertEqual(self.gen.verify(self.out), [])
        self.assertEqual(self.gen.lint(self.out), [])
        self.assertTrue((self.out / ".git").is_dir())
        m = self.manifest()
        for r, e in m["files"].items():
            if e["kind"] in ("copied", "templated"):
                self.assertEqual(e["sha256"], self.gen.sha((self.tmp / e["source"]).read_bytes()), r)
        self.assertEqual((self.out / ".gitattributes").read_bytes(), (self.tmp / ".gitattributes").read_bytes())
        self.assertEqual(json.loads((self.out / "config/protected-paths.local.json").read_text(encoding="utf-8")),
                         {"no_write_roots": [self.tmp.resolve().as_posix()]})

    def test_factory_only_files_are_never_copied(self):
        self.make()
        for r in ("engine/check_coverage.py", "engine/designcheck.py"):
            self.assertFalse((self.out / r).exists(), r)
            self.assertIn(r, self.manifest()["excluded"])
        self.assertFalse((self.out / "tests").exists())
        (self.out / "engine/designcheck.py").write_text("x", encoding="utf-8")
        self.assertTrue(any("designcheck.py: excluded" in p for p in self.gen.verify(self.out)))

    def test_dry_run_writes_nothing(self):
        s = self.make(dry_run=True)
        self.assertTrue(s["dry_run"])
        self.assertFalse(self.out.exists())

    def test_refusals(self):
        self.out.mkdir()
        (self.out / "x.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(self.gen.GenerateError, "not empty"):
            self.make()
        shutil.rmtree(self.out)
        bp = json.loads((self.tmp / BP).read_text(encoding="utf-8"))
        bp["agents"][0]["tools"] = ["Agent"]
        (self.tmp / "docs/thin/bad.json").write_text(json.dumps(bp), encoding="utf-8")
        with self.assertRaisesRegex(self.gen.GenerateError, "does not pass its checks"):
            self.make("docs/thin/bad.json")
        self.assertFalse(self.out.exists())

    def test_rendered_config(self):
        self.make()
        cfg = lambda n: json.loads((self.out / f"config/{n}.json").read_text(encoding="utf-8"))
        route = cfg("routes")["routes"]["actions"]
        self.assertEqual((route["stages"], route["gate"]), ([{"agent": "action-writer"}], "G1-actions"))
        self.assertEqual(cfg("gates")["gates"], {"G1-actions": {"mode": "human"}})
        self.assertEqual(cfg("gated-actions")["mcp"], [{"tool": "mcp__ccd_turn__update_plan", "roles": ["main"]},
                                                      {"tool": "mcp__ccd_turn__wrap_up", "roles": ["main"]}])
        caps, factory = cfg("caps"), json.loads((self.tmp / "config/caps.json").read_text(encoding="utf-8"))
        for k, v in caps.items():
            if isinstance(v, int):
                self.assertLessEqual(v, factory[k], k)
        u = caps["usage_ceiling"]
        self.assertEqual((u["tokens"], u["agent_minutes"]), (300000, 30))
        self.assertLessEqual(u["per_call_warning_tokens"], u["tokens"])
        self.assertIn("PROVISIONAL", u["_provisional"])
        settings = json.loads((self.out / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertIs(settings["disableClaudeAiConnectors"], True)
        self.assertLessEqual({"Agent", "Task"}, set(settings["permissions"]["deny"]))
        rb = (self.out / "rules/action-rules.md").read_text(encoding="utf-8")
        for rid in ("TR01", "TR02", "TR03"):
            self.assertIn(f"| {rid} |", rb)
        self.assertEqual(cfg("outputs")["agents"], {                         # T1.3 follow-up: headless answers
            "action-writer": {"schema": "schemas/action-items.schema.json", "findings": False},
            "action-critic": {"schema": "schemas/findings.schema.json", "findings": True}})

    def test_the_default_rules_go_into_claude_md_and_every_agent_byte_for_byte(self):
        self.make()
        rules = (self.tmp / "rules/default-agent-rules.md").read_bytes()
        self.assertIn(rules, (self.out / "CLAUDE.md").read_bytes())
        for f in (self.out / ".claude/agents").glob("*.md"):
            self.assertIn(rules, f.read_bytes(), f.name)


class VerifyTests(GenBase):
    def setUp(self):
        super().setUp()
        self.make()

    def test_a_hand_edit_is_caught(self):
        f = self.out / ".claude/agents/action-writer.md"
        f.write_bytes(f.read_bytes() + b"\n")
        self.assertTrue(any("action-writer.md: differs from the manifest" in p for p in self.gen.verify(self.out)))

    def test_an_unknown_file_is_caught_but_runtime_folders_are_not(self):
        (self.out / "rules/extra.md").write_text("x", encoding="utf-8")
        for r in ("jobs/x/state.json", "logs/usage.jsonl", "evals/reports/r.json", "config/x.local.json"):
            (self.out / r).parent.mkdir(parents=True, exist_ok=True)
            (self.out / r).write_text("{}", encoding="utf-8")
        self.assertEqual(self.gen.verify(self.out), ["rules/extra.md: not in the manifest"])

    def test_a_copied_file_edited_in_the_ecosystem_or_changed_in_the_factory(self):
        (self.out / "engine/labcore.py").write_bytes((self.out / "engine/labcore.py").read_bytes() + b"#")
        self.assertTrue(any("engine/labcore.py: differs from the manifest" in p for p in self.gen.verify(self.out)))
        (self.out / "engine/labcore.py").write_bytes((self.tmp / "engine/labcore.py").read_bytes())
        self.assertEqual(self.gen.verify(self.out), [])
        (self.tmp / "engine/state.py").write_bytes((self.tmp / "engine/state.py").read_bytes() + b"#")
        self.assertTrue(any("engine/state.py: differs from the factory" in p for p in self.gen.verify(self.out)))

    def test_a_missing_or_unreadable_manifest_fails(self):
        (self.out / "generation.json").write_text("{", encoding="utf-8")
        self.assertTrue(self.gen.verify(self.out)[0].startswith("generation.json: unreadable"))


class LintTests(GenBase):
    def setUp(self):
        super().setUp()
        self.make()
        self.base = self.files()
        self.agent = ".claude/agents/action-writer.md"

    def lint_with(self, old, new, path=None):
        path = path or self.agent
        files = dict(self.base)
        self.assertIn(old.encode(), files[path], old)
        files[path] = files[path].replace(old.encode(), new.encode(), 1)
        return self.gen.lint_files(files)

    def assertRefused(self, probs, text):
        self.assertTrue(any(text in p for p in probs), probs)

    def test_the_generated_tree_lints_clean(self):
        self.assertEqual(self.gen.lint_files(self.base), [])

    def test_front_matter_faults(self):
        cases = [
            ("maxTurns: 3", "maxTurns: 3\npermissionMode: bypassPermissions", "permissionMode' is not allowed"),
            ("tools: []\n", "", "front matter has no tools"),
            ("tools: []", "tools:", "is not an explicit list"),
            ("tools: []", "tools: ", "is not an explicit list"),
            ("tools: []", "tools: [Read]", "is not an explicit list"),
            ("tools: []", "tools: Read, Agent", "has the Agent tool"),
            ("tools: []", "tools: Task", "has the Task tool"),
            ("tools: []", "tools: Bash", "'Bash' is not allowed"),
            ("tools: []", "tools: mcp__tracker__save_issue", "is not allowed"),
            ("name: action-writer", "name: Action Writer", "is not lowercase-hyphen"),
            ("name: action-writer", "name: action-critic", "differs from the file name"),
            ("maxTurns: 3", "maxTurns: 0", "not a whole number from 1 to 20"),
            ("maxTurns: 3", "maxTurns: many", "not a whole number from 1 to 20"),
            ("model: inherit", "model: some-other-model", "pinned model"),
            ("onFailure: block", "onFailure: ignore", "hooks differ"),
            ("name: action-writer", "name: action-writer\nname: x", "appears twice"),
        ]
        for old, new, text in cases:
            self.assertRefused(self.lint_with(old, new), text)

    def test_default_rules_must_be_byte_identical(self):
        for old, new in (("never softer.", "never softer!"), ("1. Output", "1.  Output"), ("\n8.", "\r\n8.")):
            self.assertRefused(self.lint_with(old, new), "does not contain rules/default-agent-rules.md byte for byte")
        self.assertRefused(self.lint_with("never softer.", "softer is fine.", path="CLAUDE.md"),
                           "CLAUDE.md does not contain")

    def test_empty_tools_need_the_in_session_deny_until_verified(self):
        self.assertFalse(self.gen.EMPTY_TOOLS_VERIFIED)
        probs = self.lint_with('"Agent",\n', "", path=".claude/settings.json")
        self.assertRefused(probs, "tools [] is not yet verified")
        self.assertRefused(self.lint_with('"disableClaudeAiConnectors": true', '"disableClaudeAiConnectors": false',
                                          path=".claude/settings.json"), "disableClaudeAiConnectors")

    def test_empty_tools_are_never_read_as_every_tool(self):
        self.assertEqual(self.gen.parse_tools("[]"), [])
        for raw in ("", "[ ]", "[Read]", "Read,", ", Read"):
            self.assertIsNone(self.gen.parse_tools(raw), raw)


class HeadlessCallTests(GenBase):
    def tooled_blueprint(self):
        bp = json.loads((self.tmp / BP).read_text(encoding="utf-8"))
        bp["agents"][0]["tools"] = ["Read", "Grep"]
        (self.tmp / "docs/thin/tooled.json").write_text(json.dumps(bp), encoding="utf-8")
        return "docs/thin/tooled.json"

    def test_no_tools_means_tools_equals_nothing_and_safe_mode(self):
        lines = self.make()["headless_calls"]
        for name, argv in lines.items():
            self.assertIn("--tools=", argv, name)
            self.assertIn("--safe-mode", argv, name)
            self.assertNotIn("--allowedTools", argv, name)
            self.assertEqual(argv[argv.index("--setting-sources") + 1], "project,local")
        self.assertEqual(self.manifest()["headless_calls"], lines)

    def test_a_tool_list_is_passed_exactly_to_tools_and_allowed_tools(self):
        lines = self.make(self.tooled_blueprint())["headless_calls"]
        w = lines["action-writer"]
        self.assertIn("--tools=Read,Grep", w)
        self.assertEqual(w[w.index("--allowedTools") + 1], "Read,Grep")
        self.assertNotIn("--safe-mode", w)
        self.assertEqual(self.gen.lint(self.out), [])

    def test_call_lines_match_agent_calls_own_builder_on_the_written_files(self):
        lines = self.make(self.tooled_blueprint())["headless_calls"]
        ac = importlib.import_module("agent_call")
        for f in (self.out / ".claude/agents").glob("*.md"):
            spec = ac.parse_agent(f)
            argv = ac.build_argv(spec, ac.agent_model(spec), self.tmp, cmd=["claude"])
            argv = ["<instructions file>" if a == str(self.tmp / "instructions.md") else a for a in argv]
            self.assertEqual(lines[spec["name"]], argv, f.name)


class CliTests(GenBase):
    def test_dry_run_verify_and_lint_from_the_command_line(self):
        py, g = sys.executable, str(self.tmp / "engine/generate.py")
        env = {**__import__("os").environ, "LAB_ROOT": str(self.tmp)}
        run = lambda *a: subprocess.run([py, g, *a], capture_output=True, text=True, env=env, timeout=300)
        p = run("generate", str(self.tmp / BP), str(self.out), "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DRY RUN: nothing written", p.stdout)
        self.assertFalse(self.out.exists())
        self.make()
        for cmd in ("verify", "lint"):
            p = run(cmd, str(self.out))
            self.assertEqual(p.returncode, 0, p.stdout)
            self.assertIn(": OK", p.stdout)
        (self.out / "rules/extra.md").write_text("x", encoding="utf-8")
        self.assertEqual(run("verify", str(self.out)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
