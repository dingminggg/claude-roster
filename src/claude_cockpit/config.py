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


def validate_member(m: Member, existing_names: set[str] | None = None) -> None:
    if not NAME_RE.match(m.name):
        raise ValueError(f"成员名只能用字母/数字/下划线/连字符: {m.name!r}")
    if existing_names and m.name in existing_names:
        raise ValueError(f"成员名已存在: {m.name}")
    if not m.cwd.is_dir():
        raise ValueError(f"成员 {m.name} 的目录不存在: {m.cwd}")


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
        validate_member(m)
        members.append(m)
    if not members:
        raise ValueError("agents.yaml 里至少要有一个成员")
    names = [m.name for m in members]
    if len(set(names)) != len(names):
        raise ValueError(f"成员名重复: {names}")
    return members


def save_config(path: str | Path, members: list[Member]) -> None:
    """把成员列表写回 agents.yaml(覆盖)。"""
    items = []
    for m in members:
        d = {"name": m.name, "cwd": str(m.cwd), "emoji": m.emoji,
             "color": m.color, "permission_mode": m.permission_mode}
        if m.model:
            d["model"] = m.model
        items.append(d)
    body = yaml.safe_dump({"agents": items}, allow_unicode=True, sort_keys=False)
    text = "# claude-cockpit 成员清单(由面板自动写回)\n" + body
    Path(path).write_text(text, encoding="utf-8")
