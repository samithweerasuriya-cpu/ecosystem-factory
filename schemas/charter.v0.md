# Problem charter (schema v0, thin)

**From:** the problem owner's answers (T1.1) **To:** the blueprint
**Machine-checkable version:** [charter.v0.schema.json](charter.v0.schema.json)
**Example:** [docs/thin/charter.json](../docs/thin/charter.json)
**Hand checks:** `python engine/designcheck.py charter <file>`

v0 is the smallest charter that can drive the thin end-to-end version (Phase 1). Charter v1 (T2.1) replaces it. Fields not listed here are rejected; anything unparseable fails.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | text | yes | Must be `"0"`. |
| `slug` | text | yes | Lowercase, digits and hyphens, 2–41 characters. |
| `title` | text | yes | Short name of the problem. |
| `source` | text | yes | Where the problem owner's answers are recorded. |
| `outcome` | text | yes | What changes for people when this works. |
| `scope.in` / `scope.out` | lists of text | yes | What is in and out of scope; at least one each. |
| `input` | object | yes | `description`, `format`, `constraints` (list). |
| `output` | object | yes | `description`, `format`, `fields` (each `name`, `description`). |
| `quality_rules` | list | yes | Each `id` (`Q01`…), `text`, `severity` (`blocker`, `major`, `minor`) exactly as the problem owner gave it. |
| `examples.good` | list | yes | Each `text`. |
| `examples.bad` | list | yes | Each `text`, `why`, `breaks` (quality-rule IDs). |
| `gates` | list | yes | Each `id` (`G1`…), `decision`, `approver_role` (`"approver"`: the name comes from `config/gates.json`). |
| `data_classification` | `synthetic` or `public` | yes | v0 allows no internal data. |
| `external_writes` | `false` | yes | v0 allows none. |
| `open_questions` | list of text | yes | Unknowns, never guesses. |

## Hand checks

- Quality-rule and gate IDs are unique.
- Every bad example's `breaks` names an existing quality rule.
