"""入口:装配 配置/面板/控制器/轮询/窗口管理。
python -m claude_cockpit.main  或  claude-cockpit 命令。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
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


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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

    def _live_hwnd(name: str) -> int | None:
        h = hwnds.get(name)
        return h if (h and winman.is_window(h)) else None

    def start_member(m) -> None:
        """启动一个成员的控制台,并趁 claude 还没改标题抓住窗口句柄缓存起来(并落盘)。"""
        launch(m)
        h = winman.wait_for_title(window_title(m))
        if h:
            hwnds[m.name] = h
            store.save(hwnds)
            winman.bring_to_front(h)

    def focus_member(name: str) -> None:
        m = by_name.get(name)
        if not m:
            return
        h = _live_hwnd(name)
        if h is not None:
            winman.bring_to_front(h)        # cockpit 启动且窗口还在 → 用缓存句柄置前
        else:
            start_member(m)                 # cockpit 没启动过(或窗口已关)→ 开一个

    # 没有「全部启动」:只能单个启动(用户按节奏点),从源头杜绝齐发挤崩 daemon 的团灭。
    panel.member_clicked.connect(focus_member)

    def _persist_and_rebuild() -> None:
        try:
            save_config(cfg_path, members)
        except Exception as e:
            QMessageBox.warning(panel, "写回 agents.yaml 失败", str(e))
        controller.set_members([m.name for m in members])
        panel.rebuild(members)

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
        for m in members:
            panel.set_status(m.name, controller.status(m.name))
            # 运行中(cockpit 启动且窗口还在)→ 屏蔽其 ▶ 启动键;窗口关掉则恢复
            panel.set_running(m.name, _live_hwnd(m.name) is not None)
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

    # 托盘:显隐面板 / 退出(用多只小青蛙图标)
    tray = QSystemTrayIcon(icon, app)
    menu = QMenu()
    menu.addAction("显示/隐藏面板",
                   lambda: panel.setVisible(not panel.isVisible()))
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Claude 驾驶舱")
    tray.show()

    panel.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
