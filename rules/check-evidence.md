# Evidence-check rulebook

Mechanical rules applied by `engine/evidence.py` to every new artifact version, after the reference check and before any agent reviewer. All are blockers: the artifact goes back to its author.

Citation forms: `[S:<id> §<location>]` or `[S:<id> §<location> "exact words"]` back a **fact**; `[A:<id>]` (or `[A:<id> "exact words"]`) and `[G:<job>]` back a **decision**.

| ID | Rule | Sev |
|---|---|---|
| E01 | Every `[S:...]` citation names a source in the job's evidence registry. | blocker |
| E02 | Every cited source was stored by the fetch script, and an unfetchable source does not back a high-confidence claim. | blocker |
| E03 | Every quote appears word for word in the stored copy (whitespace and quote marks normalised). | blocker |
| E04 | Each claim type follows its own rule: a fact cites a source of the required rank or better; a decision cites the approver's recorded answers or an approved artifact (valid gate token). | blocker |
| E05 | No quote is longer than the configured maximum (25 words). | blocker |
| E06 | The stored copy of every cited source is present and its fingerprint matches the registry. | blocker |
