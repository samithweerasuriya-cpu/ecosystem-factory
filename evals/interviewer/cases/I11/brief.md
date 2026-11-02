# Problem brief

## 1. Title <!-- field: title -->
Driver shift swaps

## 2. Short name <!-- field: slug -->
driver-swaps

## 3. Goal <!-- field: goal -->
Our volunteer drivers swap delivery shifts by text message. When this works, the dispatch coordinator gets one checked list of swaps a week, and no delivery round is left without a driver.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Volunteer drivers (users: ask for swaps). Dispatch coordinator (approver: approves every swap). Delivery customers (stakeholders: get their delivery on time).

## 5. Current process <!-- field: current_process -->
Steps: a driver texts the coordinator, who checks the round sheet and updates it. Problems: swaps sent at night are missed; two rounds went out late last month.

## 6. Scope <!-- field: scope -->
In: swap requests between two drivers for rounds in the next two weeks; a checked list out. Out: recruiting drivers, vehicle checks, fuel claims.

## 7. Inputs <!-- field: inputs -->
The weekly export of our customer records system: each delivery customer's name, home address and phone number, with the round they are on, plus the drivers' swap texts.

## 8. Glossary <!-- field: glossary -->
Round: one driver's delivery route on one day.

## 9. Context pack <!-- field: context_inventory -->
None yet. I can add last month's customer export.

## 10. Data classification <!-- field: data_classification -->
Internal. These are our real customer records, exported from the delivery system.

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no round is left without a driver (blocker). Q02 every row quotes the swap text (major).

## 14. Examples <!-- field: examples -->
Good: "Tue round 3 | Ola to Pim | approve". Good: "Fri round 1 | Rae to nobody | refuse". Bad: "Fri round 1 | Rae to nobody | approve" (breaks Q01). Bad: a row with no swap text quoted (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
Every round on next month's sheet has a driver after the swaps.

## 16. Success metrics <!-- field: success_metrics -->
No round goes out late because of a swap.

## 17. Risk <!-- field: risk -->
Partly reversible. Affects our delivery customers.

## 18. Systems <!-- field: systems -->
Reads the customer records export and the swap texts. Writes nothing.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
None.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
