"""Notification hook:仅当 Claude Code 因权限确认而通知时,记下「在等你确认」。

被 Claude Code 以 `python -m claude_cockpit.hooks.notify` 拉起,hook 负载 JSON
从 stdin 读入。写到 pending/(驾驶舱读它显示信封+闪+提示音)。本项目自带,
不再依赖 desk-buddy。任何异常都吞掉并返回 0,绝不阻断 Claude Code。
"""
from __future__ import annotations

import json
import sys
import traceback

from claude_cockpit import cc_signals


def handle(payload: dict) -> None:
    session_id = payload.get("session_id")
    message = payload.get("message", "") or ""
    cwd = payload.get("cwd", "") or ""
    if session_id and "permission" in message.lower():
        cc_signals.write_pending(session_id, message, cwd)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            handle(json.loads(raw))
    except Exception:
        print("claude-cockpit notify hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
