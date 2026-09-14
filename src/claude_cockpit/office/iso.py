"""等距(isometric)投影:房间坐标 → 屏幕坐标。工位和送信的小人共用这一套。

抽成单独模块是因为 `person.py` 也要用它(坐着的人得画在和椅背同一个等距面上),
而 `person.py` 是被 `seat_item.py` 用的——投影工具留在 seat_item 里就成了循环 import。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter, QPolygonF, QTransform
# ---------- 等距(isometric)投影 ----------
# 房间坐标 (x, y, z):x 向右后、y 向左前、z 向上。1 单位 = 横 2px / 竖 1px——
# 用 2:1 等距而不是标准 30°,斜边正好压在像素上,小尺寸下不会糊成毛边。
#
# 家具全部在这套坐标里摆,投影出来自然是同一个朝向,不用逐个图元手调角度。
# 竖直的东西(桌腿、气杆)在屏幕上仍然是竖直的,所以那些直接用屏幕矩形画。
ISO_OX, ISO_OY = 62.0, 52.0         # 桌子后角在**地面**上的落点(原点)

# 桌子的房间尺寸:**长方形,长边(x)是人坐的那一边**。正方形桌子一眼就看出不对——
# 办公桌永远是长边对着人。桌上的东西和命中区都按这两个数排,改它们得跟着重排。
DESK_X, DESK_Y = 61.0, 22.0


def pt_at(ox: float, oy: float, x: float, y: float, z: float = 0.0) -> QPointF:
    """房间坐标 → 图元局部坐标,**投影原点由调用方给**。

    工位用不到这个(它的原点固定是 ISO_OX/OY),但机柜是另一套家具、摆在自己的
    图元框里,原点不一样;两边共用同一个投影公式才不会悄悄画成两个朝向。
    """
    return QPointF(ox + (x - y) * 2.0, oy + (x + y) - z)


def pt(x: float, y: float, z: float = 0.0) -> QPointF:
    """房间坐标 → 工位局部坐标。"""
    return pt_at(ISO_OX, ISO_OY, x, y, z)


def quad(*pts) -> QPolygonF:
    return QPolygonF([pt(*t) for t in pts])


def quad_at(ox: float, oy: float, *pts) -> QPolygonF:
    return QPolygonF([pt_at(ox, oy, *t) for t in pts])


# 三个平面各自的画笔坐标系。套上之后就能用普通的 drawRoundedRect / drawEllipse
# 画「斜着的」面,圆角和圆也跟着斜——不用把每个顶点手算成多边形。
ISO_TOP = QTransform(2, 1, -2, 1, 0, 0)     # 水平面:桌面、座垫、桌上的纸
ISO_FX = QTransform(2, 1, 0, 1, 0, 0)       # 朝左前的立面:屏幕、椅背、音响正面
ISO_FY = QTransform(-2, 1, 0, 1, 0, 0)      # 朝右前的立面:桌子的另一条前沿

# 写在 ISO_FX 那个面上的**文字**要单独一套:直接用 ISO_FX 会把字横向拉成两倍宽。
# 这里让横轴走 (2,1) 的**单位**方向(2/√5, 1/√5),字只是顺着板子斜下去、不变形。
ISO_TEXT_FX = QTransform(0.8944, 0.4472, 0, 1, 0, 0)


def on(p: QPainter, plane: QTransform, x: float, y: float, z: float = 0.0) -> None:
    """把画笔挪到房间点 (x,y,z) 并切进 plane 平面。调用方负责 save()/restore()。"""
    q = pt(x, y, z)
    p.translate(q.x(), q.y())
    p.setTransform(QTransform(plane), True)


def on_at(p: QPainter, plane: QTransform, ox: float, oy: float,
          x: float, y: float, z: float = 0.0) -> None:
    """同 `on`,但投影原点由调用方给(机柜用)。"""
    q = pt_at(ox, oy, x, y, z)
    p.translate(q.x(), q.y())
    p.setTransform(QTransform(plane), True)
