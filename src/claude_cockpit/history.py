"""会话间对话记录:把 `cc_signals.read_history()` 那堆流水按员工组装成收发双向视图。

**纯逻辑,不 import Qt、不读文件、不碰 peers**:记录从哪来、映射谁给的,都是调用方
的事(办公室通过 `set_address` 本来就持有「员工名 → 会话名」这份映射)。

一条记录只带发送方的 **cwd** 和收件人的**会话名**(hook 那边只拿得到这两样)。所以:
  - 「谁发的」永远准——cwd 是稳的;
  - 「发给谁」要靠 addrs 反查,会话已经结束时反查不到,**原样显示会话名,不猜**。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .matching import norm_path


@dataclass(frozen=True)
class Entry:
    direction: str      # "out" = 他发出去的 / "in" = 别人发给他的
    peer: str           # 显示用的对方名(反查不到时退回会话名 / 目录名)
    text: str
    at: float


def _dir_name(cwd: str) -> str:
    """cwd 最后一段目录名(兼容 / 与 \\ 分隔)——发送方不在花名册里时的兜底。"""
    if not cwd:
        return "?"
    return re.split(r"[\\/]", cwd.rstrip("\\/"))[-1] or "?"


def for_member(records, member, addrs, members=()) -> list[Entry]:
    """某个员工的对话记录,按时间正序。

    `addrs` = {员工名: 会话名 | None}(办公室 `set_address` 的那份);
    `members` 用来把发送方 cwd 反查成员工名。
    """
    addrs = addrs or {}
    sess_to_member = {v: k for k, v in addrs.items() if v}
    cwd_to_member = {norm_path(str(m.cwd)): m.name for m in (members or ())}
    me_cwd = norm_path(str(member.cwd))
    me_sess = addrs.get(member.name)
    out: list[Entry] = []
    for rec in records or []:
        from_cwd = str(rec.get("from_cwd") or "")
        to_name = str(rec.get("to_name") or "")
        text = str(rec.get("text") or "")
        try:
            at = float(rec.get("at") or 0.0)
        except (TypeError, ValueError):
            at = 0.0
        if norm_path(from_cwd) == me_cwd:
            out.append(Entry("out", sess_to_member.get(to_name, to_name), text, at))
            continue
        if not me_sess or to_name != me_sess:
            continue
        peer = cwd_to_member.get(norm_path(from_cwd)) or _dir_name(from_cwd)
        out.append(Entry("in", peer, text, at))
    out.sort(key=lambda e: e.at)
    return out


def unread_count(entries, seen_at: float) -> int:
    """比「上次看过的时刻」新的有几条。手机角上那颗红点按它亮。"""
    try:
        seen = float(seen_at or 0.0)
    except (TypeError, ValueError):
        seen = 0.0
    return sum(1 for e in entries if e.at > seen)
