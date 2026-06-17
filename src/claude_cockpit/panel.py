"""常驻轻量面板(深色卡片风):每个成员一张卡(配色条 + 状态灯 + 名字),
整卡左键 = 置前其控制台;右键 = 编辑/删除;顶部「＋」添加成员。

对外接口(main 依赖):
  Panel(members) / set_status(name,status) / set_running(name,bool) / rebuild(members)
  信号:member_clicked(str)、add_requested()、edit_requested(str)、delete_requested(str)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

# 图标:claude-groupchat 的「多只小青蛙」图,已复制进本包 assets
ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"

_STATUS_COLOR = {
    "pending": "#f1c40f",   # 琥珀:等你确认
    "busy": "#3fb950",      # 绿:处理中(v2 预留)
    "idle": "#6b7280",      # 灰:空闲 / 已启动
    "down": "#3a3f4b",      # 暗:未运行
}

_QSS = """
QWidget#panel { background:#181a1f; }
QLabel#title { color:#eaecef; font-size:14px; font-weight:700; }
QLabel#subtitle { color:#6e7682; font-size:11px; }
QPushButton#add {
    color:#cdd2db; background:#2a2e37; border:none; border-radius:8px;
    font-size:18px; font-weight:700;
}
QPushButton#add:hover { background:#34965a; color:#ffffff; }
QFrame#card { background:#22252d; border-radius:10px; }
QFrame#card:hover { background:#2b2f3a; }
QLabel#name { font-size:13px; font-weight:600; background:transparent; }
QLabel#dot { background:transparent; }
QPushButton#go {
    color:#cdd2db; background:#333845; border:none; border-radius:6px;
    font-size:12px; font-weight:700; padding:0;
}
QPushButton#go:hover { background:#414857; color:#ffffff; }
QPushButton#go:disabled { background:#262a33; color:#565c67; }
"""


def _dot_qss(color: str) -> str:
    return f"background:{color}; border-radius:6px;"


class _Card(QFrame):
    """整卡左键置前;右键弹「编辑/删除」。"""
    clicked = Signal()
    edit = Signal()
    delete = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction("编辑", self.edit.emit)
        menu.addAction("删除", self.delete.emit)
        menu.exec(e.globalPos())


class Panel(QWidget):
    member_clicked = Signal(str)
    add_requested = Signal()
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, members):
        super().__init__()
        self.setObjectName("panel")
        self.setWindowTitle("Claude 驾驶舱")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(_QSS)
        self.setMinimumWidth(248)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._dots: dict[str, QLabel] = {}
        self._gos: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # 头部:标题 + 副标题 + ＋添加
        top = QHBoxLayout()
        top.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        t = QLabel("Claude 驾驶舱")
        t.setObjectName("title")
        sub = QLabel("左键置前 · 右键编辑/删除 · 🟡 等你确认")
        sub.setObjectName("subtitle")
        titles.addWidget(t)
        titles.addWidget(sub)
        top.addLayout(titles, 1)
        add = QPushButton("＋")
        add.setObjectName("add")
        add.setFixedSize(30, 30)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.setToolTip("添加成员")
        add.clicked.connect(self.add_requested.emit)
        top.addWidget(add, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        self._cards = QVBoxLayout()
        self._cards.setSpacing(8)
        root.addLayout(self._cards)
        root.addStretch(1)

        self.rebuild(members)

    def _make_card(self, m) -> _Card:
        card = _Card()
        card.clicked.connect(lambda n=m.name: self.member_clicked.emit(n))
        card.edit.connect(lambda n=m.name: self.edit_requested.emit(n))
        card.delete.connect(lambda n=m.name: self.delete_requested.emit(n))
        lay = QHBoxLayout(card)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(10)

        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setMinimumHeight(40)
        accent.setStyleSheet(f"background:{m.color}; border-radius:2px;")
        lay.addWidget(accent)

        dot = QLabel()
        dot.setObjectName("dot")
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(_dot_qss(_STATUS_COLOR["down"]))
        lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._dots[m.name] = dot

        name = QLabel(f"{m.emoji}  @{m.name}")
        name.setObjectName("name")
        name.setStyleSheet(f"color:{m.color};")
        lay.addWidget(name, 1)

        go = QPushButton("▶")
        go.setObjectName("go")
        go.setFixedSize(26, 26)
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setToolTip("单独启动 / 置前这一个")
        go.clicked.connect(lambda _=False, n=m.name: self.member_clicked.emit(n))
        lay.addWidget(go, 0, Qt.AlignmentFlag.AlignVCenter)
        self._gos[m.name] = go
        return card

    def rebuild(self, members) -> None:
        """成员增删改后重建卡片列表。"""
        while self._cards.count():
            item = self._cards.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._dots.clear()
        self._gos.clear()
        for m in members:
            self._cards.addWidget(self._make_card(m))

    def set_running(self, name: str, running: bool) -> None:
        """运行中 → 屏蔽 ▶ 启动键(点卡片置前即可);窗口关掉后恢复。"""
        go = self._gos.get(name)
        if go is not None:
            go.setEnabled(not running)
            go.setToolTip("已在运行 · 点这张卡置前" if running
                          else "单独启动 / 置前这一个")

    def set_status(self, name: str, status: str) -> None:
        dot = self._dots.get(name)
        if dot is not None:
            dot.setStyleSheet(_dot_qss(_STATUS_COLOR.get(status, _STATUS_COLOR["down"])))
            dot.setToolTip({"pending": "等你确认", "busy": "处理中",
                            "idle": "空闲", "down": "未运行"}.get(status, status))

    def showEvent(self, e):
        super().showEvent(e)
        self._dark_titlebar()

    def _dark_titlebar(self) -> None:
        try:
            import ctypes
            hwnd = int(self.winId())
            for attr in (20, 19):
                v = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass
