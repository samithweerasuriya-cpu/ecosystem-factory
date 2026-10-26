# Baselines

Reference figures from the author's earlier private labs, so the factory's own reviewers can be compared with something. Anonymised: counts only, no topics, names or finding text.

The factory's own calibration suite (`evals/calibration-critic/`, 7 short synthetic cases, every planted defect found in every run) proves that the evaluation runner, scoring and lock rule work. It does not measure reviewer quality: real reviewer suites follow the Suite design rules in `evals/README.md`.

## Critic noise rate (T0.17)

A spec-writing chain in an earlier lab: a writer drafts a spec from a research brief, a critic reviews it, the writer revises. The approver marked every critic finding valid or noise after the chain ran.

| Measure | Value |
|---|---|
| Chain runs on the topic | 3 (2 stopped on mechanical checks before the critic ran) |
| Runs with critic findings | 1 (2 review rounds) |
| Critic findings | 4 (1 major, 3 minor) |
| Noise rate: noise / (valid + noise) | **0 of 4 (0%)** |
| Missed issues: not raised at all | 0 (miss rate 0 of 4) |
| Severity under-rated: raised, but rated too low | **1 of 4** (a minor that should have been major) |

Under-rated severity is counted on its own, not in the miss rate: the critic found the issue but judged it too mild.

**Caveat:** one run and four findings make a starting point, not a measurement. From Phase 2 the factory's reviewers are measured on their own gate marks (`engine/state.py quality`), and these figures are what they are first compared with.
