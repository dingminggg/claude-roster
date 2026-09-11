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
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from . import person
from .theme import BEZEL, CARPET, TXT

OUT_MS = 1500           # 单程
WAIT_MS = 900           # 到了之后停住说话
TICK_MS = 40


class WalkerItem(QGraphicsObject):
    def __init__(self, color: QColor, path: list[QPointF]):
        super().__init__()
        self.color = QColor(color)
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
            if self._elapsed >= WAIT_MS:
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
        return QRectF(-22, -74, 44, 80)     # 人 + 头顶那个气泡

    def paint(self, p: QPainter, opt, widget) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        person.draw_standing(p, self.color, 0.0, 0.0, bob=self.bob())
        if self._phase == "wait":           # 到了就冒个说话气泡
            p.setBrush(QBrush(CARPET))
            p.setPen(QPen(BEZEL, 1))
            p.drawRoundedRect(QRectF(-13, -70, 26, 14), 5, 5)
            p.drawPolygon(QPolygonF([QPointF(-3, -57), QPointF(2, -57),
                                     QPointF(-1, -52)]))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(TXT))
            for i in range(3):
                p.drawEllipse(QRectF(-7.5 + i * 5, -65, 3, 3))
