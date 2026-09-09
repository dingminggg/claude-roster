"""一个工位 = 一个成员的控制台。俯视画法:L 形隔断 + 大桌板(显示器背面 /
键盘 / 鼠标 / 刻在桌面的成员名)+ 办公椅(靠背用成员配色)+ 员工 emoji + 绿植。

屏幕光的颜色 = 运行状态(忙=蓝 / 闲=绿 / 启动中=琥珀);屏幕**闪** = 有新消息
(答完一轮 / 等你确认)。未运行不闪——没窗口就没有「在等你」这回事。

本图元只画和报事件:状态由 set_* 喂进来,不认识 peers / winman / launcher。
命中区由 r_* 一处给出,paint 和 mousePressEvent 共用同一份坐标,避免两处漂移。
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from .theme import (
    CHAIR, CHAIR_SEAT, DESK, DESK_EDGE, DESK_EDGE_OFF, DESK_OFF, DIM, FLOOR,
    FLOOR_HOVER, GEAR, HEAD, KEYS, MOUSE, NO_BG, NO_FG, OFF_OPACITY, OFF_TINT,
    PART, PART_TOP, PLANT, PLANT_OFF, PLANT_POT, TXT, YES_BG, YES_FG, mix,
)

SEAT_W, SEAT_H = 180, 112


def _font(size: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f


# 字号从不随状态变:提到模块级建一次。paint 每帧重建 QFont 要走字体匹配查找,
# 而 paint 是「每个工位 × 每次 tick/闪烁/悬停」都跑的。
FONT_NAME = _font(8, bold=True)     # 刻在桌面上的成员名
FONT_SPEAKER = _font(9)             # 朗读小喇叭(名字右边)
FONT_EMOJI = _font(11)              # 椅子上的员工
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


# 浅底上的配色:胶囊用实色底 + 白字(浅底浅字看不清),屏幕光取更饱和的一档,
# 否则洒在浅木色桌面上等于没有。
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

    clicked = Signal(str)               # 点桌面:置前该成员的控制台
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
        return QRectF(96, 84, 56, 22)

    def r_yes(self) -> QRectF:
        return QRectF(96, 84, 27, 22)

    def r_no(self) -> QRectF:
        return QRectF(125, 84, 27, 22)

    def r_picker(self) -> QRectF:
        return QRectF(94, 64, 80, 18)

    def r_speaker(self) -> QRectF:
        return QRectF(162, 20, 16, 20)

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
        # 浅底上不能用 lighter() 表示「更亮」——那只会变淡、更看不见。
        # 闪的半拍改成:光晕加浓 + 整个工位地面染一层状态色。

        # 工位地面(部门地毯在底下透出来)
        p.setPen(Qt.PenStyle.NoPen)
        base = FLOOR_HOVER if self._hover else FLOOR
        p.setBrush(QBrush(mix(base, glow, 0.22) if flash else base))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, SEAT_W, SEAT_H), 8, 8)
        p.drawPath(path)

        # L 形隔断:上 / 左两面板,顶面亮一档制造厚度
        p.setBrush(QBrush(PART))
        p.drawRect(QRectF(0, 0, SEAT_W, 10))
        p.drawRect(QRectF(0, 0, 8, SEAT_H))
        p.setBrush(QBrush(PART_TOP))
        p.drawRect(QRectF(0, 0, SEAT_W, 3))
        p.drawRect(QRectF(0, 0, 3, SEAT_H))

        # 大桌板:横跨上半,底边加亮做厚度
        p.setBrush(QBrush(DESK if up else DESK_OFF))
        p.drawRoundedRect(QRectF(12, 14, 156, 46), 3, 3)
        p.setBrush(QBrush(DESK_EDGE if up else DESK_EDGE_OFF))
        p.drawRect(QRectF(12, 58, 156, 2))

        # 屏幕光:从显示器往下(朝员工)洒在桌面上
        if up:
            g = QLinearGradient(0, 26, 0, 58)
            c0 = QColor(glow); c0.setAlpha(230 if flash else 150)
            c1 = QColor(glow); c1.setAlpha(0)
            g.setColorAt(0.0, c0)
            g.setColorAt(1.0, c1)
            p.setBrush(QBrush(g))
            spill = QPainterPath()
            spill.moveTo(30, 28)
            spill.lineTo(62, 28)
            spill.lineTo(74, 58)
            spill.lineTo(18, 58)
            spill.closeSubpath()
            p.drawPath(spill)

        # 显示器:俯视是背壳 + 支架,屏幕下沿漏一条光
        p.setBrush(QBrush(GEAR))
        p.drawRoundedRect(QRectF(30, 18, 32, 12), 2, 2)
        p.setBrush(QBrush(glow))
        p.drawRect(QRectF(32, 29, 28, 3 if flash else 2))
        p.setBrush(QBrush(GEAR))
        p.drawRect(QRectF(44, 30, 4, 4))

        # 键盘 + 鼠标:落在桌面上
        p.setBrush(QBrush(KEYS))
        p.drawRoundedRect(QRectF(28, 42, 34, 10), 2, 2)
        p.setBrush(QBrush(MOUSE))
        p.drawEllipse(QRectF(66, 43, 6, 8))

        # 成员名:直接刻在桌面右半边(不再套一张白工牌——身份已经由椅子靠背的
        # 成员配色带着了,再加一张浅色卡只是在浅底上多堆一层)
        p.setFont(FONT_NAME)
        p.setPen(QPen(TXT if up else DIM))
        p.drawText(QRectF(94, 20, 68, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   _elide(self.name, 11))

        # 朗读中:名字右侧一个小喇叭,点它停播
        if up and self._speaking:
            p.setFont(FONT_SPEAKER)
            p.setPen(QPen(TXT))
            p.drawText(self.r_speaker(), Qt.AlignmentFlag.AlignCenter, "🔊")

        # 办公椅(俯视):靠背朝下,靠背用成员配色
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(CHAIR))
        p.drawRoundedRect(QRectF(24, 70, 5, 16), 2, 2)
        p.drawRoundedRect(QRectF(53, 70, 5, 16), 2, 2)
        p.setBrush(QBrush(CHAIR_SEAT))
        p.drawRoundedRect(QRectF(28, 66, 26, 26), 7, 7)
        p.setBrush(QBrush(self.color if up else OFF_TINT))
        p.drawRoundedRect(QRectF(25, 90, 32, 9), 4, 4)
        p.setBrush(QBrush(HEAD))
        p.drawEllipse(QRectF(32, 68, 22, 22))
        p.setFont(FONT_EMOJI)
        p.setPen(QPen(TXT))
        p.drawText(QRectF(32, 68, 22, 22), Qt.AlignmentFlag.AlignCenter, self.emoji)

        # 绿植:右下角
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(PLANT_POT))
        p.drawRoundedRect(QRectF(160, 94, 12, 10), 2, 2)
        p.setBrush(QBrush(PLANT if up else PLANT_OFF))
        p.drawEllipse(QRectF(158, 84, 16, 14))

        # 右下:状态胶囊 / 会话行 / 启动键
        if up:
            p.setFont(FONT_PILL)
            p.setBrush(QBrush(QColor(st.pill_bg)))
            p.drawRoundedRect(QRectF(96, 64, 56, 20), 10, 10)
            p.setPen(QPen(QColor(st.pill_fg)))
            p.drawText(QRectF(96, 64, 56, 20),
                       Qt.AlignmentFlag.AlignCenter, st.label)
            p.setFont(FONT_SUB)
            p.setPen(QPen(DIM))
            p.drawText(QRectF(94, 86, 62, 18),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       _elide(self._title, 9))
        else:
            p.setFont(FONT_SUB)
            p.setPen(QPen(DIM))
            p.drawText(self.r_picker(),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "▾ " + _elide(self._sub, 12))
            p.setFont(FONT_PILL)
            p.setPen(Qt.PenStyle.NoPen)
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
            # 落在桌面上会被当成「点工位」把控制台最大化。
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
        super().mousePressEvent(e)      # 桌面空白 = 拖动

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            e.ignore()
            return
        super().mouseReleaseEvent(e)
        # 只有真挪过才算「拖完了」。按在启动键/确认/会话行上的那些点击压根不进
        # 这个分支(它们在 press 里就 return 了),但普通点桌面也会走到这儿——
        # 不判断就会变成「点一下工位写一次盘」。
        start = self._press_pos
        self._press_pos = None
        if start is not None and start != self.pos():
            self.moved.emit(self.name)
