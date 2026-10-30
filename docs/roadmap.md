# Roadmap

Verified agent-system generation, built in phases. Status labels: **planned** (not started), **implemented** (built),
**tested** (automated tests pass), **live-verified** (run end to end with real agent calls), **phase accepted** (exit
check passed in front of the owner).

| Phase | Goal | Status |
|---|---|---|
| **0. Foundation** | A generic, hardened engine with evaluations, usage tracking, a doctor, gate settings and finding marking, all proven by tests | Phase accepted: engine, hook, evidence module, approval chain, live drills, evaluation runner, doctor, gate review support, publish check. |
| **1. Thin end-to-end version** | Prove the whole path once: a hand-written charter and blueprint, a generated folder, one real job | Phase accepted: a generated ecosystem ran a real job to an approved gate, with evaluations to thresholds and measured usage; reporting added. |
| **2. Intake** | The factory interviews its owner and writes charters complete enough to design from | In progress. Tested: charter schema v1; onboarding and problem brief; interview guide. Planned: intake agents and route, evaluations, intake runs. |
| **3. Design** | The factory designs an ecosystem that matches, or justifiably differs from, a hand-built one | Planned |
| **4. Generation and lifecycle** | Generated ecosystems prove themselves before go-live; a register of them; upgrades and changes | Planned |
| **5. Autonomy, on evidence** | Jobs run outside the chat; selected low-risk gates switch to automatic only where the measured noise and miss rates allow | Planned |

Every phase ends with an exit check run in front of the owner; nothing moves on until it passes.
