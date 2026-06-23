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
    # 不自动 --resume:resume 由用户在面板下拉里显式选(确定没在别处开着的那条),
    # 经 build_inner_command(session_id=...) 传入,不在这里加。
    flags: list[str] = []
    if m.model:
        flags += ["--model", m.model]
    if m.permission_mode == "bypassPermissions":
        flags += ["--dangerously-skip-permissions"]
    elif m.permission_mode and m.permission_mode != "default":
        flags += ["--permission-mode", m.permission_mode]
    return flags


def build_inner_command(m: Member, session_id: str | None = None) -> str:
    """新控制台里要执行的命令:先 `title` 设窗口标题(供按标题抓句柄),cd 到 cwd,
    再停顿 ~3 秒让标题稳稳挂着,最后才跑 claude(claude 启动后会改标题)。
    句柄在窗口刚出现那一刻就被抓走、缓存起来,之后改名都不影响;这 3 秒只是
    给抓取留足富余,彻底避免「抢时间」。`cmd /k` 让窗口在 claude 退出后仍留着。

    session_id 非空 → 拼 `claude --resume <id>`,直接续接用户在面板下拉里选的那条
    会话(由用户挑、确定没在别处开着);为空 → 起全新会话(不碰任何已有窗口)。"""
    flags = " ".join(claude_flags(m))
    resume = f"--resume {session_id} " if session_id else ""
    # ping 当延时(比 timeout 更不挑环境,不依赖 stdin):-n 4 ≈ 3 秒
    return (f'title {window_title(m)} & cd /d "{m.cwd}" & '
            f'ping -n 4 127.0.0.1 >nul & claude {resume}{flags}').rstrip()


def launch(m: Member, session_id: str | None = None) -> None:
    """真正拉起控制台:用 CREATE_NEW_CONSOLE 让子进程自带一个新控制台窗口
    (不走 `start`,避免嵌套引号被 cmd 拆坏)。已存在同标题窗口由调用方先判重。
    session_id 透传给 build_inner_command 决定是否 --resume。"""
    subprocess.Popen(
        f"cmd /k {build_inner_command(m, session_id)}",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
