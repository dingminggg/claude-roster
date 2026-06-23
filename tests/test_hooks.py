"""三个 hook 的 handle() 纯逻辑测试(不起 Claude,直接喂 payload)。

用 monkeypatch 把 cc_signals 的写/清函数换成记录器,断言「谁被调用、参数对不对」。
"""
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
