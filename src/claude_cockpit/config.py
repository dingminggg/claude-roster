"""agents.yaml 加载与校验。成员 = 一个真 claude 控制台。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[\w-]+$")


@dataclass
class Member:
    name: str
    cwd: Path
    emoji: str = "🤖"
    color: str = "#3b82f6"
    model: str | None = None
    permission_mode: str = "default"


def _validate(m: Member) -> None:
    if not NAME_RE.match(m.name):
        raise ValueError(f"成员名只能用字母/数字/下划线/连字符: {m.name!r}")
    if not m.cwd.is_dir():
        raise ValueError(f"成员 {m.name} 的 cwd 不存在: {m.cwd}")


def load_config(path: str | Path = "agents.yaml") -> list[Member]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    members: list[Member] = []
    for item in raw.get("agents", []):
        m = Member(
            name=item["name"],
            cwd=Path(str(item["cwd"]).strip().strip('"')),
            emoji=item.get("emoji", "🤖"),
            color=item.get("color", "#3b82f6"),
            model=item.get("model"),
            permission_mode=item.get("permission_mode", "default"),
        )
        _validate(m)
        members.append(m)
    if not members:
        raise ValueError("agents.yaml 里至少要有一个成员")
    names = [m.name for m in members]
    if len(set(names)) != len(names):
        raise ValueError(f"成员名重复: {names}")
    return members
