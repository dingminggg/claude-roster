"""读 ~/.claude/sessions/<pid>.json,把「同机的 Claude 会话」对到成员。

Claude Code 会给每个会话在 ~/.claude/sessions/ 落一份 <pid>.json,里面有 cwd、
会话名(会话间发消息的地址)、忙/闲状态。面板拿这两样东西干两件事:
  1. 右键「复制会话地址」——会话名不是成员名(成员叫 fad-2,会话叫 fad-backend-2-f3),
     不给出来用户没法对上;
  2. 运行键从「运行中」细化成「忙碌中 / 空闲」。

**这是 Claude Code 的内部文件,不是公开契约。** 所以本模块只读不写、异常全吞:
格式一变或目录不在,一律降级成「拿不到」(read_peers 返回空),面板照旧按窗口句柄
显示「运行中」,不影响任何既有功能。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Member
from .matching import norm_path

SESSIONS_DIR = Path.home() / ".claude" / "sessions"

# pid 判活的兜底:pid 会被系统复用,光看 pid 会把陈旧残留当成活会话。
# updatedAt 超过这个秒数没动就不认(与 cc_signals 的 prune 口径一致)。
_STALE_SEC = 1800


@dataclass(frozen=True)
class Peer:
    name: str           # 会话名 = 会话间发消息的地址
    cwd: str
    status: str         # "busy" / "idle" / ""(字段缺失时)
    pid: int
    updated_at: float   # json 原样(毫秒);仅用于同 cwd 多会话时挑最近活动的那个


def pid_alive(pid: int) -> bool:
    """Windows:进程是否还活着(会话 json 不会自己清,得靠 pid 判活)。"""
    if pid <= 0:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    except Exception:
        return False


def read_peers(sessions_dir=None, is_alive=None, now: float | None = None) -> list[Peer]:
    """列出当前还活着的同机 Claude 会话。目录不在 / 文件坏 → 跳过,绝不抛。"""
    d = Path(sessions_dir) if sessions_dir is not None else SESSIONS_DIR
    alive = is_alive if is_alive is not None else pid_alive
    now_ms = (now if now is not None else time.time()) * 1000

    try:
        files = sorted(d.glob("*.json"))
    except Exception:
        return []

    peers: list[Peer] = []
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue                            # 半写入/坏文件:跳过
        if not isinstance(rec, dict):
            continue
        name = str(rec.get("name") or "").strip()
        cwd = str(rec.get("cwd") or "").strip()
        if not name or not cwd:
            continue
        try:
            pid = int(rec.get("pid") or 0)
        except (TypeError, ValueError):
            continue
        if not alive(pid):
            continue
        ts = rec.get("updatedAt") or rec.get("startedAt") or 0
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = 0.0
        # 有时间戳才做时效判断;没有就只信 pid,别一刀切丢掉
        if ts and now_ms - ts > _STALE_SEC * 1000:
            continue
        peers.append(Peer(name=name, cwd=cwd,
                          status=str(rec.get("status") or ""), pid=pid, updated_at=ts))
    return peers


def match_peers(peers: list[Peer], members: list[Member]) -> dict[str, Peer]:
    """按规范化 cwd 把会话对到成员名(同 match_pending 的口径)。
    同一目录开了多个 claude 时面板只有一张卡:取 updated_at 最大的那个,保证结果稳定。"""
    by_cwd = {norm_path(m.cwd): m.name for m in members}
    out: dict[str, Peer] = {}
    for p in peers:
        name = by_cwd.get(norm_path(p.cwd))
        if not name:
            continue
        cur = out.get(name)
        if cur is None or p.updated_at > cur.updated_at:
            out[name] = p
    return out
