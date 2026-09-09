"""托盘悬停浮层:列出有消息的成员,点一行发 picked(name)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout

_TRAY_POPUP_W = 132
_TRAY_POPUP_MARGIN = 4          # 外层只留极小边,够把 hover 高亮收进圆角即可

# 只保留浮层自己要用的两条规则:卡片列表退休了,别把整份面板 QSS 一起搬过来
_QSS = """
QFrame#popup { background:#2b2f3a; border:1px solid #3a3f4b; border-radius:8px; }
QPushButton#popitem {
    color:#c7ccd6; background:transparent; border:none; text-align:left;
    font-size:13px; padding:6px 8px; border-radius:5px;
}
QPushButton#popitem:hover { background:#363b47; color:#ffffff; }
"""


class TrayPopup(QFrame):
    """托盘悬停时弹出的无边框小浮层:列出有消息的成员,点一行发 picked(name)。
    显隐由 main 的悬停定时器控制——故意不用 Qt.Popup(那种一移开鼠标就当点了外面
    自动关,与悬停模型冲突);用 Tool + 不抢焦点窗口,我们自己控显隐。
    生命周期由调用方掌管:用完须 close() + deleteLater() 释放(它不是 Qt.Popup,不会自动销毁)。
    结构:外层窗口透明,内层 #popup 卡片画深色圆角背景——圆角处透明、其余深色,既显出圆角,
    又不像「直接给顶层窗口透明」那样把背景也一起弄没了。"""
    picked = Signal(str)

    def __init__(self, rows, parent=None):
        # rows: list[(name, emoji, color)]
        super().__init__(parent,
                         Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # 不偷当前前台焦点
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 外层透明,圆角靠内层卡片
        self.setStyleSheet(_QSS)                # 样式级联给内层 #popup / #popitem

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()                         # 深色圆角背景画在这层(顶层透明就不会丢背景)
        card.setObjectName("popup")
        card.setFixedWidth(_TRAY_POPUP_W)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(_TRAY_POPUP_MARGIN, 4, _TRAY_POPUP_MARGIN, 4)
        lay.setSpacing(2)
        # 文字可用宽 = 卡片宽 - 左右内边距 - popitem 自身左右 padding(QSS 里 8px*2)
        avail = _TRAY_POPUP_W - _TRAY_POPUP_MARGIN * 2 - 16
        fm = QFontMetrics(self.font())
        for name, emoji, color in rows:
            full = f"{emoji} @{name}"
            b = QPushButton(fm.elidedText(full, Qt.TextElideMode.ElideRight, avail))
            b.setObjectName("popitem")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"color:{color};")  # 名字用成员配色,和卡片一致
            b.setToolTip(full)                  # 截断了也能悬停看全名
            b.clicked.connect(lambda _=False, n=name: self.picked.emit(n))
            lay.addWidget(b)
