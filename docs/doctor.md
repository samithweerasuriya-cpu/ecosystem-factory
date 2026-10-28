# Doctor

`engine/doctor.py` checks that a folder (the factory, or a generated ecosystem) is safe and ready to work in. It changes nothing and makes no Claude calls unless you ask for `--deep`.

```
.venv\Scripts\python.exe engine\doctor.py            # every fast check
.venv\Scripts\python.exe engine\doctor.py --json     # the same as JSON
.venv\Scripts\python.exe engine\doctor.py --wsl      # also report WSL
.venv\Scripts\python.exe engine\doctor.py --deep     # also one live headless call: shows its cost, asks first
.venv\Scripts\python.exe engine\doctor.py ack <check> # acknowledge a warning (your own terminal)
```

Run it in your own terminal for the truest picture: sessions started by the desktop app get some settings from the app (for example, the app turns off CLI auto-updates for its own sessions).

Each line is **OK**, **WARN** (worth knowing; work can go on), **FAIL** (with a Fix line) or **INFO**. The exit code is 1 if anything fails, and `engine/gate.py lock` refuses on any FAIL.

## What it checks

| Group | Checks |
|---|---|
| Tools | venv Python and `jsonschema`; the `py -3` launcher the hooks run with; Git, a GitHub noreply commit address, no remote; the PATH `claude` and the desktop app's own Claude Code copy at or above `min_cli` (`config/doctor.json`); a claude.ai login; no `ANTHROPIC_API_KEY` or `apiKeyHelper` anywhere; automatic CLI updates (WARN while on); tool-less agents (`tools: []`) checked live on the installed CLI (`empty_tools_verified_cli` in `config/doctor.json`; WARN when never verified or verified on another version, and the generator then refuses tool-less agents) |
| Hooks | both launchers and both real hooks present, compiling and matching `engine/hooks/PINS.json`; registered in `.claude/settings.json` with `onFailure: "block"` |
| User level | user-level agents, skills, commands, CLAUDE.md and settings (WARN, names and key names only); user skills that shadow project commands or skills; CLAUDE.md files above the run folders, the repo or the ecosystems folder |
| Local config | `config/protected-paths.local.json` while `vendor/` exists (factory only); whether markitdown is configured |
| Evaluations | the pinned model and installed CLI against the latest reports, naming the suites to re-run: WARN in build mode, FAIL in operate mode (an update has invalidated the lock) |
| Mode and layout | build or operate mode and the active job; the folders, `.gitattributes` and `.gitignore` lines the engine relies on; WSL with `--wsl` |

## Privacy

The home folder is printed as `~`, everywhere including `--json`. The OS user name, email addresses and organisation names are never printed (`claude auth status` shows both; the doctor reads only "logged in" and the login type). For settings and `env` sections only key names are shown, never values.

## Acknowledging a warning

`doctor.py ack <check>` (in your own terminal) records the warning's current details in `config/doctor.local.json` (untracked). It then shows as INFO "acknowledged" until its details change (for example, a new user-level skill), when it is a WARN again. Failures can't be acknowledged.

## Turning off automatic CLI updates

The doctor never changes this; you do. Add this to `~/.claude/settings.json` (`%USERPROFILE%\.claude\settings.json`), keeping your other keys:

```json
{
  "env": {
    "DISABLE_AUTOUPDATER": "1"
  }
}
```

Check it with `claude doctor` (its auto-updates line shows "disabled") and with this doctor. `DISABLE_AUTOUPDATER` stops the background update; `claude update` still works when you choose to update. `DISABLE_UPDATES` blocks manual updates too. `autoUpdatesChannel` only picks `latest` or `stable`; it can't switch updates off. The desktop app downloads and updates its own copy of Claude Code; the documentation doesn't say whether this setting reaches it, so the doctor reports that copy's version separately. Source: code.claude.com/docs/en/setup (Disable auto-updates) and code.claude.com/docs/en/desktop.

After any CLI update, every evaluation report is stale for locking: re-run the suites (`evals/run_evals.py stale` names them).
