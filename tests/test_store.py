from claude_cockpit import store


def test_roundtrip(tmp_path, monkeypatch):
    f = tmp_path / "handles.json"
    monkeypatch.setattr(store, "_path", lambda: f)
    assert store.load() == {}            # 还没存 → 空
    store.save({"fad": 123, "driver": 456})
    assert store.load() == {"fad": 123, "driver": 456}


def test_load_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_path", lambda: tmp_path / "nope.json")
    assert store.load() == {}


def test_load_corrupt(tmp_path, monkeypatch):
    f = tmp_path / "handles.json"
    f.write_text("not json{", encoding="utf-8")
    monkeypatch.setattr(store, "_path", lambda: f)
    assert store.load() == {}
