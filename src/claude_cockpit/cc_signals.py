# 复制自 desk-buddy(src/desk_buddy/cc_signals.py),与桌宠共享同一 pending 目录。
"""文件信号：Claude Code hook 与桌宠/驾驶舱之间的「在等权限确认」通路。

约定目录 ~/.claude/data/desk-buddy/pending/ 下，每个等待确认的会话一个
<session_id>.json。写入原子（tempfile + os.replace），读取对缺失/损坏文件
容错。claude-cockpit 读这个目录,与 desk-buddy 共用同一套 hook 信号。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def data_dir() -> Path:
    return Path.home() / ".claude" / "data" / "desk-buddy"


def pending_dir() -> Path:
    return data_dir() / "pending"


def _safe_name(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id)


def _display_name(cwd: str) -> str:
    """会话的人类可读名：取 cwd 的最后一段目录名（兼容 / 与 \\ 分隔），
    拿不到则回退 'Claude Code'。"""
    if not cwd:
        return "Claude Code"
    base = re.split(r"[\\/]", cwd.rstrip("\\/"))[-1]
    return base or "Claude Code"


def write_pending(session_id: str, message: str = "", cwd: str = "") -> None:
    d = pending_dir()
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{_safe_name(session_id)}.json"
    payload = {
        "session_id": session_id,
        "message": message,
        "cwd": cwd,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    fd, tmp_path = tempfile.mkstemp(prefix=".cc-", suffix=".json", dir=str(d))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def clear_pending(session_id: str) -> None:
    target = pending_dir() / f"{_safe_name(session_id)}.json"
    try:
        target.unlink()
    except (FileNotFoundError, OSError):
        pass


def read_pending() -> dict[str, str]:
    """返回 {session_id: 显示名}。显示名取自各会话的 cwd 目录名（见
    _display_name），旧文件无 cwd 时回退 'Claude Code'。"""
    d = pending_dir()
    if not d.exists():
        return {}
    out: dict[str, str] = {}
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        sid = data.get("session_id") if isinstance(data, dict) else None
        if sid:
            out[sid] = _display_name(data.get("cwd", "") or "")
    return out


def read_pending_full() -> list[dict]:
    """返回每条 pending 的完整记录 [{session_id, message, cwd, at}, ...]。
    匹配成员要用 cwd,而 read_pending() 只给显示名,故另开此函数。"""
    d = pending_dir()
    if not d.exists():
        return []
    out: list[dict] = []
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("session_id"):
            out.append(data)
    return out


def poll_pending(max_age_seconds: int = 600) -> dict[str, str]:
    """轮询用：先清掉陈旧孤儿文件，再返回当前 {session_id: 显示名}。"""
    prune_stale(max_age_seconds)
    return read_pending()


def prune_stale(max_age_seconds: int = 600) -> None:
    d = pending_dir()
    if not d.exists():
        return
    cutoff = time.time() - max_age_seconds
    for f in d.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
