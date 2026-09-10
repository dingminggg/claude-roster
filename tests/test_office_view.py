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
    """拖完工位 400ms 后存盘会顺带 refit。只要内容还装得下,镜头就不许自己跳
    (装不下才缩回去,那是另一个测试的事)。"""
    win.resize(700, 500)
    win.show()
    app.processEvents()
    canvas = win.centralWidget()
    canvas.centerOn(900, 700)
    app.processEvents()

    def center():
        return canvas.mapToScene(canvas.viewport().rect().center())

    before = center()
    win.seats["fad"].setPos(60, 60)        # 挪一点点:内容仍然装得下
    win.save_layout()                      # 里面会 refit_scene
    app.processEvents()
    after = center()
    assert (after - before).manhattanLength() < 20


def _menu_items(menu):
    return [a.text() for a in menu.actions()]








def test_drag_seat_into_another_area_changes_dept(win):
    """把工位拖到别的地毯上 → 换部门,并报出去让 main 写回 agents.yaml。"""
    from claude_cockpit.layout import UNASSIGNED
    got = []
    win.dept_changed.connect(lambda n, d: got.append((n, d)))
    seat, target = win.seats["fad"], win.areas[UNASSIGNED]
    seat.setParentItem(seat.parentItem())          # 先确认它本来在后端组
    assert win.seats["fad"].parentItem() is win.areas["后端组"]

    seat.setPos(seat.pos())                        # 挪到「未分配」那块地毯中央
    seat.setParentItem(win.scene.items() and seat.parentItem())
    center = target.sceneBoundingRect().center()
    seat.setParentItem(target.parentItem() or None)
    win.scene.addItem(seat) if seat.scene() is None else None
    seat.setPos(center.x() - 100, center.y() - 80)
    win._on_seat_dropped("fad")

    assert got == [("fad", UNASSIGNED)]
    assert win.seats["fad"].parentItem() is target


def test_new_area_can_be_created_and_removed(win):
    win.add_area("新组", at=(2000, 2000))
    assert "新组" in win.areas
    win.remove_area("新组")
    assert "新组" not in win.areas


def test_area_with_people_cannot_be_removed(win):
    """地毯上还有人就不许删——免得默默把谁的部门清了。"""
    win.remove_area("后端组")
    assert "后端组" in win.areas
    menu = win.build_canvas_menu("后端组")
    rm = next(a for a in menu.actions() if a.text().startswith("删除"))
    assert not rm.isEnabled() and rm.toolTip()


def test_rename_area_moves_its_people(win):
    got = []
    win.dept_changed.connect(lambda n, d: got.append((n, d)))
    win.rename_area("后端组", "服务端组")
    assert "服务端组" in win.areas and "后端组" not in win.areas
    assert set(got) == {("fad", "服务端组"), ("fad-2", "服务端组")}


def test_canvas_menu_on_blank_offers_new_area(win):
    texts = [a.text() for a in win.build_canvas_menu(None).actions()]
    assert "新增成员" in texts and "新建部门区域" in texts
    assert not any(t.startswith("删除") for t in texts)






def test_person_menu_clocks_in_and_out(win):
    """右键人:没上班给「上班」,上班了给「下班」——点谁就是对谁下命令。"""
    started, stopped = [], []
    win.start_requested.connect(lambda n, sid: started.append((n, sid)))
    win.stop_requested.connect(stopped.append)

    win.set_run_state("fad", "down")
    menu = win.build_menu("fad", "person")
    texts = [a.text() for a in menu.actions()]
    assert any(t.startswith("上班") for t in texts)
    assert not any(t.startswith("下班") for t in texts)
    next(a for a in menu.actions() if "新会话" in a.text()).trigger()
    assert started == [("fad", None)]

    win.set_run_state("fad", "busy")
    menu2 = win.build_menu("fad", "person")
    texts2 = [a.text() for a in menu2.actions()]
    assert any(t.startswith("下班") for t in texts2)
    assert not any(t.startswith("上班") for t in texts2)   # 在跑的不给再开一个
    menu2.actions()[0].trigger()
    assert stopped == ["fad"]


