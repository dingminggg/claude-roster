import json
import os
from pathlib import Path

from claude_cockpit import sessions


def test_encode_cwd_windows_path():
    assert sessions.encode_cwd(r"C:\Users\LQ\PhpstormProjects\claude-cockpit") \
        == "C--Users-LQ-PhpstormProjects-claude-cockpit"


def test_encode_cwd_preserves_hyphen_and_replaces_others():
    # 连字符保留;冒号/反斜杠/点/空格都变连字符
    assert sessions.encode_cwd("a-b.c d/e") == "a-b-c-d-e"


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8")


def test_list_sessions_title_prefers_last_ai_title(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s1.jsonl", [
        {"type": "user", "message": {"content": "第一条用户消息"}},
        {"type": "ai-title", "aiTitle": "旧标题"},
        {"type": "ai-title", "aiTitle": "新标题"},
    ])
    out = sessions.list_sessions("anything", projects_root=tmp_path,
                                 _dirname="C--proj")
    assert len(out) == 1
    assert out[0].id == "s1"
    assert out[0].title == "新标题"


def test_list_sessions_falls_back_to_first_user_message(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s2.jsonl", [
        {"type": "user", "message": {"content": "帮我改一下登录逻辑"}},
        {"type": "assistant", "message": {"content": "好的"}},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "帮我改一下登录逻辑"


def test_list_sessions_user_content_as_blocks(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s3.jsonl", [
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "块状文本消息"}]}},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "块状文本消息"


def test_list_sessions_custom_title_beats_ai_title(tmp_path):
    # /rename 设的 custom-title 优先级高于 ai-title(与 /resume 一致)
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s6.jsonl", [
        {"type": "ai-title", "aiTitle": "自动标题"},
        {"type": "custom-title", "customTitle": "123123"},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "123123"


def test_list_sessions_skips_meta_user_messages(tmp_path):
    # 无 ai-title/custom-title 时,回退要跳过 isMeta 和 <system-reminder>/命令 等注入文本,
    # 取第一条真实用户消息(与 /resume 一致)
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s7.jsonl", [
        {"type": "user", "isMeta": True,
         "message": {"content": '<system-reminder> The user named this session "x"'}},
        {"type": "user",
         "message": {"content": [{"type": "text", "text": "<command-name>/clear</command-name>"}]}},
        {"type": "user", "message": {"content": "这才是我真正问的第一句"}},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "这才是我真正问的第一句"


def test_list_sessions_empty_title_when_no_title_no_user(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s4.jsonl", [{"type": "system", "subtype": "x"}])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == ""


def test_list_sessions_skips_bad_lines(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "s5.jsonl").write_text(
        "not json\n" + json.dumps({"type": "ai-title", "aiTitle": "稳"}),
        encoding="utf-8")
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "稳"


def test_list_sessions_sorted_by_mtime_desc_and_limited(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    for i in range(3):
        f = d / f"s{i}.jsonl"
        _write_jsonl(f, [{"type": "ai-title", "aiTitle": f"t{i}"}])
        os.utime(f, (1000 + i, 1000 + i))   # s2 最新
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj",
                                 limit=2)
    assert [s.id for s in out] == ["s2", "s1"]


def test_list_sessions_missing_dir_returns_empty(tmp_path):
    assert sessions.list_sessions("x", projects_root=tmp_path,
                                  _dirname="nope") == []


def test_delete_session_removes_file(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "gone.jsonl").write_text("{}", encoding="utf-8")
    assert sessions.delete_session("x", "gone", projects_root=tmp_path,
                                   _dirname="C--proj") is True
    assert not (d / "gone.jsonl").exists()


def test_delete_session_missing_returns_false(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    assert sessions.delete_session("x", "nope", projects_root=tmp_path,
                                   _dirname="C--proj") is False


def test_fmt_mtime_month_day():
    import datetime as _dt
    ts = _dt.datetime(2026, 6, 18, 9, 30).timestamp()
    assert sessions.fmt_mtime(ts) == "06-18"
