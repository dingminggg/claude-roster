"""运维:他桌上那台小机柜(本地服务的状态灯)+ 运维那个固定岗位。"""
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
    from claude_cockpit import cc_signals, settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    # 对话记录也要隔离:OfficeWindow 一建就 refresh_history,不打桩的话
    # 用例会去读开发机上真实的 history.jsonl(那里面真有 cwd 归一后
    # 和测试员工撞上的记录),结果随机器而变。只读不写,指到 tmp 即可。
    monkeypatch.setattr(cc_signals, "history_path",
                        lambda: tmp_path / "history.jsonl")
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


def test_rack_and_papers_never_coexist(win):
    """机柜和文件堆**都想占「显示器右边」**,所以它们互斥:有机柜的那张工位
    (运维)没有文件堆,有文件堆的工位没有机柜。命中区因此不会串台。"""
    ops, other = win.seats[OPS_NAME], win.seats["fad"]
    ops.set_session_count(3)
    assert ops.has_rack() and not ops.has_papers()
    other.set_session_count(3)
    assert other.has_papers() and not other.has_rack()
    # 剩下那几块和机柜是真的不重叠
    for r in (ops.r_person(), ops.r_speaker()):
        assert not ops.r_rack().intersects(r)


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
    """名字和部门锁死:yaml 里写别的部门也会被扳回运维那块部门区。"""
    from claude_cockpit.config import load_config
    p = tmp_path / "agents.yaml"
    p.write_text(f"agents:\n  - {{name: {OPS_NAME}, cwd: '.', dept: 后勤}}\n",
                 encoding="utf-8")
    assert load_config(p)[0].dept == OPS_DEPT


def test_only_the_fixed_post_is_locked(app, tmp_path):
    """别人的部门谁也不许扳——`ops` 现在是运营那位,曾经是这个固定岗位的名字,
    两处对不上就会把他硬拽进运维、还不给编辑(踩过)。"""
    from claude_cockpit.config import load_config
    p = tmp_path / "agents.yaml"
    p.write_text("agents:\n  - {name: ops, cwd: '.', dept: 运营}\n", encoding="utf-8")
    assert load_config(p)[0].dept == "运营"


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


def test_paper_fits_six_digits(app):
    """纸的尺寸是被「放得下 6 位数字」倒推出来的,别改小了写不下。

    卡的是**几何预算**不是 QFontMetrics:离屏平台的回退字体比真机宽一大截
    (同一串数字 48px vs 30px),按它算会把纸撑到桌子那么大。
    """
    from claude_cockpit.office import seat_item as si
    assert si.PAPER_LEN - 6 >= 30


def test_issue_tag_from_titles():
    from claude_cockpit.sessions import issue_tag
    assert issue_tag("#1085 修复下单") == "1085"
    assert issue_tag("feature/1085-fix") == "1085"
    assert issue_tag("issue 1085 收尾") == "1085"
    # 标题里到处是数字,认错了还不如留白
    assert issue_tag("2026-09-14 改好了") == ""
    assert issue_tag("v1.2.3 发版") == ""
    assert issue_tag("跑一下 ETL") == ""
    assert issue_tag("") == ""


def test_tag_reaches_the_top_sheet(win):
    from claude_cockpit.sessions import Session
    win.set_sessions("fad", [Session(id="a", title="#1085 修复下单", mtime=1)])
    assert win.seats["fad"]._tag == "1085"
