"""办公室画布窗口:把部门地毯和工位摆进一个可滚动缩放的 QGraphicsScene。

对外接口(方法名 + 信号名)与退休的 panel.Panel 完全一致,main.py 只换构造类:
  set_run_state / set_sessions / set_address / set_message / set_title /
  set_speaking / set_order / rebuild / set_always_on_top
  member_clicked / start_requested / add_requested / edit_requested /
  delete_requested / open_dir_requested / copy_address_requested /
  delete_session_requested / stop_speaking_requested

set_order 是空操作:画布上的位置由用户自己摆,排序没有意义。
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QMainWindow, QMenu,
)

from .. import layout as layout_mod
from .. import settings
from .dept_area import DeptAreaItem
from .seat_item import SeatItem
from .theme import CANVAS as BG, GRID, TILE, TILE_ALT

ZOOM_MIN, ZOOM_MAX = 0.5, 2.0
SAVE_DEBOUNCE_MS = 400


def _session_label(s) -> str:
    """会话在下拉里显示成什么。`s` 是 `sessions.Session`(有 .id / .title / .mtime),
    不是 dict——沿用旧面板的口径:没标题就退回「(无标题)」,别把 uuid 甩给用户看。"""
    return s.title if s.title else "(无标题)"


class _Canvas(QGraphicsView):
    """只管画背景网格和缩放;业务全在 OfficeWindow。"""

    def __init__(self, scene, on_zoom):
        super().__init__(scene)
        self._on_zoom = on_zoom
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QBrush(BG))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def drawBackground(self, p, rect):
        """地板:方砖 + 砖缝。

        原来是每 30px 一条线的网格,读起来像方格纸;改成 60px 的砖、隔一块深一档,
        才像铺在地上的地面。
        """
        super().drawBackground(p, rect)
        r = rect.toRect()
        x0 = r.left() - (r.left() % TILE)
        y0 = r.top() - (r.top() % TILE)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(TILE_ALT))
        y = y0
        while y < r.bottom():
            x = x0
            while x < r.right():
                if ((x // TILE) + (y // TILE)) % 2:      # 棋盘式隔一块
                    p.drawRect(x, y, TILE, TILE)
                x += TILE
            y += TILE

        p.setPen(QPen(GRID, 1))
        x = x0
        while x < r.right():
            p.drawLine(x, r.top(), x, r.bottom())
            x += TILE
        y = y0
        while y < r.bottom():
            p.drawLine(r.left(), y, r.right(), y)
            y += TILE

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._on_zoom(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
            e.accept(); return
        super().wheelEvent(e)           # 普通滚轮 = 平移


class OfficeWindow(QMainWindow):
    member_clicked = Signal(str)
    stop_speaking_requested = Signal(str)
    start_requested = Signal(str, object)
    add_requested = Signal()
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    open_dir_requested = Signal(str)
    copy_address_requested = Signal(str)
    delete_session_requested = Signal(str, str)

    def __init__(self, members):
        super().__init__()
        self.setWindowTitle("驾驶舱")
        self.scene = QGraphicsScene(self)
        self.zoom = 1.0
        self.seats: dict[str, SeatItem] = {}
        self.areas: dict[str, DeptAreaItem] = {}
        self._sessions: dict[str, list] = {}
        self._addrs: dict[str, str | None] = {}
        self._canvas = _Canvas(self.scene, self._zoom_by)
        self.setCentralWidget(self._canvas)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.save_layout)
        self._blink_on = True
        self._always_on_top = False      # 与 set_always_on_top 的「值没变就不动」对齐
        self._framed = False             # 镜头是否已对准过办公室(只在首次装配时对)
        self.rebuild(members)

    # ---------- 装配 ----------
    def rebuild(self, members) -> None:
        self.scene.clear()
        self.seats.clear()
        self.areas.clear()
        self._members = list(members)
        # 成员删掉后,它的会话/地址不清掉会一直留着:同名重建时会显示上一个人的
        # 会话地址和选中会话,直到下一个 tick 才被盖掉
        live = {m.name for m in self._members}
        self._sessions = {k: v for k, v in self._sessions.items() if k in live}
        self._addrs = {k: v for k, v in self._addrs.items() if k in live}
        raw = settings.load().get("office") or {}
        lay = layout_mod.ensure(layout_mod.parse(raw), self._members)
        self._lay = lay
        for dept, (x, y, w, h) in lay.areas.items():
            area = DeptAreaItem(dept, w, h)
            area.setPos(x, y)
            area.changed.connect(lambda _n: self._queue_save())
            self.scene.addItem(area)
            self.areas[dept] = area
        for m in self._members:
            seat = SeatItem(m)
            area = self.areas[layout_mod.dept_of(m)]
            seat.setParentItem(area)
            sx, sy = lay.seats[m.name]
            seat.setPos(sx, sy)
            seat.clicked.connect(self.member_clicked.emit)
            seat.speaker_clicked.connect(self.stop_speaking_requested.emit)
            seat.moved.connect(lambda _n: self._queue_save())
            self.seats[m.name] = seat
        self._apply_zoom(lay.zoom)
        self.refit_scene()
        # 窗口尺寸和镜头都只在第一次装配时设:rebuild 每次增删改成员都会跑,
        # 每次都设的话,改一个成员的 emoji 就把窗口缩回存盘尺寸、视角弹回左上角
        if not self._framed:
            self.resize(*lay.window)
            self.focus_content()
            self._framed = True

    def refit_scene(self) -> None:
        """sceneRect 跟着内容长:否则把地毯拖到边界就走不动了,「无限画布」是假的。

        改 sceneRect 会让视图重新锚定滚动位置——拖完工位 400ms 后存盘顺带 refit,
        镜头就自己跳回去了。所以前后把视口中心钉住。
        """
        r = self.scene.itemsBoundingRect()
        if r.isEmpty():
            r = QRectF(0, 0, 800, 600)
        vp = self._canvas.viewport().rect()
        center = self._canvas.mapToScene(vp.center()) if vp.isValid() else None
        self.scene.setSceneRect(r.adjusted(-600, -400, 600, 400))
        if center is not None:
            self._canvas.centerOn(center)

    def focus_content(self) -> None:
        """把视口挪到办公室的左上角。

        sceneRect 比内容大一圈(留出往外拖的余地),视口默认停在 sceneRect 中央,
        结果一开窗看到的是半屏空地、办公室缩在角上。
        """
        r = self.scene.itemsBoundingRect()
        if r.isEmpty():
            return
        # 用 centerOn 而不是直接设滚动条:滚动条的数值起点跟着 sceneRect 走,
        # sceneRect 起点不为零时自己算必偏。
        vp = self._canvas.viewport().size()
        margin = 12
        self._canvas.centerOn(
            r.left() - margin + vp.width() / 2 / self.zoom,
            r.top() - margin + vp.height() / 2 / self.zoom)

    # ---------- 对外接口(与 panel.Panel 同名同签名) ----------
    def set_run_state(self, name: str, state: str) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_run_state(state)

    def set_message(self, name: str, on: bool) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_message(on)

    def set_speaking(self, name: str, on: bool) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_speaking(on)

    def set_title(self, name: str, text: str) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_title(text)

    def set_sessions(self, name: str, sessions) -> None:
        """灌该成员的历史会话;默认选中最近一条(列表首项)。"""
        items = list(sessions or [])
        self._sessions[name] = items
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_subtitle(_session_label(items[0]) if items else "新会话")

    def set_address(self, name: str, addr: str | None) -> None:
        self._addrs[name] = addr

    def set_order(self, names) -> None:
        """空操作:画布上的位置由用户摆放,排序无意义(保留签名给 main.py)。"""

    def set_always_on_top(self, on: bool) -> None:
        """切换「置顶」。改 WindowStaysOnTopHint 后 Windows 需要重新 show() 才生效,
        重开时机会丢失当前显隐/位置,所以只在确有变化且窗口可见时才重开——
        无条件 show() 会把托盘里隐藏着的窗口硬弹出来。"""
        on = bool(on)
        if on == self._always_on_top:
            return
        self._always_on_top = on
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if was_visible:
            self.show()

    def tick_blink(self) -> None:
        """由 main 的 550ms 定时器驱动:有新消息的工位屏幕闪。"""
        self._blink_on = not self._blink_on
        for seat in self.seats.values():
            seat.set_blink(self._blink_on)

    # ---------- 右键菜单 ----------
    def build_menu(self, name: str) -> QMenu:
        """工位的右键菜单。**所有操作都在这儿**——工位上不放按钮(那样画面才干净)。

        单独成方法(不在 contextMenuEvent 里现搭):exec 阻塞,不抽出来没法单测。
        """
        menu = QMenu(self)
        seat = self.seats.get(name)
        sessions = self._sessions.get(name) or []

        if seat is not None and not seat.is_up():
            # 没上班:菜单第一档就是启动。选哪条会话由子菜单点明,
            # 「点一下就开」本身已经是个明确动作,不再另做内联确认。
            menu.addAction("启动(新会话)").triggered.connect(
                lambda: self.start_requested.emit(name, None))
            if sessions:
                # 子菜单显式建、显式挂在父菜单上:用 menu.addMenu("标题") 的话
                # 返回的 QMenu 在 Python 侧没人持有,会被回收掉(C++ 侧就没了)
                sub = QMenu("续接会话", menu)
                for sess in sessions:
                    act = sub.addAction(_session_label(sess))
                    act.triggered.connect(
                        lambda _=False, sid=sess.id:
                        self.start_requested.emit(name, sid))
                menu.addMenu(sub)
                rm = QMenu("删除会话记录", menu)
                for sess in sessions:
                    act = rm.addAction(_session_label(sess))
                    act.triggered.connect(
                        lambda _=False, sid=sess.id:
                        self.delete_session_requested.emit(name, sid))
                menu.addMenu(rm)
                menu._submenus = (sub, rm)      # 防回收
            menu.addSeparator()

        addr = self._addrs.get(name)
        copy = menu.addAction("复制会话地址")
        if addr:
            copy.triggered.connect(lambda: self.copy_address_requested.emit(name))
        else:
            copy.setEnabled(False)
            copy.setToolTip("还没探到这个成员的会话地址(会话没起来或刚启动)")
        menu.addAction("打开目录").triggered.connect(
            lambda: self.open_dir_requested.emit(name))
        menu.addAction("编辑").triggered.connect(
            lambda: self.edit_requested.emit(name))
        menu.addAction("删除").triggered.connect(
            lambda: self.delete_requested.emit(name))
        return menu

    def contextMenuEvent(self, e):
        # e.pos() 是窗口坐标,先落到画布再落到场景(直接用会偏一个画布偏移)
        in_canvas = self._canvas.mapFromGlobal(e.globalPos())
        item = self.scene.itemAt(self._canvas.mapToScene(in_canvas),
                                 self._canvas.transform())
        while item is not None and not isinstance(item, SeatItem):
            item = item.parentItem()
        if isinstance(item, SeatItem):
            self.build_menu(item.name).exec(e.globalPos())
            return
        menu = QMenu(self)
        menu.addAction("新增成员").triggered.connect(self.add_requested.emit)
        menu.exec(e.globalPos())

    # ---------- 内部 ----------
    def _zoom_by(self, factor: float) -> None:
        self._apply_zoom(self.zoom * factor)
        self._queue_save()

    def _apply_zoom(self, z: float) -> None:
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, z))
        self._canvas.resetTransform()
        self._canvas.scale(self.zoom, self.zoom)

    def _queue_save(self) -> None:
        self._save_timer.start()        # 拖动过程中别每帧写盘

    def save_layout(self) -> None:
        lay = layout_mod.Layout(
            areas={n: a.geometry() for n, a in self.areas.items()},
            seats={n: (s.pos().x(), s.pos().y()) for n, s in self.seats.items()},
            window=(self.width(), self.height()),
            zoom=self.zoom,
        )
        s = settings.load()
        s["office"] = layout_mod.dump(lay)
        settings.save(s)
        self.refit_scene()

    def showEvent(self, e):
        super().showEvent(e)
        self._titlebar_theme()

    def _titlebar_theme(self) -> None:
        """让标题栏跟随画布的明暗(DWM)。画布是浅色的,标题栏还黑着很割裂
        ——旧的卡片面板是深色主题所以刷黑,换浅色主题后要跟着改回来。
        20 / 19 是新旧两版 Windows 的属性号,都试一遍;不支持就算了,全吞。"""
        dark = BG.lightness() < 128
        try:
            import ctypes
            hwnd = int(self.winId())
            for attr in (20, 19):
                v = ctypes.c_int(1 if dark else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass

    def closeEvent(self, e):
        self.save_layout()
        super().closeEvent(e)
