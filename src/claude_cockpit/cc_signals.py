"""文件信号:Claude Code hook 与驾驶舱之间的两条独立通路(权限 pending / 答完一轮)。

均在 ~/.claude/data/claude-cockpit/ 下:pending/(每个等权限确认的会话一个
<session_id>.json)、turn-ended/(答完一轮)。写入原子(tempfile + os.replace),
读取对缺失/损坏文件容错。本项目自带这套信号,不再依赖 desk-buddy(已解耦)。
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
    return Path.home() / ".claude" / "data" / "claude-cockpit"


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


def _atomic_write(d: Path, session_id: str, message: str, cwd: str) -> None:
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


def _remove(d: Path, session_id: str) -> None:
    try:
        (d / f"{_safe_name(session_id)}.json").unlink()
    except (FileNotFoundError, OSError):
        pass


def _read_full(d: Path) -> list[dict]:
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


def _prune(d: Path, max_age_seconds: int) -> None:
    if not d.exists():
        return
    cutoff = time.time() - max_age_seconds
    for f in d.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def write_pending(session_id: str, message: str = "", cwd: str = "") -> None:
    _atomic_write(pending_dir(), session_id, message, cwd)


def clear_pending(session_id: str) -> None:
    _remove(pending_dir(), session_id)


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
    return _read_full(pending_dir())


def poll_pending(max_age_seconds: int = 600) -> dict[str, str]:
    """轮询用：先清掉陈旧孤儿文件，再返回当前 {session_id: 显示名}。"""
    prune_stale(max_age_seconds)
    return read_pending()


def prune_stale(max_age_seconds: int = 600) -> None:
    _prune(pending_dir(), max_age_seconds)


# ── 「答完一轮」信号:成员答完一轮(Stop hook 写入)。──
# 与「权限 pending」分两个目录,语义独立:pending=在等你确认,turn-ended=答完该你看了。
def turn_dir() -> Path:
    return data_dir() / "turn-ended"


def write_turn_ended(session_id: str, message: str = "", cwd: str = "") -> None:
    _atomic_write(turn_dir(), session_id, message, cwd)


def clear_turn_ended(session_id: str) -> None:
    _remove(turn_dir(), session_id)


def read_turn_ended_full() -> list[dict]:
    return _read_full(turn_dir())


def prune_turn_ended(max_age_seconds: int = 1800) -> None:
    _prune(turn_dir(), max_age_seconds)
