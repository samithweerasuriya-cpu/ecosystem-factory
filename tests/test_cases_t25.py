"""T2.5 case writing: the shipped suites of the four intake agents (charter-critic, charter-verifier, charter-writer,
interviewer) are well formed before any live call. Every key has its own canary; a canary planted in a case stops
that suite before any call; the shipped cases are leak-free; reviewer keys name real rules and a verdict their
severities imply; every quote in a reviewer case's charter is word for word in the answer or context file it cites
(unless the key plants the misquote); clean charters pass the hand checks; persona keys are consistent with the
interview guide's fields, and a persona expected to be ready fits its minimum questions in the slots the caps allow.
The seeding runs are in test_cases_run_t25.py (full tier). Factory-only (tests/): the intake agents and these suites
exist only here."""
import importlib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import REPO  # noqa: E402
from test_jobsim_t25 import FIELDS, JobSimBase  # noqa: E402

SUITES = ("charter-critic", "charter-verifier", "charter-writer", "interviewer")
REVIEWER_SUITES = ("charter-critic", "charter-verifier")
OUTCOMES = ("ready", "escalated", "stopped", "not_ready", "gate")
CANARY = re.compile(r"^[a-z]{6,}[0-9]{2,}$")
QUOTE = re.compile(r'\[(A|S):([AS]\d+)(?: §[^"\]]*?)? "(.*?)"\]')
LONG_WORDS = 2300                                         # "about 2,500 words" in the case design
SEVERITY_PAIRS = (                                        # (suite, pair, {design ID: (rule it must find, verdict)})
    ("charter-critic", "S1", {"P16": ("CH11", "fail"), "C08": ("CH14", "pass")}),
    ("charter-critic", "S2", {"P17": ("CH03", "fail"), "C09": ("CH15", "pass")}),
    ("charter-verifier", "S3", {"V-P14": ("CV02", "fail"), "V-C09": ("CV03", "fail")}),
    ("charter-verifier", "S4", {"V-P15": ("CV04", "fail"), "V-C03": ("CV09", "pass")}))


def shipped(suite):
    return [d for d in sorted((REPO / "evals" / suite / "cases").iterdir()) if d.is_dir()] \
        if (REPO / "evals" / suite / "cases").is_dir() else []


def key_of(suite, case_dir):
    return json.loads((REPO / "evals" / suite / "keys" / f"{case_dir.name}.json").read_text(encoding="utf-8"))


def case_of(case_dir):
    return json.loads((case_dir / "case.json").read_text(encoding="utf-8"))


def norm(text):
    return " ".join(str(text).split())


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


class CaseBase(JobSimBase):
    def copy_suites(self):
        """The shipped suites and the files they name, into the test copy (runs never touch the factory)."""
        for s in SUITES:
            shutil.copytree(REPO / "evals" / s, self.tmp / "evals" / s, dirs_exist_ok=True)
        for f in ("rules/charter-checklist.md", "rules/charter-verifier.md", "rules/interview-guide.md",
                  "schemas/charter.v1.md", "config/data-classes.json", "config/caps.json"):
            (self.tmp / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / f, self.tmp / f)


