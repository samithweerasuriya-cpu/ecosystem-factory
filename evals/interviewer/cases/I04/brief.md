# Problem brief

## 1. Title <!-- field: title -->
Repair queue sorter

## 2. Short name <!-- field: slug -->
repair-queue

## 3. Goal <!-- field: goal -->
Drop-off forms pile up on Saturdays. When this works, the workshop lead gets a sorted repair queue each morning, every ticket with its job type, bench time and promised date, and riders get a realistic pickup date instead of "sometime next week".

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Mechanics (users: work the queue top-down). Workshop lead (approver: signs off the queue before it goes on the board). Riders (stakeholders: want their bike back on the promised date).

## 5. Current process <!-- field: current_process -->
Steps: the rider fills in a paper drop-off form; the workshop lead reads the forms, guesses bench time and writes tickets on the board. Problems: wheel builds and bleeds get under-quoted, so promised dates slip; last month 9 of 40 tickets missed their date.

## 6. Scope <!-- field: scope -->
In: the day's drop-off forms in; a sorted queue with bench time and promised date out; the approved queue written to the repair-queue board. Out: parts ordering, payments, the mobile repair van.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed up as text: ticket number, bike type, the rider's description, drop-off date. 10 to 25 a day. Sample: dropoff-sample.txt.

## 8. Glossary <!-- field: glossary -->

## 9. Context pack <!-- field: context_inventory -->
dropoff-sample.txt, synthetic, evidence for the input format. bench-times.txt, synthetic, evidence for standard bench minutes per job type.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
Queue rows: ticket, job type, bench minutes, mechanic level (any or senior), promised date, quoted form line. A form whose job isn't on the bench-times list gets job type "unlisted" and no promised date.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the job type comes from the bench-times list; anything not on it is flagged, never guessed (blocker). Q02 the promised date allows for the bench minutes at 6 bench hours a day (major). Q03 bleeds and wheel builds go to a senior mechanic (major). Q04 each row quotes the form line (minor).

## 14. Examples <!-- field: examples -->
Good: "T-118 | true a wheel | 30 | any | 2099-06-10 | 'front wheel wobbles'". Good: "T-121 | bleed a hydraulic brake | 45 | senior | 2099-06-10 | 'rear brake spongy'". Bad: "T-121 | bleed a hydraulic brake | 45 | any | 2099-06-10 | 'rear brake spongy'" (breaks Q03). Bad: "T-125 | service a hub | 60 | any | 2099-06-11 | 'creaks somewhere'" (breaks Q01: the job was guessed).

## 15. Acceptance tests <!-- field: acceptance_tests -->
Run a Saturday's forms through it: every bleed and wheel build lands on a senior, and no promised date slips over the next two weeks.

## 16. Success metrics <!-- field: success_metrics -->
Fewer than 1 ticket in 20 misses its promised date. Agent-checkable: every job type is on the bench-times list or marked unlisted.

## 17. Risk <!-- field: risk -->
Reversible until the board is updated; once a date is on the board, riders plan around it. Affects riders, so outside the workshop.

## 18. Systems <!-- field: systems -->
Reads the typed-up forms. Writes the repair-queue board.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Do e-bike motor jobs belong in this queue? Owner: workshop lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On two Saturdays of made-up forms, every job type matches the bench-times list and every bleed and wheel build goes to a senior.
