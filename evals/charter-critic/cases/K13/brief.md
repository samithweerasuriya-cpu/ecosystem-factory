# Problem brief

## 1. Title <!-- field: title -->
Bike drop-off triage

## 2. Short name <!-- field: slug -->
dropoff-triage

## 3. Goal <!-- field: goal -->
At the Old Depot bike shed, commuters drop bikes off before work and collect them in the evening. When this works, the shed manager gets by 08:30 a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so every bike promised for the evening is ready by 17:30.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Mechanics (users: take jobs from the queue in order). Shed manager (approver: checks the queue at 08:30). Customers (stakeholders: their bike ready by 17:30 when promised).

## 5. Current process <!-- field: current_process -->
Steps: the manager reads the drop-off tags, decides what can be done today and tells each mechanic their jobs. Problems: three or four commuters a week find their bike not ready at 17:30; bolts get tightened by feel, not to the maker's torque.

## 6. Scope <!-- field: scope -->
In: the morning's drop-off tags in; a repair queue out. Out: bike sales, hire bikes, the Saturday maintenance class.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 20 each morning. Sample: dropoff-tags.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Torque: how tight a bolt is, in newton metres. Same-day job: a bike promised back by 17:30 the day it was dropped off.

## 9. Context pack <!-- field: context_inventory -->
dropoff-tags.txt, synthetic, evidence for the input format. bench-times.txt, synthetic, evidence for bench minutes. torque-chart.txt, public (copied from a component maker's website), evidence for bolt torques.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A tag with no fault description is refused as 'ask at the counter'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (minor).

## 14. Examples <!-- field: examples -->
Good: "D-31 | commuter | brakes | 25 | 2099-03-10 | 'brakes squeal in the wet'". Good: "D-32 | folding | gears | 35 | 2099-03-10 | 'skips in third gear'". Bad: "D-33 | road | wheels | 90 | 2099-03-10", when only 60 minutes are left in the day (breaks Q01). Bad: "D-34 | hybrid | brakes | 20, after D-32", when a brake job sits behind a gear job (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a fortnight of made-up tags, and every bike promised for 17:30 fits in the day's bench time.

## 16. Success metrics <!-- field: success_metrics -->
No more than one same-day bike a week not ready at 17:30. Every brake job is finished before noon.

## 17. Risk <!-- field: risk -->
Partly reversible: the queue can change during the day, but a commuter without a bike at 17:30 has to find another way home.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes nothing: the manager reads the queue out to the mechanics.

## 19. Gates <!-- field: gates -->
I check the queue at 08:30 before I read it out.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should the torque chart cover carbon parts? Owner: shed manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
