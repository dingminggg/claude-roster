"""常驻轻量面板:每个成员一行(emoji 名字 状态点),点行=置前其控制台;
顶部「▶ 全部启动」「刷新」;系统托盘可显隐/退出。状态由外部 set_status 驱动。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

_DOT = {"idle": "⚪", "pending": "🟡", "down": "⛔"}


class Panel(QWidget):
    # 信号:点某成员行 / 点全部启动
    member_clicked = Signal(str)
    launch_all_clicked = Signal()

    def __init__(self, members):
        super().__init__()
        self.setWindowTitle("Claude 驾驶舱")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._rows: dict[str, QLabel] = {}   # name -> 状态点 label
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        btn_all = QPushButton("▶ 全部启动")
        btn_all.clicked.connect(self.launch_all_clicked.emit)
        top.addWidget(btn_all)
        root.addLayout(top)
        for m in members:
            row = QHBoxLayout()
            dot = QLabel(_DOT["idle"])
            start = QPushButton("▶")
            start.setToolTip("单独启动 / 置前这一个")
            start.setFixedWidth(28)
            start.clicked.connect(
                lambda _=False, n=m.name: self.member_clicked.emit(n))
            name = QPushButton(f"{m.emoji} @{m.name}")
            name.setFlat(True)
            name.setToolTip("点击置前其控制台(没开则启动)")
            name.clicked.connect(
                lambda _=False, n=m.name: self.member_clicked.emit(n))
            row.addWidget(dot)
            row.addWidget(start)
            row.addWidget(name, 1)
            root.addLayout(row)
            self._rows[m.name] = dot

    def set_status(self, name: str, status: str) -> None:
        dot = self._rows.get(name)
        if dot is not None:
            dot.setText(_DOT.get(status, "⚪"))
