"""T0.11: the approval chain. A token records what its artifact was built from (upstream approvals by
approved content, cited approved artifacts, the inputs present at approval); any edit anywhere voids
it and blocks the next stage, approval, delivery, completion, gated actions and [G:] citations.
Identical re-approvals don't break children; gate.py relink re-points a stopped child."""
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import REPO, LabTestBase, force_rmtree

CHAIN_ROUTES = {
    "top": {"stages": [{"agent": "author"}], "reviews": [{"agent": "critic", "kind": "critic"}],
            "revise_with": "author", "gate": "G0-top"},
    "mid": {"stages": [{"agent": "author"}], "reviews": [{"agent": "critic", "kind": "critic"}],
            "revise_with": "author", "gate": "G1-mid", "requires_parent_gate": "G0-top"},
    "low": {"stages": [{"agent": "author"}], "reviews": [{"agent": "critic", "kind": "critic"}],
            "revise_with": "author", "gate": "G2-low", "deliver": "publisher", "requires_parent_gate": "G1-mid"},
}


class ChainBase(LabTestBase):
    def setUp(self):
        super().setUp()
        routes = json.loads((self.tmp / "config/routes.json").read_text())
        routes["routes"].update(CHAIN_ROUTES)
        self.dump("config/routes.json", routes)

    def approved(self, jtype, slug, text, parent=None, approve=True):
        lc = self.lc
        j = lc.new_job(jtype, slug, "x", parent=parent)["job_id"]
        lc.apply(j, "dispatch")
        lc.apply(j, "artifact_ready", artifact=self.write(f"jobs/{j}/drafts/v1.md", text))
        lc.apply(j, "review_pass")
        if approve:
            lc.approve_gate(j)
        return j

    def chain3(self):
        top = self.approved("top", "toppy", "top v1\n")
        mid = self.approved("mid", "middy", "mid v1\n", parent=top)
        low = self.approved("low", "lowly", "low v1\n", parent=mid)
        return top, mid, low

    def edit(self, job, text="edited\n"):
        f = self.tmp / self.lc.load_state(job)["artifact_path"]
        f.write_text(f.read_text() + text)

    def broken(self, job, gate):
        ok, chain = self.lc.verify_chain(job, gate)
        return ok, [c for c in chain if c["status"] != "ok"]


class ChainBasicsTests(ChainBase):
    def test_token_records_what_it_was_built_from(self):
        top, mid, low = self.chain3()
        tok = json.loads((self.tmp / f"jobs/{low}/gates/G2-low.json").read_text())
        link = tok["built_from"]["links"][0]
        self.assertEqual((link["kind"], link["job"], link["gate"]), ("parent", mid, "G1-mid"))
        self.assertEqual(link["artifact_sha256"], self.lc.sha256_path(f"jobs/{mid}/drafts/v1.md"))
        self.assertTrue(self.lc.verify_chain(low, "G2-low")[0])

    def test_edit_after_approval_refuses_the_next_stage(self):
        top = self.approved("top", "toppy", "top v1\n")
        self.edit(top)
        with self.assertRaises(self.lc.LabError) as cm:
            self.lc.new_job("mid", "middy", "x", parent=top)
        self.assertIn("artifact changed after approval", str(cm.exception))

    def test_edit_to_a_parent_voids_the_child_and_verify_chain_names_the_link(self):
        top, mid, low = self.chain3()
        self.edit(top)
        ok, bad = self.broken(low, "G2-low")
        self.assertFalse(ok)
        self.assertEqual([(b["job"], b["kind"]) for b in bad], [(top, "parent")])
        p = subprocess.run([sys.executable, str(self.tmp / "engine/gate.py"), "verify", low, "G2-low", "--chain"],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 1)
        self.assertIn("chain BROKEN", p.stdout)
        self.assertIn("artifact changed after approval", p.stdout)

    def test_a_break_at_each_level_of_a_three_level_chain(self):
        for level in range(3):
            with self.subTest(level=level):
                jobs = self.chain3()
                self.edit(jobs[level])
                self.assertFalse(self.lc.verify_chain(jobs[2], "G2-low")[0])
                for upper in jobs[:level]:
                    self.assertTrue(self.lc.verify_chain(upper, None)[0])           # nothing above the break is void

    def test_delivery_is_blocked_by_an_upstream_edit(self):
        top, mid, low = self.chain3()
        self.edit(mid)
        with self.assertRaises(self.lc.LabError) as cm:
            self.lc.apply(low, "deliver")
        self.assertIn("delivery refused", str(cm.exception))

    def test_completion_and_approval_check_the_chain(self):
        top = self.approved("top", "toppy", "top v1\n")
        mid = self.approved("mid", "middy", "mid v1\n", parent=top, approve=False)
        self.edit(top)
        with self.assertRaises(self.lc.LabError):
            self.lc.approve_gate(mid)                                                # built on a broken parent
        self.assertFalse((self.tmp / f"jobs/{mid}/gates/G1-mid.json").exists())

    def test_gated_action_uses_the_chain(self):
        top, mid, low = self.chain3()
        self.dump("config/gated-actions.json", {"mcp": [{"tool": "mcp__out__send", "gate": "G2-low"}], "shell": []})
        self.lc.set_active(low)
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        try:
            h = importlib.import_module("pre_tool_use")
        finally:
            sys.path.remove(str(self.tmp / "engine/hooks"))
        call = lambda: h.run(json.dumps({"tool_name": "mcp__out__send", "tool_input": {}, "cwd": str(self.tmp)}))
        self.assertEqual(call(), 0)
        self.edit(top)
        self.assertEqual(call(), 2)


