"""常驻轻量面板(深色卡片风):每个成员一张卡(配色条 + 状态灯 + 名字),
整卡可点 = 置前其控制台;顶部「▶ 全部启动」。状态由外部 set_status 驱动。

对外接口(main 依赖,勿改):
  Panel(members) / 信号 member_clicked(str)、launch_all_clicked() / set_status(name, status)
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

# 状态 → 灯色
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
QPushButton#launchAll {
    background:#2d7d46; color:#ffffff; border:none; border-radius:8px;
    padding:8px 12px; font-size:12px; font-weight:600;
}
QPushButton#launchAll:hover { background:#349652; }
QPushButton#launchAll:pressed { background:#27703f; }
QFrame#card { background:#22252d; border-radius:10px; }
QFrame#card:hover { background:#2b2f3a; }
QFrame#accent { border-radius:2px; }
QLabel#name { font-size:13px; font-weight:600; background:transparent; }
QLabel#dot { background:transparent; }
QPushButton#go {
    color:#cdd2db; background:#333845; border:none; border-radius:6px;
    font-size:12px; font-weight:700; padding:0;
}
QPushButton#go:hover { background:#414857; color:#ffffff; }
QPushButton#go:disabled { background:#262a33; color:#565c67; }
"""


class _Card(QFrame):
    """整张卡可点。"""
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


def _dot_qss(color: str) -> str:
    return f"background:{color}; border-radius:6px;"


class Panel(QWidget):
    member_clicked = Signal(str)
    launch_all_clicked = Signal()

    def __init__(self, members):
        super().__init__()
        self.setObjectName("panel")
        self.setWindowTitle("Claude 驾驶舱")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(_QSS)
        self.setMinimumWidth(248)

        self._dots: dict[str, QLabel] = {}
        self._gos: dict[str, QPushButton] = {}   # name -> ▶ 按钮(运行中时屏蔽)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # 头部:标题 + 副标题 + 全部启动
        header = QHBoxLayout()
        header.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        t = QLabel("Claude 驾驶舱")
        t.setObjectName("title")
        sub = QLabel("点成员置前 · 🟡 等你确认")
        sub.setObjectName("subtitle")
        titles.addWidget(t)
        titles.addWidget(sub)
        header.addLayout(titles, 1)
        btn_all = QPushButton("▶ 全部启动")
        btn_all.setObjectName("launchAll")
        btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_all.clicked.connect(self.launch_all_clicked.emit)
        header.addWidget(btn_all, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        # 成员卡片
        for m in members:
            card = _Card()
            card.clicked.connect(lambda n=m.name: self.member_clicked.emit(n))
            lay = QHBoxLayout(card)
            lay.setContentsMargins(0, 0, 10, 0)
            lay.setSpacing(10)

            accent = QFrame()
            accent.setObjectName("accent")
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

            root.addWidget(card)

        root.addStretch(1)

    def set_running(self, name: str, running: bool) -> None:
        """运行中(cockpit 已启动且窗口还在)→ 屏蔽 ▶ 启动键(点卡片置前即可);
        窗口关掉后恢复可启动。"""
        go = self._gos.get(name)
        if go is not None:
            go.setEnabled(not running)
            go.setToolTip("已在运行 · 点这张卡置前" if running
                          else "单独启动 / 置前这一个")

    def set_status(self, name: str, status: str) -> None:
        dot = self._dots.get(name)
        if dot is not None:
            color = _STATUS_COLOR.get(status, _STATUS_COLOR["down"])
            dot.setStyleSheet(_dot_qss(color))
            dot.setToolTip({"pending": "等你确认", "busy": "处理中",
                            "idle": "空闲", "down": "未运行"}.get(status, status))
