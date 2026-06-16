import textwrap

import pytest

from claude_cockpit.config import Member, load_config


def _write(tmp_path, text):
    p = tmp_path / "agents.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_load_basic(tmp_path):
    cwd = tmp_path  # 用存在的目录
    p = _write(tmp_path, f"""
        agents:
          - name: shop
            cwd: {cwd}
            emoji: "🏪"
            color: "#2980b9"
            permission_mode: default
    """)
    members = load_config(p)
    assert len(members) == 1
    m = members[0]
    assert isinstance(m, Member)
    assert m.name == "shop"
    assert str(m.cwd) == str(cwd)
    assert m.emoji == "🏪"
    assert m.permission_mode == "default"


def test_bad_name_rejected(tmp_path):
    p = _write(tmp_path, f"""
        agents:
          - name: "bad name!"
            cwd: {tmp_path}
    """)
    with pytest.raises(ValueError):
        load_config(p)


def test_missing_cwd_rejected(tmp_path):
    p = _write(tmp_path, """
        agents:
          - name: ghost
            cwd: C:\\no\\such\\dir\\xyz123
    """)
    with pytest.raises(ValueError):
        load_config(p)


def test_duplicate_names_rejected(tmp_path):
    p = _write(tmp_path, f"""
        agents:
          - name: dup
            cwd: {tmp_path}
          - name: dup
            cwd: {tmp_path}
    """)
    with pytest.raises(ValueError):
        load_config(p)
