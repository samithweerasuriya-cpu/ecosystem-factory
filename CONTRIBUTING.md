# Contributing to Ecosystem Factory

Thanks for your interest. This is a personal, open-source project (MIT) with one maintainer, built in public. Contributions are welcome, but the project runs on a deliberate, gated process, so please read this first.

## The best ways to help

- **Open an issue** for a bug, a gap in a guardrail, or an evaluation case that would fool a reviewer agent. Concrete examples are the most useful thing you can send.
- **Share your lessons.** If you build agent systems and measure whether they work, an issue comparing notes is welcome. `docs/lessons.md` shows the kind of finding that changes the design.
- **Small pull requests** are welcome after an issue has agreed the change. Unannounced large PRs will probably not be merged: the build follows a fixed plan, phase by phase (see `docs/roadmap.md`).

## What fits, and what doesn't

Read "What this is / isn't" and "Scope and non-goals" in the README first. In short, the factory builds **small, purpose-built agent systems for one owner, run locally, proven before go-live**. Out of scope: hosted or concurrent services, enterprise isolation or compliance tooling, multi-repository code generation and general agent swarms.

## Ground rules for any contribution

1. **Synthetic or public data only.** No customer data, confidential documents, real people's names, employer material or credentials, in code, tests, examples or issues.
2. **No secrets, ever.** Not in files, commits or issues. The publish check blocks the obvious cases, but it is a safety net, not permission.
3. **Fail closed.** Anything unreadable, unknown or missing must block, never default to "fine". (Lesson 6 explains why.)
4. **Never weaken a test or an evaluation threshold to make it pass.** Report the failure instead.
5. **Human-only actions stay human-only.** Gate approvals live in `engine/gate.py` and must keep working only in a person's own terminal, with no flags or shortcuts.
6. **Keep agents' tool lists minimal and explicit.** No agent gets the `Agent` tool.

## Setting up

Requirements: Windows, Python 3.13 (via `uv`), Git, and Claude Code signed in with a claude.ai subscription (no API key).

Run the setup checker and the fast test tier:

    .venv\Scripts\python.exe engine\doctor.py

    .venv\Scripts\python.exe engine\run_tests.py --fast

Install the publish hooks before your first commit:

    .venv\Scripts\python.exe engine\publish_check.py install

Before opening a pull request, run the full suite (it takes 15-30 minutes):

    .venv\Scripts\python.exe engine\run_tests.py

## Pull request checklist

- [ ] An issue agreed the change first
- [ ] Full test suite passes, and the publish check passes on your commits
- [ ] No line-ending churn: `git diff --stat` shows only the lines you meant to change
- [ ] Any change to agents, rules, schemas or config says which evaluation suites it affects
- [ ] Commits use a noreply email address, not a personal one

## How this project is built

The maintainer is a product manager who doesn't write code: Claude Code writes and tests everything, and every plan and result is reviewed before it is approved. `CLAUDE.md` holds the working rules Claude Code follows in this repository. If you use an AI coding assistant to contribute, the same rules apply to it.

## Conduct

Be kind and specific. Critique the work, not the person.
