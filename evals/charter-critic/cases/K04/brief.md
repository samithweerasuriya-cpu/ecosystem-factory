# Problem brief

## 1. Title <!-- field: title -->
Repair intake queue

## 2. Short name <!-- field: slug -->
repair-intake

## 3. Goal <!-- field: goal -->
At the Hillside cycle repair project, people leave bikes at the shed on Saturdays with a drop-off slip. When this works, the project coordinator gets each Saturday afternoon a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so nobody is promised a bike back before the work can be done.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Repair volunteers (users: work through the queue in order). Project coordinator (approver: signs off the queue each Saturday afternoon). Customers (stakeholders: their bike back on the date they were given).

## 5. Current process <!-- field: current_process -->
Steps: the coordinator sorts the slips by hand, estimates each job from memory and writes the queue on a whiteboard. Problems: estimates from memory are often an hour out; a bike with a loose headset waited two weekends.

## 6. Scope <!-- field: scope -->
In: Saturday's drop-off slips in; a repair queue out. Out: buying parts, bike donations, the Tuesday youth session.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 25 each Saturday. Sample: saturday-slips.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Headset: the bearings that let the handlebars turn. Slip: the drop-off form a customer fills in.

## 9. Context pack <!-- field: context_inventory -->
saturday-slips.txt, synthetic, evidence for the input format. bench-table.txt, synthetic, evidence for bench minutes and the bench minutes open each Saturday.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A slip with no fault description is refused as 'ask the customer'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (major).

## 14. Examples <!-- field: examples -->
Good: "S-21 | mountain | steering | 40 | 2099-05-09 | 'handlebars feel loose'". Good: "S-22 | folding | punctures | 15 | 2099-05-09 | 'flat again'". Bad: "S-23 | hybrid | gears | 50 | 2099-05-02", when two weekends of work are ahead of it (breaks Q01). Bad: "S-24 | road | brakes | 25, after S-22", when a brake job waits behind a puncture (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it four made-up Saturdays of slips, and every brake or steering job is at the top of the queue.

## 16. Success metrics <!-- field: success_metrics -->
No bike promised back earlier than the work allows, over a term. Every steering job is done the same Saturday.

## 17. Risk <!-- field: risk -->
Partly reversible: a queue can be reordered before the work starts, but a missed promise has already let a customer down.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes nothing: the coordinator copies the queue onto the whiteboard.

## 19. Gates <!-- field: gates -->
I sign off the queue before it goes on the whiteboard.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should bikes left over from last Saturday go first? Owner: project coordinator. Do children's bikes get their own bench-time line? Owner: repair volunteers.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
