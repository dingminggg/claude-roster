"""入口:装配 配置/面板/控制器/轮询/窗口管理。
python -m claude_cockpit.main  或  claude-cockpit 命令。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QSystemTrayIcon,
)

from . import cc_signals, dialogs, peers, sessions, settings, sound, store, winman
from .config import Member, load_config, save_config, validate_member
from .launcher import launch, window_title
from .matching import match_pending, norm_path, sessions_for_cwd
from .panel import ICON_PATH, UP_STATES, Panel, TrayPopup


def newly_pending(prev: set[str], cur: set[str]) -> set[str]:
    """这一轮「新进入有消息」的成员 = 现在 pending 里、上一轮还不在的。
    方向固定 cur - prev(从 pending 消失的不算新);用于决定是否响一声提示音。"""
    return cur - prev


def tray_popup_decision(has_pending: bool, over_icon: bool, over_popup: bool,
                        visible: bool, misses: int, miss_limit: int) -> str:
    """托盘悬停浮层的显隐判定(纯逻辑,Qt 几何由调用方算好传进来)。
    返回 "show"(该显示) / "hide"(该隐藏) / "none"(保持不动)。
    - 没有 pending → 在显示就 hide,否则 none。
    - 光标在图标上、浮层还没显示 → show。
    - 浮层在显示、光标既不在图标也不在浮层、且连续 miss 达阈值 → hide(给宽限避免缝隙闪烁)。
    - 其余保持不动。"""
    if not has_pending:
        return "hide" if visible else "none"
    if over_icon and not visible:
        return "show"
    if visible and not over_icon and not over_popup and misses >= miss_limit:
        return "hide"
    return "none"


def _config_path() -> Path:
    # v1:用项目根 / 当前目录的 agents.yaml;后续可加 --config
    root = Path(__file__).resolve().parent.parent.parent
    p = root / "agents.yaml"
    return p if p.exists() else Path("agents.yaml")


_SINGLE_KEY = "claude-cockpit-single-instance"
# 点开某会话时,让 TTS 朗读它最新一条已备好的回复(激活即播,没开就一直等)。
_TTS_SCRIPT = Path.home() / ".claude" / "hooks" / "tts_stop.py"


def _pid_alive(pid: int) -> bool:
    """Windows:进程是否还活着(判断某条朗读信号是否仍在播;死了就清孤儿,🔊 不常亮)。"""
    if pid <= 0:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    except Exception:
        return False


def _run_tts(*extra) -> None:
    """后台跑 tts_stop.py <extra...>(不弹窗、不阻塞 UI)。"""
    if not _TTS_SCRIPT.exists():
        return
    try:
        import subprocess
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, str(_TTS_SCRIPT), *[str(a) for a in extra]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags,
        )
    except Exception:
        pass


def speak_on_activate(cwd) -> None:
    """点开成员卡时触发:调 tts_stop.py 合成并朗读该 cwd 最新一条回复(存在才播)。"""
    _run_tts("activate", cwd)


def stop_speaking() -> None:
    """点朗读中的 🔊:停止当前播放(tts_stop.py stop 会杀播放进程并清 🔊 信号)。"""
    _run_tts("stop")


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
    hwnds: dict[str, int] = store.dedupe({
        n: h for n, h in store.load().items()
        if n in by_name and winman.is_window(h) and winman.is_console_window(h)
    })

    # 正在启动中的成员:name -> 已轮询次数。控制台从点击到出现有 ~3s 空窗,
    # 期间卡片显示「启动中」给反馈;窗口一抓到就转「运行中」。
    launching: dict[str, int] = {}
    # 探到的同机 Claude 会话(成员名 -> Peer),tick 刷新。给两处用:
    # 运行键的 忙碌中/空闲,以及右键「复制会话地址」。探不到就是空的,一切照旧。
    cur_peers: dict[str, "peers.Peer"] = {}
    member_states: dict[str, str] = {}      # 上一轮各成员状态,用于「刚回到未运行」时刷下拉
    last_order: list[str] = []
    blink_state = {"on": False}         # 托盘图标当前是否处于「灭」的那半拍
    cur_pending: set[str] = set()       # 当前「该你看了」的成员(tick 刷新)
    cur_speaking: set[str] = set()      # 当前「正在朗读」的成员(TTS 播放中,tick 刷新)
    # 「逐个点掉」:点过某张卡 / 在悬停浮层里点过某成员 → 它的 ✉ 停闪,且不再计入托盘闪烁
    # (本地标记,不删信号文件,故权限 pending 仍留到真去答时清)。成员离开 pending 后自动复位。
    # 统一口径:托盘闪烁、卡片信封、悬停浮层都看 cur_pending - card_read,逐个点掉、全点完才停。
    card_read: set[str] = set()

    # 悬停浮层:tray_popup 为当前显示的实例(None=没显示);hover_misses 累计「光标
    # 离开图标和浮层」的连续拍数,达到 _HOVER_MISS_LIMIT 才隐藏(给图标↔浮层缝隙宽限)。
    tray_popup: TrayPopup | None = None
    hover_misses = {"n": 0}
    _HOVER_MISS_LIMIT = 2

    # 提示音:有新成员进入 pending 就响一声。prev_pending 记上一轮 pending,
    # None 表示首个 tick → 只播种不响(避免开机时对遗留 pending 一通叫)。
    _settings = settings.load()
    sound_enabled = _settings.get("sound_enabled", True)
    always_on_top = _settings.get("always_on_top", True)
    panel.set_always_on_top(always_on_top)
    prev_pending: set[str] | None = None

    def _live_hwnd(name: str) -> int | None:
        h = hwnds.get(name)
        return h if (h and winman.is_window(h)) else None

    def _state_of(name: str) -> str:
        if _live_hwnd(name) is not None:
            # 窗口活着 = 起来了;再看探到的会话状态细分忙/闲。
            # 探不到(会话 json 还没落、格式变了)→ 兜底「运行中」,不退化成未运行。
            p = cur_peers.get(name)
            status = p.status if p is not None else ""
            return status if status in ("busy", "idle") else "running"
        if name in launching:
            return "launching"
        return "down"

    # 排序只分「起来了 / 启动中 / 未运行」三档:忙和闲同档,别让卡片因为忙闲切换乱跳。
    _RANK = {"running": 0, "busy": 0, "idle": 0, "launching": 1, "down": 2}

    def _refresh_states() -> None:
        """刷新每张卡的明暗/运行键,并把运行中/启动中的卡排到前面。"""
        nonlocal last_order
        pos = {m.name: i for i, m in enumerate(members)}
        states = {m.name: _state_of(m.name) for m in members}
        for m in members:
            panel.set_run_state(m.name, states[m.name])
            # 有新消息小信封:窗口还在 且 答完一轮/等你 且 这张卡还没被点掉
            panel.set_message(m.name,
                              states[m.name] in UP_STATES
                              and m.name in cur_pending
                              and m.name not in card_read)
            # 正在朗读:窗口还在 且 TTS 在播这个会话 → 卡上显示 🔊
            panel.set_speaking(m.name,
                               states[m.name] in UP_STATES
                               and m.name in cur_speaking)
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
            # 排除其它成员已持有的活句柄:绝不让两个成员指向同一个控制台
            taken = {oh for on, oh in hwnds.items() if on != name and winman.is_window(oh)}
            h = winman.find_by_title(window_title(m), exclude=taken)
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
        for sid in sessions_for_cwd(cc_signals.read_turn_ended_full(), m.cwd):
            cc_signals.clear_turn_ended(sid)

    def _purge_signals(name: str) -> None:
        """成员的控制台窗口已被关掉:它两条通道的信号都成了孤儿(Stop/UserPromptSubmit
        不会再触发清除),按 cwd 把 turn-ended + pending 全清掉。否则托盘会一直空闪却无处
        可点——卡片已置灰(点了 no-op)、悬停浮层点它也 no-op,只能干等 30min prune。"""
        m = by_name.get(name)
        if m is None:
            return
        for sid in sessions_for_cwd(cc_signals.read_turn_ended_full(), m.cwd):
            cc_signals.clear_turn_ended(sid)
        for sid in sessions_for_cwd(cc_signals.read_pending_full(), m.cwd):
            cc_signals.clear_pending(sid)

    def on_row_click(name: str) -> None:
        """点成员横条:已运行 → 先把其它还活着的控制台最小化(多屏下都最大化时
        没法一眼区分),再把它的控制台最大化弹到眼前 + 标记已读(清 turn-ended)。
        标记已读会把这成员从托盘闪烁里摘掉;多个待处理时逐个点掉、全点完才停闪。
        未运行/启动中无反应。"""
        h = _live_hwnd(name)
        if h is not None:
            card_read.add(name)             # 标记已读:✉ 停闪 + 不再计入托盘闪烁(权限 pending 不删文件)
            for other in members:           # 只碰缓存里且还活着的句柄,绝不 launch
                if other.name == name:
                    continue
                oh = _live_hwnd(other.name)
                if oh is not None:
                    winman.minimize(oh)
            winman.maximize(h)              # 点谁就把谁最大化(不再自动弹)
            _dismiss(name)
            _refresh_states()               # 立刻让信封消失,不等下一个 tick(~1s)
            m = by_name.get(name)           # 激活即朗读该会话最新一条回复(存在才播)
            if m is not None:
                speak_on_activate(m.cwd)

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
    panel.stop_speaking_requested.connect(lambda _name: stop_speaking())

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

    def on_copy_address(name: str) -> None:
        """右键「复制会话地址」:把会话名塞进剪贴板,用户可直接拿去给别的会话发消息。"""
        p = cur_peers.get(name)
        if p is None:                       # 菜单项本来就置灰,这里只是兜底
            return
        QGuiApplication.clipboard().setText(p.name)

    panel.add_requested.connect(on_add)
    panel.edit_requested.connect(on_edit)
    panel.delete_requested.connect(on_delete)
    panel.open_dir_requested.connect(on_open_dir)
    panel.copy_address_requested.connect(on_copy_address)
    panel.delete_session_requested.connect(on_delete_session)

    def tick() -> None:
        # 清掉已被关闭的窗口句柄(并落盘),让 ▶ 恢复可启动、缓存不留死句柄
        dead = [n for n, h in hwnds.items() if not winman.is_window(h)]
        if dead:
            for n in dead:
                hwnds.pop(n, None)
                _purge_signals(n)       # 关窗即清孤儿信号:托盘别再空闪(死窗口没处可点)
            store.save(hwnds)
        cc_signals.prune_turn_ended()       # 清掉没触发 clear 的陈旧「该你看了」
        # 同样清陈旧 pending:会话在权限确认中被关掉时 Stop/UserPromptSubmit 不会触发清除,
        # 孤儿 pending 文件会永远留着、每次重启都假装「有消息」。按时效裁掉(同 turn-ended 30min)。
        cc_signals.prune_stale(1800)
        # 「该你看了」= 答完一轮(turn-ended,驾驶舱专属) ∪ 等权限(与桌宠共享)
        pending = match_pending(
            cc_signals.read_turn_ended_full() + cc_signals.read_pending_full(),
            members)
        # 提示音:有成员「新进入」pending 就响一声(与信封/托盘开始闪同一时刻)。
        # 首个 tick 只播种 prev_pending 不响,避免开机时对遗留 pending 一通叫。
        nonlocal prev_pending
        newly = newly_pending(prev_pending, pending) if prev_pending is not None else set()
        if newly and sound_enabled:
            sound.play()
        # 前台会话免点播报:新进 pending 的成员,若它的控制台此刻正是前台窗口——
        # 用户已经在盯着它,不需要再点一下卡片才触发朗读(那一下纯属多余,且用户不会点
        # 自己已经在看的会话,导致这类会话永远等不到激活播放)。tts_stop.py 的 activate
        # 本身按「有没有未播的新音频」判断,没有就静默返回,重复调用无副作用。
        if newly:
            fg = winman.get_foreground_hwnd()
            if fg is not None:
                for name in newly:
                    m = by_name.get(name)
                    if m is not None and _live_hwnd(name) == fg:
                        speak_on_activate(m.cwd)
        prev_pending = set(pending)
        cur_pending.clear()
        cur_pending.update(pending)
        card_read.intersection_update(pending)  # 不再 pending 的复位 → 新一轮 pending 重新闪/亮
        # 「正在朗读」:TTS 播放期间写 speaking/<cwd>.json {cwd,pid};pid 活着才显示 🔊,
        # 死了(播完/被杀)就删孤儿。先裁超龄的,再按 pid 存活过滤。
        cc_signals.prune_speaking()
        live_speaking = []
        for rec in cc_signals.read_speaking_full():
            if _pid_alive(int(rec.get("pid") or 0)):
                live_speaking.append(rec)
            else:
                cc_signals.remove_speaking_file(rec.get("cwd", "") or "")
        cur_speaking.clear()
        cur_speaking.update(match_pending(live_speaking, members))
        # 探同机 Claude 会话:拿会话名(发消息的地址)和忙/闲。必须在 _refresh_states
        # 之前刷,_state_of 要用它细分忙/闲。读不到就清空 → 一切退回原来的「运行中」。
        cur_peers.clear()
        cur_peers.update(peers.match_peers(peers.read_peers(), members))
        for m in members:
            p = cur_peers.get(m.name)
            panel.set_address(m.name, p.name if p is not None else None)
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
        settings.save({**settings.load(), "sound_enabled": checked})

    sound_action = menu.addAction("提示音")
    sound_action.setCheckable(True)
    sound_action.setChecked(sound_enabled)
    sound_action.toggled.connect(_toggle_sound)

    def _toggle_always_on_top(checked: bool) -> None:
        """勾选/取消「窗口置顶」→ 改面板窗口标志 + 存盘。"""
        nonlocal always_on_top
        always_on_top = checked
        panel.set_always_on_top(checked)
        settings.save({**settings.load(), "always_on_top": checked})

    top_action = menu.addAction("窗口置顶")
    top_action.setCheckable(True)
    top_action.setChecked(always_on_top)
    top_action.toggled.connect(_toggle_always_on_top)

    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Claude 驾驶舱")
    # 左键/双击托盘图标 → 还原面板(顺手关掉悬停浮层)。不停闪:闪烁只由「逐个点掉成员」清。
    def _on_tray_activated(r) -> None:
        if r in (QSystemTrayIcon.ActivationReason.Trigger,
                 QSystemTrayIcon.ActivationReason.DoubleClick):
            _hide_tray_popup()
            _restore_panel()

    tray.activated.connect(_on_tray_activated)
    tray.show()

    # 闪烁:有「该你看了」且还没逐个点掉(cur_pending - card_read 非空)→ 托盘图标在 图标/空 间交替。
    # 点掉某成员(点卡 / 悬停浮层里点)→ 它从闪烁集合摘除;全部点完才停闪。悬停、点托盘都不停闪。
    _empty_icon = QIcon()

    def _blink_tick() -> None:
        if not (cur_pending - card_read):   # 没有「未点掉的待处理」→ 复位
            if blink_state["on"]:
                blink_state["on"] = False
            tray.setIcon(icon)
            tray.setToolTip("Claude 驾驶舱")
            return
        blink_state["on"] = not blink_state["on"]
        tray.setIcon(_empty_icon if blink_state["on"] else icon)
        # 闪烁时清掉系统托盘原生 tooltip:悬停就只显示我们的成员浮层,不再蹦出旧提示文字
        tray.setToolTip("")

    blink_timer = QTimer()
    blink_timer.timeout.connect(_blink_tick)
    blink_timer.start(550)

    # 托盘悬停浮层:有消息时把光标移到托盘图标上方 → 弹出「谁有消息」可点列表,
    # 点一行 = 等价点成员卡(on_row_click:最大化该控制台/其余最小化/标记已读)。
    # QSystemTrayIcon 无原生 hover 事件,只能 150ms 轮询光标对 tray.geometry()。
    def _hide_tray_popup() -> None:
        nonlocal tray_popup
        if tray_popup is not None:
            tray_popup.close()
            tray_popup.deleteLater()
            tray_popup = None
        hover_misses["n"] = 0

    def _on_popup_pick(name: str) -> None:
        _hide_tray_popup()
        on_row_click(name)              # 复用:死窗口时它本就安全 no-op

    def _show_tray_popup() -> None:
        nonlocal tray_popup
        # 只列「还没点掉」的待处理成员(与托盘闪烁/卡片信封同一口径)
        rows = [(m.name, m.emoji, m.color)
                for m in members if m.name in cur_pending and m.name not in card_read]
        if not rows:
            return
        _hide_tray_popup()              # 防御:先清掉可能残留的旧实例
        pop = TrayPopup(rows)
        pop.picked.connect(_on_popup_pick)
        pop.adjustSize()
        r = tray.geometry()
        if r.isNull() or r.isEmpty():   # 几何失准(溢出区等)→ 不弹,避免错位到屏角
            pop.deleteLater()
            return
        x = r.center().x() - pop.width() // 2   # 水平居中对齐图标(不右对齐)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry() if screen is not None else None
        above_y = r.top() - pop.height() - 6
        # 默认贴图标正上方;若上方放不下(任务栏在顶/图标贴屏顶)→ 落到图标下方
        if g is not None and above_y < g.top():
            y = r.bottom() + 6
        else:
            y = above_y
        if g is not None:               # 夹紧进所在屏幕可见区,别出屏
            x = max(g.left(), min(x, g.right() - pop.width()))
            y = max(g.top(), min(y, g.bottom() - pop.height()))
        pop.move(x, y)
        pop.show()
        tray_popup = pop
        # 悬停弹出不停闪:闪烁只在「逐个点掉成员」时清(见 _blink_tick 用 card_read)

    def _hover_tick() -> None:
        pos = QCursor.pos()
        r = tray.geometry()
        geo_ok = not (r.isNull() or r.isEmpty())   # 折叠进「隐藏图标」溢出区时几何失准
        over_icon = geo_ok and r.contains(pos)
        visible = tray_popup is not None and tray_popup.isVisible()
        over_popup = False
        if visible:
            pg = tray_popup.geometry().adjusted(-8, -8, 8, 8)   # 外扩容差,跨缝隙不丢
            over_popup = pg.contains(pos)
        if visible and not over_icon and not over_popup:
            hover_misses["n"] += 1
        else:
            hover_misses["n"] = 0
        # has_pending 用「还没点掉」的口径:全点掉后悬停不再弹空浮层
        action = tray_popup_decision(bool(cur_pending - card_read), over_icon, over_popup,
                                     visible, hover_misses["n"], _HOVER_MISS_LIMIT)
        if action == "show":
            _show_tray_popup()
        elif action == "hide":
            _hide_tray_popup()

    hover_timer = QTimer()
    hover_timer.timeout.connect(_hover_tick)
    hover_timer.start(150)

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
