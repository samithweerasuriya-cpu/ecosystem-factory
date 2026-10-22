"""T0.7: hook fixes and isolation.

Fixtures F00-F15 are generic rewrites of the 16 entries in the earlier private lab's blocked log
(mapping kept privately); each keeps the shape that mattered. Then: Samith's block list, path
spellings, no-write roots, read blocks by role and mode, the scratchpad rule, private block logs,
the fail-closed launcher and the settings registration."""
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO, LabTestBase, force_rmtree

J = "20260101-spec-sample"
LAUNCHER_SHA256 = "55cec23fbf4a1e34a229fa7a31f199fb4dab1ff098f137f23d7195eecf768ec6"


def posix_forms(path):
    """Git Bash (/c/...) and WSL (/mnt/c/...) spellings of a Windows path."""
    p = str(path).replace("\\", "/")
    drive, rest = p[0].lower(), p[2:]
    return f"/{drive}{rest}", f"/mnt/{drive}{rest}"


class HookBase(LabTestBase):
    def setUp(self):
        super().setUp()
        self.outside = Path(tempfile.mkdtemp())                  # stands in for C:\ecosystems
        self.scratch = Path(tempfile.mkdtemp())                  # the session scratchpad
        (self.tmp / "config/protected-paths.local.json").unlink(missing_ok=True)
        self.dump("config/protected-paths.json", {
            "no_write_roots": [str(self.outside / "ecosystems")],
            "source_roots": [str(self.outside / "source-lab")],
            "read_blocks": {
                "subagents": ["vendor/method-lab/**", "private/**", "docs/thin/**", "evals/**/keys/**", "evals/**/*-key.*"],
                "operate_main": ["vendor/method-lab/**", "private/**", "evals/**/keys/**", "evals/**/*-key.*"],
                "operate_main_read_only": ["private/plan/**"]}})
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        self.hook = importlib.import_module("pre_tool_use")

    def tearDown(self):
        while str(self.tmp / "engine/hooks") in sys.path:
            sys.path.remove(str(self.tmp / "engine/hooks"))
        force_rmtree(self.outside)
        force_rmtree(self.scratch)
        super().tearDown()

    def call(self, tool, agent=False, scratch=True, cwd=None, **ti):
        data = {"tool_name": tool, "tool_input": ti, "cwd": str(cwd or self.tmp),
                "scratchpad_dir": str(self.scratch) if scratch is True else scratch}
        if agent:
            data.update(agent_id="a123", agent_type="factory-critic")
        return self.hook.run(json.dumps(data))

    def sh(self, cmd, tool="Bash", **kw):
        return self.call(tool, command=cmd, **kw)

    def operate(self):
        (self.tmp / ".lab").mkdir(exist_ok=True)
        (self.tmp / ".lab/OPERATE").write_text("on")

    def assertAllowed(self, code, what=""):
        self.assertEqual(code, 0, what)

    def assertBlocked(self, code, what=""):
        self.assertEqual(code, 2, what)


