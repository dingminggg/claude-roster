# claude-cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 Windows 原生轻量面板,按成员清单拉起 N 个真 `claude` 控制台;靠 Claude Code 的 hook 信号(复用 desk-buddy 的 pending 目录)自动把需要权限确认的控制台窗口置前,面板显示状态、点行置前;可与 desk-buddy 一键同启。

**Architecture:** PySide6 应用(包 `claude_cockpit`,仿 desk-buddy 布局)。纯逻辑模块(config / 信号匹配 / 启动命令 / 轮询状态机)走 pytest TDD;GUI 面板(panel.py)与 Win32 窗口管理(winman.py)走手动验证。信号检测复用 desk-buddy 的 `cc_signals`(复制其模块,指向同一 `~/.claude/data/desk-buddy/pending/`),hooks 沿用 desk-buddy 安装的那套。

**Tech Stack:** Python ≥3.11、PySide6、PyYAML、pytest;Win32 via ctypes(不引 pywin32)。仅 Windows。

---

## 文件结构

```
claude-cockpit/
  pyproject.toml                  # 包定义 + deps + pytest 配置
  agents.yaml                     # 自带成员清单样例
  src/claude_cockpit/
    __init__.py                   # __version__
    config.py                     # Member + load_config + validate
    cc_signals.py                 # 复制自 desk-buddy,读 pending 目录
    matching.py                   # pending(cwd) → member 的纯匹配逻辑
    launcher.py                   # claude_flags / build_launch_command / launch
    winman.py                     # Win32:按标题找窗口、置前、最小化
    controller.py                 # 轮询状态机(纯逻辑:谁该被置前)
    panel.py                      # PySide6 面板 + 托盘
    main.py                       # 入口:装配一切 + QTimer 轮询
  tests/
    test_config.py
    test_matching.py
    test_launcher.py
    test_controller.py
```

职责边界:`controller.py` 是**纯逻辑**——输入「当前 pending 集合 + 成员列表 + 上一轮状态」,输出「本轮要置前哪些成员、各成员新状态」,不碰 Qt / Win32;`main.py` 把它和 QTimer / winman / panel 接起来。这样状态机可单测。

---

## Task 1: 项目脚手架

