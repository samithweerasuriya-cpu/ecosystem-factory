# Calibration critic rulebook

Rulebook for the evaluation-only calibration critic (`evals/agents/calibration-critic.md`, T0.13). It is used by no route: it exists to prove the evaluation runner, the leak check and the lock rule. Defect patterns adapted from the author's earlier private labs; every case is synthetic.

The critic reviews a draft spec against the brief it was built from. Severity: **blocker** (cannot pass) · **major** (fail) · **minor** (note only). The verdict fails on any blocker or major finding. Rule IDs are stable: a retired rule keeps its ID and is never reused.

| ID | Rule | Sev |
|---|---|---|
| CC01 | Every requirement cites a brief fact (`F<n>`) that actually supports it. A citation to a fact about something else is a missing trace. | major |
| CC02 | A question the brief leaves open stays open in the spec, unless a brief fact with medium or high confidence answers it. A low-confidence fact alone never closes a question. | major |
| CC03 | Every performance or freshness statement has a measurable target (a number with a unit, e.g. "within 5 minutes"). Words like "real time", "instantly" or "fast" alone are not targets. | major |
| CC04 | Every section of the spec template is present: Summary, Requirements, Data, Open questions, Risks. | major |
| CC05 | The spec adds nothing outside the brief's scope (see the brief's "Out of scope" list). | major |
| CC06 | Wording is concise and unambiguous. | minor |
