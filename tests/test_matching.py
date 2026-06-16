from pathlib import Path

from claude_cockpit.config import Member
from claude_cockpit.matching import match_pending


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
