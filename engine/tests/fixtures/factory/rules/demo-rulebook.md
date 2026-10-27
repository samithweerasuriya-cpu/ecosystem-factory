# Demo rulebook

Rulebook for the demo route's stand-in reviewers (T0.10). Rulebook format for every reviewer: one table row per rule, the first cell is the rule ID, and one cell holds its severity. Severity: **blocker** (cannot pass) · **major** (fail) · **minor** (note only). Verdict fails on any blocker or major.

| ID | Rule | Sev |
|---|---|---|
| DM01 | The artifact answers the goal in the brief. | blocker |
| DM02 | Every section named in the template is present. | major |
| DM03 | Open questions are listed, not guessed. | major |
| DM04 | Wording is concise. | minor |
