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

from . import cc_signals, dialogs, store, winman
from .config import Member, load_config, save_config, validate_member
from .controller import Controller
from .launcher import launch, window_title
from .matching import match_pending
from .panel import ICON_PATH, Panel


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
    controller = Controller([m.name for m in members])
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
    last_order: list[str] = []

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
        """刷新每张卡的明暗/运行键 + 状态灯,并把运行中/启动中的卡排到前面。"""
        nonlocal last_order
        pos = {m.name: i for i, m in enumerate(members)}
        states = {m.name: _state_of(m.name) for m in members}
        for m in members:
            panel.set_run_state(m.name, states[m.name])
            panel.set_status(m.name, controller.status(m.name))
        order = sorted(states, key=lambda n: (_RANK[states[n]], pos[n]))
        if order != last_order:
            panel.set_order(order)
            last_order = order

    def start_member(m) -> None:
        """启动一个成员的控制台(不阻塞 UI):立刻标记「启动中」,
        由 _poll_launching 轮询抓窗口句柄(趁 claude 改标题前),抓到再落盘并置前。"""
        launch(m)
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

    def focus_member(name: str) -> None:
        m = by_name.get(name)
        if not m or name in launching:      # 启动中别重复开
            return
        h = _live_hwnd(name)
        if h is not None:
            winman.bring_to_front(h)        # cockpit 启动且窗口还在 → 用缓存句柄置前
        else:
            start_member(m)                 # cockpit 没启动过(或窗口已关)→ 开一个

    # 没有「全部启动」:只能单个启动(用户按节奏点),从源头杜绝齐发挤崩 daemon 的团灭。
    panel.member_clicked.connect(focus_member)

    def _persist_and_rebuild() -> None:
        nonlocal last_order
        try:
            save_config(cfg_path, members)
        except Exception as e:
            QMessageBox.warning(panel, "写回 agents.yaml 失败", str(e))
        controller.set_members([m.name for m in members])
        panel.rebuild(members)
        last_order = []                     # 强制重排(卡片已重建)
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

    panel.add_requested.connect(on_add)
    panel.edit_requested.connect(on_edit)
    panel.delete_requested.connect(on_delete)

    def tick() -> None:
        # 清掉已被关闭的窗口句柄(并落盘),让 ▶ 恢复可启动、缓存不留死句柄
        dead = [n for n, h in hwnds.items() if not winman.is_window(h)]
        if dead:
            for n in dead:
                hwnds.pop(n, None)
            store.save(hwnds)
        pending = match_pending(cc_signals.read_pending_full(), members)
        to_raise = controller.update(pending)
        _refresh_states()                   # 明暗/运行键/状态灯 + 运行中靠前排序
        # 自动弹窗:只置前「cockpit 启动且句柄还在」的窗口,绝不新开。
        # (pending 按 cwd 匹配,可能命中你手动开的同目录 claude;那种 cockpit 没句柄,
        #  此时若走 start_member 就会重复开一个空白窗口——正是这个 bug。)
        for name in to_raise:
            h = _live_hwnd(name)
            if h is not None:
                winman.bring_to_front(h)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000)

    # 启动中的成员单独快轮询(200ms),尽快抓到刚出现的控制台窗口句柄
    launch_timer = QTimer()
    launch_timer.timeout.connect(_poll_launching)
    launch_timer.start(200)

    # 托盘:显隐面板 / 退出(用多只小青蛙图标)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    menu.addAction("显示/隐藏面板",
                   lambda: panel.setVisible(not panel.isVisible()))
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Claude 驾驶舱")
    tray.show()

    # 单实例服务端:后续实例连进来 → 把本面板弹到前台
    def _raise_panel() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.close()
        panel.setWindowState(panel.windowState() & ~Qt.WindowState.WindowMinimized)
        panel.show()
        panel.raise_()
        panel.activateWindow()

    QLocalServer.removeServer(_SINGLE_KEY)   # 清掉上次崩溃残留的名字
    server = QLocalServer(app)
    server.listen(_SINGLE_KEY)
    server.newConnection.connect(_raise_panel)

    _refresh_states()                        # 启动即按缓存句柄点亮/排序,不等首个 tick
    panel.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
