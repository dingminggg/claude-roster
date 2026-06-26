# 托盘悬停弹出「谁有消息」可点列表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 托盘图标有消息时,鼠标悬停其上方直接弹出可点小浮层,点一行即把那个成员的控制台最大化弹到眼前(等价于现在「点成员卡」),省去开面板找卡的三步。

**Architecture:** 三块。(1) `tray_popup_decision` 纯函数,把「显示/隐藏/不动」判定从 Qt 几何里剥出来单测。(2) `TrayPopup` 无边框 Tool 浮层(panel.py 纯视图),点行发 `picked(name)`。(3) main.py 用 150ms `hover_timer` 轮询 `QCursor.pos()` 对 `tray.geometry()`,据 `tray_popup_decision` 显隐浮层,`picked` 接到现有 `on_row_click`。

**Tech Stack:** Python 3 / PySide6(Qt Widgets)/ pytest;Windows 托盘(QSystemTrayIcon)。

参考 spec:`docs/superpowers/specs/2026-06-26-tray-hover-popup-design.md`

约定:仓库 `docs/` 被 .gitignore,但本计划/spec 用 `git add -f` 入库。提交信息中文 + 末尾 `Co-Authored-By`。测试用 venv:`QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest`。

---

### Task 1: `tray_popup_decision` 纯函数 + 单测

把悬停浮层的显隐判定做成模块级纯函数(仿照现有 `newly_pending`),Qt 几何由调用方算好后传入。

**Files:**
- Modify: `src/claude_cockpit/main.py`(在 `newly_pending` 之后新增模块级函数)
- Test: `tests/test_tray_popup_decision.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tray_popup_decision.py`:

```python
from claude_cockpit.main import tray_popup_decision as D

LIMIT = 2


def test_no_pending_hides_when_visible():
    assert D(False, True, True, True, 0, LIMIT) == "hide"


def test_no_pending_noop_when_hidden():
    assert D(False, False, False, False, 0, LIMIT) == "none"


def test_over_icon_shows_when_hidden():
    assert D(True, True, False, False, 0, LIMIT) == "show"


def test_over_icon_noop_when_already_visible():
    assert D(True, True, False, True, 0, LIMIT) == "none"


def test_on_popup_keeps_open():
    # 光标移到浮层上(不在图标)→ 不关
    assert D(True, False, True, True, 0, LIMIT) == "none"


def test_grace_before_hide():
    # 离开图标和浮层,但 miss 还没到阈值 → 暂不关
    assert D(True, False, False, True, 1, LIMIT) == "none"


def test_hide_after_miss_limit():
    assert D(True, False, False, True, 2, LIMIT) == "hide"


def test_hidden_and_not_over_icon_noop():
    assert D(True, False, False, False, 0, LIMIT) == "none"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_tray_popup_decision.py -q`
Expected: FAIL（`ImportError: cannot import name 'tray_popup_decision'`）

- [ ] **Step 3: 实现纯函数**

在 `src/claude_cockpit/main.py` 里 `newly_pending` 函数之后插入:

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_tray_popup_decision.py -q`
Expected: PASS(8 passed)

- [ ] **Step 5: 提交**

```bash
git add src/claude_cockpit/main.py tests/test_tray_popup_decision.py
git commit -m "$(printf 'feat: 托盘悬停浮层显隐判定纯函数 tray_popup_decision\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: `TrayPopup` 浮层视图(panel.py)

无边框、不抢焦点的 Tool 窗口,列出有消息的成员,点行发 `picked(name)`。复用现有 `#popup`/`#popitem` 的 QSS 与 `_POPUP_W`。

