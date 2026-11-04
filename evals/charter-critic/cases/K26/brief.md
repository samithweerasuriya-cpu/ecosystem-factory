# Problem brief

## 1. Title <!-- field: title -->
Morning returns list

## 2. Short name <!-- field: slug -->
morning-returns

## 3. Goal <!-- field: goal -->
At the Hollins Road community library, the overnight returns bin fills up every night. When this works, the volunteer shelvers get a sorted list before the doors open saying which books go back on the shelf, which go to the pick-up shelf for a reader and which go to the fix-it tub, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Volunteer shelvers (users: empty the bin and shelve from the list). Library coordinator (approver: reads the list and agrees it). Readers with reservations (stakeholders: pick up reserved books the day they are told).

## 5. Current process <!-- field: current_process -->
Steps: a shelver empties the bin, types each barcode into the loans screen, checks for a reservation and a damage note, and shelves the book. Problems: readers are told a book is waiting when it has gone back on the shelves; books with loose pages go out again.

## 6. Scope <!-- field: scope -->
In: the overnight bin's returns in; a sorted list (shelve, pick-up shelf, fix-it tub) out. Out: membership cards, late charges, the toy library.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, damage note, reservation flag. Around 45 a night. Sample: bin-returns.txt (made up).

## 8. Glossary <!-- field: glossary -->
Pick-up shelf: the shelf by the door where readers collect what they reserved. Fix-it tub: the tub of books with loose pages or broken spines. Reservation flag: the export's yes or no for an open reservation.

## 9. Context pack <!-- field: context_inventory -->
bin-returns.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, pick-up shelf or fix-it tub) and the reason in one sentence.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a damage note that is not blank sends the book to the fix-it tub (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Garden of Stones | none | shelve". Good: "The Last Lighthouse | reserved | pick-up shelf". Bad: "The Last Lighthouse | reserved | shelve", although it is reserved (breaks Q01). Bad: "Clay and Kiln | loose pages | shelve", although the note says loose pages (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it ten made-up nights of the bin, and every reserved book is under pick-up shelf.

## 16. Success metrics <!-- field: success_metrics -->
No reader told a book is waiting when it is not, over a month. Every reserved book is on the pick-up shelf when the doors open.

## 17. Risk <!-- field: risk -->
Reversible: the shelvers can move a book again the same day. Readers of this library only.

## 18. Systems <!-- field: systems -->
Reads the returns export. Writes nothing: the shelvers move the books and mark the loans screen by hand.

## 19. Gates <!-- field: gates -->
I agree the list before the shelvers start.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should the fix-it tub list say what is wrong with each book? Owner: library coordinator.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
