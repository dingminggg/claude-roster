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
    area = DeptAreaItem("后端组", 420, 150)
    area.setPos(10, 30)
    scene.addItem(area)
    seat = SeatItem(Member(name="fad", cwd=Path(".")))
    seat.setParentItem(area)          # 工位是地毯的子项 → 拖地毯自动跟着走
    seat.setPos(20, 26)
    area._test_scene = scene          # 防止 scene 被 GC 连带删掉场景里的图元
    return area, seat


def test_moving_area_moves_seat_in_scene_but_not_locally(area_with_seat):
    area, seat = area_with_seat
    assert seat.scenePos() == QPointF(30, 56)
    area.setPos(110, 230)
    assert seat.scenePos() == QPointF(130, 256)     # 场景坐标跟着走
    assert seat.pos() == QPointF(20, 26)            # 相对坐标不变 → 存盘不用重算


def test_grip_is_at_bottom_right(area_with_seat):
    area, _ = area_with_seat
    g = area.r_grip()
    assert g.right() == 420 and g.bottom() == 150


def test_resize_changes_size_only(area_with_seat):
    area, _ = area_with_seat
    before = area.pos()
    area.resize_to(QPointF(600, 400))
    assert (area.w, area.h) == (600, 400)
    assert area.pos() == before                     # 拉伸不该顺手把地毯挪走


def test_resize_clamped_to_minimum(area_with_seat):
    area, _ = area_with_seat
    area.resize_to(QPointF(10, 10))
    assert (area.w, area.h) == AREA_MIN


def test_geometry_reports_absolute_rect(area_with_seat):
    area, _ = area_with_seat
    area.setPos(7, 9)
    area.resize_to(QPointF(300, 200))
    assert area.geometry() == (7.0, 9.0, 300.0, 200.0)


def test_paint_does_not_crash(app, area_with_seat):
    from PySide6.QtGui import QImage, QPainter
    area, _ = area_with_seat
    img = QImage(500, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    area.paint(p, None, None)
    p.end()
