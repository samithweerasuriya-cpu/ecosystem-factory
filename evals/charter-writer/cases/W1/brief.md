# Problem brief

## 1. Title <!-- field: title -->
Returns cart sorter

## 2. Short name <!-- field: slug -->
returns-cart

## 3. Goal <!-- field: goal -->
At the Fernhill branch library, returned books wait on a cart until someone has time. When this works, the returns volunteers get one sorted list each morning saying which books go back on the shelf, which go to the reserved shelf and which go to the repair bin, so reserved books stop disappearing onto the open shelves.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Returns volunteers (users: sort the cart from the list). Branch supervisor (approver: checks the list each morning). Readers with reservations (stakeholders: find their book waiting).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer takes each book from the cart, looks it up for a reservation, checks it for damage and shelves it. Problems: about one reserved book a week ends up on the open shelves; damaged books go back out to readers.

## 6. Scope <!-- field: scope -->
In: the morning's returns export; a sorted list (shelve, reserved shelf, repair bin) out. Out: fines, book sales, the home delivery service.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. About 60 a day. Sample: returns-sample.txt (made up).

## 8. Glossary <!-- field: glossary -->
Reserved shelf: the shelf by the desk for books a reader has reserved. Repair bin: the bin of books waiting to be mended.

## 9. Context pack <!-- field: context_inventory -->
returns-sample.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the repair bin (major). Q03 every row quotes the barcode from the export (major).

## 14. Examples <!-- field: examples -->
Good: "510201 | The Wren's Year | shelve". Good: "510202 | Harbour Songs | reserved shelf". Bad: "510202 | Harbour Songs | shelve", because it is reserved (breaks Q01). Bad: "510203 | Tin Lanterns | shelve", because its note says pages wet (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up returns, and no reserved book is on the shelve part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book on the open shelves in a month.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the volunteers move the books by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should books reserved at another branch go on our reserved shelf? Owner: branch supervisor.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
