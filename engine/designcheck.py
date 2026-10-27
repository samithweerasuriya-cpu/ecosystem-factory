#!/usr/bin/env python3
"""Charter v0 and blueprint v0 checks (stdlib only, T1.2): the JSON Schema plus the hand checks in
schemas/charter.v0.md and schemas/blueprint.v0.md.

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
    probs = schemacheck.check(doc, json.loads((ROOT / "schemas/charter.v0.schema.json").read_text(encoding="utf-8")))
    if probs:
        return probs
    ids = [r["id"] for r in doc["quality_rules"]]
    probs += [f"quality rule {d} appears twice" for d in dupes(ids)]
    probs += [f"gate {d} appears twice" for d in dupes([g["id"] for g in doc["gates"]])]
    for n, ex in enumerate(doc["examples"]["bad"]):
        probs += [f"examples.bad[{n}] breaks unknown rule {r}" for r in ex["breaks"] if r not in ids]
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
        rules = {r["id"] for r in rulebook}
        subtle = sum(1 for x in designs if x.get("subtle"))
        if subtle * 3 < len(cases):
            probs.append(f"suite {ev['suite']}: {subtle} subtle cases of {len(cases)}; needs at least a third")
        if not any(len(k.get("must_find", [])) >= 2 for k in keys.values()):
            probs.append(f"suite {ev['suite']}: no case with 2 or more defects")
        for cdir, case in cases:
            k = keys[cdir.name]
            unknown = set(k.get("must_find", [])) - rules
            probs += [f"suite {ev['suite']} case {cdir.name}: unknown rule {r}" for r in sorted(unknown)]
            if set(k.get("locations", {})) - set(k.get("must_find", [])):
                probs.append(f"suite {ev['suite']} case {cdir.name}: locations for a rule it does not plant")
            if (case.get("kind") == "clean") != (k.get("verdict") == "pass" and not k.get("must_find")):
                probs.append(f"suite {ev['suite']} case {cdir.name}: kind and key disagree")
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
