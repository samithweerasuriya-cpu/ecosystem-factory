# Problem brief

## 1. Title <!-- field: title -->
Repair queue builder

## 2. Short name <!-- field: slug -->
queue-builder

## 3. Goal <!-- field: goal -->
At the Market Square bike kitchen, bikes come in through the week with a tag and a note from the owner. When this works, the kitchen lead gets on Mondays and Thursdays a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so bikes are worked on in a fair, safe order.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Kitchen volunteers (users: pick jobs from the queue). Kitchen lead (approver: approves the queue on Monday and Thursday). Customers (stakeholders: a fair place in the queue).

## 5. Current process <!-- field: current_process -->
Steps: the lead reads the tags and notes, puts loud notes at the top and writes the queue in a notebook. Problems: owners who write the loudest notes get served first; safety jobs wait behind easy ones.

## 6. Scope <!-- field: scope -->
In: the tags since the last queue in; a repair queue out. Out: selling parts, teaching sessions, bikes left over three months.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 30 a week. Sample: tags-and-notes.txt (made up).

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Tag: the card tied to each bike with its ticket number. Note: what the owner wrote about the fault.

## 9. Context pack <!-- field: context_inventory -->
tags-and-notes.txt, synthetic, evidence for the input format. bench-times.txt, synthetic, evidence for bench minutes.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A tag with no note is refused as 'ask the owner'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (minor).

## 14. Examples <!-- field: examples -->
Good: "K-41 | town | steering | 40 | 2099-02-12 | 'bars turn stiffly'". Good: "K-42 | mountain | punctures | 15 | 2099-02-13 | 'slow puncture'". Bad: "K-43 | road | wheels | 120 | 2099-02-10", when a full week of work is ahead of it (breaks Q01). Bad: "K-44 | kids | brakes | 20, after K-42", when a brake job waits behind a puncture (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up tags, and the queue is in the same order whatever the notes say.

## 16. Success metrics <!-- field: success_metrics -->
Customers are happier with how long repairs take. No safety job waits behind an easier one.

## 17. Risk <!-- field: risk -->
Partly reversible: a queue can be redone, but an owner who waited behind a queue-jumper has lost days.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes nothing: the lead copies the queue into the notebook.

## 19. Gates <!-- field: gates -->
I approve the queue before it goes in the notebook.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should a bike left more than a month go back to the end of the queue? Owner: kitchen lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
