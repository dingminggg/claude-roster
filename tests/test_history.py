"""会话间对话记录:cc_signals 里那条只进不出的历史通道(append_history /
read_history / history_stat,以及裁剪),以及 message_sent hook 同时落
事件通道 + 历史通道这一层接线,以及按员工把流水组装成收发双向视图。"""
from pathlib import Path

from claude_cockpit import cc_signals, history
from claude_cockpit.config import Member
from claude_cockpit.hooks import message_sent


def test_history_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "把昨天的单子跑一遍")
    got = cc_signals.read_history()
    assert len(got) == 1
    assert got[0]["from_cwd"] == r"C:\proj\fad"
    assert got[0]["to_name"] == "etl-7a"
    assert got[0]["text"] == "把昨天的单子跑一遍"
    assert got[0]["at"] > 0


def test_history_is_append_only(tmp_path, monkeypatch):
    """同一个会话连发两条,后一条不能盖掉前一条(pending 那种覆盖写法不适用)。"""
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "第一条")
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "第二条")
    assert [r["text"] for r in cc_signals.read_history()] == ["第一条", "第二条"]


def test_history_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cc_signals, "history_path", lambda: tmp_path / "nope.jsonl")
    assert cc_signals.read_history() == []


def test_history_skips_bad_lines(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "好的那条")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("这行不是 json\n\n")
    # 坏行逐行跳过,绝不抛:记录是便利功能,不能因为它打不开办公室
    assert [r["text"] for r in cc_signals.read_history()] == ["好的那条"]


def test_history_skips_bad_line_in_middle(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "前面那条")
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("这行不是 json\n")
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "后面那条")
    assert [r["text"] for r in cc_signals.read_history()] == ["前面那条", "后面那条"]


def test_history_text_truncated(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "字" * 5000)
    assert len(cc_signals.read_history()[0]["text"]) == cc_signals.HIST_TEXT_MAX


def test_history_newlines_squashed(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "第一行\n第二行")
    assert cc_signals.read_history()[0]["text"] == "第一行 第二行"


def test_history_trimmed_keeps_newest(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    monkeypatch.setattr(cc_signals, "HISTORY_MAX", 10)
    for i in range(14):
        cc_signals.append_history(r"C:\proj\fad", "etl-7a", f"第{i}条")
    got = cc_signals.read_history()
    assert len(got) <= 10
    assert got[-1]["text"] == "第13条"          # 最新的一定还在
    assert got[0]["text"] != "第0条"            # 最老的被截掉了


def test_history_needs_both_ends(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    cc_signals.append_history("", "etl-7a", "没有发送方")
    cc_signals.append_history(r"C:\proj\fad", "", "没有收件人")
    assert cc_signals.read_history() == []


def test_history_stat_changes_after_append(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(cc_signals, "history_path", lambda: p)
    assert cc_signals.history_stat() is None        # 文件还不存在
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "一")
    first = cc_signals.history_stat()
    cc_signals.append_history(r"C:\proj\fad", "etl-7a", "二")
    assert first is not None and cc_signals.history_stat() != first


def test_hook_writes_event_and_history(tmp_path, monkeypatch):
    """一次 SendMessage 要同时落:事件(驱动动画)+ 历史(过后查得到)。"""
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    monkeypatch.setattr(cc_signals, "history_path", lambda: tmp_path / "history.jsonl")
    message_sent.handle({
        "tool_name": "SendMessage",
        "cwd": r"C:\proj\fad",
        "tool_input": {"to": "etl-7a", "message": "跑一下昨天的单子"},
    })
    assert [r["to_name"] for r in cc_signals.take_messages()] == ["etl-7a"]
    hist = cc_signals.read_history()
    assert [(r["to_name"], r["text"]) for r in hist] == [("etl-7a", "跑一下昨天的单子")]


def test_hook_ignores_other_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    monkeypatch.setattr(cc_signals, "history_path", lambda: tmp_path / "history.jsonl")
    message_sent.handle({"tool_name": "Bash", "cwd": r"C:\proj\fad",
                         "tool_input": {"to": "etl-7a", "message": "x"}})
    assert cc_signals.read_history() == []


def _members():
    return [
        Member(name="fad", cwd=Path(r"C:\proj\fad"), emoji="🏪"),
        Member(name="etl", cwd=Path(r"C:\proj\etl-pipeline"), emoji="🧪"),
    ]


_ADDRS = {"fad": "fad-backend-2-f3", "etl": "etl-7a"}


def _recs():
    return [
        {"from_cwd": r"C:\proj\fad", "to_name": "etl-7a", "text": "跑一下", "at": 10.0},
        {"from_cwd": r"C:\proj\etl-pipeline", "to_name": "fad-backend-2-f3",
         "text": "跑完了", "at": 20.0},
        {"from_cwd": r"C:\proj\other", "to_name": "someone-else", "text": "无关", "at": 30.0},
    ]


def test_for_member_both_directions():
    ms = _members()
    got = history.for_member(_recs(), ms[0], _ADDRS, ms)
    assert [(e.direction, e.peer, e.text) for e in got] == [
        ("out", "etl", "跑一下"),
        ("in", "etl", "跑完了"),
    ]


def test_for_member_sorted_by_time():
    ms = _members()
    recs = list(reversed(_recs()))
    assert [e.at for e in history.for_member(recs, ms[0], _ADDRS, ms)] == [10.0, 20.0]


def test_out_peer_falls_back_to_session_name():
    """收件人的会话已经结束(addrs 里没了)→ 原样显示会话名,不猜。"""
    ms = _members()
    got = history.for_member(_recs(), ms[0], {"fad": "fad-backend-2-f3"}, ms)
    assert [(e.direction, e.peer) for e in got] == [("out", "etl-7a")]


def test_in_peer_falls_back_to_dir_name():
    """发送方不是花名册里的员工 → 退回 cwd 最后一段目录名。"""
    ms = _members()
    recs = [{"from_cwd": r"C:\proj\some-tool", "to_name": "fad-backend-2-f3",
             "text": "嗨", "at": 5.0}]
    got = history.for_member(recs, ms[0], _ADDRS, ms)
    assert [(e.direction, e.peer) for e in got] == [("in", "some-tool")]


def test_for_member_ignores_others():
    ms = _members()
    got = history.for_member(_recs(), ms[1], _ADDRS, ms)
    assert [(e.direction, e.peer) for e in got] == [("in", "fad"), ("out", "fad")]


def test_unread_count():
    ms = _members()
    entries = history.for_member(_recs(), ms[0], _ADDRS, ms)
    assert history.unread_count(entries, 0.0) == 2
    assert history.unread_count(entries, 10.0) == 1
    assert history.unread_count(entries, 99.0) == 0
