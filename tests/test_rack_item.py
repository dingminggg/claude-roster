"""机房:机柜图元 + 运维小人 + 它们在办公室里的装配。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claude_cockpit import layout as layout_mod
from claude_cockpit import services
from claude_cockpit.config import Member
from claude_cockpit.office.rack_item import OpsItem, RackItem
from claude_cockpit.office.view import OfficeWindow


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    members = [Member(name="fad", cwd=Path("."), dept="服务端")]
    return OfficeWindow(members, services.DEFAULTS)


def _paint(item):
    img = QImage(240, 200, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        item.paint(p, None)
    finally:
        p.end()


# ---------- 机柜 ----------
def test_rack_starts_down(app):
    assert RackItem(services.Service("mysql", 3306)).state() == services.DOWN


def test_only_stuck_racks_flash(app):
    """灭灯不闪、绿灯也不闪——闪只用来说「这台不对劲」。"""
    rack = RackItem(services.Service("mysql", 3306))
    for state, flashing in ((services.UP, False), (services.DOWN, False),
                            (services.STUCK, True)):
        rack.set_state(state)
        assert rack.is_flashing() is flashing


def test_unknown_state_reads_as_down(app):
    rack = RackItem(services.Service("mysql", 3306))
    rack.set_state("胡说八道")
    assert rack.state() == services.DOWN


def test_tooltip_carries_address_and_state(app):
    rack = RackItem(services.Service("mysql", 3306))
    rack.set_state(services.UP)
    assert "127.0.0.1:3306" in rack.toolTip() and "运行中" in rack.toolTip()


def test_rack_paints_in_every_state(app):
    rack = RackItem(services.Service("mysql", 3306))
    for state in (services.UP, services.DOWN, services.STUCK):
        rack.set_state(state)
        _paint(rack)


# ---------- 运维小人 ----------
def test_ops_paints_sitting_and_standing(app):
    ops = OpsItem()
    _paint(ops)
    ops.set_alarm(True)
    assert ops.is_alarmed()
    _paint(ops)


def test_ops_sticks_to_the_bottom_right(app):
    ops = OpsItem()
    ops.place(400, 300)
    assert ops.pos().x() == 400 - OpsItem.W - 16
    assert ops.pos().y() == 300 - OpsItem.H - 12


def test_ops_never_leaves_the_area_when_it_is_tiny(app):
    ops = OpsItem()
    ops.place(10, 10)
    assert ops.pos().x() == 0 and ops.pos().y() == 0


# ---------- 装配 ----------
def test_server_room_area_is_built(win):
    assert layout_mod.SERVER_ROOM in win.areas
    assert set(win.racks) == {"mysql", "redis", "apache"}
    assert win.ops is not None


def test_no_services_no_server_room(app, tmp_path, monkeypatch):
    """不给服务清单就不该凭空多出一块机房(测试和离屏自检都指着这条)。"""
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    w = OfficeWindow([Member(name="fad", cwd=Path("."))])
    assert layout_mod.SERVER_ROOM not in w.areas and w.racks == {}


def test_states_reach_the_racks(win):
    win.set_service_states({"mysql": services.UP, "redis": services.DOWN})
    assert win.racks["mysql"].state() == services.UP
    assert win.racks["redis"].state() == services.DOWN


def test_ops_stands_up_when_anything_is_not_green(win):
    win.set_service_states({"mysql": services.UP, "redis": services.UP,
                            "apache": services.UP})
    assert not win.ops.is_alarmed()
    win.set_service_states({"apache": services.DOWN})
    assert win.ops.is_alarmed()


def test_rack_positions_are_saved_under_the_svc_prefix(win):
    win.save_layout()
    from claude_cockpit import settings
    seats = settings.load()["office"]["seats"]
    assert layout_mod.SVC_PREFIX + "mysql" in seats
    assert "fad" in seats           # 员工的坐标没被机柜挤掉


def test_rack_menu_is_read_only(win):
    texts = [a.text() for a in win.build_rack_menu("mysql").actions()]
    assert texts == ["复制连接地址"]      # 没有启停:误点一下就把 MySQL 关了


def test_rack_menu_copies_the_address(win):
    got = []
    win.copy_text_requested.connect(got.append)
    win.build_rack_menu("mysql").actions()[0].trigger()
    assert got == ["127.0.0.1:3306"]


def test_blink_tick_drives_racks_too(win):
    """柜灯和工位屏幕共用同一拍——两种节奏同时闪就乱了。"""
    win.set_service_states({"mysql": services.STUCK})
    before = win._blink_on
    win.tick_blink()
    assert win._blink_on is not before
