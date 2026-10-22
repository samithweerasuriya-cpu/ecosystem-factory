# Lessons

What building the factory taught, kept so later tasks and generated ecosystems don't repeat it. Each lesson names where it came from and what changed because of it.

| # | Lesson | Where it came from | What changed |
|---|---|---|---|
| 1 | **A check that scanned nothing is not a pass.** A shell `grep` used as a publish check reported "clean" when the shell had rewritten part of its pattern and the command had errored. A zero-file or errored scan looks the same as a clean one unless the check says how much it looked at. | Phase 0, T0.5 | `publish_check.py` (T0.19) is written in Python, not as a shell grep, and fails if it scanned zero files. Every guard reports how much it checked (the test guard prints how many files it fingerprinted). |
| 2 | **Test the guard, not only what it guards.** The test-run guard first passed while watching empty folders, so it proved nothing. | Phase 0, T0.5 | The guard is now tested against a fake repo with planted writes, as a permanent test. |
| 3 | **A mistake made twice deserves a guard, not a reminder.** Test helpers used one-letter job slugs in two tasks in a row; the engine rightly refused them, but the errors pointed away from the cause. | Phase 0, T0.5 and T0.6 | The test helpers now refuse slugs shorter than 3 characters with a message that names the cause. |
| 4 | **Look things up by what defines them, not by where they might be.** Job lookup took any folder with the job's name, so a stray public folder could have redirected an internal job's writes into a tracked path. The leak test found it. | Phase 0, T0.6 follow-up | Jobs are found by their state file; state in two places is refused. |
| 5 | **An option the tool doesn't offer is dropped silently.** The desktop app runs in-session subagents in the background, so the usage hook saw 0 tokens for a call that used 46,923. Asking for a foreground call changed nothing: the app removed the option before the hook saw it. | Phase 0, T0.12 drill 11 | While a job is active, the hook refuses any subagent call that doesn't explicitly ask for the foreground, so in the desktop app job agents run headless. Live checks record what the hook actually received, not what was sent. |
| 6 | **An unreadable file is not an empty file.** The doctor read a settings file with a missing comma as "no keys": it reported nothing wrong, let the approver acknowledge that, and would have missed an API key inside it. A reader that swallows parse errors fails open. | Phase 0, T0.14 (found live, the approver's own settings file) | Every check that reads a file Samith edits says "can't be read" and fails; a check that can't prove the absence of a risk (an API key) fails too. A test plants the broken file. |

## Hook tuning list

Commands the guard blocks although they are harmless. Each one failed closed, as designed; none is fixed yet. They are collected here so the read-only list can be widened in one reviewed change, with a test per entry.

| # | Command shape | Message | Seen in | Workaround |
|---|---|---|---|---|
| H1 | A read-only PowerShell line with a bare string as a separator next to protected paths, e.g. `Get-Content logs\usage.jsonl; "---"; Get-Content logs\usage-unmatched.jsonl` | "this command names a protected path and is not entirely read-only" | T0.12 | Read each file in its own call, or use `Write-Output "---"` |
| H2 | A heredoc appending documentation text that contains the word "eval" (e.g. "eval runner") to a tracked file | "eval / iex / Invoke-Expression / base64 decoding and encoded commands are not allowed" | T0.13 | Write documentation with the Edit or Write tool, not a shell heredoc |
| H3 | Running a scratch script whose own file name ends in `gate.py` (e.g. `demo_gate.py`) | "engine/gate.py is human-only" | T0.16 | Don't name scripts `*gate.py` |
