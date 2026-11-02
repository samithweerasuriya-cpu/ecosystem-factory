# Security Policy

Ecosystem Factory is a personal, open-source project that runs locally for a single user. Its safety rests on a small set of guarantees: fail-closed hooks, human-only approval gates, approvals bound to exact file contents, and evaluations that must pass before go-live. A report that breaks any of those is exactly what this policy is for.

## Supported versions

Only the latest commit on `main` is supported. There are no maintained release branches.

## Reporting a vulnerability

**Please don't open a public issue for a security problem.**

Report it privately through GitHub: go to the **Security** tab of this repository and choose **Report a vulnerability**. Include:

- what you found and why it matters;
- the steps or input that reproduce it (synthetic data only, never real secrets or personal data);
- the commit you tested against.

This is a one-person project, so responses are best effort: an acknowledgement within 7 days and an assessment within 30. Credit is given in the fix's commit and in `docs/lessons.md` unless you'd rather stay anonymous.

## In scope

- **Guard bypass:** any way for an agent or the coding session to write to protected paths, run a human-only command, or slip past the hook (it must fail closed).
- **Gate forgery:** approving, voiding or re-pointing an approval without a person acting in their own terminal, or an approval that survives a change to the files it covers.
- **Prompt injection:** content in a brief, context file or agent output that makes an agent act on it, or that reaches a human as an instruction instead of labelled data.
- **Evaluation integrity:** leaking answer keys into prompts, a report that counts toward a lock without real runs behind it, or a passing result for a suite that changed since it ran.
- **Publish safety:** a secret, personal detail or protected path getting past the publish check into a commit or push.
- **Spend and caps:** a way to exceed a configured token, call or loop limit without being stopped.

## Out of scope

- Problems in Claude, Claude Code or GitHub themselves. Report those to the vendor.
- Attacks that need an already-compromised machine or user account.
- Enterprise isolation, multi-tenant separation or compliance features. These are deliberate non-goals (see the README's "Scope and non-goals").
- Findings that only apply to modified copies with the guards removed.

## Handling secrets

The project never needs an API key: it runs on a claude.ai subscription. If you find a secret anywhere in this repository or its history, report it privately as above.
