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
