# Problem brief

## 1. Title <!-- field: title -->
Feeding rota swaps

## 2. Short name <!-- field: slug -->
feeding-swaps

## 3. Goal <!-- field: goal -->
Volunteers at the city farm swap animal-feeding shifts by message. When this works, every morning and evening feed has a trained volunteer after the swaps, and nobody has to rebuild the rota from a chat thread on Sunday night.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Marta Kowal and Jonas Reed sort out the swaps; the volunteers ask them, and the farm manager wants every feed covered.

## 5. Current process <!-- field: current_process -->
Steps: a volunteer posts a swap in the farm's group chat; on Sunday night someone rebuilds the week's rota from the thread and pins it in the feed shed. Problems: swaps posted after the rebuild are lost; twice this month the evening feed was covered by someone not trained on the pigs.

## 6. Scope <!-- field: scope -->
In: swaps between two volunteers for feeding shifts in the coming week; a checked list of swaps out. Out: new volunteer inductions, vet visits, the farm shop rota.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: volunteer giving up, shift (day, morning or evening), volunteer taking it. About 15 a week. Sample: swap-messages.txt.

## 8. Glossary <!-- field: glossary -->
Feed: one morning or evening feeding round. Trained: signed off on every animal group in the round.

## 9. Context pack <!-- field: context_inventory -->
swap-messages.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
keep default

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 every feed has a trained volunteer after the swaps (blocker). Q02 a swap for a shift more than 7 days ahead is refused (major). Q03 every row quotes the swap message (major).

## 14. Examples <!-- field: examples -->
Good: "Mon evening | Ivo to Kit | approve | Kit is trained". Good: "Sat morning (in 9 days) | Lu to Max | refuse | more than 7 days ahead". Bad: "Tue morning | Ned to Ola | approve", when Ola is not trained (breaks Q01). Bad: "Sat morning (in 9 days) | Lu to Max | approve" (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up swap messages, and no feed ever ends up with an untrained volunteer.

## 16. Success metrics <!-- field: success_metrics -->
No feed covered by an untrained volunteer in a month. Agent-checkable: every approved swap's taker is on the trained list.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be fixed before the feed, not after. Affects the animals and the volunteers (the farm team).

## 18. Systems <!-- field: systems -->
Reads the swap messages. Writes nothing: the rota in the feed shed is updated by hand.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Does a volunteer trained on poultry only count for the morning feed? Owner: farm manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On a month of made-up swap messages, every approved swap keeps a trained volunteer on each feed.
