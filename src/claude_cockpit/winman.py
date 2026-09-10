"""Win32(ctypes)窗口管理:按标题找控制台、置前、最小化。仅 Windows。
所有失败吞掉——拿不到窗口不该让面板崩。"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3

_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def title_matches(title: str, needle: str) -> bool:
    """标题里是否有「完整的」needle:命中处后面必须是结尾或空白。
    纯子串匹配会让 CCKPT:fad 抓到 CCKPT:fad-3 的窗口(两成员共用一个句柄的历史 bug),
    所以名字后面紧跟 -/数字/字母 一律不算。前后允许宿主加的装饰(如 "Administrator: ")。"""
    start = 0
    while True:
        i = title.find(needle, start)
        if i < 0:
            return False
        j = i + len(needle)
        if j >= len(title) or title[j].isspace():
            return True
        start = i + 1


def find_by_title(needle: str, exclude: set[int] | frozenset[int] = frozenset()) -> int | None:
    """返回标题完整包含 needle 的第一个可见窗口句柄;找不到返回 None。
    exclude:已归属其它成员的句柄,跳过——防止把别人的控制台再抓一遍。"""
    found: list[int] = []

    def cb(hwnd, _):
        if hwnd in exclude or not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if title_matches(buf.value, needle):
            found.append(hwnd)
            return False  # 停止枚举
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return found[0] if found else None


def get_title(hwnd: int) -> str:
    """读已知句柄的窗口标题(用于显示;不参与判活)。读不到返回空串。
    用缓存的活句柄直接取,不枚举窗口、不违反「只认句柄」约束。"""
    try:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def get_foreground_hwnd() -> int | None:
    """当前前台(用户正盯着的)窗口句柄;拿不到返回 None。"""
    try:
        h = user32.GetForegroundWindow()
        return h if h else None
    except Exception:
        return None


def is_window(hwnd: int) -> bool:
    """句柄是否仍指向一个存在的窗口(用户关掉控制台后即失效)。"""
    try:
        return bool(user32.IsWindow(hwnd))
    except Exception:
        return False


_CONSOLE_CLASSES = {
    "ConsoleWindowClass",              # 经典 conhost
    "CASCADIA_HOSTING_WINDOW_CLASS",   # Windows Terminal
    "PseudoConsoleWindow",
}


def is_console_window(hwnd: int) -> bool:
    """是不是控制台窗口。用于复用落盘句柄时的保险:句柄可能被无关窗口复用,
    若窗口类明显不是控制台就拒绝。读不到类名则给予信任(返回 True)。"""
    try:
        buf = ctypes.create_unicode_buffer(128)
        n = user32.GetClassNameW(hwnd, buf, 128)
        if n <= 0:
            return True
        return buf.value in _CONSOLE_CLASSES
    except Exception:
        return True


def wait_for_title(needle: str, timeout: float = 8.0, interval: float = 0.1) -> int | None:
    """启动控制台后按标题轮询抓窗口句柄。窗口一出现(零点几秒)就抓到;超时返回 None。
    超时给得很宽(默认 8s),配合启动命令里 ~3s 的标题停顿,抓取毫无时间压力。"""
    end = time.time() + timeout
    while True:
        h = find_by_title(needle)
        if h:
            return h
        if time.time() >= end:
            return None
        time.sleep(interval)


def _force_foreground(hwnd: int) -> None:
    """用 AttachThreadInput 绕过后台进程置前限制,把窗口拉到最前并取得焦点。"""
    fg = user32.GetForegroundWindow()
    cur_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    for tid in {target_tid, fg_tid}:
        if tid and tid != cur_tid:
            user32.AttachThreadInput(cur_tid, tid, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    for tid in {target_tid, fg_tid}:
        if tid and tid != cur_tid:
            user32.AttachThreadInput(cur_tid, tid, False)


def bring_to_front(hwnd: int) -> None:
    """还原 + 置前。失败退化为闪任务栏。"""
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        _force_foreground(hwnd)
    except Exception:
        pass


def maximize(hwnd: int) -> None:
    """最大化 + 置前。成员答完一轮时把它的控制台铺满弹到眼前。"""
    try:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        _force_foreground(hwnd)
    except Exception:
        pass


def minimize(hwnd: int) -> None:
    try:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    except Exception:
        pass


WM_CLOSE = 0x0010


def close_window(hwnd: int) -> None:
    """请求关掉这个控制台窗口(「下班」)。

    发 WM_CLOSE 而不是杀进程:等同于用户点窗口右上角的 ×,cmd 会正常收尾,
    claude 也有机会把 transcript 落盘(不落盘就 --resume 不回来了)。
    关不掉(窗口没响应)就算了,别升级成强杀。
    """
    try:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception:
        pass
