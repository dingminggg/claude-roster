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

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QInputDialog, QMainWindow, QMenu,
)

from .. import layout as layout_mod
from ..config import OPS_NAME
from ..layout import GAP
from .. import settings
from .. import cc_signals, history as history_mod
from .history_popup import HistoryPopup
# 直接 import 函数:set_sessions 的形参就叫 sessions,import 模块会被它遮住
from ..sessions import issue_tag
from .dept_area import DeptAreaItem
from . import bubble, seat_item
from .seat_item import SeatItem
from .walker_item import WalkerItem
from . import theme
from .theme import CANVAS as BG, GRID, TILE, TILE_ALT

# 每个工位自己的大小档位。**整体缩放已经退休**:那是把所有人一起缩,等于没解决
# 「成员多了看不过来」——真正要的是把不常用的单独缩小。
# 机柜现在是**运维桌上的一样家具**(见 office/rack_item.py),不再占格子、
# 不再存坐标——它跟着运维那张工位走。

SEAT_SCALES = (("标准", 1.0), ("小", 0.7), ("更小", 0.5))
SAVE_DEBOUNCE_MS = 400
SCREEN_MS = 120                 # 屏幕上那几行往上滚的帧间隔
WAVE_MS = 180            # 音浪一帧;只在有人朗读时才转,没人说话就停表


def _session_label(s) -> str:
    """会话在下拉里显示成什么。`s` 是 `sessions.Session`(有 .id / .title / .mtime),
    不是 dict——沿用旧面板的口径:没标题就退回「(无标题)」,别把 uuid 甩给用户看。"""
    return s.title if s.title else "(无标题)"