def test_person_menu_can_resume_last_session(win):
    win.set_run_state("fad", "down")
    win.set_sessions("fad", [Session(id="s-new", title="最近那条", mtime=2.0),
                             Session(id="s-old", title="更早那条", mtime=1.0)])
    got = []
    win.start_requested.connect(lambda n, sid: got.append((n, sid)))
    menu = win.build_menu("fad", "person")
    next(a for a in menu.actions() if "上次" in a.text()).trigger()
    assert got == [("fad", "s-new")]


def test_files_menu_lists_sessions(win):
    """右键桌上那叠文件 = 会话历史:能接着某条继续,也能删掉某条记录。"""
    win.set_run_state("fad", "down")
    win.set_sessions("fad", [Session(id="s1", title="第一条", mtime=2.0),
                             Session(id="s2", title="第二条", mtime=1.0)])
    started, deleted = [], []
    win.start_requested.connect(lambda n, sid: started.append((n, sid)))
    win.delete_session_requested.connect(lambda n, sid: deleted.append((n, sid)))

    menu = win.build_menu("fad", "files")
    resume = next(a.menu() for a in menu.actions() if a.text() == "接着这条继续")
    assert [a.text() for a in resume.actions()] == ["第一条", "第二条"]
    resume.actions()[1].trigger()
    assert started == [("fad", "s2")]

    rm = next(a.menu() for a in menu.actions() if a.text() == "删除这条记录")
    rm.actions()[0].trigger()
    assert deleted == [("fad", "s1")]


def test_files_menu_of_running_seat_cannot_start_another(win):
    """已经在跑的成员:文件菜单里只剩「删除记录」,没有「接着继续」——防重复启动。"""
    win.set_sessions("fad", [Session(id="s1", title="第一条", mtime=1.0)])
    win.set_run_state("fad", "busy")
    texts = [a.text() for a in win.build_menu("fad", "files").actions()]
    assert texts == ["删除这条记录"]


def test_seat_menu_is_about_the_member(win):
    texts = [a.text() for a in win.build_menu("fad", "seat").actions()
             if a.text()]
    assert texts == ["大小", "复制会话地址", "打开目录", "编辑", "删除"]


def test_file_stack_follows_session_count(win):
    win.set_sessions("fad", [Session(id="s1", title="a", mtime=1.0),
                             Session(id="s2", title="b", mtime=2.0)])
    assert win.seats["fad"]._papers == 2
    win.set_sessions("fad", [])
    assert win.seats["fad"]._papers == 0


def test_each_seat_scales_on_its_own(win, app, tmp_path, monkeypatch):
    """整体缩放退休了,换成每个工位单独缩:不常用的缩小,别人不受影响。"""
    from claude_cockpit import settings
    win.set_seat_scale("fad", 0.5)
    assert win.seats["fad"].scale() == 0.5
    assert win.seats["fad-2"].scale() == 1.0        # 别人纹丝不动

    win.save_layout()
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "settings.json")
    again = OfficeWindow(_members())
    assert again.seats["fad"].scale() == 0.5        # 重开还记得
    assert again.seats["fad-2"].scale() == 1.0


def test_size_menu_marks_current_scale(win):
    win.set_seat_scale("fad", 0.7)
    menu = win.build_menu("fad", "seat")
    size = next(a.menu() for a in menu.actions() if a.text() == "大小")
    checked = [a.text() for a in size.actions() if a.isChecked()]
    assert checked == ["小"]


def test_wave_timer_runs_only_while_someone_talks(win):
    """音浪定时器有人朗读才开表——没人说话时不该每 180ms 醒一次。"""
    assert not win._wave_timer.isActive()
    win.set_run_state("fad", "busy")
    win.set_speaking("fad", True)
    assert win._wave_timer.isActive()
    win.set_speaking("fad", False)
    assert not win._wave_timer.isActive()
