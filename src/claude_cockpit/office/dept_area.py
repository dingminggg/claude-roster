"""一块部门地毯:圆角矩形 + 部门名 + 右下角拉伸角。

工位挂在它下面当子项,所以拖地毯 = 整个部门搬家,工位的相对坐标不动。
部门归属只认 agents.yaml 的 dept 字段——把工位拖到别的地毯上不会改部门。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import AREA_MIN
from .theme import CARPET, CARPET_EDGE as EDGE, CARPET_LABEL as LABEL
from .theme import GRIP as GRIP_COLOR

GRIP = 14                       # 右下角拉伸角的边长(px,别和 theme 的颜色撞名)
CONTENT_PAD = 10.0              # 收缩时给最靠边的那个工位留的边


class DeptAreaItem(QGraphicsObject):
    changed = Signal(str)       # 拖完 / 拉伸完:该存盘了

    def __init__(self, name: str, w: float, h: float):
        super().__init__()
        self.name = name
        self.w = float(w)
        self.h = float(h)
        self._resizing = False
        self.setZValue(-1)      # 画在工位底下
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.w, self.h)

    def r_grip(self) -> QRectF:
        return QRectF(self.w - GRIP, self.h - GRIP, GRIP, GRIP)

    def geometry(self) -> tuple[float, float, float, float]:
        return (self.pos().x(), self.pos().y(), self.w, self.h)

    def content_min(self) -> tuple[float, float]:
        """地毯至少要多大才装得下现有的工位(工位是子项,位置由用户拖出来的)。

        光用固定下限不够:工位可以被拖到地毯右下角,那时候还按 200×120 收缩,
        地毯就缩到工位下面去了。
        """
        w, h = AREA_MIN
        for it in self.childItems():
            r = it.boundingRect()
            w = max(w, it.pos().x() + r.width() + CONTENT_PAD)
            h = max(h, it.pos().y() + r.height() + CONTENT_PAD)
        return (w, h)

    def resize_to(self, pos: QPointF) -> None:
        """按局部坐标里的一点定尺寸(夹到最小值)。拉伸只改尺寸,不动位置。"""
        min_w, min_h = self.content_min()
        self.prepareGeometryChange()
        self.w = max(min_w, float(pos.x()))
        self.h = max(min_h, float(pos.y()))
        self.update()

    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(EDGE, 1, Qt.PenStyle.DashLine))
        p.setBrush(QBrush(CARPET))
        p.drawRoundedRect(QRectF(0, 0, self.w, self.h), 10, 10)
        f = QFont(); f.setPointSize(9); f.setBold(True); p.setFont(f)
        p.setPen(QPen(LABEL))
        p.drawText(QRectF(12, 4, max(20.0, self.w - 20), 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.name)
        # 拉伸角:三条斜线,常见 resize handle 的样子
        p.setPen(QPen(GRIP_COLOR, 1.4))
        g = self.r_grip()
        for d in (3, 7, 11):
            p.drawLine(QPointF(g.right() - d, g.bottom() - 2),
                       QPointF(g.right() - 2, g.bottom() - d))

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()          # 右键只该弹菜单,别把地毯拖走/拉伸
            return
        if self.r_grip().contains(e.pos()):
            self._resizing = True       # 抓着角就只改大小,别顺手把地毯拖走
            e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self.resize_to(e.pos())
            e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        was_resizing = self._resizing
        self._resizing = False
        if not was_resizing:
            super().mouseReleaseEvent(e)
        self.changed.emit(self.name)
