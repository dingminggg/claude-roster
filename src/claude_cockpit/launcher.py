"""为每个成员拉起一个独立 claude 控制台窗口。

启动命令的确切 flag 以 `claude --help` 为准——实现/验证时核对:
  - 模型:`--model <m>`
  - 权限:bypassPermissions → `--dangerously-skip-permissions`;
          其余 → `--permission-mode <default|acceptEdits|plan>`
"""
from __future__ import annotations

import subprocess

from .config import Member

TITLE_PREFIX = "CCKPT:"


def window_title(m: Member) -> str:
    return f"{TITLE_PREFIX}{m.name}"


def claude_flags(m: Member) -> list[str]:
    # 始终带 --resume:控制台起来后弹历史对话列表让你选,接上之前的会话
    # (不带的话每次都是空白新会话)。
    flags: list[str] = ["--resume"]
    if m.model:
        flags += ["--model", m.model]
    if m.permission_mode == "bypassPermissions":
        flags += ["--dangerously-skip-permissions"]
    elif m.permission_mode and m.permission_mode != "default":
        flags += ["--permission-mode", m.permission_mode]
    return flags


def build_inner_command(m: Member) -> str:
    """新控制台里要执行的命令:先 `title` 设窗口标题(供按标题查找),再 cd 到 cwd,
    最后跑 claude。`cmd /k` 让窗口在 claude 退出后仍留着(便于看输出 / 重开会话)。"""
    flags = " ".join(claude_flags(m))
    return f'title {window_title(m)} & cd /d "{m.cwd}" & claude {flags}'.rstrip()


def launch(m: Member) -> None:
    """真正拉起控制台:用 CREATE_NEW_CONSOLE 让子进程自带一个新控制台窗口
    (不走 `start`,避免嵌套引号被 cmd 拆坏)。已存在同标题窗口由调用方先判重。"""
    subprocess.Popen(
        f"cmd /k {build_inner_command(m)}",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