class ReapprovalAndRelinkTests(ChainBase):
    def reapprove(self, job, text):
        """A new approved version of an approved job. The engine has no path from APPROVED back to GATE
        yet (new versions of approved work arrive with change jobs, T4.5), so the test puts the job back
        at GATE with a new version the way a change job will, then approves it through the engine."""
        lc = self.lc
        n = len(list((self.tmp / f"jobs/{job}/drafts").glob("*.md"))) + 1
        art = self.write(f"jobs/{job}/drafts/v{n}.md", text)
        f = self.tmp / f"jobs/{job}/state.json"
        st = json.loads(f.read_text())
        st.update(state="GATE", artifact_path=art, stage=None, stage_kind=None)
        f.write_text(json.dumps(st))
        lc.approve_gate(job)

    def test_identical_reapproval_does_not_break_children(self):
        top, mid, low = self.chain3()
        self.reapprove(mid, "mid v1\n")                                              # same content, new version
        self.assertTrue(self.lc.verify_chain(low, "G2-low")[0])

    def test_different_reapproval_stops_the_child_and_relink_sends_it_back(self):
        lc = self.lc
        top = self.approved("top", "toppy", "top v1\n")
        mid = self.approved("mid", "middy", "mid v1\n", parent=top, approve=False)    # at GATE
        self.reapprove(top, "top v2 with new content\n")
        with self.assertRaises(lc.LabError) as cm:
            lc.approve_gate(mid)
        self.assertIn("relink", str(cm.exception))
        p = subprocess.run([sys.executable, str(self.tmp / "engine/gate.py"), "relink", mid], capture_output=True,
                           text=True, env=self.hook_env(), stdin=subprocess.DEVNULL)
        self.assertEqual(p.returncode, 1)                                            # no terminal: refused
        with self.assertRaises(lc.LabError):
            lc.apply(mid, "relink")                                                  # human-only
        g = importlib.import_module("gate")
        g.confirm = lambda word: None
        self.assertEqual(g.main(["relink", mid]), 0)
        st = lc.load_state(mid)
        self.assertEqual((st["state"], st["stage"]), ("REVIEW", "critic"))          # back to its first review
        self.assertEqual(st["parent_link"]["artifact_sha256"], lc.sha256_path(f"jobs/{top}/drafts/v2.md"))
        audit = [json.loads(l) for l in (self.tmp / "logs/gate-audit.jsonl").read_text().splitlines()]
        self.assertEqual(audit[-1]["action"], "relink")
        lc.apply(mid, "review_pass")
        lc.approve_gate(mid)
        self.assertTrue(lc.verify_chain(mid, "G1-mid")[0])

    def test_relink_voids_an_existing_child_approval(self):
        lc = self.lc
        top, mid, low = self.chain3()
        self.reapprove(top, "top v2 changed\n")
        self.assertFalse(lc.verify_chain(mid, "G1-mid")[0])
        lc.relink(mid)
        self.assertFalse((self.tmp / f"jobs/{mid}/gates/G1-mid.json").exists())
        self.assertTrue((self.tmp / f"jobs/{mid}/gates/G1-mid.void-1.json").exists())
        self.assertEqual(lc.load_state(mid)["state"], "REVIEW")


