from claude_cockpit import cc_signals


def test_pending_dir_in_cockpit_namespace():
    # 彻底解耦:pending 目录归 claude-cockpit,不再在 desk-buddy 命名空间下
    p = str(cc_signals.pending_dir())
    assert "claude-cockpit" in p
    assert "desk-buddy" not in p
    # pending 与 turn-ended 同在一个 data_dir 下
    assert str(cc_signals.turn_dir()).startswith(str(cc_signals.data_dir()))


def test_pending_roundtrip(tmp_path, monkeypatch):
    d = tmp_path / "pending"
    monkeypatch.setattr(cc_signals, "pending_dir", lambda: d)
    cc_signals.write_pending("s1", "needs permission",
                             r"C:\Users\LQ\PhpstormProjects\fad-backend")
    assert cc_signals.read_pending() == {"s1": "fad-backend"}
    full = cc_signals.read_pending_full()
    assert full[0]["session_id"] == "s1" and full[0]["message"] == "needs permission"
    cc_signals.clear_pending("s1")
    assert cc_signals.read_pending() == {}


def test_read_pending_display_name_fallback(tmp_path, monkeypatch):
    d = tmp_path / "pending"
    monkeypatch.setattr(cc_signals, "pending_dir", lambda: d)
    cc_signals.write_pending("s2", "msg", "")        # 无 cwd → 回退
    assert cc_signals.read_pending() == {"s2": "Claude Code"}
