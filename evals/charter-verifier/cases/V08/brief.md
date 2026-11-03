# Problem brief

## 1. Title <!-- field: title -->
Reserved returns sorter

## 2. Short name <!-- field: slug -->
reserved-returns

## 3. Goal <!-- field: goal -->
At the Hillcrest branch library, returns pile up in the returns room until a volunteer is free. When this works, the returns team get a sorted list each morning saying which books go back on the shelf, which go to the holds shelf for a reader and which go to the repair box, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Returns team (users: sort the trolley from the list). Branch librarian (approver: checks the list before the books are moved). Readers with reservations (stakeholders: get their book on time).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer takes each book off the trolley, looks it up for reservations, checks it for damage, then shelves it. Problems: reserved books get shelved by mistake, so readers wait days; damaged books go back on the shelf.

## 6. Scope <!-- field: scope -->
In: the morning's returns in; a sorted list (shelve, holds shelf, repair box) out. Out: fines, new purchases, the mobile library.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. About 120 a day. Sample: hillcrest-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Holds shelf: the shelf behind the desk for reserved books, kept for 7 days. Repair box: the box of books waiting for tape, glue or a new cover. Reservation flag: the export's yes or no for an open reservation.

## 9. Context pack <!-- field: context_inventory -->
hillcrest-returns.txt, synthetic, evidence for the input format. desk-guide.txt, synthetic, evidence for desk routines.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, holds shelf or repair box) and the reason in one sentence. A book with no barcode is listed as 'check by hand'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the repair box (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Kettle Hill | no reservation, no damage | shelve". Good: "A Map of Rain | reserved | holds shelf". Bad: "A Map of Rain | reserved | shelve", when its reservation flag is set (breaks Q01). Bad: "The Copper Fox | split spine | shelve", when its note says split spine (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up returns, and no reserved book is ever on the shelve part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book shelved by mistake in a month. Every reserved book is on the holds shelf by 10:00 on the day it comes back.

## 17. Risk <!-- field: risk -->
Partly reversible: a shelved reserved book can be found again, but the reader may already have been told it is lost.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the volunteers move the books and update the loans system by hand.

## 19. Gates <!-- field: gates -->
I check the sorted list before the books are moved.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should books reserved by another branch go to the holds shelf or the courier crate? Owner: branch librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
