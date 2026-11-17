# Problem brief

## 1. Title <!-- field: title -->
Hall request checker

## 2. Short name <!-- field: slug -->
hall-check

## 3. Goal <!-- field: goal -->
Groups ask to book the Larkfield community hall by e-mail. When this works, the hall secretary gets one checked list of the week's requests every Sunday, each checked against the calendar with clashes flagged, so no two groups are given the same room at the same time.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Booking volunteers (users: send the replies from the list). Hall secretary (approver: checks the list before anything goes in the calendar). Hall trustees (stakeholders: want the hall used fairly).

## 5. Current process <!-- field: current_process -->
Steps: the secretary reads each e-mail, checks the wall calendar, writes the booking in and replies. Problems: twice last term two groups were given the main hall on the same evening; replies take up to two weeks.

## 6. Scope <!-- field: scope -->
In: one week's request e-mails; a checked list of proposed bookings out; approved bookings written to the hall calendar. Out: payments, key holders, cleaning.

## 7. Inputs <!-- field: inputs -->
Plain-text e-mails, one request each: group name, room, date, start and end time. About 12 a week. Sample: requests-week.txt (made up).

## 8. Glossary <!-- field: glossary -->
Main hall: the large room with the stage. Craft room: the small room with sinks. Clash: two bookings for the same room that overlap in time.

## 9. Context pack <!-- field: context_inventory -->
requests-week.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
*Default:* **synthetic**.

**Your answer:** keep default

## 11. Source policy <!-- field: source_policy -->
*Default:* five ranks, strongest first: (1) your own decisions and approved documents; (2) reference documents in the
context pack; (3) specifications and contracts; (4) official documentation on the maker's own site; (5) everything
else, used as leads only. A higher rank wins in its own area; a conflict the ranks don't settle is reported with both
sources, never decided silently.

**Your answer:** keep default

## 12. Output format <!-- field: output -->
*Default:* a structured object (JSON) with named fields, checked by a script, plus a short readable summary for you.

**Your answer:** keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no proposed booking overlaps another booking for the same room (blocker). Q02 every row quotes the request it came from (major). Q03 a request outside opening hours (09:00 to 22:00) is refused, with the reason (major).

## 14. Examples <!-- field: examples -->
Good: "Mon 2099-06-01 | Craft room | Pottery group | 10:00-12:00 | propose | no clash". Good: "Wed 2099-06-03 | Main hall | Film club | 19:00-21:30 | clash | main hall booked 18:00-20:00 by the youth band". Bad: "Wed 2099-06-03 | Main hall | Film club | 19:00-21:30 | propose", because it overlaps the youth band (breaks Q01). Bad: "Fri 2099-06-05 | Main hall | Disco | 21:00-23:00 | propose", because it runs past 22:00 (breaks Q03).

## 15. Acceptance tests <!-- field: acceptance_tests -->
When I run a week of requests through it, every clash is flagged and I can approve the list in a quarter of an hour.

## 16. Success metrics <!-- field: success_metrics -->
No double bookings in a term. Every group gets a reply within 7 days.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the request e-mails as text. Writes to the hall's shared calendar.

## 19. Gates <!-- field: gates -->
I check the list each Sunday, and nothing goes in the calendar until I have approved it.

## 20. Limits <!-- field: caps -->
*Default:* the factory's limits: 2 reviewer revision rounds, 3 revisions before the gate, 3 gate rejections, 25 agent
calls and 350,000 tokens or 20 agent minutes per job.

**Your answer:** keep default

## 21. Open questions <!-- field: open_questions -->
Should the trustees' own meetings go through the list? Owner: hall trustees.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
