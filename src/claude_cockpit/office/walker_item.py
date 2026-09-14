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

from . import bubble, person

# 单程走多久。**走得慢一点**:1.5 秒那版像在赶路,一眼扫过去只看见有东西闪过。
OUT_MS = 3000
TICK_MS = 40

# 到了之后那一段,分四拍演:
#   开窗 → 一个字一个字打 → 停住让人读 → 关窗
# 「窗口先展开、字后一个个出」是有意的:框跟着字一起长的话,每多一个字框就抖
# 一下,读起来像在挣扎。
OPEN_MS = 220                   # 消息窗口展开
TYPE_MS_PER_CHAR = 55           # 每个字
HOLD_MS = 5000                  # 打完停住让人读
CLOSE_MS = 180                  # 收回去
DOTS_HOLD_MS = 1200             # 没正文时只冒三个点,不用停这么久


class WalkerItem(QGraphicsObject):
    def __init__(self, color: QColor, path: list[QPointF], text: str = ""):
        super().__init__()
        self.color = QColor(color)
        self._lines = bubble.wrap(text)
        self._chars = bubble.total_chars(self._lines)
        self._type_ms = self._chars * TYPE_MS_PER_CHAR
        self._hold_ms = HOLD_MS if self._lines else DOTS_HOLD_MS
        self._bw, self._bh = bubble.size(self._lines)
        self._path = [QPointF(q) for q in path]
        # 每段的累计长度:按**长度**在折线上取点,不按段数——不然长段走得飞快、
        # 短段磨蹭,一趟路走出好几种速度。
        self._acc = [0.0]
        for i in range(1, len(self._path)):
            d = self._path[i] - self._path[i - 1]
            self._acc.append(self._acc[-1] + (d.x() ** 2 + d.y() ** 2) ** 0.5)
        self._total = self._acc[-1] or 1.0
        self._elapsed = 0
        # out → open → type → hold → close → back →(自己从场景里摘掉)
        self._phase = "out"
        self.setZValue(60)                  # 走在地毯和工位上面
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setPos(self._path[0])
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(TICK_MS)

    # ---------- 动画 ----------
    # 每一拍走完就把 _elapsed 清零,下一拍自己从 0 开始数——各拍的时长互不相干,
    # 加一拍只要在这张表里插一行。
    _NEXT = {"open": "type", "type": "hold", "hold": "close", "close": "back"}

    def _phase_ms(self) -> int:
        return {"out": OUT_MS, "open": OPEN_MS, "type": self._type_ms,
                "hold": self._hold_ms, "close": CLOSE_MS, "back": OUT_MS}[self._phase]

    def _step(self) -> None:
        self._elapsed += TICK_MS
        done = self._elapsed >= self._phase_ms()
        if self._phase == "out":
            if done:
                self.setPos(self._path[-1])
                self._phase, self._elapsed = "open", 0
            else:
                self.setPos(self._lerp(self._elapsed / OUT_MS))
        elif self._phase == "back":
            if done:
                self._timer.stop()
                sc = self.scene()
                if sc is not None:
                    sc.removeItem(self)
                self.deleteLater()
                return
            self.setPos(self._lerp(1.0 - self._elapsed / OUT_MS))
        elif done:                      # 站着说话那几拍:到点就翻到下一拍
            self._phase, self._elapsed = self._NEXT[self._phase], 0
        self.update()

    def _grow(self) -> float:
        """消息窗口展开/收回的进度(0~1)。"""
        if self._phase == "open":
            return self._elapsed / OPEN_MS
        if self._phase == "close":
            return max(0.0, 1.0 - self._elapsed / CLOSE_MS)
        return 1.0

    def _reveal(self) -> int:
        """打到第几个字了。打完那一拍之后一直显示全文。"""
        if self._phase == "type":
            return int(self._elapsed / TYPE_MS_PER_CHAR) if self._chars else 0
        return self._chars

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
        return self._phase in ("out", "back")

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
        top = -(56 + bubble.height(self._lines) + 4)
        return QRectF(-half, top, half * 2, -top + 6)

    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        person.draw_standing(p, self.color, 0.0, 0.0, bob=self.bob())
        if not self.is_walking():           # 到了就开个消息窗口,把话打出来
            bubble.draw(p, self._lines, QPointF(0, -56),
                        grow=self._grow(), reveal=self._reveal())
