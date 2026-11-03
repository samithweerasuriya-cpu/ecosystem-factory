# Problem brief

## 1. Title <!-- field: title -->
Food bank swap checker

## 2. Short name <!-- field: slug -->
foodbank-swaps

## 3. Goal <!-- field: goal -->
Volunteers at the Riverside food bank swap shifts by message, and the coordinator checks each swap by hand against the rota board, the hygiene certificates and the driving checks. When this works, the volunteer coordinator gets one checked list of swap requests every evening, each marked approve or refuse with the reason, so no shift is ever left without a certified volunteer on distribution or a checked driver on the collection run, and volunteers hear back the same day.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Food bank volunteers (users: ask for swaps and read the result). Volunteer coordinator (approver: checks the list every evening and updates the rota board). Shift leads (stakeholders: need a full team on every shift). Warehouse manager (stakeholder: needs a checked driver on every collection run).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer sends a swap message to the coordinator's phone; the coordinator checks the rota board, the certificate folder and the driving checks; the coordinator writes the swap on the board and replies. Problems: twice this spring the distribution shift ran without anyone holding a hygiene certificate; messages sent late in the evening wait until the next afternoon; once a volunteer without a driving check drove the van.

## 6. Scope <!-- field: scope -->
In: one day's swap messages between two volunteers for shifts in the next 14 days, checked against the certificate list and the driving checks; a checked list of swaps out. Out: sickness calls (they are not swaps), new volunteer sign-ups, the food stock system, the Saturday breakfast club.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages, one swap each: the time sent, who gives up the shift, which shift (day and role) and who takes it. About 25 a week. Sample: swap-messages.txt (made up). The certificate and driving lists are typed up weekly as plain text; for testing they are made up as well.

## 8. Glossary <!-- field: glossary -->
Distribution: the 14:00-17:00 shift when food parcels are handed out. Collection run: the 17:00-19:00 van trip to collect donations. Hygiene certificate: the food hygiene certificate a distribution volunteer needs. Driving check: the yearly check a volunteer needs before driving the van. Swap partner: the volunteer who takes the shift. Shift lead: the volunteer in charge of one shift. Rota board: the board in the warehouse office that records who works which shift.

## 9. Context pack <!-- field: context_inventory -->
swap-messages.txt, synthetic, evidence for the input format. volunteer-handbook.txt, synthetic, evidence for shift and role rules.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a distribution shift keeps at least one volunteer with a valid hygiene certificate after the swap (blocker). Q02 the evening collection run keeps a driver with a valid driving check (blocker). Q03 a swap asked for less than 24 hours before the shift is refused (major). Q04 a swap is only between two volunteers in the same role (major). Q05 a sickness call is never treated as a swap (major). Q06 every row quotes the swap message (major). Q07 a swap for a shift more than 14 days ahead is refused (major). Q08 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Wed distribution | Cora to Dev | approve | Dev holds a valid hygiene certificate". Good: "Wed collection run | Eli to Fern | approve | Fern has a driving check on file". Good: "Fri distribution | Lou to Max | refuse | asked 16 hours before the shift". Bad: "Thu distribution | Hana to Ivo | approve", because Ivo's certificate has run out and nobody else on the shift has one (breaks Q01). Bad: "Wed collection run | Eli to Fern | approve" when Fern has no driving check (breaks Q02). Bad: "Fri distribution | Lou to Max | approve", because it was asked 16 hours before the shift (breaks Q03). Bad: "Tue packing | Asha to Ben (sorting) | approve", because Ben works sorting, not packing (breaks Q04).

## 15. Acceptance tests <!-- field: acceptance_tests -->
When I give it a week of made-up swap messages, no distribution shift is left without a certificate holder and no collection run without a checked driver. When I give it a message sent at 22:47 for the next afternoon, it is refused as too late. When I give it a sickness call, it is not on the swap list at all.

## 16. Success metrics <!-- field: success_metrics -->
No distribution shift without a certificate holder in a quarter. No collection run without a checked driver, ever. Every swap message answered by the end of the day it arrives.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the swap messages, the certificate list and the driving list as text. Writes nothing: the coordinator updates the rota board by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Can a shift lead swap with an ordinary volunteer if another lead covers? Owner: volunteer coordinator. Does a volunteer shadowing their first shifts count as a swap partner? Owner: shift leads. Should Saturday shifts follow the same 24-hour rule? Owner: volunteer coordinator.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
