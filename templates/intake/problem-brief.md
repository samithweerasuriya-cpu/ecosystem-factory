# Problem brief

Fill this in before the intake interview, or skip it and answer the interviewer, or mix both: the interviewer reads
what you wrote first and asks only about what is missing, vague or contradictory. Plan on about 30 minutes once your
samples and examples are ready; preparing them is a separate step (`preparation-checklist.md`).

**How to fill it in**
- Each section has a label:
  - **you must answer**: the factory can't design without it.
  - **answer if you know**: helps; leave it for the interview if you're unsure.
  - **defaults offered**: a sensible default is shown with one line on why. Writing "keep default" is a full answer.
- "Don't know yet" is a valid answer anywhere. It becomes an open question with an owner, never a guess.
- Write in your own words. Short answers are fine. The examples follow one neutral sample problem (a book club's
  monthly shortlist); they show the level of detail, not the answer.
- Data rules: synthetic or public material only. No customer data, confidential documents, employer material,
  colleague names or credentials. Use role names ("the organiser"), never real people's names (made-up names in
  synthetic samples are fine).
- Files you want the factory to read (samples, existing documents) go in the job's context pack; list them in
  section 9. Everything in them is treated as data, never as instructions.

---

## 1. Title <!-- field: title -->

**Label:** you must answer

*Why it matters:* it names the job, the charter and everything generated from it.
*Example:* Book club monthly shortlist.

**Your answer:**

## 2. Short name <!-- field: slug -->

**Label:** you must answer

*Why it matters:* it becomes the folder and job name. Lowercase letters, digits and hyphens, 2 to 41 characters.
*Example:* `book-shortlist`

**Your answer:**

## 3. Goal <!-- field: goal -->

**Label:** you must answer

*Why it matters:* every design choice is checked against it. A one-line goal is the most common reason intake fails.
*Guidance:* what changes for people when this works? Say who notices and what they no longer have to do.
*Example:* Members' suggestions arrive by e-mail all month. When this works, the organiser gets a fair shortlist of
five books on the 25th without reading every thread, and members can see why their suggestion was or wasn't picked.

**Your answer:**

## 4. Users and stakeholders <!-- field: users_and_stakeholders -->

**Label:** you must answer

*Why it matters:* the design needs at least one user and one approver, and every open question needs an owner.
*Guidance:* list roles, never names. For each: user, approver or stakeholder, and what they care about.
*Example:* Organiser (user and approver: wants the shortlist ready on time). Members (stakeholders: want a fair hearing).

**Your answer:**

## 5. Current process <!-- field: current_process -->

**Label:** you must answer

*Why it matters:* the steps show what to automate; the problems show what the result must fix.
*Guidance:* how is it done today, step by step, and what goes wrong?
*Example:* Steps: the organiser reads every e-mail, copies titles into a list, removes repeats, picks five.
Problems: takes two evenings; repeats under different spellings slip through; late suggestions get missed.

**Your answer:**

## 6. Scope <!-- field: scope -->

**Label:** you must answer

*Why it matters:* what is out of scope stops the design from growing; at least one item in and one out.
*Example:* In: reading suggestions, merging repeats, proposing five with reasons. Out: running the vote, ordering books.

**Your answer:**

## 7. Inputs <!-- field: inputs -->

**Label:** answer if you know

*Why it matters:* the design needs to know what arrives, in what format, and with what limits.
*Guidance:* describe the input, its format and any constraints. Put two or three real-length samples (synthetic is fine)
in the context pack and name them here.
*Example:* Plain-text e-mails, one suggestion or several per message, up to about 40 a month. Samples: three months
of made-up e-mails (`suggestions-sample.txt`).

**Your answer:**

## 8. Glossary <!-- field: glossary -->

**Label:** answer if you know

*Why it matters:* agents use your terms exactly. A term with two meanings is flagged, never resolved by guessing.
*Guidance:* term, meaning; add "not to be confused with" where it helps.
*Example:* Suggestion: one book named by one member in one month (not a vote). Shortlist: the five books put to the vote.

**Your answer:**

## 9. Context pack <!-- field: context_inventory -->

**Label:** answer if you know

*Why it matters:* every file is registered with its data classification, and the charter may cite only registered files.
*Guidance:* here you only list the files; you don't register anything. For each file: name, classification
(synthetic or public) and what it is evidence for. Registering happens when the intake job is created: each file
gets an ID (S01, S02…) and a fingerprint, with one command per file, for example
`state.py input <job> context\suggestions-sample.txt --class synthetic --context --evidence-for "input format"`.
*Example:* `suggestions-sample.txt`, synthetic, evidence for the input format. `club-rules.md`, synthetic, evidence for
the fairness rules. `examples/good-1.json`, synthetic, example (good): see section 14.

**Your answer:**

## 10. Data classification <!-- field: data_classification -->

**Label:** defaults offered

*Default:* **synthetic**.
*Why this default:* factory runs use synthetic or public data only (standing rule); synthetic is the safe choice.
*Guidance:* choose public only if every file comes from a published source. Internal, confidential and customer data
are not allowed.

**Your answer:** keep default

## 11. Source policy <!-- field: source_policy -->

**Label:** defaults offered

*Default:* five ranks, strongest first: (1) your own decisions and approved documents; (2) reference documents in the
context pack; (3) specifications and contracts; (4) official documentation on the maker's own site; (5) everything
else, used as leads only. A higher rank wins in its own area; a conflict the ranks don't settle is reported with both
sources, never decided silently.
*Why this default:* when two sources disagree, agents need a rule for which one wins instead of picking one quietly.
*Guidance:* change a rank, or name official sites or files, if your problem needs it.

