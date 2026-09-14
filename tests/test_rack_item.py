"""机房:一台机柜(一层一个服务)+ 运维工位 + 会巡检的运维本人。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claude_cockpit import layout as layout_mod
from claude_cockpit import services
from claude_cockpit.config import Member
from claude_cockpit.office import rack_item
from claude_cockpit.office.rack_item import OpsDeskItem, OpsItem, RackItem
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
def test_one_rack_holds_every_service(app):
    rack = RackItem(services.DEFAULTS)
    assert [s.name for s in rack.services] == ["mysql", "redis", "apache"]
    assert all(rack.state_of(s.name) == services.DOWN for s in services.DEFAULTS)


def test_states_land_on_their_own_layer(app):
    rack = RackItem(services.DEFAULTS)
    rack.set_states({"mysql": services.UP, "redis": services.STUCK})
    assert rack.state_of("mysql") == services.UP
    assert rack.state_of("redis") == services.STUCK
    assert rack.state_of("apache") == services.DOWN     # 没喂到的层不受影响


def test_unknown_service_and_state_are_ignored(app):
    rack = RackItem(services.DEFAULTS)
    rack.set_states({"这个服务不存在": services.UP, "mysql": "胡说八道"})
    assert rack.state_of("mysql") == services.DOWN


def test_only_stuck_layers_make_the_rack_flash(app):
    """灭灯不闪、绿灯也不闪——闪只用来说「这一层不对劲」。"""
    rack = RackItem(services.DEFAULTS)
    rack.set_states({"mysql": services.UP, "redis": services.DOWN})
    assert not rack.is_flashing()
    rack.set_states({"apache": services.STUCK})
    assert rack.is_flashing()


def test_all_green_needs_every_layer(app):
    rack = RackItem(services.DEFAULTS)
    rack.set_states({s.name: services.UP for s in services.DEFAULTS})
    assert rack.all_green()
    rack.set_states({"redis": services.DOWN})
    assert not rack.all_green()


def test_empty_rack_is_not_green(app):
    """没有服务 ≠ 一切正常:不然空清单会让运维一直坐着,看着像在说「都好」。"""
    assert not RackItem([]).all_green()


def test_tooltip_lists_every_layer(app):
    rack = RackItem(services.DEFAULTS)
    rack.set_states({"mysql": services.UP})
    tip = rack.toolTip()
    assert "127.0.0.1:3306" in tip and "运行中" in tip and "apache" in tip


def test_rack_paints_in_every_state(app):
    rack = RackItem(services.DEFAULTS)
    for state in (services.UP, services.DOWN, services.STUCK):
        rack.set_states({s.name: state for s in services.DEFAULTS})
        _paint(rack)


# ---------- 运维工位 ----------
def test_ops_desk_paints_and_offers_a_seat(app):
    desk = OpsDeskItem()
    _paint(desk)
    assert desk.seat_point().x() > 0 and desk.seat_point().y() > 0


# ---------- 运维本人 ----------
def test_ops_starts_at_the_desk(app):
    ops = OpsItem()
    ops.set_points(QPointF(20, 100), QPointF(300, 100), 140)
    assert ops.phase() == rack_item.DESK
    _paint(ops)


def test_alarm_sends_him_to_the_rack(app):
    ops = OpsItem()
    ops.set_points(QPointF(20, 100), QPointF(300, 100), 140)
    ops.set_alarm(True)
    assert ops.phase() == rack_item.TO_RACK
    _paint(ops)                       # 走路时画站姿


def test_he_walks_the_whole_way_then_stands_there(app):
    ops = OpsItem()
    ops.set_points(QPointF(20, 100), QPointF(300, 100), 140)
    ops.set_alarm(True)
    for _ in range(int(rack_item.WALK_MS / rack_item.STEP_MS) + 2):
        ops._tick()
    assert ops.phase() == rack_item.AT_RACK
    assert abs(ops.pos().x() + ops.W / 2 - 300) < 1      # 站到柜子跟前了


def test_he_does_not_go_home_while_it_is_still_broken(app):
    ops = OpsItem()
    ops.set_points(QPointF(20, 100), QPointF(300, 100), 140)
    ops.set_alarm(True)
    for _ in range(int(rack_item.WALK_MS / rack_item.STEP_MS) + 2):
        ops._tick()
    ops._go()                         # 看够了:还没修好 → 继续站着
    assert ops.phase() == rack_item.AT_RACK
    ops.set_alarm(False)              # 修好了
    ops._go()
    assert ops.phase() == rack_item.TO_DESK


def test_the_path_bends_through_the_lane(app):
    """走折线不走直线:直连会从桌面上横穿过去。中途必须绕到过道那条线上。"""
    ops = OpsItem()
    ops.set_points(QPointF(20, 100), QPointF(300, 100), 160)
    ops.set_alarm(True)
    assert ops._at(0.5).y() == 160
    assert ops._at(0.0) == QPointF(20, 100) and ops._at(1.0) == QPointF(300, 100)


# ---------- 装配 ----------
def test_server_room_has_a_rack_and_an_ops_desk(win):
    assert layout_mod.SERVER_ROOM in win.areas
    assert win.rack is not None and win.ops_desk is not None and win.ops is not None


def test_no_services_no_server_room(app, tmp_path, monkeypatch):
    """不给服务清单就不该凭空多出一块机房(测试和离屏自检都指着这条)。"""
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    w = OfficeWindow([Member(name="fad", cwd=Path("."))])
    assert layout_mod.SERVER_ROOM not in w.areas and w.rack is None


def test_states_reach_the_rack(win):
    win.set_service_states({"mysql": services.UP, "redis": services.DOWN})
    assert win.rack.state_of("mysql") == services.UP
    assert win.rack.state_of("redis") == services.DOWN


def test_he_leaves_his_desk_only_when_something_is_wrong(win):
    win.set_service_states({s.name: services.UP for s in services.DEFAULTS})
    assert not win.ops.is_alarmed()
    win.set_service_states({"apache": services.DOWN})
    assert win.ops.is_alarmed()


def test_room_positions_are_saved_under_the_svc_prefix(win):
    win.save_layout()
    from claude_cockpit import settings
    seats = settings.load()["office"]["seats"]
    assert layout_mod.SVC_PREFIX + "rack" in seats
    assert layout_mod.SVC_PREFIX + "opsdesk" in seats
    assert "fad" in seats           # 员工的坐标没被机房挤掉


def test_rack_menu_is_read_only_with_one_entry_per_layer(win):
    menu = win.build_rack_menu()
    assert [a.text() for a in menu.actions()] == ["复制连接地址"]
    sub = menu.actions()[0].menu()
    assert len(sub.actions()) == 3      # 一层一条;没有启停


def test_rack_menu_copies_that_layer_address(win):
    got = []
    win.copy_text_requested.connect(got.append)
    win.build_rack_menu().actions()[0].menu().actions()[1].trigger()
    assert got == ["127.0.0.1:6379"]


def test_blink_tick_drives_the_rack_too(win):
    """柜灯和工位屏幕共用同一拍——两种节奏同时闪就乱了。"""
    win.set_service_states({"mysql": services.STUCK})
    before = win._blink_on
    win.tick_blink()
    assert win._blink_on is not before
