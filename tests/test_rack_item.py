"""机房:一台机柜(一层一个服务)+ 运维那个固定岗位(内置员工)+ 巡检。"""
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
from claude_cockpit.config import OPS_DEPT, OPS_NAME
from claude_cockpit.office.rack_item import RackItem
from claude_cockpit.office.view import OfficeWindow


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    members = [Member(name="fad", cwd=Path("."), dept="服务端"),
               Member(name=OPS_NAME, cwd=Path("."), dept=OPS_DEPT)]
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


# ---------- 运维 ----------
def test_ops_is_a_normal_employee_with_a_normal_seat(win):
    """运维有会话,所以他就是个员工——工位、状态屏、会话历史全走 SeatItem 那套,
    别再为他自绘一套(自绘那版少一半功能)。"""
    assert OPS_NAME in win.seats
    assert win.seats[OPS_NAME].parentItem() is win.areas[layout_mod.SERVER_ROOM]


def test_ops_department_is_locked(app, tmp_path, monkeypatch):
    """名字和部门锁死:yaml 里写别的部门也会被扳回机房。"""
    from claude_cockpit.config import load_config
    p = tmp_path / "agents.yaml"
    p.write_text("agents:\n  - {name: ops, cwd: '.', dept: 后勤}\n", encoding="utf-8")
    assert load_config(p)[0].dept == OPS_DEPT


def test_patrol_sends_him_to_the_rack(win):
    win.seats[OPS_NAME].set_run_state("idle")
    assert win.patrol() is True
    assert win._walkers and win._away.get(OPS_NAME)   # 工位画成空椅子


def test_no_patrol_when_ops_is_off_work(win):
    """没上班就不演:空椅子上站起来一个人太灵异。"""
    win.seats[OPS_NAME].set_run_state("down")
    assert win.patrol() is False


def test_report_names_the_broken_ones(win):
    win.set_service_states({s.name: services.UP for s in services.DEFAULTS})
    assert "都正常" in win.service_report()
    win.set_service_states({"apache": services.DOWN})
    report = win.service_report()
    assert "apache" in report and "mysql" not in report


def test_going_red_sends_him_over_at_once(win):
    """刚出事就派他过去,不等下一轮巡检。"""
    win.seats[OPS_NAME].set_run_state("idle")
    win.set_service_states({s.name: services.UP for s in services.DEFAULTS})
    assert not win._walkers
    win.set_service_states({"redis": services.DOWN})
    assert win._walkers                     # 走起来了
    n = len(win._walkers)
    win.set_service_states({"apache": services.DOWN})
    assert len(win._walkers) == n           # 还没修好的期间不反复派人


# ---------- 装配 ----------
def test_server_room_has_a_rack(win):
    assert layout_mod.SERVER_ROOM in win.areas
    assert win.rack is not None


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


def test_room_positions_are_saved_under_the_svc_prefix(win):
    win.save_layout()
    from claude_cockpit import settings
    seats = settings.load()["office"]["seats"]
    assert layout_mod.SVC_PREFIX + "rack" in seats
    assert "fad" in seats and OPS_NAME in seats     # 运维按员工存,不带前缀


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


def test_ops_cannot_be_edited_or_deleted_from_the_panel(win):
    """固定岗位:置灰而不是隐藏(隐藏了用户会以为功能没了)。"""
    acts = {a.text(): a for a in win.build_menu(OPS_NAME).actions()}
    assert acts["编辑"].isEnabled() is False and acts["删除"].isEnabled() is False
    normal = {a.text(): a for a in win.build_menu("fad").actions()}
    assert normal["编辑"].isEnabled() and normal["删除"].isEnabled()
