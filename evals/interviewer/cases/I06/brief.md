# Problem brief

## 1. Title <!-- field: title -->
Returns triage

## 2. Short name <!-- field: slug -->
returns-triage

## 3. Goal <!-- field: goal -->
At the branch library, returned books pile up on the returns trolley. When this works, the returns volunteers get a sorted list each morning saying which books go back on the shelf, which go for repair and which go to the holds shelf for a reader, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Returns volunteers (users: sort the trolley from the list). Branch librarian (approver: checks the list each morning). Readers with reservations (stakeholders: get their book on time).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer takes each returned book, looks it up for reservations, checks it for damage, then shelves it. Problems: reserved books get shelved by mistake, so readers wait days; damaged books go back on the shelf.

## 6. Scope <!-- field: scope -->
In: the morning's returns in; a sorted list (shelve, repair, holds shelf) out. Out: fines, new purchases, the mobile library.

## 7. Inputs <!-- field: inputs -->

## 8. Glossary <!-- field: glossary -->
None.

## 9. Context pack <!-- field: context_inventory -->
None.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
keep default

## 14. Examples <!-- field: examples -->
Good: "The Salt Road | no reservation, no damage | shelve". Good: "Winter Birds | reserved | holds shelf". Bad: "Night Garden | holds shelf | reserved by reader 4471", when the returns show no reservation for it (breaks Q02: the reservation is invented). Bad: "River Maps | (no decision)" (breaks Q03: a required field is empty).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a morning's returns, and every reserved book is on the holds-shelf part of the list and none is on the shelve part.

## 16. Success metrics <!-- field: success_metrics -->

## 17. Risk <!-- field: risk -->

## 18. Systems <!-- field: systems -->

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
