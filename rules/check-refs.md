# Reference-check rulebook

Mechanical rules applied by `engine/check_refs.py` to every new artifact version, before any agent reviewer. All are blockers: an artifact with an unresolved or stale reference goes back to its author.

| ID | Rule | Sev |
|---|---|---|
| REF01 | Every repo path in the artifact exists. | blocker |
| REF02 | Every job ID and input ID (`[A:<id>]`) in the artifact resolves. | blocker |
| REF03 | The artifact does not point to another draft of its own job. | blocker |
