"""入口:装配 配置/面板/控制器/轮询/窗口管理。
python -m claude_cockpit.main  或  claude-cockpit 命令。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QSystemTrayIcon,
)

from . import cc_signals, dialogs, sessions, settings, sound, store, winman
from .config import Member, load_config, save_config, validate_member
from .launcher import launch, window_title
from .matching import match_pending, norm_path
from .panel import ICON_PATH, Panel


def newly_pending(prev: set[str], cur: set[str]) -> set[str]:
    """这一轮「新进入有消息」的成员 = 现在 pending 里、上一轮还不在的。
    方向固定 cur - prev(从 pending 消失的不算新);用于决定是否响一声提示音。"""
    return cur - prev


def _config_path() -> Path:
    # v1:用项目根 / 当前目录的 agents.yaml;后续可加 --config
    root = Path(__file__).resolve().parent.parent.parent
    p = root / "agents.yaml"
    return p if p.exists() else Path("agents.yaml")


_SINGLE_KEY = "claude-cockpit-single-instance"


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 单实例:已有实例在跑 → 让它把面板弹到前台,自己退出。
    probe = QLocalSocket()
    probe.connectToServer(_SINGLE_KEY)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return 0
    probe.abort()

    icon = QIcon(str(ICON_PATH)) if ICON_PATH.exists() else QIcon()
    app.setWindowIcon(icon)
    try:                                # 让任务栏也用我们的图标(而非宿主 python 图标)
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("claude-cockpit")
    except Exception:
        pass

    cfg_path = _config_path()
    members = load_config(cfg_path)
    panel = Panel(members)
    by_name = {m.name: m for m in members}
    # name -> 控制台窗口句柄。落盘缓存:退出/重启 cockpit 后载回,凡是句柄仍指向
    # 一个存活的控制台窗口就复用(置前 / 屏蔽 ▶),不必重开;失效的丢弃。
    hwnds: dict[str, int] = {
        n: h for n, h in store.load().items()
        if n in by_name and winman.is_window(h) and winman.is_console_window(h)
    }

    # 正在启动中的成员:name -> 已轮询次数。控制台从点击到出现有 ~3s 空窗,
    # 期间卡片显示「启动中」给反馈;窗口一抓到就转「运行中」。
    launching: dict[str, int] = {}
    member_states: dict[str, str] = {}      # 上一轮各成员状态,用于「刚回到未运行」时刷下拉
    last_order: list[str] = []
    blink_state = {"on": False}         # 托盘图标当前是否处于「灭」的那半拍
    cur_pending: set[str] = set()       # 当前「该你看了」的成员(tick 刷新)
    acked: set[str] = set()             # 已确认过闪烁的成员:列表仍标待处理,只是不再闪
    # 信封「逐个点掉」:点过某张卡 → 它的 ✉ 停闪(本地标记,不删信号文件,
    # 故权限 pending 仍留给小青蛙/真去答时清)。成员离开 pending 后自动复位 → 再来重新闪。
    card_read: set[str] = set()

    # 提示音:有新成员进入 pending 就响一声。prev_pending 记上一轮 pending,
    # None 表示首个 tick → 只播种不响(避免开机时对遗留 pending 一通叫)。
    sound_enabled = settings.load().get("sound_enabled", True)
    prev_pending: set[str] | None = None

    def _ack_blink() -> None:
        """你已经在看了(点了托盘图标 / 点了某张卡)→ 当前 pending 全部标为已确认,
        托盘停闪;但列表里仍保留「待处理」高亮,直到逐个点掉。新 pending 会重新闪。"""
        acked.update(cur_pending)

    def _live_hwnd(name: str) -> int | None:
        h = hwnds.get(name)
        return h if (h and winman.is_window(h)) else None

    def _state_of(name: str) -> str:
        if _live_hwnd(name) is not None:
            return "running"
        if name in launching:
            return "launching"
        return "down"

    _RANK = {"running": 0, "launching": 1, "down": 2}

    def _refresh_states() -> None:
        """刷新每张卡的明暗/运行键,并把运行中/启动中的卡排到前面。"""
        nonlocal last_order
        pos = {m.name: i for i, m in enumerate(members)}
        states = {m.name: _state_of(m.name) for m in members}
        for m in members:
            panel.set_run_state(m.name, states[m.name])
            # 有新消息小信封:窗口还在 且 答完一轮/等你 且 这张卡还没被点掉
            panel.set_message(m.name,
                              states[m.name] == "running"
                              and m.name in cur_pending
                              and m.name not in card_read)
            # 刚回到/初次为「未运行」→ 刷新它的会话下拉(避免每 tick 重扫文件)
            if states[m.name] == "down" and member_states.get(m.name) != "down":
                _refresh_sessions(m.name)
            member_states[m.name] = states[m.name]
        order = sorted(states, key=lambda n: (_RANK[states[n]], pos[n]))
        if order != last_order:
            panel.set_order(order)
            last_order = order

    def start_member(m, session_id=None) -> None:
        """启动一个成员的控制台(不阻塞 UI):立刻标记「启动中」,
        由 _poll_launching 轮询抓窗口句柄(趁 claude 改标题前),抓到再落盘并置前。
        session_id 非空 → 续接用户在下拉里选的那条会话。"""
        launch(m, session_id)
        launching[m.name] = 0
        _refresh_states()                   # 立刻给「启动中」反馈

    def _poll_launching() -> None:
        """每 200ms:给启动中的成员抓窗口句柄;抓到→缓存+置前;超时→放弃。"""
        if not launching:
            return
        done = []
        for name in list(launching):
            m = by_name.get(name)
            if m is None:
                done.append(name)
                continue
            h = winman.find_by_title(window_title(m))
            if h:
                hwnds[name] = h
                store.save(hwnds)
                winman.bring_to_front(h)
                done.append(name)
            else:
                launching[name] += 1
                if launching[name] > 40:    # ~8s 还没出现就放弃,卡片回到未运行
                    done.append(name)
        for name in done:
            launching.pop(name, None)
        if done:
            _refresh_states()

    def _dismiss(name: str) -> None:
        """标记「已读」:清掉该成员(按 cwd 匹配)的所有 turn-ended 信号,
        于是它停闪、出队,队首顶到下一个。权限 pending 不在此清(那得真去答)。"""
        m = by_name.get(name)
        if m is None:
            return
        target = norm_path(m.cwd)
        for rec in cc_signals.read_turn_ended_full():
            if norm_path(rec.get("cwd", "")) == target and rec.get("session_id"):
                cc_signals.clear_turn_ended(rec["session_id"])

    def on_row_click(name: str) -> None:
        """点成员横条:已运行 → 先把其它还活着的控制台最小化(多屏下都最大化时
        没法一眼区分),再把它的控制台最大化弹到眼前 + 标记已读(清 turn-ended)
        + 确认闪烁(托盘停闪)。未运行/启动中无反应。"""
        h = _live_hwnd(name)
        if h is not None:
            _ack_blink()                    # 点了列表 → 托盘停闪
            card_read.add(name)             # 这张卡的 ✉ 也停闪(权限 pending 不删文件,仅本地已读)
            for other in members:           # 只碰缓存里且还活着的句柄,绝不 launch
                if other.name == name:
                    continue
                oh = _live_hwnd(other.name)
                if oh is not None:
                    winman.minimize(oh)
            winman.maximize(h)              # 点谁就把谁最大化(不再自动弹)
            _dismiss(name)
            _refresh_states()               # 立刻让信封消失,不等下一个 tick(~1s)

    def on_start(name: str, session_id=None) -> None:
        """面板里点「启动」→「确定」后发来 (name, session_id):拉起控制台。
        session_id 为下拉选中的会话(None=新会话)。已运行/启动中忽略。
        没有「全部启动」:只能单个启动,从源头杜绝齐发挤崩 daemon 的团灭。"""
        m = by_name.get(name)
        if not m or name in launching or _live_hwnd(name) is not None:
            return
        start_member(m, session_id)

    def _refresh_sessions(name: str) -> None:
        """重新扫该成员 cwd 的历史会话,灌进它的下拉。"""
        m = by_name.get(name)
        if m is None:
            return
        try:
            sess = sessions.list_sessions(m.cwd)
        except Exception:
            sess = []
        panel.set_sessions(name, sess)

    def on_delete_session(name: str, sid: str) -> None:
        """下拉里删某条会话记录(.jsonl)→ 删完立刻刷新该成员下拉。"""
        m = by_name.get(name)
        if m is None:
            return
        sessions.delete_session(m.cwd, sid)
        _refresh_sessions(name)

    panel.member_clicked.connect(on_row_click)
    panel.start_requested.connect(on_start)

    def _persist_and_rebuild() -> None:
        nonlocal last_order
        try:
            save_config(cfg_path, members)
        except Exception as e:
            QMessageBox.warning(panel, "写回 agents.yaml 失败", str(e))
        panel.rebuild(members)
        last_order = []                     # 强制重排(卡片已重建)
        member_states.clear()               # 成员增删改后旧状态作废,让下拉重新刷
        _refresh_states()

    def on_add() -> None:
        data = dialogs.member_dialog(panel)
        if not data:
            return
        try:
            m = Member(name=data["name"], cwd=Path(data["cwd"]), emoji=data["emoji"],
                       color=data["color"], model=data["model"],
                       permission_mode=data["permission_mode"])
            validate_member(m, existing_names=set(by_name))
        except Exception as e:
            QMessageBox.warning(panel, "添加失败", str(e))
            return
        members.append(m)
        by_name[m.name] = m
        _persist_and_rebuild()

    def on_edit(name: str) -> None:
        old = by_name.get(name)
        if old is None:
            return
        data = dialogs.member_dialog(panel, member=old)
        if not data:
            return
        try:
            new = Member(name=name, cwd=Path(data["cwd"]), emoji=data["emoji"],
                         color=data["color"], model=data["model"],
                         permission_mode=data["permission_mode"])
            validate_member(new)            # 名字没变,不查重名
        except Exception as e:
            QMessageBox.warning(panel, "保存失败", str(e))
            return
        members[members.index(old)] = new
        by_name[name] = new
        _persist_and_rebuild()

    def on_delete(name: str) -> None:
        if name not in by_name:
            return
        if len(members) <= 1:
            QMessageBox.warning(panel, "无法删除", "至少要保留一个成员。")
            return
        if QMessageBox.question(panel, "删除成员",
                                f"确定删除 @{name}?(只从面板移除,不动它的窗口/会话)") \
                != QMessageBox.StandardButton.Yes:
            return
        members[:] = [m for m in members if m.name != name]
        by_name.pop(name, None)
        if hwnds.pop(name, None) is not None:
            store.save(hwnds)
        _persist_and_rebuild()

    def on_open_dir(name: str) -> None:
        """右键「打开目录」:用资源管理器打开该成员的 cwd(项目根目录)。"""
        m = by_name.get(name)
        if m is None:
            return
        p = Path(m.cwd)
        if not p.is_dir():
            QMessageBox.warning(panel, "打不开目录", f"目录不存在:\n{p}")
            return
        try:
            import os
            os.startfile(str(p))            # Windows:用资源管理器打开文件夹
        except Exception as e:
            QMessageBox.warning(panel, "打不开目录", str(e))

    panel.add_requested.connect(on_add)
    panel.edit_requested.connect(on_edit)
    panel.delete_requested.connect(on_delete)
    panel.open_dir_requested.connect(on_open_dir)
    panel.delete_session_requested.connect(on_delete_session)

    def tick() -> None:
        # 清掉已被关闭的窗口句柄(并落盘),让 ▶ 恢复可启动、缓存不留死句柄
        dead = [n for n, h in hwnds.items() if not winman.is_window(h)]
        if dead:
            for n in dead:
                hwnds.pop(n, None)
            store.save(hwnds)
        cc_signals.prune_turn_ended()       # 清掉没触发 clear 的陈旧「该你看了」
        # 「该你看了」= 答完一轮(turn-ended,驾驶舱专属) ∪ 等权限(与桌宠共享)
        pending = match_pending(
            cc_signals.read_turn_ended_full() + cc_signals.read_pending_full(),
            members)
        # 提示音:有成员「新进入」pending 就响一声(与信封/托盘开始闪同一时刻)。
        # 首个 tick 只播种 prev_pending 不响,避免开机时对遗留 pending 一通叫。
        nonlocal prev_pending
        if prev_pending is not None:
            if sound_enabled and newly_pending(prev_pending, pending):
                sound.play()
        prev_pending = set(pending)
        cur_pending.clear()
        cur_pending.update(pending)
        acked.intersection_update(pending)  # 不再 pending 的从已确认里移除 → 再来会重新闪
        card_read.intersection_update(pending)  # 同理:答完/清掉后复位,新一轮 pending 重新闪
        # 有消息只显示信封 + 闪托盘,不主动动窗口;窗口最大化交给「点成员」时做。
        _refresh_states()                   # 明暗/运行键 + 信封 + 运行中靠前排序
        # 名字下面那行:用缓存的活句柄直接读控制台标题(claude 起来后会改成它的状态)
        for m in members:
            h = _live_hwnd(m.name)
            panel.set_title(m.name, winman.get_title(h) if h is not None else "")

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000)

    # 启动中的成员单独快轮询(200ms),尽快抓到刚出现的控制台窗口句柄
    launch_timer = QTimer()
    launch_timer.timeout.connect(_poll_launching)
    launch_timer.start(200)

    def _restore_panel() -> None:
        """从最小化/隐藏还原面板并置前。"""
        panel.setWindowState(panel.windowState() & ~Qt.WindowState.WindowMinimized)
        panel.show()
        panel.raise_()
        panel.activateWindow()

    def _panel_away() -> bool:
        return panel.isHidden() or panel.isMinimized()

    # 托盘:显隐面板 / 提示音开关 / 退出(用多只小青蛙图标)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    menu.addAction("显示/隐藏面板",
                   lambda: panel.hide() if not _panel_away() else _restore_panel())

    def _toggle_sound(checked: bool) -> None:
        """勾选/取消「提示音」→ 改运行时开关 + 存盘。"""
        nonlocal sound_enabled
        sound_enabled = checked
        settings.save({"sound_enabled": checked})

    sound_action = menu.addAction("提示音")
    sound_action.setCheckable(True)
    sound_action.setChecked(sound_enabled)
    sound_action.toggled.connect(_toggle_sound)

    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Claude 驾驶舱")
    # 左键/双击托盘图标 → 还原面板 + 停闪(你已经在看了;待处理高亮仍留在列表)
    def _on_tray_activated(r) -> None:
        if r in (QSystemTrayIcon.ActivationReason.Trigger,
                 QSystemTrayIcon.ActivationReason.DoubleClick):
            _ack_blink()
            _restore_panel()

    tray.activated.connect(_on_tray_activated)
    tray.show()

    # 闪烁:有「该你看了」且尚未确认(未点托盘/未点卡)→ 托盘图标在 图标/空 间交替。
    # 点了托盘或某张卡 → 确认停闪(列表仍标待处理);处理掉或新成员答完会再变。
    _empty_icon = QIcon()

    def _blink_tick() -> None:
        if not (cur_pending - acked):       # 没有「未确认的待处理」→ 复位
            if blink_state["on"]:
                blink_state["on"] = False
            tray.setIcon(icon)
            tray.setToolTip("Claude 驾驶舱")
            return
        blink_state["on"] = not blink_state["on"]
        tray.setIcon(_empty_icon if blink_state["on"] else icon)
        tray.setToolTip("有成员答完/等你 · 点我打开")

    blink_timer = QTimer()
    blink_timer.timeout.connect(_blink_tick)
    blink_timer.start(550)

    # 单实例服务端:后续实例连进来 → 把本面板弹到前台
    def _raise_panel() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.close()
        _restore_panel()

    QLocalServer.removeServer(_SINGLE_KEY)   # 清掉上次崩溃残留的名字
    server = QLocalServer(app)
    server.listen(_SINGLE_KEY)
    server.newConnection.connect(_raise_panel)

    _refresh_states()                        # 启动即按缓存句柄点亮/排序,不等首个 tick
    panel.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
