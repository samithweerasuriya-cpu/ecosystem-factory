# Problem brief

## 1. Title <!-- field: title -->
Steward swap checker

## 2. Short name <!-- field: slug -->
steward-swaps

## 3. Goal <!-- field: goal -->
Match-day stewards ask to swap shifts by message. When this works, the steward coordinator gets each week's swap requests already checked against the handbook rules, and every match has its full steward count, without checking each swap by hand.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Stewards (users: ask for swaps and read the decisions). Steward coordinator (approver: approves every swap). Club secretary (stakeholder: needs the right number of stewards at every match).

## 5. Current process <!-- field: current_process -->
Steps: a steward posts a swap request in the group chat; the coordinator checks the handbook and the rota, then updates the rota sheet. Problems: last season three matches started one steward short; swaps asked too late were approved by mistake.

## 6. Scope <!-- field: scope -->
In: one week's swap requests in, a checked list of swaps out, approved swaps written to the rota sheet. Out: recruiting stewards, training records, pay.

## 7. Inputs <!-- field: inputs -->
Plain-text messages, one swap each: the steward giving up a shift, the shift, the steward taking it, and when it was asked. About 10 a week. Sample: swap-requests-sample.txt (made up).

## 8. Glossary <!-- field: glossary -->
Shift: one steward position at one match. Kick-off: the published start time of the match.

## 9. Context pack <!-- field: context_inventory -->
swap-requests-sample.txt, synthetic, evidence for the input format. steward-handbook-2098.txt and steward-handbook-2099.txt, synthetic, evidence for the swap rules.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
A table, one row per request: request line, steward giving up, steward taking, match date, position, decision (approve or refuse) and a one-sentence reason. A request that names no steward taking the shift is refused.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 no match is left with fewer stewards than the handbook requires (blocker). Q02 a swap that breaks the handbook's notice period is refused (major). Q03 every row quotes its request (major).

## 14. Examples <!-- field: examples -->
Good: "Sat 2099-08-15 | Gate B | Ravi to Lena | asked Thu 11:00 | approve | asked 52 hours before kick-off". Good: "Sat 2099-08-15 | Gate C | Omar to Jo | asked Sat 09:00 | refuse | asked 6 hours before kick-off". Bad: "Sat 2099-08-15 | Gate C | Omar to Jo | asked Sat 09:00 | approve", because it was asked too late (breaks Q02). Bad: "Sat 2099-08-22 | Gate A | Mia to nobody | approve", because the match is left one steward short (breaks Q01).

## 15. Acceptance tests <!-- field: acceptance_tests -->
When I give it a week of swap requests, every late swap is refused and no match is left short.

## 16. Success metrics <!-- field: success_metrics -->
No match starts short of stewards all season.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be undone before the match, but not once the match has started.

## 18. Systems <!-- field: systems -->
Reads the swap messages as text. Writes to the steward rota sheet.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Do cup matches use the same notice period? Owner: club secretary.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
