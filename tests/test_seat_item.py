"""工位图元:状态映射(文字/屏幕光/明暗)、消息闪、命中区。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

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
    _press(seat, 40, 44)                # 没在朗读:音响只是摆设,当点工位
    assert got == []
    seat.set_speaking(True)
    _press(seat, 40, 44)
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
    assert seat.hit(QPointF(100, 100)) == "person"   # 椅子上的人
    assert seat.hit(QPointF(40, 150)) == "seat"      # 桌腿旁边的空地
    at_speaker = QPointF(40, 44)                     # 桌上那个小音响
    assert seat.hit(at_speaker) == "seat"            # 没在朗读:它只是个摆设
    seat.set_speaking(True)
    assert seat.hit(at_speaker) == "speaker"


def test_files_only_exist_when_there_are_sessions(app, seat):
    """没有历史会话就没有那叠文件,那块地方当普通桌面。"""
    seat.set_run_state("down")
    at_files = QPointF(150, 44)
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
