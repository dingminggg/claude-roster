"""常驻轻量面板(深色卡片风):每个成员一张卡(配色条 + 名字 + 运行键),
整卡左键 = 置前/已读其控制台;右键 = 编辑/删除;列表最底部一张「＋ 新成员」卡。

运行中的成员排在最前、整卡点亮;未运行的置灰排后。

对外接口(main 依赖):
  Panel(members) / set_run_state(name,state) / set_sessions(name,sessions) /
  set_order(names) / rebuild(members)
  信号:member_clicked(str)、start_requested(str, object)、add_requested()、
        edit_requested(str)、delete_requested(str)、open_dir_requested(str)、
        delete_session_requested(str, str)
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QIcon
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
QLabel#env { color:#ffffff; font-size:19px; background:transparent; }
QFrame#addcard {
    background:transparent; border:1px dashed #3a3f4b; border-radius:10px;
}
QFrame#addcard:hover { background:#22252d; border-color:#34965a; }
QLabel#addtext { color:#7b828d; font-size:13px; font-weight:600; background:transparent; }
QFrame#addcard:hover QLabel#addtext { color:#9be6b4; }
QLabel#name { font-size:13px; font-weight:600; background:transparent; }
QLabel#ctitle { color:#6e7682; font-size:10px; background:transparent; }
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
QPushButton#picker {
    color:#8a93a0; background:transparent; border:none; text-align:left;
    font-size:10px; padding:0;
}
QPushButton#picker:hover { color:#c7ccd6; }
QFrame#popup { background:#2b2f3a; border:1px solid #3a3f4b; border-radius:8px; }
QPushButton#popitem {
    color:#c7ccd6; background:transparent; border:none; text-align:left;
    font-size:11px; padding:4px 6px; border-radius:5px;
}
QPushButton#popitem:hover { background:#363b47; color:#ffffff; }
QPushButton#popdel {
    color:#7b828d; background:transparent; border:none;
    font-size:13px; font-weight:700; border-radius:5px;
}
QPushButton#popdel:hover { color:#ff6b6b; background:#3a2a2a; }
"""

# 运行键统一尺寸:三种状态同宽,右侧排成一条干净的竖列(不再忽大忽小)
_GO_W, _GO_H = 56, 22
# 名字下方会话标题的最大显示宽度(px),超出用省略号截断(面板固定宽 310)
_CTITLE_W = 185
# 会话下拉(未运行成员名字下方):按钮文字省略宽度、弹层宽度
_PICKER_W = 170
# 下拉按钮末尾的展开箭头(提示这行可点开),始终可见
_PICKER_ARROW = "  ▾"
_POPUP_W = 250

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
    open_dir = Signal()

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
        menu.addAction("打开目录", self.open_dir.emit)
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


