"""T1.7: the status export (engine/report.py --json) and the evaluation run records.

The export holds IDs, counts and numbers only (marker test), matches schemas/report-export.schema.json, keeps
every timestamp in UTC with a trailing Z, and fails closed: anything missing or unreadable is an error naming
the file, and nothing is written (lesson 6). A call counts only when the call record and the usage log agree,
and an evaluation report counts only with its run records behind it or as a pre-T1.7 "legacy" report; a report
on config/invalid-reports.json or with failing records is "invalid" for the export and for the lock rule
(lesson 15). No live calls: evaluation runs use fake_claude.py."""
import importlib
import json
import re

from support import LabTestBase
from test_evals_t13 import CLI, SUITE, EvalBase

MARKER = "REPORT-MARKER-5512"
APPROVER = "Approver Markerson"
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$")
TS_FIELDS = ("ts", "generated_at", "at", "created_at", "updated_at", "started_at", "ended_at")


def timestamps(node):
    """Every value of a timestamp field anywhere in the export."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in TS_FIELDS and isinstance(v, str):
                yield v
            else:
                yield from timestamps(v)
    elif isinstance(node, list):
        for v in node:
            yield from timestamps(v)


class ReportBase:
    """Mixin: a fresh report module, a full-run test record and a job with two counted calls."""
    auto_result = False

    def report_setup(self):
        self.rp = importlib.import_module("report")
        self.version = (self.tmp / "engine/VERSION").read_text(encoding="utf-8").strip()
        self.dump("logs/tests-last.json", {"engine_version": self.version, "tier": "full", "tests": 500, "failures": 0,
                                           "skipped": 0, "guard_ok": True, "at": "2026-10-28T12:00:00Z"})
        gates = json.loads((self.tmp / "config/gates.json").read_text(encoding="utf-8"))
        gates["approver"] = APPROVER
        self.dump("config/gates.json", gates)

    def call(self, job, agent, tokens=(100, 50)):
        lc = self.lc
        st = self.raw_record_call(job, agent)
        cid = st["calls"][-1]["id"]
        usage = lc.usage_from_tokens({"input_tokens": tokens[0], "output_tokens": tokens[1]}, model="claude-opus-5-5")
        lc.record_result(job, cid, "done", usage=usage, source="headless", note=f"{MARKER} note",
                         output={"path": f"jobs/{job}/drafts/{MARKER}.json", "sha256": "0" * 64})
        return cid

    def job(self):
        lc = self.lc
        j = lc.new_job("spec", "sample-job", f"Goal with {MARKER}")["job_id"]
        lc.apply(j, "dispatch", note=f"{MARKER} dispatch note")
        self.call(j, "researcher")
        lc.apply(j, "stage_done", note=MARKER)
        self.call(j, "writer", tokens=(200, 80))
        lc.set_ceiling(j, tokens=900000, _human=True)           # a human-only event: actor is the approver
        return j

    def build(self, roots=None):
        return self.rp.build(roots)

    def fails(self, *needles, roots=None):
        with self.assertRaises(self.rp.ExportError) as cm:
            self.build(roots)
        msg = str(cm.exception)
        for n in needles:
            self.assertIn(n, msg)
        self.assertNotIn(MARKER, msg)
        return msg

    def exports(self):
        d = self.tmp / "private/reports"
        return sorted(d.glob("*.json")) if d.is_dir() else []


class ExportTests(ReportBase, LabTestBase):
    def setUp(self):
        super().setUp()
        self.report_setup()

    def test_the_export_matches_its_schema_and_counts_the_job(self):
        j = self.job()
        ex = self.build()
        schema = json.loads((self.tmp / "schemas/report-export.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(self.lc.schemacheck.check(ex, schema), [])
        self.assertEqual(ex["meta"]["engine_version"], self.version)
        self.assertEqual(ex["meta"]["tests"]["count"], 500)
        self.assertEqual(ex["meta"]["roots"][0]["label"], self.tmp.name)
        row = next(r for r in ex["jobs"] if r["job_id"] == j)
        self.assertEqual((row["calls"], row["calls_counted"], row["unbacked_calls"], row["tokens_total"]), (2, 2, 0, 430))
        agents = {r["agent"]: r for r in ex["usage_by_job_agent"] if r["job_id"] == j}
        self.assertEqual((agents["researcher"]["tokens_total"], agents["writer"]["tokens_output"]), (150, 80))
        ev = [e for e in ex["events"] if e["job_id"] == j]
        self.assertEqual([e["seq"] for e in ev], list(range(1, len(ev) + 1)))
        self.assertEqual({e["actor_role"] for e in ev}, {"orchestrator", "script", "human"})
        self.assertIn("C001", {e["call_id"] for e in ev})

    def test_every_timestamp_is_utc_with_a_z(self):
        self.job()
        ex = self.build()
        stamps = list(timestamps(ex))
        self.assertGreater(len(stamps), 10)
        self.assertTrue(all(TS_RE.match(t) for t in stamps), [t for t in stamps if not TS_RE.match(t)])
        schema = json.loads((self.tmp / "schemas/report-export.schema.json").read_text(encoding="utf-8"))
        self.assertIn("Z", schema["$defs"]["ts"]["pattern"])
        bad = json.loads(json.dumps(ex))
        bad["jobs"][0]["created_at"] = "2026-10-28T12:00:00+00:00"   # an offset instead of Z fails the schema
        self.assertTrue(self.lc.schemacheck.check(bad, schema))
        self.assertEqual(self.rp.z(__import__("datetime").datetime.fromisoformat("2026-10-28T14:00:00.250+02:00")),
                         "2026-10-28T12:00:00.250Z")

    def test_markers_never_leave_the_logs(self):
        """Answer paths, notes, goals and the approver's name are in the logs; none reaches the export."""
        j = self.job()
        log = (self.tmp / f"jobs/{j}/run.log.jsonl").read_text(encoding="utf-8")
        self.assertIn(MARKER, log)
        self.assertIn(APPROVER, log)
        self.assertEqual(self.rp.main(["--json"]), 0)
        text = self.exports()[0].read_text(encoding="utf-8")
        for needle in (MARKER, APPROVER, str(self.tmp), self.tmp.as_posix(), "jobs/", "drafts"):
            self.assertNotIn(needle, text)

    def test_a_value_that_is_not_an_id_stops_the_export_without_quoting_it(self):
        j = self.job()
        st = json.loads((self.tmp / f"jobs/{j}/state.json").read_text(encoding="utf-8"))
        st["calls"][0]["usage"]["model"] = f"model {MARKER}"
        self.dump(f"jobs/{j}/state.json", st)
        self.fails(f"jobs/{j}/state.json", "model")

    def test_the_export_is_written_under_private_and_never_overwritten(self):
        self.job()
        self.assertEqual(self.rp.main(["--json", "--out", str(self.tmp / "private/reports/x.json")]), 0)
        self.assertEqual(self.rp.main(["--json", "--out", str(self.tmp / "private/reports/x.json")]), 0)
        self.assertEqual([f.name for f in self.exports()], ["x-2.json", "x.json"])
        self.assertEqual(self.rp.main(["--json", "--out", str(self.tmp / "logs/x.json")]), 1)
        self.assertFalse((self.tmp / "logs/x.json").exists())

    def test_internal_jobs_are_only_counted(self):
        self.job()
        j = self.lc.new_job("spec", "inside-job", f"Internal {MARKER}", cls="internal")["job_id"]
        ex = self.build()
        self.assertEqual(ex["meta"]["roots"][0]["internal_jobs_excluded"], 1)
        self.assertNotIn(j, json.dumps(ex))


