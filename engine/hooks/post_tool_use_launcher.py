#!/usr/bin/env python3
"""Fail-closed launcher for the PostToolUse usage hook. NEVER EDIT THIS FILE.

Settings register this file, not the hook. It imports the real hook (post_tool_use.py, next to it)
and runs it; any failure (syntax error, import error, crash, a bad return value) exits 2, which
tells the session the usage was not recorded. The call then stays open, and the engine refuses
the next call until its result is recorded. The engine tests pin this file's SHA-256.
"""
import sys


def launch():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
        import post_tool_use
        code = post_tool_use.run(raw)
    except SystemExit as e:
        code = e.code
    except BaseException as exc:
        print(f"usage hook failed to load or run ({exc!r}); usage not recorded.", file=sys.stderr)
        return 2
    return code if code in (0, 2) else 2


if __name__ == "__main__":
    sys.exit(launch())
