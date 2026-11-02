# Problem brief

## 1. Title <!-- field: title -->
Village hall booking replies

## 2. Short name <!-- field: slug -->
hall-replies

## 3. Goal <!-- field: goal -->
Groups e-mail the village hall to book a room. When this works, each request gets a checked draft reply within two days, saying yes, no or "clashes with", and nobody is double-booked.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Booking volunteers (users: send the replies). Committee chair (approver: approves each week's replies). Hall committee (stakeholder: wants the hall used fairly).

## 5. Current process <!-- field: current_process -->

## 6. Scope <!-- field: scope -->
In: one-off and regular weekly booking requests; a checked draft reply for each. Out: payments, keys, cleaning.

## 7. Inputs <!-- field: inputs -->
Request e-mails as plain text: group, room, date, start and end time. About 15 a week. Sample: hall-requests.txt.

## 8. Glossary <!-- field: glossary -->
Main hall: the large room. Small room: the meeting room by the kitchen. Clash: two bookings for one room that overlap.

## 9. Context pack <!-- field: context_inventory -->
hall-requests.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One draft reply per request: the request quoted, the decision (yes, no or clash), the clashing booking if any, and a two-line reply text.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 never say yes to a request that clashes (blocker). Q02 every reply quotes its request (major). Q03 replies stay under 60 words (minor).

## 14. Examples <!-- field: examples -->

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it two weeks of made-up requests and every clash gets a "clashes with" reply, never a yes.

## 16. Success metrics <!-- field: success_metrics -->
Every request answered within two days; no double bookings in a term.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong yes can be withdrawn, but a group that has already told its members has a problem. Affects the groups who book (outside the hall).

## 18. Systems <!-- field: systems -->
Reads the request e-mails. Writes nothing: the volunteers send the approved replies themselves.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should the small room be bookable on Sundays? Owner: hall committee.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On two weeks of made-up requests, every clash is caught and every reply quotes its request.
