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

BG = QColor("#181a1f")
GRID = QColor("#20232a")
ZOOM_MIN, ZOOM_MAX = 0.5, 2.0
SAVE_DEBOUNCE_MS = 400


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
        super().drawBackground(p, rect)
        p.setPen(QPen(GRID, 1))
        step = 30
        r = rect.toRect()
        x = r.left() - (r.left() % step)
        while x < r.right():
            p.drawLine(x, r.top(), x, r.bottom())
            x += step
        y = r.top() - (r.top() % step)
        while y < r.bottom():
            p.drawLine(r.left(), y, r.right(), y)
            y += step

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
        self._picked: dict[str, str | None] = {}
        self._addrs: dict[str, str | None] = {}
        self._canvas = _Canvas(self.scene, self._zoom_by)
        self.setCentralWidget(self._canvas)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.save_layout)
        self._blink_on = True
        self.rebuild(members)

    # ---------- 装配 ----------
    def rebuild(self, members) -> None:
        self.scene.clear()
        self.seats.clear()
        self.areas.clear()
        self._members = list(members)
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
            seat.confirmed.connect(self._on_confirmed)
            seat.picker_clicked.connect(self._on_picker)
            seat.speaker_clicked.connect(self.stop_speaking_requested.emit)
            seat.moved.connect(lambda _n: self._queue_save())
            self.seats[m.name] = seat
        self.resize(*lay.window)
        self._apply_zoom(lay.zoom)
        self.refit_scene()

    def refit_scene(self) -> None:
        """sceneRect 跟着内容长:否则把地毯拖到边界就走不动了,「无限画布」是假的。"""
        r = self.scene.itemsBoundingRect()
        if r.isEmpty():
            r = QRectF(0, 0, 800, 600)
        self.scene.setSceneRect(r.adjusted(-600, -400, 600, 400))

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
        self._picked[name] = items[0].get("id") if items else None
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_subtitle(items[0].get("title") or "上次会话"
                              if items else "新会话")

    def set_address(self, name: str, addr: str | None) -> None:
        self._addrs[name] = addr

    def set_order(self, names) -> None:
        """空操作:画布上的位置由用户摆放,排序无意义(保留签名给 main.py)。"""

    def set_always_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()

    def tick_blink(self) -> None:
        """由 main 的 550ms 定时器驱动:有新消息的工位屏幕闪。"""
        self._blink_on = not self._blink_on
        for seat in self.seats.values():
            seat.set_blink(self._blink_on)

    # ---------- 右键菜单 ----------
    def build_menu(self, name: str) -> QMenu:
        """单独成方法(不在 contextMenuEvent 里现搭):exec 阻塞,不抽出来没法单测。"""
        menu = QMenu(self)
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
    def _on_confirmed(self, name: str) -> None:
        self.start_requested.emit(name, self._picked.get(name))

    def _on_picker(self, name: str) -> None:
        """会话下拉:选一条 / 新会话 / 删一条。"""
        items = self._sessions.get(name) or []
        menu = QMenu(self)
        new = menu.addAction("新会话")
        new.triggered.connect(lambda: self._pick(name, None, "新会话"))
        for s in items:
            title = s.get("title") or s.get("id")
            act = menu.addAction(title)
            act.triggered.connect(
                lambda _=False, sid=s.get("id"), t=title: self._pick(name, sid, t))
            rm = menu.addAction(f"  删除「{title}」")
            rm.triggered.connect(
                lambda _=False, sid=s.get("id"):
                self.delete_session_requested.emit(name, sid))
        menu.exec(self._canvas.mapToGlobal(
            self._canvas.mapFromScene(self.seats[name].scenePos())))

    def _pick(self, name: str, sid: str | None, title: str) -> None:
        self._picked[name] = sid
        self.seats[name].set_subtitle(title)

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

    def closeEvent(self, e):
        self.save_layout()
        super().closeEvent(e)
