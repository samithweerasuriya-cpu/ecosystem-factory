"""Shared test setup: every test runs against a temporary copy of the repo (LAB_ROOT),
so nothing in the real jobs/, logs/ or .lab/ is touched."""
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
MIN_TEST_SLUG = 3

PY_CHECK = "import pathlib,sys; sys.exit(0 if pathlib.Path(sys.argv[1], 'ok').exists() else 1)"
PY_PACKAGE = "import pathlib,sys; pathlib.Path(sys.argv[1], 'delivery', 'pkg.txt').write_text('pkg')"

TEST_ROUTES = {
    "_doc": "test routes",
    "routes": {
        "spec": {"stages": [{"agent": "researcher"}, {"agent": "writer"}],
                 "reviews": [{"agent": "critic", "kind": "critic"}, {"agent": "verifier", "kind": "verifier"}],
                 "revise_with": "writer", "gate": "G1-spec", "deliver": None},
        "tickets": {"stages": [{"agent": "ticketer"}],
                    "reviews": [{"agent": "verifier", "kind": "verifier"}],
                    "revise_with": "ticketer", "gate": "G3-publish", "deliver": "ticketer",
                    "requires_parent_gate": "G1-spec"},
        "report": {"stages": [{"agent": "researcher"}, {"agent": "reporter"}],
                   "reviews": [{"agent": "verifier", "kind": "verifier"}],
                   "revise_with": "reporter", "gate": None, "deliver": None},
        "build": {"stages": [{"agent": "builder"}, {"script": "check"}, {"agent": "summariser"}],
                  "reviews": [{"agent": "critic", "kind": "critic"}],
                  "revise_with": "summariser", "fix_with": "builder", "gate": "G2-build"},
        "slowbuild": {"stages": [{"agent": "builder"}, {"script": "slow"}, {"agent": "summariser"}],
                      "reviews": [{"agent": "critic", "kind": "critic"}],
                      "revise_with": "summariser", "fix_with": "builder", "gate": None},
        "package": {"stages": [{"agent": "builder"}, {"script": "package"}],
                    "reviews": [{"agent": "critic", "kind": "critic"}],
                    "revise_with": "builder", "fix_with": "builder", "gate": None},
        "survey": {"stages": [{"agent": "planner"}, {"fanout": {"agent": "researcher", "max": 3, "split_by": "group"}},
                              {"agent": "merger"}],
                   "reviews": [{"agent": "critic", "kind": "critic"}],
                   "revise_with": "merger", "gate": None},
    },
}

TEST_SCRIPTS = {"scripts": {
    "check": {"argv": ["{python}", "-c", PY_CHECK, "{job_dir}"], "timeout": 30},
    "slow": {"argv": ["{python}", "-c", "import time; time.sleep(10)"], "timeout": 1},
    "package": {"argv": ["{python}", "-c", PY_PACKAGE, "{job_dir}"], "timeout": 30,
                "artifact": "{job_path}/delivery/pkg.txt"},
}}

TEST_GATED = {
    "mcp": [
        {"tool": "mcp__docs__search*"},
        {"tool": "mcp__tracker__save_*", "job_types": ["tickets"], "states": ["DELIVERING"], "gate": "G3-publish"},
    ],
    "shell": [
        {"pattern": r"\bdeploytool\s+push\b", "gate": "G2-build", "reason": "deploytool push needs G2-build"},
    ],
}

TEST_RULEBOOK = """# Test rulebook

| ID | Rule | Sev | Applies |
|---|---|---|---|
| TR01 | Ownership is stated correctly. | blocker | all |
| TR15 | Gaps are listed. | minor | all |
| TR16 | Limits are stated. | major | all |
| TR17 | Effects are explained. | minor | all |
| TR20 | Wording is concise. | minor | all |
| AB06 | Two-letter prefixes parse. | blocker | all |
| XYZ101 | Three-digit numbers parse. | major | all |
"""

TEST_REVIEWERS = {"reviewers": {"critic": {"rulebook": "rules/test-rulebook.md"},
                                "verifier": {"rulebook": "rules/test-rulebook.md"}}}


def force_rmtree(path):
    # Windows: copytree carries the read-only attribute, and read-only dirs cannot be removed.
    def force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))


