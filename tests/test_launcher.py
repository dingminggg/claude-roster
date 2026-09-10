from pathlib import Path

from claude_cockpit.config import Member
from claude_cockpit.launcher import (
    CHILD_SESSION_MARKER,
    build_inner_command,
    child_env,
    claude_flags,
    window_title,
)


def _m(**kw):
    kw.setdefault("cwd", Path("."))
    return Member(name=kw.pop("name", "shop"), **kw)


def test_window_title():
    assert window_title(_m(name="driver")) == "CCKPT:driver"


def test_flags_no_auto_resume():
    # 启动不自动 --resume(自动 resume 会抢走/关闭已开着的会话窗口)
    assert "--resume" not in claude_flags(_m(permission_mode="default"))
    assert "--resume" not in claude_flags(_m(permission_mode="bypassPermissions"))


def test_flags_bypass():
    assert "--dangerously-skip-permissions" in claude_flags(
        _m(permission_mode="bypassPermissions"))


def test_flags_mode_and_model():
    f = claude_flags(_m(permission_mode="plan", model="opus"))
    assert "--permission-mode" in f and "plan" in f
    assert "--model" in f and "opus" in f


def test_flags_default_no_model():
    f = claude_flags(_m(permission_mode="default"))
    assert "--model" not in f


def test_build_inner_command_contains_cwd_title_and_claude(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_inner_command(m)
    assert "CCKPT:shop" in cmd
    assert str(tmp_path) in cmd
    assert "claude" in cmd
    assert cmd.startswith("title ")  # 先设标题,供按标题查找


def test_build_inner_command_with_resume(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_inner_command(m, session_id="abc-123")
    assert "claude --resume abc-123" in cmd


def test_build_inner_command_without_resume_unchanged(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_inner_command(m)
    assert "--resume" not in cmd
    assert "claude" in cmd


def test_child_env_strips_child_session_marker():
    # cockpit 若从 Claude 会话里启动会继承该标记;透传给成员 claude 会让它关闭 transcript 保存
    base = {CHILD_SESSION_MARKER: "1", "PATH": "x", "CLAUDE_COCKPIT_PY": "py"}
    env = child_env(base)
    assert CHILD_SESSION_MARKER not in env
    assert env["PATH"] == "x" and env["CLAUDE_COCKPIT_PY"] == "py"


def test_child_env_does_not_mutate_input():
    base = {CHILD_SESSION_MARKER: "1", "PATH": "x"}
    child_env(base)
    assert base == {CHILD_SESSION_MARKER: "1", "PATH": "x"}


def test_child_env_without_marker_is_passthrough():
    base = {"PATH": "x"}
    assert child_env(base) == {"PATH": "x"}


def test_child_env_strips_the_whole_parent_session_family():
    """成员是各自独立的顶层会话:父会话的身份标记一个都不该带进去。

    里层 claude 看到 CLAUDECODE=1 就按「嵌套在别人里面跑」处理,渲染降级成
    近乎黑白(踩过)。按前缀剔,别列白名单——这族变量以后还会加。
    """
    from claude_cockpit.launcher import child_env
    base = {
        "CLAUDECODE": "1",
        "CLAUDE_CODE_CHILD_SESSION": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "CLAUDE_CODE_SESSION_ID": "abc",
        "CLAUDE_CODE_MESSAGING_SOCKET": r"\.\pipe\x",
        "CLAUDE_PID": "123",
        "CLAUDE_EFFORT": "medium",
        # 这两个不是父会话标记,要留着
        "CLAUDE_COCKPIT_PY": r"C:\py.exe",
        "PATH": "keep-me",
    }
    env = child_env(base)
    assert set(env) == {"CLAUDE_COCKPIT_PY", "PATH"}
    assert base["CLAUDECODE"] == "1"        # 不改动入参


def test_child_env_drops_no_color_only_when_launched_by_claude():
    """Claude Code 给子进程注入 NO_COLOR=1(让工具输出干净)。cockpit 从 Claude
    会话里被启动时会继承它,再传给成员窗口 → 里层 claude 一律不上色、纯黑白
    (踩过;换主题救不回来,NO_COLOR 一句话全禁)。

    但用户自己设的 NO_COLOR 是明确偏好:没有 Claude 会话标记时必须留着。
    """
    from claude_cockpit.launcher import child_env
    # 从 Claude 会话里启动:注入的 NO_COLOR 要剔掉
    got = child_env({"CLAUDECODE": "1", "NO_COLOR": "1", "PATH": "x"})
    assert got == {"PATH": "x"}

    # 正常启动(开机自启 / 小青蛙拉起):用户的偏好照旧
    got2 = child_env({"NO_COLOR": "1", "PATH": "x"})
    assert got2 == {"NO_COLOR": "1", "PATH": "x"}
