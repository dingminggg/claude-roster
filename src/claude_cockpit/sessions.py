"""Claude CLI 会话发现:列出某成员 cwd 下的历史会话(id/标题/最后活跃),并可删除。

会话存于 ~/.claude/projects/<编码cwd>/<session-uuid>.jsonl。标题取该文件内最后一条
type=="ai-title" 的 aiTitle(Claude Code 自动生成的人类可读标题);没有则退回首条用户
消息截断;再没有为空(调用方显示「(无标题)」)。纯逻辑、无 Qt,便于测试。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def encode_cwd(cwd: str | Path) -> str:
    """cwd → ~/.claude/projects/ 下的目录名:非字母数字一律变连字符。"""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


@dataclass
class Session:
    id: str
    title: str
    mtime: float


def _user_text(obj: dict) -> str | None:
    """从一条 user 记录里取出文本内容(content 可能是 str 或 block 列表)。"""
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = (part.get("text") or "").strip()
                if t:
                    return t
    return None


def _parse_title(jsonl_path: Path, max_len: int = 40) -> str:
    title = None
    first_user = None
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                t = obj.get("type")
                if t == "ai-title":
                    at = obj.get("aiTitle")
                    if at:
                        title = at          # 取最后一条
                elif t == "user" and first_user is None:
                    first_user = _user_text(obj)
    except OSError:
        return ""
    if title:
        return title
    if first_user:
        return first_user[:max_len]
    return ""


def _sessions_dir(cwd, projects_root, _dirname=None) -> Path:
    root = Path(projects_root) if projects_root is not None else PROJECTS_ROOT
    return root / (_dirname if _dirname is not None else encode_cwd(cwd))


def list_sessions(cwd, limit: int = 12, projects_root=None,
                  _dirname: str | None = None) -> list[Session]:
    """列出该 cwd 对应的历史会话,按最后活跃倒序,最多 limit 条。"""
    d = _sessions_dir(cwd, projects_root, _dirname)
    if not d.is_dir():
        return []
    out: list[Session] = []
    for f in d.glob("*.jsonl"):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        out.append(Session(id=f.stem, title=_parse_title(f), mtime=mtime))
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out[:limit]
