# Problem brief

## 1. Title <!-- field: title -->
School library returns sorter

## 2. Short name <!-- field: slug -->
school-returns

## 3. Goal <!-- field: goal -->
At the secondary school library, pupils drop books in the returns box all day. When this works, the library helper gets a sorted list at the end of each school day saying which books go back on the shelf, which go to the reserved shelf for a pupil, and which go to the repair tray, so reserved books reach pupils the next morning.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Library helpers (users: empty the returns box and sort it from the list). School librarian (approver: checks the list before the helpers act on it). Pupils with reservations (stakeholders: want their book the next morning). Subject teachers (stakeholders: class sets come back complete).

## 5. Current process <!-- field: current_process -->
Steps: a helper empties the returns box, looks each book up on the loans screen for reservations, checks it for damage and shelves it. Problems: reserved books get shelved by mistake, so pupils wait up to a week; class sets go back with missing copies nobody notices.

## 6. Scope <!-- field: scope -->
In: one school day's returned books in; a sorted list (shelve, reserved shelf, repair tray) out. Out: overdue letters, buying books, the staff room collection.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the day's returns: barcode, title, condition note, reservation flag. About 60 a day. Sample: returns-export.txt (made up).

## 8. Glossary <!-- field: glossary -->
Reserved shelf: the shelf behind the desk for books a pupil has reserved. Class set: 30 copies of one title lent to one class. Repair tray: books waiting for tape or a new cover.

## 9. Context pack <!-- field: context_inventory -->
returns-export.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per returned book: barcode, title, decision (shelve, reserved shelf or repair tray) and the reason in one sentence. A book with no barcode is listed as "check by hand".

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to "shelve" (blocker). Q02 a condition note that mentions damage sends the book to the repair tray (major). Q03 every row quotes the barcode from the export (minor).

## 14. Examples <!-- field: examples -->
Good: "0041 | Storm Island | reserved shelf | reservation flag set". Good: "0187 | Moths of the Marsh | repair tray | condition note: torn spine". Bad: "0041 | Storm Island | shelve", when its reservation flag is set (breaks Q01). Bad: "0187 | Moths of the Marsh | shelve", when the note says torn spine (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up return exports, and no book with a reservation flag is ever on the shelve part of the list.

## 16. Success metrics <!-- field: success_metrics -->
Make returns easier for everyone.

## 17. Risk <!-- field: risk -->
Reversible: a wrongly shelved book can be pulled back the next day. Affects pupils at this school only.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the helpers move the books and update the loans screen by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should class sets be checked for missing copies here or by the teacher? Owner: school librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On a week of made-up return exports, no reserved book is listed under shelve and every damaged book is under repair tray.
