"""工位图元:状态映射(文字/屏幕光/明暗)、消息闪、命中区。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QApplication, QGraphicsSceneMouseEvent

from claude_cockpit.config import Member
from claude_cockpit.office.seat_item import UP_STATES, STATE_STYLE, SeatItem


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def seat(app):
    return SeatItem(Member(name="fad", cwd=Path("."), emoji="🏪", color="#e74c3c"))


@pytest.mark.parametrize("state,text", [
    ("down", "未上班"),
    ("launching", "启动中"),
    ("busy", "忙碌中"),
    ("idle", "空闲"),
    ("running", "运行中"),
])
def test_label_per_state(seat, state, text):
    """状态文字只出现在 tooltip 里——画面上状态是靠屏幕颜色表达的。"""
    seat.set_run_state(state)
    assert seat.status_text() == text
    assert text in seat.toolTip()


def test_up_states_are_exactly_the_three(seat):
    assert UP_STATES == ("running", "busy", "idle")
    for s in UP_STATES:
        seat.set_run_state(s)
        assert seat.is_up()
    for s in ("down", "launching"):
        seat.set_run_state(s)
        assert not seat.is_up()


def test_unknown_state_falls_back_to_running(seat):
    """探不到状态时兜底「运行中」,绝不退化成未运行(否则会重复开空白窗口)。"""
    seat.set_run_state("wat")
    assert seat.status_text() == "运行中"
    assert seat.is_up()


def test_glow_colors_differ_between_busy_and_idle(seat):
    assert STATE_STYLE["busy"].glow != STATE_STYLE["idle"].glow


def test_flash_only_when_up(seat):
    """有新消息 = 屏幕闪;未运行的一律不闪(没窗口就没有「在等你」这回事)。"""
    seat.set_message(True)
    seat.set_blink(True)
    seat.set_run_state("busy")
    assert seat.is_flashing()
    seat.set_run_state("down")
    assert not seat.is_flashing()
    seat.set_run_state("launching")
    assert not seat.is_flashing()


def test_flash_follows_blink_half_beat(seat):
    seat.set_run_state("busy")
    seat.set_message(True)
    seat.set_blink(False)
    assert not seat.is_flashing()
    seat.set_blink(True)
    assert seat.is_flashing()




def test_down_seat_does_not_emit_clicked(app, seat):
    """未运行的工位点桌面没反应——只有启动键能开(硬约束 3:自动动作绝不 launch)。"""
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent
    from PySide6.QtCore import QEvent, Qt
    got = []
    seat.clicked.connect(got.append)
    scene = QGraphicsScene()
    scene.addItem(seat)
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(QPointF(60, 40))          # 桌面空白
    ev.setButton(Qt.MouseButton.LeftButton)
    seat.set_run_state("down")
    seat.mousePressEvent(ev)
    assert got == []
    seat.set_run_state("busy")
    seat.mousePressEvent(ev)
    assert got == ["fad"]


def test_paint_does_not_crash_in_any_state(app, seat):
    """离屏渲染一遍每个状态:绘制代码里有算色/渐变,别让它在某个状态下炸。"""
    from PySide6.QtGui import QImage, QPainter
    img = QImage(200, 130, QImage.Format.Format_ARGB32)
    for state in ("down", "launching", "busy", "idle", "running"):
        seat.set_run_state(state)
        p = QPainter(img)
        seat.paint(p, None, None)
        p.end()


def _press(seat, x, y):
    """造一次**左键**按下打到工位的局部坐标 (x, y)。

    必须显式设 button:不设就是 Qt.NoButton,会被「只处理左键」那道拦截挡掉。
    """
    from PySide6.QtCore import QEvent, Qt as _Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(QPointF(x, y))
    ev.setButton(_Qt.MouseButton.LeftButton)
    seat.mousePressEvent(ev)











def test_press_speaker_emits_only_while_speaking(app, seat):
    got = []
    seat.speaker_clicked.connect(got.append)
    seat.set_run_state("busy")
    _press(seat, 59, 26)                # 没在朗读:音响只是摆设,当点工位
    assert got == []
    seat.set_speaking(True)
    _press(seat, 59, 26)
    assert got == ["fad"]


def test_moved_only_fires_when_position_actually_changed(app, seat):
    """点一下工位不该触发存盘;只有真拖动过才发 moved。"""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    got = []
    seat.moved.connect(got.append)
    seat.set_run_state("busy")

    def release():
        ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
        ev.setPos(QPointF(60, 40))
        ev.setButton(Qt.MouseButton.LeftButton)
        seat.mouseReleaseEvent(ev)

    _press(seat, 60, 40)                # 点桌面没挪
    release()
    assert got == []

    _press(seat, 60, 40)
    seat.setPos(300, 200)               # 拖走
    release()
    assert got == ["fad"]


def _press_button(seat, x, y, button):
    from PySide6.QtCore import QEvent, Qt as _Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(QPointF(x, y))
    ev.setButton(button)
    seat.mousePressEvent(ev)
    return ev




def test_left_click_still_works(app, seat):
    """确认上面那道拦截没把左键一起挡掉。"""
    from PySide6.QtCore import Qt as _Qt
    clicks = []
    seat.clicked.connect(clicks.append)
    seat.set_run_state("busy")
    _press_button(seat, 60, 40, _Qt.MouseButton.LeftButton)
    assert clicks == ["fad"]


def test_hit_regions_are_semantic(app, seat):
    """命中区是有语义的:点人 = 管上下班,点文件 = 管会话历史,其余 = 点工位。"""
    seat.set_run_state("busy")
    assert seat.hit(QPointF(43, 90)) == "person"   # 椅子上的人
    assert seat.hit(QPointF(40, 150)) == "seat"      # 桌腿旁边的空地
    at_speaker = QPointF(59, 26)                     # 桌上那个小音响
    assert seat.hit(at_speaker) == "seat"            # 没在朗读:它只是个摆设
    seat.set_speaking(True)
    assert seat.hit(at_speaker) == "speaker"


def test_files_only_exist_when_there_are_sessions(app, seat):
    """没有历史会话就没有那叠文件,那块地方当普通桌面。"""
    seat.set_run_state("down")
    at_files = QPointF(134, 95)
    assert seat.hit(at_files) == "seat"
    seat.set_session_count(3)
    assert seat.hit(at_files) == "files"
    seat.set_session_count(0)
    assert seat.hit(at_files) == "seat"


def test_right_click_does_not_maximize(app, seat):
    """右键只该弹菜单,不许顺带把控制台弹到眼前。"""
    from PySide6.QtCore import QEvent, Qt as _Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    got = []
    seat.clicked.connect(got.append)
    seat.set_run_state("busy")
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(QPointF(100, 100))
    ev.setButton(_Qt.MouseButton.RightButton)
    seat.mousePressEvent(ev)
    assert got == []


def test_wave_only_animates_while_speaking(app, seat):
    """音浪只在朗读时走帧;没在说话就别让它空转(那是每 180ms 一次重绘)。"""
    seat.set_run_state("busy")
    seat.advance_wave()
    assert seat._wave == 0
    seat.set_speaking(True)
    seat.advance_wave()
    assert seat._wave == 1
    seat.set_speaking(False)
    assert seat._wave == 0              # 停了就归位,下次从头跳


def test_screen_scrolls_only_while_busy(app, seat):
    """屏幕在滚 = 正在干活。空闲的不滚——那是「谁在忙」的第二遍表达,滚了就没信息量。"""
    seat.set_run_state("idle")
    before = seat._scroll
    seat.advance_scroll()
    assert seat._scroll == before
    seat.set_run_state("busy")
    seat.advance_scroll()
    assert seat._scroll > before


def test_screen_scroll_wraps(app, seat):
    """偏移必须绕回来,不然滚着滚着行就跑到屏幕外面再也不回来了。"""
    from claude_cockpit.office.seat_item import LINE_GAP
    seat.set_run_state("busy")
    span = len(seat._lines) * LINE_GAP
    for _ in range(500):
        seat.advance_scroll()
        assert 0 <= seat._scroll < span


def _press_at(pos: QPointF) -> QGraphicsSceneMouseEvent:
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(pos)
    ev.setButton(Qt.MouseButton.LeftButton)
    return ev


def test_no_phone_without_history(seat):
    """一条记录都没有就不画手机:桌面不多一块杂物。"""
    assert not seat.has_phone()
    assert seat.hit(seat.r_phone().center()) != "phone"


def test_phone_appears_with_history(seat):
    seat.set_history(3, 1)
    assert seat.has_phone()
    assert seat.hit(seat.r_phone().center()) == "phone"


@pytest.mark.parametrize("with_rack", [False, True])
def test_phone_hit_rect_disjoint_from_others(seat, with_rack):
    """命中区两两不相交——叠了就会「点手机弹控制台」这种串台。

    **按工位的两种形态各验一遍**:普通工位(桌右侧是那叠文件)和运维那张(桌右侧
    换成机柜)。文件堆和机柜**永不共存**(`set_papers_enabled(False)`),它俩正好
    都占着「显示器右边」那块地,所以只能分开验——一起塞进同一个字典必然假报。
    手机在桌子左端,两种形态里都在,所以两轮都卡住了它。
    """
    from claude_cockpit.services import Service
    seat.set_history(3, 1)
    seat.set_session_count(3)
    if with_rack:                       # 运维那张:机柜顶掉文件堆
        seat.set_services([Service("mysql", 3306)])
        seat.set_papers_enabled(False)
        assert seat.has_rack() and not seat.has_papers()
    else:
        assert seat.has_papers() and not seat.has_rack()
    rects = {"phone": seat.r_phone(), "person": seat.r_person(),
             "speaker": seat.r_speaker()}
    rects["rack" if with_rack else "files"] = (
        seat.r_rack() if with_rack else seat.r_files())
    names = sorted(rects)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not rects[a].intersects(rects[b]), f"{a} 和 {b} 的命中区叠了"


def test_phone_tooltip_counts(seat):
    seat.set_history(3, 1)
    seat._sync_tip("phone")
    assert "3 条对话记录" in seat.toolTip()
    assert "1 条未读" in seat.toolTip()
    seat.set_history(3, 0)
    seat._sync_tip("phone")
    assert "未读" not in seat.toolTip()


def test_phone_click_emits(seat):
    got = []
    seat.phone_clicked.connect(got.append)
    seat.set_history(2, 0)
    seat.set_run_state("idle")
    seat.mousePressEvent(_press_at(seat.r_phone().center()))
    assert got == [seat.name]


def test_phone_click_does_not_raise_console(seat):
    """点手机只开记录窗,不该顺带把控制台弹到眼前(clicked 是那件事)。"""
    raised = []
    seat.clicked.connect(raised.append)
    seat.set_history(2, 0)
    seat.set_run_state("idle")
    seat.mousePressEvent(_press_at(seat.r_phone().center()))
    assert raised == []


def test_phone_paints_in_every_state(seat):
    """画一遍别炸(包括未上班那档整体置灰)。"""
    from PySide6.QtGui import QImage, QPainter
    seat.set_history(3, 2)
    for st in ("down", "launching", "busy", "idle", "running"):
        seat.set_run_state(st)
        img = QImage(240, 200, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        seat.paint(p, None, None)
        p.end()


# ---------- 钉住的气泡(点工位时印出来的那句「总结」) ----------
def test_plain_say_expires_on_its_own(seat):
    seat.set_run_state("idle")
    seat.say("都正常")
    assert seat.is_saying() and not seat.is_sticky_saying()
    assert seat._say_timer.isActive()


def test_sticky_say_never_expires(seat):
    """语音要念好一会儿,气泡自己收掉的话人一抬头就没了。"""
    seat.set_run_state("idle")
    seat.say("改完了。", sticky=True)
    assert seat.is_sticky_saying()
    assert not seat._say_timer.isActive()


def test_sticky_bubble_is_a_hit_region_and_click_closes_it(seat):
    seat.set_run_state("idle")
    seat.say("改完了。", sticky=True)
    assert seat.hit(seat.r_bubble().center()) == "bubble"
    raised = []
    seat.clicked.connect(raised.append)
    seat.mousePressEvent(_press_at(seat.r_bubble().center()))
    assert not seat.is_saying()
    assert raised == []         # 点气泡只收气泡,不顺带把控制台弹到眼前


def test_plain_bubble_is_not_clickable(seat):
    """会自己收的那种不抢点击:点下去仍是「点工位」。"""
    seat.set_run_state("idle")
    seat.say("都正常")
    assert seat.hit(seat.r_bubble().center()) != "bubble"


def test_no_bubble_no_hit_region(seat):
    assert seat.r_bubble().isEmpty()
    assert not seat.r_bubble().contains(QPointF(0, 0))


def test_bubble_hit_rect_disjoint_from_the_desk(seat):
    """气泡整个在工位框上方,和桌上那几块命中区不能叠(叠了就串台)。"""
    from claude_cockpit.services import Service
    seat.set_history(3, 1)
    seat.set_session_count(3)
    seat.set_run_state("idle")
    seat.say("啊" * 200, sticky=True)        # 最长的那种气泡
    b = seat.r_bubble()
    for other in (seat.r_person(), seat.r_speaker(), seat.r_files(),
                  seat.r_phone()):
        assert not b.intersects(other)
    seat.set_services([Service("mysql", 3306)])
    assert not b.intersects(seat.r_rack())


def test_sticky_bubble_grows_the_bounding_rect(seat):
    seat.set_run_state("idle")
    plain = seat.boundingRect()
    seat.say("啊" * 200, sticky=True)
    assert seat.boundingRect().top() < plain.top()


def test_bounding_rect_covers_the_whole_bubble(seat):
    """包围盒要把气泡整块含进去——**两侧也要**。满宽的气泡往左伸出工位框外,
    只让上边的话 Qt 不给那截重画区域,画面上就是「气泡左边少一块」。"""
    seat.set_run_state("idle")
    seat.say("啊" * 200, sticky=True)
    b = seat.r_bubble()
    assert b.left() < 0                     # 确实伸到工位框外了,这条才有意义
    assert seat.boundingRect().contains(b)
