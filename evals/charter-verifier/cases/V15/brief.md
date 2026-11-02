# Problem brief

## 1. Title <!-- field: title -->
Hall booking request sorter

## 2. Short name <!-- field: slug -->
hall-bookings

## 3. Goal <!-- field: goal -->
Groups ask to book the community hall by e-mail. When this works, the hall coordinator gets one weekly list of the requests, each checked against the calendar with clashes flagged, instead of reading every message and checking the diary by hand. Groups hear back within a week.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Booking volunteers (users: work through the list and send the replies). Hall coordinator (approver: checks the list and confirms bookings). Hall committee (stakeholder: wants fair use of the hall). Booking groups (stakeholders: want a quick, clear answer).

## 5. Current process <!-- field: current_process -->
Steps: the coordinator reads each request e-mail, checks the paper diary, writes the booking in and replies. Problems: twice this spring two groups were booked into the main hall on the same evening; replies take up to three weeks.

## 6. Scope <!-- field: scope -->
In: one week's booking requests in, a checked list of proposed bookings out, and approved bookings written to the hall calendar. Out: taking payments, key handover, cleaning rotas.

## 7. Inputs <!-- field: inputs -->
Plain-text e-mails, one request each: group name, room, date, start and end time. About 15 a week. Sample: requests-sample.txt (made up).

## 8. Glossary <!-- field: glossary -->
Main hall: the large room. Side room: the small meeting room. Clash: two bookings for the same room that overlap in time.

## 9. Context pack <!-- field: context_inventory -->
requests-sample.txt, synthetic, evidence for the input format. hall-prices-2098.txt and hall-prices-2099.txt, synthetic, evidence for hall hire prices.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A table, one row per request: request line, group, room, date, start, end, decision (propose, clash or refuse), the hire fee and a one-sentence reason. The fee is the hours booked times the room's hourly price from the current price list in the pack. A request with no room or no time is refused as incomplete.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no proposed booking overlaps another booking for the same room (blocker). Q02 every row quotes the request it came from (major). Q03 a request outside opening hours (08:00 to 22:00) is refused, with the reason (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Tue 2099-03-03 | Side room | Knitting circle | 10:00-12:00 | propose | no clash". Good: "Thu 2099-03-05 | Main hall | Youth band | 19:00-21:00 | clash | Main hall booked 18:00-20:00 by the dance class". Bad: "Thu 2099-03-05 | Main hall | Youth band | 19:00-21:00 | propose", because it overlaps the dance class (breaks Q01). Bad: "Sat 2099-03-07 | Main hall | Quiz night | 21:00-23:30 | propose", because it runs past 22:00 (breaks Q03).

## 15. Acceptance tests <!-- field: acceptance_tests -->
When I run a week of requests through it, every clash is flagged and I can approve the list in ten minutes.

## 16. Success metrics <!-- field: success_metrics -->
No double bookings in a term. Every group gets a reply within 7 days of its request.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong booking can be cancelled, but a group that turns up to a double-booked room has lost its evening.

## 18. Systems <!-- field: systems -->
Reads the request e-mails as text. Writes to the hall's shared booking calendar.

## 19. Gates <!-- field: gates -->
I approve the checked list, and I confirm once more right before anything goes into the calendar.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should regular weekly bookings go through the same list? Owner: hall committee.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
