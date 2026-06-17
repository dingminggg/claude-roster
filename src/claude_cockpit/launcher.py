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
    # 不在启动时自动 --resume:resume 一个"已经开着"的会话会把它从原窗口抢走、
    # 导致原窗口被关。起全新会话最安全(不碰任何已有窗口)。
    # 要接旧对话,在窗口里手动输入 /resume —— 由你挑确定没在别处开着的那条。
    flags: list[str] = []
    if m.model:
        flags += ["--model", m.model]
    if m.permission_mode == "bypassPermissions":
        flags += ["--dangerously-skip-permissions"]
    elif m.permission_mode and m.permission_mode != "default":
        flags += ["--permission-mode", m.permission_mode]
    return flags


def build_inner_command(m: Member) -> str:
    """新控制台里要执行的命令:先 `title` 设窗口标题(供按标题抓句柄),cd 到 cwd,
    再停顿 ~3 秒让标题稳稳挂着,最后才跑 claude(claude 启动后会改标题)。
    句柄在窗口刚出现那一刻就被抓走、缓存起来,之后改名都不影响;这 3 秒只是
    给抓取留足富余,彻底避免「抢时间」。`cmd /k` 让窗口在 claude 退出后仍留着。"""
    flags = " ".join(claude_flags(m))
    # ping 当延时(比 timeout 更不挑环境,不依赖 stdin):-n 4 ≈ 3 秒
    return (f'title {window_title(m)} & cd /d "{m.cwd}" & '
            f'ping -n 4 127.0.0.1 >nul & claude {flags}').rstrip()


def launch(m: Member) -> None:
    """真正拉起控制台:用 CREATE_NEW_CONSOLE 让子进程自带一个新控制台窗口
    (不走 `start`,避免嵌套引号被 cmd 拆坏)。已存在同标题窗口由调用方先判重。"""
    subprocess.Popen(
        f"cmd /k {build_inner_command(m)}",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