class SourceFixtureTests(HookBase):
    """The earlier lab's blocked log, re-run: 8 false positives now allowed, 5 correct blocks,
    3 still blocked by design (they name a protected path and are not entirely read-only)."""

    def test_F00_listing_lab_folder_with_harmless_redirect(self):
        self.assertAllowed(self.sh("python3 --version && ls -la && ls -la .lab 2>/dev/null"))

    def test_F01_secret_names_inside_a_grep_pattern(self):
        cmd = ("git log --oneline; echo \"remotes: [$(git remote -v)]\"; git status --short | head; "
               "git ls-files | grep -iE '\\.env|master\\.key|^logs/[^.]|^\\.lab' ; echo \"tracked: $(git ls-files | wc -l)\"")
        self.assertAllowed(self.sh(cmd))

    def test_F02_write_to_a_gate_file(self):
        self.assertBlocked(self.call("Write", file_path=str(self.tmp / "jobs/test/gates/x.json")))

    def test_F03_F05_gate_py_show_stays_human_only(self):
        self.assertBlocked(self.sh("python3 engine/gate.py show x"))
        self.assertBlocked(self.sh("python3 engine/gate.py show x", tool="Monitor"))

    def test_F04_reading_dot_env(self):
        self.assertBlocked(self.sh("cat .env"))

    def test_F06_by_design_text_naming_a_protected_path_appended_to_a_file(self):
        cmd = ("printf '%s\\n' '| T0.8 | pass | ran `gate.py lock` / `unlock` in own terminal; `.lab/OPERATE` absent after. |'"
               " >> docs/build-log.md && tail -n 1 docs/build-log.md | cut -c1-60")
        self.assertBlocked(self.sh(cmd))

    def test_F07_F14_writes_into_the_harness_scratchpad(self):
        self.assertAllowed(self.call("Write", file_path=str(self.scratch / "tools/force_ipv4.rb")))
        self.assertAllowed(self.call("Write", file_path=str(self.scratch / "inspect.sh")))

    def test_F08_write_to_an_engine_file_in_operate_mode(self):
        self.operate()
        self.assertBlocked(self.call("Write", file_path=str(self.tmp / "engine/tools/force_ipv4.rb")))

    def test_F09_by_design_interpreter_loading_a_protected_file(self):
        self.operate()
        self.assertBlocked(self.sh(f"ruby -r\"{self.tmp}/engine/tools/force_ipv4.rb\" -rnet/http -e 'puts 1'"))

    def test_F10_read_only_checks_naming_protected_paths(self):
        self.operate()
        cmd = ("test -e .lab/OPERATE && echo LOCKED || echo UNLOCKED; grep -rIn \"NameA\\|NameB\" CLAUDE.md rules/ "
               ".claude/agents/*.md 2>/dev/null | cut -c1-220")
        self.assertAllowed(self.sh(cmd))

    def test_F11_by_design_pipe_into_inline_python(self):
        cmd = (f"ls -a .lab; git log --oneline | head -1; python3 engine/state.py status {J} | "
               "python3 -c \"import json,sys; print(json.load(sys.stdin)['state'])\"")
        self.assertBlocked(self.sh(cmd))

    def test_F12_relative_paths_after_cd_elsewhere(self):
        self.operate()
        cmd = (f"cd \"{self.scratch}/agency-src\" && grep -n -A30 \"^install\" engine/install.sh; "
               "sed -n 380,388p engine/install.sh; grep -c \"\" engine/install.sh")
        self.assertAllowed(self.sh(cmd))

    def test_F13_loop_over_unprotected_folders(self):
        cmd = (f"S=\"{self.scratch}/agency-src\"; cd \"$S\"\necho \"== keys ==\"; for f in $(grep -l -r \"^---\" academic design); "
               "do awk 'NR==1{print FILENAME}' \"$f\"; done | sort | uniq -c")
        self.assertAllowed(self.sh(cmd))

    def test_F15_heredoc_copying_between_unprotected_paths(self):
        cmd = ("python3 - <<'EOF'\nimport shutil\nfrom pathlib import Path\n"
               f"src = Path(\"jobs/{J}/drafts/v7\")\nshutil.copyfile(src / \"adr.md\", \"contracts/adr/ADR-001.md\")\nEOF")
        self.assertAllowed(self.sh(cmd))


