# Problem brief

## 1. Title <!-- field: title -->
Return slot sorter

## 2. Short name <!-- field: slug -->
return-slot

## 3. Goal <!-- field: goal -->
At Millbrook library, books come back through the return slot overnight and wait in a bin. When this works, the early-shift assistants get a sorted list before opening saying which books go back on the shelf, which go to the reservation shelf for a reader and which go to the mending tray, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Early-shift assistants (users: sort the trolley from the list). Senior librarian (approver: signs off the list before the bin is emptied). Readers with reservations (stakeholders: get their book on time).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer takes each book off the trolley, looks it up for reservations, checks it for damage, then shelves it. Problems: reserved books get shelved by mistake, so readers wait days; damaged books go back on the shelf.

## 6. Scope <!-- field: scope -->
In: the morning's returns in; a sorted list (shelve, reservation shelf, mending tray) out. Out: fines, new purchases, the mobile library.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. About 90 a day. Sample: slot-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Reservation shelf: the shelf by the entrance for books a reader has reserved. Mending tray: the tray of books waiting to be mended. Reservation flag: the export's yes or no for an open reservation.

## 9. Context pack <!-- field: context_inventory -->
slot-returns.txt, synthetic, evidence for the input format. bad-examples.txt, synthetic, evidence for bad examples.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, reservation shelf or mending tray) and the reason in one sentence. A book with no barcode is listed as 'check by hand'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the mending tray (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Field Notes | no reservation, no damage | shelve". Good: "The Clockmaker | reserved | reservation shelf". Bad: "The Clockmaker | reserved | shelve", when its reservation flag is set (breaks Q01). Bad: "Blue Orchard | coffee stain | shelve", when its note says coffee stain (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up returns, and no reserved book is ever on the shelve part of the list.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book shelved by mistake in a month. Every reserved book is on the holds shelf by 10:00 on the day it comes back.

## 17. Risk <!-- field: risk -->
Partly reversible: a shelved reserved book can be found again, but the reader may already have been told it is lost.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the volunteers move the books and update the loans system by hand.

## 19. Gates <!-- field: gates -->
I sign off the sorted list before the bin is emptied.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should books reserved by another branch go to the holds shelf or the courier crate? Owner: senior librarian.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
