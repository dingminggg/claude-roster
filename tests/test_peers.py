"""peers.read_peers / match_peers:把 ~/.claude/sessions/<pid>.json 对到成员。"""
import json

import pytest

from claude_cockpit.config import Member
from claude_cockpit.peers import Peer, match_peers, read_peers

NOW = 1_000_000.0          # 秒
NOW_MS = int(NOW * 1000)


def _write(d, pid, *, name, cwd, status="idle", updated=NOW_MS, **extra):
    rec = {"pid": pid, "cwd": cwd, "name": name, "status": status,
           "updatedAt": updated, "messagingSocketPath": r"\.\pipe\LOCAL\cc-msg-x"}
    rec.update(extra)
    (d / f"{pid}.json").write_text(json.dumps(rec), encoding="utf-8")


def _alive_all(_pid):
    return True


def test_reads_name_cwd_status(tmp_path):
    _write(tmp_path, 42, name="fad-backend-2-f3",
           cwd=r"C:\proj\fad-backend-2", status="busy")
    peers = read_peers(tmp_path, is_alive=_alive_all, now=NOW)
    assert len(peers) == 1
    p = peers[0]
    assert (p.name, p.status, p.pid) == ("fad-backend-2-f3", "busy", 42)
    assert p.cwd == r"C:\proj\fad-backend-2"


def test_missing_dir_returns_empty(tmp_path):
    assert read_peers(tmp_path / "nope", is_alive=_alive_all, now=NOW) == []


def test_dead_pid_dropped(tmp_path):
    _write(tmp_path, 1, name="a-11", cwd=r"C:\a")
    _write(tmp_path, 2, name="b-22", cwd=r"C:\b")
    peers = read_peers(tmp_path, is_alive=lambda pid: pid == 2, now=NOW)
    assert [p.name for p in peers] == ["b-22"]


def test_stale_record_dropped_even_if_pid_alive(tmp_path):
    """pid 会被系统复用:光看 pid 会把陈旧残留当成活会话,再加时效兜底。"""
    _write(tmp_path, 1, name="old-11", cwd=r"C:\a", updated=NOW_MS - 3600 * 1000)
    assert read_peers(tmp_path, is_alive=_alive_all, now=NOW) == []


def test_record_without_timestamp_kept(tmp_path):
    """拿不到时间戳就只靠 pid 判活,别一刀切当陈旧丢掉。"""
    _write(tmp_path, 1, name="a-11", cwd=r"C:\a", updated=None)
    (tmp_path / "1.json").write_text(
        json.dumps({"pid": 1, "cwd": r"C:\a", "name": "a-11", "status": "idle"}),
        encoding="utf-8")
    assert [p.name for p in read_peers(tmp_path, is_alive=_alive_all, now=NOW)] == ["a-11"]


def test_malformed_and_nameless_files_ignored(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "9.json").write_text(json.dumps({"pid": 9, "cwd": r"C:\a"}),
                                     encoding="utf-8")   # 没有 name
    _write(tmp_path, 10, name="ok-11", cwd=r"C:\a")
    assert [p.name for p in read_peers(tmp_path, is_alive=_alive_all, now=NOW)] == ["ok-11"]


def test_missing_status_becomes_empty(tmp_path):
    (tmp_path / "1.json").write_text(
        json.dumps({"pid": 1, "cwd": r"C:\a", "name": "a-11", "updatedAt": NOW_MS}),
        encoding="utf-8")
    assert read_peers(tmp_path, is_alive=_alive_all, now=NOW)[0].status == ""


def _member(name, cwd):
    return Member(name=name, cwd=cwd)


def test_match_by_cwd_ignoring_case_and_separators():
    peers = [Peer(name="fad-backend-2-f3", cwd=r"C:\Proj\Fad-Backend-2/",
                  status="busy", pid=1, updated_at=NOW_MS)]
    got = match_peers(peers, [_member("fad-2", r"c:\proj\fad-backend-2")])
    assert got["fad-2"].name == "fad-backend-2-f3"


def test_unmatched_cwd_absent():
    peers = [Peer(name="other-11", cwd=r"C:\elsewhere", status="idle",
                  pid=1, updated_at=NOW_MS)]
    assert match_peers(peers, [_member("fad", r"C:\proj\fad")]) == {}


def test_same_cwd_picks_most_recently_updated():
    """同一目录开了两个 claude:面板只有一张卡,取最近活动的那个,结果稳定。"""
    peers = [
        Peer(name="old-11", cwd=r"C:\a", status="idle", pid=1, updated_at=NOW_MS - 5000),
        Peer(name="new-22", cwd=r"C:\a", status="busy", pid=2, updated_at=NOW_MS),
    ]
    got = match_peers(peers, [_member("a", r"C:\a")])
    assert got["a"].name == "new-22"
    assert got["a"].status == "busy"
