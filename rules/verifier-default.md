# Default verifier rulebook

Judgement rules for any verifier, adapted from the author's earlier private lab. The mechanical checks (a citation is present and registered, the source was stored by script, quotes are verbatim, ranks fit the claim type) run first by script (`rules/check-evidence.md`); the verifier judges what a script cannot. Generated ecosystems extend this from their charter's source policy.

| ID | Rule | Sev |
|---|---|---|
| VR01 | Each cited source actually supports the claim it is attached to (read the stored copy around the cited location). | blocker |
| VR02 | Factual sentences listed as uncited by the evidence check are either cited or turned into open questions. | major |
| VR03 | Conflicts between sources are disclosed with both citations, not resolved silently. | major |
| VR04 | Names of systems, interfaces, fields and objects appear in a cited source. | blocker |
| VR05 | Numbers, dates and versions match the source. | major |
| VR06 | Open questions are not presented as decided facts anywhere in the text. | major |
| VR07 | A decision cites the approver's answer or an approved artifact that actually states it. | blocker |
