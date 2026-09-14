"""本地服务清单和探活。坏配置一律退回内置缺省、绝不抛。"""
import socket
import threading

import pytest

from claude_cockpit import services


def test_defaults_when_file_missing(tmp_path):
    got = services.load(tmp_path / "没有这个文件.yaml")
    assert [s.name for s in got] == ["mysql", "redis", "apache"]


def test_reads_custom_list(tmp_path):
    p = tmp_path / "services.yaml"
    p.write_text("services:\n  - {name: pg, port: 5432}\n  - {name: mongo, port: 27017}\n",
                 encoding="utf-8")
    got = services.load(p)
    assert [(s.name, s.port) for s in got] == [("pg", 5432), ("mongo", 27017)]


@pytest.mark.parametrize("body", [
    "services: 这不是列表",
    "services:\n  - {name: pg}\n",                    # 缺端口
    "services:\n  - {name: pg, port: 说不清}\n",
    "services:\n  - {name: pg, port: 99999}\n",       # 端口越界
    "services: []\n",
    "别的键: 1\n",
    "[ 这不是 yaml 映射",
])
def test_bad_config_falls_back_to_defaults(tmp_path, body):
    """坏数据不能让办公室打不开(同 layout.py / peers.py 的口径)。"""
    p = tmp_path / "services.yaml"
    p.write_text(body, encoding="utf-8")
    assert [s.name for s in services.load(p)] == ["mysql", "redis", "apache"]


def test_bad_entry_drops_only_that_entry(tmp_path):
    p = tmp_path / "services.yaml"
    p.write_text("services:\n  - {name: pg, port: 5432}\n  - 这条是坏的\n",
                 encoding="utf-8")
    assert [s.name for s in services.load(p)] == ["pg"]


def test_duplicate_names_keep_the_first(tmp_path):
    p = tmp_path / "services.yaml"
    p.write_text("services:\n  - {name: pg, port: 5432}\n  - {name: pg, port: 5433}\n",
                 encoding="utf-8")
    got = services.load(p)
    assert [(s.name, s.port) for s in got] == [("pg", 5432)]


def test_probe_up_on_a_real_listening_port():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept(), daemon=True).start()
    try:
        assert services.probe(services.Service("t", port)) == services.UP
    finally:
        srv.close()


def test_probe_down_when_nobody_listens():
    srv = socket.socket()           # 先占一个端口拿到号,再关掉 → 保证没人听
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    assert services.probe(services.Service("t", port)) == services.DOWN


def test_probe_stuck_on_timeout(monkeypatch):
    """超时和「连接被拒」不是一回事:端口在但不搭理你,画面上给琥珀而不是灭灯。"""
    def boom(*a, **k):
        raise socket.timeout()
    monkeypatch.setattr(services.socket, "create_connection", boom)
    assert services.probe(services.Service("t", 1)) == services.STUCK


def test_probe_all_returns_one_state_per_service(monkeypatch):
    monkeypatch.setattr(services, "probe", lambda s, t=0.1: services.UP)
    got = services.probe_all(services.DEFAULTS)
    assert got == {"mysql": "up", "redis": "up", "apache": "up"}


def test_address_is_what_the_menu_copies():
    assert services.Service("mysql", 3306).address == "127.0.0.1:3306"
