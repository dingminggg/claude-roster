"""Claude CLI 会话发现:列出某成员 cwd 下的历史会话(id/标题/最后活跃),并可删除。

会话存于 ~/.claude/projects/<编码cwd>/<session-uuid>.jsonl。标题与 /resume 选择器对齐,
优先级:最后一条 custom-title(用户 /rename 设的)→ 最后一条 ai-title(Claude Code 自动
生成)→ 首条「真实」用户消息(跳过 isMeta 及 <system-reminder>/<command-…> 等注入文本,
截断)→ 为空(调用方显示「(无标题)」)。纯逻辑、无 Qt,便于测试。
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


# 回退取首条用户消息时,跳过这些「非人类输入」的注入文本(与 /resume 一致)
_META_PREFIXES = ("<system-reminder", "<command-", "<local-command", "Caveat:")


def _parse_title(jsonl_path: Path, max_len: int = 40) -> str:
    custom = None
    ai = None
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
                if t == "custom-title":
                    ct = obj.get("customTitle")
                    if ct:
                        custom = ct         # 取最后一条
                elif t == "ai-title":
                    at = obj.get("aiTitle")
                    if at:
                        ai = at             # 取最后一条
                elif t == "user" and first_user is None and not obj.get("isMeta"):
                    tx = _user_text(obj)
                    if tx and not tx.lstrip().startswith(_META_PREFIXES):
                        first_user = tx
    except OSError:
        return ""
    if custom:
        return custom
    if ai:
        return ai
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


def delete_session(cwd, session_id: str, projects_root=None,
                   _dirname: str | None = None) -> bool:
    """删除某会话的 .jsonl 文件;成功 True,文件不存在/失败 False。"""
    f = _sessions_dir(cwd, projects_root, _dirname) / f"{session_id}.jsonl"
    try:
        f.unlink()
        return True
    except OSError:
        return False


def fmt_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%m-%d")