class _SessionPopup(QFrame):
    """会话下拉的浮层(Qt.Popup:点外部自动关闭)。第一行「＋ 新会话」,
    其下每行 [标题·日期 | 删除×];删除是二次点确认(再点同一个×才真删)。"""
    picked = Signal(str)            # "" = 新会话;否则 session_id
    delete_requested = Signal(str)  # session_id

    def __init__(self, sessions, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("popup")
        self.setFixedWidth(_POPUP_W)
        self._confirm_id: str | None = None
        self._dels: dict[str, QPushButton] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        new = QPushButton("＋  新会话")
        new.setObjectName("popitem")
        new.setCursor(Qt.CursorShape.PointingHandCursor)
        new.clicked.connect(lambda: self._pick(""))
        lay.addWidget(new)

        from . import sessions as _sess
        for s in sessions:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            label = s.title if s.title else "(无标题)"
            pick = QPushButton(f"{label} · {_sess.fmt_mtime(s.mtime)}")
            pick.setObjectName("popitem")
            pick.setCursor(Qt.CursorShape.PointingHandCursor)
            pick.setToolTip(s.title or s.id)
            pick.clicked.connect(lambda _=False, sid=s.id: self._pick(sid))
            rl.addWidget(pick, 1)
            dele = QPushButton("×")
            dele.setObjectName("popdel")
            dele.setFixedWidth(28)
            dele.setCursor(Qt.CursorShape.PointingHandCursor)
            dele.setToolTip("删除这条会话记录(再点一次确认)")
            dele.clicked.connect(lambda _=False, sid=s.id: self._on_del(sid))
            rl.addWidget(dele, 0)
            self._dels[s.id] = dele
            lay.addWidget(row)

    def _pick(self, sid: str) -> None:
        self.picked.emit(sid)
        self.close()

    def _on_del(self, sid: str) -> None:
        if self._confirm_id == sid:         # 第二次点同一个 × → 真删
            self.delete_requested.emit(sid)
            self.close()
            return
        self._reset_confirm()               # 先复原别的「确认?」
        self._confirm_id = sid
        b = self._dels[sid]
        b.setText("确认?")
        b.setFixedWidth(44)
        b.setStyleSheet("color:#fff; background:#a33; border-radius:5px;"
                        " font-size:10px; font-weight:600;")

    def _reset_confirm(self) -> None:
        if self._confirm_id and self._confirm_id in self._dels:
            b = self._dels[self._confirm_id]
            b.setText("×")
            b.setFixedWidth(28)
            b.setStyleSheet("")
        self._confirm_id = None


class _SessionPicker(QWidget):
    """未运行成员名字下方的会话下拉:平时显示当前选中(「续:<标题>」或「＋ 新会话」),
    点开弹 _SessionPopup 选择/删除。删除经 delete_requested 上抛给卡片。"""
    delete_requested = Signal(str)  # session_id

    def __init__(self):
        super().__init__()
        self._sessions: list = []
        self._sel_id: str | None = None     # None = 新会话
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._btn = QPushButton(f"＋ 新会话{_PICKER_ARROW}")
        self._btn.setObjectName("picker")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._open)
        lay.addWidget(self._btn)

    def set_sessions(self, sessions) -> None:
        self._sessions = list(sessions)
        # 默认选中最近一条;没有历史 → 新会话
        self._sel_id = self._sessions[0].id if self._sessions else None
        self._update_btn()

    def selected_id(self) -> str | None:
        return self._sel_id

    def _update_btn(self) -> None:
        if self._sel_id is None:
            self._btn.setText(f"＋ 新会话{_PICKER_ARROW}")
            self._btn.setToolTip("启动后开一个全新会话(点开可选历史会话)")
            return
        s = next((x for x in self._sessions if x.id == self._sel_id), None)
        label = (s.title if (s and s.title) else "(无标题)")
        # 标题先按「留出箭头宽度」省略,再拼上箭头,使 ▾ 始终可见、提示可展开
        fm = QFontMetrics(self._btn.font())
        avail = _PICKER_W - fm.horizontalAdvance(_PICKER_ARROW)
        text = fm.elidedText(f"续:{label}", Qt.TextElideMode.ElideRight, max(0, avail))
        self._btn.setText(f"{text}{_PICKER_ARROW}")
        self._btn.setToolTip(f"启动后续接:{label}(点开可换/新建/删除)")

    def _open(self) -> None:
        pop = _SessionPopup(self._sessions, self)
        pop.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # 关一个销毁一个,别堆积
        pop.picked.connect(self._on_picked)
        pop.delete_requested.connect(self.delete_requested.emit)
        pop.move(self._btn.mapToGlobal(self._btn.rect().bottomLeft()))
        pop.show()

    def _on_picked(self, sid: str) -> None:
        self._sel_id = sid or None
        self._update_btn()


