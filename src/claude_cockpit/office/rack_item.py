"""机房里的三样东西:机柜(`RackItem`)、运维工位(`OpsDeskItem`)、运维本人(`OpsItem`)。

**一台机柜装下所有服务**,一层 1U = 一个服务(层上印服务名、右端一颗灯)——
一个服务一台柜子的话,几台一模一样的黑箱子摆成一排,得凑近看名字才知道谁是谁;
挤在一台柜子里反而一眼扫得完,也更像真机房。

状态语义和工位「屏幕色 = 运行状态」完全一致:绿 = 端口听得到、灭 = 没在跑、
琥珀半拍一闪 = 端口在但不搭理你。画面上不写状态文字,文字版在悬停提示里。

运维小人**有自己的工位**:平时坐在那儿玩手机,每隔一阵起身走到机柜前看一眼再
走回来;有服务不绿就一直站在柜子前不回座。他不是员工——没有控制台、不上下班,
所以用的是自己这套图元,不是 SeatItem。

**只读**:点它不启停服务(要管理员权限,而且看板上误点一下就把 MySQL 关了)。
"""
from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import SEAT_H, SEAT_W
from ..services import DOWN, STUCK, UP
from . import person
from .iso import ISO_FX, ISO_TEXT_FX, ISO_TOP
from .iso import on_at as _on
from .iso import pt_at as _pt
from .iso import quad_at as _quad
from .theme import (
    BEZEL, CHAIR, CHAIR_DARK, CHAIR_LEG, DESK_FRONT, DESK_LEG, DESK_SHADE,
    DESK_TOP, LED_DOWN, LED_STUCK, LED_UP, RACK, RACK_NAME, RACK_SIDE,
    RACK_SLOT, RACK_TOP, SHADOW, mix,
)

# ---------- 机柜 ----------
# 房间尺寸(x 宽 / y 深 / z 高)。高瘦——机柜就该比桌子高、比桌子窄,尺寸本身
# 就是「这不是办公家具」的第一个信号。
RX, RY, RZ = 27.0, 17.0, 78.0
ROX, ROY = SEAT_W / 2 - RX + 4, SEAT_H - 22.0     # 投影原点:柜子摆在格子中间偏下

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


# ---------- 运维工位 ----------
# 比员工工位小一圈:运维只有一张桌子和一把椅子,没有显示器/音响/文件那一套
# (他没有控制台,画上去就是在暗示「这儿能点」)。
DX, DY = 30.0, 15.0             # 桌面(长边对着人,同员工的桌子)
DOX, DOY = 62.0, 58.0           # 投影原点
# 椅子在桌子**正前方中间**:偏到一端去就读成「他坐在桌子旁边」而不是「坐在桌前」。
# 「前面」在等距下要 x、y 一起加——只加 y 是往左前走(杯子那次踩过)。
CHX, CHY = DX / 2 + 5.0, DY + 11.0


