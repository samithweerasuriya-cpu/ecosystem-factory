# Problem brief

## 1. Title <!-- field: title -->
Dog-walk swap helper

## 2. Short name <!-- field: slug -->
walk-swaps

## 3. Goal <!-- field: goal -->
Volunteers at the animal shelter swap dog-walking slots by message. When this works, every walking slot keeps a walker, and the approver sees each week's swaps checked in one list instead of chasing messages.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Walking volunteers (users: ask for swaps and see the result). Shift lead (approver: signs off each week's swaps). Shelter manager (stakeholder: every dog is walked twice a day).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer posts a swap in the group chat; someone copies it onto the paper rota on the kennel door. Problems: swaps posted late at night are missed; twice last month a slot had no walker.

## 6. Scope <!-- field: scope -->
In: swap requests between two walking volunteers for slots in the next 14 days; a checked list of swaps out. Out: new volunteer sign-ups, kennel cleaning, vet visits.

## 7. Inputs <!-- field: inputs -->
Plain-text messages, one swap each: the volunteer giving up a slot, the slot (date, morning or afternoon) and the volunteer taking it. About 20 a week. No sample yet: the group chat can't be exported, so samples will be made up for testing.

## 8. Glossary <!-- field: glossary -->
Slot: one morning or afternoon walking session. Walker: a volunteer who walks the shelter dogs.

## 9. Context pack <!-- field: context_inventory -->
None.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 every slot keeps at least one walker after the swaps (blocker). Q02 a swap for a slot more than 14 days ahead is refused (major). Q03 every row quotes its request (major).

## 14. Examples <!-- field: examples -->
Good: "Mon 2099-05-04 morning | Ana to Ben | approve | the slot keeps a walker". Good: "Wed 2099-05-27 afternoon | Cai to Dee | refuse | more than 14 days ahead". Bad: "Tue 2099-05-05 morning | Eli to nobody | approve", because the slot is left without a walker (breaks Q01). Bad: "Wed 2099-05-27 afternoon | Cai to Dee | approve", because it is more than 14 days ahead (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
When I give it a week of swap messages, no slot is left without a walker and I don't have to read the chat.

## 16. Success metrics <!-- field: success_metrics -->
No slot without a walker in a whole month.

## 17. Risk <!-- field: risk -->
Don't know yet.

## 18. Systems <!-- field: systems -->
Reads the swap messages as text. Writes nothing: the rota on the kennel door is updated by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Can a volunteer from the cat room take a dog-walking slot? Owner: shelter manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
