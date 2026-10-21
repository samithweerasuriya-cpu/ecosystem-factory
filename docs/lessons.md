# Lessons

What building the factory taught, kept so later tasks and generated ecosystems don't repeat it. Each lesson names where it came from and what changed because of it.

| # | Lesson | Where it came from | What changed |
|---|---|---|---|
| 1 | **A check that scanned nothing is not a pass.** A shell `grep` used as a publish check reported "clean" when the shell had rewritten part of its pattern and the command had errored. A zero-file or errored scan looks the same as a clean one unless the check says how much it looked at. | Phase 0, T0.5 | `publish_check.py` (T0.19) is written in Python, not as a shell grep, and fails if it scanned zero files. Every guard reports how much it checked (the test guard prints how many files it fingerprinted). |
| 2 | **Test the guard, not only what it guards.** The test-run guard first passed while watching empty folders, so it proved nothing. | Phase 0, T0.5 | The guard is now tested against a fake repo with planted writes, as a permanent test. |