class InputAndCitationTests(ChainBase):
    def test_inputs_present_at_approval_are_bound(self):
        lc = self.lc
        top = lc.new_job("top", "inputs", "x")["job_id"]
        _, a1 = lc.record_input(top, "-", "synthetic", data=b"answer one\n")
        _, a2 = lc.record_input(top, "-", "synthetic", data=b"answer two\n")
        lc.apply(top, "dispatch")
        lc.apply(top, "artifact_ready", artifact=self.write(f"jobs/{top}/drafts/v1.md", "v1\n"))
        lc.apply(top, "review_pass"); lc.approve_gate(top)
        lc.record_input(top, "-", "synthetic", data=b"a later answer\n")             # adding one: still valid
        self.assertTrue(lc.verify_chain(top, "G0-top")[0])
        (self.tmp / a1["path"]).write_bytes(b"answer one, changed\n")                # editing one voids
        ok, bad = self.broken(top, "G0-top")
        self.assertEqual([b["kind"] for b in bad], ["input A01"])
        (self.tmp / a1["path"]).write_bytes(b"answer one\n")
        self.assertTrue(lc.verify_chain(top, "G0-top")[0])
        (self.tmp / a2["path"]).unlink()                                             # deleting one voids
        ok, bad = self.broken(top, "G0-top")
        self.assertEqual([b["status"] for b in bad], ["token void: recorded input missing"])

    def test_cited_approved_artifact_valid_only_while_its_chain_holds(self):
        lc = self.lc
        top = self.approved("top", "toppy", "top v1\n")
        mid = self.approved("mid", "middy", "mid v1\n", parent=top)
        ev = importlib.import_module("evidence")
        art = self.write("jobs/probe.md", f"As agreed in [G:{mid}].\n")
        self.assertEqual(ev.check(lc.load_state(mid)["job_id"], art)[0], [])
        self.edit(top)                                                               # upstream of the cited job
        problems = ev.check(mid, art)[0]
        self.assertEqual([p["rule"] for p in problems], ["E04"])
        self.assertIn("not an approved artifact", problems[0]["issue"])

    def test_a_citing_job_binds_the_cited_approval(self):
        lc = self.lc
        cited = self.approved("top", "cited", "cited v1\n")
        j = self.approved("top", "citer", f"Builds on [G:{cited}].\n")
        tok = json.loads((self.tmp / f"jobs/{j}/gates/G0-top.json").read_text())
        self.assertEqual([(l["kind"], l["job"]) for l in tok["built_from"]["links"]], [("cited", cited)])
        self.edit(cited)
        self.assertFalse(lc.verify_chain(j, "G0-top")[0])