**Files:**
- Modify: `src/claude_cockpit/panel.py`(在 `_SessionPicker` 类之后、`Panel` 类之前新增 `TrayPopup`)
- Test: `tests/test_tray_popup.py`(新建)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_tray_popup.py`(需要 QApplication,用 offscreen):

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from claude_cockpit.panel import TrayPopup


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    yield a


def test_rows_render_as_clickable_items(app):
    rows = [("alice", "🐸", "#2980b9"), ("bob", "🦊", "#e67e22")]
    pop = TrayPopup(rows)
    items = pop.findChildren(QPushButton)
    assert len(items) == 2
    assert "@alice" in items[0].text()
    assert "@bob" in items[1].text()


def test_click_emits_picked_name(app):
    pop = TrayPopup([("alice", "🐸", "#2980b9")])
    got = []
    pop.picked.connect(got.append)
    pop.findChildren(QPushButton)[0].click()
    assert got == ["alice"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_tray_popup.py -q`
Expected: FAIL（`ImportError: cannot import name 'TrayPopup'`）

- [ ] **Step 3: 实现 TrayPopup**

在 `src/claude_cockpit/panel.py` 中,`class _SessionPicker` 定义结束之后、`class Panel` 之前,插入:

```python
class TrayPopup(QFrame):
    """托盘悬停时弹出的无边框小浮层:列出有消息的成员,点一行发 picked(name)。
    显隐由 main 的悬停定时器控制——故意不用 Qt.Popup(那种一移开鼠标就当点了外面
    自动关,与悬停模型冲突);用 Tool + 不抢焦点窗口,我们自己控显隐。"""
    picked = Signal(str)

    def __init__(self, rows, parent=None):
        # rows: list[(name, emoji, color)]
        super().__init__(parent,
                         Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # 不偷当前前台焦点
        self.setObjectName("popup")
        self.setStyleSheet(_QSS)                # 顶层窗口自带样式,不靠 Panel 级联
        self.setFixedWidth(_POPUP_W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        for name, emoji, color in rows:
            b = QPushButton(f"{emoji} @{name}  ✉")
            b.setObjectName("popitem")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"color:{color};")  # 名字用成员配色,和卡片一致
            b.clicked.connect(lambda _=False, n=name: self.picked.emit(n))
            lay.addWidget(b)
```

注:`QFrame`、`Signal`、`Qt`、`QVBoxLayout`、`QPushButton`、`_QSS`、`_POPUP_W` 在 panel.py 顶部均已导入/定义,无需新增 import。

- [ ] **Step 4: 跑测试确认通过**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_tray_popup.py -q`
Expected: PASS(2 passed)

- [ ] **Step 5: 提交**

```bash
git add src/claude_cockpit/panel.py tests/test_tray_popup.py
git commit -m "$(printf 'feat: TrayPopup 托盘悬停浮层视图(点行发 picked)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: main.py 悬停控制器接线

新增 150ms `hover_timer` 轮询光标 vs 托盘几何,据 `tray_popup_decision` 显隐 `TrayPopup`,点行接到现有 `on_row_click`。

**Files:**
- Modify: `src/claude_cockpit/main.py`(import 行、状态变量、tray 创建之后新增控制器与定时器)

- [ ] **Step 1: 补两处 import**

把
```python
from PySide6.QtGui import QIcon
```
改为
```python
from PySide6.QtGui import QCursor, QGuiApplication, QIcon
```

把
```python
from .panel import ICON_PATH, Panel
```
改为
```python
from .panel import ICON_PATH, Panel, TrayPopup
```

- [ ] **Step 2: 新增控制器状态变量**

在 `main()` 内、`card_read: set[str] = set()` 那一行(状态变量块)之后,新增:

```python
    # 悬停浮层:tray_popup 为当前显示的实例(None=没显示);hover_misses 累计「光标
    # 离开图标和浮层」的连续拍数,达到 _HOVER_MISS_LIMIT 才隐藏(给图标↔浮层缝隙宽限)。
    tray_popup: TrayPopup | None = None
    hover_misses = {"n": 0}
    _HOVER_MISS_LIMIT = 2
```