**Files:** Create `pyproject.toml`, `src/claude_cockpit/__init__.py`, `agents.yaml`, `tests/__init__.py`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-cockpit"
dynamic = ["version"]
description = "Windows 原生面板:调度多个真 claude 控制台,按 CC hook 信号自动置前"
requires-python = ">=3.11"
dependencies = ["PySide6>=6.6", "PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.dynamic]
version = {attr = "claude_cockpit.__version__"}

[tool.setuptools.packages.find]
where = ["src"]

[project.scripts]
claude-cockpit = "claude_cockpit.main:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: 写 `src/claude_cockpit/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: 写 `agents.yaml`(样例,2 个成员)**

```yaml
# claude-cockpit 成员清单。每个成员 = 一个真 claude 控制台窗口。
agents:
  - name: demo
    cwd: C:\Users\LQ\PhpstormProjects\claude-cockpit
    emoji: "🏪"
    color: "#2980b9"
    permission_mode: default
```

- [ ] **Step 4: 创建空 `tests/__init__.py`**(内容为空)。

- [ ] **Step 5: 建 venv 装依赖**

Run:
```
cd /c/Users/LQ/PhpstormProjects/claude-cockpit
py -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```
Expected: 安装成功,末尾 `Successfully installed ... claude-cockpit-0.1.0`。

- [ ] **Step 6: 跑空测试确认 pytest 就绪**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `no tests ran`(或收集到 0 个),无 import 错误。

- [ ] **Step 7: Commit**

```
git add -A && git commit -m "scaffold: pyproject + 包骨架 + 样例 agents.yaml"
```

---

## Task 2: config.py(成员配置)

**Files:** Create `src/claude_cockpit/config.py`, `tests/test_config.py`

- [ ] **Step 1: 写失败测试 `tests/test_config.py`**

```python
import textwrap
import pytest
from claude_cockpit.config import Member, load_config

def _write(tmp_path, text):
    p = tmp_path / "agents.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p

def test_load_basic(tmp_path):
    cwd = tmp_path  # 用存在的目录
    p = _write(tmp_path, f"""
        agents:
          - name: shop
            cwd: {cwd}
            emoji: "🏪"
            color: "#2980b9"
            permission_mode: default
    """)
    members = load_config(p)
    assert len(members) == 1
    m = members[0]
    assert isinstance(m, Member)
    assert m.name == "shop"
    assert str(m.cwd) == str(cwd)
    assert m.emoji == "🏪"
    assert m.permission_mode == "default"

def test_bad_name_rejected(tmp_path):
    p = _write(tmp_path, f"""
        agents:
          - name: "bad name!"
            cwd: {tmp_path}
    """)
    with pytest.raises(ValueError):
        load_config(p)

def test_missing_cwd_rejected(tmp_path):
    p = _write(tmp_path, """
        agents:
          - name: ghost
            cwd: C:\\no\\such\\dir\\xyz123
    """)
    with pytest.raises(ValueError):
        load_config(p)

def test_duplicate_names_rejected(tmp_path):
    p = _write(tmp_path, f"""
        agents:
          - name: dup
            cwd: {tmp_path}
          - name: dup
            cwd: {tmp_path}
    """)
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL(`ModuleNotFoundError: claude_cockpit.config`)。

- [ ] **Step 3: 写 `src/claude_cockpit/config.py`**

```python
"""agents.yaml 加载与校验。成员 = 一个真 claude 控制台。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[\w-]+$")


@dataclass
class Member:
    name: str
    cwd: Path
    emoji: str = "🤖"
    color: str = "#3b82f6"
    model: str | None = None
    permission_mode: str = "default"


def _validate(m: Member) -> None:
    if not NAME_RE.match(m.name):
        raise ValueError(f"成员名只能用字母/数字/下划线/连字符: {m.name!r}")
    if not m.cwd.is_dir():
        raise ValueError(f"成员 {m.name} 的 cwd 不存在: {m.cwd}")


def load_config(path: str | Path = "agents.yaml") -> list[Member]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    members: list[Member] = []
    for item in raw.get("agents", []):
        m = Member(
            name=item["name"],
            cwd=Path(str(item["cwd"]).strip().strip('"')),
            emoji=item.get("emoji", "🤖"),
            color=item.get("color", "#3b82f6"),
            model=item.get("model"),
            permission_mode=item.get("permission_mode", "default"),
        )
        _validate(m)
        members.append(m)
    if not members:
        raise ValueError("agents.yaml 里至少要有一个成员")
    names = [m.name for m in members]
    if len(set(names)) != len(names):
        raise ValueError(f"成员名重复: {names}")
    return members
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: PASS(4 passed)。

- [ ] **Step 5: Commit**

```
git add -A && git commit -m "feat: config.py 成员加载与校验 + 测试"
```

---

## Task 3: cc_signals.py + matching.py(信号读取 + 对到成员)

**Files:** Create `src/claude_cockpit/cc_signals.py`(复制自 desk-buddy), `src/claude_cockpit/matching.py`, `tests/test_matching.py`

- [ ] **Step 1: 复制 desk-buddy 的 cc_signals**

把 `C:\Users\LQ\PhpstormProjects\desk-buddy\src\desk_buddy\cc_signals.py` 原样复制到
`src/claude_cockpit/cc_signals.py`(它已指向 `~/.claude/data/desk-buddy/pending/`,与 desk-buddy
共享同一目录,正是我们要的)。**新增**一个返回完整记录(含 cwd)的函数,供按 cwd 匹配——
在文件末尾追加:

```python
def read_pending_full() -> list[dict]:
    """返回每条 pending 的完整记录 [{session_id, message, cwd, at}, ...]。
    匹配成员要用 cwd,而 read_pending() 只给显示名,故另开此函数。"""
    d = pending_dir()
    if not d.exists():
        return []
    out: list[dict] = []
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("session_id"):
            out.append(data)
    return out
```

- [ ] **Step 2: 写失败测试 `tests/test_matching.py`**

```python
from pathlib import Path
from claude_cockpit.config import Member
from claude_cockpit.matching import match_pending

def _m(name, cwd):
    return Member(name=name, cwd=Path(cwd))

def test_match_by_cwd_exact(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    members = [_m("alpha", a), _m("beta", b)]
    pending = [{"session_id": "s1", "cwd": str(a)}]
    assert match_pending(pending, members) == {"alpha"}

def test_match_normalizes_separators_and_case(tmp_path):
    a = tmp_path / "Proj"; a.mkdir()
    members = [_m("alpha", a)]
    # 分隔符/大小写/尾斜杠都不该影响匹配
    weird = str(a).replace("\\", "/").upper() + "/"
    pending = [{"session_id": "s1", "cwd": weird}]
    assert match_pending(pending, members) == {"alpha"}

def test_unrelated_cwd_ignored(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    members = [_m("alpha", a)]
    pending = [{"session_id": "s9", "cwd": str(tmp_path / "elsewhere")}]
    assert match_pending(pending, members) == set()

def test_missing_cwd_ignored(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    members = [_m("alpha", a)]
    assert match_pending([{"session_id": "s1"}], members) == set()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_matching.py -q`
Expected: FAIL(`ModuleNotFoundError: claude_cockpit.matching`)。

- [ ] **Step 4: 写 `src/claude_cockpit/matching.py`**

```python
"""把 pending 信号(按 cwd)对到成员名。纯逻辑,可单测。"""
from __future__ import annotations

import os
from pathlib import Path

from .config import Member


def _norm(p: str | os.PathLike) -> str:
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))
    except Exception:
        return ""


def match_pending(pending: list[dict], members: list[Member]) -> set[str]:
    """返回有 pending 信号(等你确认)的成员名集合。按规范化后的 cwd 精确匹配。"""
    by_cwd = {_norm(m.cwd): m.name for m in members}
    hit: set[str] = set()
    for rec in pending:
        cwd = rec.get("cwd") if isinstance(rec, dict) else None
        if not cwd:
            continue
        name = by_cwd.get(_norm(cwd))
        if name:
            hit.add(name)
    return hit
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_matching.py -q`
Expected: PASS(4 passed)。

- [ ] **Step 6: Commit**

```
git add -A && git commit -m "feat: 复用 desk-buddy cc_signals + cwd→成员匹配 + 测试"
```

---

## Task 4: launcher.py(启动命令 + 拉起控制台)

**Files:** Create `src/claude_cockpit/launcher.py`, `tests/test_launcher.py`

- [ ] **Step 1: 写失败测试 `tests/test_launcher.py`**

```python
from pathlib import Path
from claude_cockpit.config import Member
from claude_cockpit.launcher import window_title, claude_flags, build_launch_command

def _m(**kw):
    kw.setdefault("cwd", Path("."))
    return Member(name=kw.pop("name", "shop"), **kw)

def test_window_title():
    assert window_title(_m(name="driver")) == "CCKPT:driver"

def test_flags_bypass():
    assert "--dangerously-skip-permissions" in claude_flags(_m(permission_mode="bypassPermissions"))

def test_flags_mode_and_model():
    f = claude_flags(_m(permission_mode="plan", model="opus"))
    assert "--permission-mode" in f and "plan" in f
    assert "--model" in f and "opus" in f

def test_flags_default_no_model():
    f = claude_flags(_m(permission_mode="default"))
    assert "--model" not in f

def test_build_command_contains_cwd_title_and_claude(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_launch_command(m)
    assert "CCKPT:shop" in cmd
    assert str(tmp_path) in cmd
    assert "claude" in cmd
    assert cmd.startswith("start ")  # 通过 cmd /c 执行
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_launcher.py -q`
Expected: FAIL(`ModuleNotFoundError: claude_cockpit.launcher`)。

- [ ] **Step 3: 写 `src/claude_cockpit/launcher.py`**

```python
"""为每个成员拉起一个独立 claude 控制台窗口。

启动命令的确切 flag 以 `claude --help` 为准——实现/验证时核对:
  - 模型:`--model <m>`
  - 权限:bypassPermissions → `--dangerously-skip-permissions`;
          其余 → `--permission-mode <default|acceptEdits|plan>`
"""
from __future__ import annotations

import subprocess

from .config import Member

TITLE_PREFIX = "CCKPT:"


def window_title(m: Member) -> str:
    return f"{TITLE_PREFIX}{m.name}"


def claude_flags(m: Member) -> list[str]:
    flags: list[str] = []
    if m.model:
        flags += ["--model", m.model]
    if m.permission_mode == "bypassPermissions":
        flags += ["--dangerously-skip-permissions"]
    elif m.permission_mode and m.permission_mode != "default":
        flags += ["--permission-mode", m.permission_mode]
    return flags


def build_launch_command(m: Member) -> str:
    """返回交给 `cmd /c` 的命令串:开一个带标题的新控制台,cd 到 cwd 后跑 claude。
    `cmd /k` 让窗口在 claude 退出后仍留着(便于看输出 / 重开会话)。"""
    title = window_title(m)
    flags = " ".join(claude_flags(m))
    inner = f'cd /d "{m.cwd}" & claude {flags}'.rstrip()
    return f'start "{title}" cmd /k {inner}'


def launch(m: Member) -> None:
    """真正拉起控制台(独立窗口)。已存在同标题窗口由调用方先判重。"""
    subprocess.Popen(["cmd", "/c", build_launch_command(m)],
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_launcher.py -q`
Expected: PASS(5 passed)。

- [ ] **Step 5: 手动验证真启动**(确认 flag/cwd 正确)

新建 `_smoke_launch.py`(临时):
```python
from pathlib import Path
from claude_cockpit.config import Member
from claude_cockpit.launcher import launch
launch(Member(name="smoke", cwd=Path.cwd(), permission_mode="default"))
```
Run: `.venv/Scripts/python.exe _smoke_launch.py` → 期望弹出一个标题为 `CCKPT:smoke` 的控制台,
里面进入了当前目录并启动了 claude(若 claude 报未知 flag,据 `claude --help` 修正 `claude_flags`)。
验证后删除 `_smoke_launch.py`。

- [ ] **Step 6: Commit**

```
git add -A && git commit -m "feat: launcher 启动命令构造 + 真控制台拉起 + 测试"
```

---

## Task 5: winman.py(Win32 窗口管理,手动验证)

**Files:** Create `src/claude_cockpit/winman.py`

- [ ] **Step 1: 写 `src/claude_cockpit/winman.py`**

```python
"""Win32(ctypes)窗口管理:按标题找控制台、置前、最小化。仅 Windows。
所有失败吞掉——拿不到窗口不该让面板崩。"""
from __future__ import annotations

import ctypes
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
```

- [ ] **Step 2: 手动验证**

先用 Task 4 的方式开一个 `CCKPT:smoke` 控制台,点别的窗口让它失焦,然后:
```python
from claude_cockpit import winman
h = winman.find_by_title("CCKPT:smoke")
print("hwnd:", h)
winman.bring_to_front(h)   # 期望:smoke 控制台被还原并置到最前
winman.minimize(h)         # 期望:被最小化
```
Run: `.venv/Scripts/python.exe -c "<上面代码>"`(或临时脚本)。期望窗口如注释所述响应。
若 `bring_to_front` 只闪任务栏不置前,记录现象——这是已知 Windows 限制,可接受的退化。

- [ ] **Step 3: Commit**

```
git add -A && git commit -m "feat: winman Win32 找窗口/置前/最小化"
```

---

## Task 6: controller.py(轮询状态机,纯逻辑)

**Files:** Create `src/claude_cockpit/controller.py`, `tests/test_controller.py`

状态机职责:每轮拿到「当前等你确认的成员名集合」,与上一轮比对,输出「这一轮**新出现**、需要置前的成员」(只在从无到有时置前一次,避免反复抢焦点),并维护每个成员的状态字符串。

- [ ] **Step 1: 写失败测试 `tests/test_controller.py`**

```python
from claude_cockpit.controller import Controller

def test_new_pending_triggers_raise():
    c = Controller(["alpha", "beta"])
    to_raise = c.update({"alpha"})
    assert to_raise == ["alpha"]
    assert c.status("alpha") == "pending"
    assert c.status("beta") == "idle"

def test_same_pending_does_not_retrigger():
    c = Controller(["alpha"])
    assert c.update({"alpha"}) == ["alpha"]
    assert c.update({"alpha"}) == []      # 仍在 pending,不重复置前

def test_cleared_then_new_retriggers():
    c = Controller(["alpha"])
    c.update({"alpha"})
    assert c.update(set()) == []          # 清除
    assert c.status("alpha") == "idle"
    assert c.update({"alpha"}) == ["alpha"]  # 再次出现,重新置前

def test_multiple_new():
    c = Controller(["a", "b", "c"])
    assert set(c.update({"a", "c"})) == {"a", "c"}
    assert c.status("b") == "idle"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_controller.py -q`
Expected: FAIL(`ModuleNotFoundError: claude_cockpit.controller`)。

- [ ] **Step 3: 写 `src/claude_cockpit/controller.py`**

```python
"""轮询状态机(纯逻辑,不碰 Qt/Win32)。

每轮 update(当前 pending 成员名集合) → 返回本轮新出现、需要置前的成员名列表。
"""
from __future__ import annotations


class Controller:
    def __init__(self, member_names: list[str]):
        self._names = list(member_names)
        self._pending: set[str] = set()      # 上一轮 pending 集合

    def update(self, pending_now: set[str]) -> list[str]:
        """返回从「无 pending」变成「有 pending」的成员(需置前),保持成员顺序。"""
        newly = pending_now - self._pending
        self._pending = set(pending_now)
        return [n for n in self._names if n in newly]

    def status(self, name: str) -> str:
        return "pending" if name in self._pending else "idle"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_controller.py -q`
Expected: PASS(4 passed)。

- [ ] **Step 5: 全量测试**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS(config 4 + matching 4 + launcher 5 + controller 4 = 17 passed)。

- [ ] **Step 6: Commit**

```
git add -A && git commit -m "feat: controller 轮询状态机(置前去抖)+ 测试"
```

---

## Task 7: panel.py(PySide6 面板 + 托盘,手动验证)

**Files:** Create `src/claude_cockpit/panel.py`

- [ ] **Step 1: 写 `src/claude_cockpit/panel.py`**

```python
"""常驻轻量面板:每个成员一行(emoji 名字 状态点),点行=置前其控制台;
顶部「▶ 全部启动」「刷新」;系统托盘可显隐/退出。状态由外部 set_status 驱动。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

_DOT = {"idle": "⚪", "pending": "🟡", "down": "⛔"}


class Panel(QWidget):
    # 信号:点某成员行 / 点全部启动
    member_clicked = Signal(str)
    launch_all_clicked = Signal()

    def __init__(self, members):
        super().__init__()
        self.setWindowTitle("Claude 驾驶舱")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._rows: dict[str, QLabel] = {}   # name -> 状态点 label
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        btn_all = QPushButton("▶ 全部启动")
        btn_all.clicked.connect(self.launch_all_clicked.emit)
        top.addWidget(btn_all)
        root.addLayout(top)
        for m in members:
            row = QHBoxLayout()
            dot = QLabel(_DOT["idle"])
            name = QPushButton(f"{m.emoji} @{m.name}")
            name.setFlat(True)
            name.clicked.connect(lambda _=False, n=m.name: self.member_clicked.emit(n))
            row.addWidget(dot)
            row.addWidget(name, 1)
            root.addLayout(row)
            self._rows[m.name] = dot

    def set_status(self, name: str, status: str) -> None:
        dot = self._rows.get(name)
        if dot is not None:
            dot.setText(_DOT.get(status, "⚪"))
```

- [ ] **Step 2: 手动验证(脱离信号,纯界面)**

临时 `_smoke_panel.py`:
```python
import sys
from PySide6.QtWidgets import QApplication
from claude_cockpit.config import load_config
from claude_cockpit.panel import Panel
app = QApplication(sys.argv)
panel = Panel(load_config("agents.yaml"))
panel.member_clicked.connect(lambda n: print("clicked", n))
panel.launch_all_clicked.connect(lambda: print("launch all"))
panel.set_status("demo", "pending")
panel.show()
app.exec()
```
Run: `.venv/Scripts/python.exe _smoke_panel.py` → 期望出现置顶小窗,demo 行状态点是 🟡,
点成员名打印 `clicked demo`,点「▶ 全部启动」打印 `launch all`。验证后删脚本。

- [ ] **Step 3: Commit**

```
git add -A && git commit -m "feat: PySide6 面板(成员行/状态点/全部启动)"
```

---

## Task 8: main.py(装配 + 轮询,端到端手动验证)

**Files:** Create `src/claude_cockpit/main.py`

- [ ] **Step 1: 写 `src/claude_cockpit/main.py`**

```python
"""入口:装配 配置/面板/控制器/轮询/窗口管理。
python -m claude_cockpit.main  或  claude-cockpit 命令。"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
)
from PySide6.QtGui import QIcon

from . import cc_signals, winman
from .config import load_config
from .controller import Controller
from .launcher import launch, window_title
from .matching import match_pending
from .panel import Panel


def _config_path() -> Path:
    # v1:用包同级 / 当前目录的 agents.yaml;后续可加 --config
    here = Path(__file__).resolve().parent.parent.parent
    p = here / "agents.yaml"
    return p if p.exists() else Path("agents.yaml")


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    members = load_config(_config_path())
    panel = Panel(members)
    controller = Controller([m.name for m in members])
    by_name = {m.name: m for m in members}

    def focus_member(name: str) -> None:
        m = by_name.get(name)
        if not m:
            return
        h = winman.find_by_title(window_title(m))
        if h is None:
            launch(m)                       # 没开就开
        else:
            winman.bring_to_front(h)

    def launch_all() -> None:
        for m in members:
            if winman.find_by_title(window_title(m)) is None:
                launch(m)

    panel.member_clicked.connect(focus_member)
    panel.launch_all_clicked.connect(launch_all)

    def tick() -> None:
        pending = match_pending(cc_signals.read_pending_full(), members)
        to_raise = controller.update(pending)
        for name in members:
            panel.set_status(name.name, controller.status(name.name))
        for name in to_raise:               # 新出现的等待 → 自动置前
            focus_member(name)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(1000)

    # 托盘:显隐面板 / 退出
    tray = QSystemTrayIcon(QIcon(), app)
    menu = QMenu()
    menu.addAction("显示/隐藏面板", lambda: panel.setVisible(not panel.isVisible()))
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("Claude 驾驶舱")
    tray.show()

    panel.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

注:`tick()` 里循环变量用 `name`(实为 Member 对象,`name.name` 取名)——实现时改名为 `m`
以免混淆:`for m in members: panel.set_status(m.name, controller.status(m.name))`。

- [ ] **Step 2: 端到端手动验证**

前置:确认 desk-buddy 已 `install_hooks` 且重启过 Claude Code(hooks 生效)。
Run: `.venv/Scripts/python.exe -m claude_cockpit.main`
逐项:
  - 面板出现,列出 agents.yaml 的成员,状态 ⚪。
  - 点「▶ 全部启动」→ 每个成员弹出 `CCKPT:<name>` 控制台,在各自 cwd 跑 claude。
  - 点面板成员行 → 对应控制台被置前。
  - 在某 default/plan 成员的控制台里触发一次权限确认 → ~1s 内该控制台自动弹到前面,
    面板该行变 🟡;答复后该行回 ⚪。
  - 托盘「显示/隐藏面板」「退出」可用。

- [ ] **Step 3: Commit**

```
git add -A && git commit -m "feat: main 装配 + 1s 轮询 + 托盘(端到端可用)"
```

---

## Task 9: 与 desk-buddy 一键同启(最小集成)

**Files:** Modify `C:\Users\LQ\PhpstormProjects\desk-buddy\src\desk_buddy\main.py`(末尾,可选拉起)

- [ ] **Step 1: 在 desk-buddy 的 `main()` 里、`pet.show()` 之前加可选拉起**

```python
    # 可选:同时拉起 Claude 驾驶舱(装了才拉,失败不影响桌宠)
    try:
        import os
        cockpit_py = os.environ.get("CLAUDE_COCKPIT_PY")  # 指向 cockpit venv 的 python
        if cockpit_py and os.path.exists(cockpit_py):
            import subprocess
            subprocess.Popen([cockpit_py, "-m", "claude_cockpit.main"])
    except Exception:
        pass
```

说明:用环境变量 `CLAUDE_COCKPIT_PY` 指向 cockpit 的 venv python(避免 desk-buddy 硬依赖
cockpit)。没设就不拉,完全向后兼容。更紧的集成(配置项/菜单开关)留 v2。

- [ ] **Step 2: 手动验证**

设 `CLAUDE_COCKPIT_PY=C:\Users\LQ\PhpstormProjects\claude-cockpit\.venv\Scripts\python.exe`,
启动 desk-buddy → 期望桌宠出现的同时,cockpit 面板也起来。取消该环境变量 → 只起桌宠。

- [ ] **Step 3: Commit(在 desk-buddy 仓库)**

```
cd /c/Users/LQ/PhpstormProjects/desk-buddy
git add src/desk_buddy/main.py
git commit -m "feat: 可选同启 claude-cockpit(CLAUDE_COCKPIT_PY 环境变量,默认关闭)"
```

---

## Task 10: README + 收尾

**Files:** Create `claude-cockpit/README.md`

- [ ] **Step 1: 写 `README.md`**:简述用途、安装(venv + pip install -e)、配置 agents.yaml、
  运行(`claude-cockpit`)、与 desk-buddy 的关系(共享 `~/.claude/data/desk-buddy/pending/`、
  需先在 desk-buddy 装 hook、`CLAUDE_COCKPIT_PY` 同启)、已知限制(Win32 置前可能退化为闪任务栏、
  v1 只有 🟡/⚪)。

- [ ] **Step 2: 全量测试 + Commit**

```
.venv/Scripts/python.exe -m pytest -q     # 期望 17 passed
git add -A && git commit -m "docs: README"
```

---

## Self-Review 备注

- **Spec 覆盖**:成员配置(T2)、控制台启动器(T4)、Win32 窗口管理(T5)、信号检测复用 desk-buddy
  (T3)、轮询联动状态机(T6)、面板(T7)、装配/托盘(T8)、desk-buddy 同启(T9)。非目标(忙/闲
  绿红灯、内嵌终端、跨平台、打包)均未排任务,符合 v1。
- **类型一致**:`Member`(config)贯穿;`window_title(m)` 在 launcher 定义、main 调用一致;
  `match_pending(pending, members)->set[str]`、`Controller.update(set)->list[str]`、
  `controller.status(name)->str`、`panel.set_status(name, status)`、`cc_signals.read_pending_full()->list[dict]`
  全程一致。
- **已知占位**:claude CLI 确切 flag 标注以 `claude --help` 为准并在 T4 Step5 手动核对;
  main.py 的 `tick()` 循环变量命名在 T8 Step1 注里明确修正。无其它 TBD。
