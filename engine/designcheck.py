#!/usr/bin/env python3
"""Charter v0 and v1 and blueprint v0 checks (stdlib only, T1.2, T2.1): the JSON Schema plus the hand checks
in schemas/charter.v0.md, schemas/charter.v1.md and schemas/blueprint.v0.md. The charter version comes from
its schema_version.

  python engine/designcheck.py charter <charter.json>
  python engine/designcheck.py blueprint <blueprint.json>

Prints every problem; exit 0 when there are none, 1 otherwise. Anything unreadable fails.
"""
import json
import re
import sys
from pathlib import Path

import schemacheck

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = "schemas/findings.schema.json"
CAP_KEYS = ("critic_revisions", "total_revisions_before_gate", "gate_rejections", "agent_calls_per_job")


def load(path):
    """(document, problems)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), []
    except (OSError, ValueError) as e:
        return None, [f"{path}: unreadable ({e})"]


def dupes(values):
    seen, out = set(), []
    for v in values:
        if v in seen and v not in out:
            out.append(v)
        seen.add(v)
    return out


def check_charter(path):
    doc, probs = load(path)
    if doc is None:
        return probs
    if isinstance(doc, dict) and doc.get("schema_version") == "1":
        return check_charter_v1(Path(path), doc)
    probs = schemacheck.check(doc, json.loads((ROOT / "schemas/charter.v0.schema.json").read_text(encoding="utf-8")))
    if probs:
        return probs
    ids = [r["id"] for r in doc["quality_rules"]]
    probs += [f"quality rule {d} appears twice" for d in dupes(ids)]
    probs += [f"gate {d} appears twice" for d in dupes([g["id"] for g in doc["gates"]])]
    for n, ex in enumerate(doc["examples"]["bad"]):
        probs += [f"examples.bad[{n}] breaks unknown rule {r}" for r in ex["breaks"] if r not in ids]
    return probs


UNKNOWN_RE = re.compile(r"\b(TBD|TBC|TODO)\b|\bto be (decided|confirmed|determined)\b|\bdon['’]?t know\b|\?\?\?",
                        re.IGNORECASE)


def strings(value, path="$"):
    """(path, text) for every string in a charter, leaving out citations and open questions."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in ("cites", "open_questions"):
                yield from strings(v, f"{path}.{k}")


def cited(value, path="$"):
    """(path, citation) for every citation in a charter."""
    if isinstance(value, list):
        for i, v in enumerate(value):
            yield from cited(v, f"{path}[{i}]")
    elif isinstance(value, dict):
        for k, v in value.items():
            if k == "cites":
                yield from ((f"{path}.cites[{i}]", c) for i, c in enumerate(v))
            else:
                yield from cited(v, f"{path}.{k}")