class FailClosedShellTests(HookBase):
    """Samith's list: each names a protected path and must be blocked."""

    def test_substitution_and_obfuscation(self):
        for cmd in (f"cat $(echo jobs/{J}/state.json)", f"cat `echo jobs/{J}/state.json`",
                    f"eval \"rm jobs/{J}/state.json\"", "echo cm0gLWYgam9icy8qL3N0YXRlLmpzb24= | base64 -d | sh",
                    "eval echo hello"):                                    # eval is blocked even without a path
            self.assertBlocked(self.sh(cmd), cmd)
        self.assertBlocked(self.sh(f"iex \"Remove-Item jobs\\{J}\\state.json\"", tool="PowerShell"))
        self.assertBlocked(self.sh("powershell -EncodedCommand UgBlAG0AbwB2AGUALQBJAHQAZQBtACAA", tool="PowerShell"))

    def test_git_write_subcommands(self):
        for sub in (f"checkout -- jobs/{J}/state.json", f"restore jobs/{J}/state.json",
                    f"apply --include=jobs/{J}/state.json fix.patch", f"mv jobs/{J}/state.json old.json",
                    f"stash push jobs/{J}/state.json"):
            self.assertBlocked(self.sh(f"git {sub}"), sub)

    def test_file_tools(self):
        for cmd in (f"find jobs/{J} -name state.json -delete", f"find jobs/{J} -name '*.json' | xargs rm",
                    f"dd if=/dev/zero of=jobs/{J}/state.json", f"rsync -a backup/ jobs/{J}/gates/",
                    f"rm -rf jobs/{J}", "rm -rf ."):
            self.assertBlocked(self.sh(cmd), cmd)
        for cmd in (f"robocopy . jobs\\{J}\\gates", f"xcopy x.json jobs\\{J}\\gates\\", f"copy x.json jobs\\{J}\\state.json",
                    f"move x.json jobs\\{J}\\state.json"):
            self.assertBlocked(self.sh(f"cmd /c {cmd}"), cmd)
        for cmd in (f"Add-Content jobs\\{J}\\state.json 'x'", "New-Item -Path .lab\\OPERATE -ItemType File",
                    f"[IO.File]::WriteAllText('jobs\\{J}\\state.json','x')", f"[System.IO.File]::WriteAllBytes(\"jobs/{J}/state.json\", $b)"):
            self.assertBlocked(self.sh(cmd, tool="PowerShell"), cmd)

    def test_nested_shells_are_checked_recursively(self):
        for cmd in (f"bash -c \"echo x > jobs/{J}/state.json\"", f"sh -c 'rm .lab/OPERATE'",
                    f"cmd /c del jobs\\{J}\\state.json", f"wsl -d Ubuntu -- bash -lc \"rm /mnt/c/x/jobs/{J}/state.json\"",
                    f"bash -c \"bash -c 'touch .lab/OPERATE'\""):
            self.assertBlocked(self.sh(cmd), cmd)
        self.assertBlocked(self.sh(f"powershell -Command \"Set-Content jobs\\{J}\\state.json x\"", tool="PowerShell"))
        self.assertAllowed(self.sh(f"bash -c \"cat jobs/{J}/state.json | head -5\""))  # read-only all the way down

    def test_unparseable_command_naming_a_protected_path(self):
        self.assertBlocked(self.sh(f"cat \"jobs/{J}/state.json"))               # unbalanced quote
        self.assertAllowed(self.sh("echo \"unbalanced but harmless"))          # nothing protected named

    def test_read_only_commands_on_protected_paths_are_allowed(self):
        for cmd in (f"cat jobs/{J}/state.json", f"head -20 jobs/{J}/run.log.jsonl", f"wc -l jobs/{J}/run.log.jsonl",
                    f"git log -- jobs/{J}/state.json", f"git diff jobs/{J}/state.json 2>&1 | head", "ls .lab"):
            self.assertAllowed(self.sh(cmd), cmd)
        self.assertAllowed(self.sh(f"Get-Content jobs\\{J}\\state.json | Select-String state", tool="PowerShell"))
        self.assertAllowed(self.sh("git grep --cached -niE 'term1|term2' -- ."))                 # the publish scan
        self.assertAllowed(self.sh(f"git check-ignore -v jobs/{J}/state.json"))
        self.assertBlocked(self.sh(f"sort -o jobs/{J}/state.json jobs/{J}/state.json"))  # write flag
        self.assertBlocked(self.sh(f"git diff --output=jobs/{J}/state.json"))

    def test_a_dot_inside_text_is_not_the_repo_root(self):
        self.assertAllowed(self.sh("sed -i 's/^root = x$/root = Path(\".\").resolve()/' docs/notes.md"))
        self.assertAllowed(self.sh("python -c \"print('a. b. c.')\""))
        self.assertBlocked(self.sh("rm -rf ."))                             # as an argument it is
        self.assertBlocked(self.sh("cp -r backup/* ./"))

    def test_engine_tools_may_name_job_folders(self):
        self.assertAllowed(self.sh(f"python engine/state.py status {J}"))
        self.assertAllowed(self.sh(f".venv/Scripts/python.exe engine/validate_findings.py jobs/{J}/reviews/critic-v1.json"))
        self.assertBlocked(self.sh(f"python engine/state.py status {J} > jobs/{J}/state.json"))


