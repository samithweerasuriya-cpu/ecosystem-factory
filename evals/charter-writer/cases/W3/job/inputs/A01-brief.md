# Problem brief

## 1. Title <!-- field: title -->
Evening repair queue

## 2. Short name <!-- field: slug -->
evening-repairs

## 3. Goal <!-- field: goal -->
At the Ferry Road community bike workshop, people leave bikes on weekday evenings with a paper slip. When this works, the workshop lead gets a repair queue each evening built from the slips, with bench minutes and a promised date for each bike, so customers are given dates the workshop can keep.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Volunteer mechanics (users: take the next job from the queue). Workshop lead (approver: approves the queue each evening). Customers (stakeholders: get their bike back on the promised date).

## 5. Current process <!-- field: current_process -->
Steps: the lead reads the slips, guesses each job's time and writes the queue on a whiteboard. Problems: promised dates are often missed; brake jobs wait behind long wheel builds.

## 6. Scope <!-- field: scope -->
In: the evening's drop-off slips; a repair queue out. Out: parts ordering, bike sales, e-bike motor faults.

## 7. Inputs <!-- field: inputs -->
Typed drop-off slips: ticket number, bike, the customer's description of the fault and the date they need it. About 10 an evening. No sample yet: samples will be made up for testing.

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table the lead keeps. Truing: straightening a wheel so it spins without a wobble.

## 9. Context pack <!-- field: context_inventory -->
None.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the slip (major).

## 14. Examples <!-- field: examples -->
Good: "F-12 | hybrid | brakes | 30 | 2099-07-07 | 'front brake rubs'". Good: "F-13 | road | wheels | 60 | 2099-07-09 | 'back wheel wobbles'". Bad: "F-14 | town | gears | 45 | 2099-07-06", when three hours of work are ahead of it (breaks Q01). Bad: "F-15 | kids | brakes | 20, after F-13", when a brake job sits behind a wheel job (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
Don't know yet.

## 16. Success metrics <!-- field: success_metrics -->
Nine promised dates in ten are kept over a month. No brake job waits more than two evenings.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the typed slips. Writes nothing: the lead copies the queue onto the whiteboard.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should e-bikes with no motor fault join this queue? Owner: workshop lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
