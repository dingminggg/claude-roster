"""机房里的机柜:`RackItem`。

**一台机柜装下所有服务**,一层 1U = 一个服务(层上印服务名、右端一颗灯)——
一个服务一台柜子的话,几台一模一样的黑箱子摆成一排,得凑近看名字才知道谁是谁;
挤在一台柜子里反而一眼扫得完,也更像真机房。

状态语义和工位「屏幕色 = 运行状态」完全一致:绿 = 端口听得到、灭 = 没在跑、
琥珀半拍一闪 = 端口在但不搭理你。画面上不写状态文字,文字版在悬停提示里。

运维**是一个真员工**(`config.OPS_NAME`,机房里的固定岗位),所以他用的是标准
`SeatItem`——显示器状态屏、会话历史、上下班、点击置前全是现成的。曾经给他自绘过
一套「小桌 + 玩手机的小人」,撤了:那等于把 SeatItem 再实现一遍,还少一半功能。
巡检复用送信那套小人(`WalkerItem`),见 `office/view.py` 的 `patrol`。

**只读**:点它不启停服务(要管理员权限,而且看板上误点一下就把 MySQL 关了)。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import SEAT_H, SEAT_W
from ..services import DOWN, STUCK, UP
from .iso import ISO_FX, ISO_TEXT_FX
from .iso import on_at as _on
from .iso import pt_at as _pt
from .iso import quad_at as _quad
from .theme import (
    BEZEL, LED_DOWN, LED_STUCK, LED_UP, RACK, RACK_NAME, RACK_SIDE, RACK_SLOT,
    RACK_TOP, SHADOW, mix,
)

# ---------- 机柜 ----------
# 房间尺寸(x 宽 / y 深 / z 高)。高瘦——机柜就该比桌子高、比桌子窄,尺寸本身
# 就是「这不是办公家具」的第一个信号。
RX, RY, RZ = 27.0, 17.0, 78.0
# 投影原点。**ROY 要让整台柜子装进格子**:近角(x=RX,y=RY)的屏幕 y 是
# `ROY + RX + RY`,顶角是 `ROY - RZ`。原来 ROY=SEAT_H-22,近角顶出下沿 22px,
# 看着整台柜子沉在格子外面。
ROX, ROY = SEAT_W / 2 - RX + 4, SEAT_H - (RX + RY) - 4

SLOT_H, SLOT_GAP = 8.0, 3.4     # 一层的厚度 / 层间距(房间单位)
SLOT_Z0 = 16.0                  # 最下面那层的高度
BLANK_SLOTS = 2                 # 服务之外再画几层空位:机柜本来就有空槽,不然太满
# 层上那行字的可用长度:沿板方向 1 个房间单位 = 2.2361px(横 2、竖 1)。
# **算出来的、别写死**——改柜宽,字的地盘自动跟着变(同工位名牌那套)。
LABEL_LEN = (RX - 4.0) * 2.2361

STATE_TEXT = {UP: "运行中", DOWN: "没在跑", STUCK: "无响应"}
LED = {UP: LED_UP, DOWN: LED_DOWN, STUCK: LED_STUCK}

FONT_SLOT = QFont()
FONT_SLOT.setPointSize(6)
FONT_SLOT.setBold(True)


class RackItem(QGraphicsObject):
    """一台机柜,一层一个服务。QGraphicsObject 是为了能发信号(同 SeatItem)。"""

    moved = Signal(str)                 # 拖完:该存盘了

    def __init__(self, svcs):
        super().__init__()
        self.name = "rack"
        self.services = list(svcs)
        self._states = {s.name: DOWN for s in self.services}
        self._blink = True
        self._press_pos = None
        # 同 SeatItem:可拖但**不可选**——Qt 会把选中的可移动图元跟着父级一起拖,
        # 点过的那个会比别人多挪一倍。
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self._sync_tip()

    # ---------- 状态入口 ----------
    def set_states(self, states: dict) -> None:
        for name, st in (states or {}).items():
            if name in self._states:
                self._states[name] = st if st in LED else DOWN
        self._sync_tip()
        self.update()

    def state_of(self, name: str) -> str:
        return self._states.get(name, DOWN)

    def all_green(self) -> bool:
        return bool(self._states) and all(s == UP for s in self._states.values())

    def set_blink(self, on: bool) -> None:
        """半拍一闪的相位(由 OfficeWindow 那条 550ms 的表统一喂)。
        没有哪一层在闪就别重画。"""
        self._blink = bool(on)
        if self.is_flashing():
            self.update()

    def is_flashing(self) -> bool:
        return any(s == STUCK for s in self._states.values())

    def _sync_tip(self) -> None:
        lines = [f"{s.name}  {s.address}  "
                 f"{STATE_TEXT.get(self._states[s.name], '未知')}"
                 for s in self.services]
        self.setToolTip("机柜\n" + "\n".join(lines) if lines else "机柜(没有服务)")

    # ---------- 几何 ----------
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, SEAT_W, SEAT_H)

    def front_point(self) -> QPointF:
        """柜子正前方那块地(运维过来看柜子时站的位置)。"""
        return _pt(ROX, ROY, RX * 0.5, RY + 13.0)

    # ---------- 画 ----------
    def paint(self, p: QPainter, opt, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(SHADOW))      # 落地影子:说明这东西是立着的
        p.drawEllipse(_pt(ROX, ROY, RX / 2, RY / 2),
                      (RX + RY) * 0.6, (RX + RY) * 0.3)

        # 三个面都要画:少一面就塌成纸片(工位上的音响踩过)
        p.setBrush(QBrush(RACK_SIDE))   # x=RX 那面:侧板,深一档
        p.drawPolygon(_quad(ROX, ROY, (RX, 0, 0), (RX, RY, 0),
                            (RX, RY, RZ), (RX, 0, RZ)))
        p.setBrush(QBrush(RACK))        # y=RY 那面:柜门,层和灯都在这儿
        p.drawPolygon(_quad(ROX, ROY, (0, RY, 0), (RX, RY, 0),
                            (RX, RY, RZ), (0, RY, RZ)))
        p.setBrush(QBrush(RACK_TOP))
        p.drawPolygon(_quad(ROX, ROY, (0, 0, RZ), (RX, 0, RZ),
                            (RX, RY, RZ), (0, RY, RZ)))
        self._paint_slots(p)

    def _paint_slots(self, p: QPainter) -> None:
        """柜门上一层层的 1U 槽位。

        门开在 **y = RY 那个面**上,也就是 `ISO_FX` 平面——这个平面的横轴走房间的
        **x**、纵轴是屏幕往下。挂错成常 x 的那个面,整排灯会飞到柜子外面去(踩过)。

        服务从**上往下**排:机柜的第一台设备在顶上,空槽留在底下,和真柜子一个样。
        """
        rows = len(self.services) + BLANK_SLOTS
        top_z = SLOT_Z0 + (rows - 1) * (SLOT_H + SLOT_GAP)
        zs = [top_z - i * (SLOT_H + SLOT_GAP) for i in range(len(self.services))]

        for i in range(BLANK_SLOTS):        # 底下的空槽:深一点,一看就是没插东西
            self._slot_bar(p, SLOT_Z0 + i * (SLOT_H + SLOT_GAP),
                           mix(RACK_SLOT, BEZEL, 0.55), None)
        for svc, z in zip(self.services, zs):
            st = self._states.get(svc.name, DOWN)
            led = LED[st]
            if st == STUCK and not self._blink:
                led = mix(led, QColor("#ffffff"), 0.5)      # 异常:半拍一闪
            self._slot_bar(p, z, RACK_SLOT, led)

        # **字统一放到最后画**:每层画完就写字的话,下一层的槽位(位置更低、画在
        # 后面)会把上一层的字压掉半截(踩过)。
        p.setFont(FONT_SLOT)
        for svc, z in zip(self.services, zs):
            st = self._states.get(svc.name, DOWN)
            p.save()
            # 用 ISO_TEXT_FX,不然字被横向拉成两倍宽
            _on(p, ISO_TEXT_FX, ROX, ROY, 2.6, RY, z - SLOT_H)
            p.setPen(QPen(RACK_NAME if st != DOWN
                          else mix(RACK_NAME, RACK_SLOT, 0.5)))
            p.drawText(QRectF(0, -SLOT_H, LABEL_LEN - 12.0, SLOT_H),
                       int(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter),
                       svc.name)
            p.restore()

    def _slot_bar(self, p: QPainter, z: float, fill, led) -> None:
        """一层 1U:一条横板 + 右端一颗灯(`led` 为 None 就是空槽,不画灯)。"""
        p.save()
        _on(p, ISO_FX, ROX, ROY, 2.0, RY, z)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawRect(QRectF(0, -SLOT_H, RX - 4.0, SLOT_H))
        if led is not None:
            p.setBrush(QBrush(led))
            p.drawRect(QRectF(RX - 7.0, -SLOT_H + 1.4, 2.4, SLOT_H - 2.8))
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