class SpellingTests(HookBase):
    """(g) the hook, not the prefix-matching deny rules, is the real guard: spellings resolve."""

    def test_write_tool_spellings(self):
        tmp = str(self.tmp)
        for path in (f"{tmp}/jobs/{J}/gates/t.json", f"{tmp}\\jobs\\{J}\\state.json", f"./jobs/../jobs/{J}/state.json",
                     f"JOBS/{J.upper()}/STATE.JSON", f"jobs/{J}/scripts/../state.json", ".lab/OPERATE"):
            self.assertBlocked(self.call("Write", file_path=path), path)

    def test_shell_spellings(self):
        gb, wsl = posix_forms(self.tmp)
        for cmd in (f"echo x > \"{self.tmp}/jobs/{J}/state.json\"", f"echo x > {gb}/jobs/{J}/state.json",
                    f"echo x > '{wsl}/jobs/{J}/state.json'", f"cd jobs/{J} && echo x > state.json",
                    f"cd jobs && cd {J} && rm state.json", f"echo x > ./jobs/./{J}/state.json",
                    f"python -c \"open('jobs/{J}/state.json','w').write('x')\"",
                    "node -e \"require('fs').writeFileSync('.lab/OPERATE','x')\"", f"echo x>jobs/{J}/state.json"):
            self.assertBlocked(self.sh(cmd), cmd)
        self.assertBlocked(self.sh(f"Set-Content -Path \".\\jobs\\{J}\\state.json\" -Value x", tool="PowerShell"))
        self.assertBlocked(self.sh(f"py -3 .\\engine\\gate.py approve {J}", tool="PowerShell"))
        self.assertBlocked(self.sh(f"\"{self.tmp}/engine/gate.py\" approve {J}"))
        self.assertBlocked(self.sh("git -C . push origin main"))


class NoWriteRootTests(HookBase):
    """(b) the generated ecosystems' folder and the source folders are never written from a session."""

    def test_ecosystems_folder(self):
        eco = self.outside / "ecosystems"
        self.assertBlocked(self.call("Write", file_path=str(eco / "probe/notes.md")))
        self.assertBlocked(self.call("Edit", file_path=str(eco / "probe/jobs/x/gates/t.json")))
        self.assertBlocked(self.sh(f"echo {{}} > \"{eco}/probe/jobs/x/gates/t.json\""))
        self.assertBlocked(self.sh(f"cp a.md \"{eco}/probe/\""))
        self.assertAllowed(self.sh(f"ls \"{eco}/probe\""))
        self.assertAllowed(self.call("Read", file_path=str(eco / "probe/CLAUDE.md")))

    def test_another_ecosystems_gate_file_anywhere(self):
        self.assertBlocked(self.sh("echo {} > /tmp/someplace/jobs/x/gates/t.json"))

    def test_source_folders(self):
        src = self.outside / "source-lab"
        self.assertBlocked(self.call("Write", file_path=str(src / "x.md")))
        self.assertBlocked(self.sh(f"rm -rf \"{src}/logs\""))
        self.assertAllowed(self.sh(f"git -C \"{src}\" log --oneline"))


class ScratchpadTests(HookBase):
    """Rec 3: only the harness's scratchpad_dir, and only outside the repo and the guarded roots."""

    def test_only_the_harness_field_counts(self):
        target = str(self.scratch / "x.txt")
        self.assertAllowed(self.call("Write", file_path=target))
        self.assertBlocked(self.call("Write", file_path=target, scratch=None))                  # no field
        self.assertBlocked(self.call("Write", file_path=target, scratch=str(self.outside / "other")))  # different folder

    def test_a_scratchpad_inside_a_guarded_root_is_ignored(self):
        for bad in (self.outside / "ecosystems" / "s", self.outside / "source-lab" / "s", self.outside):
            self.assertBlocked(self.call("Write", file_path=str(bad / "x.txt"), scratch=str(bad)), str(bad))
        ctx = self.hook.Ctx({"tool_name": "Write", "tool_input": {}, "scratchpad_dir": str(self.tmp / "scratch")})
        self.assertIsNone(ctx.scratch)                                   # inside the repo: never a scratchpad


