from pathlib import Path

from claude_cockpit.config import Member
from claude_cockpit.matching import (
    latest_message_for_cwd, match_pending, sessions_for_cwd,
)


def _m(name, cwd):
    return Member(name=name, cwd=Path(cwd))


def test_match_by_cwd_exact(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    members = [_m("alpha", a), _m("beta", b)]
    pending = [{"session_id": "s1", "cwd": str(a)}]
    assert match_pending(pending, members) == {"alpha"}


def test_match_normalizes_separators_and_case(tmp_path):
    a = tmp_path / "Proj"
    a.mkdir()
    members = [_m("alpha", a)]
    # 分隔符/大小写/尾斜杠都不该影响匹配
    weird = str(a).replace("\\", "/").upper() + "/"
    pending = [{"session_id": "s1", "cwd": weird}]
    assert match_pending(pending, members) == {"alpha"}


def test_unrelated_cwd_ignored(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    members = [_m("alpha", a)]
    pending = [{"session_id": "s9", "cwd": str(tmp_path / "elsewhere")}]
    assert match_pending(pending, members) == set()


def test_missing_cwd_ignored(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    members = [_m("alpha", a)]
    assert match_pending([{"session_id": "s1"}], members) == set()


def test_sessions_for_cwd_collects_all_matching(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    recs = [
        {"session_id": "s1", "cwd": str(a)},
        {"session_id": "s2", "cwd": str(a).replace("\\", "/").upper() + "/"},
        {"session_id": "s3", "cwd": str(tmp_path / "elsewhere")},
    ]
    # 同一 cwd 的所有会话都要收上来(分隔符/大小写/尾斜杠归一),别的不收
    assert sorted(sessions_for_cwd(recs, a)) == ["s1", "s2"]


def test_sessions_for_cwd_skips_bad_records(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    recs = [
        {"session_id": "s1", "cwd": str(a)},
        {"cwd": str(a)},                 # 无 session_id
        {"session_id": "s2"},            # 无 cwd
        "not-a-dict",
    ]
    assert sessions_for_cwd(recs, a) == ["s1"]


def test_latest_message_for_cwd_picks_the_newest():
    """同一个 cwd 可能留着好几条会话的 turn-ended,点工位要冒的是最新那句。"""
    recs = [
        {"session_id": "a", "cwd": r"C:\proj\fad", "message": "旧的那句",
         "at": "2026-09-15T01:00:00+00:00"},
        {"session_id": "b", "cwd": r"C:\proj\fad", "message": "改完了。",
         "at": "2026-09-15T02:00:00+00:00"},
        {"session_id": "c", "cwd": r"C:\proj\etl", "message": "别人的",
         "at": "2026-09-15T03:00:00+00:00"},
    ]
    assert latest_message_for_cwd(recs, r"C:/proj/fad") == "改完了。"


def test_latest_message_for_cwd_empty_when_nothing_matches():
    assert latest_message_for_cwd([], r"C:\proj\fad") == ""
    assert latest_message_for_cwd([{"cwd": r"C:\other"}], r"C:\proj\fad") == ""
    assert latest_message_for_cwd(["坏数据"], r"C:\proj\fad") == ""
