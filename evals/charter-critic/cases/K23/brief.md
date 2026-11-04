# Problem brief

## 1. Title <!-- field: title -->
Weekend returns sorter

## 2. Short name <!-- field: slug -->
weekend-returns

## 3. Goal <!-- field: goal -->
At the Station Road library, Monday mornings start with two days of weekend returns on the floor by the desk. When this works, the Monday volunteers get a sorted list on Monday at 09:00 saying which books go back on the shelf, which go to the collection shelf for a reader and which go to the damaged-books bag, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Monday volunteers (users: work through the weekend pile from the list). Ruth Calloway (approver: looks over the list on Monday morning). Readers with reservations (stakeholders: hear on Monday that their book is in).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer picks up each book from the pile, scans it, reads the reservation and condition notes and shelves it. Problems: Monday reservations are missed until Wednesday; damaged books are shelved with the rest.

## 6. Scope <!-- field: scope -->
In: Saturday's and Sunday's returns in; a sorted list (shelve, collection shelf, damaged-books bag) out. Out: Monday's own returns, fines, the home delivery service.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. About 200 each weekend. Sample: weekend-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Collection shelf: the shelf of reserved books waiting to be collected. Damaged-books bag: the bag of books going to the county repair service. Reservation flag: the export's yes or no for an open reservation. Check by hand: someone looks at the book before it is sorted.

## 9. Context pack <!-- field: context_inventory -->
weekend-returns.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, collection shelf, damaged-books bag or check by hand) and the reason in one sentence. A book with a blank reservation flag is listed as 'check by hand'. It refuses to sort Monday's own returns.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the damaged-books bag (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Ironbridge Tales | no reservation | shelve". Good: "Small Wild Things | reserved | collection shelf". Bad: "Small Wild Things | reserved | shelve", because it is reserved (breaks Q01). Bad: "A Map of Rain | cover torn off | shelve", because the cover is torn off (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it three made-up weekends, and every reserved book is on the collection shelf part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No Monday reservation missed in a quarter. Every weekend reserved book is on the collection shelf by 11:00 on Monday.

## 17. Risk <!-- field: risk -->
Partly reversible: a missed reservation can be fixed on Tuesday, but the reader has lost two days.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the volunteers move the books and update the loans system.

## 19. Gates <!-- field: gates -->
Ruth looks over the list at 09:00 before the volunteers start.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should books for the county repair service be listed separately? Owner: Monday volunteers.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
