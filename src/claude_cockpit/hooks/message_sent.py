"""PostToolUse hook(匹配 SendMessage 工具):某个会话给另一个会话发了消息 → 记一笔,
驾驶舱看到就让发送方的小人走过去说一句再走回来;同时落一条长期历史记录,供过后
翻旧账用(事件通道读一次删一次,历史通道只进不出,两条互不影响)。

**为什么用 hook 而不是直接监听**:会话之间的消息走的是 `~/.claude/sessions/*.json` 里
那个 `messagingSocketPath` 命名管道,那是 Claude Code 的内部协议、不是公开契约(同
peers.py 的口径:只读公开的,不碰内部的)。而 PostToolUse 是官方 hook,发送方那边
必然触发,负载里就有「发给谁」。

被 Claude Code 以 `python -m claude_cockpit.hooks.message_sent` 拉起,负载 JSON 从
stdin 读入。异常一律吞掉返回 0,绝不阻断 Claude。
"""
from __future__ import annotations

import json
import sys
import traceback

from ._payload import read_payload

from claude_cockpit import cc_signals


def handle(payload: dict) -> None:
    # matcher 只是个过滤器,真跑起来还是要自己确认一次工具名:settings.json 被改坏、
    # 或者 matcher 规则以后变了,都不该让别的工具误触发走动。
    if payload.get("tool_name") != "SendMessage":
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    to_name = str(tool_input.get("to") or "").strip()
    cwd = str(payload.get("cwd") or "").strip()
    # 正文也记一笔:气泡里要显示「说了什么」,不然一屋子人跑来跑去只知道谁找谁。
    # 长度在写入侧就截断(见 cc_signals.MSG_MAX)——气泡只有一两行,整篇正文
    # 既画不下,也没必要落到磁盘上。
    text = str(tool_input.get("message") or "")
    if to_name and cwd:
        cc_signals.write_message(cwd, to_name, text)
        # 再落一条**长期**记录:事件读一次就没了,而桌上那部手机要能翻旧账。
        # 两条通道互不影响——一条只进不出,一条读一次删一次。
        cc_signals.append_history(cwd, to_name, text)


def main() -> int:
    try:
        payload = read_payload()        # **按 UTF-8 读**,别用 sys.stdin(见 _payload.py)
        if payload is not None:
            handle(payload)
    except Exception:
        print("claude-cockpit message_sent hook error:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