class ShippedCaseTests(CaseBase):
    """Checks on the shipped case files; anything that loads a suite does so from the test copy."""

    def setUp(self):
        super().setUp()
        self.copy_suites()
        self.dc = importlib.import_module("designcheck")

    def all_cases(self):
        return [(s, d) for s in SUITES for d in shipped(s)]

    def test_every_suite_has_cases(self):
        for s in SUITES:
            self.assertTrue(shipped(s), f"evals/{s} has no cases")

    def test_every_key_has_its_own_canary(self):
        seen = {}
        for s, d in self.all_cases():
            canary = key_of(s, d).get("canary")
            self.assertIsInstance(canary, str, f"{s}/{d.name}: no canary")
            self.assertRegex(canary, CANARY, f"{s}/{d.name}: canary {canary!r} is not a made-up word with digits")
            self.assertNotIn(canary, seen, f"{s}/{d.name} reuses the canary of {seen.get(canary)}")
            seen[canary] = f"{s}/{d.name}"

    def test_no_canary_appears_in_any_case_or_agent_file(self):
        canaries = {key_of(s, d)["canary"]: f"{s}/{d.name}" for s, d in self.all_cases()}
        texts = [f for s in SUITES for f in (REPO / "evals" / s / "cases").rglob("*") if f.is_file()]
        texts += sorted((REPO / ".claude/agents").glob("*.md")) + sorted((REPO / "rules").glob("*.md"))
        for f in texts:
            body = f.read_text(encoding="utf-8").lower()
            for canary, owner in canaries.items():
                self.assertNotIn(canary, body, f"the canary of {owner} appears in {f.relative_to(REPO)}")

    def test_case_ids_are_neutral_and_match_their_keys(self):
        for s, d in self.all_cases():
            self.assertEqual(case_of(d)["id"], d.name)
            self.assertEqual(key_of(s, d).get("case"), d.name)
            self.assertIn("design_id", key_of(s, d))
            if s in REVIEWER_SUITES:          # the ID reaches the agent: it must not say planted or clean
                self.assertRegex(d.name, r"^[KV]\d{2}$")

    def test_the_shipped_cases_are_leak_free(self):
        re_ = importlib.import_module("run_evals")
        for s in SUITES:
            suite = re_.load_suite(s)
            self.assertEqual(re_.leak_check(suite, re_.load_cases(suite)), [], s)

    def test_reviewer_keys_name_real_rules_and_an_implied_verdict(self):
        vf = importlib.import_module("validate_findings")
        for s in REVIEWER_SUITES:
            sev = vf.rulebook_severities(REPO / json.loads((REPO / f"evals/{s}/suite.json").read_text())["rulebook"])
            sev.setdefault("DR07", "minor")
            for d in shipped(s):
                k, c = key_of(s, d), case_of(d)
                must, never = set(k["must_find"]), set(k["must_not_find"])
                self.assertFalse(must & never, d.name)
                self.assertLessEqual(must | never, set(sev), d.name)
                fails = any(sev[r] in ("blocker", "major") for r in must)
                self.assertEqual(k["verdict"], "fail" if fails else "pass", d.name)
                self.assertEqual(c["kind"], "planted" if fails else "clean", d.name)
                self.assertLessEqual(set(k.get("locations", {})), must, d.name)

    def test_every_quote_is_word_for_word_unless_the_key_plants_a_misquote(self):
        re_ = importlib.import_module("run_evals")
        for s in REVIEWER_SUITES:
            for d in shipped(s):
                c, k = case_of(d), key_of(s, d)
                c["dir"] = d
                pools, n = {"A": {}, "S": {}}, {"A": 0, "S": 0}
                for f, role, _ in re_.case_inputs(c):
                    if f == c["artifact"] or role not in ("answer", "context"):
                        continue
                    p = "A" if role == "answer" else "S"
                    n[p] += 1
                    pools[p][f"{p}{n[p]:02d}"] = norm((d / f).read_text(encoding="utf-8"))
                doc = json.loads((d / c["artifact"]).read_text(encoding="utf-8"))
                planted = set(k.get("planted_misquotes", []))
                quotes = [m for t in strings(doc) for m in QUOTE.findall(t)]
                self.assertTrue(quotes, d.name)
                for kind, sid, q in quotes:
                    if q in planted:
                        self.assertNotIn(norm(q), pools[kind].get(sid, ""), f"{d.name}: planted misquote is exact")
                    else:
                        self.assertIn(norm(q), pools[kind].get(sid, ""), f"{d.name}: [{sid}] {q!r} is not word for word")

    def test_clean_charters_pass_the_hand_checks(self):
        for s in REVIEWER_SUITES:
            for d in shipped(s):
                c = case_of(d)
                if c["kind"] == "clean":
                    self.assertEqual(self.dc.check_charter(d / c["artifact"]), [], d.name)

    def test_a_persona_expected_to_be_ready_fits_its_questions_in_the_slots(self):
        """Minimum questions = the answers each concrete field needs, plus one question for every field that must
        end as an open question. Slots = question rounds the caps allow (the lifetime cap, or the per-cycle cap
        times one plus the simulated resumes, whichever is lower) minus the playback round, times the questions a
        round may hold. A persona whose minimum exceeds its slots can't reach ready or the gate."""
        caps = json.loads((REPO / "config/caps.json").read_text(encoding="utf-8"))
        ac = importlib.import_module("agent_call")
        rounds = min(caps["input_rounds"], caps["input_rounds_per_cycle"] * (1 + self.js.SIMULATED_RESUMES))
        slots = (rounds - 1) * ac.MAX_QUESTIONS
        self.assertEqual(slots, 12)                       # the figure in the case design and the vague profile
        for d in shipped("interviewer"):
            k = key_of("interviewer", d)
            if k["expect"]["outcome"] not in ("ready", "gate"):
                continue
            need = sum(n for n in k.get("concrete", {}).values() if n > 0) + len(k["expect"].get("open_questions", []))
            self.assertLessEqual(need, slots, f"{d.name}: needs at least {need} questions, the caps allow {slots}")

    def test_the_cap_case_needs_more_questions_than_the_slots(self):
        """The cap case hits the round cap by construction: its minimum questions exceed the slots, and it expects
        escalation."""
        caps = json.loads((REPO / "config/caps.json").read_text(encoding="utf-8"))
        ac = importlib.import_module("agent_call")
        rounds = min(caps["input_rounds"], caps["input_rounds_per_cycle"] * (1 + self.js.SIMULATED_RESUMES))
        slots = (rounds - 1) * ac.MAX_QUESTIONS
        caps_cases = [d for d in shipped("interviewer") if key_of("interviewer", d)["design_id"] == "cap"]
        self.assertEqual(len(caps_cases), 1)
        k = key_of("interviewer", caps_cases[0])
        need = sum(n for n in k["concrete"].values() if n > 0)
        self.assertGreater(need, slots, f"{caps_cases[0].name}: needs {need} questions, the caps allow {slots}")
        self.assertEqual(k["expect"]["outcome"], "escalated")

    def test_every_writer_key_reads_invented_content_structurally(self):
        for d in shipped("charter-writer"):
            k = key_of("charter-writer", d)
            entries = k.get("invented_entries")
            self.assertTrue(entries, f"{d.name}: no invented_entries")
            for e in entries:
                self.assertEqual(set(e), {"field", "match"}, d.name)
                self.assertTrue(e["match"], d.name)
                for pattern in e["match"].values():
                    re.compile(pattern)

    def test_long_cases_are_full_length(self):
        """A key marked "length": "long" is a full-length case: its charter (or, without one, its case files) has
        at least LONG_WORDS words."""
        for s, d in self.all_cases():
            if key_of(s, d).get("length") != "long":
                continue
            c = case_of(d)
            files = [d / c["artifact"]] if c.get("artifact") else [f for f in d.iterdir() if f.is_file()]
            n = sum(len(f.read_text(encoding="utf-8").split()) for f in files)
            self.assertGreaterEqual(n, LONG_WORDS, f"{s}/{d.name}: {n} words")

    def test_severity_pairs_have_both_halves_as_designed(self):
        """Rule 8 pairs: the same defect breaks a different rule depending on where it sits. Once either half is
        shipped, both are, each expecting its rule and verdict."""
        for s, pair, halves in SEVERITY_PAIRS:
            keys = {key_of(s, d)["design_id"]: key_of(s, d) for d in shipped(s)}
            present = [h for h in halves if h in keys]
            if not present:
                continue
            self.assertEqual(len(present), 2, f"{pair}: only {present} shipped")
            for design, (rule, verdict) in halves.items():
                self.assertIn(rule, keys[design]["must_find"], f"{pair} {design}")
                self.assertEqual(keys[design]["verdict"], verdict, f"{pair} {design}")

    def test_planted_cases_in_one_domain_do_not_share_a_location(self):
        """Cases built on one domain base vary their surface; the planted defects sit at different places. Each
        reviewer key names its domain and an anchor (a dotted path into the charter) for every rule it must find;
        no two planted cases in one domain share an anchor."""
        for s in REVIEWER_SUITES:
            seen = {}
            for d in shipped(s):
                k, c = key_of(s, d), case_of(d)
                self.assertIn(k.get("domain"), ("D1", "D2", "D3", "D4"), f"{s}/{d.name}")
                anchors = k.get("anchors")
                self.assertIsInstance(anchors, dict, f"{s}/{d.name}")
                self.assertEqual(set(anchors), set(k["must_find"]), f"{s}/{d.name}: an anchor for each must_find rule")
                doc = json.loads((d / c["artifact"]).read_text(encoding="utf-8"))
                for rule, where in anchors.items():
                    node = doc
                    for part in where.split("."):
                        self.assertIn(part, node, f"{s}/{d.name}: {rule} anchor {where} is not in the charter")
                        node = node[part]
                if c["kind"] != "planted":
                    continue
                for where in set(anchors.values()):
                    spot = (k["domain"], where)
                    self.assertNotIn(spot, seen, f"{s}/{d.name} and {seen.get(spot)} plant at {where} in {k['domain']}")
                    seen[spot] = d.name

    def test_design_ids_are_unique(self):
        for s in SUITES:
            ids = [key_of(s, d)["design_id"] for d in shipped(s)]
            self.assertEqual(len(ids), len(set(ids)), s)

    def test_persona_keys_fit_the_guide(self):
        for d in shipped("interviewer"):
            c, k = case_of(d), key_of("interviewer", d)
            self.assertIn(k["expect"]["outcome"], OUTCOMES, d.name)
            for group in ("concrete", "answers"):
                self.assertLessEqual(set(k.get(group, {})), set(FIELDS), f"{d.name}: {group}")
            for f in k.get("reference", []) + k.get("contradictions", []) + k["expect"].get("open_questions", []):
                self.assertIn(f, FIELDS, d.name)
            for f, need in k.get("concrete", {}).items():
                self.assertGreaterEqual(len(k.get("answers", {}).get(f, [])), need, f"{d.name}: {f} needs {need} answers")
            for f in k["expect"].get("open_questions", []):
                self.assertNotIn(f, k.get("concrete", {}), f"{d.name}: {f} can't be both concrete and open")
            if c.get("single_call"):
                self.assertEqual(k["expect"]["outcome"], "not_ready", d.name)
                self.assertTrue(k.get("probe_fields"), d.name)
                for f in k["probe_fields"]:
                    self.assertNotIn(f, k["concrete"], d.name)
            if c.get("end_to_end"):
                self.assertEqual(k["expect"]["outcome"], "gate", d.name)
                self.assertTrue(k.get("reference_charter"), d.name)
            text = " ".join(f.read_text(encoding="utf-8") for f in d.iterdir() if f.is_file()).lower()
            for words in k.get("injections", []):         # every planted instruction-like text is in the case
                self.assertTrue(any(w.lower() in text for w in words), f"{d.name}: injection {words} not planted")


class CanaryRunTests(CaseBase):
    """Runs in the test copy: a planted canary stops each suite before any call (the seeding runs are in
    test_cases_run_t25.py, full tier)."""

    def test_a_planted_canary_stops_each_suite_before_any_call(self):
        self.copy_suites()
        for s in SUITES:
            d = shipped(s)[0]
            target = self.tmp / "evals" / s / "cases" / d.name / ("brief.md" if (d / "brief.md").exists() else "charter.json")
            original = target.read_text(encoding="utf-8")
            target.write_text(original + f"\nReference: {key_of(s, d)['canary']}\n", encoding="utf-8")
            out = []
            rep, code = self.re.run(s, "quick", out=out.append)
            self.assertEqual((rep, code, self.calls()), (None, 2, []), (s, out))
            self.assertTrue(any(f"LEAK: case {d.name}: {key_of(s, d)['canary']!r}" in line for line in out), (s, out))
            target.write_text(original, encoding="utf-8")
