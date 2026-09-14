"""对话记录窗:点桌上那部手机弹出来,列这个员工收发的会话间消息。

**浅色**(跟画布配色走,不套 tray_popup 那份深色 QSS——那个是托盘悬停用的)。
`Qt.Popup`:点外面自动关、Esc 关,关了自己销毁。
内容由调用方算好传进来(`history.for_member` 的结果),**开窗时现读现组装**,
不常驻、不订阅刷新——记录是「翻旧账」,不是实时流。
"""
from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QTextBrowser, QVBoxLayout

POPUP_W = 320
POPUP_H = 360           # 超了自己滚

_QSS = """
QFrame#histpop { background:#ffffff; border:1px solid #d4d9e0; border-radius:8px; }
QTextBrowser#histbody { border:none; background:transparent; font-size:12px; }
"""


def _row(e) -> str:
    """一条 = 两行:「→ 对方 · 时间」+ 正文。正文**必须转义**——那是别的会话发来
    的原文,带尖括号会把这份 HTML 撑坏。"""
    arrow, color = ("→", "#2563eb") if e.direction == "out" else ("←", "#15803d")
    when = time.strftime("%m-%d %H:%M", time.localtime(e.at))
    return (f'<p style="margin:8px 0 2px 0;color:{color};font-weight:bold;">'
            f'{arrow} {html.escape(e.peer)} '
            f'<span style="color:#98a1ad;font-weight:normal;">· {when}</span></p>'
            f'<p style="margin:0;color:#2b3038;">{html.escape(e.text)}</p>')


class HistoryPopup(QFrame):
    """`entries` 是 `history.for_member()` 的结果(按时间正序)。"""

    def __init__(self, name: str, entries, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName("histpop")
        self.setStyleSheet(_QSS)
        self.setFixedWidth(POPUP_W)
        self.setMaximumHeight(POPUP_H)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        self.body = QTextBrowser()
        self.body.setObjectName("histbody")
        self.body.setReadOnly(True)
        self.body.setOpenExternalLinks(False)
        self.body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        head = (f'<p style="margin:0 0 4px 0;color:#6b7480;font-size:11px;">'
                f'{html.escape(name)} 的对话记录</p>')
        if entries:
            self.body.setHtml(head + "".join(_row(e) for e in entries))
        else:
            self.body.setHtml(head + '<p style="color:#98a1ad;">还没有对话记录</p>')
        lay.addWidget(self.body)

    def showEvent(self, e):
        super().showEvent(e)
        # 最近的在底部,开窗滚到底——像聊天记录,不像日志
        bar = self.body.verticalScrollBar()
        bar.setValue(bar.maximum())
