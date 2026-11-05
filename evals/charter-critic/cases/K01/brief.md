# Problem brief

## 1. Title <!-- field: title -->
Youth club helper swaps

## 2. Short name <!-- field: slug -->
helper-swaps

## 3. Goal <!-- field: goal -->
Helpers at the Larch Avenue youth club swap evening sessions in a group chat. When this works, the club leader gets each Sunday a checked list of the swap requests, each marked approve or refuse with the reason, so every session has two helpers with a current safeguarding check.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Session helpers (users: get a text telling them which sessions they now have). Club leader (approver: approves each Sunday's list). Parents (stakeholder: every session is properly staffed).

## 5. Current process <!-- field: current_process -->
Steps: a helper posts the swap in the group chat, the leader checks the safeguarding list and texts both helpers. Problems: a Tuesday session once ran with only one checked helper; swaps posted late at night get lost in the chat.

## 6. Scope <!-- field: scope -->
In: the week's swap posts in; a checked list of swaps out. Out: new helper checks, trips and residentials, the tuck shop.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: who gives up the session, which session (evening and age group) and who takes it. About 6 a week. Sample: chat-swaps.txt (made up). The training list (each volunteer's role and checks) is in helper-list.txt (made up).

## 8. Glossary <!-- field: glossary -->
Safeguarding check: the background check every helper needs, renewed every three years. Session: one evening with one age group.

## 9. Context pack <!-- field: context_inventory -->
chat-swaps.txt, synthetic, evidence for the input format. helper-list.txt, synthetic, evidence for each volunteer's role and checks.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per swap message: the message quoted, the session, who gives it up, who takes it, the decision (approve or refuse) and the reason in one sentence. A post that names no session is refused as incomplete. A swap for the tuck shop is refused as out of scope.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the volunteer taking a session holds the training it needs (blocker). Q02 a swap is only between two volunteers in the same role (major). Q03 every row quotes the swap message (major). Q04 the reason is one sentence (minor).

## 14. Examples <!-- field: examples -->
Good: "Tue juniors | Quin to Ros | approve | Ros has a current check". Good: "Thu seniors | Sam to Tam | approve | Tam has a current check". Bad: "Mon juniors | Uri to Val | approve", when Val's check has run out (breaks Q01). Bad: "Wed seniors | Wil (helper) to Xan (driver) | approve", when Xan only drives the minibus (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it two months of made-up swap posts, and no session ever has a helper without a current check.

## 16. Success metrics <!-- field: success_metrics -->
No session with fewer than two checked helpers in a term. Both helpers get their text by Sunday evening.

## 17. Risk <!-- field: risk -->
Reversible: a wrong swap can be swapped back before the session. Only the club's helpers are affected.

## 18. Systems <!-- field: systems -->
Reads the swap posts. Sends a text to both helpers of each approved swap through the club's texting service. A text cannot be recalled once it is sent.

## 19. Gates <!-- field: gates -->
I approve the list each Sunday, and nothing is texted until I have.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Can a helper swap into an age group they haven't worked with before? Owner: club leader.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
