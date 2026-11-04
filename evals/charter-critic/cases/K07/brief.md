# Problem brief

## 1. Title <!-- field: title -->
Service queue planner

## 2. Short name <!-- field: slug -->
service-queue

## 3. Goal <!-- field: goal -->
At the Riverside cycle co-op, service bookings and walk-ins are dropped off at the counter with a job card. When this works, the co-op manager gets every evening for the next day a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so every bike is promised a day the co-op can actually meet.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Co-op mechanics (users: pull the next card from the board). Co-op manager (approver: approves the queue before it is posted to the board). Customers (stakeholders: their bike on the promised day).

## 5. Current process <!-- field: current_process -->
Steps: the manager reads the job cards, plans the next day on paper and moves the cards on the board. Problems: walk-ins get promised dates the bookings have already used up; a steering job once waited behind three services.

## 6. Scope <!-- field: scope -->
In: the day's job cards in; a repair queue out. Out: bike fitting, warranty claims to makers, the rental fleet.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 18 a day. Sample: job-cards.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Service: a booked check-over with a fixed list of jobs. Walk-in: a bike dropped off without a booking.

## 9. Context pack <!-- field: context_inventory -->
job-cards.txt, synthetic, evidence for the input format. bench-times.txt, synthetic, evidence for bench minutes and the bench minutes open each day.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A card with no fault description is refused as 'ask at the counter'. A card for a rental fleet bike or a warranty claim is refused as out of scope.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (minor).

## 14. Examples <!-- field: examples -->
Good: "C-51 | road | service | 60 | 2099-08-04 | 'full service please'". Good: "C-52 | hybrid | steering | 30 | 2099-08-03 | 'clunk when braking hard'". Bad: "C-53 | town | wheels | 75 | 2099-08-03", when the day is already full (breaks Q01). Bad: "C-54 | commuter | brakes | 25, after C-51", when a brake job sits behind a service (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it two made-up weeks of job cards, and no walk-in is promised a day that the bookings have filled.

## 16. Success metrics <!-- field: success_metrics -->
No more than two missed promised days a month. Every steering or brake job starts the morning after drop-off.

## 17. Risk <!-- field: risk -->
Reversible: if the queue is wrong I can just post a new one. It affects our own mechanics only.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes the approved queue to the co-op's repair-queue board, which replaces the cards each time and keeps no copy of the old ones.

## 19. Gates <!-- field: gates -->
I approve the queue every evening, right before it is posted to the board.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should booked services ever give way to a walk-in brake job? Owner: co-op manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
