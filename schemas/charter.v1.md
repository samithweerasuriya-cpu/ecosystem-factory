# Problem charter (schema v1)

**From:** the problem owner's answers and context pack (intake, T2.4) **To:** the blueprint
**Machine-checkable version:** [charter.v1.schema.json](charter.v1.schema.json)
**Examples:** [examples/](examples/) (`charter.v1.*.json`, each with its answers file)
**Hand checks:** `python engine/designcheck.py charter <file>` (picks v0 or v1 from `schema_version`)

v1 replaces the thin v0 charter for every new job; v0 stays only for the Phase 1 thin version. Fields not listed here are rejected; anything unparseable fails.

**Citations.** Every section and every list item has `cites`: one or more citations in the evidence module's format (`rules/check-evidence.md`). `[A:<id>]` or `[A:<id> "exact words"]` cites one of the approver's recorded answers (IDs `A01`, `A02`… as `state.py input` gives them); `[S:<id> §<location>]` or with `"exact words"` cites a file in the context inventory. A charter has no `[G:…]` citations: nothing is approved before it. Quotes are at most 25 words (`config/evidence.json`).

**Unknowns.** A charter never says "TBD" or "don't know". Every unknown is an entry in `open_questions`, with an owner. ("Don't know yet" is fine in the T2.2 problem brief; the charter writer turns it into an open question.)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | text | yes | Must be `"1"`. |
| `slug` | text | yes | Lowercase, digits and hyphens, 2–41 characters. |
| `title` | text | yes | Short name of the problem. |
| `answers_ref` | text | no | The answers file, from the charter's folder (format: `$defs.answers_file` in the schema). When given, every `[A:…]` must name an answer in it and every quote must be word for word. In a job, answers are checked by `engine/evidence.py` and the charter verifier instead. |
| `goal` | `text`, `cites` | yes | What changes for people when this works. |
| `success_metrics.agent_checkable` | list | yes | Each `id` (`M01`…), `metric`, `target`, `check` (how a script or reviewer measures it), `cites`. |
| `success_metrics.outcome` | list | yes | Each `id`, `metric`, `target`, `cites`: what the people involved notice; not checkable by an agent. |
| `users_and_stakeholders` | list | yes | Each `role` (a role name, never a person's name), `relation` (`user`, `approver`, `stakeholder`), `interest`, `cites`. At least one user and one approver. |
| `current_process` | `steps`, `problems`, `cites` | yes | How it is done today and what goes wrong. |
| `scope` | `in`, `out`, `cites` | yes | At least one item each. |
| `inputs` | object | yes | `description`, `format`, `constraints`, `samples` (each `source`: a context-inventory ID, and `description`), `cites`. |
| `glossary` | list | yes | Each `term`, `meaning`, `cites`. May be empty. |
| `acceptance_tests` | list | yes | Each `id` (`T01`…), `words` (the problem owner's own answer to "how will you know it worked?"), `cites`. |
| `context_inventory` | list | yes | Every file in the context pack: `id` (`S01`…), `path` (inside the job folder, e.g. `inputs/context/notes.txt`), `classification`, `evidence_for`. May be empty. Quotes from these files are checked at job time by `engine/evidence.py`. |
| `data_classification` | `class`, `cites` | yes | `synthetic`, `public` or `internal` in the schema; only the classes in `config/data-classes.json` pass (now: synthetic, public). Confidential and customer data have no value. |
| `source_policy` | object | yes | `ranks` (1 to 5, each `rank`, `what`, `use_for`); `official_sources` (`domains` and `files`, each mapping a host or file to a rank: the shape of `config/evidence.json`); `confidence` (`high`, `medium`, `low`: what each needs); `conflicts` (the conflict rules); `cites`. |
| `output` | object | yes | `description`, `format`, `fields` (each `name`, `description`), `cites`. |
| `quality_rulebook` | object | yes | `rules` (each `id` `Q01`…, `statement`, `severity` `blocker`/`major`/`minor` exactly as the problem owner gave it, `cites`); optional `definitions` (sentences defining terms the rules use; not rules). IDs starting `DR` are reserved: the generator adds DR07 (minor) to every rulebook. A verdict fails on any blocker or major, and only then. |
| `examples.good` / `examples.bad` | lists | yes | At least 2 each. Each `id` (`E01`…), `text`, `origin` (`real` or `synthetic`), `cites`; a bad one also `why` and `breaks` (quality-rule IDs). |
| `risk` | object | yes | `reversibility` (`reversible`, `partly`, `irreversible`), `blast_radius` (`self`, `team`, `organisation`, `external`), `notes`, `cites`. |
| `systems` | list | yes | Each system the ecosystem touches: `id`, `description`, `access` (`read`/`write`), `cites`. May be empty. |
| `gates` | list | yes | Each `id` (`G1`…), `decision`, `mode`, `approver_role` (`"approver"`: the name comes from `config/gates.json`), `before_write` (the write systems this gate is placed directly before; empty for a gate on review only), `cites`. |
| `caps` | object | yes | `critic_revisions`, `total_revisions_before_gate`, `gate_rejections`, `agent_calls_per_job`, `usage_ceiling` (`tokens`, `agent_minutes`), `cites`. |
| `open_questions` | list | yes | Each `id` (`OQ01`…), `question`, `owner` (a role from `users_and_stakeholders`). |
| `acceptance_criteria` | list | yes | Each `id` (`AC01`…), `criterion`, `check` (how it is verified before go-live), `cites`. |

## Source policy template

A starting point the interviewer offers; the problem owner changes it to fit. Rank 1 is the strongest.

| Rank | What | Use for |
|---|---|---|
| 1 | The problem owner's own decisions and approved documents | Goals, scope, rules, terminology |
| 2 | Internal reference documents in the context pack | How things work here |
| 3 | Specifications and contracts | Exact names, fields, formats |
| 4 | Official documentation published by the maker of a product, on its own domain, and verified findings | Product behaviour |
| 5 | Everything else (third-party pages, community posts, earlier AI-assisted analyses, meeting summaries) | Leads only; never the only support for a claim |

Confidence: **high** needs a stored source of rank 4 or better with a word-for-word quote; **medium** a reputable secondary source; **low** is inferred or backed by one weak source. Conflicts: the higher rank wins within its own area; newer beats older within a rank only when the newer source covers the point; a conflict the ranks settle is applied and disclosed with both citations; one they do not settle is reported and escalated with both citations; agents never pick a side silently; agent output never becomes a source.

## Hand checks

- IDs are unique (metrics, acceptance tests, context files, rules, examples, gates, systems, open questions, acceptance criteria).
- Every citation is well formed, is `[A:…]` or `[S:…]`, and its quote is at most 25 words. Every `[S:…]` names a context-inventory file; with `answers_ref`, every `[A:…]` names an answer and every quote is word for word in it.
- Every acceptance test's `words` are quoted from an answer (`[A:<id> "<the same words>"]`).
- Every input sample names a context-inventory file.
- The charter's class and every context file's class are in `config/data-classes.json`, and no file is classed above the charter.
- Ranks are exactly 1 to 5; every official file is in the context inventory.
- `users_and_stakeholders` has a user and an approver; every open question's owner is one of its roles.
- Every bad example names an existing quality rule.
- Every `write` system is named in the `before_write` of a gate placed before that write; a gate on review only does not count. Every `before_write` entry is a write system.
- Every gate's mode is `human` (automatic gates come in Phase 5, T0.15).
- Caps are no higher than the factory's (`config/caps.json`), and `critic_revisions` is no higher than `total_revisions_before_gate`.
- No "TBD", "TBC", "TODO", "to be decided/confirmed/determined", "don't know" or "???" outside `open_questions`.
