"""三个 hook 的 handle() 纯逻辑测试(不起 Claude,直接喂 payload)。

用 monkeypatch 把 cc_signals 的写/清函数换成记录器,断言「谁被调用、参数对不对」。
"""
import io
import json
import sys

from claude_cockpit import cc_signals
from claude_cockpit.hooks import clear as clear_hook
from claude_cockpit.hooks import notify as notify_hook
from claude_cockpit.hooks import turn_ended as turn_ended_hook


def _recorder(monkeypatch, fn_name):
    calls = []
    monkeypatch.setattr(cc_signals, fn_name, lambda *a, **k: calls.append((a, k)))
    return calls


def test_notify_writes_pending_only_on_permission(monkeypatch):
    writes = _recorder(monkeypatch, "write_pending")
    notify_hook.handle({"session_id": "s1", "message": "needs your permission",
                        "cwd": "C:/x"})
    assert len(writes) == 1
    notify_hook.handle({"session_id": "s1", "message": "just finished", "cwd": "C:/x"})
    assert len(writes) == 1            # 非 permission 不写
    notify_hook.handle({"message": "permission", "cwd": "C:/x"})
    assert len(writes) == 1            # 无 session_id 不写


def test_turn_ended_writes_turn_and_clears_pending(monkeypatch):
    turns = _recorder(monkeypatch, "write_turn_ended")
    cleared = _recorder(monkeypatch, "clear_pending")
    turn_ended_hook.handle({"session_id": "s1", "cwd": "C:/x"})
    assert len(turns) == 1
    assert cleared == [(("s1",), {})]   # 答完一轮顺手清掉权限 pending


def test_clear_clears_turn_and_pending(monkeypatch):
    cleared_turn = _recorder(monkeypatch, "clear_turn_ended")
    cleared_pending = _recorder(monkeypatch, "clear_pending")
    clear_hook.handle({"session_id": "s1"})
    assert cleared_turn == [(("s1",), {})]
    assert cleared_pending == [(("s1",), {})]


def test_hooks_ignore_missing_session_id(monkeypatch):
    turns = _recorder(monkeypatch, "write_turn_ended")
    cleared = _recorder(monkeypatch, "clear_turn_ended")
    turn_ended_hook.handle({"cwd": "C:/x"})
    clear_hook.handle({})
    assert turns == [] and cleared == []


# ---------- stdin 一律按 UTF-8 读(踩过的大坑) ----------
class _FakeStdin:
    """假的 stdin:只有 .buffer 给原始字节,和 Claude Code 喂给 hook 的一样。"""

    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)


def test_payload_is_decoded_as_utf8(monkeypatch):
    """**Claude Code 发的是 UTF-8,而 Windows 的 sys.stdin 按本地编码(GBK)解**——
    正文里有中文就会被拆成孤立代理字符,再往 UTF-8 文件里写直接抛,而写信号那几处
    异常全吞 → 整条信号静默消失。所以必须走 sys.stdin.buffer 自己解。"""
    from claude_cockpit.hooks._payload import read_payload
    raw = json.dumps({"tool_name": "SendMessage",
                      "tool_input": {"to": "etl-7a", "message": "帮我跑一下 ETL"}},
                     ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(raw))
    got = read_payload()
    assert got["tool_input"]["message"] == "帮我跑一下 ETL"


def test_payload_survives_broken_bytes(monkeypatch):
    """坏字节换成 �,别整条抛掉:宁可丢一个字,也不能让整条信号消失。"""
    from claude_cockpit.hooks._payload import read_payload
    raw = b'{"tool_name": "SendMessage", "tool_input": {"to": "a", "message": "\xff\xfe ok"}}'
    monkeypatch.setattr(sys, "stdin", _FakeStdin(raw))
    assert read_payload()["tool_input"]["to"] == "a"


def test_empty_or_non_object_payload_is_none(monkeypatch):
    from claude_cockpit.hooks._payload import read_payload
    for raw in (b"", b"   ", b"[1, 2]", b'"just a string"'):
        monkeypatch.setattr(sys, "stdin", _FakeStdin(raw))
        assert read_payload() is None


def test_a_chinese_message_reaches_the_signal_dir(tmp_path, monkeypatch):
    """整条链的回归:中文正文 → hook 的 main() → 信号文件真的落盘。"""
    from claude_cockpit import cc_signals
    from claude_cockpit.hooks import message_sent
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    raw = json.dumps({"tool_name": "SendMessage", "cwd": r"C:\proj\fad",
                      "tool_input": {"to": "etl-7a", "message": "帮我跑一下 ETL"}},
                     ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", _FakeStdin(raw))
    assert message_sent.main() == 0
    got = cc_signals.take_messages()
    assert got and got[0]["text"] == "帮我跑一下 ETL"


def test_write_message_survives_a_lone_surrogate(tmp_path, monkeypatch):
    """第二道闸:就算有人塞进来一段没洗过的文本,也只丢那个字、不丢整条信号。"""
    from claude_cockpit import cc_signals
    monkeypatch.setattr(cc_signals, "messages_dir", lambda: tmp_path / "messages")
    cc_signals.write_message(r"C:\proj\fad", "etl-7a", "坏字符在这儿 \udc84 后面还有话")
    got = cc_signals.take_messages()
    assert got and "后面还有话" in got[0]["text"]
