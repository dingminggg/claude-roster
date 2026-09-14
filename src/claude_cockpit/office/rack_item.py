"""机房里的两样东西:机柜(`RackItem`)和运维小人(`OpsItem`)。

一台机柜 = 一个本地服务(mysql / redis / apache)。**状态就是柜面那排灯**,和工位
「屏幕色 = 运行状态」同一个口径:绿 = 端口听得到、灭 + 整柜置灰 = 没跑、
琥珀半拍一闪 = 端口在但不搭理你(防火墙吞了 / 进程僵住)。画面上不写状态文字,
文字版挂在悬停提示里——和工位一样。

机柜占一个**工位大小的格子**(SEAT_W × SEAT_H):机房区就是一块普通部门区,
拖动吸附、存盘、缩放全走现成那套,不用为机房另起一套布局账本。

**只读**:点它不启停服务(要管理员权限,而且看板上误点一下就把 MySQL 关了)。
右键只有「复制连接地址」。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import SEAT_H, SEAT_W
from ..services import DOWN, STUCK, UP
from . import person
from .iso import ISO_FX, ISO_TEXT_FX
from .iso import on_at as _on
from .iso import pt_at as _pt
from .iso import quad_at as _quad
from .theme import (
    BEZEL, LED_DOWN, LED_STUCK, LED_UP, OFF_OPACITY, RACK, RACK_NAME, RACK_OFF,
    RACK_SIDE, RACK_SLOT, RACK_TOP, SHADOW, mix,
)

# 机柜的房间尺寸(x 宽 / y 深 / z 高)。高瘦——机柜就该比桌子高、比桌子窄,
# 尺寸本身就是「这不是办公家具」的第一个信号。
RX, RY, RZ = 22.0, 16.0 , 64.0
# 投影原点:把柜子摆到格子中间偏下(柜子高,顶会往上顶出去)
ROX, ROY = SEAT_W / 2 - RX + 6, SEAT_H - 26.0

SLOTS = 5                   # 柜门上几个 1U 槽位
SLOT_Z0, SLOT_H, SLOT_GAP = 26.0, 6.5, 3.2   # 起始高度 / 每层厚 / 层间距
NAME_Z = 16.0               # 服务名那条:压在最低一层槽位下面

STATE_TEXT = {UP: "运行中", DOWN: "没在跑", STUCK: "无响应"}
LED = {UP: LED_UP, DOWN: LED_DOWN, STUCK: LED_STUCK}

FONT_NAME = QFont()
FONT_NAME.setPointSize(7)
FONT_NAME.setBold(True)


class RackItem(QGraphicsObject):
    """一台机柜。QGraphicsObject 是为了能发信号(同 SeatItem)。"""

    moved = Signal(str)                 # 拖完:该存盘了

    def __init__(self, svc):
        super().__init__()
        self.svc = svc
        self.name = svc.name
        self._state = DOWN
        self._blink = True
        self._press_pos = None
        # 同 SeatItem:可拖但**不可选**——Qt 会把选中的可移动图元跟着父级一起拖,
        # 点过的那个会比别人多挪一倍。
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self._sync_tip()

    # ---------- 状态入口 ----------
    def set_state(self, state: str) -> None:
        self._state = state if state in LED else DOWN
        self._sync_tip()
        self.update()

    def set_blink(self, on: bool) -> None:
        """半拍一闪的相位(由 OfficeWindow 那条 550ms 的表统一喂)。
        只有异常状态才闪,所以别的状态下直接不重画。"""
        self._blink = bool(on)
        if self.is_flashing():
            self.update()

    def is_flashing(self) -> bool:
        return self._state == STUCK

    def state(self) -> str:
        return self._state

    def _sync_tip(self) -> None:
        self.setToolTip(f"{self.name}  {self.svc.address}\n"
                        f"{STATE_TEXT.get(self._state, '未知')}")

    # ---------- 几何 ----------
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, SEAT_W, SEAT_H)

    # ---------- 画 ----------
    def paint(self, p: QPainter, opt, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        up = self._state != DOWN
        if not up:
            p.setOpacity(OFF_OPACITY)
        body = RACK if up else RACK_OFF
        side = RACK_SIDE if up else mix(RACK_OFF, RACK_SIDE, 0.35)
        top = RACK_TOP if up else mix(RACK_OFF, RACK_TOP, 0.35)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(SHADOW))      # 落地影子:说明这东西是立着的
        base = _pt(ROX, ROY, RX / 2, RY / 2)
        p.drawEllipse(base, (RX + RY) * 0.62, (RX + RY) * 0.31)

        # 三个面都要画:少一面就塌成纸片(工位上的音响踩过)
        p.setBrush(QBrush(side))        # x=RX 那面:侧板,深一档
        p.drawPolygon(_quad(ROX, ROY, (RX, 0, 0), (RX, RY, 0),
                            (RX, RY, RZ), (RX, 0, RZ)))
        p.setBrush(QBrush(body))        # y=RY 那面:柜门,灯和名字都在这儿
        p.drawPolygon(_quad(ROX, ROY, (0, RY, 0), (RX, RY, 0),
                            (RX, RY, RZ), (0, RY, RZ)))
        p.setBrush(QBrush(top))
        p.drawPolygon(_quad(ROX, ROY, (0, 0, RZ), (RX, 0, RZ),
                            (RX, RY, RZ), (0, RY, RZ)))

        self._paint_face(p, up)

    def _paint_face(self, p: QPainter, up: bool) -> None:
        """柜面:一排 1U 槽位,每层右端一颗状态灯,最下面印服务名。

        门开在 **y = RY 那个面**上,也就是 `ISO_FX` 平面——这个平面的横轴走房间的
        **x**、纵轴是屏幕往下(挂错成常 x 的面,整排灯会飞到柜子外面去,踩过)。
        和工位的显示器、椅背同一个面,所以整间屋子的「正面」都朝一个方向。
        """
        led = LED[self._state]
        if self.is_flashing() and not self._blink:
            led = mix(led, QColor("#ffffff"), 0.5)      # 异常:半拍一闪
        slot = RACK_SLOT if up else mix(RACK_OFF, RACK_SLOT, 0.45)
        z = SLOT_Z0
        for _ in range(SLOTS):
            p.save()
            _on(p, ISO_FX, ROX, ROY, 1.6, RY, z)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(slot))
            p.drawRect(QRectF(0, -SLOT_H, RX - 3.2, SLOT_H))
            p.setBrush(QBrush(led))                     # 每层右端那颗灯
            p.drawRect(QRectF(RX - 6.4, -SLOT_H + 1.2, 2.2, SLOT_H - 2.4))
            p.restore()
            z += SLOT_H + SLOT_GAP

        p.save()                        # 服务名:印在柜面最下面那条
        _on(p, ISO_TEXT_FX, ROX, ROY, 1.6, RY, NAME_Z)
        p.setPen(QPen(RACK_NAME if up else mix(RACK_OFF, RACK_NAME, 0.55)))
        p.setFont(FONT_NAME)
        # 可用长度是**算出来的**:沿板方向 1 个房间单位 = 2.2361px(横 2、竖 1),
        # 所以改柜宽,名字的地盘自动跟着变,不用手调(同工位名牌那套)。
        p.drawText(QRectF(0, -9.0, (RX - 4.0) * 2.2361, 10.0),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   self.name)
        p.restore()

    # ---------- 交互 ----------
    def mousePressEvent(self, e) -> None:
        """**只接左键**:右键一律放过去给菜单,不然右键会顺带把图元拖走(工位踩过)。"""
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        self._press_pos = self.pos()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        if self._press_pos is not None and self.pos() != self._press_pos:
            self.moved.emit(self.name)      # 真挪过才存盘
        self._press_pos = None


class OpsItem(QGraphicsObject):
    """机房里的运维小人:全绿就坐着,有服务挂了就站起来。

    它是机房区的**固定摆设**,不可拖也不存坐标(位置由 `place()` 钉在区域右下角)——
    给它一个格子反而要占掉一台机柜的位置,而它并不是一台设备。
    """

    W, H = 60, 76

    def __init__(self, color: str = "#6f7b8d"):
        super().__init__()
        self.color = QColor(color)
        self._alarm = False
        self.setToolTip("运维:服务全绿就坐着,有服务挂了就站起来")

    def set_alarm(self, on: bool) -> None:
        if self._alarm != bool(on):
            self._alarm = bool(on)
            self.update()

    def is_alarmed(self) -> bool:
        return self._alarm

    def place(self, area_w: float, area_h: float) -> None:
        """钉在机房区右下角(区域一拉伸就得重钉,所以单独一个方法)。"""
        self.setPos(max(0.0, area_w - self.W - 16.0),
                    max(0.0, area_h - self.H - 12.0))

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.W, self.H)

    def paint(self, p: QPainter, opt, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        cx, floor = self.W / 2, self.H - 8
        if self._alarm:
            person.draw_standing(p, self.color, cx, floor)
            return
        self._sit(p, cx, floor)

    def _sit(self, p: QPainter, cx: float, floor: float) -> None:
        """坐在小凳子上。**没有复用 person.draw_sitting**:那一份是为工位定制的——
        胳膊伸向键盘、躯干要和椅背对齐;机房里既没桌也没椅背,照搬过来胳膊就成了
        指向天的两根棍子(踩过)。这里是一份不依赖家具的坐姿:凳面 + 躯干 + 头 +
        垂下的小腿,全用屏幕坐标(同站姿的口径,切变一个整身会让人看着驼背)。
        """
        head_c, torso_c, limb_c = person.skin(self.color)
        p.setBrush(QBrush(SHADOW))
        p.drawEllipse(QRectF(cx - 13, floor - 6, 26, 10))
        p.setPen(QPen(limb_c, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for dx in (-4.5, 4.5):                      # 小腿:从凳沿垂到地上
            p.drawLine(QPointF(cx + dx, floor - 16), QPointF(cx + dx, floor - 3))
        p.setPen(Qt.PenStyle.NoPen)
        stool = mix(self.color, BEZEL, 0.5)
        p.setBrush(QBrush(stool))
        p.setPen(QPen(stool, 2.4))
        p.drawLine(QPointF(cx, floor - 15), QPointF(cx, floor - 4))     # 凳腿
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - 10, floor - 20, 20, 8))               # 凳面
        p.setPen(QPen(limb_c, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for dx in (-8.0, 8.0):                      # 胳膊:贴着身体垂下来
            p.drawLine(QPointF(cx + dx, floor - 34), QPointF(cx + dx * 1.1, floor - 23))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(torso_c))
        p.drawRoundedRect(QRectF(cx - 9, floor - 37, 18, 20), 5, 5)
        p.setBrush(QBrush(head_c))
        p.drawEllipse(QRectF(cx - 7.5, floor - 51, 15, 15))
