"""文件信号:Claude Code hook 与驾驶舱之间的几条独立通路。

均在 ~/.claude/data/claude-cockpit/ 下:
  pending/      每个等权限确认的会话一个 <session_id>.json(**状态**,清了才没)
  turn-ended/   答完一轮(**状态**)
  speaking/     正在朗读(**状态**,由 TTS 写)
  messages/     会话之间发了消息(**事件**:读一次删一次,同一会话可以连着好几条)

写入原子(tempfile + os.replace),读取对缺失/损坏文件容错。本项目自带这套信号,
不再依赖 desk-buddy(已解耦)。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
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


# ── 「会话间发消息」信号:PostToolUse hook(匹配 SendMessage 工具)写,驾驶舱读走就删。──
# 和上面两条通道不同,**这是事件不是状态**:同一个会话可能连发好几条,所以文件名带
# 时间戳 + 随机后缀(不能像 pending 那样按 session_id 覆盖),读一次删一次。


def messages_dir() -> Path:
    return data_dir() / "messages"


def write_message(from_cwd: str, to_name: str) -> None:
    """记一笔「谁给谁发了消息」。from 是发送方的 cwd(用来对成员),to 是**会话名**
    (不是成员名——成员叫 fad-2、会话叫 fad-backend-2-f3,对应关系由 peers 给)。"""
    if not from_cwd or not to_name:
        return
    d = messages_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = {"from_cwd": from_cwd, "to_name": to_name, "at": time.time()}
    fd, tmp = tempfile.mkstemp(prefix=".cc-", suffix=".json", dir=str(d))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, d / f"{time.time_ns()}-{uuid.uuid4().hex[:6]}.json")
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def take_messages(max_age_seconds: int = 30) -> list[dict]:
    """**读走**(并删掉)所有消息事件,按时间排序。

    超龄的直接丢不补演:驾驶舱没开着的时候攒下一堆,开面板时一窝蜂全跑起来没意义。
    """
    d = messages_dir()
    if not d.exists():
        return []
    cutoff = time.time() - max_age_seconds
    out: list[dict] = []
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            rec = None
        try:
            f.unlink()                      # 读一次就删,事件不留底
        except OSError:
            pass
        if isinstance(rec, dict) and float(rec.get("at") or 0) >= cutoff:
            out.append(rec)
    return out


# ── 「正在朗读」信号:TTS(~/.claude/hooks/tts_stop.py)播放某会话回复期间写入,播完删。──
# 记录含 {cwd, pid}:cwd 用来匹配成员显示 🔊,pid 让消费方自愈(播放进程没了就丢弃,不会常亮)。
# 只读,不写(写在 TTS 脚本侧)。
def speaking_dir() -> Path:
    return data_dir() / "speaking"


def read_speaking_full() -> list[dict]:
    """[{cwd, pid, at}, ...]。不同于 pending/turn-ended,朗读信号按 cwd 记录(无 session_id)。"""
    d = speaking_dir()
    if not d.exists():
        return []
    out: list[dict] = []
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("cwd"):
            out.append(data)
    return out


def remove_speaking_file(cwd: str) -> None:
    """按 cwd 删掉一条朗读信号(消费方发现进程已死时清理孤儿用)。"""
    try:
        (speaking_dir() / f"{_safe_name(cwd)}.json").unlink()
    except (FileNotFoundError, OSError):
        pass


def prune_speaking(max_age_seconds: int = 1800) -> None:
    _prune(speaking_dir(), max_age_seconds)