class LabTestBase(unittest.TestCase):
    auto_result = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for d in ("engine", "config", "schemas", "rules", "evals"):
            # machine-specific *.local.json never enters a test copy: tests must not depend on this machine
            if (REPO / d).is_dir():
                shutil.copytree(REPO / d, self.tmp / d, ignore=shutil.ignore_patterns("__pycache__", "tests", "*.local.json",
                                                                                     "reports"))
        # The factory config the tests assume (caps, gates, the demo route, publish settings), frozen as a fixture,
        # so the engine's tests behave the same in the factory and in every generated ecosystem (T1.3).
        shutil.copytree(FIX / "factory", self.tmp, dirs_exist_ok=True)
        (self.tmp / "jobs").mkdir()
        self.dump("config/routes.json", TEST_ROUTES)
        self.dump("config/scripts.json", TEST_SCRIPTS)
        self.dump("config/gated-actions.json", TEST_GATED)
        self.dump("config/reviewers.json", TEST_REVIEWERS)
        self.write("rules/test-rulebook.md", TEST_RULEBOOK)
        self._env = {k: os.environ.get(k) for k in ("LAB_ROOT", "CLAUDE_PROJECT_DIR")}
        os.environ["LAB_ROOT"] = str(self.tmp)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        sys.path.insert(0, str(self.tmp / "engine"))
        # Every engine, hook and evals module is reloaded from this test's copy. Lesson (T0.9, T0.13, T0.16):
        # a hand-kept list missed each new module in turn, which then kept a deleted test folder.
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", None) or ""
            if Path(f).parent.name in ("engine", "hooks", "evals") and "tests" not in Path(f).parts:
                sys.modules.pop(name, None)
        self.lc = importlib.import_module("labcore")
        self.assertEqual(self.lc.ROOT, self.tmp)  # never the real repo
        engine_new_job = self.lc.new_job

        def new_job(jtype, slug, *args, **kwargs):
            # Lesson (T0.5, T0.6): one-letter slugs twice produced confusing engine errors in tests.
            if len(slug) < MIN_TEST_SLUG:
                raise AssertionError(f"test helper: slug {slug!r} is too short; tests use at least "
                                     f"{MIN_TEST_SLUG} characters (the engine needs 2)")
            return engine_new_job(jtype, slug, *args, **kwargs)
        self.lc.new_job = new_job

        # T0.8: a call stays open until its result is recorded (in a session, the post hook does it).
        # Tests about other behaviour get that result straight away; usage tests set auto_result = False.
        self.raw_record_call = self.lc.record_call

        def record_call(job_id, agent, item=None):
            st = self.raw_record_call(job_id, agent, item=item)
            if self.auto_result:
                call = st["calls"][-1]
                if call.get("status") == "open":
                    st, _ = self.lc.record_result(job_id, call["id"], "done", usage=None, source="test")
            return st
        self.lc.record_call = record_call

    def tearDown(self):
        while str(self.tmp / "engine") in sys.path:  # labcore also inserts its own folder
            sys.path.remove(str(self.tmp / "engine"))
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        force_rmtree(self.tmp)

    def write(self, relpath, text="x"):
        p = self.tmp / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return relpath

    def dump(self, relpath, data):
        return self.write(relpath, json.dumps(data, indent=2))

    def hook_env(self):
        env = {**os.environ, "LAB_ROOT": str(self.tmp)}
        env.pop("CLAUDE_PROJECT_DIR", None)
        return env

    def run_hook(self, payload, raw=None):
        p = subprocess.run([sys.executable, str(self.tmp / "engine/hooks/pre_tool_use.py")],
                           input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, env=self.hook_env())
        return p.returncode

    def spec_to_gate(self):
        lc = self.lc
        j = lc.new_job("spec", "sample", "Sample spec")["job_id"]
        lc.apply(j, "dispatch")
        lc.apply(j, "stage_done")
        art = self.write(f"jobs/{j}/drafts/v1.md", "draft v1")
        lc.apply(j, "artifact_ready", artifact=art)
        lc.apply(j, "review_pass")
        lc.apply(j, "review_pass")
        return j, art
