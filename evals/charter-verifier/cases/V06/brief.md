# Problem brief

## 1. Title <!-- field: title -->
Pop-up repair queue

## 2. Short name <!-- field: slug -->
popup-repair

## 3. Goal <!-- field: goal -->
At the market-square pop-up bike repair stall, bikes are left in the morning with a slip. When this works, the stall lead gets by 10:00 each market day a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so nobody is promised a bike back before the work can be done.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Repair volunteers (users: work through the queue in order). Stall lead (approver: signs off the queue by 10:00). Customers (stakeholders: their bike back on the date they were given).

## 5. Current process <!-- field: current_process -->
Steps: the coordinator sorts the slips by hand, estimates each job from memory and writes the queue on a whiteboard. Problems: estimates from memory are often an hour out; a bike with a loose headset waited two weekends.

## 6. Scope <!-- field: scope -->
In: Saturday's drop-off slips in; a repair queue out. Out: buying parts, bike donations, the Tuesday youth session.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 25 each Saturday. Sample: stall-slips.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Headset: the bearings that let the handlebars turn. Slip: the drop-off form a customer fills in.

## 9. Context pack <!-- field: context_inventory -->
stall-slips.txt, synthetic, evidence for the input format. bench-table.txt, synthetic, evidence for bench minutes.

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
I sign off the queue by 10:00 before any bike goes on a stand.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should bikes we couldn't finish go to next week's queue? Owner: stall lead. Who phones customers when a date slips? Owner: repair volunteers.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
