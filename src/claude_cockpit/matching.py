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
