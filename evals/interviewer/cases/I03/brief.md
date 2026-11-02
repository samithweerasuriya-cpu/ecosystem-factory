# Problem brief

## 1. Title <!-- field: title -->
Scout hut hire enquiries

## 2. Short name <!-- field: slug -->
hut-hire

## 3. Goal <!-- field: goal -->

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->

## 5. Current process <!-- field: current_process -->

## 6. Scope <!-- field: scope -->

## 7. Inputs <!-- field: inputs -->
Plain-text enquiry e-mails: group name, date, start and end time, number of people. About 10 a week. Sample: hire-enquiries.txt (made up).

## 8. Glossary <!-- field: glossary -->
Hut: the scout hut's main room, up to 50 people. Troop night: the scouts' own meeting, every Thursday 18:30 to 20:30.

## 9. Context pack <!-- field: context_inventory -->
hire-enquiries.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per enquiry: the enquiry quoted, the decision (offer, decline or clash) and the reason in one sentence.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 never offer a slot that overlaps troop night or another hire (blocker). Q02 never offer the hut to more than 50 people (major). Q03 every row quotes its enquiry (minor).

## 14. Examples <!-- field: examples -->

## 15. Acceptance tests <!-- field: acceptance_tests -->

## 16. Success metrics <!-- field: success_metrics -->
Every enquiry gets an answer within five days. Agent-checkable: no offered row breaks Q01 or Q02.

## 17. Risk <!-- field: risk -->
Reversible: an offer can be withdrawn before the hire is paid. Affects outside groups who hire the hut.

## 18. Systems <!-- field: systems -->
Reads the enquiry e-mails. Writes nothing: the answers are sent by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Do parties count as a hire or need the group leader's say? Owner: group scout leader.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On a month of made-up enquiries, no offered row overlaps troop night or another hire, and none is over 50 people.