class Panel(QWidget):
    member_clicked = Signal(str)    # 点整条横条:仅运行后置前
    start_requested = Signal(str, object)   # (name, session_id|None):点「确定」后拉起
    add_requested = Signal()
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    open_dir_requested = Signal(str)    # 右键「打开目录」:用资源管理器开成员 cwd
    delete_session_requested = Signal(str, str)  # (name, session_id):删该成员某会话记录

    def __init__(self, members):
        super().__init__()
        self.setObjectName("panel")
        self.setWindowTitle("Claude 花名册")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)  # 不给最大化
        self.setStyleSheet(_QSS)
        self.setFixedWidth(310)             # 固定宽度,只允许竖向随成员数伸缩
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._gos: dict[str, QPushButton] = {}
        self._envs: dict[str, QLabel] = {}     # 每行的「有新消息」小信封
        self._ctitles: dict[str, QLabel] = {}  # 名字下面那行:成员会话的实时窗口标题
        self._ctitle_raw: dict[str, str] = {}  # 标题原文(用于宽度变化时重新省略)
        self._pickers: dict[str, "_SessionPicker"] = {}  # 未运行成员的会话下拉
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
        t = QLabel("Claude 花名册")
        t.setObjectName("title")
        sub = QLabel("点「启动」开 · 答完亮信封+闪烁 · 点横条=该窗最大化/其余最小化")
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
        card.open_dir.connect(lambda n=m.name: self.open_dir_requested.emit(n))
        lay = QHBoxLayout(card)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(10)

        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setMinimumHeight(46)
        accent.setStyleSheet(f"background:{m.color}; border-radius:2px;")
        lay.addWidget(accent)

        # 左侧一列:第一行 名字 + 信封,第二行 该会话的实时窗口标题(小灰字)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        name = QLabel(f"{m.emoji}  @{m.name}")
        name.setObjectName("name")
        name.setStyleSheet(f"color:{m.color};")
        row1.addWidget(name, 0)

        # 「有新消息」小信封:紧跟名字后面,始终占位(固定宽),只切换 ✉/空,闪烁
        env = QLabel()
        env.setObjectName("env")
        env.setFixedWidth(26)
        env.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1.addWidget(env, 0, Qt.AlignmentFlag.AlignVCenter)
        self._envs[m.name] = env
        row1.addStretch(1)
        col.addLayout(row1)

        # 名字下面:成员会话的实时窗口标题(claude 起来后会改成它当前状态)。
        # 空就藏起来不占行高;过长由 set_title 省略号截断。
        ctitle = QLabel()
        ctitle.setObjectName("ctitle")
        ctitle.setVisible(False)
        col.addWidget(ctitle)
        self._ctitles[m.name] = ctitle

        # 同一行位:未运行显示会话下拉(选要续的会话),运行中让位给上面的实时标题
        picker = _SessionPicker()
        picker.delete_requested.connect(
            lambda sid, n=m.name: self.delete_session_requested.emit(n, sid))
        col.addWidget(picker)
        self._pickers[m.name] = picker

        lay.addLayout(col, 1)                   # 这一列吃掉中间空间,把运行键顶到最右

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
        self._ctitles.clear()
        self._ctitle_raw.clear()
        self._pickers.clear()
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
        """确定 → 收起确认条,按下拉选中的会话走启动流程。"""
        self._confirming.discard(name)
        box = self._confirm_boxes.get(name)
        if box is not None:
            box.setVisible(False)
        go = self._gos.get(name)
        if go is not None:
            go.setVisible(True)
        picker = self._pickers.get(name)
        sid = picker.selected_id() if picker is not None else None
        self.start_requested.emit(name, sid)

    def _apply_dot(self, name: str) -> None:
        env = self._envs.get(name)
        if env is None:
            return
        lit = name in self._msg_on and self._blink_on   # 有消息且当前在「亮」相位
        env.setText("✉" if lit else "")

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

    def set_title(self, name: str, text: str) -> None:
        """名字下面那行:成员会话控制台的实时窗口标题。
        空 / 仍是启动占位标题(CCKPT:<name>)→ 藏起来不占行高;过长省略号截断。"""
        lbl = self._ctitles.get(name)
        if lbl is None:
            return
        text = (text or "").strip()
        if text in ("", f"CCKPT:{name}"):
            self._ctitle_raw.pop(name, None)
            lbl.setVisible(False)
            lbl.clear()
            return
        self._ctitle_raw[name] = text
        elided = QFontMetrics(lbl.font()).elidedText(
            text, Qt.TextElideMode.ElideRight, _CTITLE_W)
        lbl.setText(elided)
        lbl.setToolTip(text)
        lbl.setVisible(True)

    def set_sessions(self, name: str, sessions) -> None:
        """给某成员的会话下拉灌数据(列表已按最近活跃倒序);默认选最近一条/无则新会话。"""
        p = self._pickers.get(name)
        if p is not None:
            p.set_sessions(sessions)

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

        picker = self._pickers.get(name)
        if picker is not None:
            picker.setVisible(state == "down")
        if state == "down":
            ctitle = self._ctitles.get(name)
            if ctitle is not None:
                ctitle.setVisible(False)

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
