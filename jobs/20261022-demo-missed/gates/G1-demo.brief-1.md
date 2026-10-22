# Gate brief: 20261022-demo-missed at G1-demo

State GATE. Goal: Summarise three topics for a newsletter (live missed-issue check, synthetic)

## What you are approving

- Artifact jobs/20261022-demo-missed/drafts/v1.md (v1), fingerprint 7253a17a3b8ec31a237def72eb53ab8aadb3a3d9c6e76377b3e1b0b4dd912a05
- No recorded inputs

## Approval chain

- Nothing upstream: this approval depends on no other approval.

## Evidence checks

- Reference check: passed on v1
- Evidence check: passed on v1
- Uncited sentences listed for the Verifier: 0

## Open questions

- Which garden group can we name?

## Usage

- calls 5 (closed 5, with token figures 0); agent minutes 0.04
- tokens: input 0, output 0, cache_read 0, cache_write 0, total 0
- ceiling (provisional): tokens 2000000, agent minutes 180; per-call warning at 500000 tokens
- demo-critic: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-planner: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-researcher: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-verifier: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- demo-writer: calls 1, retries 0, failed 0, tokens 0, minutes 0.01, usage unknown 1
- Not included: the Orchestrator's own main-session tokens (until the headless runner, T5.2).

## Changes since the last version

```
(first version: nothing to compare)
```

## Findings in this gate cycle

### demo-critic
- F-01 [minor DM04] v1 first sentence: 'Three topics:' reads abruptly.
- F-02 [minor DM04] v1 title: The title could name the month.

### demo-verifier
- F-01 [major DM02] v1 whole draft: The template asks for one paragraph per topic; there is one line for all three.


## Your options

- Approve: python engine/gate.py approve 20261022-demo-missed [--as pilot] --note "..."
- Reject (counts as gate rejection 1 of 3): python engine/gate.py reject 20261022-demo-missed --feedback "..."
- Hold (not a rejection; restart with gate.py resume): python engine/gate.py hold 20261022-demo-missed --note "..."
- You will mark 1 blocker/major finding(s) and 1 of 2 minor finding(s).