- [ ] **Step 3: 在 tray 那段之后新增控制器函数与定时器**

定位到 `blink_timer.start(550)` 这一行(托盘闪烁定时器启动处)。在它之后、`# 单实例服务端` 注释之前,插入:

```python
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
        rows = [(m.name, m.emoji, m.color) for m in members if m.name in cur_pending]
        if not rows:
            return
        _hide_tray_popup()              # 防御:先清掉可能残留的旧实例
        pop = TrayPopup(rows)
        pop.picked.connect(_on_popup_pick)
        pop.adjustSize()
        r = tray.geometry()
        # 贴托盘图标正上方、右边缘对齐(任务栏在底部)
        x = r.right() - pop.width()
        y = r.top() - pop.height() - 6
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:          # 夹紧进所在屏幕可见区,别出屏
            g = screen.availableGeometry()
            x = max(g.left(), min(x, g.right() - pop.width()))
            y = max(g.top(), min(y, g.bottom() - pop.height()))
        pop.move(x, y)
        pop.show()
        tray_popup = pop
        _ack_blink()                    # 你已经在看了 → 托盘停闪

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
        action = tray_popup_decision(bool(cur_pending), over_icon, over_popup,
                                     visible, hover_misses["n"], _HOVER_MISS_LIMIT)
        if action == "show":
            _show_tray_popup()
        elif action == "hide":
            _hide_tray_popup()

    hover_timer = QTimer()
    hover_timer.timeout.connect(_hover_tick)
    hover_timer.start(150)
```

- [ ] **Step 4: 离屏装配自检(确保接线不报错)**

Run:
```bash
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "import claude_cockpit.main as M; from PySide6.QtWidgets import QApplication; QApplication.exec=lambda self:0; print('exit', M.main())"
```
Expected: 打印 `exit 0`,无 traceback(offscreen 下 `tray.geometry()` 为空 → `_hover_tick` 安全跳过 show)。

- [ ] **Step 5: 跑全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q`
Expected: 全部 PASS(原 22 个 + 本次新增,共 32 个左右)

- [ ] **Step 6: 提交**

```bash
git add src/claude_cockpit/main.py
git commit -m "$(printf 'feat: 托盘悬停弹出有消息成员列表,点行直接最大化其控制台\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: 真实手动验证(用户执行,非自动)

离屏跑不出真实托盘几何,需在真机确认悬停体验。

- [ ] **Step 1: 无窗启动**

Run: `C:\Users\LQ\PhpstormProjects\claude-cockpit\.venv\Scripts\pythonw.exe -m claude_cockpit.main`

- [ ] **Step 2: 制造一条消息**

让任一成员答完一轮(或等权限),确认托盘图标开始闪烁。

- [ ] **Step 3: 悬停验证**

鼠标移到托盘图标上方 → 应弹出列出该成员的小浮层(emoji + @名字 + ✉),且托盘停闪。

- [ ] **Step 4: 点行验证**

点浮层里的成员 → 其控制台最大化弹到眼前、其余最小化、面板里该卡 ✉ 消失;浮层关闭。

- [ ] **Step 5: 移开验证**

再次制造消息、悬停弹出后把鼠标移开图标与浮层 → 浮层在约 1~2 拍内自动消失。

- [ ] **Step 6: 左键不变验证**

左键单击托盘图标 → 仍是显示/隐藏面板(行为未变)。

---

## 备注

- **门控**:浮层用 `cur_pending` 非空门控(有成员有消息就能悬停弹),非「正在闪烁」门控——ack 停闪后只要还有没看的消息,悬停仍能跳过去。
- **已知局限(已与用户确认接受)**:图标折叠进任务栏「^ 隐藏图标」溢出区时 `tray.geometry()` 失准,`over_icon` 恒 False → 弹不出;无可靠 API 补偿。
- 提交计划/spec 文档:`git add -f docs/...`(docs 被 .gitignore)。
