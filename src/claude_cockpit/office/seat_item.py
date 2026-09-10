"""一个工位 = 一个成员的控制台。3/4 斜视画法(不是正俯视):

    名字浮在头顶 → 椅子 → 人(肩膀用成员配色,脑袋上压 emoji)→ 桌子(梯形桌面 +
    前沿板厚 + 两条桌腿)→ 显示器(屏幕朝观察者)→ 桌下一条信息条

正俯视画出来所有东西都像贴纸,而且显示器只能画背面、认不出是电脑;斜视才有
「有人坐在那儿上班」的样子。**颜色只给两样**:屏幕(=运行状态)和人(=成员配色),
其余全是白模,场景才不花。

没上班就是**空椅子 + 黑屏**——比「整张工位灰掉」直觉得多。

本图元只画和报事件:状态由 set_* 喂进来,不认识 peers / winman / launcher。
命中区由 r_* 一处给出,paint 和 mousePressEvent 共用同一份坐标,避免两处漂移。
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
FONT_PILL = _font(8, bold=True)     # 状态胶囊 / 启动键
FONT_SUB = _font(8)                 # 会话行 / 控制台标题


# 「起来了」的状态:明暗、手型、屏幕闪统一按它判断,别散着写 == "running"
UP_STATES = ("running", "busy", "idle")


@dataclass(frozen=True)
class _Style:
    label: str
    pill_bg: str
    pill_fg: str
    glow: str


# 屏幕色 = 状态色;胶囊用实色底 + 白字(浅底浅字看不清)。
STATE_STYLE = {
    "down":      _Style("启动",   "#eef0f3", "#4b5563", "#c9ced6"),
    "launching": _Style("启动中", "#c2760a", "#ffffff", "#f0a92e"),
    "busy":      _Style("忙碌中", "#2563eb", "#ffffff", "#3b82f6"),
    "idle":      _Style("空闲",   "#15803d", "#ffffff", "#22c55e"),
    "running":   _Style("运行中", "#15803d", "#ffffff", "#22c55e"),
}


def _elide(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class SeatItem(QGraphicsObject):
    """一个工位。QGraphicsObject(而非 QGraphicsItem)是为了能发信号。"""

    clicked = Signal(str)               # 点工位:置前该成员的控制台
    start_clicked = Signal(str)         # 点「启动」:展开内联确认
    confirmed = Signal(str)             # 点 ✓:真的拉起
    picker_clicked = Signal(str)        # 点会话行:弹会话下拉
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
        self._confirm = False
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
        self._confirm = self._confirm and not self.is_up()
        self.update()

    def set_message(self, on: bool) -> None:
        self._msg = bool(on)
        self.update()

    def set_blink(self, on: bool) -> None:
        self._blink = bool(on)
        if self.is_flashing() or self._msg:
            self.update()

    def set_confirm(self, on: bool) -> None:
        self._confirm = bool(on)
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

    def r_go(self) -> QRectF:
        return QRectF(22, 142, 56, 20)

    def r_yes(self) -> QRectF:
        return QRectF(22, 142, 27, 20)

    def r_no(self) -> QRectF:
        return QRectF(51, 142, 27, 20)

    def r_picker(self) -> QRectF:
        return QRectF(84, 142, 110, 20)

    def r_speaker(self) -> QRectF:
        return QRectF(172, 0, 22, 16)

    def hit(self, pos: QPointF) -> str:
        """局部坐标 → "go"/"yes"/"no"/"picker"/"speaker"/"seat"。"""
        if self.is_up():
            if self._speaking and self.r_speaker().contains(pos):
                return "speaker"
            return "seat"
        if self._confirm:
            if self.r_yes().contains(pos):
                return "yes"
            if self.r_no().contains(pos):
                return "no"
        elif self.r_go().contains(pos):
            return "go"
        if self.r_picker().contains(pos):
            return "picker"
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

        # 地面投影:桌椅合起来的一大片软影,是立体感的主要来源
        p.setBrush(QBrush(SHADOW))
        p.drawPolygon(QPolygonF([QPointF(28, 108), QPointF(150, 108),
                                 QPointF(196, 142), QPointF(74, 142)]))

        # 椅子(在桌子后面,先画):椅背 + 座垫 + 气杆
        p.setBrush(QBrush(CHAIR_DARK))
        p.drawRoundedRect(QRectF(78, 20, 46, 44), 10, 10)
        p.setBrush(QBrush(CHAIR))
        p.drawRoundedRect(QRectF(76, 58, 50, 16), 6, 6)
        p.setBrush(QBrush(CHAIR_DARK))
        p.drawRect(QRectF(99, 72, 4, 10))

        # 人:肩膀用成员配色,脑袋是白的、上面压 emoji。没上班就不画人(空椅子)
        if up:
            p.setBrush(QBrush(self.color))
            p.drawRoundedRect(QRectF(84, 42, 38, 36), 14, 14)
            p.setBrush(QBrush(HEAD))
            p.drawEllipse(QRectF(88, 18, 28, 28))
            p.setFont(FONT_EMOJI)
            p.setPen(QPen(TXT))
            p.drawText(QRectF(88, 18, 28, 28),
                       Qt.AlignmentFlag.AlignCenter, self.emoji)
            p.setPen(Qt.PenStyle.NoPen)

        # 桌子:梯形桌面(近大远小)+ 前沿板厚 + 两条腿
        p.setBrush(QBrush(SHADOW_HARD))
        p.drawPolygon(QPolygonF([QPointF(36, 78), QPointF(166, 78),
                                 QPointF(178, 104), QPointF(24, 104)]))
        p.setBrush(QBrush(DESK_TOP if up else DESK_TOP_OFF))
        p.drawPolygon(QPolygonF([QPointF(34, 74), QPointF(164, 74),
                                 QPointF(176, 100), QPointF(22, 100)]))
        p.setBrush(QBrush(DESK_FRONT if up else DESK_FRONT_OFF))
        p.drawPolygon(QPolygonF([QPointF(22, 100), QPointF(176, 100),
                                 QPointF(176, 106), QPointF(22, 106)]))
        p.setBrush(QBrush(DESK_LEG))
        p.drawRect(QRectF(30, 106, 6, 26))
        p.drawRect(QRectF(162, 106, 6, 26))

        # 显示器:屏幕朝观察者,亮起来就是状态色。摆在桌面左侧,别挡着人
        p.setBrush(QBrush(SHADOW))
        p.drawRoundedRect(QRectF(32, 58, 44, 28), 3, 3)
        p.setBrush(QBrush(BEZEL))
        p.drawRoundedRect(QRectF(30, 54, 44, 28), 3, 3)
        p.setBrush(QBrush(glow if up else SCREEN_OFF))
        p.drawRoundedRect(QRectF(32, 56, 40, 22), 2, 2)
        if up:
            p.setBrush(QBrush(QColor(255, 255, 255, 145)))
            for i, wpx in enumerate((26, 16, 30)):
                p.drawRect(QRectF(35, 60 + i * 5, wpx, 2))
        p.setBrush(QBrush(BEZEL))
        p.drawRect(QRectF(48, 82, 8, 3))                    # 支架
        p.drawRoundedRect(QRectF(42, 85, 20, 3), 1.5, 1.5)  # 底座
        p.setBrush(QBrush(MUG))
        p.drawRoundedRect(QRectF(140, 78, 12, 12), 3, 3)    # 杯子,桌面别空着

        # 名字:浮在头顶
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

        # 桌下信息条:上班了 = 状态胶囊 + 控制台标题;没上班 = 启动键 + 会话下拉
        p.setFont(FONT_PILL)
        if up:
            p.setBrush(QBrush(QColor(st.pill_bg)))
            p.drawRoundedRect(QRectF(22, 142, 56, 20), 10, 10)
            p.setPen(QPen(QColor(st.pill_fg)))
            p.drawText(QRectF(22, 142, 56, 20),
                       Qt.AlignmentFlag.AlignCenter, st.label)
            p.setFont(FONT_SUB)
            p.setPen(QPen(DIM))
            p.drawText(QRectF(84, 142, 110, 20),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       _elide(self._title, 15))
        else:
            if self._confirm:
                p.setBrush(QBrush(YES_BG))
                p.drawRoundedRect(self.r_yes(), 10, 10)
                p.setBrush(QBrush(NO_BG))
                p.drawRoundedRect(self.r_no(), 10, 10)
                p.setPen(QPen(YES_FG))
                p.drawText(self.r_yes(), Qt.AlignmentFlag.AlignCenter, "✓")
                p.setPen(QPen(NO_FG))
                p.drawText(self.r_no(), Qt.AlignmentFlag.AlignCenter, "✕")
            else:
                p.setBrush(QBrush(QColor(st.pill_bg)))
                p.drawRoundedRect(self.r_go(), 10, 10)
                p.setPen(QPen(QColor(st.pill_fg)))
                p.drawText(self.r_go(), Qt.AlignmentFlag.AlignCenter, st.label)
            p.setFont(FONT_SUB)
            p.setPen(QPen(DIM))
            p.drawText(self.r_picker(),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "▾ " + _elide(self._sub, 15))

    # ---------- 交互 ----------
    def hoverEnterEvent(self, e):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            # 右键只该弹菜单。不挡掉的话,右键落在会话行上会弹会话下拉、
            # 落在别处会被当成「点工位」把控制台最大化。
            e.ignore()
            return
        where = self.hit(e.pos())
        if where == "go":
            self.set_confirm(True)
            self.start_clicked.emit(self.name)
            e.accept(); return
        if where == "yes":
            self.set_confirm(False)
            self.confirmed.emit(self.name)
            e.accept(); return
        if where == "no":
            self.set_confirm(False)
            e.accept(); return
        if where == "picker":
            self.picker_clicked.emit(self.name)
            e.accept(); return
        if where == "speaker":
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
        # 只有真挪过才算「拖完了」。按在启动键/确认/会话行上的那些点击压根不进
        # 这个分支(它们在 press 里就 return 了),但普通点工位也会走到这儿——
        # 不判断就会变成「点一下工位写一次盘」。
        start = self._press_pos
        self._press_pos = None
        if start is not None and start != self.pos():
            self.moved.emit(self.name)
