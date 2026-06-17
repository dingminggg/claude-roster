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

_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_by_title(needle: str) -> int | None:
    """返回标题里包含 needle 的第一个可见窗口句柄;找不到返回 None。"""
    found: list[int] = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if needle in buf.value:
            found.append(hwnd)
            return False  # 停止枚举
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return found[0] if found else None


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


def bring_to_front(hwnd: int) -> None:
    """还原 + 置前。用 AttachThreadInput 绕过后台进程置前限制;失败退化为闪任务栏。"""
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
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
    except Exception:
        pass


def minimize(hwnd: int) -> None:
    try:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    except Exception:
        pass
