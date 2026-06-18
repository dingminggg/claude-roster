"""常驻轻量面板(深色卡片风):每个成员一张卡(配色条 + 名字 + 运行键),
整卡左键 = 置前/已读其控制台;右键 = 编辑/删除;列表最底部一张「＋ 新成员」卡。

运行中的成员排在最前、整卡点亮;未运行的置灰排后。

对外接口(main 依赖):
  Panel(members) / set_run_state(name,state) / set_order(names) / rebuild(members)
  信号:member_clicked(str)、start_requested(str)、add_requested()、
        edit_requested(str)、delete_requested(str)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QPushButton,
    QVBoxLayout, QWidget,
)

# 图标:claude-groupchat 的「多只小青蛙」图,已复制进本包 assets
ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"

_QSS = """
QWidget#panel { background:#181a1f; }
QLabel#title { color:#eaecef; font-size:14px; font-weight:700; }
QLabel#subtitle { color:#6e7682; font-size:11px; }
QFrame#card { background:#22252d; border-radius:10px; }
QFrame#card:hover { background:#2b2f3a; }
QLabel#env { background:transparent; }
QFrame#addcard {
    background:transparent; border:1px dashed #3a3f4b; border-radius:10px;
}
QFrame#addcard:hover { background:#22252d; border-color:#34965a; }
QLabel#addtext { color:#7b828d; font-size:13px; font-weight:600; background:transparent; }
QFrame#addcard:hover QLabel#addtext { color:#9be6b4; }
QLabel#name { font-size:13px; font-weight:600; background:transparent; }
QPushButton#go {
    color:#c7ccd6; background:#2f343f; border:none; border-radius:11px;
    font-size:11px; font-weight:600; padding:0;
}
QPushButton#go:hover { background:#34965a; color:#ffffff; }
QPushButton#go:disabled { background:#2a2e37; color:#7b828d; }
QPushButton#yes {
    color:#dff5e6; background:#2e7d46; border:none; border-radius:11px;
    font-size:11px; font-weight:600;
}
QPushButton#yes:hover { background:#369152; color:#ffffff; }
QPushButton#no {
    color:#cdd2db; background:#3a3f4b; border:none; border-radius:11px;
    font-size:11px; font-weight:600;
}
QPushButton#no:hover { background:#4a505e; color:#ffffff; }
"""

# 运行键统一尺寸:三种状态同宽,右侧排成一条干净的竖列(不再忽大忽小)
_GO_W, _GO_H = 56, 22

# 未运行的卡片整张置灰(半透明),运行中/启动中恢复全亮
_DIM = 0.4
# 运行中:绿色胶囊
_RUNNING_QSS = ("color:#9be6b4; background:#1f3a29; border:none;"
                " border-radius:11px; font-size:11px; font-weight:600;")
# 启动中:琥珀胶囊(提示正在拉起,中间这段以前没反馈)
_LAUNCHING_QSS = ("color:#f1c40f; background:#3a3320; border:none;"
                  " border-radius:11px; font-size:11px; font-weight:600;")


class _Card(QFrame):
    """整卡左键置前/启动;右键弹「编辑/删除」。"""
    clicked = Signal()
    edit = Signal()
    delete = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        # 默认不是手型:未运行时整条点了也没反应(只有「启动」键能开)。
        # 运行后由 set_run_state 切成手型,表示「点横条可置前」。
        self.setCursor(Qt.CursorShape.ArrowCursor)

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
    member_clicked = Signal(str)    # 点整条横条:仅运行后置前
    start_requested = Signal(str)   # 点「启动」键:拉起控制台
    add_requested = Signal()
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, members):
        super().__init__()
        self.setObjectName("panel")
        self.setWindowTitle("Claude 驾驶舱")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)  # 不给最大化
        self.setStyleSheet(_QSS)
        self.setFixedWidth(310)             # 固定宽度,只允许竖向随成员数伸缩
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._gos: dict[str, QPushButton] = {}
        self._envs: dict[str, QLabel] = {}     # 每行的「有新消息」小信封
        self._effects: dict[str, QGraphicsOpacityEffect] = {}
        self._cards: dict[str, _Card] = {}
        self._confirm_boxes: dict[str, QWidget] = {}   # 内联「确定/取消」条
        self._confirming: set[str] = set()             # 当前处于确认态的成员
        self._msg_on: set[str] = set()                 # 当前有新消息(红点)的成员
        self._blink_on = True                          # 红点闪烁相位

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # 头部:标题 + 副标题(添加按钮已移到列表底部)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        t = QLabel("Claude 驾驶舱")
        t.setObjectName("title")
        sub = QLabel("点「启动」开 · 答完亮红点+闪烁 · 点横条=最大化/已读")
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

        # 红点闪烁:有新消息的行,红点在 红↔灭 间交替,比静止更醒目
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_dots)
        self._blink_timer.start(550)

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

        # 「有新消息」红点角标:靠左(名字前),始终占位 10px,只切红/透明,名字不抖
        env = QLabel()
        env.setObjectName("env")
        env.setFixedSize(10, 10)
        lay.addWidget(env, 0, Qt.AlignmentFlag.AlignVCenter)
        self._envs[m.name] = env

        name = QLabel(f"{m.emoji}  @{m.name}")
        name.setObjectName("name")
        name.setStyleSheet(f"color:{m.color};")
        lay.addWidget(name, 1)

        go = QPushButton("启动")
        go.setObjectName("go")
        go.setFixedSize(_GO_W, _GO_H)
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setToolTip("启动这个成员的控制台")
        go.clicked.connect(lambda _=False, n=m.name: self._enter_confirm(n))
        lay.addWidget(go, 0, Qt.AlignmentFlag.AlignVCenter)
        self._gos[m.name] = go

        # 内联确认条:点「启动」后原地替换成「确定/取消」,默认隐藏
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        yes = QPushButton("确定")
        yes.setObjectName("yes")
        yes.setFixedSize(36, _GO_H)
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.clicked.connect(lambda _=False, n=m.name: self._confirm_yes(n))
        no = QPushButton("取消")
        no.setObjectName("no")
        no.setFixedSize(36, _GO_H)
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.clicked.connect(lambda _=False, n=m.name: self._confirm_no(n))
        bl.addWidget(yes)
        bl.addWidget(no)
        box.setVisible(False)
        lay.addWidget(box, 0, Qt.AlignmentFlag.AlignVCenter)
        self._confirm_boxes[m.name] = box

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
        self._gos.clear()
        self._envs.clear()
        self._effects.clear()
        self._cards.clear()
        self._confirm_boxes.clear()
        self._confirming.clear()
        self._msg_on.clear()
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

    def _enter_confirm(self, name: str) -> None:
        """点「启动」→ 原地把按钮换成「确定/取消」。"""
        self._confirming.add(name)
        go = self._gos.get(name)
        box = self._confirm_boxes.get(name)
        if go is not None:
            go.setVisible(False)
        if box is not None:
            box.setVisible(True)
        eff = self._effects.get(name)
        if eff is not None:                     # 确认中点亮,确定/取消看得清
            eff.setOpacity(1.0)

    def _confirm_no(self, name: str) -> None:
        """取消 → 回到「启动」按钮。"""
        self._confirming.discard(name)
        self.set_run_state(name, "down")

    def _confirm_yes(self, name: str) -> None:
        """确定 → 收起确认条,走启动流程。"""
        self._confirming.discard(name)
        box = self._confirm_boxes.get(name)
        if box is not None:
            box.setVisible(False)
        go = self._gos.get(name)
        if go is not None:
            go.setVisible(True)
        self.start_requested.emit(name)

    def _apply_dot(self, name: str) -> None:
        env = self._envs.get(name)
        if env is None:
            return
        lit = name in self._msg_on and self._blink_on   # 有消息且当前在「亮」相位
        env.setStyleSheet("background:#ff4d4f; border-radius:5px;" if lit
                          else "background:transparent;")

    def _blink_dots(self) -> None:
        self._blink_on = not self._blink_on
        for name in list(self._msg_on):
            self._apply_dot(name)

    def set_message(self, name: str, on: bool) -> None:
        """切换这一行左侧的「有新消息」红点(答完一轮/等你);红点会闪烁。不动运行键文字。"""
        env = self._envs.get(name)
        if env is None:
            return
        if on:
            self._msg_on.add(name)
        else:
            self._msg_on.discard(name)
        env.setToolTip("有新消息 · 点这张卡查看并已读" if on else "")
        self._apply_dot(name)

    def set_run_state(self, name: str, state: str) -> None:
        """state ∈ {down(未运行), launching(启动中), running(运行中)}。
        控制整卡明暗 + 右侧运行键的文字/样式;确认态优先(显示确定/取消)。"""
        if state != "down":                     # 一旦进入启动/运行,确认态作废
            self._confirming.discard(name)
        confirming = name in self._confirming and state == "down"

        box = self._confirm_boxes.get(name)
        if box is not None:
            box.setVisible(confirming)
        card = self._cards.get(name)
        if card is not None:                    # 运行后横条才是手型 + 可点置前
            card.setCursor(Qt.CursorShape.PointingHandCursor if state == "running"
                           else Qt.CursorShape.ArrowCursor)
        eff = self._effects.get(name)
        if eff is not None:                     # 确认中也点亮;纯未运行才置灰
            eff.setOpacity(_DIM if (state == "down" and not confirming) else 1.0)

        go = self._gos.get(name)
        if go is None:
            return
        go.setVisible(not confirming)
        if confirming:
            return
        # 尺寸三态统一(_GO_W×_GO_H),只换文字/配色,右侧始终对齐成一列
        if state == "running":
            go.setEnabled(False)
            go.setText("运行中")
            go.setStyleSheet(_RUNNING_QSS)
            go.setToolTip("已在运行 · 点这张卡置前")
        elif state == "launching":
            go.setEnabled(False)
            go.setText("启动中")
            go.setStyleSheet(_LAUNCHING_QSS)
            go.setToolTip("正在拉起控制台…")
        else:                                   # down
            go.setEnabled(True)
            go.setText("启动")
            go.setStyleSheet("")                # 回退到 #go 默认样式
            go.setToolTip("启动这个成员的控制台")

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
