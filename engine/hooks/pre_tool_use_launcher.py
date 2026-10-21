#!/usr/bin/env python3
"""Fail-closed launcher for the PreToolUse hook. NEVER EDIT THIS FILE.

Settings register this file, not the hook. It imports the real hook (pre_tool_use.py, next to it)
and runs it; any failure (syntax error, import error, crash, a bad return value) exits 2, which
blocks the tool call. onFailure: "block" in settings covers a launcher that cannot start.
The engine tests pin this file's SHA-256, so an edit is caught.
"""
import sys


def launch():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
        import pre_tool_use
        code = pre_tool_use.run(raw)
    except SystemExit as e:
        code = e.code
    except BaseException as exc:
        print(f"BLOCKED by engine guardrail: hook failed to load or run ({exc!r}); failing closed.", file=sys.stderr)
        return 2
    return code if code in (0, 2) else 2


if __name__ == "__main__":
    sys.exit(launch())
