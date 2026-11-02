# Problem brief

## 1. Title <!-- field: title -->
Studio shift swaps

## 2. Short name <!-- field: slug -->
studio-swaps

## 3. Goal <!-- field: goal -->
Presenters at Harbour community radio trade studio slots in a shared inbox. When this works, the station coordinator gets each Monday a checked list of the swap requests, each marked approve or refuse with the reason, so no slot goes out with nobody trained on the desk.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Presenters (users: check the list for the slots they swapped). Station coordinator (approver: signs off the swaps each Monday). Listeners (stakeholder: no dead air).

## 5. Current process <!-- field: current_process -->
Steps: a presenter e-mails the shared inbox, the coordinator reads it on Monday and updates the slot board. Problems: last month a breakfast slot went to a presenter not trained on the desk, and the station was silent for twenty minutes; swaps sent after Monday are not seen until the next week.

## 6. Scope <!-- field: scope -->
In: the week's swap e-mails in; a checked list of swaps out. Out: new presenter training, programme ideas, the outside broadcast rota.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: who gives up the slot, which slot (day and hour) and who takes it. About 8 a week. Sample: inbox-swaps.txt (made up).

## 8. Glossary <!-- field: glossary -->
Desk trained: signed off on running the studio desk alone. Slot: one hour on air.

## 9. Context pack <!-- field: context_inventory -->
inbox-swaps.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per swap message: the message quoted, the slot, who gives it up, who takes it, the decision (approve or refuse) and the reason in one sentence. A swap that names no slot is refused as incomplete.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the volunteer taking a slot holds the training it needs (blocker). Q02 a swap is only between two volunteers in the same role (major). Q03 every row quotes the swap message (major). Q04 the reason is one sentence (minor). Also, a swap must reach the inbox at least 48 hours before the slot, and the cover rule applies.

## 14. Examples <!-- field: examples -->
Good: "Tue 07:00 | Ari to Bex | approve | Bex is desk trained". Good: "Sun 18:00 | Cal to Dot | approve | Dot is desk trained". Bad: "Mon 07:00 | Eve to Fin | approve", when Fin is not desk trained (breaks Q01). Bad: "Wed 12:00 | Gil (presenter) to Hal (producer) | approve", when Hal is a producer, not a presenter (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up swap e-mails, and no slot ever goes to someone who isn't desk trained.

## 16. Success metrics <!-- field: success_metrics -->
No dead air caused by a swap in a quarter. Every swap is answered on the Monday after it arrives.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be changed before the slot, but dead air can't be undone.

## 18. Systems <!-- field: systems -->
Reads the swap messages. Writes nothing: the coordinator updates the slot board by hand.

## 19. Gates <!-- field: gates -->
I sign off the list on Monday before I touch the slot board.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should a presenter be able to swap a slot with a guest presenter? Owner: station coordinator.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