class ReadBlockTests(HookBase):
    """(c) subagents: method lab, private/, docs/thin/, eval keys; operate-mode main session:
    method lab, private/ (plan read-only), eval keys; build-mode main session: full access."""

    BLOCKED_FOR_AGENTS = ("vendor/method-lab/CLAUDE.md", "private/plan/BUILD_PLAN.md", "docs/thin/answers.md",
                          "evals/critic/keys/k1.md", "evals/critic/cases/c1/calibration-key.md")

    def test_subagents(self):
        for path in self.BLOCKED_FOR_AGENTS:
            self.assertBlocked(self.call("Read", agent=True, file_path=path), path)
            self.assertBlocked(self.sh(f"cat {path}", agent=True), path)
        self.assertAllowed(self.call("Read", agent=True, file_path="engine/labcore.py"))
        self.assertBlocked(self.call("Grep", agent=True, pattern="x"))                       # whole repo
        self.assertBlocked(self.call("Grep", agent=True, pattern="x", path="vendor"))
        self.assertAllowed(self.call("Grep", agent=True, pattern="x", path="engine"))
        self.assertBlocked(self.sh("grep -r secret .", agent=True))
        self.assertAllowed(self.sh("grep -r secret engine", agent=True))
        self.assertBlocked(self.call("Write", agent=True, file_path="private/notes.md"))

    def test_main_session_in_build_mode_has_full_access(self):
        for path in self.BLOCKED_FOR_AGENTS:
            self.assertAllowed(self.call("Read", file_path=path), path)
        self.assertAllowed(self.call("Write", file_path="private/plan/build-log.md"))
        self.assertAllowed(self.call("Grep", pattern="x"))

    def test_main_session_in_operate_mode(self):
        self.operate()
        for path in ("vendor/method-lab/CLAUDE.md", "evals/critic/keys/k1.md", "private/comparisons/x.md"):
            self.assertBlocked(self.call("Read", file_path=path), path)
        self.assertAllowed(self.call("Read", file_path="private/plan/BUILD_PLAN.md"))         # read-only area
        self.assertBlocked(self.call("Write", file_path="private/plan/build-log.md"))
        self.assertBlocked(self.sh("echo x >> private/plan/build-log.md"))
        self.assertAllowed(self.sh("cat private/plan/primer.md"))
        self.assertAllowed(self.call("Read", file_path="docs/thin/answers.md"))              # subagents only

    def test_active_internal_job_folder_is_the_only_exception(self):
        lc = self.lc
        mine = lc.new_job("spec", "mine", "x", cls="internal")["job_id"]
        other = lc.new_job("spec", "other", "x", cls="internal")["job_id"]
        lc.set_active(mine)
        self.assertAllowed(self.call("Read", agent=True, file_path=f"private/jobs/{mine}/brief.md"))
        self.assertAllowed(self.call("Write", agent=True, file_path=f"private/jobs/{mine}/drafts/v1.md"))
        self.assertBlocked(self.call("Write", agent=True, file_path=f"private/jobs/{mine}/state.json"))  # still protected
        self.assertBlocked(self.call("Read", agent=True, file_path=f"private/jobs/{other}/brief.md"))
        self.assertBlocked(self.call("Read", agent=True, file_path="private/plan/primer.md"))
        pub = lc.new_job("spec", "pubjob", "x", cls="public")["job_id"]
        lc.set_active(pub)                                                                   # exception only for internal jobs
        self.assertBlocked(self.call("Read", agent=True, file_path=f"private/jobs/{mine}/brief.md"))

    def test_secret_files_blocked_for_every_read_tool(self):
        for tool, ti in (("Read", {"file_path": ".env"}), ("Read", {"file_path": "config/.env.local"}),
                         ("Grep", {"pattern": "KEY", "path": ".env"}), ("Read", {"file_path": "keys/master.key"})):
            self.assertBlocked(self.call(tool, **ti), str(ti))
        self.assertAllowed(self.call("Read", file_path=".venv/pyvenv.cfg"))


class BlockLogTests(HookBase):
    """Rec 4: blocks that touch private/ or happen while an internal job is active are logged under private/logs/."""

    def logs(self):
        read = lambda p: (self.tmp / p).read_text(encoding="utf-8") if (self.tmp / p).exists() else ""
        return read("logs/blocked.jsonl"), read("private/logs/blocked.jsonl")

    def test_private_routing(self):
        self.call("Read", agent=True, file_path="private/plan/secret-plan.md")
        public, private = self.logs()
        self.assertNotIn("secret-plan", public)
        self.assertIn("secret-plan", private)
        self.sh("cat .env")
        public, _ = self.logs()
        self.assertIn(".env", public)

    def test_internal_job_active(self):
        lc = self.lc
        j = lc.new_job("spec", "intjob", "x", cls="internal")["job_id"]
        lc.set_active(j)
        self.sh("git push origin INTERNAL-MARKER")
        public, private = self.logs()
        self.assertNotIn("INTERNAL-MARKER", public)
        self.assertIn("INTERNAL-MARKER", private)