class OpsDeskItem(QGraphicsObject):
    """运维的工位:一张小桌 + 一把椅子。人是另一个图元(他要走来走去)。"""

    moved = Signal(str)

    def __init__(self):
        super().__init__()
        self.name = "opsdesk"
        self._press_pos = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setToolTip("运维工位")

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, SEAT_W, SEAT_H)

    def seat_point(self) -> QPointF:
        """椅子上那一点(运维坐着时人画在这儿)。"""
        return _pt(DOX, DOY, CHX, CHY)

    def paint(self, p: QPainter, opt, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(SHADOW))
        p.drawEllipse(_pt(DOX, DOY, DX / 2, DY / 2), DX * 0.95, DX * 0.45)

        p.setBrush(QBrush(DESK_TOP))            # 桌面
        p.drawPolygon(_quad(DOX, DOY, (0, 0, 14), (DX, 0, 14),
                            (DX, DY, 14), (0, DY, 14)))
        p.setBrush(QBrush(DESK_FRONT))          # 两条朝镜头的桌沿板厚
        p.drawPolygon(_quad(DOX, DOY, (0, DY, 14), (DX, DY, 14),
                            (DX, DY, 11.5), (0, DY, 11.5)))
        p.drawPolygon(_quad(DOX, DOY, (DX, 0, 14), (DX, DY, 14),
                            (DX, DY, 11.5), (DX, 0, 11.5)))
        p.setBrush(QBrush(DESK_SHADE))          # 两端的侧板腿(朝镜头那一面)
        for x0 in (1.5, DX - 5.0):
            p.drawPolygon(_quad(DOX, DOY, (x0, DY, 11.5), (x0 + 3.5, DY, 11.5),
                                (x0 + 3.5, DY, 0), (x0, DY, 0)))
        p.setBrush(QBrush(DESK_LEG))            # 右端那块板的侧面:盒子才立得起来
        for x0 in (1.5, DX - 5.0):
            p.drawPolygon(_quad(DOX, DOY, (x0 + 3.5, DY - 3.5, 11.5),
                                (x0 + 3.5, DY, 11.5),
                                (x0 + 3.5, DY, 0), (x0 + 3.5, DY - 3.5, 0)))
        self._chair(p)

    def _chair(self, p: QPainter) -> None:
        """五爪转椅。椅背落在人的左下方(房间坐标 +y,人背后那一侧),一眼看出
        椅子朝着桌子——和员工工位同一条规矩。"""
        c = _pt(DOX, DOY, CHX, CHY)
        p.setPen(QPen(CHAIR_LEG, 2.6, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        for dx, dy in ((-11, 5), (11, 5), (0, 8), (-8, -3), (8, -3)):
            p.drawLine(c, QPointF(c.x() + dx, c.y() + dy))
        p.setPen(QPen(CHAIR_LEG, 3.0))
        p.drawLine(QPointF(c.x(), c.y()), QPointF(c.x(), c.y() - 9))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(CHAIR))               # 座垫
        p.save()
        _on(p, ISO_TOP, DOX, DOY, CHX - 5.5, CHY - 5.5, 10)
        p.drawRoundedRect(QRectF(0, 0, 11, 11), 3, 3)
        p.restore()
        p.setBrush(QBrush(CHAIR_DARK))          # 椅背:画在 ISO_FX 面上才读得出朝向
        p.save()
        _on(p, ISO_FX, DOX, DOY, CHX - 5.0, CHY + 4.0, 26)
        p.drawRoundedRect(QRectF(0, 0, 10, 14), 3, 3)
        p.restore()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        self._press_pos = self.pos()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        if self._press_pos is not None and self.pos() != self._press_pos:
            self.moved.emit(self.name)
        self._press_pos = None


# ---------- 运维本人 ----------
STEP_MS = 60                    # 走路一帧
WALK_MS = 2200                  # 单程走多久(固定时长,不按距离算——同送信的小人)
LOOK_MS = 5000                  # 在柜子前看多久
PATROL_MS = (45000, 90000)      # 隔多久去巡一次(随机,免得像整点报时一样准)

DESK, TO_RACK, AT_RACK, TO_DESK = "desk", "to_rack", "at_rack", "to_desk"


class OpsItem(QGraphicsObject):
    """运维本人。平时在工位坐着玩手机,隔一阵去机柜前看一眼;有服务不绿就一直
    站在柜子前不回座(那是余光信号,看出是哪一层挂了还得靠柜灯)。

    **自带定时器**,不挂进 OfficeWindow 的 tick——那条主循环已经管着轮询/闪烁/
    音浪三件事了(同 WalkerItem 的口径)。
    """

    W, H = 52, 70
    COLOR = "#6f7b8d"           # 和椅子同色系:他是机房的摆设,不该抢员工的配色

    def __init__(self):
        super().__init__()
        self.color = QColor(self.COLOR)
        self._phase = DESK
        self._alarm = False
        self._t = 0.0                       # 走路进度 0~1
        self._from = QPointF()
        self._to = QPointF()
        self._desk = QPointF()
        self._rack = QPointF()
        self._lane = 0.0                    # 过道的 y:绕开桌子和柜子,不穿家具
        self._step = QTimer(self)
        self._step.setInterval(STEP_MS)
        self._step.timeout.connect(self._tick)
        self._wait = QTimer(self)
        self._wait.setSingleShot(True)
        self._wait.timeout.connect(self._go)
        self.setToolTip("运维:平时在工位,隔一阵去机柜前看一眼;"
                        "有服务挂了就一直站在柜子前")

    # ---------- 落位 ----------
    def set_points(self, desk: QPointF, rack: QPointF, lane: float) -> None:
        """告诉他工位和机柜在哪(都是机房区里的坐标),以及走哪条过道。

        **由 OfficeWindow 喂进来**:这两样是别的图元的位置,图元之间不该互相认识;
        桌子或柜子被拖走了,重喂一次就行。
        """
        self._desk, self._rack, self._lane = desk, rack, lane
        if self._phase in (DESK, AT_RACK):
            self._move_to(self._anchor())
        self._arm()

    def _anchor(self) -> QPointF:
        return self._rack if self._phase in (AT_RACK, TO_RACK) else self._desk

    def _move_to(self, p: QPointF) -> None:
        """把脚底那一点摆到 p(图元的原点在左上角,所以要减掉半宽和身高)。"""
        self.setPos(p.x() - self.W / 2, p.y() - (self.H - 8))

    # ---------- 状态 ----------
    def set_alarm(self, on: bool) -> None:
        """有服务不绿 → 立刻起身去柜子前,并且一直站着不回座。"""
        on = bool(on)
        if self._alarm == on:
            return
        self._alarm = on
        if on and self._phase == DESK:
            self._start(TO_RACK)
        elif not on and self._phase == AT_RACK:
            self._wait.start(LOOK_MS)       # 修好了:再看一会儿就回座
        self.update()

    def is_alarmed(self) -> bool:
        return self._alarm

    def phase(self) -> str:
        return self._phase

    # ---------- 巡检 ----------
    def _arm(self) -> None:
        """排下一趟巡检。只在工位待着时才排——走着/站着的时候排等于催自己。"""
        if self._phase == DESK and not self._wait.isActive():
            self._wait.start(random.randint(*PATROL_MS))

    def _go(self) -> None:
        """等够了:该动身了。"""
        if self._phase == DESK:
            self._start(TO_RACK)
        elif self._phase == AT_RACK:
            if self._alarm:                 # 还没修好就继续站着
                self._wait.start(LOOK_MS)
            else:
                self._start(TO_DESK)

    def _start(self, phase: str) -> None:
        self._wait.stop()
        self._from = self._anchor()
        self._phase = phase
        self._to = self._rack if phase == TO_RACK else self._desk
        self._t = 0.0
        self._step.start()

    def _tick(self) -> None:
        # 不在走路就直接回:stop() 之后可能还有一个已经排进队列的 timeout,
        # 不挡住的话「站在柜子前」会被它顶成「回到工位」——人瞬移(踩过)。
        if self._phase not in (TO_RACK, TO_DESK):
            return
        self._t += STEP_MS / WALK_MS
        if self._t >= 1.0:
            self._t = 1.0
            self._step.stop()
            self._phase = AT_RACK if self._phase == TO_RACK else DESK
            if self._phase == AT_RACK:
                self._wait.start(LOOK_MS)
            else:
                self._arm()
        self._move_to(self._at(self._t))
        self.update()

    def _at(self, t: float) -> QPointF:
        """走**折线**不走直线:直连会从桌面上横穿过去。先退到过道,横着走,再拐进去。
        取点按**路程**比例、不按段数,不然长段飞快、短段磨蹭(同送信的小人)。"""
        a, b = self._from, self._to
        pts = [a, QPointF(a.x(), self._lane), QPointF(b.x(), self._lane), b]
        segs = [(pts[i], pts[i + 1]) for i in range(3)]
        lens = [max(1e-6, ((q.x() - p.x()) ** 2 + (q.y() - p.y()) ** 2) ** 0.5)
                for p, q in segs]
        total = sum(lens)
        want = t * total
        for (p, q), ln in zip(segs, lens):
            if want <= ln:
                k = want / ln
                return QPointF(p.x() + (q.x() - p.x()) * k,
                               p.y() + (q.y() - p.y()) * k)
            want -= ln
        return b

    # ---------- 画 ----------
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.W, self.H)

    def paint(self, p: QPainter, opt, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        cx, floor = self.W / 2, self.H - 8
        if self._phase == DESK:
            self._sit(p, cx, floor)
            return
        walking = self._phase in (TO_RACK, TO_DESK)
        bob = 2.0 if walking and int(self._t * 14) % 2 else 0.0
        person.draw_standing(p, self.color, cx, floor, bob=bob)

    def _sit(self, p: QPainter, cx: float, floor: float) -> None:
        """坐在工位上**玩手机**:两只手举到胸前,手里一小块亮的。

        **没有复用 person.draw_sitting**:那一份是为员工工位定制的——胳膊伸向键盘、
        躯干要和椅背对齐。这里人要低头看手机,胳膊的去处完全不同,照搬过来就是
        两根指向天的棍子(踩过)。全用屏幕坐标(同站姿的口径)。
        """
        head_c, torso_c, limb_c = person.skin(self.color)
        p.setBrush(QBrush(torso_c))
        p.drawRoundedRect(QRectF(cx - 9, floor - 34, 18, 20), 5, 5)      # 躯干
        p.setPen(QPen(limb_c, 3.0, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for dx in (-7.5, 7.5):          # 胳膊:从肩折到胸前(肘要折,不然是两根棍)
            p.drawPolyline(QPolygonF([QPointF(cx + dx, floor - 31),
                                      QPointF(cx + dx * 1.25, floor - 24),
                                      QPointF(cx + dx * 0.45, floor - 26)]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(head_c))
        p.drawEllipse(QRectF(cx - 7.5, floor - 48, 15, 15))              # 头
        p.setBrush(QBrush(QColor("#dfe7f2")))                            # 手机
        p.drawRoundedRect(QRectF(cx - 3.2, floor - 29.5, 6.4, 9.0), 1.4, 1.4)
