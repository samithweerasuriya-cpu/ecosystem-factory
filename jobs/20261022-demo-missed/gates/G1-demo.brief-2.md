# Gate brief: 20261022-demo-missed at G1-demo

State GATE. Goal: Summarise three topics for a newsletter (live missed-issue check, synthetic)

## What you are approving

- Artifact jobs/20261022-demo-missed/drafts/v2.md (v2), fingerprint 93840b9797f6042f91c487df1cf10280e1e6f66a9c251ad46fdef3bf297e5612
- No recorded inputs

## Approval chain

- Nothing upstream: this approval depends on no other approval.

## Evidence checks

- Reference check: passed on v2
- Evidence check: passed on v2
- Uncited sentences listed for the Verifier: 0

## Open questions

- Which garden group can we name?

## Usage

- calls 8 (closed 8, with token figures 0); agent minutes 0.54
- tokens: input 0, output 0, cache_read 0, cache_write 0, total 0
- ceiling (provisional): tokens 2000000, agent minutes 180; per-call warning at 500000 tokens
- demo-critic: calls 2, retries 0, failed 0, tokens 0, minutes 0.19, usage unknown 2
- demo-planner: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-researcher: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-verifier: calls 2, retries 0, failed 0, tokens 0, minutes 0.17, usage unknown 2
- demo-writer: calls 2, retries 0, failed 0, tokens 0, minutes 0.17, usage unknown 2
- Not included: the Orchestrator's own main-session tokens (until the headless runner, T5.2).

## Changes since the last version

```
Compared with jobs/20261022-demo-missed/drafts/v1.md:
--- before/v1.md
+++ now/v2.md
@@ -2,3 +2,7 @@
 
-Three topics: a community garden, food waste and water bottles.
+A community garden needs a shared plan for plots, watering and tools, and a first meeting to agree it.
+
+Food waste falls when meals are planned for the week and leftovers have a set night.
+
+A reusable water bottle is worth choosing for how easily it cleans, not only for how it looks.
 
```

## Findings in this gate cycle

### demo-critic
- F-02 [minor DM04] v1 title: The title could name the month.
- F-01 [minor DM04] v2 third paragraph: 'not only for how it looks' can go.


## Your options

- Approve: python engine/gate.py approve 20261022-demo-missed [--as pilot] --note "..."
- Reject (counts as gate rejection 2 of 3): python engine/gate.py reject 20261022-demo-missed --feedback "..."
- Hold (not a rejection; restart with gate.py resume): python engine/gate.py hold 20261022-demo-missed --note "..."
- You will mark 0 blocker/major finding(s) and 1 of 2 minor finding(s).
