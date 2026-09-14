"""`WalkerItem`:会话之间发消息时,从发送方工位走到接收方工位、说一句、再走回去的小人。

信号来源见 `hooks/message_sent.py`(PostToolUse 匹配 SendMessage 工具)。

两个设计决定:

* **自带定时器、走完自己摘掉**。不挂进 `OfficeWindow` 的 tick——那条主循环已经管着
  轮询、闪烁、音浪三件事,再塞一样进去只会更难读;walker 是个用完即走的临时图元,
  生命周期自理最省事。
* **单程时长固定,不按距离算**。同部门的两个工位可能只隔 200px,跨部门能隔两千多,
  按速度走的话远的那趟要走十几秒、早没人看了。固定时长 = 远的走得快,读起来一样。
* **走折线,不走直线**。两点之间直着连过去会从桌面上横穿过去(人从桌子上走),
  路线由 `OfficeWindow._walk_path` 排:先退到本工位前面的过道,沿过道横着走到对方
  工位那一列,再拐进去。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from . import person
from .theme import BEZEL, PAPER, TXT

OUT_MS = 1500           # 单程
TICK_MS = 40

# 气泡:到了之后停住说话的那一下。**停多久按字数算**——一句「好了」和一段两行的
# 说明,给同样的时间要么是干等、要么根本没读完。
WAIT_MS = 900           # 没正文时只冒三个点,停这么久就够
READ_MS_PER_CHAR = 55
WAIT_MAX_MS = 4200

BUBBLE_W = 168.0        # 气泡最宽多少(再宽就盖住旁边的工位了)
BUBBLE_PAD = 6.0
BUBBLE_LINES = 3        # 最多几行,超了末行省略号
LINE_H = 12.0
TAIL_H = 6.0            # 气泡底下那个小尖

FONT_MSG = QFont()      # 模块级:paint 每帧重建 QFont 要走字体匹配查找
FONT_MSG.setPointSize(7)
_FM = QFontMetricsF(FONT_MSG)


def _break_at(line: str, nxt: str) -> tuple[str, str]:
    """一行满了要换行:返回 (这一行, 退回去接着排的那截)。

    **别把一个英文词从中间劈开**——按字符折的话 `ETL` 会排成「ET / L」,一眼就
    看出是机器折的。所以当断点正好落在一串 ASCII 词里面时,退到它前面那个空格。
    中文没这个问题(每个字都能断),所以只对 ASCII 串做这件事。
    """
    if not (line and line[-1].isascii() and line[-1].isalnum()
            and nxt.isascii() and nxt.isalnum()):
        return line, ""
    cut = line.rfind(" ")
    if cut <= 0:                    # 整行就是一个长词,劈开总比空着强
        return line, ""
    return line[:cut], line[cut + 1:]


def wrap(text: str, width: float = BUBBLE_W - BUBBLE_PAD * 2,
         lines: int = BUBBLE_LINES) -> list[str]:
    """把一句话折成最多 `lines` 行,末行放不下就省略号。

    **按字宽折、不按字数折**:中文一个字的宽度是英文的两倍,按字数折的话
    「好的我这就去改」和「ok sure」会排成完全不同的长度(工位名牌那边同一条)。
    """
    text = " ".join(str(text or "").split())
    if not text:
        return []
    out: list[str] = []
    cur = ""
    for ch in text:
        if _FM.horizontalAdvance(cur + ch) <= width:
            cur += ch
            continue
        done, carry = _break_at(cur, ch)
        out.append(done)
        cur = carry + ch
        if len(out) == lines:               # 装不下了:末行收成省略号
            last = out[-1]
            while last and _FM.horizontalAdvance(last + "…") > width:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
            return out
    if cur:
        out.append(cur)
    return out[:lines]


class WalkerItem(QGraphicsObject):
    def __init__(self, color: QColor, path: list[QPointF], text: str = ""):
        super().__init__()
        self.color = QColor(color)
        self._lines = wrap(text)
        self._wait_ms = (min(WAIT_MAX_MS, 900 + len(text) * READ_MS_PER_CHAR)
                         if self._lines else WAIT_MS)
        w = max((_FM.horizontalAdvance(ln) for ln in self._lines), default=0.0)
        self._bw = w + BUBBLE_PAD * 2 if self._lines else 26.0
        self._bh = (len(self._lines) * LINE_H + BUBBLE_PAD * 2
                    if self._lines else 14.0)
        self._path = [QPointF(q) for q in path]
        # 每段的累计长度:按**长度**在折线上取点,不按段数——不然长段走得飞快、
        # 短段磨蹭,一趟路走出好几种速度。
        self._acc = [0.0]
        for i in range(1, len(self._path)):
            d = self._path[i] - self._path[i - 1]
            self._acc.append(self._acc[-1] + (d.x() ** 2 + d.y() ** 2) ** 0.5)
        self._total = self._acc[-1] or 1.0
        self._elapsed = 0
        self._phase = "out"                 # out → wait → back → (删除)
        self.setZValue(60)                  # 走在地毯和工位上面
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setPos(self._path[0])
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(TICK_MS)

    # ---------- 动画 ----------
    def _step(self) -> None:
        self._elapsed += TICK_MS
        if self._phase == "out":
            if self._elapsed >= OUT_MS:
                self._phase, self._elapsed = "wait", 0
                self.setPos(self._path[-1])
            else:
                self.setPos(self._lerp(self._elapsed / OUT_MS))
        elif self._phase == "wait":
            if self._elapsed >= self._wait_ms:
                self._phase, self._elapsed = "back", 0
        else:
            if self._elapsed >= OUT_MS:
                self._timer.stop()
                sc = self.scene()
                if sc is not None:
                    sc.removeItem(self)
                self.deleteLater()
                return
            self.setPos(self._lerp(1.0 - self._elapsed / OUT_MS))
        self.update()

    def _lerp(self, t: float) -> QPointF:
        """按走过的**路程比例**在折线上取点。"""
        want = max(0.0, min(1.0, t)) * self._total
        for i in range(1, len(self._acc)):
            if want <= self._acc[i] or i == len(self._acc) - 1:
                seg = self._acc[i] - self._acc[i - 1]
                k = 0.0 if seg <= 0 else (want - self._acc[i - 1]) / seg
                a, b = self._path[i - 1], self._path[i]
                return QPointF(a.x() + (b.x() - a.x()) * k,
                               a.y() + (b.y() - a.y()) * k)
        return QPointF(self._path[-1])

    def is_walking(self) -> bool:
        return self._phase != "wait"

    def bob(self) -> float:
        """走路时身体上下起伏 1.5px;站着说话时不动。"""
        if not self.is_walking():
            return 0.0
        return abs(math.sin(self._elapsed / TICK_MS * 0.9)) * 1.5

    # ---------- 绘制 ----------
    def boundingRect(self) -> QRectF:
        """人 + 头顶那个气泡。气泡按正文算大小,所以包围盒也得跟着算——
        写死的话长气泡会被裁掉一块(重画区域不够)。"""
        half = max(22.0, self._bw / 2 + 2)
        top = -(56 + TAIL_H + self._bh + 4)
        return QRectF(-half, top, half * 2, -top + 6)

    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        person.draw_standing(p, self.color, 0.0, 0.0, bob=self.bob())
        if self._phase == "wait":           # 到了就冒个说话气泡
            self._bubble(p)

    def _bubble(self, p: QPainter) -> None:
        """头顶的说话气泡:有正文就把话写出来,没有(旧信号 / 空消息)就三个点。"""
        bottom = -56.0                      # 尖尖底端:刚好在头顶上方
        rect = QRectF(-self._bw / 2, bottom - TAIL_H - self._bh,
                      self._bw, self._bh)
        p.setBrush(QBrush(PAPER))      # 纸白:气泡多半压在地毯上,
        p.setPen(QPen(BEZEL, 1))       # 用地毯色的话只剩一圈描边撑着
        p.drawRoundedRect(rect, 5, 5)
        p.drawPolygon(QPolygonF([QPointF(-3, rect.bottom() - 0.5),
                                 QPointF(3, rect.bottom() - 0.5),
                                 QPointF(0, bottom)]))
        if not self._lines:                 # 没正文:老三点
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(TXT))
            for i in range(3):
                p.drawEllipse(QRectF(-7.5 + i * 5, rect.center().y() - 1.5, 3, 3))
            return
        p.setPen(QPen(TXT))
        p.setFont(FONT_MSG)
        y = rect.top() + BUBBLE_PAD
        for line in self._lines:
            p.drawText(QRectF(rect.left() + BUBBLE_PAD, y,
                              self._bw - BUBBLE_PAD * 2, LINE_H),
                       int(Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter), line)
            y += LINE_H
        p.setPen(Qt.PenStyle.NoPen)
