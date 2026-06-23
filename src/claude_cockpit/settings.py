"""面板的小设置(目前仅「提示音开关」),落盘到 settings.json。

与 store.py(窗口句柄缓存)分开:各管各的,互不污染。load() 永远返回补齐默认键的
完整 dict,调用方不必自己兜底;文件缺失/损坏 → 全默认。
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULTS = {"sound_enabled": True}


def _path() -> Path:
    return Path.home() / ".claude" / "data" / "claude-cockpit" / "settings.json"


def load() -> dict:
    """读回设置;缺失/损坏 → 默认。读到的内容会与默认合并,保证键齐全。"""
    data = {}
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    return {**_DEFAULTS, **data}


def save(s: dict) -> None:
    """落盘(失败静默)。"""
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(s), encoding="utf-8")
    except Exception:
        pass
