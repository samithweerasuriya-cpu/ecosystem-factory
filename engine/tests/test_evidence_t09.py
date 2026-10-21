"""T0.9: the evidence module. Pages are fetched and stored by script (text in an untracked cache,
metadata and short quotes in tracked files); claims are checked against the stored copies before any
reviewer runs (E01-E06); the fetch script is the only writer of the store. A small local web server
stands in for the internet, allowed only through the test config."""
import http.server
import importlib
import json
import shutil
import subprocess
import sys
import threading
import time
import unittest

from support import REPO, LabTestBase

FACT = "The widget limit is 42 items per order for standard accounts."
PAGE = ("<html><head><title>Widget limits</title></head><body><h1>Limits</h1><p>" + FACT + "</p>"
        "<p>PAGE-ONLY-MARKER: this paragraph is third-party text that must never reach a tracked file.</p>"
        + "<p>" + "Background text about widgets and orders. " * 15 + "</p></body></html>")
JS_PAGE = ("<html><body><div id='app'></div><noscript>Please enable JavaScript to view this site.</noscript>"
           "<script>render()</script></body></html>")


class _Handler(http.server.BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        r = self.routes.get(self.path)
        if r is None and self.path.startswith("/hop/"):
            n = int(self.path.rsplit("/", 1)[1])
            self.send_response(302)
            self.send_header("Location", f"/hop/{n + 1}" if n < 9 else "/page")
            self.end_headers()
            return
        if r is None:
            self.send_response(404); self.end_headers(); return
        ctype, body = r
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def log_message(self, *a):
        pass


class EvidenceBase(LabTestBase):
    auto_result = False

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        super().setUp()
        _Handler.routes = {"/page": ("text/html", PAGE), "/js": ("text/html", JS_PAGE),
                           "/notes.txt": ("text/plain", "Plain notes. " + FACT), "/doc.pdf": ("application/pdf", b"%PDF-1.4 fake")}
        self.set_evidence(domains={"127.0.0.1": 2}, allow_private_hosts=True, polite_pause_s=0.0)
        self.ev = importlib.import_module("evidence")

    def set_evidence(self, **kw):
        cfg = json.loads((self.tmp / "config/evidence.json").read_text())
        cfg.update(kw)
        self.dump("config/evidence.json", cfg)

    def set_caps(self, **kw):
        caps = json.loads((self.tmp / "config/caps.json").read_text())
        caps.update(kw)
        self.dump("config/caps.json", caps)

    def writer_job(self, slug="evidence", cls="synthetic"):
        """A spec job at its writing stage, with an open writer call and its handoff id."""
        lc = self.lc
        j = lc.new_job("spec", slug, "x", cls=cls)["job_id"]
        lc.apply(j, "dispatch")
        lc.handoff(j); c = lc.record_call(j, "researcher")["calls"][-1]
        lc.record_result(j, c["id"], "done")
        lc.apply(j, "stage_done")
        _, text = lc.handoff(j)
        hid = text.split("HANDOFF: ")[1].split()[0]
        lc.record_call(j, "writer")
        return j, hid

    def fetch(self, j, hid, path="/page"):
        return self.ev.fetch(j, self.base + path, hid)

    def ready(self, j, text, version="v1"):
        lc = self.lc
        call = next(c for c in lc.load_state(j)["calls"] if c["status"] == "open")
        lc.record_result(j, call["id"], "done")
        return lc.apply(j, "artifact_ready", artifact=self.write(f"{lc.rel(lc.job_dir(j))}/drafts/{version}.md", text))

    def findings(self, j):
        d = self.lc.job_dir(j) / "reviews"
        f = sorted(d.glob("check-evidence-*.json"))[-1]
        return [x["rule"] for x in json.loads(f.read_text())["findings"]]


class FetchTests(EvidenceBase):
    def test_page_text_goes_to_the_untracked_cache_and_only_metadata_to_the_registry(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid)
        self.assertEqual((e["id"], e["status"], e["rank"], e["kind"]), ("S01", "stored", 2, "web"))
        cached = (self.tmp / "cache/evidence" / f"{e['sha256']}.txt").read_text(encoding="utf-8")
        self.assertIn("PAGE-ONLY-MARKER", cached)
        self.assertIn(FACT, cached)
        reg = (self.lc.job_dir(j) / "evidence/registry.json").read_text(encoding="utf-8")
        self.assertNotIn("PAGE-ONLY-MARKER", reg)
        log = self.ev.fetch_log(j)
        self.assertEqual((log[-1]["status"], log[-1]["source"]), ("stored", "S01"))

    def test_tracked_files_hold_only_metadata_and_short_quotes(self):
        if not shutil.which("git"):
            self.skipTest("git not available")
        shutil.copy2(REPO / ".gitignore", self.tmp / ".gitignore")
        git = lambda *a: subprocess.run(["git", "-C", str(self.tmp), *a], capture_output=True, text=True)
        git("init", "-q")
        j, hid = self.writer_job()
        self.fetch(j, hid)
        st = self.ready(j, 'Orders are capped [S:S01 §Limits "The widget limit is 42 items per order"].\n')
        self.assertEqual(st["state"], "REVIEW")
        git("add", "-A")
        tracked = git("ls-files").stdout.splitlines()
        self.assertFalse([t for t in tracked if t.startswith("cache/")], tracked)
        blob = "".join((self.tmp / t).read_text(encoding="utf-8", errors="replace") for t in tracked if (self.tmp / t).is_file())
        self.assertNotIn("PAGE-ONLY-MARKER", blob)
        self.assertIn("The widget limit is 42 items per order", blob)                  # the short quote may be tracked
        quotes = json.loads((self.lc.job_dir(j) / "evidence/quotes.json").read_text())
        self.assertEqual(quotes["quotes"][0]["source"], "S01")

    def test_a_page_built_by_javascript_is_unfetchable(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid, "/js")
        self.assertEqual(e["status"], "unfetchable")
        self.assertIn("JavaScript", e["reason"])

    def test_pdf_without_a_converter_is_unfetchable(self):
        self.set_evidence(pdf_converter=["no-such-markitdown-xyz"])
        j, hid = self.writer_job()
        e = self.fetch(j, hid, "/doc.pdf")
        self.assertEqual(e["status"], "unfetchable")
        self.assertIn("markitdown", e["reason"])

    def test_pdf_with_a_converter_is_stored(self):
        conv = self.write("scratch/fake_markitdown.py", f"print({FACT!r})\n")
        self.set_evidence(pdf_converter=[sys.executable, str(self.tmp / conv)])
        j, hid = self.writer_job()
        e = self.fetch(j, hid, "/doc.pdf")
        self.assertEqual(e["status"], "stored")
        self.assertIn(FACT, self.ev.stored_text(j, e))

    def test_fetching_needs_an_open_agent_call(self):
        j, hid = self.writer_job()
        with self.assertRaises(self.lc.LabError):
            self.ev.fetch(j, self.base + "/page", "H099")                               # no such handoff
        call = next(c for c in self.lc.load_state(j)["calls"] if c["status"] == "open")
        self.lc.record_result(j, call["id"], "done")
        with self.assertRaises(self.lc.LabError):
            self.ev.fetch(j, self.base + "/page", hid)                                  # call already closed

    def test_fetch_caps_per_call_and_per_job(self):
        self.set_caps(fetches_per_call=2, fetches_per_job=60)
        j, hid = self.writer_job()
        self.fetch(j, hid, "/page"); self.fetch(j, hid, "/notes.txt")
        with self.assertRaises(self.lc.LabError) as cm:
            self.fetch(j, hid, "/js")
        self.assertIn("fetches_per_call", str(cm.exception))
        self.set_caps(fetches_per_call=15, fetches_per_job=2)
        with self.assertRaises(self.lc.LabError) as cm:
            self.fetch(j, hid, "/js")
        self.assertIn("fetches_per_job", str(cm.exception))

    def test_polite_pause_and_user_agent(self):
        seen = []
        orig = _Handler.do_GET

        def spy(handler):
            seen.append(handler.headers.get("User-Agent"))
            orig(handler)
        _Handler.do_GET = spy
        try:
            self.set_evidence(polite_pause_s=0.4)
            j, hid = self.writer_job()
            t0 = time.monotonic()
            self.fetch(j, hid, "/page"); self.fetch(j, hid, "/notes.txt")
            self.assertGreaterEqual(time.monotonic() - t0, 0.4)
        finally:
            _Handler.do_GET = orig
        self.assertTrue(all(ua.startswith("ecosystem-factory-evidence/") for ua in seen), seen)

    def test_redirects_are_limited(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid, "/hop/5")                                                # 5 hops, then the page
        self.assertEqual((e["status"], e["final_url"]), ("stored", self.base + "/page"))
        with self.assertRaises(self.lc.LabError) as cm:
            self.fetch(j, hid, "/hop/1")                                                # 9 hops
        self.assertIn("redirect", str(cm.exception))

    def test_private_addresses_refused_including_after_a_redirect(self):
        cfg = {**self.ev.config(), "allow_private_hosts": False}
        for url in ("http://127.0.0.1/x", "http://10.1.2.3/", "http://169.254.169.254/latest", "http://[::1]/", "file:///etc/passwd"):
            with self.assertRaises(self.lc.LabError, msg=url):
                self.ev.check_host(url, cfg)
        handler = self.ev._Redirects(cfg)
        with self.assertRaises(self.lc.LabError):
            handler.redirect_request(None, None, 302, "Found", {}, "http://192.168.1.1/admin")
        self.set_evidence(allow_private_hosts=False)
        j, hid = self.writer_job()
        with self.assertRaises(self.lc.LabError):
            self.fetch(j, hid)                                                          # the test server is local
        self.assertEqual(self.ev.fetch_log(j)[-1]["status"], "refused")

    def test_shipped_domain_table_is_empty(self):
        cfg = json.loads((REPO / "config/evidence.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["domains"], cfg["files"], cfg["allow_private_hosts"]), ({}, {}, False))
        caps = json.loads((REPO / "config/caps.json").read_text(encoding="utf-8"))
        self.assertEqual((caps["fetches_per_call"], caps["fetches_per_job"]), (15, 60))


class CheckTests(EvidenceBase):
    """Planted faults: each must be caught before any reviewer runs; the clean artifact passes."""

    def run_artifact(self, text, fetch_paths=("/page",), inputs=()):
        j, hid = self.writer_job()
        for p in fetch_paths:
            self.fetch(j, hid, p)
        for data in inputs:
            self.lc.record_input(j, "-", "synthetic", data=data)
        return j, self.ready(j, text)

    def test_clean_artifact_reaches_the_first_reviewer(self):
        j, st = self.run_artifact('Cap: [S:S01 §Limits "The widget limit is 42 items per order"]. '
                                  'We chose a hard stop [A:A01 "stop at the limit"].\n', inputs=[b"Please stop at the limit.\n"])
        self.assertEqual((st["state"], st["stage"]), ("REVIEW", "critic"))

    def test_invented_source_id(self):
        j, st = self.run_artifact("Orders are capped [S:S07 §Limits].\n")
        self.assertEqual((st["state"], st["last_failed_by"]), ("REVISING", "check-evidence"))
        self.assertEqual(self.findings(j), ["E01"])

    def test_unfetched_or_unfetchable_source_cannot_back_a_fact(self):
        j, st = self.run_artifact("The app shows widgets [S:S01 §home].\n", fetch_paths=("/js",))
        self.assertEqual(self.findings(j), ["E02"])

    def test_altered_quote(self):
        j, st = self.run_artifact('Cap [S:S01 §Limits "The widget limit is 50 items per order"].\n')
        self.assertEqual(self.findings(j), ["E03"])

    def test_rank_too_low_for_a_fact(self):
        self.set_evidence(domains={})                                                   # unlisted: rank 5
        j, st = self.run_artifact('Cap [S:S01 §Limits "The widget limit is 42 items per order"].\n')
        self.assertEqual(self.findings(j), ["E04"])

    def test_quote_too_long(self):
        long_quote = " ".join(["word"] * 26)
        j, st = self.run_artifact(f'Cap [S:S01 §x "{long_quote}"].\n')
        self.assertIn("E05", self.findings(j))

    def test_missing_stored_copy_and_refetch(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid)
        (self.tmp / "cache/evidence" / f"{e['sha256']}.txt").unlink()                   # a fresh clone
        problems, _, _ = self.ev.check(j, self.write(f"jobs/{j}/drafts/probe.md", "Cap [S:S01 §Limits].\n"))
        self.assertEqual([p["rule"] for p in problems], ["E06"])
        self.assertEqual(self.ev.refetch(j), [("S01", "restored")])
        self.assertEqual(self.ev.check(j, f"jobs/{j}/drafts/probe.md")[0], [])
        (self.tmp / "cache/evidence" / f"{e['sha256']}.txt").unlink()
        _Handler.routes["/page"] = ("text/html", PAGE.replace("42", "40"))                # the page changed
        self.assertEqual(self.ev.refetch(j), [("S01", "changed")])
        self.assertEqual([p["rule"] for p in self.ev.check(j, f"jobs/{j}/drafts/probe.md")[0]], ["E06"])

    def test_decisions_need_answers_or_approved_artifacts(self):
        lc = self.lc
        parent, _ = self.spec_to_gate()
        j, st = self.run_artifact(f"We stop at the limit [A:A01]. As agreed in [G:{parent}].\n", inputs=[b"Stop.\n"])
        self.assertEqual(self.findings(j), ["E04"])                                      # the parent is not approved yet
        lc.approve_gate(parent)
        self.assertEqual(self.ev.check(j, st["artifact_path"])[0], [])                    # an approved artifact backs it
        j2, st2 = self.run_artifact("We stop at the limit [A:A09].\n")
        self.assertEqual(st2["last_failed_by"], "check-refs")                             # an unknown answer: REF02, one step earlier

    def test_answers_never_back_a_fact(self):
        j, hid = self.writer_job()
        _, rec = self.lc.record_input(j, "-", "synthetic", data=b"The widget limit is 42 items per order.\n")
        e = self.ev.register(j, rec["path"])                                             # the answer as a "source"
        self.assertEqual(e["rank"], 5)
        st = self.ready(j, f'Cap [S:{e["id"]} §1 "The widget limit is 42 items per order"].\n')
        self.assertEqual(self.findings(j), ["E04"])

    def test_check_evidence_findings_pass_the_validator(self):
        j, st = self.run_artifact("Orders are capped [S:S07 §Limits].\n")
        f = sorted((self.lc.job_dir(j) / "reviews").glob("check-evidence-*.json"))[-1]
        p = subprocess.run([sys.executable, str(self.tmp / "engine/validate_findings.py"), str(f)],
                           capture_output=True, text=True, env=self.hook_env())
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_uncited_sentences_are_listed_for_the_verifier(self):
        j, st = self.run_artifact("Revenue grew 12% last year.\nThe sky is blue.\n")
        self.assertEqual(st["state"], "REVIEW")                                          # a hint list, not a failure
        un = json.loads((self.lc.job_dir(j) / "evidence/uncited-v1.json").read_text())
        self.assertEqual([s["sentence"] for s in un["sentences"]], ["Revenue grew 12% last year."])


class StoreProtectionTests(EvidenceBase):
    """Only the fetch script writes the evidence store."""

    def hook(self):
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        try:
            return importlib.import_module("pre_tool_use")
        finally:
            sys.path.remove(str(self.tmp / "engine/hooks"))

    def test_writes_to_the_store_are_blocked_and_the_script_is_allowed(self):
        h = self.hook()
        run = lambda tool, agent=False, **ti: h.run(json.dumps({"tool_name": tool, "tool_input": ti, "cwd": str(self.tmp),
                                                                 **({"agent_id": "a1"} if agent else {})}))
        for path in ("jobs/20260101-spec-a/evidence/registry.json", "jobs/20260101-spec-a/evidence/quotes.json",
                     "cache/evidence/abc.txt", "private/jobs/20260101-spec-a/evidence/cache/abc.txt"):
            self.assertEqual(run("Write", file_path=path), 2, path)
        self.assertEqual(run("Bash", command="echo x > cache/evidence/abc.txt"), 2)
        self.assertEqual(run("Bash", agent=True, command="python engine/evidence.py fetch 20260101-spec-a https://example.org/ --handoff H002"), 0)

    def test_registering_agent_written_files_is_refused(self):
        j, hid = self.writer_job()
        self.write(f"jobs/{j}/research/my-notes.md", "Trust me.")
        with self.assertRaises(self.lc.LabError):
            self.ev.register(j, f"jobs/{j}/research/my-notes.md")
        _, rec = self.lc.record_input(j, "-", "synthetic", data=b"context file\n")
        self.assertEqual(self.ev.register(j, rec["path"])["kind"], "file")


class InternalCacheTests(EvidenceBase):
    def test_internal_pages_live_in_the_job_folder_and_only_that_job_can_read_them(self):
        lc = self.lc
        j, hid = self.writer_job(slug="intone", cls="internal")
        e = self.fetch(j, hid)
        own = lc.job_dir(j) / "evidence/cache" / f"{e['sha256']}.txt"
        self.assertTrue(own.is_file())
        self.assertFalse((self.tmp / "cache/evidence").exists() and any((self.tmp / "cache/evidence").iterdir()))
        other, _ = self.writer_job(slug="inttwo", cls="internal")
        lc.set_active(j)
        sys.path.insert(0, str(self.tmp / "engine/hooks"))
        try:
            h = importlib.import_module("pre_tool_use")
        finally:
            sys.path.remove(str(self.tmp / "engine/hooks"))
        read = lambda path: h.run(json.dumps({"tool_name": "Read", "tool_input": {"file_path": path},
                                              "cwd": str(self.tmp), "agent_id": "a1", "agent_type": "researcher"}))
        self.assertEqual(read(lc.rel(own)), 0)                                           # its own job's cached page
        self.assertEqual(read(f"private/jobs/{other}/evidence/registry.json"), 2)         # another job's store


class RegistryCheckTests(EvidenceBase):
    """Ported from the earlier lab (3 tests), now over the evidence store."""

    def run_check(self, *jobs):
        p = subprocess.run([sys.executable, str(self.tmp / "engine/registry_check.py"), *jobs],
                           capture_output=True, text=True, env=self.hook_env())
        return p.returncode, p.stdout

    def test_all_present_passes_and_reports_orphans(self):
        j, hid = self.writer_job()
        self.fetch(j, hid)
        self.write("cache/evidence/stray.txt", "x")
        code, out = self.run_check(j)
        self.assertEqual(code, 0, out)
        self.assertIn("ORPHAN   cache/evidence/stray.txt", out)

    def test_missing_stored_copy_fails(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid)
        (self.tmp / "cache/evidence" / f"{e['sha256']}.txt").unlink()
        code, out = self.run_check(j)
        self.assertEqual(code, 1)
        self.assertIn("MISSING stored copy for S01", out)

    def test_duplicate_id_fails(self):
        j, hid = self.writer_job()
        e = self.fetch(j, hid)
        reg = self.ev.load_registry(j)
        reg["sources"].append(dict(e))
        self.ev.save_registry(j, reg)
        code, out = self.run_check(j)
        self.assertEqual(code, 1)
        self.assertIn("DUPLICATE id S01", out)


if __name__ == "__main__":
    unittest.main()
