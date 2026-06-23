"""UserPromptSubmit hook:你回话了 → 清掉该会话的「该你看了」信号(驾驶舱停闪),
并清掉权限 pending(你已经在回话,自然不再等确认)。

被 Claude Code 以 `python -m claude_cockpit.hooks.clear` 拉起。异常吞掉返回 0。
"""
from __future__ import annotations

import json
import sys
import traceback

from claude_cockpit import cc_signals


def handle(payload: dict) -> None:
    session_id = payload.get("session_id")
    if session_id:
        cc_signals.clear_turn_ended(session_id)
        cc_signals.clear_pending(session_id)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            handle(json.loads(raw))
    except Exception:
        print("claude-cockpit clear hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
