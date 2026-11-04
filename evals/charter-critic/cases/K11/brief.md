# Problem brief

## 1. Title <!-- field: title -->
Workshop repair queue

## 2. Short name <!-- field: slug -->
workshop-queue

## 3. Goal <!-- field: goal -->
At the Canal Street community bike workshop, bikes are dropped off with a paper form and wait in the rack. When this works, the workshop lead gets each morning a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so customers get a promised date the workshop can keep.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Volunteer mechanics (users: take the next job from the board). Workshop lead (approver: approves the queue before it goes on the board). Customers (stakeholders: a promised date that holds).

## 5. Current process <!-- field: current_process -->
Steps: the lead reads the forms, guesses the time for each job, writes cards on the board and phones customers with a date. Problems: about one promised date in five is missed; brake jobs wait behind slow wheel builds.

## 6. Scope <!-- field: scope -->
In: the day's drop-off forms in; a repair queue out. Out: parts ordering, sales of second-hand bikes, e-bike motor faults.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 15 a day. Sample: dropoff-forms.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Truing: straightening a wheel so it spins without a wobble. Rack: where dropped-off bikes wait.

## 9. Context pack <!-- field: context_inventory -->
dropoff-forms.txt, synthetic, evidence for the input format. bench-times.txt, synthetic, evidence for bench minutes and the bench minutes open each day.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A form with no fault description is refused as 'ask the customer'. A form for an e-bike motor fault is refused as out of scope.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (minor).

## 14. Examples <!-- field: examples -->
Good: "T-104 | hybrid | brakes | 30 | 2099-04-02 | 'front brake rubs'". Good: "T-105 | road | wheels | 60 | 2099-04-03 | 'back wheel wobbles'". Bad: "T-106 | town | gears | 45 | 2099-04-01", when the queue ahead needs three hours first (breaks Q01). Bad: "T-107 | kids | brakes | 20, after T-105", when a brake job sits behind a wheel job (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a week of made-up forms, and no promised date is earlier than the bench time allows.

## 16. Success metrics <!-- field: success_metrics -->
Nine promised dates in ten are kept, over a month. No brake job waits more than one day.

## 17. Risk <!-- field: risk -->
Not reversible on the board: it keeps no history, so once the queue is written the old order is gone; the lead can only rebuild it from the forms.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes the approved queue to the shared repair-queue board, which keeps no history of earlier cards.

## 19. Gates <!-- field: gates -->
It writes the queue to the board as soon as it is built; I look over the board at the end of the day.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should e-bikes with no motor fault join this queue? Owner: workshop lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
