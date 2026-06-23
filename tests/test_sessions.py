from pathlib import Path

from claude_cockpit import sessions


def test_encode_cwd_windows_path():
    assert sessions.encode_cwd(r"C:\Users\LQ\PhpstormProjects\claude-cockpit") \
        == "C--Users-LQ-PhpstormProjects-claude-cockpit"


def test_encode_cwd_preserves_hyphen_and_replaces_others():
    # 连字符保留;冒号/反斜杠/点/空格都变连字符
    assert sessions.encode_cwd("a-b.c d/e") == "a-b-c-d-e"
