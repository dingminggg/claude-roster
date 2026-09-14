"""会话间对话记录:cc_signals 里那条只进不出的历史通道(append_history /
read_history / history_stat,以及裁剪),以及 message_sent hook 同时落
事件通道 + 历史通道这一层接线。按员工组装是后续任务,不在这个文件测。"""
from pathlib import Path

from claude_cockpit import cc_signals
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
