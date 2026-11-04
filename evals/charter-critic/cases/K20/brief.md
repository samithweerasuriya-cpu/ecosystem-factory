# Problem brief

## 1. Title <!-- field: title -->
Till shift swap checker

## 2. Short name <!-- field: slug -->
till-swaps

## 3. Goal <!-- field: goal -->
Volunteers at the Brook Street charity shop swap till shifts by text. When this works, the shop manager gets every Friday a checked list of the swap requests, each marked approve or refuse with the reason, so the till is never left with someone who can't cash up.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Shop volunteers (users: read the list and turn up for the shifts they took). Shop manager (approver: approves the list every Friday). Area office (stakeholder: every till is cashed up correctly).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer texts the manager, the manager checks the training folder and changes the paper rota. Problems: twice this year a volunteer who had never cashed up took a closing shift; texts sent on a Saturday are often missed until Tuesday.

## 6. Scope <!-- field: scope -->
In: the week's swap texts in; a checked list of swaps out. Out: new volunteer sign-ups, holiday cover, the stock room rota.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: who gives up the shift, which shift (day, morning or afternoon) and who takes it. About 12 a week. Sample: till-texts.txt (made up). The training list (each volunteer's role and training) is in till-list.txt (made up).

## 8. Glossary <!-- field: glossary -->
Cashing up: counting the till and filling in the takings sheet at closing. Till trained: signed off on the till and on cashing up.

## 9. Context pack <!-- field: context_inventory -->
till-texts.txt, synthetic, evidence for the input format. till-list.txt, synthetic, evidence for each volunteer's role and training.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per swap message: the message quoted, the shift, who gives it up, who takes it, the decision (approve or refuse) and the reason in one sentence. A message that names no shift is refused as incomplete.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the volunteer taking a shift holds the training it needs (blocker). Q02 a swap is only between two volunteers in the same role (major). Q03 every row quotes the swap message (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Wed afternoon | Lena to Omar | approve | Omar is till trained". Good: "Sat morning | Pat to Rae | approve | Rae is till trained". Bad: "Fri afternoon | Sid to Ula | approve", when Ula is not till trained (breaks Q01). Bad: "Thu morning | Vic (till) to Wyn (sorting room) | approve", when Wyn works in the sorting room (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a month of made-up swap texts, and no closing shift ever goes to someone who isn't till trained.

## 16. Success metrics <!-- field: success_metrics -->
No shift taken by someone who isn't till trained in a quarter. Every swap text is answered by the Friday after it arrives.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be undone before the shift, but not after the till is short.

## 18. Systems <!-- field: systems -->
Reads the swap messages. Writes nothing: the manager changes the paper rota by hand.

## 19. Gates <!-- field: gates -->
I approve the list every Friday before I change the rota.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Can a volunteer take two shifts on one day through a swap? Owner: shop manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
