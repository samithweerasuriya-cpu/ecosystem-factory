# Problem brief

## 1. Title <!-- field: title -->
Returns sorting list

## 2. Short name <!-- field: slug -->
returns-list

## 3. Goal <!-- field: goal -->
At the Marsh Lane library, returns come in at the counter and wait in a tray behind it. When this works, the counter staff get a sorted list twice a day saying which books go back on the shelf, which go to the reserve shelf for a reader and which go to the repair crate, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Counter staff (users: sort the tray from the list). Senior librarian (approver: approves each list). Readers with reservations (stakeholders: collect their book when the library says it is ready).

## 5. Current process <!-- field: current_process -->
Steps: a member of counter staff takes each book from the tray, checks the loans screen for a reservation, looks it over and shelves it. Problems: reserved books are missed in the tray, and readers are sent away; books with broken spines go back out.

## 6. Scope <!-- field: scope -->
In: the counter tray's returns in; a sorted list (shelve, reserve shelf, repair crate) out. Out: reader accounts, book sales, the reading group sets.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. About 90 a day. Sample: tray-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Reserve shelf: the shelf of reserved books waiting for their reader. Repair crate: the crate of books going to the repair volunteer on Fridays. Reservation flag: the export's yes or no for an open reservation. Check by hand: someone looks at the book before it is sorted.

## 9. Context pack <!-- field: context_inventory -->
tray-returns.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, reserve shelf, repair crate or check by hand) and the reason in one sentence. A line with a blank reservation flag is listed as 'check by hand'. It refuses to sort reading group sets. A book that is both reserved and damaged goes to the repair crate.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the repair crate (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor). Q05 a reserved book can be found quickly on the list (minor).

## 14. Examples <!-- field: examples -->
Good: "Ash and Ember | no reservation | shelve". Good: "The Tidal Clock | reserved | reserve shelf". Bad: "The Tidal Clock | reserved | shelve", when it has a reservation (breaks Q01). Bad: "North of Nowhere | broken spine | shelve", when the note says broken spine (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a fortnight of made-up tray returns, and no book with a reservation is on the shelve part.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book shelved by mistake in a term. Reserved books reach the reserve shelf by the next list after they come back.

## 17. Risk <!-- field: risk -->
Partly reversible: a reserved book can be pulled from the shelves, but a reader who was sent away may not come back.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: counter staff move the books and update the loans screen.

## 19. Gates <!-- field: gates -->
I approve each list before the tray is sorted.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should a book reserved by two readers say which one is first? Owner: senior librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
