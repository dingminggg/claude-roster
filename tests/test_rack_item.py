"""机房:运维桌上那台小机柜(本地服务的状态灯)+ 运维那个固定岗位。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claude_cockpit import layout as layout_mod
from claude_cockpit import services
from claude_cockpit.config import Member, OPS_DEPT, OPS_NAME
from claude_cockpit.office import rack_item
from claude_cockpit.office.view import OfficeWindow

ALL_UP = {s.name: services.UP for s in services.DEFAULTS}


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


@pytest.fixture
def ops(win):
    seat = win.seats[OPS_NAME]
    seat.set_run_state("idle")
    return seat


def _paint(item):
    img = QImage(260, 220, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        item.paint(p, None, None)
    finally:
        p.end()


# ---------- 机柜(一套画法,不是图元) ----------
def test_report_says_all_clear_when_green():
    assert rack_item.report(services.DEFAULTS, ALL_UP) == "3 个服务都正常"


def test_report_names_the_broken_ones():
    """点名是哪几个:光说「有服务挂了」还得再凑近看柜灯,等于白说一句。"""
    got = rack_item.report(services.DEFAULTS, {**ALL_UP, "apache": services.DOWN})
    assert "apache" in got and "mysql" not in got


def test_all_green_needs_every_service():
    assert rack_item.all_green(services.DEFAULTS, ALL_UP)
    assert not rack_item.all_green(services.DEFAULTS,
                                   {**ALL_UP, "redis": services.DOWN})


def test_empty_rack_is_not_green():
    """没有服务 ≠ 一切正常:空清单不该报平安。"""
    assert not rack_item.all_green([], {})
    assert rack_item.report([], {}) == ""


def test_only_stuck_makes_it_flash():
    """灭灯不闪、绿灯也不闪——闪只用来说「这一层不对劲」。"""
    assert not rack_item.any_stuck(services.DEFAULTS,
                                   {**ALL_UP, "redis": services.DOWN})
    assert rack_item.any_stuck(services.DEFAULTS,
                               {**ALL_UP, "redis": services.STUCK})


def test_tooltip_lists_every_layer():
    """桌面尺寸下印不下服务名了,哪一层是谁只能靠悬停提示。"""
    tip = rack_item.tooltip(services.DEFAULTS, ALL_UP)
    assert "127.0.0.1:3306" in tip and "运行中" in tip and "apache" in tip


# ---------- 它长在运维工位上 ----------
def test_only_the_ops_seat_has_a_rack(win):
    assert win.seats[OPS_NAME].has_rack()
    assert not win.seats["fad"].has_rack()


def test_rack_hit_area_does_not_overlap_the_others(win):
    """几块命中区互不重叠,不然会「点机柜弹出会话菜单」这种串台。"""
    seat = win.seats[OPS_NAME]
    r = seat.r_rack()
    for other in (seat.r_files(), seat.r_person(), seat.r_speaker()):
        assert not r.intersects(other)


def test_clicking_the_rack_is_its_own_hit(win):
    seat = win.seats[OPS_NAME]
    assert seat.hit(seat.r_rack().center()) == "rack"


def test_seat_paints_with_and_without_the_rack(win):
    for name in (OPS_NAME, "fad"):
        seat = win.seats[name]
        for state in ("down", "idle", "busy"):
            seat.set_run_state(state)
            seat.set_service_states({"mysql": services.STUCK})
            _paint(seat)


# ---------- 状态变了就说一句 ----------
def test_he_speaks_when_something_changes(win, ops):
    win.set_service_states(ALL_UP)
    assert ops.is_saying() and "都正常" in " ".join(ops._say)


def test_he_shuts_up_when_nothing_changed(win, ops):
    win.set_service_states(ALL_UP)
    ops.say("")
    win.set_service_states(ALL_UP)          # 同一份状态再来一遍
    assert not ops.is_saying()              # 每轮都冒一次就成噪音了


def test_he_names_the_broken_one(win, ops):
    win.set_service_states(ALL_UP)
    win.set_service_states({"redis": services.DOWN})
    assert "redis" in " ".join(ops._say)


def test_off_work_ops_says_nothing(win):
    """没上班就不说话:空椅子上冒气泡太灵异。"""
    seat = win.seats[OPS_NAME]
    seat.set_run_state("down")
    win.set_service_states(ALL_UP)
    assert not seat.is_saying()


def test_bubble_makes_the_seat_taller(win, ops):
    """气泡比工位框高,包围盒要跟着变——不然气泡会被裁掉半截。"""
    quiet = ops.boundingRect().height()
    ops.say("三个服务都正常")
    assert ops.boundingRect().height() > quiet


# ---------- 装配 / 菜单 ----------
def test_ops_is_a_normal_employee_with_a_normal_seat(win):
    """运维有会话,所以他就是个员工——工位、状态屏、会话历史全走 SeatItem 那套。"""
    assert OPS_NAME in win.seats
    assert win.seats[OPS_NAME].parentItem() is win.areas[layout_mod.SERVER_ROOM]


def test_ops_department_is_locked(app, tmp_path):
    """名字和部门锁死:yaml 里写别的部门也会被扳回机房。"""
    from claude_cockpit.config import load_config
    p = tmp_path / "agents.yaml"
    p.write_text("agents:\n  - {name: ops, cwd: '.', dept: 后勤}\n", encoding="utf-8")
    assert load_config(p)[0].dept == OPS_DEPT


def test_ops_cannot_be_edited_or_deleted_from_the_panel(win):
    """固定岗位:置灰而不是隐藏(隐藏了用户会以为功能没了)。"""
    acts = {a.text(): a for a in win.build_menu(OPS_NAME).actions()}
    assert acts["编辑"].isEnabled() is False and acts["删除"].isEnabled() is False
    normal = {a.text(): a for a in win.build_menu("fad").actions()}
    assert normal["编辑"].isEnabled() and normal["删除"].isEnabled()


def test_rack_menu_is_read_only_with_one_entry_per_layer(win):
    menu = win.build_rack_menu()
    assert [a.text() for a in menu.actions()] == ["复制连接地址"]
    assert len(menu.actions()[0].menu().actions()) == 3     # 一层一条;没有启停


def test_rack_menu_copies_that_layer_address(win):
    got = []
    win.copy_text_requested.connect(got.append)
    win.build_rack_menu().actions()[0].menu().actions()[1].trigger()
    assert got == ["127.0.0.1:6379"]


def test_the_rack_no_longer_takes_a_grid_slot(win):
    """机柜是桌上的一样家具了,不占格子也不存坐标(跟着运维那张工位走)。"""
    win.save_layout()
    from claude_cockpit import settings
    seats = settings.load()["office"]["seats"]
    assert not any(k.startswith(layout_mod.SVC_PREFIX) for k in seats)
    assert OPS_NAME in seats and "fad" in seats
