import json

from claude_cockpit import settings


def test_load_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    assert settings.load() == {"sound_enabled": True, "always_on_top": True, "seen_messages": {}}


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_path", lambda: p)
    settings.save({"sound_enabled": False})
    assert settings.load() == {"sound_enabled": False, "always_on_top": True, "seen_messages": {}}


def test_load_bad_json_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(settings, "_path", lambda: p)
    assert settings.load() == {"sound_enabled": True, "always_on_top": True, "seen_messages": {}}


def test_load_fills_missing_keys_with_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(settings, "_path", lambda: p)
    # 空对象也应补齐默认键,调用方不必自己兜底
    assert settings.load() == {"sound_enabled": True, "always_on_top": True, "seen_messages": {}}


def test_seen_messages_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    settings.save({"seen_messages": {"fad": 123.5}})
    assert settings.load()["seen_messages"] == {"fad": 123.5}


def test_seen_messages_bad_type_falls_back(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"seen_messages": "坏数据"}), encoding="utf-8")
    monkeypatch.setattr(settings, "_path", lambda: p)
    # 坏数据退回缺省,别让办公室因为一段脏设置打不开
    assert settings.load()["seen_messages"] == {}


def test_default_seen_messages_not_shared(tmp_path, monkeypatch):
    """默认值那个 {} 是可变对象:两次 load() 不能拿到同一个实例,不然调用方往里
    写一笔就污染了模块级默认值。"""
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    a = settings.load()["seen_messages"]
    a["fad"] = 1.0
    assert settings.load()["seen_messages"] == {}