class RobustnessTests(ChainBase):
    def test_cycles_are_broken(self):
        lc = self.lc
        a = self.approved("top", "aaa", "a\n")
        b = self.approved("top", "bbb", "b\n")
        for x, y in ((a, b), (b, a)):                                                # forge a loop between two tokens
            f = self.tmp / f"jobs/{x}/gates/G0-top.json"
            tok = json.loads(f.read_text())
            tok["built_from"]["links"] = [{"job": y, "gate": "G0-top", "kind": "parent",
                                           "artifact_sha256": lc.sha256_path(f"jobs/{y}/drafts/v1.md")}]
            f.write_text(json.dumps(tok))
        ok, bad = self.broken(a, "G0-top")
        self.assertFalse(ok)
        self.assertIn("cycle", bad[0]["status"])

    def test_depth_is_capped(self):
        self.lc.CHAIN_MAX_DEPTH = 1
        top, mid, low = self.chain3()
        ok, bad = self.broken(low, "G2-low")
        self.assertFalse(ok)
        self.assertIn("deeper than 1", bad[0]["status"])

    def test_folder_hashing_is_deterministic(self):
        lc = self.lc
        for name, order in (("one", ("b.txt", "a.txt", "sub/c.txt")), ("two", ("sub/c.txt", "a.txt", "b.txt"))):
            for f in order:
                self.write(f"jobs/x/{name}/{f}", f"content of {f}\n")
        self.assertEqual(lc.sha256_path("jobs/x/one"), lc.sha256_path("jobs/x/two"))
        (self.tmp / "jobs/x/two/a.txt").rename(self.tmp / "jobs/x/two/z.txt")
        self.assertNotEqual(lc.sha256_path("jobs/x/one"), lc.sha256_path("jobs/x/two"))

    def test_gate_show_lists_what_approval_would_bind(self):
        top = self.approved("top", "toppy", "top v1\n")
        mid = self.approved("mid", "middy", "mid v1\n", parent=top, approve=False)
        p = subprocess.run([sys.executable, str(self.tmp / "engine/gate.py"), "show", mid],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertIn(f"Built from: parent {top}/G0-top  approved content {self.lc.sha256_path(f'jobs/{top}/drafts/v1.md')}",
                      p.stdout)


@unittest.skipUnless(shutil.which("git"), "git not available")
class LineEndingTests(ChainBase):
    """A token stays valid after a commit and a fresh checkout with core.autocrlf=true."""

    def clone_and_verify(self, with_attributes):
        lc = self.lc
        shutil.copy2(REPO / ".gitignore", self.tmp / ".gitignore")
        if with_attributes:
            shutil.copy2(REPO / ".gitattributes", self.tmp / ".gitattributes")
        git = lambda cwd, *a: subprocess.run(["git", "-C", str(cwd), "-c", "core.autocrlf=true", *a],
                                             capture_output=True, text=True)
        git(self.tmp, "init", "-q")
        top = lc.new_job("top", "eol", "x")["job_id"]
        lc.apply(top, "dispatch")
        art = self.tmp / f"jobs/{top}/drafts/v1.md"
        art.write_bytes(b"line one\nline two\nline three\n")                         # LF bytes (write_text would give CRLF)
        lc.apply(top, "artifact_ready", artifact=f"jobs/{top}/drafts/v1.md")
        lc.apply(top, "review_pass"); lc.approve_gate(top)
        agent = self.tmp / ".claude/agents/probe-writer.md"                          # agent files are hashed from T0.13
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_bytes(b"---\nname: probe-writer\ntools: Read\n---\nWrite one line.\n")
        git(self.tmp, "add", "-A")
        git(self.tmp, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "x")
        dest = Path(tempfile.mkdtemp()) / "clone"
        try:
            subprocess.run(["git", "-c", "core.autocrlf=true", "clone", "-q", str(self.tmp), str(dest)],
                           check=True, capture_output=True)
            env = {**self.hook_env(), "LAB_ROOT": str(dest)}
            p = subprocess.run([sys.executable, str(dest / "engine/gate.py"), "verify", top, "G0-top", "--chain"],
                               capture_output=True, text=True, env=env)
            crlf = b"\r\n" in (dest / f"jobs/{top}/drafts/v1.md").read_bytes()
            agent_same = (dest / ".claude/agents/probe-writer.md").read_bytes() == agent.read_bytes()
            return p.returncode, crlf, agent_same
        finally:
            force_rmtree(dest.parent)

    def test_token_survives_a_fresh_checkout(self):
        code, crlf, agent_same = self.clone_and_verify(with_attributes=True)
        self.assertEqual((code, crlf, agent_same), (0, False, True))

    def test_control_without_attributes_the_checkout_converts_and_voids(self):
        code, crlf, agent_same = self.clone_and_verify(with_attributes=False)
        self.assertEqual((code, crlf, agent_same), (1, True, False))                 # proves the test bites


if __name__ == "__main__":
    unittest.main()
