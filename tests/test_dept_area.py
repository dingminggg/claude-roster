"""部门地毯:整块拖动带着工位走、右下角拉伸只改尺寸。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsScene

from claude_cockpit.config import Member
from claude_cockpit.office.dept_area import AREA_MIN, DeptAreaItem
from claude_cockpit.office.seat_item import SeatItem


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def area_with_seat(app):
    scene = QGraphicsScene()
    area = DeptAreaItem("后端组", 452, 216)
    area.setPos(10, 30)
    scene.addItem(area)
    seat = SeatItem(Member(name="fad", cwd=Path(".")))
    seat.setParentItem(area)          # 工位是地毯的子项 → 拖地毯自动跟着走
    seat.setPos(18, 26)
    area._test_scene = scene          # 防止 scene 被 GC 连带删掉场景里的图元
    return area, seat


def test_moving_area_moves_seat_in_scene_but_not_locally(area_with_seat):
    area, seat = area_with_seat
    assert seat.scenePos() == QPointF(28, 56)
    area.setPos(110, 230)
    assert seat.scenePos() == QPointF(128, 256)     # 场景坐标跟着走
    assert seat.pos() == QPointF(18, 26)            # 相对坐标不变 → 存盘不用重算


def test_grip_is_at_bottom_right(area_with_seat):
    area, _ = area_with_seat
    g = area.r_grip()
    assert g.right() == 452 and g.bottom() == 216


def test_resize_changes_size_only(area_with_seat):
    area, _ = area_with_seat
    before = area.pos()
    area.resize_to(QPointF(600, 400))
    assert (area.w, area.h) == (600, 400)
    assert area.pos() == before                     # 拉伸不该顺手把地毯挪走


def test_resize_clamped_to_fit_its_seats(area_with_seat):
    """想缩到极小时,夹到「装得下现有工位」而不是那个固定下限。"""
    area, seat = area_with_seat
    seat.setPos(120, 60)                       # 工位往右下挪,下限就该跟着变大
    area.resize_to(QPointF(10, 10))
    assert (area.w, area.h) == area.content_min()
    assert area.w >= 120 + seat.boundingRect().width()
    assert area.h >= 60 + seat.boundingRect().height()
    assert area.w > AREA_MIN[0]                # 已经超过固定下限了


def test_geometry_reports_absolute_rect(area_with_seat):
    area, _ = area_with_seat
    area.setPos(7, 9)
    area.resize_to(QPointF(600, 500))
    assert area.geometry() == (7.0, 9.0, 600.0, 500.0)


def test_paint_does_not_crash(app, area_with_seat):
    from PySide6.QtGui import QImage, QPainter
    area, _ = area_with_seat
    img = QImage(500, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    area.paint(p, None, None)
    p.end()


def test_resize_cannot_shrink_below_its_seats(area_with_seat):
    """地毯不许缩到比里面的工位还小——工位是拖出来的,可能贴在右下角。"""
    area, seat = area_with_seat
    seat.setPos(234, 200)                      # 把工位拖到偏右下
    area.resize_to(QPointF(10, 10))            # 想缩到最小
    need_w = 234 + seat.boundingRect().width()
    need_h = 200 + seat.boundingRect().height()
    assert area.w >= need_w and area.h >= need_h


def test_resize_still_honours_flat_minimum_when_empty(app):
    """没有工位的空地毯仍然按固定下限夹。"""
    from claude_cockpit.office.dept_area import AREA_MIN, DeptAreaItem
    scene = QGraphicsScene()
    area = DeptAreaItem("空组", 452, 216)
    scene.addItem(area)
    area._keep = scene                         # 保活:场景被回收会连带删掉图元
    area.resize_to(QPointF(1, 1))
    assert (area.w, area.h) == AREA_MIN


def test_right_click_does_not_move_or_resize_area(area_with_seat):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    area, _ = area_with_seat
    before_pos, before_size = area.pos(), (area.w, area.h)
    ev = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    ev.setPos(QPointF(area.w - 4, area.h - 4))     # 正好落在拉伸角上
    ev.setButton(Qt.MouseButton.RightButton)
    area.mousePressEvent(ev)
    area.mouseMoveEvent(ev)
    assert area.pos() == before_pos and (area.w, area.h) == before_size
