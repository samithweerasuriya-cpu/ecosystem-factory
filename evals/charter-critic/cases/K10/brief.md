# Problem brief

## 1. Title <!-- field: title -->
Gallery steward swaps

## 2. Short name <!-- field: slug -->
steward-swaps

## 3. Goal <!-- field: goal -->
Gallery stewards at the Old Mill museum swap their weekend duties by e-mail. When this works, the visitor services lead gets on Thursdays a checked list of the swap requests, each marked approve or refuse with the reason, so every gallery has a steward who knows its evacuation route.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Gallery stewards (users: check which duties they now have). Visitor services lead (approver: approves the list on Thursdays). Museum trustees (stakeholder: the galleries are covered safely).

## 5. Current process <!-- field: current_process -->
Steps: a steward e-mails the lead, the lead checks the steward handbook's training table and edits the weekend sheet. Problems: one Sunday the upper gallery was covered by a steward who hadn't done its fire walk; the training table in the handbook and the weekend sheet disagree about who is trained.

## 6. Scope <!-- field: scope -->
In: the week's swap e-mails in; a checked list of swaps out. Out: school group bookings, volunteer recruitment, the café rota.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: who gives up the duty, which duty (day and gallery) and who takes it. About 10 a week. Sample: swap-emails.txt (made up). The training list (each volunteer's role and fire walks) is in steward-list.txt (made up).

## 8. Glossary <!-- field: glossary -->
Fire walk: the walk-through of a gallery's evacuation route that a steward must do before covering it. Duty: one gallery for one half-day.

## 9. Context pack <!-- field: context_inventory -->
swap-emails.txt, synthetic, evidence for the input format. steward-handbook.txt, public (it is on the museum's website), evidence for the training needs. steward-list.txt, synthetic, evidence for each volunteer's role and fire walks.

## 10. Data classification <!-- field: data_classification -->
Internal: the handbook is the museum's own, and the swap e-mails are made up.

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per swap message: the message quoted, the duty, who gives it up, who takes it, the decision (approve or refuse) and the reason in one sentence. An e-mail that names no gallery is refused as incomplete.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the volunteer taking a duty holds the training it needs (blocker). Q02 a swap is only between two volunteers in the same role (major). Q03 every row quotes the swap message (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Sat am | Upper gallery | Ida to Jem | approve | Jem has done its fire walk". Good: "Sun pm | Mill room | Kai to Lou | approve | Lou has done its fire walk". Bad: "Sun am | Upper gallery | Mo to Nat | approve", when Nat has not done its fire walk (breaks Q01). Bad: "Sat pm | Mill room | Oz (steward) to Pip (shop) | approve", when Pip works in the shop (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up swap e-mails, and no gallery ever goes to a steward without its fire walk.

## 16. Success metrics <!-- field: success_metrics -->
No gallery covered without its fire walk in a season. Every swap e-mail is answered by the Thursday after it arrives.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be fixed before the weekend, not during an evacuation.

## 18. Systems <!-- field: systems -->
Reads the swap messages. Writes nothing: the lead edits the weekend sheet by hand.

## 19. Gates <!-- field: gates -->
I approve the list on Thursday before the weekend sheet changes.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Should a steward be able to cover two galleries at once on quiet days? Owner: visitor services lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
