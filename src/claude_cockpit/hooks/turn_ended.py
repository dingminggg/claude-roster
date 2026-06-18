"""Stop hook:Claude 答完一轮 → 记一笔「该你看了」到驾驶舱专属信号目录。

被 Claude Code 以 `python -m claude_cockpit.hooks.turn_ended` 拉起,hook 负载
JSON 从 stdin 读入。写到 turn-ended/(桌宠不读),所以只有驾驶舱会因此
最大化窗口 + 闪托盘;桌宠仍只管权限提醒。异常一律吞掉返回 0,绝不阻断 Claude。
"""
from __future__ import annotations

import json
import sys
import traceback

from claude_cockpit import cc_signals


def handle(payload: dict) -> None:
    session_id = payload.get("session_id")
    cwd = payload.get("cwd", "") or ""
    if session_id:
        cc_signals.write_turn_ended(session_id, "", cwd)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if raw.strip():
            handle(json.loads(raw))
    except Exception:
        print("claude-cockpit turn_ended hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
