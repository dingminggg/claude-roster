"""为每个成员拉起一个独立 claude 控制台窗口。

启动命令的确切 flag 以 `claude --help` 为准——实现/验证时核对:
  - 模型:`--model <m>`
  - 权限:bypassPermissions → `--dangerously-skip-permissions`;
          其余 → `--permission-mode <default|acceptEdits|plan>`
"""
from __future__ import annotations

import os
import subprocess
from typing import Mapping

from .config import Member

TITLE_PREFIX = "CCKPT:"

# claude 给自己拉起的 shell 设这个标记;在带标记的环境里启动的 claude 会把自己当嵌套子会话,
# 关闭 transcript 保存(无法 --resume、面板会话下拉列不到)。cockpit 若曾从某个 Claude 会话里
# 被启动就会继承它,再经 Popen 透传给每个成员窗口——所以启动前必须剔掉。
CHILD_SESSION_MARKER = "CLAUDE_CODE_CHILD_SESSION"

# 除了上面那个,「我正跑在某个 Claude Code 会话里」这件事还由一整族变量宣告。
# cockpit 若从某个 Claude 会话里被启动就会继承它们,再透传给成员窗口——里层
# claude 于是把自己当成嵌套在别人里面跑,渲染降级(界面近乎黑白,踩过)。
# 成员是**各自独立的顶层会话**,父会话的身份标记一个都不该带进去。
# 按前缀剔除而不是列白名单:这族变量以后还会加,漏一个又是一次同样的坑。
PARENT_SESSION_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID",
                           "CLAUDE_EFFORT")


def child_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """返回给成员 claude 用的环境:复制 base(默认 os.environ),剔除父会话的身份标记。
    不改动入参;除了那族标记,其他变量原样透传。

    还有一个 `NO_COLOR`:Claude Code 会给自己拉起的子进程注入它(让工具输出干净)。
    cockpit 若从某个 Claude 会话里被启动就会继承,再传给成员窗口——里层 claude
    于是一律不上色,界面纯黑白(踩过,而且换主题完全救不回来:NO_COLOR 一句话全禁)。
    **只在确认自己跑在 Claude 会话里时才剔它**:用户自己设的 NO_COLOR 是明确偏好,
    不该被我们悄悄抹掉。
    """
    src = os.environ if base is None else base
    env = dict(src)
    launched_by_claude = any(k in src for k in ("CLAUDECODE", CHILD_SESSION_MARKER,
                                                "CLAUDE_CODE_ENTRYPOINT"))
    env.pop(CHILD_SESSION_MARKER, None)
    for k in [k for k in env if k.startswith(PARENT_SESSION_PREFIXES)]:
        env.pop(k, None)
    if launched_by_claude:
        env.pop("NO_COLOR", None)
    return env


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
    session_id 透传给 build_inner_command 决定是否 --resume。
    env=child_env() 剔除继承的子会话标记,保证成员 claude 是正常顶层会话。"""
    subprocess.Popen(
        f"cmd /k {build_inner_command(m, session_id)}",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=child_env(),
    )
