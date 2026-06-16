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
    flags: list[str] = []
    if m.model:
        flags += ["--model", m.model]
    if m.permission_mode == "bypassPermissions":
        flags += ["--dangerously-skip-permissions"]
    elif m.permission_mode and m.permission_mode != "default":
        flags += ["--permission-mode", m.permission_mode]
    return flags


def build_launch_command(m: Member) -> str:
    """返回交给 `cmd /c` 的命令串:开一个带标题的新控制台,cd 到 cwd 后跑 claude。
    `cmd /k` 让窗口在 claude 退出后仍留着(便于看输出 / 重开会话)。"""
    title = window_title(m)
    flags = " ".join(claude_flags(m))
    inner = f'cd /d "{m.cwd}" & claude {flags}'.rstrip()
    return f'start "{title}" cmd /k {inner}'


def launch(m: Member) -> None:
    """真正拉起控制台(独立窗口)。已存在同标题窗口由调用方先判重。"""
    subprocess.Popen(["cmd", "/c", build_launch_command(m)],
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
