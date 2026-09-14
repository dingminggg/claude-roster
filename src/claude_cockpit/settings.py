"""面板的小设置(提示音开关 / 是否置顶),落盘到 settings.json。

与 store.py(窗口句柄缓存)分开:各管各的,互不污染。load() 永远返回补齐默认键的
完整 dict,调用方不必自己兜底;文件缺失/损坏 → 全默认。
"""
from __future__ import annotations

import json
from pathlib import Path

# seen_messages:每个员工「对话记录看到哪儿了」的时间水位 {员工名: epoch 秒}。
# 桌上那部手机角上那颗红点按它亮(见 history.unread_count)。
_DEFAULTS = {"sound_enabled": True, "always_on_top": True, "seen_messages": {}}


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
    merged = {**_DEFAULTS, **data}
    # 坏数据退回缺省;即便类型对,只要它就是 _DEFAULTS["seen_messages"] 那个共享
    # 实例(缺键时会被原样带出来),也要换成新 dict——否则调用方往里一写就污染了
    # 模块级默认值,下次 load() 就不再是空的了。
    seen = merged.get("seen_messages")
    if not isinstance(seen, dict) or seen is _DEFAULTS["seen_messages"]:
        merged["seen_messages"] = dict(seen) if isinstance(seen, dict) else {}
    return merged


def save(s: dict) -> None:
    """落盘(失败静默)。"""
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(s), encoding="utf-8")
    except Exception:
        pass
