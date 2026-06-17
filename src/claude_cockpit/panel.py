"""常驻轻量面板(深色卡片风):每个成员一张卡(配色条 + 状态灯 + 名字 + 运行键),
整卡左键 = 置前/启动其控制台;右键 = 编辑/删除;列表最底部一张「＋ 新成员」卡。

运行中的成员排在最前、整卡点亮;未运行的置灰排后。

对外接口(main 依赖):
  Panel(members) / set_status(name,status) / set_run_state(name,state) /
  set_order(names) / rebuild(members)
  信号:member_clicked(str)、add_requested()、edit_requested(str)、delete_requested(str)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QPushButton,
    QVBoxLayout, QWidget,
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
QFrame#card { background:#22252d; border-radius:10px; }
QFrame#card:hover { background:#2b2f3a; }
QFrame#addcard {
    background:transparent; border:1px dashed #3a3f4b; border-radius:10px;
}
QFrame#addcard:hover { background:#22252d; border-color:#34965a; }
QLabel#addtext { color:#7b828d; font-size:13px; font-weight:600; background:transparent; }
QFrame#addcard:hover QLabel#addtext { color:#9be6b4; }
QLabel#name { font-size:13px; font-weight:600; background:transparent; }
QLabel#dot { background:transparent; }
QPushButton#go {
    color:#cdd2db; background:#333845; border:none; border-radius:6px;
    font-size:12px; font-weight:700; padding:0;
}
QPushButton#go:hover { background:#414857; color:#ffffff; }
QPushButton#go:disabled { background:#262a33; color:#565c67; }
"""

# 未运行的卡片整张置灰(半透明),运行中/启动中恢复全亮
_DIM = 0.4
# 运行中的「运行中」徽标:绿底绿字,一眼可辨
_RUNNING_QSS = ("color:#9be6b4; background:#1f3a29; border:none;"
                " border-radius:6px; font-size:11px; font-weight:700;")
# 启动中的「启动中」徽标:琥珀底,提示正在拉起(中间这段以前没反馈)
_LAUNCHING_QSS = ("color:#f1c40f; background:#3a3320; border:none;"
                  " border-radius:6px; font-size:11px; font-weight:700;")


def _dot_qss(color: str) -> str:
    return f"background:{color}; border-radius:6px;"


class _Card(QFrame):
    """整卡左键置前/启动;右键弹「编辑/删除」。"""
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


class _AddCard(QFrame):
    """列表底部的「＋ 新成员」卡,样式与成员卡一致(虚线框区分)。"""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("addcard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel("＋  新成员")
        label.setObjectName("addtext")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(label)
        self.setMinimumHeight(40)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


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
        self._effects: dict[str, QGraphicsOpacityEffect] = {}
        self._cards: dict[str, _Card] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # 头部:标题 + 副标题(添加按钮已移到列表底部)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        t = QLabel("Claude 驾驶舱")
        t.setObjectName("title")
        sub = QLabel("左键置前 · 右键编辑/删除 · 🟡 等你确认")
        sub.setObjectName("subtitle")
        titles.addWidget(t)
        titles.addWidget(sub)
        root.addLayout(titles)

        self._list = QVBoxLayout()
        self._list.setSpacing(8)
        root.addLayout(self._list)
        root.addStretch(1)

        self._add_card = _AddCard()
        self._add_card.clicked.connect(self.add_requested.emit)

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

        # 默认未运行 → 整卡置灰;set_run_state 命中后再点亮
        eff = QGraphicsOpacityEffect(card)
        eff.setOpacity(_DIM)
        card.setGraphicsEffect(eff)
        self._effects[m.name] = eff
        self._cards[m.name] = card
        return card

    def rebuild(self, members) -> None:
        """成员增删改后重建卡片列表(成员卡 + 底部「＋ 新成员」卡)。"""
        self._add_card.setParent(None)          # 先摘下复用,避免被删
        while self._list.count():
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._add_card:
                w.setParent(None)
                w.deleteLater()
        self._dots.clear()
        self._gos.clear()
        self._effects.clear()
        self._cards.clear()
        for m in members:
            self._list.addWidget(self._make_card(m))
        self._list.addWidget(self._add_card)

    def set_order(self, names: list[str]) -> None:
        """按给定顺序重排成员卡(运行中靠前);「＋ 新成员」恒在最底。"""
        self._add_card.setParent(None)
        for w in self._cards.values():
            self._list.removeWidget(w)
        for n in names:
            card = self._cards.get(n)
            if card is not None:
                self._list.addWidget(card)
        self._list.addWidget(self._add_card)

    def set_run_state(self, name: str, state: str) -> None:
        """state ∈ {down(未运行), launching(启动中), running(运行中)}。
        控制整卡明暗 + 右侧运行键的文字/样式。"""
        eff = self._effects.get(name)
        if eff is not None:
            eff.setOpacity(_DIM if state == "down" else 1.0)
        go = self._gos.get(name)
        if go is None:
            return
        if state == "running":
            go.setEnabled(False)
            go.setText("运行中")
            go.setFixedSize(52, 26)
            go.setStyleSheet(_RUNNING_QSS)
            go.setToolTip("已在运行 · 点这张卡置前")
        elif state == "launching":
            go.setEnabled(False)
            go.setText("启动中")
            go.setFixedSize(52, 26)
            go.setStyleSheet(_LAUNCHING_QSS)
            go.setToolTip("正在拉起控制台…")
        else:                                   # down
            go.setEnabled(True)
            go.setText("▶")
            go.setFixedSize(26, 26)
            go.setStyleSheet("")                # 回退到 #go 默认样式
            go.setToolTip("单独启动 / 置前这一个")

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