def check_charter_v1(path, doc, answers=None, context_ids=None):
    """Charter v1 (T2.1): the schema plus the hand checks in schemas/charter.v1.md. In a job (T2.4,
    agent_call), answers is {answer ID: text} from the job's recorded answers (instead of answers_ref) and
    context_ids the job's registered context files, which the context inventory may not go beyond."""
    from evidence import CITE_RE, normalise
    schema = json.loads((ROOT / "schemas/charter.v1.schema.json").read_text(encoding="utf-8"))
    probs = schemacheck.check(doc, schema)
    if probs:
        return probs
    for name, items, key in (
            ("metric", doc["success_metrics"]["agent_checkable"] + doc["success_metrics"]["outcome"], "id"),
            ("acceptance test", doc["acceptance_tests"], "id"), ("context file", doc["context_inventory"], "id"),
            ("quality rule", doc["quality_rulebook"]["rules"], "id"),
            ("example", doc["examples"]["good"] + doc["examples"]["bad"], "id"), ("gate", doc["gates"], "id"),
            ("system", doc["systems"], "id"), ("open question", doc["open_questions"], "id"),
            ("acceptance criterion", doc["acceptance_criteria"], "id"), ("role", doc["users_and_stakeholders"], "role")):
        probs += [f"{name} {d} appears twice" for d in dupes([x[key] for x in items])]

    # citations: well formed, A or S, short quotes; S in the inventory; A in the answers file when one is given
    files = {f["id"]: f for f in doc["context_inventory"]}
    source = "the job's recorded answers" if answers is not None else doc.get("answers_ref")
    if context_ids is not None:
        probs += [f"context file {f} is not registered in this job" for f in sorted(set(files) - set(context_ids))]
    if answers is None and "answers_ref" in doc:
        adoc, p = load(path.parent / doc["answers_ref"])
        p = p or schemacheck.check(adoc, schema["$defs"]["answers_file"], root=schema)
        if p:
            return [f"answers_ref {doc['answers_ref']}: {x}" for x in p]
        answers = {a["id"]: a["text"] for a in adoc["answers"]}
    max_words = json.loads((ROOT / "config/evidence.json").read_text(encoding="utf-8"))["max_quote_words"]
    quotes = {}
    for loc, c in cited(doc):
        m = CITE_RE.fullmatch(c.strip())
        if not m:
            probs.append(f"{loc}: citation {c!r} is not well formed")
            continue
        kind, sid, quote = m.group(1), m.group(2), m.group(4)
        if quote is not None and words(quote) > max_words:
            probs.append(f"{loc}: quote longer than {max_words} words")
        if kind == "S" and sid not in files:
            probs.append(f"{loc}: [S:{sid}] is not in the context inventory")
        elif kind == "A" and answers is not None:
            if sid not in answers:
                probs.append(f"{loc}: [A:{sid}] is not an answer in {source}")
            elif quote is not None and normalise(quote) not in normalise(answers[sid]):
                probs.append(f"{loc}: quote is not word for word in answer {sid}")
        if kind == "A" and quote is not None:
            quotes.setdefault(loc.rsplit(".cites", 1)[0], []).append(normalise(quote))
    for n, t in enumerate(doc["acceptance_tests"]):
        if normalise(t["words"]) not in quotes.get(f"$.acceptance_tests[{n}]", []):
            probs.append(f"acceptance test {t['id']}: words are not quoted from an answer ([A:<id> \"<the same words>\"])")
    probs += [f"input sample {s['source']} is not in the context inventory" for s in doc["inputs"]["samples"]
              if s["source"] not in files]

    # data classes: allowed by config, and no file above the charter
    allowed = json.loads((ROOT / "config/data-classes.json").read_text(encoding="utf-8"))["allowed"]
    order = ["synthetic", "public", "internal"]
    cls = doc["data_classification"]["class"]
    if cls not in allowed:
        probs.append(f"data classification {cls} is not allowed (config/data-classes.json: {', '.join(allowed)})")
    for f in doc["context_inventory"]:
        if f["classification"] not in allowed:
            probs.append(f"context file {f['id']}: classification {f['classification']} is not allowed "
                         "(config/data-classes.json)")
        elif order.index(f["classification"]) > order.index(cls):
            probs.append(f"context file {f['id']}: classified {f['classification']}, above the charter's {cls}")

    sp = doc["source_policy"]
    if sorted(r["rank"] for r in sp["ranks"]) != [1, 2, 3, 4, 5]:
        probs.append("source_policy.ranks must be exactly 1 to 5, once each")
    paths = {f["path"] for f in doc["context_inventory"]}
    probs += [f"source_policy.official_sources.files: {p} is not in the context inventory"
              for p in sp["official_sources"]["files"] if p not in paths]

    relations = {r["relation"] for r in doc["users_and_stakeholders"]}
    probs += [f"users_and_stakeholders has no {r}" for r in ("user", "approver") if r not in relations]
    roles = {r["role"] for r in doc["users_and_stakeholders"]}
    probs += [f"open question {q['id']}: owner {q['owner']} is not a role in users_and_stakeholders"
              for q in doc["open_questions"] if q["owner"] not in roles]

    ids = {r["id"] for r in doc["quality_rulebook"]["rules"]}
    for ex in doc["examples"]["bad"]:
        probs += [f"example {ex['id']} breaks unknown rule {r}" for r in ex["breaks"] if r not in ids]
    writes = {s["id"] for s in doc["systems"] if s["access"] == "write"}
    guarded = {w for g in doc["gates"] for w in g["before_write"]}
    probs += [f"system {w}: no gate is placed before this write (a gate's before_write must name it)"
              for w in sorted(writes - guarded)]
    for g in doc["gates"]:
        probs += [f"gate {g['id']}: before_write names {w}, which is not a write system"
                  for w in g["before_write"] if w not in writes]
    probs += [f"gate {g['id']}: mode must be 'human' until Phase 5 (T0.15)" for g in doc["gates"] if g["mode"] != "human"]

    caps, factory = doc["caps"], json.loads((ROOT / "config/caps.json").read_text(encoding="utf-8"))
    for k in CAP_KEYS:
        if caps[k] > factory[k]:
            probs.append(f"caps.{k} {caps[k]} is above the factory's {factory[k]}")
    for k in ("tokens", "agent_minutes"):
        if caps["usage_ceiling"][k] > factory["usage_ceiling"][k]:
            probs.append(f"caps.usage_ceiling.{k} is above the factory's {factory['usage_ceiling'][k]}")
    if caps["critic_revisions"] > caps["total_revisions_before_gate"]:
        probs.append("caps.critic_revisions is above caps.total_revisions_before_gate")

    probs += [f"{loc}: {m.group(0)!r} is not allowed; make it an open question with an owner"
              for loc, text in strings(doc) for m in [UNKNOWN_RE.search(text)] if m]
    return probs


def words(text):
    return len(re.findall(r"\S+", text))


def norm(text):
    return " ".join(str(text).split()).lower()


def check_suite(ev, agent, rulebook):
    """Problems with one evaluation suite folder, against evals/README.md."""
    probs, d = [], ROOT / ev["path"]
    suite, p = load(d / "suite.json")
    if suite is None:
        return p
    if suite.get("kind") != ev["kind"] or ev["kind"] != ("reviewer" if agent["role"] == "reviewer" else "agent"):
        probs.append(f"suite {ev['suite']}: kind {suite.get('kind')!r} does not fit the agent's role")
    if ev["kind"] == "agent":
        probs += [f"suite {ev['suite']}: suite.json needs {k}" for k in
                  ("output_schema", "items_field", "quote_field", "check_fields") if not suite.get(k)]
    cases, keys = [], {}
    for cdir in sorted((d / "cases").iterdir()) if (d / "cases").is_dir() else []:
        case, p = load(cdir / "case.json")
        key, q = load(d / "keys" / f"{cdir.name}.json")
        probs += p + q
        if case is None or key is None:
            continue
        missing = [n for n in case.get("inputs", []) if not (cdir / n).is_file()]
        probs += [f"suite {ev['suite']} case {cdir.name}: input {n} missing" for n in missing]
        cases.append((cdir, case))
        keys[cdir.name] = key
    th = json.loads((ROOT / "evals/thresholds.json").read_text(encoding="utf-8"))["min_counts"][ev["kind"]]
    clean = sum(1 for _, c in cases if c.get("kind") == "clean")
    if len(cases) < th["cases"] or clean < th.get("clean", 0):
        probs.append(f"suite {ev['suite']}: {len(cases)} cases ({clean} clean); needs {th['cases']}"
                     + (f" ({th['clean']} clean)" if th.get("clean") else ""))
    designs = [k.get("design", {}) for k in keys.values()]
    if not any(x.get("injection") for x in designs):
        probs.append(f"suite {ev['suite']}: no injection case")
    if not any(x.get("real_length") for x in designs):
        probs.append(f"suite {ev['suite']}: no case at real length")
    if ev["kind"] == "reviewer":
        from generate import DEFAULT_RULES, reserved_rules           # T1.4: DR07, added to every rulebook
        reserved = {r["id"]: r["severity"] for r in reserved_rules((ROOT / DEFAULT_RULES).read_bytes())}
        severity = {**{r["id"]: r["severity"] for r in rulebook}, **reserved}
        rules = {r["id"] for r in rulebook}
        subtle = sum(1 for x in designs if x.get("subtle"))
        if subtle * 3 < len(cases):
            probs.append(f"suite {ev['suite']}: {subtle} subtle cases of {len(cases)}; needs at least a third")
        if not any(len(k.get("must_find", [])) >= 2 for k in keys.values()):
            probs.append(f"suite {ev['suite']}: no case with 2 or more defects")
        for cdir, case in cases:
            k = keys[cdir.name]
            unknown = set(k.get("must_find", [])) - set(severity)
            probs += [f"suite {ev['suite']} case {cdir.name}: unknown rule {r}" for r in sorted(unknown)]
            if set(k.get("locations", {})) - set(k.get("must_find", [])):
                probs.append(f"suite {ev['suite']} case {cdir.name}: locations for a rule it does not plant")
            serious = [r for r in k.get("must_find", []) if severity.get(r) in ("blocker", "major")]
            if (case.get("kind") == "clean") != (k.get("verdict") == "pass" and not serious):
                probs.append(f"suite {ev['suite']} case {cdir.name}: kind and key disagree")
            injection = bool(k.get("design", {}).get("injection"))
            for r in sorted(reserved):                                 # the injection cases plant DR07, no other
                if injection and (r not in k.get("must_find", []) or not k.get("locations", {}).get(r)):
                    probs.append(f"suite {ev['suite']} case {cdir.name}: an injection case must expect {r} "
                                 "at the injected text")
                if not injection and r not in k.get("must_not_find", []):
                    probs.append(f"suite {ev['suite']} case {cdir.name}: {r} must be in must_not_find "
                                 "(only injection cases expect it)")
        for r in sorted(rules):
            if not any(r in k.get("must_find", []) for k in keys.values()):
                probs.append(f"suite {ev['suite']}: no planted case for {r}")
            if not any(r in k.get("design", {}).get("near_miss", []) for k in keys.values() if not k.get("must_find")):
                probs.append(f"suite {ev['suite']}: no clean near-miss twin for {r}")
    else:
        for cdir, case in cases:
            k = keys[cdir.name]
            if not k.get("expected"):
                probs.append(f"suite {ev['suite']} case {cdir.name}: no expected items")
                continue
            text = norm(" ".join((cdir / n).read_text(encoding="utf-8") for n in case.get("inputs", [])
                                 if (cdir / n).is_file()))
            for e in k["expected"]:
                probs += [f"suite {ev['suite']} case {cdir.name} {e.get('id')}: source not in the inputs"
                          for s in e.get("sources", []) if norm(s) not in text]
                if not e.get("sources"):
                    probs.append(f"suite {ev['suite']} case {cdir.name} {e.get('id')}: no sources")
    return probs


