"""小人:坐姿和站姿两种画法。工位(SeatItem)和送信的小人(WalkerItem)共用这一份。

**不走等距切变**:切变后矩形的上沿是斜的,左肩会比右肩高一截、人看着驼背;和同样
要画在它旁边的椅背(也用屏幕坐标)更是永远对不齐。箱子才需要切变,身体是圆的——
所以这里只收一个**屏幕坐标的落脚点**,形状全用屏幕坐标的圆和圆角矩形画。

配色只有成员色一种,靠明度分三档:头最浅、躯干中、四肢最深。整张画布只给屏幕和人
上色(见 theme),小人内部再引入第二种颜色就花了。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from .iso import ISO_FX, on, pt
from .theme import BEZEL, SHADOW, mix


def skin(color: QColor) -> tuple[QColor, QColor, QColor]:
    """成员配色 → (头, 躯干, 四肢) 三档明度。"""
    return (color, mix(color, BEZEL, 0.16), mix(color, BEZEL, 0.32))


def draw_sitting(p: QPainter, color: QColor, hx: float, hy: float) -> None:
    """坐姿:只画头和躯干——腿在桌子和椅背后面,本来就看不见,画了也是白费。
    收的是**房间坐标**(椅子那一点),调用方负责在这之后画椅背压住下半身。

    躯干画在 **ISO_FX 面**上,和椅背同一个面:两者上沿平行,露出来的肩膀就是一条
    等宽的带子。躯干若用屏幕矩形(上沿水平)、椅背用等距面(上沿是斜的),两条边不
    平行,肩膀会左薄右厚,看着像人歪在椅子上(踩过)。头是球,没有朝向问题,照旧
    用屏幕坐标画圆。
    """
    head_c, torso_c, limb_c = skin(color)
    # 胳膊:从肩膀伸到键盘上(手落在键盘那一片,不凭空停在半路)。起点压得比头低,
    # 不然胳膊看着是从脑袋里长出来的——这个尺寸下头占的地方不小。
    # **肘部要折一下**:肩到手拉一根直线,人看着像插了两根棍子。肘往下外侧顶出来,
    # 偏移量直接在屏幕坐标上加(等距坐标里没有「屏幕往下」这个方向,换算反而绕)。
    p.setPen(QPen(limb_c, 3.5, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for dx, hdx in ((-4.0, 0.0), (4.0, 6.0)):
        a = pt(hx + dx, hy - 1, 30)                 # 肩
        b = pt(hx + hdx, hy - 14, 27)               # 手(落在键盘那一片上,不是它前面)
        elbow = QPointF((a.x() + b.x()) / 2 + 1.5, (a.y() + b.y()) / 2 + 5.5)
        p.drawPolyline(QPolygonF([a, elbow, b]))
    p.setPen(Qt.PenStyle.NoPen)
    p.save()
    on(p, ISO_FX, hx - 4.1, hy, 36)
    p.setBrush(QBrush(torso_c))
    p.drawRoundedRect(QRectF(0, 0, 8.2, 16), 3.5, 3.5)
    p.restore()
    c = pt(hx, hy, 40)
    p.setBrush(QBrush(head_c))
    p.drawEllipse(QRectF(c.x() - 7.5, c.y() - 7.5, 15, 15))


def draw_sitting_legs(p: QPainter, color: QColor, hx: float, hy: float) -> None:
    """坐姿的腿:大腿从胯往前伸到桌子底下(-y 方向),小腿再竖下来。

    **必须画在椅子之前**:腿在座垫和五爪底盘的后面,画在后面会盖住它们,看着像人
    把腿甩到椅子外面(踩过)。这样只有桌子底下那一截露出来——桌下没有挡板,正好
    看得见;不画的话人就是个「浮在椅子上的半身」。
    """
    _, _, limb_c = skin(color)
    p.setPen(QPen(limb_c, 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for dx in (-2.2, 2.2):
        knee = pt(hx + dx, hy - 5, 15)
        p.drawLine(pt(hx + dx, hy, 15), knee)
        p.drawLine(knee, pt(hx + dx, hy - 5, 6.5))
    p.setPen(Qt.PenStyle.NoPen)


def draw_standing(p: QPainter, color: QColor, cx: float, floor_y: float,
                  bob: float = 0.0, shadow: bool = True) -> None:
    """站姿:头 + 躯干 + 下身 + 两只脚,站在 `(cx, floor_y)` 上。

    腿不劈成两条(等距下必然一高一低、散成两根棍),用「下身整块 + 两只脚」;胳膊用
    **圆头线段**贴在身体两侧,别用细长的圆角矩形——那个在这个尺寸下会糊成毛刺,
    而且两头接不到身上(踩过)。
    `bob` 是走路时上下起伏的位移(只抬身体,影子和脚不动,才像迈步)。
    """
    head_c, torso_c, limb_c = skin(color)
    if shadow:
        p.setBrush(QBrush(SHADOW))
        p.drawEllipse(QRectF(cx - 11, floor_y - 4, 22, 8))
    p.setBrush(QBrush(limb_c))
    for dx in (-4.5, 4.5):                      # 两只脚
        p.drawEllipse(QRectF(cx + dx - 3.5, floor_y - 4, 7, 3.6))
    y = floor_y - bob
    p.drawRoundedRect(QRectF(cx - 7, y - 16, 14, 14), 3, 3)     # 下身
    p.setPen(QPen(limb_c, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for dx in (-8.0, 8.0):                      # 两条胳膊:贴着身体两侧垂下来
        p.drawLine(cx + dx, y - 28, cx + dx * 1.15, y - 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(torso_c))                 # 躯干:肩比腰宽一点才像人
    p.drawRoundedRect(QRectF(cx - 9, y - 31, 18, 17), 5, 5)
    p.setBrush(QBrush(head_c))
    p.drawEllipse(QRectF(cx - 7.5, y - 45.5, 15, 15))
