import json

from claude_cockpit import settings


def test_load_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    assert settings.load() == {"sound_enabled": True}


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_path", lambda: p)
    settings.save({"sound_enabled": False})
    assert settings.load() == {"sound_enabled": False}


def test_load_bad_json_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(settings, "_path", lambda: p)
    assert settings.load() == {"sound_enabled": True}


def test_load_fills_missing_keys_with_defaults(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(settings, "_path", lambda: p)
    # 空对象也应补齐默认键,调用方不必自己兜底
    assert settings.load() == {"sound_enabled": True}