def check_blueprint(path):
    path = Path(path)
    doc, probs = load(path)
    if doc is None:
        return probs
    probs = schemacheck.check(doc, json.loads((ROOT / "schemas/blueprint.v0.schema.json").read_text(encoding="utf-8")))
    if probs:
        return probs
    charter_path = ROOT / doc["charter_ref"]
    cprobs = check_charter(charter_path)
    if cprobs:
        return [f"charter {doc['charter_ref']}: {p}" for p in cprobs]
    charter = json.loads(charter_path.read_text(encoding="utf-8"))
    if charter["schema_version"] != "0":
        return [f"charter {doc['charter_ref']}: blueprint v0 needs a charter v0"]
    if charter["slug"] != doc["slug"]:
        probs.append(f"slug {doc['slug']!r} differs from the charter's {charter['slug']!r}")
    agents = {a["name"]: a for a in doc["agents"]}
    probs += [f"agent {d} appears twice" for d in dupes([a["name"] for a in doc["agents"]])]
    for field, role in (("author", "author"), ("reviewer", "reviewer")):
        a = agents.get(doc["route"][field])
        if a is None or a["role"] != role:
            probs.append(f"route.{field} {doc['route'][field]!r} is not an agent with role {role}")
    if doc["route"]["gate"] not in {g["id"] for g in doc["gates"]}:
        probs.append(f"route.gate {doc['route']['gate']} is not a gate")
    probs += [f"gate {d} appears twice" for d in dupes([g["id"] for g in doc["gates"]])]
    if agents.get(doc["final_output"]["from"], {}).get("role") != "author":
        probs.append("final_output.from is not an author agent")
    for a in doc["agents"]:
        if a["role"] == "reviewer" and a["output_schema"] != FINDINGS:
            probs.append(f"agent {a['name']}: a reviewer's output schema is {FINDINGS}")
        if not ((path.parent / a["output_schema"]).is_file() or (ROOT / a["output_schema"]).is_file()):
            probs.append(f"agent {a['name']}: output schema {a['output_schema']} not found")
    rules = doc["rulebook"]["rules"]
    probs += [f"rulebook rule {d} appears twice" for d in dupes([r["id"] for r in rules])]
    probs += [f"rulebook {r['id']}: IDs starting DR are reserved (rules/default-agent-rules.md)" for r in rules
              if r["id"].startswith("DR")]
    for q in charter["quality_rules"]:
        mapped = [r for r in rules if r["charter_rule"] == q["id"]]
        if len(mapped) != 1:
            probs.append(f"charter rule {q['id']} has {len(mapped)} rulebook rules; needs exactly 1")
        elif mapped[0]["severity"] != q["severity"]:
            probs.append(f"rulebook {mapped[0]['id']}: severity {mapped[0]['severity']} differs from the charter's "
                         f"{q['severity']} for {q['id']}")
    probs += [f"rulebook {r['id']}: unknown charter rule {r['charter_rule']}" for r in rules
              if r["charter_rule"] not in {q["id"] for q in charter["quality_rules"]}]
    factory = json.loads((ROOT / "config/caps.json").read_text(encoding="utf-8"))
    for k in CAP_KEYS:
        if doc["caps"][k] > factory[k]:
            probs.append(f"caps.{k} {doc['caps'][k]} is above the factory's {factory[k]}")
    for k in ("tokens", "agent_minutes"):
        if doc["caps"]["usage_ceiling"][k] > factory["usage_ceiling"][k]:
            probs.append(f"caps.usage_ceiling.{k} is above the factory's {factory['usage_ceiling'][k]}")
    if doc["connectors"]:
        probs.append("connectors must be empty in v0")
    suites = {e["agent"]: e for e in doc["evals"]}
    for name, a in agents.items():
        if name not in suites:
            probs.append(f"agent {name}: no evaluation suite")
        else:
            probs += check_suite(suites[name], a, rules)
    probs += [f"evals: suite for unknown agent {e['agent']}" for e in doc["evals"] if e["agent"] not in agents]
    return probs


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) != 2 or argv[0] not in ("charter", "blueprint"):
        print(__doc__.strip())
        return 1
    probs = (check_charter if argv[0] == "charter" else check_blueprint)(argv[1])
    for p in probs:
        print(f"- {p}")
    print(f"{argv[0]} {argv[1]}: {'OK' if not probs else f'{len(probs)} problem(s)'}")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
