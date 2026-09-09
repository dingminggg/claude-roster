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
    ("down", "启动"),
    ("launching", "启动中"),
    ("busy", "忙碌中"),
    ("idle", "空闲"),
    ("running", "运行中"),
])
def test_label_per_state(seat, state, text):
    seat.set_run_state(state)
    assert seat.status_text() == text


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


@pytest.mark.parametrize("state,point,expect", [
    ("down", (120, 92), "go"),          # 启动键
    ("down", (120, 70), "picker"),      # 会话行
    ("down", (60, 40), "seat"),         # 桌面空白 → 拖动
    ("busy", (120, 92), "seat"),        # 运行中没有启动键
    ("busy", (60, 40), "seat"),
])
def test_hit_regions(seat, state, point, expect):
    seat.set_run_state(state)
    assert seat.hit(QPointF(*point)) == expect


def test_hit_confirm_buttons(seat):
    seat.set_run_state("down")
    seat.set_confirm(True)
    assert seat.hit(QPointF(105, 92)) == "yes"
    assert seat.hit(QPointF(140, 92)) == "no"


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


def test_press_start_button_emits_and_expands_confirm(app, seat):
    """点启动键:发 start_clicked 且原地展开成 ✓/✕(不弹窗)。"""
    got = []
    seat.start_clicked.connect(got.append)
    seat.set_run_state("down")
    _press(seat, 120, 92)
    assert got == ["fad"]
    assert seat.hit(QPointF(105, 92)) == "yes"      # 已经是确认态


def test_press_yes_emits_confirmed_and_collapses(app, seat):
    got = []
    seat.confirmed.connect(got.append)
    seat.set_run_state("down")
    seat.set_confirm(True)
    _press(seat, 105, 92)
    assert got == ["fad"]
    assert seat.hit(QPointF(120, 92)) == "go"       # 收回成启动键


def test_press_no_collapses_without_starting(app, seat):
    got = []
    seat.confirmed.connect(got.append)
    seat.set_run_state("down")
    seat.set_confirm(True)
    _press(seat, 140, 92)
    assert got == []
    assert seat.hit(QPointF(120, 92)) == "go"


def test_press_picker_emits(app, seat):
    got = []
    seat.picker_clicked.connect(got.append)
    seat.set_run_state("down")
    _press(seat, 120, 70)
    assert got == ["fad"]


def test_press_speaker_emits_only_while_speaking(app, seat):
    got = []
    seat.speaker_clicked.connect(got.append)
    seat.set_run_state("busy")
    _press(seat, 170, 30)               # 没在朗读:喇叭不存在,当点桌面
    assert got == []
    seat.set_speaking(True)
    _press(seat, 170, 30)
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


def test_right_click_does_not_trigger_click_or_picker(app, seat):
    """右键只该弹菜单:不许顺带把控制台最大化,也不许弹会话下拉。"""
    from PySide6.QtCore import Qt as _Qt
    clicks, pickers, starts = [], [], []
    seat.clicked.connect(clicks.append)
    seat.picker_clicked.connect(pickers.append)
    seat.start_clicked.connect(starts.append)

    seat.set_run_state("busy")
    _press_button(seat, 60, 40, _Qt.MouseButton.RightButton)     # 右键点桌面
    assert clicks == []

    seat.set_run_state("down")
    _press_button(seat, 120, 70, _Qt.MouseButton.RightButton)    # 右键点会话行
    _press_button(seat, 120, 92, _Qt.MouseButton.RightButton)    # 右键点启动键
    assert pickers == [] and starts == []
    assert seat.hit(QPointF(120, 92)) == "go"                    # 没被展开成确认态


def test_left_click_still_works(app, seat):
    """确认上面那道拦截没把左键一起挡掉。"""
    from PySide6.QtCore import Qt as _Qt
    clicks = []
    seat.clicked.connect(clicks.append)
    seat.set_run_state("busy")
    _press_button(seat, 60, 40, _Qt.MouseButton.LeftButton)
    assert clicks == ["fad"]
