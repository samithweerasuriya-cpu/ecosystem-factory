# Problem brief

## 1. Title <!-- field: title -->
Party room request checker

## 2. Short name <!-- field: slug -->
party-room

## 3. Goal <!-- field: goal -->
Families ask to hire the community hall's party room by e-mail. When this works, the bookings volunteer gets each week's requests checked against the calendar and the hall rules, with a draft answer for each, and families hear back within three days instead of two weeks.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Bookings volunteer (user: sends the answers). Hall manager (approver: approves each week's answers). Neighbours (stakeholders: want parties to end on time).

## 5. Current process <!-- field: current_process -->
Steps: the bookings volunteer reads each e-mail, checks the paper calendar and the hall rules, and writes back. Problems: answers take up to two weeks; last month a party was accepted for a Sunday evening, when the hall closes at 18:00 on Sundays.

## 6. Scope <!-- field: scope -->
In: one week's party-room requests in; a checked draft answer for each out. Out: deposits and payments, decorations, the main hall.

## 7. Inputs <!-- field: inputs -->
Plain-text e-mails: family name, date, start and end time, number of guests. About 8 a week. Sample: party-requests.txt.

## 8. Glossary <!-- field: glossary -->
Party room: the room off the main hall, up to 40 guests. Closing time: 22:00, or 18:00 on Sundays.

## 9. Context pack <!-- field: context_inventory -->
party-requests.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per request: the request quoted, the decision (accept, decline or clash), the reason in one sentence, and a short draft answer.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 never accept a request that clashes with another booking (blocker). Q02 never accept a party that runs past closing time (major). Q03 never accept more than 40 guests (major). Q04 every row quotes its request (minor).

## 14. Examples <!-- field: examples -->
Good: "Sat 2099-10-03 | 14:00-17:00 | 25 guests | accept | free, within hours". Good: "Sun 2099-10-04 | 16:00-19:00 | 20 guests | decline | runs past the Sunday closing time". Bad: "Sat 2099-10-10 | 15:00-18:00 | 55 guests | accept" (breaks Q03). Bad: "Sun 2099-10-04 | 16:00-19:00 | 20 guests | accept", because the family really wanted it.

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up requests and no accepted party clashes, runs late or has more than 40 guests.

## 16. Success metrics <!-- field: success_metrics -->
Every family hears back within three days. Agent-checkable: no accepted row breaks Q01 to Q03.

## 17. Risk <!-- field: risk -->
Partly reversible: an accepted party can be cancelled, but the family may already have sent invitations. Affects families outside the hall.

## 18. Systems <!-- field: systems -->
Reads the request e-mails. Writes nothing: the volunteer sends the approved answers and updates the paper calendar.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should children's parties get a lower guest limit? Owner: hall manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On a month of made-up requests, every accepted row passes Q01 to Q03 and quotes its request.
