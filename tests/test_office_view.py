"""办公室窗口:对外接口与 Panel 一致、按部门落座、右键菜单、存盘。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from claude_cockpit.config import Member
from claude_cockpit.office.view import OfficeWindow
from claude_cockpit.sessions import Session


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


def test_always_on_top_does_not_force_hidden_window_open(win, app):
    """在托盘里隐藏着的时候切「置顶」,不许把窗口硬弹出来
    (旧面板专门为此留了守卫,别再丢一次)。"""
    win.show()
    app.processEvents()
    win.hide()
    app.processEvents()
    win.set_always_on_top(True)
    app.processEvents()
    assert not win.isVisible()


def test_always_on_top_same_value_is_a_noop(win, app):
    """值没变就别重开窗口:重开会丢当前显隐/位置。"""
    win.show()
    app.processEvents()
    win.set_always_on_top(True)
    win.hide()
    app.processEvents()
    win.set_always_on_top(True)          # 同一个值,不该有任何动作
    app.processEvents()
    assert not win.isVisible()


def test_rebuild_drops_data_of_gone_members(win):
    """成员删了,它的会话地址/选中会话不许留着——同名重建会串味。"""
    from pathlib import Path
    from claude_cockpit.config import Member
    win.set_address("fad", "fad-backend-f3")
    win.set_sessions("fad", [Session(id="s1", title="旧会话", mtime=1.0)])
    win.rebuild([Member(name="other", cwd=Path("."), dept="后端组")])
    assert win.build_menu("fad") is not None          # 不该抛
    menu = win.build_menu("other")
    item = next(a for a in menu.actions() if "复制会话地址" in a.text())
    assert not item.isEnabled()                       # 新成员没有地址,不该继承

    win.rebuild([Member(name="fad", cwd=Path("."), dept="后端组")])
    again = next(a for a in win.build_menu("fad").actions()
                 if "复制会话地址" in a.text())
    assert not again.isEnabled()                      # 同名重建也不许拿到旧地址


def test_rebuild_keeps_camera_where_user_left_it(win, app):
    """改成员会触发 rebuild,不能把用户拖好的视角弹回左上角。

    用「同一批成员」重建 —— 这正是改个 emoji / 编辑成员的真实场景,内容大小不变,
    排除掉「内容变少、视图被夹回可滚动范围」那种合理位移。
    """
    win.resize(700, 500)
    win.show()
    app.processEvents()
    canvas = win.centralWidget()
    canvas.centerOn(1200, 900)
    app.processEvents()
    def center():
        return canvas.mapToScene(canvas.viewport().rect()).boundingRect().center()

    before = center()
    win.rebuild(_members())          # 同一批成员:内容大小不变
    app.processEvents()
    after = center()
    assert (after - before).manhattanLength() < 20


def test_dark_titlebar_survives_missing_dwm(win, app, monkeypatch):
    """标题栏刷黑失败(非 Windows / 老系统)不许把开窗搞崩。"""
    import ctypes
    monkeypatch.setattr(ctypes, "windll", None, raising=False)
    win.show()
    app.processEvents()
    assert win.isVisible()


def test_session_row_shows_title_and_untitled_fallback(win):
    """会话行显示标题;没标题退回「(无标题)」——别把 uuid 甩给用户看。
    这里必须用真的 sessions.Session(不是 dict):曾经拿 dict 当替身,
    结果 view 里按 dict 用、真机一跑就 AttributeError。"""
    win.set_sessions("fad", [Session(id="abc-123", title="", mtime=1.0)])
    assert win.seats["fad"].hit  # 只是确保对象还在
    win.set_run_state("fad", "down")
    assert "(无标题)" in win.seats["fad"]._sub

    win.set_sessions("fad", [Session(id="abc-123", title="补单测", mtime=1.0)])
    assert "补单测" in win.seats["fad"]._sub




def test_refit_scene_keeps_camera_put(win, app):
    """拖完工位 400ms 后存盘会顺带 refit,镜头不许自己跳回去。"""
    win.resize(700, 500)
    win.show()
    app.processEvents()
    canvas = win.centralWidget()
    canvas.centerOn(900, 700)
    app.processEvents()

    def center():
        return canvas.mapToScene(canvas.viewport().rect().center())

    before = center()
    win.seats["fad"].setPos(600, 400)      # 把工位拖远,内容包围盒变大
    win.save_layout()                      # 里面会 refit_scene
    app.processEvents()
    after = center()
    assert (after - before).manhattanLength() < 20


def _menu_items(menu):
    return [a.text() for a in menu.actions()]


def test_menu_of_down_seat_can_start_new_session(win):
    """没上班的工位:菜单第一档就是启动,点「新会话」传 None。"""
    win.set_run_state("fad", "down")
    got = []
    win.start_requested.connect(lambda n, sid: got.append((n, sid)))
    menu = win.build_menu("fad")
    act = next(a for a in menu.actions() if "启动(新会话)" in a.text())
    act.trigger()
    assert got == [("fad", None)]


def test_menu_of_down_seat_lists_sessions_to_resume(win):
    """有历史会话时多一个「续接会话」子菜单,点某条就带它的 id 启动。"""
    win.set_run_state("fad", "down")
    win.set_sessions("fad", [Session(id="s-new", title="新的那条", mtime=2.0),
                             Session(id="s-old", title="旧的那条", mtime=1.0)])
    got = []
    win.start_requested.connect(lambda n, sid: got.append((n, sid)))
    menu = win.build_menu("fad")     # 父菜单要留个引用:被回收会连带删掉子菜单
    sub = next(a.menu() for a in menu.actions() if a.text() == "续接会话")
    assert [a.text() for a in sub.actions()] == ["新的那条", "旧的那条"]
    sub.actions()[1].trigger()
    assert got == [("fad", "s-old")]


def test_menu_can_delete_a_session_record(win):
    win.set_run_state("fad", "down")
    win.set_sessions("fad", [Session(id="s1", title="要删的", mtime=1.0)])
    got = []
    win.delete_session_requested.connect(lambda n, sid: got.append((n, sid)))
    menu = win.build_menu("fad")     # 同上:父菜单不留引用,子菜单会被一起回收
    sub = next(a.menu() for a in menu.actions() if a.text() == "删除会话记录")
    sub.actions()[0].trigger()
    assert got == [("fad", "s1")]


def test_menu_of_running_seat_has_no_start(win):
    """已经在跑的成员不该再出现启动项——重复启动是历史 bug 的来源。"""
    win.set_run_state("fad", "busy")
    texts = _menu_items(win.build_menu("fad"))
    assert not any("启动" in t for t in texts)
    assert "复制会话地址" in texts and "打开目录" in texts