class UnbackedTests(ReportBase, LabTestBase):
    """Lesson 15 for jobs: a call counts only when its call record and its usage line agree."""
    def setUp(self):
        super().setUp()
        self.report_setup()

    def usage_lines(self):
        f = self.tmp / "logs/usage.jsonl"
        return f, [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]

    def test_a_call_without_its_usage_line_is_not_counted(self):
        j = self.job()
        f, lines = self.usage_lines()
        f.write_text("".join(json.dumps(x) + "\n" for x in lines if x["call"] != "C002"), encoding="utf-8")
        row = next(r for r in self.build()["jobs"] if r["job_id"] == j)
        self.assertEqual((row["calls_counted"], row["unbacked_calls"], row["tokens_total"]), (1, 1, 150))

    def test_a_usage_line_that_disagrees_is_not_counted_and_an_orphan_is_counted_apart(self):
        j = self.job()
        f, lines = self.usage_lines()
        for x in lines:
            if x["call"] == "C001":
                x["tokens"]["total"] = 99999
        lines.append({**lines[0], "job_id": "20261028-ghost-job", "call": "C001"})
        f.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        ex = self.build()
        row = next(r for r in ex["jobs"] if r["job_id"] == j)
        self.assertEqual((row["calls_counted"], row["unbacked_calls"], row["tokens_total"]), (1, 1, 280))
        self.assertEqual(ex["meta"]["roots"][0]["orphan_usage_lines"], 1)
        self.assertNotIn("C001", {r["call_id"] for r in ex["usage_calls"] if r["job_id"] == j})


