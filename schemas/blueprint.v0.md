# Ecosystem blueprint (schema v0, thin)

**From:** a charter v0 **To:** the generator (T1.3)
**Machine-checkable version:** [blueprint.v0.schema.json](blueprint.v0.schema.json)
**Example:** [docs/thin/blueprint.json](../docs/thin/blueprint.json)
**Hand checks:** `python engine/designcheck.py blueprint <file>`

v0 describes one author, one reviewer, one human gate. Blueprint v1 (T3.2) replaces it. Fields not listed here are rejected; anything unparseable fails. Paths in `charter_ref` and `evals[].path` are from the factory root; `output_schema` paths are inside the generated ecosystem and are found next to the blueprint (`<blueprint folder>/schemas/`) or in the factory's `schemas/`.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | text | yes | Must be `"0"`. |
| `slug` | text | yes | Folder name under `C:\ecosystems`; equals the charter's slug. |
| `charter_ref` | text | yes | The charter this design answers. |
| `purpose` | text | yes | One or two sentences. |
| `agents` | list | yes | Each `name` (lowercase-hyphen), `role` (`author` or `reviewer`), `purpose`, `instructions` (list), `tools` (only `Read`, `Grep`, `Glob`; never `Agent`), `max_turns` (1–20), `output_schema`. |
| `route` | object | yes | `name`, `author`, `reviewer` (agent names), `gate` (a gate ID). |
| `gates` | list | yes | Each `id`, `decision`, `mode` (`"human"`), `approver_role` (`"approver"`). |
| `caps` | object | yes | `critic_revisions`, `total_revisions_before_gate`, `gate_rejections`, `agent_calls_per_job`, `usage_ceiling` (`tokens`, `agent_minutes`); names as in `config/caps.json`, values no higher than the factory's. |
| `rulebook` | object | yes | `name`, `rules` (each `id`, `rule`, `severity`, `charter_rule`), optional `definitions` (sentences defining terms the rules use; not rules). Rendered as a rulebook table, then the reserved rules from `rules/default-agent-rules.md` (DR07), then the definitions. Rule IDs starting `DR` are reserved. |
| `final_output` | object | yes | `from` (the author), `rendered_as` (`"markdown-table"`), `columns`. |
| `evals` | list | yes | Each `suite`, `agent`, `kind` (`reviewer` or `agent`), `path`. |
| `external_writes` | `false` | yes | No external writes before G2. |
| `connectors` | list | yes | Must be empty in v0. |

## Hand checks

- The charter exists, passes its own checks and has the same slug.
- Agent names are unique; the route's author has role `author` and its reviewer role `reviewer`; the route's gate exists.
- Every agent's output schema exists; the reviewer's is `schemas/findings.schema.json`.
- Every charter quality rule has exactly one rulebook rule, with the same severity (never softer).
- Caps are no higher than the factory's (`config/caps.json`).
- `connectors` is empty.
- Every agent has an evaluation suite; each suite folder follows `evals/README.md`, meets the minimum case counts (`evals/thresholds.json`) and has at least one injection case and one real-length case. A reviewer suite also follows the suite design rules: at least a third of its cases subtle, some with 2 or more defects, a planted case and a clean near-miss twin for every blueprint rule (read from each key's `design` field). The reserved rule DR07 is planted by the injection cases: every injection case expects it, no other case may. A clean case has verdict pass and expects no blocker or major rule (it may expect DR07, which is minor). Context-dependent severity cases (rule 8) are not checked in v0: no rule's severity depends on context.
