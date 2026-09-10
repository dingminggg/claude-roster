"""一个工位 = 一个成员的控制台。3/4 斜视画法,从**人的背后**看过去:

    名字 → 桌子(梯形桌面 + 前沿板厚 + 两条腿)→ 显示器(屏幕朝下,正对着座位)
         → 椅子和人(在桌子前面,我们看到的是后脑勺和椅背)→ 底部一行状态

人坐桌子前、屏幕对着人,这个朝向才对;之前把人摆在桌子后面,等于让他盯着显示器
背面,看着别扭。**颜色只给两样**:屏幕(=运行状态)和人(=成员配色),其余全是
白模,场景才不花。没上班就是**空椅子 + 黑屏**。

**工位上没有任何按钮**:启动、选会话、复制地址那些全在右键菜单里(见 view.py)。
工位本身只有两件事——左键点它把控制台弹到眼前,拖它换位置。

本图元只画和报事件:状态由 set_* 喂进来,不认识 peers / winman / launcher。
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from ..layout import SEAT_H, SEAT_W
from .theme import (
    BEZEL, CHAIR, CHAIR_DARK, DESK_FRONT, DESK_FRONT_OFF, DESK_LEG, DESK_TOP,
    DESK_TOP_OFF, DIM, HEAD, MUG, NO_BG, NO_FG, OFF_OPACITY, SCREEN_OFF,
    SHADOW, SHADOW_HARD, TXT, YES_BG, YES_FG,
)


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


# 字号从不随状态变:提到模块级建一次。paint 每帧重建 QFont 要走字体匹配查找,
# 而 paint 是「每个工位 × 每次 tick/闪烁/悬停」都跑的。
FONT_NAME = _font(9, bold=True)     # 浮在头顶的成员名
FONT_SPEAKER = _font(9)             # 朗读小喇叭
FONT_EMOJI = _font(12)              # 脑袋上的 emoji
FONT_SUB = _font(8)                 # 会话行 / 控制台标题


# 「起来了」的状态:明暗、手型、屏幕闪统一按它判断,别散着写 == "running"
UP_STATES = ("running", "busy", "idle")


@dataclass(frozen=True)
class _Style:
    label: str      # 只出现在 tooltip 里(画面上不写状态文字)
    glow: str       # 屏幕颜色 —— 这才是状态的表达方式


STATE_STYLE = {
    "down":      _Style("未上班", "#c9ced6"),
    "launching": _Style("启动中", "#f0a92e"),
    "busy":      _Style("忙碌中", "#3b82f6"),
    "idle":      _Style("空闲",   "#22c55e"),
    "running":   _Style("运行中", "#22c55e"),
}


def _elide(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class SeatItem(QGraphicsObject):
    """一个工位。QGraphicsObject(而非 QGraphicsItem)是为了能发信号。"""

    clicked = Signal(str)               # 点工位:置前该成员的控制台
    speaker_clicked = Signal(str)       # 点 🔊:停止朗读
    moved = Signal(str)                 # 拖完:该存盘了

    def __init__(self, member):
        super().__init__()
        self.name = member.name
        self.emoji = member.emoji
        self.color = QColor(member.color)
        self._state = "down"
        self._msg = False
        self._blink = True
        self._speaking = False
        self._title = ""
        self._sub = "新会话"
        self._hover = False
        self._press_pos = None          # 按下时的位置,用来判断松手时是否真挪过
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

    # ---------- 状态入口(由 OfficeWindow 转发 main 的 tick) ----------
    def set_run_state(self, state: str) -> None:
        self._state = state if state in STATE_STYLE else "running"
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.is_up()
                       else Qt.CursorShape.ArrowCursor)
        # 状态本身靠屏幕颜色表达,画面上不写字;文字版挂 tooltip,悬停查得到
        self.setToolTip(f"{self.name} · {self.status_text()}")
        self.update()

    def set_message(self, on: bool) -> None:
        self._msg = bool(on)
        self.update()

    def set_blink(self, on: bool) -> None:
        self._blink = bool(on)
        if self.is_flashing() or self._msg:
            self.update()

    def set_speaking(self, on: bool) -> None:
        self._speaking = bool(on)
        self.update()

    def set_title(self, text: str) -> None:
        self._title = text or ""
        self.update()

    def set_subtitle(self, text: str) -> None:
        """未运行时显示的「上次会话 / 新会话」。"""
        self._sub = text or "新会话"
        self.update()

    # ---------- 查询(测试与绘制共用) ----------
    def is_up(self) -> bool:
        return self._state in UP_STATES

    def status_text(self) -> str:
        return STATE_STYLE[self._state].label

    def is_flashing(self) -> bool:
        return self.is_up() and self._msg and self._blink

    # ---------- 命中区 ----------
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, SEAT_W, SEAT_H)

    def r_speaker(self) -> QRectF:
        return QRectF(172, 0, 22, 16)

    def hit(self, pos: QPointF) -> str:
        """局部坐标 → "speaker" / "seat"。

        工位上只剩这一个可点的小东西(朗读中的喇叭);启动、选会话那些操作
        全在右键菜单里,所以别的地方一律当「点工位」。
        """
        if self.is_up() and self._speaking and self.r_speaker().contains(pos):
            return "speaker"
        return "seat"

    # ---------- 绘制 ----------
    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        up = self.is_up()
        st = STATE_STYLE[self._state]
        p.setOpacity(1.0 if up else OFF_OPACITY)
        flash = self.is_flashing()
        glow = QColor(st.glow)
        p.setPen(Qt.PenStyle.NoPen)

        # 有新消息:整张工位罩一层状态色光晕。白模场景里这比「把屏幕调亮」显眼得多
        if flash:
            halo = QColor(glow)
            halo.setAlpha(52)
            p.setBrush(QBrush(halo))
            p.drawRoundedRect(QRectF(6, 10, SEAT_W - 12, SEAT_H - 16), 14, 14)
        elif self._hover:
            p.setBrush(QBrush(QColor(255, 255, 255, 170)))
            p.drawRoundedRect(QRectF(6, 10, SEAT_W - 12, SEAT_H - 16), 14, 14)

        # 桌子:先画(在最后面)。梯形桌面(近大远小)+ 前沿板厚 + 两条腿
        p.setBrush(QBrush(SHADOW_HARD))
        p.drawPolygon(QPolygonF([QPointF(36, 34), QPointF(166, 34),
                                 QPointF(178, 62), QPointF(24, 62)]))
        p.setBrush(QBrush(DESK_TOP if up else DESK_TOP_OFF))
        p.drawPolygon(QPolygonF([QPointF(34, 30), QPointF(164, 30),
                                 QPointF(176, 58), QPointF(22, 58)]))
        p.setBrush(QBrush(DESK_FRONT if up else DESK_FRONT_OFF))
        p.drawPolygon(QPolygonF([QPointF(22, 58), QPointF(176, 58),
                                 QPointF(176, 64), QPointF(22, 64)]))
        p.setBrush(QBrush(DESK_LEG))
        p.drawRect(QRectF(30, 64, 6, 22))
        p.drawRect(QRectF(162, 64, 6, 22))

        # 显示器:摆在桌面中间偏后,**屏幕朝下正对着座位**(也就是朝我们)
        p.setBrush(QBrush(SHADOW))
        p.drawRoundedRect(QRectF(64, 16, 54, 32), 3, 3)
        p.setBrush(QBrush(BEZEL))
        p.drawRoundedRect(QRectF(62, 12, 54, 32), 3, 3)
        p.setBrush(QBrush(glow if up else SCREEN_OFF))
        p.drawRoundedRect(QRectF(64, 14, 50, 26), 2, 2)
        if up:
            p.setBrush(QBrush(QColor(255, 255, 255, 145)))
            for i, wpx in enumerate((32, 20, 36)):
                p.drawRect(QRectF(68, 19 + i * 6, wpx, 2))
        p.setBrush(QBrush(BEZEL))
        p.drawRect(QRectF(84, 44, 10, 4))                   # 支架
        p.drawRoundedRect(QRectF(78, 47, 22, 3), 1.5, 1.5)  # 底座
        p.setBrush(QBrush(MUG))
        p.drawRoundedRect(QRectF(140, 42, 12, 12), 3, 3)    # 杯子,桌面别空着

        # 椅子和人:在桌子**前面**(下方),我们看到的是后脑勺和椅背
        p.setBrush(QBrush(SHADOW))
        p.drawEllipse(QRectF(70, 128, 60, 16))              # 落地影
        if up:
            # 先画人,再用椅背盖住身体——从背后看就是这个遮挡关系
            p.setBrush(QBrush(self.color))
            p.drawRoundedRect(QRectF(82, 86, 36, 34), 14, 14)
            p.setBrush(QBrush(HEAD))
            p.drawEllipse(QRectF(86, 68, 28, 28))           # 后脑勺
            p.setFont(FONT_EMOJI)
            p.setPen(QPen(TXT))
            p.drawText(QRectF(86, 68, 28, 28),
                       Qt.AlignmentFlag.AlignCenter, self.emoji)
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(CHAIR_DARK))
        p.drawRoundedRect(QRectF(76, 96, 48, 34), 10, 10)   # 椅背(朝着我们)
        p.setBrush(QBrush(CHAIR))
        p.drawRoundedRect(QRectF(82, 102, 36, 20), 7, 7)    # 椅背中间那块软垫
        p.setBrush(QBrush(CHAIR_DARK))
        p.drawRect(QRectF(98, 128, 4, 8))                   # 气杆

        # 名字:工位最上面一行
        p.setFont(FONT_NAME)
        p.setPen(QPen(TXT if up else DIM))
        p.drawText(QRectF(0, 0, SEAT_W, 14),
                   Qt.AlignmentFlag.AlignCenter, _elide(self.name, 14))

        # 朗读中:名字右边一个小喇叭,点它停播
        if up and self._speaking:
            p.setFont(FONT_SPEAKER)
            p.setPen(QPen(TXT))
            p.drawText(self.r_speaker(), Qt.AlignmentFlag.AlignCenter, "🔊")
        p.setPen(Qt.PenStyle.NoPen)

        # 底部一行:只有控制台标题(没上班时是上次会话)。
        # **状态不写字**——忙/闲/启动中全靠屏幕颜色表达,底下再挂个胶囊是重复。
        # 文字版状态留在 tooltip 里(见 set_run_state),悬停查得到。
        p.setFont(FONT_SUB)
        p.setPen(QPen(DIM))
        p.drawText(QRectF(14, 144, 172, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter,
                   _elide(self._title if up else self._sub, 24))

    # ---------- 交互 ----------
    def hoverEnterEvent(self, e):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            # 右键只该弹菜单,不挡掉会被当成「点工位」把控制台最大化。
            e.ignore()
            return
        if self.hit(e.pos()) == "speaker":
            self.speaker_clicked.emit(self.name)
            e.accept(); return
        if self.is_up():
            self.clicked.emit(self.name)
        self._press_pos = self.pos()    # 记下起点,松手时判断到底有没有挪
        super().mousePressEvent(e)      # 空白处 = 拖动

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        super().mouseReleaseEvent(e)
        # 只有真挪过才算「拖完了」:不判断的话,点一下工位就写一次盘。
        start = self._press_pos
        self._press_pos = None
        if start is not None and start != self.pos():
            self.moved.emit(self.name)
