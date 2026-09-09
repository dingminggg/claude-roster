"""办公室窗口:对外接口与 Panel 一致、按部门落座、右键菜单、存盘。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from claude_cockpit.config import Member
from claude_cockpit.office.view import OfficeWindow


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _members():
    return [
        Member(name="fad", cwd=Path("."), emoji="🏪", color="#e74c3c", dept="后端组"),
        Member(name="fad-2", cwd=Path("."), emoji="📊", dept="后端组"),
        Member(name="etl", cwd=Path("."), emoji="🧪"),          # 没写部门
    ]


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    from claude_cockpit import settings
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    return OfficeWindow(_members())


def test_has_panel_api(win):
    """main.py 只认这一套接口,少一个就得改 main。"""
    for fn in ("set_run_state", "set_sessions", "set_address", "set_message",
               "set_title", "set_order", "set_speaking", "rebuild",
               "set_always_on_top"):
        assert callable(getattr(win, fn))
    for sig in ("member_clicked", "start_requested", "add_requested",
                "edit_requested", "delete_requested", "open_dir_requested",
                "copy_address_requested", "delete_session_requested",
                "stop_speaking_requested"):
        assert hasattr(win, sig)


def test_seat_per_member_parented_to_its_dept_area(win):
    assert set(win.seats) == {"fad", "fad-2", "etl"}
    assert win.seats["fad"].parentItem() is win.areas["后端组"]
    from claude_cockpit.layout import UNASSIGNED
    assert win.seats["etl"].parentItem() is win.areas[UNASSIGNED]


def test_set_run_state_forwards_to_seat(win):
    win.set_run_state("fad", "busy")
    assert win.seats["fad"].status_text() == "忙碌中"


def test_set_order_is_a_noop(win):
    """画布上位置由用户摆,排序没有意义;保留签名只为 main.py 不用改。"""
    before = win.seats["fad"].pos()
    win.set_order(["etl", "fad-2", "fad"])
    assert win.seats["fad"].pos() == before


def test_seat_click_is_forwarded_as_member_clicked(win):
    """工位的 clicked 直通到 member_clicked(「未运行不发」由 SeatItem 负责,
    在 test_seat_item.py 里按命中区验证)。"""
    got = []
    win.member_clicked.connect(got.append)
    win.set_run_state("fad", "busy")
    win.seats["fad"].clicked.emit("fad")
    assert got == ["fad"]


def test_confirm_emits_start_requested_with_selected_session(win):
    got = []
    win.start_requested.connect(lambda n, sid: got.append((n, sid)))
    win.set_sessions("fad", [{"id": "s1", "title": "上次那条", "mtime": 1}])
    win.seats["fad"].confirmed.emit("fad")
    assert got == [("fad", "s1")]


def test_confirm_without_session_passes_none(win):
    got = []
    win.start_requested.connect(lambda n, sid: got.append((n, sid)))
    win.set_sessions("fad", [])
    win.seats["fad"].confirmed.emit("fad")
    assert got == [("fad", None)]


def test_menu_copy_address_disabled_not_hidden(win):
    """探不到会话地址时该项置灰而不是隐藏——隐藏用户会以为功能没了。"""
    menu = win.build_menu("fad")
    item = next(a for a in menu.actions() if "复制会话地址" in a.text())
    assert not item.isEnabled() and item.isVisible()
    assert item.toolTip()

    win.set_address("fad", "fad-backend-f3")
    item2 = next(a for a in win.build_menu("fad").actions()
                 if "复制会话地址" in a.text())
    assert item2.isEnabled()


def test_layout_saved_and_restored(win, tmp_path, monkeypatch, app):
    from claude_cockpit import settings
    win.seats["fad"].setPos(333, 222)
    win.save_layout()
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    again = OfficeWindow(_members())
    assert (again.seats["fad"].pos().x(), again.seats["fad"].pos().y()) == (333, 222)


def test_rebuild_replaces_seats(win):
    win.rebuild([Member(name="solo", cwd=Path("."), dept="独立组")])
    assert set(win.seats) == {"solo"}
    assert set(win.areas) == {"独立组"}


def test_scene_rect_grows_with_content(win):
    before = win.scene.sceneRect()
    win.areas["后端组"].setPos(3000, 2000)
    win.refit_scene()
    assert win.scene.sceneRect().width() > before.width()


def test_focus_content_puts_office_at_viewport_topleft(win, app):
    """开窗别停在 sceneRect 中央那片空地上:办公室要在左上角。"""
    win.resize(700, 500)
    win.show()
    app.processEvents()
    win.refit_scene()
    win.focus_content()
    app.processEvents()
    canvas = win.centralWidget()
    seen = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
    content = win.scene.itemsBoundingRect()
    assert seen.left() <= content.left()
    assert seen.top() <= content.top()
    assert seen.left() > content.left() - 200      # 不是停在几百像素外的空地
    assert seen.top() > content.top() - 200
