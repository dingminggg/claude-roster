"""把 cockpit 启动的窗口句柄缓存落盘。

退出/重启 cockpit 后,内存里的 hwnds 会丢。落盘后重启可载回:凡是句柄仍指向
一个存活的控制台窗口(winman.is_window + is_console_window)就复用,不必重开。
"""
from __future__ import annotations

import json
from pathlib import Path


def _path() -> Path:
    return Path.home() / ".claude" / "data" / "claude-cockpit" / "handles.json"


def load() -> dict[str, int]:
    """读回 {成员名: hwnd};文件缺失/损坏 → {}。"""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data.items()}
    except Exception:
        return {}


def dedupe(hwnds: dict[str, int]) -> dict[str, int]:
    """同一句柄被多个成员缓存时只认最早写入的那个:后来者是误抓(抓句柄时
    子串匹配到了兄弟成员的窗口),点它会弹出别人的会话。"""
    seen: set[int] = set()
    out: dict[str, int] = {}
    for n, h in hwnds.items():
        if h in seen:
            continue
        seen.add(h)
        out[n] = h
    return out


def save(hwnds: dict[str, int]) -> None:
    """落盘(原子性要求不高,失败静默)。"""
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(hwnds), encoding="utf-8")
    except Exception:
        pass
