# Problem brief

## 1. Title <!-- field: title -->
School library returns list

## 2. Short name <!-- field: slug -->
school-returns

## 3. Goal <!-- field: goal -->
At a primary school library, pupils drop returned books in a box at the door. When this works, the library helpers get one list each afternoon saying which books go back on the shelf and which go to the mending pile, so torn books stop going back out.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Library helpers (users: sort the box from the list). School librarian (approver: checks the list each afternoon). Pupils (stakeholders: borrow books in good condition).

## 5. Current process <!-- field: current_process -->
Steps: a helper empties the box, looks at each book and shelves it. Problems: torn books go back on the shelves; nobody records what was mended.

## 6. Scope <!-- field: scope -->
In: the day's returned books, typed into a list; a sorted list out. Out: overdue letters, buying books, the reading club.

## 7. Inputs <!-- field: inputs -->
A typed list of the day's returns: title, class, a note on condition. About 40 a day. No sample yet: samples will be made up for testing.

## 8. Glossary <!-- field: glossary -->
Mending pile: the shelf of books waiting for tape or glue.

## 9. Context pack <!-- field: context_inventory -->
None.

## 10. Data classification <!-- field: data_classification -->
*Default:* **synthetic**.

**Your answer:** keep default

## 11. Source policy <!-- field: source_policy -->
*Default:* five ranks, strongest first:

| Rank | What | Use for |
|---|---|---|
| 1 | The problem owner's own decisions and approved documents | Goals, scope, rules, terminology |
| 2 | Internal reference documents in the context pack | How things work here |
| 3 | Specifications and contracts | Exact names, fields, formats |
| 4 | Official documentation published by the maker of a product, on its own domain, and verified findings | Product behaviour |
| 5 | Everything else (third-party pages, community posts, earlier AI-assisted analyses, meeting summaries) | Leads only; never the only support for a claim |

Confidence: **high** needs a stored source of rank 4 or better with a word-for-word quote; **medium** a reputable secondary source; **low** is inferred or backed by one weak source. Conflicts: the higher rank wins within its own area; newer beats older within a rank only when the newer source covers the point; a conflict the ranks settle is applied and disclosed with both citations; one they do not settle is reported and escalated with both citations; agents never pick a side silently; agent output never becomes a source.

**Your answer:** keep default

## 12. Output format <!-- field: output -->
*Default:* a structured object (JSON) with named fields, checked by a script, plus a short readable summary for you.

**Your answer:** keep default

## 13. Quality rules <!-- field: quality_rulebook -->
*Default (starter rules):* Q01 every output item traces to an input (major); Q02 nothing is invented (blocker);
Q03 every required field is filled, or the gap is raised as an open question (major).

**Your answer:** keep default

## 14. Examples <!-- field: examples -->
Good: "The Quiet Owl | class 3 | no note | shelve". Good: "Rainy Day Games | class 1 | cover torn | mending pile". Bad: "Rainy Day Games | class 1 | cover torn | shelve, glued on 2099-02-03", because the mending date is not in the list (breaks Q02). Bad: "Moon Boat | shelve", because no book of that title is in the list (breaks Q01).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up returns, and every book with a torn cover is on the mending pile part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No torn book back on the shelves in a term.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the typed returns list. Writes nothing: the helpers move the books.

## 19. Gates <!-- field: gates -->
*Default:* one human gate: you approve the final output before it is used or written anywhere.

**Your answer:** keep default

## 20. Limits <!-- field: caps -->
*Default:* the factory's limits: 2 reviewer revision rounds, 3 revisions before the gate, 3 gate rejections, 25 agent
calls and 350,000 tokens or 20 agent minutes per job.

**Your answer:** keep default

## 21. Open questions <!-- field: open_questions -->
Should books from the staff room go through the same list? Owner: school librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
