# Problem brief

## 1. Title <!-- field: title -->
Bike kitchen job board

## 2. Short name <!-- field: slug -->
bike-kitchen-jobs

## 3. Goal <!-- field: goal -->
At the community bike kitchen, people bring bikes in on open evenings and a volunteer mechanic helps them fix it. When this works, the evening's lead gets the night's jobs sorted by stand and by the parts they need, so each visitor is matched to a mechanic who can do the job within the first half hour.

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->
Volunteer mechanics (users: pick their next job from the list). Evening lead (approver: checks the list before the doors open). Visitors (stakeholders: want their bike fixed the same evening). Parts volunteer (stakeholder: keeps the second-hand parts bins stocked).

## 5. Current process <!-- field: current_process -->
Steps: visitors write their name and the problem on the whiteboard by the door; the evening lead reads the board and sends each visitor to a free stand; the mechanic at the stand looks at the bike and fetches parts from the bins.

## 6. Scope <!-- field: scope -->
In: one evening's sign-in sheet; a list of jobs with stand, mechanic skill and parts needed. Also in: matching each job to a mechanic who has signed off that skill.

## 7. Inputs <!-- field: inputs -->
The evening's sign-in sheet typed into plain text: visitor first name, bike type, problem in the visitor's words. About 20 an evening. Sample: signin-sheet.txt (made up).

## 8. Glossary <!-- field: glossary -->
Stand: one of the four repair stands. Skill sign-off: a mechanic has been checked on that kind of job (brakes, gears, wheels, punctures). Bins: the boxes of second-hand parts.

## 9. Context pack <!-- field: context_inventory -->
signin-sheet.txt, synthetic, evidence for the input format.

## 10. Data classification <!-- field: data_classification -->
keep default

## 11. Source policy <!-- field: source_policy -->
keep default

## 12. Output format <!-- field: output -->
One row per visitor: first name, job type (brakes, gears, wheels, punctures or other), the skill needed, the parts to fetch, and a one-sentence reason. A problem that names no part of the bike is listed as "ask at the door".

## 13. Quality rules <!-- field: quality_rulebook -->
Q01 a brake job is only matched to a mechanic signed off on brakes (blocker). Q02 every row quotes the visitor's own words for the problem (major). Q03 parts are only listed if the job type needs them (minor).

## 14. Examples <!-- field: examples -->
Good: "Ada | hybrid | brakes | brakes sign-off | brake pads | 'back brake squeals and barely stops'". Good: "Tom | road | punctures | punctures sign-off | inner tube 700c | 'front tyre flat again'". Bad: "Ada | hybrid | brakes | gears sign-off", when the job is brakes (breaks Q01). Bad: "Tom | road | punctures | inner tube | tyre problem", with no quote of the visitor's words (breaks Q02).

## 15. Acceptance tests <!-- field: acceptance_tests -->
I give it four made-up sign-in sheets, and every brake job is matched to a brakes-signed-off mechanic.

## 16. Success metrics <!-- field: success_metrics -->
Every visitor is at a stand within 30 minutes of the doors opening. Agent-checkable: no row breaks Q01.

## 17. Risk <!-- field: risk -->
Reversible: a wrong match is changed at the stand. Affects visitors on that evening only.

## 18. Systems <!-- field: systems -->
Reads the typed sign-in sheet. Writes nothing: the lead reads the list out at the start of the evening.

## 19. Gates <!-- field: gates -->
keep default

## 20. Limits <!-- field: caps -->
keep default

## 21. Open questions <!-- field: open_questions -->
Do e-bike jobs get their own skill sign-off? Owner: evening lead.

## 22. Acceptance criteria <!-- field: acceptance_criteria -->
On four made-up sign-in sheets, every brake job goes to a brakes-signed-off mechanic and every row quotes the visitor.
