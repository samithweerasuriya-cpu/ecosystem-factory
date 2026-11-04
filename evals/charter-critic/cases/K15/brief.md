# Problem brief

## 1. Title <!-- field: title -->
Branch returns sorter

## 2. Short name <!-- field: slug -->
branch-returns

## 3. Goal <!-- field: goal -->
At the Riverside branch library, returns arrive from the drop box, the counter and the overnight chute. When this works, the library assistants get a sorted list at opening time saying which books go back on the shelf, which go to the hold shelf for a reader and which go to the repair trolley, so reserved books stop getting shelved by mistake.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Library assistants (users: sort the returns from the list). Branch manager (approver: checks the list before opening). Readers with reservations (stakeholders: have their reserved book ready when they are told it is). Courier driver (stakeholder: gets the courier crate packed by closing time).

## 5. Current process <!-- field: current_process -->
Steps: an assistant scans each returned book, checks the screen for reservations and home branch, looks for damage and puts it on a shelving trolley. Problems: reserved books end up on the open shelves, so readers are told a book is ready that nobody can find; books from other branches sit here for weeks. Books from other branches wait in a corner until someone has time to pack the crate, and nobody checks group loans for missing copies.

## 6. Scope <!-- field: scope -->
In: the overnight and morning returns in; a sorted list (shelve, hold shelf, repair trolley) out. Out: fines, new purchases, the mobile library, sorting another branch's books beyond listing them for the courier crate.

## 7. Inputs <!-- field: inputs -->
A plain-text export of the returns: barcode, title, condition note, reservation flag. Volume not counted yet. Sample: overnight-returns.txt (made up). The branch barcode ranges are in branch-ranges.txt (made up).

## 8. Glossary <!-- field: glossary -->
Hold shelf: the shelf by the issue desk for reserved books, kept for 7 days. Repair trolley: the trolley of books going to the mending table. Reservation flag: the export's yes or no for an open reservation. Courier crate: the crate that goes to the central library each evening, for books that belong to another branch. Group loan: a set of copies lent to one school class or reading group. Home branch: the branch whose barcode range a book is in. Issue desk: the counter where loans and returns are scanned. Barcode range: the run of barcode numbers given to one branch. Spine split: the binding has cracked so pages can come loose. Check by hand: an assistant looks at the book before it is sorted.

## 9. Context pack <!-- field: context_inventory -->
overnight-returns.txt, synthetic, evidence for the input format. branch-ranges.txt, synthetic, evidence for which barcodes belong to this branch.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A list, one row per returned book: barcode, title, decision (shelve, hold shelf, repair trolley or check by hand) and the reason in one sentence. A book with a blank reservation flag is listed as 'check by hand', and it refuses to decide anything for another branch's books beyond listing them for the courier crate. It refuses to sort books from the mobile library.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a book with a reservation flag never goes to shelve (blocker). Q02 a condition note that mentions damage sends the book to the repair trolley (major). Q03 every row quotes the barcode from the export (major). Q04 the reason is one sentence (minor). Q05 a book returned from another branch is listed for the courier crate, not shelved here (major). Q06 a book whose barcode is in no branch's range is listed as 'check by hand' (major). Q07 a class or group loan returned in part is flagged as incomplete (major). Q08 titles are copied exactly, with no shortening (minor).

## 14. Examples <!-- field: examples -->
Good: "Lanterns at Dusk | no reservation, home branch, no damage | shelve". Good: "The Fox and the Ferry | reserved | hold shelf". Bad: "The Fox and the Ferry | reserved | shelve", when its reservation flag is set (breaks Q01). Bad: "Copper Hill | spine split | shelve", when its note says spine split (breaks Q02). Good: "Moonlit Quarry | home branch Eastfield | listed for the courier crate". Bad: "Moonlit Quarry | home branch Eastfield | shelve", when it belongs to Eastfield (breaks Q05). Bad: "Year 4 reading set | 22 of 30 copies | shelve", when 8 copies are missing (breaks Q07). Good: "Year 6 class set | 30 of 30 copies | shelve".

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it three made-up nights of returns, and no reserved book is on the shelve part of the list. I give it a night of returns with five Eastfield books, and all five are listed for the courier crate. I give it a class set with three copies missing, and it is flagged as an incomplete group loan, not shelved.

## 16. Success metrics <!-- field: success_metrics -->
No reserved book on the open shelves in a month. Every reserved book is on the hold shelf before opening on the day after it comes back. No other branch's book is still here a week after it came back.

## 17. Risk <!-- field: risk -->
Partly reversible: a misplaced book can be found and moved, but a reader told their book is ready may make a wasted trip.

## 18. Systems <!-- field: systems -->
Reads the returns export and the branch barcode ranges (branch-ranges.txt). Writes nothing: the assistants move the books and update the loans system by hand.

## 19. Gates <!-- field: gates -->
I check the list before opening, before anyone touches the returns.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should a reserved book that belongs to another branch stay here for the reader or go back in the crate? Owner: branch manager. Should the hold shelf keep books for 7 days or 10? Owner: branch manager. Who packs the courier crate on a Saturday, when the branch closes at 13:00? Should damaged books that belong to another branch be mended here or sent back as they are? Owner of both: branch manager. Does a reading group's set count as a group loan when only some members borrowed it? Owner: library assistants.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
