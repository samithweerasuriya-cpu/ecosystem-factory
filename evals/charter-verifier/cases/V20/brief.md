# Problem brief

## 1. Title <!-- field: title -->
Hillside repair intake

## 2. Short name <!-- field: slug -->
hillside-intake

## 3. Goal <!-- field: goal -->
At the Hillside cycle repair project, people leave bikes at the shed on Saturdays with a drop-off slip. When this works, the project coordinator gets each Saturday afternoon a repair queue built from the drop-off forms, with bench minutes and a promised date for each bike, so nobody is promised a bike back before the work can be done.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Repair volunteers (users: work through the queue in order). Project coordinator (approver: signs off the queue each Saturday afternoon). Customers (stakeholders: their bike back on the date they were given). Parts volunteer (stakeholder: orders parts on Mondays and needs to know what is waiting).

## 5. Current process <!-- field: current_process -->
Steps: the coordinator sorts the slips by hand, estimates each job from memory and writes the queue on a whiteboard. Problems: estimates from memory are often an hour out; a bike with a loose headset waited two weekends. Parts are ordered on Mondays from one supplier, so a bike waiting for a part can sit in the shed for a week; nobody tells the customer until they ask. Long wheel builds are started late on a Saturday and left half done.

## 6. Scope <!-- field: scope -->
In: Saturday's drop-off slips in; a repair queue out. Out: buying parts, bike donations, the Tuesday youth session.

## 7. Inputs <!-- field: inputs -->
Drop-off forms typed into plain text: ticket number, bike, the customer's description of the fault, and the date they need it. About 25 each Saturday. Sample: saturday-slips.txt (made up). The form has a 'needed for work' box and a line for parts the customer already brought. Parts in stock are listed on the shed wall, not in a file.

## 8. Glossary <!-- field: glossary -->
Bench minutes: the standard time a job takes, from the bench-time table. Headset: the bearings that let the handlebars turn. Slip: the drop-off form a customer fills in. Needed for work: the box on the form a customer ticks when they ride the bike to work. Waiting for parts: a job that cannot start until a part arrives. Wheel build: lacing a new wheel from a rim, spokes and a hub. Indexing: adjusting the gears so each click moves one sprocket. Split job: a job worked over two days because it is longer than 90 bench minutes.

## 9. Context pack <!-- field: context_inventory -->
saturday-slips.txt, synthetic, evidence for the input format. bench-table.txt, synthetic, evidence for bench minutes.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per drop-off form: ticket, bike, job type, bench minutes, promised date, and a one-sentence reason. A slip with no fault description is refused as 'ask the customer'.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a promised date is never earlier than the queue's bench time allows (blocker). Q02 a brake or steering job goes ahead of every other job (major). Q03 every row quotes the customer's description from the form (major). Q04 bench minutes come from the bench-time table, never a guess (major). Q05 a job the form marks 'needed for work' goes ahead of other jobs of the same kind (major). Q06 a bike waiting for a part is listed as 'waiting for parts' and gets no promised date (major). Q07 a job over 90 bench minutes is split over two days, never squeezed into one (major). Q08 ticket numbers are copied exactly as the form gives them (minor).

## 14. Examples <!-- field: examples -->
Good: "S-21 | mountain | steering | 40 | 2099-05-09 | 'handlebars feel loose'". Good: "S-22 | folding | punctures | 15 | 2099-05-09 | 'flat again'". Bad: "S-23 | hybrid | gears | 50 | 2099-05-02", when two weekends of work are ahead of it (breaks Q01). Bad: "S-24 | road | brakes | 25, after S-22", when a brake job waits behind a puncture (breaks Q02). Good: "H-41 | commuter | brakes | 30 | 2099-06-03 | 'needed for work, brakes squeal' | ahead of H-42". Good: "H-43 | tandem | wheels | 120 | 2099-06-05 | 'rear wheel buckled' | split over two days". Good: "H-44 | town | gears | — | waiting for parts | 'needs a new gear hanger'". Bad: "H-45 | road | wheels | 120 | 2099-06-03", when a 120-minute wheel build is squeezed into one day (breaks Q07). Bad: "H-46 | town | gears | 45 | 2099-06-04 | 'needs a new gear hanger'", when the part is not in stock (breaks Q06). Bad: "H-47 | hybrid | brakes | 30, after H-48 brakes for leisure", when a 'needed for work' brake job waits behind a leisure one (breaks Q05).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it four made-up Saturdays of slips, and every brake or steering job is at the top of the queue. I give it a day with a 120-minute wheel build, and the build is split over two days. I give it a form whose part is not in stock, and the bike is listed as waiting for parts with no date. I give it two brake jobs, one needed for work, and the work one comes first.

## 16. Success metrics <!-- field: success_metrics -->
No bike promised back earlier than the work allows, over a term. Every steering job is done the same Saturday. No split job is promised for one day. Every waiting-for-parts bike has no date until its part arrives.

## 17. Risk <!-- field: risk -->
Partly reversible: a queue can be reordered before the work starts, but a missed promise has already let a customer down. A bike promised for a day it can't be ready means a customer without a way to get to work; that is the case the coordinator worries about most.

## 18. Systems <!-- field: systems -->
Reads the typed drop-off forms. Writes nothing: the coordinator copies the queue onto the whiteboard.

## 19. Gates <!-- field: gates -->
I sign off the queue before it goes on the whiteboard.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should bikes left over from last Saturday go first? Owner: project coordinator. Do children's bikes get their own bench-time line? Owner: repair volunteers. Should a customer be phoned when a part arrives, or wait for the next queue? Owner: project coordinator. Do e-bike batteries count as a part we wait for? Owner: project coordinator. Can a split job's second day be a Sunday? Owner: repair volunteers. Who decides when the bench-time table is updated? Owner: project coordinator.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
