"""把 pending 信号(按 cwd)对到成员名。纯逻辑,可单测。"""
from __future__ import annotations

import os

from .config import Member


def norm_path(p: str | os.PathLike) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    except Exception:
        return ""


_norm = norm_path   # 兼容旧名


def match_pending(pending: list[dict], members: list[Member]) -> set[str]:
    """返回有 pending 信号(等你确认)的成员名集合。按规范化后的 cwd 精确匹配。"""
    by_cwd = {_norm(m.cwd): m.name for m in members}
    hit: set[str] = set()
    for rec in pending:
        cwd = rec.get("cwd") if isinstance(rec, dict) else None
        if not cwd:
            continue
        name = by_cwd.get(_norm(cwd))
        if name:
            hit.add(name)
    return hit


def sessions_for_cwd(records: list[dict], cwd: str | os.PathLike) -> list[str]:
    """给定一批信号记录,返回落在目标 cwd 下的所有 session_id(cwd 归一后精确比对)。
    用于「按成员清信号」:标记已读、以及关窗后清孤儿信号。"""
    target = _norm(cwd)
    return [rec["session_id"] for rec in records
            if isinstance(rec, dict) and rec.get("session_id")
            and _norm(rec.get("cwd", "")) == target]


def latest_message_for_cwd(records: list[dict], cwd: str | os.PathLike) -> str:
    """给定一批信号记录,返回目标 cwd 下**最新**那条的 message(没有就空串)。

    用于「点工位时把这一轮的第一句话冒出来」:同一个 cwd 可能留着好几条会话的
    turn-ended,按 `at` 取最新的那条——旧会话那句话已经是上一轮的事了。
    """
    target = _norm(cwd)
    best: tuple[str, str] | None = None
    for rec in records:
        if not isinstance(rec, dict) or _norm(rec.get("cwd", "")) != target:
            continue
        at = str(rec.get("at") or "")       # ISO 串,字典序即时间序
        if best is None or at >= best[0]:
            best = (at, str(rec.get("message") or ""))
    return best[1] if best else ""
