"""入口:装配 配置/面板/控制器/轮询/窗口管理。
python -m claude_cockpit.main  或  claude-cockpit 命令。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMenu, QStyle, QSystemTrayIcon,
)

from . import cc_signals, winman
from .config import load_config
from .controller import Controller
from .launcher import launch, window_title
from .matching import match_pending
from .panel import Panel


def _config_path() -> Path:
    # v1:用项目根 / 当前目录的 agents.yaml;后续可加 --config
    root = Path(__file__).resolve().parent.parent.parent
    p = root / "agents.yaml"
    return p if p.exists() else Path("agents.yaml")


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    members = load_config(_config_path())
    panel = Panel(members)
    controller = Controller([m.name for m in members])
    by_name = {m.name: m for m in members}
    hwnds: dict[str, int] = {}              # name -> 控制台窗口句柄(启动时抓,标题被 claude 改也不怕)

    def _live_hwnd(name: str) -> int | None:
        h = hwnds.get(name)
        return h if (h and winman.is_window(h)) else None

    def start_member(m) -> None:
        """启动一个成员的控制台,并趁 claude 还没改标题抓住窗口句柄缓存起来。"""
        launch(m)
        h = winman.wait_for_title(window_title(m))
        if h:
            hwnds[m.name] = h
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

    # 一次起多个 claude 会挤崩共享的后台服务、把所有会话一起带走(团灭)。
    # 实测:逐个、间隔 ~5 秒启动则安全。所以「全部启动」用 QTimer 错开,绝不齐发。
    LAUNCH_GAP_MS = 5000

    def launch_all() -> None:
        todo = [m for m in members if _live_hwnd(m.name) is None]
        for i, m in enumerate(todo):
            QTimer.singleShot(i * LAUNCH_GAP_MS, lambda m=m: start_member(m))

    panel.member_clicked.connect(focus_member)
    panel.launch_all_clicked.connect(launch_all)

    def tick() -> None:
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

    # 托盘:显隐面板 / 退出(用系统标准图标,保证可见)
    icon: QIcon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
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
