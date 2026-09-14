"""说话气泡:折行 + 画。**送信的小人和工位共用这一份**。

原来只长在 `WalkerItem` 上(会话之间发消息时冒的那个);机柜搬到运维桌上之后,
「走过去看一眼」没意义了,改成他在工位上直接说一句——两处要是各画各的,同一个
气泡会有两种圆角、两种字号,一眼看得出是拼的。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QFontMetricsF, QPainter, QPen, QPolygonF

from .theme import BEZEL, PAPER, TXT

W = 168.0               # 最宽多少(再宽就盖住旁边的工位了)
PAD = 6.0
MAX_LINES = 3           # 最多几行,超了末行省略号
LINE_H = 12.0
TAIL_H = 6.0            # 底下那个小尖

FONT = QFont()          # 模块级:paint 每帧重建 QFont 要走字体匹配查找
FONT.setPointSize(7)
FM = QFontMetricsF(FONT)


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


def wrap(text: str, width: float = W - PAD * 2,
         lines: int = MAX_LINES) -> list[str]:
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
        if FM.horizontalAdvance(cur + ch) <= width:
            cur += ch
            continue
        done, carry = _break_at(cur, ch)
        out.append(done)
        cur = carry + ch
        if len(out) == lines:               # 装不下了:末行收成省略号
            last = out[-1]
            while last and FM.horizontalAdvance(last + "…") > width:
                last = last[:-1]
            out[-1] = last.rstrip() + "…"
            return out
    if cur:
        out.append(cur)
    return out[:lines]


def size(lines: list[str]) -> tuple[float, float]:
    """气泡框多大(不含底下那个尖)。没正文时是「三个点」那个小框。"""
    if not lines:
        return (26.0, 14.0)
    w = max((FM.horizontalAdvance(ln) for ln in lines), default=0.0)
    return (w + PAD * 2, len(lines) * LINE_H + PAD * 2)


def height(lines: list[str]) -> float:
    """连尖一起多高——调用方拿它算包围盒(写死的话长气泡会被裁掉一块)。"""
    return size(lines)[1] + TAIL_H


def draw(p: QPainter, lines: list[str], tip: QPointF) -> None:
    """把气泡画在 `tip` 上方(尖尖正好落在 tip 上)。"""
    bw, bh = size(lines)
    rect = QRectF(tip.x() - bw / 2, tip.y() - TAIL_H - bh, bw, bh)
    p.setBrush(QBrush(PAPER))       # 纸白:气泡多半压在地毯或桌面上,
    p.setPen(QPen(BEZEL, 1))        # 用同色的话只剩一圈描边撑着
    p.drawRoundedRect(rect, 5, 5)
    p.drawPolygon(QPolygonF([QPointF(tip.x() - 3, rect.bottom() - 0.5),
                             QPointF(tip.x() + 3, rect.bottom() - 0.5),
                             QPointF(tip.x(), tip.y())]))
    if not lines:                   # 没正文:老三点
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(TXT))
        for i in range(3):
            p.drawEllipse(QRectF(tip.x() - 7.5 + i * 5,
                                 rect.center().y() - 1.5, 3, 3))
        return
    p.setPen(QPen(TXT))
    p.setFont(FONT)
    y = rect.top() + PAD
    for line in lines:
        p.drawText(QRectF(rect.left() + PAD, y, bw - PAD * 2, LINE_H),
                   int(Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter), line)
        y += LINE_H
    p.setPen(Qt.PenStyle.NoPen)
