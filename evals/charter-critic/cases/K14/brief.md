# Problem brief

## 1. Title <!-- field: title -->
Station volunteer duty swaps

## 2. Short name <!-- field: slug -->
station-duty-swaps

## 3. Goal <!-- field: goal -->
Volunteers at the Fernbrook heritage railway swap station duties (platform, booking office, signal box tours) through a shared swaps mailbox. When this works, the duty roster manager gets every Wednesday a checked list of the swap requests, each marked approve or refuse with the reason, so every duty on an operating day is covered by someone passed out for it.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Station volunteers (users: check the list for the duties they gave up or took). Duty roster manager (approver: approves the list every Wednesday). Operations manager (stakeholder: no operating day starts short of passed-out volunteers). Visitors (stakeholders: a safe, staffed platform).

## 5. Current process <!-- field: current_process -->
Steps: a volunteer e-mails the swaps mailbox, the roster manager checks the competence register for both volunteers and edits the duty roster spreadsheet. Problems: on two gala days a platform duty went to a volunteer not passed out for platform work; swaps for the same duty sometimes arrive twice and both get accepted. On gala days the operations manager checks the platform posts again in the morning.

## 6. Scope <!-- field: scope -->
In: the week's swap e-mails for operating days in; a checked list of swaps out. Out: recruiting and passing out new volunteers, engine crew rosters, the café and shop, non-operating maintenance days.

## 7. Inputs <!-- field: inputs -->
Plain-text swap messages: who gives up the duty, which duty (operating day and post) and who takes it. About 25 a week in the season, a handful in winter. Sample: swap-mailbox.txt (made up).

## 8. Glossary <!-- field: glossary -->
Passed out: signed off by an assessor as competent for a post. Post: one of platform, booking office or signal box tours. Operating day: a day when trains run for the public. Gala day: a busy operating day with extra trains. Maintenance day: a day with no public trains. Competence register: the list of who is passed out for which post. Duplicate: a second swap for a duty that has already been swapped.

## 9. Context pack <!-- field: context_inventory -->
swap-mailbox.txt, synthetic, evidence for the input format. competence-register.txt, synthetic, evidence for who is passed out for which post.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per swap message: the message quoted, the duty, who gives it up, who takes it, the decision (approve or refuse) and the reason in one sentence. A swap that names no operating day or no post is refused as incomplete; a second swap for a duty already swapped is refused as a duplicate.

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 the volunteer taking a duty holds the training it needs (blocker). Q02 a swap is only between two volunteers in the same role (major). Q03 every row quotes the swap message (major). Q04 the reason is one sentence (minor). Q05 a second swap for a duty already swapped is refused as a duplicate (major). Q06 a swap for a non-operating day is refused as out of scope (major). Q07 a volunteer is never given two posts at the same time on one day (blocker). Q08 posts are named exactly as in the register (minor).

## 14. Examples <!-- field: examples -->
Good: "Sat 2099-06-06 platform | Ada to Ben | approve | Ben is passed out for platform". Good: "Sun 2099-06-07 booking office | Cy to Di | approve | Di is passed out for booking office". Bad: "Sat 2099-06-13 platform | Ed to Flo | approve", when Flo is not passed out for platform (breaks Q01). Bad: "Sun 2099-06-14 tours | Gus (tours) to Hen (café) | approve", when Hen works in the café (breaks Q02). Good: "Sat 2099-06-20 platform | Ivo to Jo | refuse | duplicate: Ivo's duty was already swapped to Kit". Bad: "Tue 2099-06-16 platform | Lu to Max | approve", when Tuesday is a maintenance day (breaks Q06). Bad: "Sun 2099-06-21 platform and tours | Ned to Oli | approve", when Oli already has tours at that time (breaks Q07). Good: "Sat 2099-07-04 (gala day) booking office | Pam to Quy | approve | Quy is passed out for booking office and has no other post that day". Good: "Wed 2099-07-08 platform | Ray to Sue | refuse | out of scope: Wednesday is a maintenance day".

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it a made-up month of swap e-mails from the season, and no duty ever goes to someone not passed out for its post. I give it a week with two swaps for the same duty, and the second is refused as a duplicate. I give it a swap for a maintenance day, and it is refused as out of scope.

## 16. Success metrics <!-- field: success_metrics -->
No duty taken by someone not passed out for its post in a season. Every swap e-mail is answered by the Wednesday after it arrives.

## 17. Risk <!-- field: risk -->
Partly reversible: a wrong swap can be put right before the operating day, but not once the trains are running.

## 18. Systems <!-- field: systems -->
Reads the swap e-mails and the competence register. Writes nothing: the roster manager edits the duty roster spreadsheet by hand.

## 19. Gates <!-- field: gates -->
I approve the list every Wednesday before I edit the duty roster.

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Can a volunteer passed out for platform also cover signal box tours on a quiet day? Owner: operations manager. Do gala days need a second volunteer on the platform? Owner: operations manager. Should a swap that arrives after Wednesday be held for the next week or refused? Owner: duty roster manager. Can a volunteer whose pass-out lapses mid-season keep duties they already took? Owner: operations manager.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
Don't know yet.
