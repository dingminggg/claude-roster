"""小人:坐姿和站姿两种画法。工位(SeatItem)和送信的小人(WalkerItem)共用这一份。

**不走等距切变**:切变后矩形的上沿是斜的,左肩会比右肩高一截、人看着驼背;和同样
要画在它旁边的椅背(也用屏幕坐标)更是永远对不齐。箱子才需要切变,身体是圆的——
所以这里只收一个**屏幕坐标的落脚点**,形状全用屏幕坐标的圆和圆角矩形画。

配色只有成员色一种,靠明度分三档:头最浅、躯干中、四肢最深。整张画布只给屏幕和人
上色(见 theme),小人内部再引入第二种颜色就花了。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPainter

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
    head_c, torso_c, _ = skin(color)
    p.save()
    on(p, ISO_FX, hx - 4.1, hy, 36)
    p.setBrush(QBrush(torso_c))
    p.drawRoundedRect(QRectF(0, 0, 8.2, 16), 3.5, 3.5)
    p.restore()
    c = pt(hx, hy, 40)
    p.setBrush(QBrush(head_c))
    p.drawEllipse(QRectF(c.x() - 7.5, c.y() - 7.5, 15, 15))


def draw_standing(p: QPainter, color: QColor, cx: float, floor_y: float,
                  bob: float = 0.0, shadow: bool = True) -> None:
    """站姿:头 + 躯干 + 下身 + 两只脚,站在 `(cx, floor_y)` 上。

    **不画胳膊、不画两条分开的腿**:整个人只有 46px 高,细长条在这个尺寸下只会糊成
    毛刺,两条腿在等距下还必然一高一低、散成两根棍。下身整块 + 两只脚更像人。
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
    p.setBrush(QBrush(torso_c))                 # 躯干:肩比腰宽一点才像人
    p.drawRoundedRect(QRectF(cx - 9, y - 31, 18, 17), 5, 5)
    p.setBrush(QBrush(head_c))
    p.drawEllipse(QRectF(cx - 7.5, y - 45.5, 15, 15))