class FailClosedTests(ReportBase, LabTestBase):
    """Lesson 6: a missing or unreadable source is an error naming the file; nothing is written."""
    def setUp(self):
        super().setUp()
        self.report_setup()
        self.j = self.job()

    def nothing_written(self):
        self.assertEqual(self.rp.main(["--json"]), 1)
        self.assertEqual(self.exports(), [])

    def test_missing_test_results(self):
        (self.tmp / "logs/tests-last.json").unlink()
        self.fails("logs/tests-last.json", "missing")
        self.nothing_written()

    def test_test_results_from_another_engine_version(self):
        self.dump("logs/tests-last.json", {"engine_version": "0.0.1", "tier": "full", "tests": 1, "failures": 0,
                                           "skipped": 0, "guard_ok": True, "at": "2026-10-28T12:00:00Z"})
        self.fails("logs/tests-last.json", "another engine version")

    def test_an_unreadable_run_log_line(self):
        with open(self.tmp / f"jobs/{self.j}/run.log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(f"not json {MARKER}\n")
        self.fails(f"jobs/{self.j}/run.log.jsonl", "is not JSON")
        self.nothing_written()

    def test_a_missing_run_log(self):
        (self.tmp / f"jobs/{self.j}/run.log.jsonl").unlink()
        self.fails(f"jobs/{self.j}/run.log.jsonl", "missing")

    def test_an_unreadable_state(self):
        (self.tmp / f"jobs/{self.j}/state.json").write_text("{", encoding="utf-8")
        self.fails(f"jobs/{self.j}/state.json", "unreadable")

    def test_a_missing_usage_log_with_closed_calls(self):
        (self.tmp / "logs/usage.jsonl").unlink()
        self.fails("logs/usage.jsonl", "missing")

    def test_a_timestamp_without_a_time_zone(self):
        f = self.tmp / f"jobs/{self.j}/run.log.jsonl"
        lines = f.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["ts"] = "2026-10-28T12:00:00"
        f.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n", encoding="utf-8")
        self.fails(f"jobs/{self.j}/run.log.jsonl line 1", "time zone")

    def test_an_unknown_actor_on_a_machine_event(self):
        f = self.tmp / f"jobs/{self.j}/run.log.jsonl"
        lines = f.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["actor"] = MARKER
        f.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n", encoding="utf-8")
        self.fails(f"jobs/{self.j}/run.log.jsonl line 1", "actor")

    def test_an_unreadable_evaluation_report(self):
        self.write("evals/reports/20261028T120000Z-calibration-critic-full.json", "{ broken")
        self.fails("evals/reports/20261028T120000Z-calibration-critic-full.json", "unreadable")

    def test_a_missing_root(self):
        self.fails("root not found", "no-such-tree", roots=[str(self.tmp), str(self.tmp / "no-such-tree")])

    def test_a_missing_or_malformed_invalid_list(self):
        self.dump("config/invalid-reports.json", {"reports": [{"tree": "x", "report_id": "nope"}]})
        self.fails("config/invalid-reports.json", "entry 0")
        (self.tmp / "config/invalid-reports.json").unlink()
        self.fails("config/invalid-reports.json", "missing")
        with self.assertRaises(self.lc.LabError):
            importlib.import_module("evalcheck").lock_problems(cli=CLI)


class EvalBackingTests(ReportBase, EvalBase):
    """Lesson 15 for evaluations: records, legacy and invalid, in the export and in the lock rule."""
    auto_result = True

    def setUp(self):
        super().setUp()
        self.report_setup()

    def full_run(self):
        rep, code = self.run_suite()
        self.assertEqual(code, 0, self.out)
        f = self.reports()[-1]
        return f, rep

    def runs(self, ex):
        return {r["report_id"]: r for r in ex["eval_runs"]}

    def test_a_new_report_lists_one_record_per_run_and_is_backed(self):
        f, rep = self.full_run()
        self.assertEqual(len(rep["run_records"]), rep["metrics"]["runs"])
        self.assertEqual(len(list(self.ec.runs_dir(SUITE).glob("*.json"))), 21)
        rep2, _ = self.run_suite()                                     # all cached: same records, no new files
        self.assertEqual(sorted(rep2["run_records"]), sorted(rep["run_records"]))
        self.assertEqual(len(list(self.ec.runs_dir(SUITE).glob("*.json"))), 21)
        ex = self.build()
        r = self.runs(ex)[f.stem]
        self.assertEqual((r["backing"], r["backing_reason"], r["runs"], r["runs_passed"], r["cases"]),
                         ("records", None, 21, 21, 7))
        self.assertEqual(len([c for c in ex["eval_cases"] if c["report_id"] == f.stem]), 7)
        self.assertEqual(self.ec.lock_problems(cli=CLI), [])

    def test_a_missing_record_makes_the_report_invalid_for_export_and_lock(self):
        f, rep = self.full_run()
        (self.ec.runs_dir(SUITE) / f"{rep['run_records'][4]}.json").unlink()
        ex = self.build()
        r = self.runs(ex)[f.stem]
        self.assertEqual((r["backing"], r["backing_reason"]), ("invalid", "records_missing"))
        self.assertEqual([c for c in ex["eval_cases"] if c["report_id"] == f.stem], [])   # never charted
        probs = self.ec.lock_problems(cli=CLI)
        self.assertTrue(any("no evaluation reports" in p or "no passing full" in p for p in probs), probs)
        self.assertEqual(self.ec.refused_reports(), [(f.stem, "records_missing")])

    def test_a_changed_record_or_tokens_that_do_not_add_up_make_it_invalid(self):
        f, rep = self.full_run()
        rf = self.ec.runs_dir(SUITE) / f"{rep['run_records'][0]}.json"
        rec = json.loads(rf.read_text(encoding="utf-8"))
        rec["usage"]["total"] = (rec["usage"]["total"] or 0) + 1
        rf.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(self.runs(self.build())[f.stem]["backing_reason"], "records_changed")
        self.assertNotEqual(self.ec.lock_problems(cli=CLI), [])
        rec["usage"]["total"] -= 1
        rf.write_text(json.dumps(rec), encoding="utf-8")
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["usage"]["tokens_all"] += 7
        f.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.runs(self.build())[f.stem]["backing_reason"], "tokens_mismatch")
        self.assertNotEqual(self.ec.lock_problems(cli=CLI), [])

    def test_a_listed_report_is_invalid_for_export_and_lock(self):
        f, _ = self.full_run()
        self.assertEqual(self.ec.lock_problems(cli=CLI), [])
        self.dump("config/invalid-reports.json", {"reports": [
            {"tree": self.tmp.name, "report_id": f.stem, "date": "2026-10-28", "reason": "simulated run"}]})
        ex = self.build()
        r = self.runs(ex)[f.stem]
        self.assertEqual((r["backing"], r["backing_reason"]), ("invalid", "listed"))
        self.assertEqual(ex["meta"]["invalid_list"], [{"tree": self.tmp.name, "report_id": f.stem, "date": "2026-10-28"}])
        self.assertNotIn("simulated run", json.dumps(ex))                # the reason is free text: never exported
        self.assertNotEqual(self.ec.lock_problems(cli=CLI), [])
        self.assertEqual(self.ec.refused_reports(), [(f.stem, "listed")])

    def test_a_report_without_records_is_legacy_and_still_counts(self):
        f, _ = self.full_run()
        doc = json.loads(f.read_text(encoding="utf-8"))
        del doc["run_records"]
        f.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.runs(self.build())[f.stem]["backing"], "legacy")
        self.assertEqual(self.ec.lock_problems(cli=CLI), [])

    def test_the_export_reads_a_second_tree(self):
        f, _ = self.full_run()
        other = self.tmp / "private/archive-tree"
        for d in ("engine", "evals/reports", "jobs"):
            (other / d).mkdir(parents=True, exist_ok=True)
        (other / "engine/VERSION").write_text("0.14.0\n", encoding="utf-8")
        (other / "evals/reports" / f.name).write_bytes(f.read_bytes())   # its records are not in that tree
        ex = self.build(roots=[str(self.tmp), str(other)])
        rows = [r for r in ex["eval_runs"] if r["root"] == "archive-tree"]
        self.assertEqual([(r["backing"], r["backing_reason"]) for r in rows], [("invalid", "records_missing")])
        self.assertEqual([r["engine_version"] for r in ex["meta"]["roots"]], [self.version, "0.14.0"])
