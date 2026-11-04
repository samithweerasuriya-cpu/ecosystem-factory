# Problem brief

## 1. Title <!-- field: title -->
Returns desk triage

## 2. Short name <!-- field: slug -->
returns-desk

## 3. Goal <!-- field: goal -->
At Northgate library, books come back through the returns chute all day and wait in two crates. When this works, the shelving assistants get a sorted list at noon and at closing time saying which books go back on the shelf, which go to the reservations shelf for a reader and which go to the mending crate, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Shelving assistants (users: clear the crates from the list). Duty librarian (approver: signs off each list). Readers with reservations (stakeholders: find their reserved book waiting).

## 5. Current process <!-- field: current_process -->
Steps: an assistant empties the chute crates, scans each book, reads the screen for reservations and puts it on a trolley. Problems: about one reserved book in twenty ends up on the open shelves; torn books go out again to the next reader.

## 6. Scope <!-- field: scope -->
In: the chute returns since the last list in; a sorted list (shelve, reservations shelf, mending crate) out. Out: overdue charges, donations, the local history room.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, damage note, reservation flag. About 80 a day. Sample: chute-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Reservations shelf: the shelf by the desk for books waiting for the reader who reserved them. Mending crate: the crate for books that need mending before they go out again. Reservation flag: the export's yes or no for an open reservation. Check by hand: someone looks at the book before it is sorted.

## 9. Context pack <!-- field: context_inventory -->
chute-returns.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, reservations shelf, mending crate or check by hand) and the reason in one sentence. A line with no title is listed as 'check by hand'. It refuses to sort donations.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a damage note that is not blank sends the book to the mending crate (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Harbour Lights | no reservation, no damage | shelve". Good: "The Glass Orchard | reserved | reservations shelf". Bad: "The Glass Orchard | reserved | shelve", when it is reserved (breaks Q01). Bad: "Ten Small Hills | torn page | shelve", when its note says torn page (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I run two days of made-up chute returns through it, and every reserved book is on the reservations shelf part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book on the open shelves in a month. Agent-checkable: faster triage.

## 17. Risk <!-- field: risk -->
Partly reversible: a book on the wrong shelf can be moved back, but a reader who was told it is ready leaves without it.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the assistants move the books and the duty librarian updates the catalogue.

## 19. Gates <!-- field: gates -->
I sign off each list before the crates are cleared.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Do inter-library loans get their own decision? Owner: duty librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
