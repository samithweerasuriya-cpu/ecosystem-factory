# Problem brief

## 1. Title <!-- field: title -->
Church hall request checker

## 2. Short name <!-- field: slug -->
church-hall-requests

## 3. Goal <!-- field: goal -->
Local groups ask to use St Aidan's church hall by filling in a paper slip in the porch. When this works, the hall secretary gets every Monday a checked list of the requests, each checked against the calendar with clashes flagged, so no two groups turn up to the same room.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Booking helpers (users: type up the slips and send the replies). Hall secretary (approver: checks the list before anything goes in the calendar). Parochial church council (stakeholders: wants the hall used by the whole village).

## 5. Current process <!-- field: current_process -->
Steps: a helper collects the slips on Sunday, the secretary checks the wall planner, writes the booking in and rings the group. Problems: last winter a slimming club and a toddler group were both given the small room on a Tuesday morning; slips go missing from the porch.

## 6. Scope <!-- field: scope -->
In: the week's slips, including one-off family celebrations such as christenings and birthday parties, and a checked list out. Out: private parties, funerals and weddings in the church itself, the car park.

## 7. Inputs <!-- field: inputs -->
Plain-text request slips, one request each: group name, room, date, start and end time. About 12 a week. Sample: porch-slips.txt (made up).

## 8. Glossary <!-- field: glossary -->
Large room: the main hall with the stage. Small room: the room next to the kitchen. Clash: two bookings for the same room that overlap in time.

## 9. Context pack <!-- field: context_inventory -->
porch-slips.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A table, one row per request: request line, group, room, date, start, end, decision (propose, clash or refuse) and a one-sentence reason. A slip with no room or no time is refused as incomplete. A request for the car park is refused as out of scope.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no proposed booking overlaps another booking for the same room (blocker). Q02 every row quotes the request it came from (major). Q03 a request outside opening hours (09:00 to 21:30) is refused, with the reason (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Wed 2099-09-02 | Small room | Book club | 14:00-15:30 | propose | no clash". Good: "Tue 2099-09-08 | Small room | Toddler group | 10:00-11:30 | clash | small room booked 09:30-11:00 by the slimming club". Bad: "Tue 2099-09-08 | Small room | Toddler group | 10:00-11:30 | propose", because it overlaps the slimming club (breaks Q01). Bad: "Fri 2099-09-04 | Large room | Ceilidh | 20:00-23:00 | propose", because it runs past 21:30 (breaks Q03).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up slips, and every clash in the small room is flagged.

## 16. Success metrics <!-- field: success_metrics -->
No double bookings in a year. Every group hears back within a week.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong booking can be cancelled, but a group that arrives to find the room taken has lost its session.

## 18. Systems <!-- field: systems -->
Reads the request slips as text. Writes to the hall's shared calendar.

## 19. Gates <!-- field: gates -->
I check the list each Monday, and nothing goes in the calendar until I have.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should the vicar's own meetings go through the list? Owner: parochial church council.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
