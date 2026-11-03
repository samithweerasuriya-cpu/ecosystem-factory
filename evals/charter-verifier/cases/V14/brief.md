# Problem brief

## 1. Title <!-- field: title -->
Clubhouse booking checker

## 2. Short name <!-- field: slug -->
clubhouse-bookings

## 3. Goal <!-- field: goal -->
Clubs ask to book the Riverside clubhouse through the town council's web form. When this works, the clubhouse manager gets each Wednesday a checked list of the requests, each checked against the calendar with clashes flagged, so clubs stop arriving to a locked or double-booked pavilion.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Clubhouse volunteers (users: send the replies and hand out the keys). Clubhouse manager (approver: approves the list before the calendar changes). Sports clubs (stakeholders: want their regular slots kept).

## 5. Current process <!-- field: current_process -->
Steps: the manager prints the form entries, checks the key log and the calendar, and e-mails each group. Problems: three times this season a club arrived to find the changing rooms booked by a party; replies take up to a fortnight.

## 6. Scope <!-- field: scope -->
In: one week's form entries in and a checked list out. Out: pitch bookings, bar licences, the groundsman's rota.

## 7. Inputs <!-- field: inputs -->
Plain-text form entrys, one request each: group name, room, date, start and end time. About 10 a week. Sample: clubhouse-entries.txt (made up).

## 8. Glossary <!-- field: glossary -->
Function room: the upstairs room with the kitchen. Changing rooms: the two rooms downstairs with showers. Clash: two bookings for the same room that overlap in time.

## 9. Context pack <!-- field: context_inventory -->
clubhouse-entries.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A table, one row per request: request line, group, room, date, start, end, decision (propose, clash or refuse) and a one-sentence reason. An entry with no room or no time is refused as incomplete.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no proposed booking overlaps another booking for the same room (blocker). Q02 every row quotes the request it came from (major). Q03 a request outside opening hours (08:00 to 22:30) is refused, with the reason (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Sat 2099-04-11 | Changing rooms | Under-11s football | 09:00-11:00 | propose | no clash". Good: "Sat 2099-04-11 | Function room | Birthday party | 14:00-18:00 | clash | function room booked 13:00-17:00 by the cricket club tea". Bad: "Sat 2099-04-11 | Function room | Birthday party | 14:00-18:00 | propose", because it overlaps the cricket club tea (breaks Q01). Bad: "Fri 2099-04-10 | Function room | Quiz | 21:00-23:30 | propose", because it runs past 22:30 (breaks Q03).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up form entries, and no club's regular slot is ever given to someone else.

## 16. Success metrics <!-- field: success_metrics -->
No more than two late replies a week. No club turns up to a double-booked room in a season.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong booking can be cancelled, but a group that arrives to find the room taken has lost its session.

## 18. Systems <!-- field: systems -->
Reads the form entrys as text. Writes to the pavilion's online calendar.

## 19. Gates <!-- field: gates -->
I approve the list each Wednesday, right before anything is added to the calendar.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should regular club slots for next season be checked here too? Owner: clubhouse manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
