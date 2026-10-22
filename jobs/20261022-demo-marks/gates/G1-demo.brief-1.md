# Gate brief: 20261022-demo-marks at G1-demo

State GATE. Goal: Summarise three topics for a newsletter (live gate-review check, synthetic)

## What you are approving

- Artifact jobs/20261022-demo-marks/drafts/v2.md (v2), fingerprint 763c1bc850d9a5105c4542c80fa734741524b051fa6aad40c398c148abf94f6f
- No recorded inputs

## Approval chain

- Nothing upstream: this approval depends on no other approval.

## Evidence checks

- Reference check: passed on v2
- Evidence check: passed on v2
- Uncited sentences listed for the Verifier: 0

## Open questions

- Which local garden groups may we name as contacts?

## Usage

- calls 7 (closed 7, with token figures 0); agent minutes 1.18
- tokens: input 0, output 0, cache_read 0, cache_write 0, total 0
- ceiling (provisional): tokens 2000000, agent minutes 180; per-call warning at 500000 tokens
- demo-critic: calls 2, retries 0, failed 0, tokens 0, minutes 0.4, usage unknown 2
- demo-planner: calls 1, retries 0, failed 0, tokens 0, minutes 0.15, usage unknown 1
- demo-researcher: calls 1, retries 0, failed 0, tokens 0, minutes 0.15, usage unknown 1
- demo-verifier: calls 1, retries 0, failed 0, tokens 0, minutes 0.17, usage unknown 1
- demo-writer: calls 2, retries 0, failed 0, tokens 0, minutes 0.31, usage unknown 2
- Not included: the Orchestrator's own main-session tokens (until the headless runner, T5.2).

## Changes since the last version

```
Compared with jobs/20261022-demo-marks/drafts/v1.md:
--- before/v1.md
+++ now/v2.md
@@ -1,3 +1,7 @@
-# Newsletter summary (stand-in writer, gate-review check)
+# Newsletter (stand-in writer, gate-review check)
 
-This issue covers three practical topics: planning a small community garden, reducing household food waste, and choosing a reusable water bottle. Each topic gets a short paragraph with the main things to consider and where readers can learn more.
+This issue covers three topics: planning a small community garden, reducing household food waste, and choosing a reusable water bottle. Each topic gets a short paragraph on cost, effort and the first step to take.
+
+## Open questions
+
+- Which local garden groups may we name as contacts?
```

## Findings in this gate cycle

### demo-critic
- F-01 [major DM03] v1 whole draft: No open questions are listed, although the summary promises 'where readers can learn more' without saying where.
- F-02 [minor DM04] v1 first sentence: 'practical topics' adds nothing.
- F-03 [minor DM04] v1 second sentence: 'the main things to consider' is vague.
- F-04 [minor DM04] v1 title: The title says 'summary' twice with the heading.
- F-01 [minor DM04] v2 second sentence: 'gets a short paragraph' could be 'has a paragraph'.
- F-02 [minor DM04] v2 Open questions: 'may we name' is formal.

### demo-verifier
- F-01 [minor DM04] v2 title: The bracketed note in the title is for the drill, not for readers.


## Your options

- Approve: python engine/gate.py approve 20261022-demo-marks [--as pilot] --note "..."
- Reject (counts as gate rejection 1 of 3): python engine/gate.py reject 20261022-demo-marks --feedback "..."
- Hold (not a rejection; restart with gate.py resume): python engine/gate.py hold 20261022-demo-marks --note "..."
- You will mark 1 blocker/major finding(s) and 2 of 6 minor finding(s).
