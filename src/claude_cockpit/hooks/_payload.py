"""所有 hook 共用的一件事:**把 stdin 上那段 JSON 按 UTF-8 读进来**。

Claude Code 发给 hook 的负载是 **UTF-8**,而 Windows 上 `sys.stdin` 默认按**本地
编码**(这台机器是 GBK)解码——正文里只要有中文,就会被拆成孤立代理字符
(`'\\udc84'` 这种)。那玩意儿 json 能解析、看着一切正常,但**再往 UTF-8 文件里写
就抛 UnicodeEncodeError**;而写信号那几处按设计是「异常全吞」,于是整条信号被静默
丢掉——表现出来就是「中文消息发出去了,办公室里小人不动 / 屏幕不闪」,而且完全没有
报错可查(踩过,查了很久)。

所以一律走 `sys.stdin.buffer`(原始字节)自己按 UTF-8 解,坏字节用 `replace` 换成
`�`:宁可丢一个字,也不能让整条信号消失。
"""
from __future__ import annotations

import json
import sys


def read_payload() -> dict | None:
    """读 stdin 上那段 JSON。空输入 / 不是 JSON 对象 → None(调用方直接返回)。"""
    buf = getattr(sys.stdin, "buffer", None)
    raw = buf.read() if buf is not None else (sys.stdin.read() or "").encode()
    if isinstance(raw, str):                    # 被打桩成纯文本流时也认
        text = raw
    else:
        text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else None