class LauncherTests(LabTestBase):
    """(e) the launcher turns any failure of the real hook into a block."""

    def launch(self, payload):
        p = subprocess.run([sys.executable, str(self.tmp / "engine/hooks/pre_tool_use_launcher.py")],
                           input=payload, capture_output=True, text=True, env=self.hook_env())
        return p.returncode, p.stderr

    def harmless(self):
        return json.dumps({"tool_name": "Read", "tool_input": {"file_path": "engine/labcore.py"}})

    def test_healthy_hook(self):
        self.assertEqual(self.launch(self.harmless())[0], 0)
        self.assertEqual(self.launch(json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat .env"}}))[0], 2)
        self.assertEqual(self.launch("not json")[0], 2)

    def corrupt(self, text):
        (self.tmp / "engine/hooks/pre_tool_use.py").write_text(text, encoding="utf-8")
        code, err = self.launch(self.harmless())
        self.assertEqual(code, 2, err)
        self.assertIn("failing closed", err)

    def test_syntax_error_blocks(self):
        self.corrupt("def run(raw:\n    return 0\n")

    def test_import_error_blocks(self):
        self.corrupt("import module_that_does_not_exist\ndef run(raw):\n    return 0\n")

    def test_crash_blocks(self):
        self.corrupt("def run(raw):\n    raise RuntimeError('boom')\n")

    def test_missing_run_or_bad_return_blocks(self):
        self.corrupt("x = 1\n")
        (self.tmp / "engine/hooks/pre_tool_use.py").write_text("def run(raw):\n    return 1\n", encoding="utf-8")
        self.assertEqual(self.launch(self.harmless())[0], 2)

    def test_launcher_is_pinned(self):
        digest = hashlib.sha256((REPO / "engine/hooks/pre_tool_use_launcher.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        self.assertEqual(digest, LAUNCHER_SHA256, "the launcher changed: it must never be edited")


class BackgroundAgentTests(HookBase):
    """T0.12 drill 11 follow-up (rule 7): while a job is active, subagent calls must say they run in
    the foreground, because a background call returns before the usage is known."""

    def agent(self, tool="Agent", **ti):
        return self.call(tool, description="x", subagent_type="Explore", prompt="JOB: x", **ti)

    def test_no_active_job_leaves_subagent_calls_alone(self):
        self.assertAllowed(self.agent())
        self.assertAllowed(self.agent(run_in_background=True))

    def test_active_job_needs_an_explicit_foreground_call(self):
        j = self.lc.new_job("spec", "bgjob", "x")["job_id"]
        self.lc.set_active(j)
        for tool in ("Agent", "Task"):
            self.assertBlocked(self.agent(tool), f"{tool}: not said, so the app may run it in the background")
            self.assertBlocked(self.agent(tool, run_in_background=True), tool)
            self.assertBlocked(self.agent(tool, run_in_background="false"), f"{tool}: only a real false counts")
            self.assertAllowed(self.agent(tool, run_in_background=False), tool)
        log = (self.tmp / "logs/blocked.jsonl").read_text(encoding="utf-8")
        self.assertIn("run_in_background", log)
        self.assertIn(j, log)

    def test_paused_jobs_are_still_active_and_finished_ones_are_not(self):
        lc = self.lc
        j = lc.new_job("spec", "pausejob", "x")["job_id"]
        lc.set_active(j)
        lc.apply(j, "escalate")
        self.assertBlocked(self.agent(), "ESCALATED is not finished")
        lc.apply(j, "cancel")
        self.assertAllowed(self.agent(), "CANCELLED")

    def test_an_unreadable_active_job_counts_as_active(self):
        (self.tmp / ".lab").mkdir(exist_ok=True)
        (self.tmp / ".lab/active_job").write_text("20260101-spec-gone", encoding="utf-8")
        self.assertBlocked(self.agent())
        self.assertAllowed(self.agent(run_in_background=False))

    def test_other_tools_are_unaffected_by_an_active_job(self):
        j = self.lc.new_job("spec", "otherjob", "x")["job_id"]
        self.lc.set_active(j)
        self.assertAllowed(self.sh("ls"))
        self.assertAllowed(self.call("Read", file_path="README.md"))


class T07FollowupTests(HookBase):
    """Samith's changes after T0.7: role-limited MCP entries, a stricter read-only list, and
    inline code that deletes files."""

    def test_app_tools_for_the_main_session_only(self):
        self.dump("config/gated-actions.json", {"mcp": [
            {"tool": "mcp__ccd_turn__update_plan", "roles": ["main"]},
            {"tool": "mcp__ccd_turn__wrap_up", "roles": ["main"]}], "shell": []})
        for tool in ("mcp__ccd_turn__update_plan", "mcp__ccd_turn__wrap_up"):
            self.assertAllowed(self.call(tool, items=[]), tool)
            self.assertBlocked(self.call(tool, agent=True, items=[]), tool + " from a subagent")
        self.assertBlocked(self.call("mcp__ccd_turn__something_else"))                   # exact names only
        self.assertBlocked(self.call("mcp__ccd_session__start_session"))

    def test_shipped_config_lists_the_app_tools_by_exact_name(self):
        cfg = json.loads((REPO / "config/gated-actions.json").read_text(encoding="utf-8"))
        for e in cfg["mcp"]:
            self.assertNotIn("*", e["tool"], e)
            self.assertEqual(e.get("roles"), ["main"], e)

    def test_read_only_commands_with_writing_or_program_running_options(self):
        p = f"jobs/{J}/state.json"
        for cmd in (f"sort -o {p} {p}", f"sort --output={p} {p}", f"uniq {p} {p}.bak", f"git grep -O state -- {p}",
                    f"git grep --open-files-in-pager=vi state -- {p}", f"git log --output={p}", f"git diff --output {p}",
                    f"git show --ext-diff HEAD -- {p}", f"git diff --textconv -- {p}", f"git -c core.pager=x log -- {p}",
                    f"git --config-env=core.pager=X log -- {p}"):
            self.assertBlocked(self.sh(cmd), cmd)
        for cmd in (f"sort {p}", f"uniq {p}", f"git grep state -- {p}", f"git log -- {p}"):
            self.assertAllowed(self.sh(cmd), cmd)

    def test_inline_code_that_deletes_is_blocked_whatever_it_names(self):
        for cmd in ("python -c \"import shutil; shutil.rmtree('build')\"", "python3 -c \"import os; os.remove('a.txt')\"",
                    "python -c \"from pathlib import Path; Path('x').unlink()\"", "python -c \"import os; os.rmdir('d')\"",
                    "python - <<'EOF'\nimport shutil\nshutil.rmtree('.')\nEOF", "ruby -e \"FileUtils.rm_rf('tmp')\"",
                    "node -e \"require('fs').rmSync('x', {recursive: true})\"", "node -e \"require('fs').unlinkSync('a')\""):
            self.assertBlocked(self.sh(cmd), cmd)
        for cmd in ("Get-ChildItem x | ForEach-Object { Remove-Item $_ }", "& { Remove-Item notes.md }",
                    "powershell -Command \"Remove-Item scratch.txt\""):
            self.assertBlocked(self.sh(cmd, tool="PowerShell"), cmd)
        self.assertAllowed(self.sh("python -c \"print(sum([1, 2]))\""))
        self.assertAllowed(self.sh("python engine/state.py event x needs_input --note \"remove the old section\""))


class SettingsRegistrationTests(unittest.TestCase):
    """(f) ported from the earlier lab: the project settings register the launcher, fail-closed."""

    def test_settings_register_the_launcher_fail_closed(self):
        s = json.loads((REPO / ".claude/settings.json").read_text(encoding="utf-8"))
        entries = s["hooks"]["PreToolUse"]
        self.assertEqual([e["matcher"] for e in entries], ["*"])
        h = entries[0]["hooks"][0]
        self.assertEqual((h["type"], h.get("onFailure")), ("command", "block"))
        self.assertIn("args", h)                                         # exec form: no shell
        self.assertTrue(h["args"][-1].endswith("engine/hooks/pre_tool_use_launcher.py"), h["args"])
        self.assertTrue(shutil.which(h["command"]), f"{h['command']} must be a real executable on PATH")


if __name__ == "__main__":
    unittest.main()