class _Canvas(QGraphicsView):
    """只管画背景网格和缩放;业务全在 OfficeWindow。"""

    def __init__(self, scene):
        super().__init__(scene)
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
    dept_changed = Signal(str, str)      # (成员名, 新部门):拖进哪块地毯就归哪个部门
    stop_requested = Signal(str)         # 「下班」:关掉那个员工的控制台
    copy_text_requested = Signal(str)    # 把一段文本塞进剪贴板(机柜的连接地址)

    def __init__(self, members, services=()):
        """`services` 是本地服务清单(运维桌上那台机柜)。**默认为空**:构造函数里不读盘
        不探活,真正的清单由 main 传进来——否则一建窗口就凭空多出一块运维部门区,
        测试和离屏自检都得跟着迁就。"""
        super().__init__()
        self.setWindowTitle("办公室")
        self.scene = QGraphicsScene(self)
        self.seats: dict[str, SeatItem] = {}
        self._services = list(services)
        self.areas: dict[str, DeptAreaItem] = {}
        self._sessions: dict[str, list] = {}
        self._addrs: dict[str, str | None] = {}
        # 对话记录:上次读到的文件签名(mtime,size)+ 每个员工的已读水位。
        # 一秒一轮全量读那个 JSONL 没必要,签名没变就跳过这一轮。
        self._hist_sig = None
        self._hist: list[dict] = []
        self._seen: dict[str, float] = dict(settings.load().get("seen_messages") or {})
        self._canvas = _Canvas(self.scene)
        self.setCentralWidget(self._canvas)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.save_layout)
        self._blink_on = True
        self._screen_timer = QTimer(self)    # 屏幕滚动:有人在忙才跑
        self._screen_timer.setInterval(SCREEN_MS)
        self._screen_timer.timeout.connect(self._tick_screen)
        self._wave_timer = QTimer(self)      # 音浪:朗读时才跑,免得白烧 CPU
        self._wave_timer.setInterval(WAVE_MS)
        self._wave_timer.timeout.connect(self._tick_wave)
        self._extra_depts: set[str] = set()   # 用户手工建的地毯(可能还没人)
        self._always_on_top = False      # 与 set_always_on_top 的「值没变就不动」对齐
        self._framed = False             # 镜头是否已对准过办公室(只在首次装配时对)
        self._walkers: list[WalkerItem] = []   # 正在跑腿送信的小人
        self._away: dict[str, int] = {}       # 谁离座了(同一个人可能连送几趟)
        self.rebuild(members)

    # ---------- 装配 ----------
    def rebuild(self, members) -> None:
        # **先清名单、再 clear 场景**:scene.clear() 会删掉 walker,触发它的 destroyed
        # 回调,那个回调会回头找发送方工位——这时 seats 里还挂着已经被删掉的 C++ 对象,
        # 一碰就 RuntimeError(踩过)。
        self.seats.clear()
        self.areas.clear()
        self._walkers.clear()
        self._away.clear()
        self.scene.clear()
        self._members = list(members)
        # 成员删掉后,它的会话/地址不清掉会一直留着:同名重建时会显示上一个人的
        # 会话地址和选中会话,直到下一个 tick 才被盖掉
        live = {m.name for m in self._members}
        self._sessions = {k: v for k, v in self._sessions.items() if k in live}
        self._addrs = {k: v for k, v in self._addrs.items() if k in live}
        # `_seen`(对话记录的已读水位)**故意不跟着筛**:同名员工重建时留着水位
        # 才对——筛掉的话,他以前看过的那些消息会被当成新的再亮一次红点。
        raw = settings.load().get("office") or {}
        parsed = layout_mod.parse(raw)
        self._extra_depts |= {d for d in parsed.depts}
        parsed.depts = sorted(self._extra_depts | set(parsed.depts))
        # 机柜不参与布局:它是运维**桌上的一样家具**,不占格子也不存坐标。
        # (老 settings.json 里可能还躺着 `svc:` 开头的键——那是它当独立图元那阵子
        # 留下的,`layout.ensure` 会丢掉。)
        lay = layout_mod.ensure(parsed, self._members)
        self._lay = lay
        for dept, (x, y, w, h) in lay.areas.items():
            area = DeptAreaItem(dept, w, h)
            area.setPos(x, y)
            area.changed.connect(self._on_area_changed)
            self.scene.addItem(area)
            self.areas[dept] = area
        for m in self._members:
            seat = SeatItem(m)
            area = self.areas[layout_mod.dept_of(m)]
            seat.setParentItem(area)
            sx, sy = lay.seats[m.name]
            seat.setPos(sx, sy)
            seat.setScale(lay.scales.get(m.name, 1.0))
            seat.clicked.connect(self.member_clicked.emit)
            seat.speaker_clicked.connect(self.stop_speaking_requested.emit)
            seat.phone_clicked.connect(self.open_history)
            seat.moved.connect(self._on_seat_dropped)
            self.seats[m.name] = seat
        ops = self.seats.get(OPS_NAME)      # 机柜摆在运维桌上
        if ops is not None:
            ops.set_services(self._services)
            # 运维没有文件堆:那叠纸的意思是「几条历史会话、右键挑一条接着聊」,
            # 他不走这条路;腾出来的地方正好给机柜。
            ops.set_papers_enabled(False)
        # 重建后的工位立刻带上手机(否则要等下一轮 tick 才冒出来):
        # 这里 _seen / _addrs 都已经就位——前者在 __init__ 里 rebuild 之前读好,
        # 后者在本方法开头按活着的员工筛过一遍。
        self.refresh_history(force=True)
        self.refit_scene()
        # 窗口尺寸和镜头都只在第一次装配时设:rebuild 每次增删改成员都会跑,
        # 每次都设的话,改一个成员的 emoji 就把窗口缩回存盘尺寸、视角弹回左上角
        if not self._framed:
            self.resize(*lay.window)
            self._framed = True

    def _area_at(self, seat) -> str | None:
        """工位中心落在哪块地毯上。压着两块边界时取 z 值最上面的那块。"""
        center = seat.mapToScene(seat.boundingRect().center())
        hits = [n for n, a in self.areas.items()
                if a.sceneBoundingRect().contains(center)]
        return hits[-1] if hits else None

    def _on_seat_dropped(self, name: str) -> None:
        """拖完工位:落在别的地毯上就换部门(写回 agents.yaml 由 main 负责),
        然后**咬到最近的空槽位**——松手自动对齐,不用自己对得准。"""
        seat = self.seats.get(name)
        if seat is not None:
            landed = self._area_at(seat)
            here = seat.parentItem()
            if name == OPS_NAME:        # 运维的部门锁死:拖到哪儿都还是运维部门的人
                landed = None
            if landed and self.areas.get(landed) is not here:
                area = self.areas[landed]
                scene_pos = seat.scenePos()
                seat.setParentItem(area)                 # 换爸爸,位置保持不动
                seat.setPos(area.mapFromScene(scene_pos))
                self.dept_changed.emit(name, landed)
            self._snap(seat)
        self._queue_save()

    def _on_area_changed(self, name: str) -> None:
        """地毯拖完/拉伸完:位置咬到地砖网格,边缘就不会歪在砖缝中间。"""
        area = self.areas.get(name)
        if area is not None:
            g = theme.TILE
            area.setPos(round(area.pos().x() / g) * g,
                        round(area.pos().y() / g) * g)
        self._queue_save()

    def _snap(self, seat) -> None:
        """把工位咬到它所在地毯的最近空槽位(同地毯里别人占的格子跳过)。"""
        area = seat.parentItem()
        if not isinstance(area, DeptAreaItem):
            return
        siblings = list(self.seats.values())
        taken = [(s.pos().x(), s.pos().y()) for s in siblings
                 if s is not seat and s.parentItem() is area]
        x, y = layout_mod.snap_to_slot((seat.pos().x(), seat.pos().y()),
                                       (area.w, area.h), taken)
        seat.setPos(x, y)

    def add_area(self, name: str, at=None) -> None:
        """新建一块部门地毯。人还没拖进来时它是空的——空地毯要能存住,
        否则「先建区、再拖人」的第一步就没了(layout.depts 记这份名单)。"""
        name = (name or "").strip()
        if not name or name in self.areas:
            return
        area = DeptAreaItem(name, *layout_mod.AREA_DEFAULT)
        if at is None:
            r = self.scene.itemsBoundingRect()
            at = (r.left(), r.bottom() + layout_mod.GAP)
        area.setPos(*at)
        area.changed.connect(self._on_area_changed)
        self.scene.addItem(area)
        self.areas[name] = area
        self._extra_depts.add(name)
        self.refit_scene()
        self._queue_save()

    def rename_area(self, old: str, new: str) -> None:
        new = (new or "").strip()
        if not new or new == old or new not in ("",) and new in self.areas:
            return
        area = self.areas.pop(old, None)
        if area is None:
            return
        area.name = new
        self.areas[new] = area
        area.update()
        if old in self._extra_depts:
            self._extra_depts.discard(old)
        self._extra_depts.add(new)
        # 这块地毯上的人跟着改部门(写回 yaml 由 main 做)
        for seat_name, seat in self.seats.items():
            if seat.parentItem() is area:
                self.dept_changed.emit(seat_name, new)
        self._queue_save()

    def remove_area(self, name: str) -> None:
        """删掉一块空地毯。上面还有人就不动——人得先拖走,免得默默把谁的部门清了。"""
        area = self.areas.get(name)
        if area is None or any(s.parentItem() is area for s in self.seats.values()):
            return
        self.scene.removeItem(area)
        self.areas.pop(name, None)
        self._extra_depts.discard(name)
        self.refit_scene()
        self._queue_save()

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
        # 只留一圈窄边:留一大片空地的话,东西会被越拖越散,最后一眼看不全
        self.scene.setSceneRect(r.adjusted(-60, -40, 60, 40))
        if center is not None:
            self._canvas.centerOn(center)

    # ---------- 运维桌上那台机柜 ----------
    def set_service_states(self, states: dict) -> None:
        """喂一整份服务状态(由 main 的后台探测回来)→ 运维桌上那台机柜的柜灯。

        **状态一变他就在工位上说一句**(全绿报平安、否则点名是哪几个不对):柜灯只
        说明「有没有事」,是哪一层还得凑近看——那句话才是这条信息真正有用的地方。
        不变就不说:每轮都冒一次气泡,一分钟十二次,成了噪音。
        """
        ops = self.seats.get(OPS_NAME)
        if ops is None or not ops.has_rack():
            return
        before = ops.service_report()
        ops.set_service_states(states)
        after = ops.service_report()
        if after != before and ops.is_up():     # 没上班就不说话(空椅子上冒气泡太灵异)
            ops.say(after)

    # ---------- 工位上说一句 ----------
    def say(self, name: str, text: str, sticky: bool = False) -> bool:
        """让某个员工在工位上冒个气泡说一句(和会话间发消息那个气泡同一份画法)。

        `sticky=True` 的不自己收、点一下才关——点工位会朗读这一轮的回复,同时把
        那句结论印出来,自动消失的话人一抬头就没了。没上班的不说话(空椅子上冒
        气泡太灵异),说不出来就回 False,调用方不用管。
        """
        seat = self.seats.get(name)
        if seat is None or not text or not seat.is_up():
            return False
        seat.say(text, sticky=sticky,
                 lines=seat_item.SAY_LINES if sticky else bubble.MAX_LINES)
        return True

    def set_run_state(self, name: str, state: str) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_run_state(state)
        self._sync_screen_timer()

    def _sync_screen_timer(self) -> None:
        """有人在干活才开表:一屋子闲人不该每 120ms 醒一次(同音浪那条的口径)。"""
        working = any(s.is_working() for s in self.seats.values())
        if working and not self._screen_timer.isActive():
            self._screen_timer.start()
        elif not working and self._screen_timer.isActive():
            self._screen_timer.stop()

    def _tick_screen(self) -> None:
        for seat in self.seats.values():
            seat.advance_scroll()

    def set_message(self, name: str, on: bool) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_message(on)

    def set_speaking(self, name: str, on: bool) -> None:
        seat = self.seats.get(name)
        if seat is not None:
            seat.set_speaking(on)
        self._sync_wave_timer()

    def _sync_wave_timer(self) -> None:
        """有人在朗读才开表:没人说话的时候不该每 180ms 醒一次。"""
        talking = any(s._speaking and s.is_up() for s in self.seats.values())
        if talking and not self._wave_timer.isActive():
            self._wave_timer.start()
        elif not talking and self._wave_timer.isActive():
            self._wave_timer.stop()

    def _tick_wave(self) -> None:
        for seat in self.seats.values():
            seat.advance_wave()

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
            seat.set_session_count(len(items))
            seat.set_subtitle(_session_label(items[0]) if items else "新会话")
            # 最上面那张纸上印最近这条会话的 issue 号(抠不出来就留白)
            seat.set_session_tag(issue_tag(items[0].title) if items else "")

    def set_address(self, name: str, addr: str | None) -> None:
        self._addrs[name] = addr

    def refresh_history(self, force: bool = False) -> None:
        """刷新每张桌上那部手机:几条记录、几条没看过。由 main 的 1s tick 调。

        **文件签名没变就不重读**——记录文件可以长到几百 K,一秒读一遍纯属白烧。
        """
        sig = cc_signals.history_stat()
        if not force and sig == self._hist_sig:
            return
        self._hist_sig = sig
        self._hist = cc_signals.read_history()
        self._apply_history()

    def _apply_history(self) -> None:
        """把手上这份记录铺到每张桌上的手机(几条 / 其中几条没看过)。

        单独一个方法:水位一推,红点该当场灭,但那用的还是刚读进来的同一份记录
        ——没必要为此再读一遍盘。
        """
        for m in self._members:
            entries = history_mod.for_member(self._hist, m, self._addrs, self._members)
            seat = self.seats.get(m.name)
            if seat is not None:
                seat.set_history(
                    len(entries),
                    history_mod.unread_count(entries, self._seen.get(m.name, 0.0)))

    def open_history(self, name: str):
        """点手机(或右键那一项):弹记录窗 + 把这个人的已读水位推到最新。"""
        m = next((x for x in self._members if x.name == name), None)
        if m is None:
            return None
        # **只读一遍文件**:先刷新(顺带把 self._hist 换成最新的那份),再从这份
        # 里组装 entries——分两次读同一个文件有可能拿到不一致的两份。
        self.refresh_history(force=True)
        entries = history_mod.for_member(self._hist, m, self._addrs, self._members)
        if entries:
            # 顺序要紧:**先算出 entries(含未读数)、再推水位**,反过来的话
            # 这一轮的未读数会被自己刚写的水位抹平。
            self._seen[name] = max(e.at for e in entries)
            self._save_seen()
            self._apply_history()       # 红点立刻灭,不等下一轮 tick(也不再读一遍盘)
        # 窗以办公室为父:WA_DeleteOnClose 只管关掉时销毁 C++ 那半边,**在此之前**
        # 得有人持有它——父子关系就是那个持有者,不然出了这个函数就没人引用了。
        pop = HistoryPopup(name, entries, self)
        seat = self.seats.get(name)
        if seat is not None:
            at = self._canvas.mapToGlobal(
                self._canvas.mapFromScene(seat.mapToScene(seat.r_phone().center())))
            pop.move(at.x() + 12, at.y() + 12)
        pop.show()
        return pop

    def _save_seen(self) -> None:
        """已读水位立刻落盘(用户点一次才写一次,不用防抖)。

        和 save_layout 一样是「现读 settings → 只改自己那一段 → 写回」:两边都**当场**
        重读,谁也不揣着旧 dict,所以不会把对方刚写的那段吃掉。
        失败静默——水位丢了最多多亮一次红点,不值得为它弹错误框。
        """
        try:
            s = settings.load()
            s["seen_messages"] = self._seen
            settings.save(s)
        except Exception:
            pass

    def _menu_phone(self, name: str) -> QMenu:
        """点桌上那部手机:只有一件事——把对话记录翻出来看。
        (左键点它是同一件事的快捷方式,同音响。)"""
        menu = QMenu(self)
        menu.addAction("查看对话记录").triggered.connect(lambda: self.open_history(name))
        return menu

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
        """由 main 的 550ms 定时器驱动:有新消息的工位屏幕闪,异常的机柜柜灯闪。
        两者共用同一拍——画面上同时有两种节奏在闪就乱了。"""
        self._blink_on = not self._blink_on
        for seat in self.seats.values():
            seat.set_blink(self._blink_on)


    # ---------- 送信的小人 ----------
    MAX_WALKERS = 4          # 同时最多几个在跑:再多就是一屋子人乱窜,反而看不出谁找谁

    def send_walker(self, from_name: str, to_name: str, text: str = "") -> bool:
        """`from_name` 给 `to_name` 发了消息 → 放一个小人走过去说一句再走回来,
        `text` 是消息正文(显示在气泡里)。

        两头都得是画布上**认得的**员工;自己给自己发不演(那是 SendMessage 到自己,
        画出来是原地抖一下,没意义)。
        """
        a, b = self.seats.get(from_name), self.seats.get(to_name)
        if a is None or b is None or a is b:
            return False
        return self._launch_walker(from_name, self._walk_path(a, b), text)

    def _launch_walker(self, from_name: str, path, text: str) -> bool:
        """放一个小人上路(送信和巡检共用):记账、把工位画成空椅子、走完自己摘掉。"""
        seat = self.seats.get(from_name)
        if seat is None or len(self._walkers) >= self.MAX_WALKERS:
            return False
        w = WalkerItem(seat.color, path, text)
        self.scene.addItem(w)
        self._walkers.append(w)
        self._away[from_name] = self._away.get(from_name, 0) + 1
        seat.set_away(True)                 # 人走了,工位上那把椅子空着
        w.destroyed.connect(lambda *_: self._drop_walker(w, from_name))
        return True

    @staticmethod
    def _lane_y(seat) -> float:
        """工位前面那条过道的 y:工位包围盒下沿再往前半个间距。

        工位的下半截是空地(桌子在上半截),所以从椅子**往下**走一定不会穿过桌子;
        走到这条线上再横着走,就是沿着过道走。
        """
        return seat.mapToScene(seat.boundingRect()).boundingRect().bottom() + GAP / 2

    def _walk_path(self, a, b) -> list[QPointF]:
        """排一条不穿桌子的路线:退到本工位前的过道 → 沿过道横着走 → 拐进对方工位。

        两头不在同一排时,竖着那一段走在对方那一列上——中间要是正好还坐着别人,
        会从人家工位边上蹭过去。这只是个装饰动画,不值得为此做真的寻路。
        """
        start = a.mapToScene(a.chair_pos())
        # 落点偏到对方椅子左前方一点:直接站在人家椅子上太挤,也会把对方盖住
        end = b.mapToScene(b.chair_pos() + QPointF(-26, 10))
        lane_a, lane_b = self._lane_y(a), self._lane_y(b)
        path = [start, QPointF(start.x(), lane_a)]
        if abs(lane_a - lane_b) > 1:            # 不在同一排:先横着到对方那一列,再竖着换排
            path.append(QPointF(end.x(), lane_a))
            path.append(QPointF(end.x(), lane_b))
        else:
            path.append(QPointF(end.x(), lane_a))
        path.append(end)
        return path

    def _drop_walker(self, w, from_name: str) -> None:
        try:
            self._walkers.remove(w)
        except ValueError:
            pass
        # 连送几趟时按计数回座,不能第一趟回来就把人画回去(那会和还在路上的那个撞)
        n = self._away.get(from_name, 0) - 1
        if n > 0:
            self._away[from_name] = n
            return
        self._away.pop(from_name, None)
        seat = self.seats.get(from_name)
        if seat is not None:
            try:
                seat.set_away(False)
            except RuntimeError:
                pass        # 面板正在拆(工位的 C++ 对象已经删了),回不回座都无所谓了

    # ---------- 右键菜单 ----------
    def build_menu(self, name: str, where: str = "seat") -> QMenu:
        """工位的右键菜单。**按落点分发**——点谁就是对谁下命令:

            person → 上班 / 下班          files → 会话历史(续接 / 删除)
            phone  → 对话记录(会话间收发的那些消息)
            其余   → 这个成员本身(地址 / 目录 / 编辑 / 删除)

        单独成方法(不在 contextMenuEvent 里现搭):exec 阻塞,不抽出来没法单测。
        """
        if where == "person":
            return self._menu_person(name)
        if where == "files":
            return self._menu_files(name)
        if where == "phone":
            return self._menu_phone(name)
        return self._menu_member(name)

    def build_rack_menu(self) -> QMenu:
        """机柜的右键菜单。**只读**——没有启停:启停服务要管理员权限,而且在一块
        状态看板上误点一下就把 MySQL 关了,代价太大。

        一台柜子装着好几个服务,所以「复制连接地址」是个子菜单(一层一条)。
        子菜单必须用 `QMenu(标题, 父菜单)` 显式建:直接 `addMenu("标题")` 返回的
        QMenu 在 Python 侧没人持有,会被回收掉、点开就报对象已删除(踩过)。
        """
        menu = QMenu(self)
        svcs = self._services
        sub = QMenu("复制连接地址", menu)
        for svc in svcs:
            sub.addAction(f"{svc.name}  {svc.address}").triggered.connect(
                lambda _=False, a=svc.address: self.copy_text_requested.emit(a))
        sub.setEnabled(bool(svcs))
        menu.addMenu(sub)
        return menu

    def _menu_person(self, name: str) -> QMenu:
        """点人:管他上下班。"""
        menu = QMenu(self)
        seat = self.seats.get(name)
        up = seat is not None and seat.is_up()
        if up:
            menu.addAction("下班(关掉控制台)").triggered.connect(
                lambda: self.stop_requested.emit(name))
        else:
            menu.addAction("上班(新会话)").triggered.connect(
                lambda: self.start_requested.emit(name, None))
            if self._sessions.get(name):
                menu.addAction("上班(接着上次那条)").triggered.connect(
                    lambda: self.start_requested.emit(
                        name, self._sessions[name][0].id))
        return menu

    def _menu_files(self, name: str) -> QMenu:
        """点桌上那叠文件:一张纸 = 一条历史会话。"""
        menu = QMenu(self)
        seat = self.seats.get(name)
        up = seat is not None and seat.is_up()
        subs = []
        for title, sink in (("接着这条继续",
                             lambda sid: self.start_requested.emit(name, sid)),
                            ("删除这条记录",
                             lambda sid: self.delete_session_requested.emit(name, sid))):
            if title.startswith("接着") and up:
                continue        # 已经在跑的成员不给「再开一个」,防重复启动
            sub = QMenu(title, menu)
            for sess in self._sessions.get(name) or []:
                act = sub.addAction(_session_label(sess))
                act.triggered.connect(
                    lambda _=False, sid=sess.id, f=sink: f(sid))
            menu.addMenu(sub)
            subs.append(sub)
        menu._submenus = tuple(subs)     # 防回收:子菜单在 Python 侧得有人持有
        return menu

    def set_seat_scale(self, name: str, k: float) -> None:
        """把某个工位单独缩放:成员多了,不常用的缩小,常用的留原样。"""
        seat = self.seats.get(name)
        if seat is None:
            return
        seat.setScale(k)
        self.refit_scene()
        self._queue_save()

    def _menu_member(self, name: str) -> QMenu:
        """点工位其余地方:这个成员本身的事 + 这个工位显示多大。"""
        menu = QMenu(self)
        seat = self.seats.get(name)
        size = QMenu("大小", menu)
        for label, k in SEAT_SCALES:
            act = size.addAction(label)
            act.setCheckable(True)
            act.setChecked(seat is not None and abs(seat.scale() - k) < 0.01)
            act.triggered.connect(
                lambda _=False, kk=k: self.set_seat_scale(name, kk))
        menu.addMenu(size)
        menu._submenus = (size,)         # 防回收
        menu.addSeparator()
        addr = self._addrs.get(name)
        copy = menu.addAction("复制会话地址")
        if addr:
            copy.triggered.connect(lambda: self.copy_address_requested.emit(name))
        else:
            copy.setEnabled(False)
            copy.setToolTip("还没探到这个员工的会话地址(会话没起来或刚启动)")
        menu.addAction("打开目录").triggered.connect(
            lambda: self.open_dir_requested.emit(name))
        edit = menu.addAction("编辑")
        rm = menu.addAction("删除")
        if name == OPS_NAME:
            # 运维是运维部门的**固定岗位**,不是你临时拉的人:面板里不给改也不给删
            # (要换目录就去 agents.yaml 改那一行)。**置灰而不是隐藏**——隐藏了
            # 用户会以为功能没了,同「复制会话地址」那条的口径。
            for act in (edit, rm):
                act.setEnabled(False)
                act.setToolTip("运维是固定岗位,改 agents.yaml 里那一行")
        else:
            edit.triggered.connect(lambda: self.edit_requested.emit(name))
            rm.triggered.connect(lambda: self.delete_requested.emit(name))
        return menu

    def build_canvas_menu(self, area: str | None, scene_pos=None) -> QMenu:
        """画布上的右键菜单:空白处能新建部门;点在地毯上还能改名 / 删掉。

        和 build_menu 一样单独成方法——exec 阻塞,不抽出来没法单测。
        """
        menu = QMenu(self)
        menu.addAction("新增员工").triggered.connect(self.add_requested.emit)
        at = (scene_pos.x(), scene_pos.y()) if scene_pos is not None else None
        menu.addAction("新建部门区").triggered.connect(
            lambda: self._ask_new_area(at))
        if area:
            menu.addSeparator()
            menu.addAction(f"重命名「{area}」").triggered.connect(
                lambda: self._ask_rename_area(area))
            occupied = any(s.parentItem() is self.areas.get(area)
                           for s in self.seats.values())
            rm = menu.addAction(f"删除「{area}」")
            if occupied:
                rm.setEnabled(False)
                rm.setToolTip("这个部门区里还有人:先把工位拖到别的部门再删")
            else:
                rm.triggered.connect(lambda: self.remove_area(area))
        return menu

    def _ask_new_area(self, at=None) -> None:
        name, ok = QInputDialog.getText(self, "新建部门区", "部门名")
        if ok:
            self.add_area(name, at)

    def _ask_rename_area(self, old: str) -> None:
        name, ok = QInputDialog.getText(self, "重命名部门", "新的部门名", text=old)
        if ok:
            self.rename_area(old, name)

    def contextMenuEvent(self, e):
        # e.pos() 是窗口坐标,先落到画布再落到场景(直接用会偏一个画布偏移)
        in_canvas = self._canvas.mapFromGlobal(e.globalPos())
        item = self.scene.itemAt(self._canvas.mapToScene(in_canvas),
                                 self._canvas.transform())
        while item is not None and not isinstance(item, SeatItem):
            item = item.parentItem()
        if isinstance(item, SeatItem):
            where = item.hit(item.mapFromScene(self._canvas.mapToScene(in_canvas)))
            if where == "rack":
                self.build_rack_menu().exec(e.globalPos())
                return
            self.build_menu(item.name, where).exec(e.globalPos())
            return
        scene_pos = self._canvas.mapToScene(in_canvas)
        area = next((n for n, a in self.areas.items()
                     if a.sceneBoundingRect().contains(scene_pos)), None)
        self.build_canvas_menu(area, scene_pos).exec(e.globalPos())

    # ---------- 内部 ----------
    def _queue_save(self) -> None:
        self._save_timer.start()        # 拖动过程中别每帧写盘

    def save_layout(self) -> None:
        lay = layout_mod.Layout(
            areas={n: a.geometry() for n, a in self.areas.items()},
            seats={n: (s.pos().x(), s.pos().y()) for n, s in self.seats.items()},
            scales={n: s.scale() for n, s in self.seats.items() if s.scale() != 1.0},
            depts=sorted(self.areas),
            window=(self.width(), self.height()),
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
