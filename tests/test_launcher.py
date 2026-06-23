from pathlib import Path

from claude_cockpit.config import Member
from claude_cockpit.launcher import build_inner_command, claude_flags, window_title


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