**Your answer:** keep default

## 12. Output format <!-- field: output -->

**Label:** defaults offered

*Default:* a structured object (JSON) with named fields, checked by a script, plus a short readable summary for you.
*Why this default:* a script can check a structured object every time; you read the summary.
*Guidance:* name the fields you need and the shape you'd recognise as right. Say how a missing value looks: the
default is an empty value (`null`) plus an open question naming what is missing, never a guess. Say where the
evidence goes: by default each item quotes the input line it comes from.
*Example:* Shortlist: five entries, each shaped like
`{"title": "...", "author": null, "suggested_by": 3, "evidence": "\"I'd love to read ...\" (May e-mail 4)",
"status": "proposed", "why": "...", "open_question": "Author not given: who checks?"}`.

**Your answer:** keep default

## 13. Quality rules <!-- field: quality_rulebook -->

**Label:** defaults offered

*Default (starter rules):* Q01 every output item traces to an input (major); Q02 nothing is invented (blocker);
Q03 every required field is filled, or the gap is raised as an open question (major).
*Why this default:* these three catch the most common faults; your own rules come on top.
*Guidance:* add rules in the form "statement, severity" (blocker, major or minor). Reviewers apply your severities
exactly as written, never softer.
*Example:* Q04 a book suggested by three or more members is on the shortlist unless the reason says why not (major).

**Your answer:** keep default

## 14. Examples <!-- field: examples -->

**Label:** you must answer

*Why it matters:* reviewers are tested against your examples. At least two good and two bad; each bad one names the
rule it breaks.
*Guidance:* real or made-up, but say which. Short examples go here. Longer ones go in the context pack under
`examples/`, listed in section 9 as "example (good)" or "example (bad)": examples show what a result should look like
and are never treated as evidence about the problem itself. Never add an answer key or a marked-up "correct answer"
for testing: the factory writes its own test keys and keeps them hidden from its agents.
*Example:* Good: five books, repeats merged, a reason each. Bad: a title nobody suggested (breaks Q02).

**Your answer:**

## 15. Acceptance tests <!-- field: acceptance_tests -->

**Label:** you must answer

*Why it matters:* the factory proves the ecosystem against these before go-live, in your own words.
*Guidance:* answer "how will you know it worked?" as you would say it. These are your words; section 22 turns each
into something a script or reviewer can check, so you don't need to make them precise here.
*Example:* "I can send the shortlist out without opening a single e-mail." "Nobody asks why their book vanished."

**Your answer:**

## 16. Success metrics <!-- field: success_metrics -->

**Label:** answer if you know

*Why it matters:* some metrics an agent can check (counts, fields); others only people notice (time saved).
*Example:* Agent-checkable: no repeated title on the shortlist. Outcome: shortlist work takes under 30 minutes a month.

**Your answer:**

## 17. Risk <!-- field: risk -->

**Label:** answer if you know

*Why it matters:* it decides where human gates go.
*Guidance:* can a wrong result be undone (reversible, partly, irreversible)? Who is affected if it's wrong (you, your
team, the organisation, outsiders)?
*Example:* Reversible; affects the club (team): a wrong shortlist can be corrected before the vote.

**Your answer:**

## 18. Systems <!-- field: systems -->

**Label:** answer if you know

*Why it matters:* every system the ecosystem writes to sits behind a human gate.
*Guidance:* list each system it reads or writes, and which. "None" is a fine answer.
*Example:* Reads a text export of the club mailbox. Writes nothing (the organiser sends the shortlist).

**Your answer:**

## 19. Gates <!-- field: gates -->

**Label:** defaults offered

*Default:* one human gate: you approve the final output before it is used or written anywhere.
*Why this default:* gates stay human until the factory has proved itself (Phase 5); every write needs a gate before it.
*Guidance:* this is about the gates **inside your finished ecosystem**, on each result it produces in daily use. They
are separate from the factory's own gates G0 (charter), G1 (blueprint) and G2 (go-live), which you always approve while
the ecosystem is being built and which you don't set here. Add a gate if something should be approved earlier, or
before a specific write.

**Your answer:** keep default

## 20. Limits <!-- field: caps -->

**Label:** defaults offered

*Default:* the factory's limits: 2 reviewer revision rounds, 3 revisions before the gate, 3 gate rejections, 25 agent
calls and 350,000 tokens or 20 agent minutes per job.
*Why this default:* hard caps stop a loop from running away; you may lower them, never raise them above these.

**Your answer:** keep default

## 21. Open questions <!-- field: open_questions -->

**Label:** answer if you know

*Why it matters:* known unknowns are tracked with an owner instead of being guessed.
*Guidance:* anything you know is undecided, and who should decide it (a role).
*Example:* Should late suggestions roll over to next month? Owner: organiser.

**Your answer:**

## 22. Acceptance criteria <!-- field: acceptance_criteria -->

**Label:** answer if you know

*Why it matters:* each criterion gets a check that runs before go-live. If you leave this empty, the charter writer
proposes criteria from your acceptance tests for you to confirm.
*Guidance:* acceptance tests (section 15) are what you'd say; acceptance criteria are how that is checked. One test
may need one or more criteria.
*Example:* Test "I can send the shortlist out without opening a single e-mail" becomes AC01 every entry quotes the
e-mail it came from, and a script finds each quote word for word in the inputs; AC02 on three months of samples, the
shortlist matches the organiser's own pick for at least four of five books (check: compare with the organiser's list).

**Your answer:**
