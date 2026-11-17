# Evidence-check rulebook

Mechanical rules applied by `engine/evidence.py` to every new artifact version, after the reference check and before any agent reviewer. All are blockers: the artifact goes back to its author.

Citation forms: `[S:<id> §<location>]` or `[S:<id> §<location> "exact words"]` back a **fact**; `[A:<id>]` (or `[A:<id> "exact words"]`) and `[G:<job>]` back a **decision**. A JSON artifact is checked as its decoded string values, so the quote marks around a quote are plain `"` there.

Source ranks: web pages take the evidence settings' domain table (rank 5 if unlisted). Files take the settings' file table; in an intake job, a file in the owner's context pack (`inputs/context/`) is rank 2 unless the brief's source policy gives it a rank (a line naming the file and "rank N"; an unreadable or conflicting rank there counts as rank 5). Any other file is rank 5. Decided by Samith, 2026-11-16.

| ID | Rule | Sev |
|---|---|---|
| E01 | Every `[S:...]` citation names a source in the job's evidence registry. | blocker |
| E02 | Every cited source was stored by the fetch script, and an unfetchable source does not back a high-confidence claim. | blocker |
| E03 | Every quote appears word for word in the stored copy (whitespace and quote marks normalised). | blocker |
| E04 | Each claim type follows its own rule: a fact cites a source of the required rank or better; a decision cites the approver's recorded answers or an approved artifact (valid gate token). | blocker |
| E05 | No quote is longer than the configured maximum (25 words). | blocker |
| E06 | The stored copy of every cited source is present and its fingerprint matches the registry. | blocker |
| E07 | Every citation is in a readable form: text that opens like a citation (`[S:`, `[A:`, `[G:`) but does not parse in full, or a JSON artifact that does not parse, fails; it never passes unchecked. | blocker |
