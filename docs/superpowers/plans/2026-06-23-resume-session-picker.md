# 启动时选会话 / 续接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给每个未运行成员的卡片加一个会话下拉(默认续最近一次,可选新会话,每条带二次确认删除),启动时按选中项决定 `claude --resume <id>`。

**Architecture:** 新增纯逻辑模块 `sessions.py`(扫 `~/.claude/projects/<编码cwd>/*.jsonl` 列出会话+标题、删除会话);`launcher.py` 的 `launch/build_inner_command` 增加可选 `session_id`;`panel.py` 在名字下方那行(原实时标题位)放一个 `_SessionPicker`(未运行显示、运行中让位给实时标题);`main.py` 负责刷新下拉数据、把选中会话传给 launch、处理删除。

**Tech Stack:** Python 3 / PySide6(Qt Widgets)/ pytest(纯逻辑)。Windows。

参考 spec:`docs/superpowers/specs/2026-06-23-resume-session-picker-design.md`

---

## 文件结构

- **新建** `src/claude_cockpit/sessions.py` — 会话发现/标题解析/删除(纯逻辑,无 Qt)。职责单一,便于 pytest。
- **新建** `tests/test_sessions.py` — 上面的纯逻辑测试。
- **改** `src/claude_cockpit/launcher.py` — `build_inner_command(m, session_id=None)`、`launch(m, session_id=None)`。
- **改** `tests/test_launcher.py` — 加 resume 拼接测试。
- **改** `src/claude_cockpit/panel.py` — `_SessionPicker` + `_SessionPopup` 组件;集成进卡片;`start_requested` 改签名;新增 `delete_session_requested`、`set_sessions`;`set_run_state` 切换下拉/实时标题显示。
- **改** `src/claude_cockpit/main.py` — 刷新下拉数据、按选中会话 `launch`、处理删除会话。
- **改** `CLAUDE.md` — launcher 一节「没有 --resume」更新为「可选 --resume(下拉选会话)」。

---

## Task 1: sessions.py — `encode_cwd`(cwd → projects 目录名)

**Files:**
- Create: `src/claude_cockpit/sessions.py`
- Test: `tests/test_sessions.py`

实测:Claude CLI 把会话存在 `~/.claude/projects/<目录名>/<uuid>.jsonl`,目录名 = 把 cwd 里每个非字母数字字符替换成 `-`(连字符本身也被「替换成连字符」,故保持不变)。例:`C:\Users\LQ\PhpstormProjects\claude-cockpit` → `C--Users-LQ-PhpstormProjects-claude-cockpit`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sessions.py
from pathlib import Path

from claude_cockpit import sessions


def test_encode_cwd_windows_path():
    assert sessions.encode_cwd(r"C:\Users\LQ\PhpstormProjects\claude-cockpit") \
        == "C--Users-LQ-PhpstormProjects-claude-cockpit"


def test_encode_cwd_preserves_hyphen_and_replaces_others():
    # 连字符保留;冒号/反斜杠/点/空格都变连字符
    assert sessions.encode_cwd("a-b.c d/e") == "a-b-c-d-e"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'claude_cockpit.sessions'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/claude_cockpit/sessions.py
"""Claude CLI 会话发现:列出某成员 cwd 下的历史会话(id/标题/最后活跃),并可删除。

会话存于 ~/.claude/projects/<编码cwd>/<session-uuid>.jsonl。标题取该文件内最后一条
type=="ai-title" 的 aiTitle(Claude Code 自动生成的人类可读标题);没有则退回首条用户
消息截断;再没有为空(调用方显示「(无标题)」)。纯逻辑、无 Qt,便于测试。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def encode_cwd(cwd: str | Path) -> str:
    """cwd → ~/.claude/projects/ 下的目录名:非字母数字一律变连字符。"""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/claude_cockpit/sessions.py tests/test_sessions.py
git commit -m "feat: sessions.encode_cwd 把 cwd 编码成 claude projects 目录名"
```

---

## Task 2: sessions.py — `Session` + `list_sessions`(列会话 + 解析标题)

**Files:**
- Modify: `src/claude_cockpit/sessions.py`
- Test: `tests/test_sessions.py`

标题优先级:最后一条 `ai-title` → 首条 `user` 文本消息(截断 40 字)→ 空。按 mtime 倒序,截 `limit`。

- [ ] **Step 1: Write the failing test**

```python
# 追加到 tests/test_sessions.py
import json
import os


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8")


def test_list_sessions_title_prefers_last_ai_title(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s1.jsonl", [
        {"type": "user", "message": {"content": "第一条用户消息"}},
        {"type": "ai-title", "aiTitle": "旧标题"},
        {"type": "ai-title", "aiTitle": "新标题"},
    ])
    out = sessions.list_sessions("anything", projects_root=tmp_path,
                                 _dirname="C--proj")
    assert len(out) == 1
    assert out[0].id == "s1"
    assert out[0].title == "新标题"


def test_list_sessions_falls_back_to_first_user_message(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s2.jsonl", [
        {"type": "user", "message": {"content": "帮我改一下登录逻辑"}},
        {"type": "assistant", "message": {"content": "好的"}},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "帮我改一下登录逻辑"


def test_list_sessions_user_content_as_blocks(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s3.jsonl", [
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "块状文本消息"}]}},
    ])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "块状文本消息"


def test_list_sessions_empty_title_when_no_title_no_user(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    _write_jsonl(d / "s4.jsonl", [{"type": "system", "subtype": "x"}])
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == ""


def test_list_sessions_skips_bad_lines(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "s5.jsonl").write_text(
        "not json\n" + json.dumps({"type": "ai-title", "aiTitle": "稳"}),
        encoding="utf-8")
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj")
    assert out[0].title == "稳"


def test_list_sessions_sorted_by_mtime_desc_and_limited(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    for i in range(3):
        f = d / f"s{i}.jsonl"
        _write_jsonl(f, [{"type": "ai-title", "aiTitle": f"t{i}"}])
        os.utime(f, (1000 + i, 1000 + i))   # s2 最新
    out = sessions.list_sessions("x", projects_root=tmp_path, _dirname="C--proj",
                                 limit=2)
    assert [s.id for s in out] == ["s2", "s1"]


def test_list_sessions_missing_dir_returns_empty(tmp_path):
    assert sessions.list_sessions("x", projects_root=tmp_path,
                                  _dirname="nope") == []
```

> 说明:`_dirname` 是测试钩子,直接指定目录名,避免在测试里依赖 `encode_cwd` 对临时路径的编码。生产调用不传 `_dirname`,由 `encode_cwd(cwd)` 算出。

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: FAIL — `AttributeError: module 'claude_cockpit.sessions' has no attribute 'list_sessions'`

- [ ] **Step 3: Write minimal implementation**

追加到 `src/claude_cockpit/sessions.py`:

```python
@dataclass
class Session:
    id: str
    title: str
    mtime: float


def _user_text(obj: dict) -> str | None:
    """从一条 user 记录里取出文本内容(content 可能是 str 或 block 列表)。"""
    msg = obj.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = (part.get("text") or "").strip()
                if t:
                    return t
    return None


def _parse_title(jsonl_path: Path, max_len: int = 40) -> str:
    title = None
    first_user = None
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                t = obj.get("type")
                if t == "ai-title":
                    at = obj.get("aiTitle")
                    if at:
                        title = at          # 取最后一条
                elif t == "user" and first_user is None:
                    first_user = _user_text(obj)
    except OSError:
        return ""
    if title:
        return title
    if first_user:
        return first_user[:max_len]
    return ""


def _sessions_dir(cwd, projects_root, _dirname=None) -> Path:
    root = Path(projects_root) if projects_root is not None else PROJECTS_ROOT
    return root / (_dirname if _dirname is not None else encode_cwd(cwd))


def list_sessions(cwd, limit: int = 12, projects_root=None,
                  _dirname: str | None = None) -> list[Session]:
    """列出该 cwd 对应的历史会话,按最后活跃倒序,最多 limit 条。"""
    d = _sessions_dir(cwd, projects_root, _dirname)
    if not d.is_dir():
        return []
    out: list[Session] = []
    for f in d.glob("*.jsonl"):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        out.append(Session(id=f.stem, title=_parse_title(f), mtime=mtime))
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: PASS(全部 sessions 测试通过)

- [ ] **Step 5: Commit**

```bash
git add src/claude_cockpit/sessions.py tests/test_sessions.py
git commit -m "feat: sessions.list_sessions 列会话并解析标题(ai-title 优先,回退首条消息)"
```

---

## Task 3: sessions.py — `delete_session` + `fmt_mtime`

**Files:**
- Modify: `src/claude_cockpit/sessions.py`
- Test: `tests/test_sessions.py`

`fmt_mtime` 给 UI 用(`MM-DD`),也顺手测一下,避免 UI 里出错。

- [ ] **Step 1: Write the failing test**

```python
# 追加到 tests/test_sessions.py
def test_delete_session_removes_file(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    (d / "gone.jsonl").write_text("{}", encoding="utf-8")
    assert sessions.delete_session("x", "gone", projects_root=tmp_path,
                                   _dirname="C--proj") is True
    assert not (d / "gone.jsonl").exists()


def test_delete_session_missing_returns_false(tmp_path):
    d = tmp_path / "C--proj"
    d.mkdir()
    assert sessions.delete_session("x", "nope", projects_root=tmp_path,
                                   _dirname="C--proj") is False


def test_fmt_mtime_month_day():
    import datetime as _dt
    ts = _dt.datetime(2026, 6, 18, 9, 30).timestamp()
    assert sessions.fmt_mtime(ts) == "06-18"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'delete_session'`

- [ ] **Step 3: Write minimal implementation**

追加到 `src/claude_cockpit/sessions.py`:

```python
def delete_session(cwd, session_id: str, projects_root=None,
                   _dirname: str | None = None) -> bool:
    """删除某会话的 .jsonl 文件;成功 True,文件不存在/失败 False。"""
    f = _sessions_dir(cwd, projects_root, _dirname) / f"{session_id}.jsonl"
    try:
        f.unlink()
        return True
    except OSError:
        return False


def fmt_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime).strftime("%m-%d")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_sessions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/claude_cockpit/sessions.py tests/test_sessions.py
git commit -m "feat: sessions.delete_session + fmt_mtime"
```

---

## Task 4: launcher.py — 可选 `session_id`(拼 `--resume`)

**Files:**
- Modify: `src/claude_cockpit/launcher.py:35-52`
- Test: `tests/test_launcher.py`

`claude_flags(m)` 保持不带 resume(现有 `test_flags_no_auto_resume` 仍应通过);resume 是每次启动单独传入的,拼在 `claude` 与 flags 之间。

- [ ] **Step 1: Write the failing test**

```python
# 追加到 tests/test_launcher.py
def test_build_inner_command_with_resume(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_inner_command(m, session_id="abc-123")
    assert "claude --resume abc-123" in cmd


def test_build_inner_command_without_resume_unchanged(tmp_path):
    m = _m(name="shop", cwd=tmp_path, permission_mode="default")
    cmd = build_inner_command(m)
    assert "--resume" not in cmd
    assert "claude" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_launcher.py -v`
Expected: FAIL — `TypeError: build_inner_command() got an unexpected keyword argument 'session_id'`

- [ ] **Step 3: Write minimal implementation**

替换 `src/claude_cockpit/launcher.py` 的 `build_inner_command` 与 `launch`:

```python
def build_inner_command(m: Member, session_id: str | None = None) -> str:
    """新控制台里要执行的命令:先 `title` 设窗口标题(供按标题抓句柄),cd 到 cwd,
    再停顿 ~3 秒让标题稳稳挂着,最后才跑 claude(claude 启动后会改标题)。
    句柄在窗口刚出现那一刻就被抓走、缓存起来,之后改名都不影响;这 3 秒只是
    给抓取留足富余,彻底避免「抢时间」。`cmd /k` 让窗口在 claude 退出后仍留着。

    session_id 非空 → 拼 `claude --resume <id>`,直接续接用户在面板下拉里选的那条
    会话(由用户挑、确定没在别处开着);为空 → 起全新会话(不碰任何已有窗口)。"""
    flags = " ".join(claude_flags(m))
    resume = f"--resume {session_id} " if session_id else ""
    # ping 当延时(比 timeout 更不挑环境,不依赖 stdin):-n 4 ≈ 3 秒
    return (f'title {window_title(m)} & cd /d "{m.cwd}" & '
            f'ping -n 4 127.0.0.1 >nul & claude {resume}{flags}').rstrip()


def launch(m: Member, session_id: str | None = None) -> None:
    """真正拉起控制台:用 CREATE_NEW_CONSOLE 让子进程自带一个新控制台窗口
    (不走 `start`,避免嵌套引号被 cmd 拆坏)。已存在同标题窗口由调用方先判重。
    session_id 透传给 build_inner_command 决定是否 --resume。"""
    subprocess.Popen(
        f"cmd /k {build_inner_command(m, session_id)}",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
```

同时更新文件顶部注释里关于 resume 的说明(第 21-24 行那段「不在启动时自动 --resume」):把它改为说明「不自动 resume;由面板下拉显式选会话后经 session_id 传入」。改为:

```python
def claude_flags(m: Member) -> list[str]:
    # 不自动 --resume:resume 由用户在面板下拉里显式选(确定没在别处开着的那条),
    # 经 build_inner_command(session_id=...) 传入,不在这里加。
    flags: list[str] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_launcher.py -v`
Expected: PASS(含原有 `test_flags_no_auto_resume`)

- [ ] **Step 5: Commit**

```bash
git add src/claude_cockpit/launcher.py tests/test_launcher.py
git commit -m "feat: launcher 支持可选 session_id,拼 claude --resume"
```

---

## Task 5: panel.py — `_SessionPicker` + `_SessionPopup` 组件

**Files:**
- Modify: `src/claude_cockpit/panel.py`

纯 Qt 组件,逻辑由后续离屏装配自检覆盖(项目惯例:GUI 不写单测)。本任务只加组件类,不接进卡片。

- [ ] **Step 1: 在 panel.py 顶部加常量与 QSS**

在 `_CTITLE_W = 185` 附近加:

```python
# 会话下拉(未运行成员名字下方):按钮文字省略宽度、弹层宽度
_PICKER_W = 170
_POPUP_W = 250
```

在 `_QSS` 字符串末尾(`"""` 前)追加:

```css
QPushButton#picker {
    color:#8a93a0; background:transparent; border:none; text-align:left;
    font-size:10px; padding:0;
}
QPushButton#picker:hover { color:#c7ccd6; }
QFrame#popup { background:#2b2f3a; border:1px solid #3a3f4b; border-radius:8px; }
QPushButton#popitem {
    color:#c7ccd6; background:transparent; border:none; text-align:left;
    font-size:11px; padding:4px 6px; border-radius:5px;
}
QPushButton#popitem:hover { background:#363b47; color:#ffffff; }
QPushButton#popdel {
    color:#7b828d; background:transparent; border:none;
    font-size:13px; font-weight:700; border-radius:5px;
}
QPushButton#popdel:hover { color:#ff6b6b; background:#3a2a2a; }
```

- [ ] **Step 2: 加 `_SessionPopup` 类**(放在 `_AddCard` 之后、`Panel` 之前)

```python
class _SessionPopup(QFrame):
    """会话下拉的浮层(Qt.Popup:点外部自动关闭)。第一行「＋ 新会话」,
    其下每行 [标题·日期 | 删除×];删除是二次点确认(再点同一个×才真删)。"""
    picked = Signal(str)            # "" = 新会话;否则 session_id
    delete_requested = Signal(str)  # session_id

    def __init__(self, sessions, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("popup")
        self.setFixedWidth(_POPUP_W)
        self._confirm_id: str | None = None
        self._dels: dict[str, QPushButton] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        new = QPushButton("＋  新会话")
        new.setObjectName("popitem")
        new.setCursor(Qt.CursorShape.PointingHandCursor)
        new.clicked.connect(lambda: self._pick(""))
        lay.addWidget(new)

        from . import sessions as _sess
        for s in sessions:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            label = s.title if s.title else "(无标题)"
            pick = QPushButton(f"{label} · {_sess.fmt_mtime(s.mtime)}")
            pick.setObjectName("popitem")
            pick.setCursor(Qt.CursorShape.PointingHandCursor)
            pick.setToolTip(s.title or s.id)
            pick.clicked.connect(lambda _=False, sid=s.id: self._pick(sid))
            rl.addWidget(pick, 1)
            dele = QPushButton("×")
            dele.setObjectName("popdel")
            dele.setFixedWidth(28)
            dele.setCursor(Qt.CursorShape.PointingHandCursor)
            dele.setToolTip("删除这条会话记录(再点一次确认)")
            dele.clicked.connect(lambda _=False, sid=s.id: self._on_del(sid))
            rl.addWidget(dele, 0)
            self._dels[s.id] = dele
            lay.addWidget(row)

    def _pick(self, sid: str) -> None:
        self.picked.emit(sid)
        self.close()

    def _on_del(self, sid: str) -> None:
        if self._confirm_id == sid:         # 第二次点同一个 × → 真删
            self.delete_requested.emit(sid)
            self.close()
            return
        self._reset_confirm()               # 先复原别的「确认?」
        self._confirm_id = sid
        b = self._dels[sid]
        b.setText("确认?")
        b.setFixedWidth(44)
        b.setStyleSheet("color:#fff; background:#a33; border-radius:5px;"
                        " font-size:10px; font-weight:600;")

    def _reset_confirm(self) -> None:
        if self._confirm_id and self._confirm_id in self._dels:
            b = self._dels[self._confirm_id]
            b.setText("×")
            b.setFixedWidth(28)
            b.setStyleSheet("")
        self._confirm_id = None
```

- [ ] **Step 3: 加 `_SessionPicker` 类**(紧跟 `_SessionPopup` 之后)

```python
class _SessionPicker(QWidget):
    """未运行成员名字下方的会话下拉:平时显示当前选中(「续:<标题>」或「＋ 新会话」),
    点开弹 _SessionPopup 选择/删除。删除经 delete_requested 上抛给卡片。"""
    delete_requested = Signal(str)  # session_id

    def __init__(self):
        super().__init__()
        self._sessions: list = []
        self._sel_id: str | None = None     # None = 新会话
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._btn = QPushButton("＋ 新会话")
        self._btn.setObjectName("picker")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._open)
        lay.addWidget(self._btn)

    def set_sessions(self, sessions) -> None:
        self._sessions = list(sessions)
        # 默认选中最近一条;没有历史 → 新会话
        self._sel_id = self._sessions[0].id if self._sessions else None
        self._update_btn()

    def selected_id(self) -> str | None:
        return self._sel_id

    def _update_btn(self) -> None:
        if self._sel_id is None:
            self._btn.setText("＋ 新会话")
            self._btn.setToolTip("启动后开一个全新会话")
            return
        s = next((x for x in self._sessions if x.id == self._sel_id), None)
        label = (s.title if (s and s.title) else "(无标题)")
        text = QFontMetrics(self._btn.font()).elidedText(
            f"续:{label}", Qt.TextElideMode.ElideRight, _PICKER_W)
        self._btn.setText(text)
        self._btn.setToolTip(f"启动后续接:{label}(点开可换/新建/删除)")

    def _open(self) -> None:
        pop = _SessionPopup(self._sessions, self)
        pop.picked.connect(self._on_picked)
        pop.delete_requested.connect(self.delete_requested.emit)
        pop.move(self._btn.mapToGlobal(self._btn.rect().bottomLeft()))
        pop.show()

    def _on_picked(self, sid: str) -> None:
        self._sel_id = sid or None
        self._update_btn()
```

- [ ] **Step 4: 离屏冒烟自检**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from claude_cockpit.panel import _SessionPicker, _SessionPopup
from claude_cockpit.sessions import Session
from PySide6.QtWidgets import QApplication
app = QApplication([])
p = _SessionPicker()
p.set_sessions([Session('id1','改登录逻辑',1000.0), Session('id2','',2000.0)])
assert p.selected_id() == 'id1'              # 默认最近(列表已按调用方倒序;此处第一条)
p.set_sessions([])
assert p.selected_id() is None               # 无历史 → 新会话
pop = _SessionPopup([Session('id1','t',1000.0)])
print('OK picker+popup')
"
```
Expected: 打印 `OK picker+popup`,无异常。

- [ ] **Step 5: Commit**

```bash
git add src/claude_cockpit/panel.py
git commit -m "feat: panel 加 _SessionPicker/_SessionPopup 会话下拉组件"
```

---

## Task 6: panel.py — 把下拉接进卡片 + 信号 + 显隐切换

**Files:**
- Modify: `src/claude_cockpit/panel.py`

- [ ] **Step 1: Panel 新增信号 + 字典 + 改 start_requested 签名**

把 `start_requested = Signal(str)` 改为带会话 id:

```python
    start_requested = Signal(str, object)   # (name, session_id|None):点「确定」后拉起
```

在信号区追加:

```python
    delete_session_requested = Signal(str, str)  # (name, session_id):删该成员某会话记录
```

在 `__init__` 的字典初始化区(`self._ctitles = ...` 附近)追加:

```python
        self._pickers: dict[str, "_SessionPicker"] = {}  # 未运行成员的会话下拉
```

- [ ] **Step 2: `_make_card` 里在 ctitle 之后加 picker,并加高行**

把 accent 的最小高度从 40 提到 46(行略加高):

```python
        accent.setMinimumHeight(46)
```

在 `col.addWidget(ctitle); self._ctitles[m.name] = ctitle` 之后追加:

```python
        # 同一行位:未运行显示会话下拉(选要续的会话),运行中让位给上面的实时标题
        picker = _SessionPicker()
        picker.delete_requested.connect(
            lambda sid, n=m.name: self.delete_session_requested.emit(n, sid))
        col.addWidget(picker)
        self._pickers[m.name] = picker
```

- [ ] **Step 3: `rebuild` 里清理 picker 字典**

在 `self._ctitles.clear()` 附近追加:

```python
        self._pickers.clear()
```

- [ ] **Step 4: `_confirm_yes` 带上选中的会话 id**

替换 `_confirm_yes`:

```python
    def _confirm_yes(self, name: str) -> None:
        """确定 → 收起确认条,按下拉选中的会话走启动流程。"""
        self._confirming.discard(name)
        box = self._confirm_boxes.get(name)
        if box is not None:
            box.setVisible(False)
        go = self._gos.get(name)
        if go is not None:
            go.setVisible(True)
        picker = self._pickers.get(name)
        sid = picker.selected_id() if picker is not None else None
        self.start_requested.emit(name, sid)
```

- [ ] **Step 5: `set_run_state` 切换下拉/实时标题显隐**

在 `set_run_state` 里、设置 `eff.setOpacity(...)` 之后追加(未运行才显示下拉,并藏掉实时标题;运行/启动中藏下拉,实时标题由 set_title 管):

```python
        picker = self._pickers.get(name)
        if picker is not None:
            picker.setVisible(state == "down")
        if state == "down":
            ctitle = self._ctitles.get(name)
            if ctitle is not None:
                ctitle.setVisible(False)
```

- [ ] **Step 6: 新增 `set_sessions` 方法**(放在 `set_title` 附近)

```python
    def set_sessions(self, name: str, sessions) -> None:
        """给某成员的会话下拉灌数据(列表已按最近活跃倒序);默认选最近一条/无则新会话。"""
        p = self._pickers.get(name)
        if p is not None:
            p.set_sessions(sessions)
```

- [ ] **Step 7: 离屏冒烟自检**

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
from claude_cockpit.panel import Panel
from claude_cockpit.config import Member
from claude_cockpit.sessions import Session
from pathlib import Path
from PySide6.QtWidgets import QApplication
app = QApplication([])
p = Panel([Member(name='shop', cwd=Path('.'))])
got = {}
p.start_requested.connect(lambda n, sid: got.update(name=n, sid=sid))
p.set_sessions('shop', [Session('sid-x','改登录',1000.0)])
p.set_run_state('shop', 'down')
assert p._pickers['shop'].isVisible() or True   # down 下应可见(离屏 isVisible 可能为 False,仅验证不报错)
p._enter_confirm('shop'); p._confirm_yes('shop')
assert got == {'name':'shop','sid':'sid-x'}, got
p.set_sessions('shop', [])
p._enter_confirm('shop'); p._confirm_yes('shop')
assert got == {'name':'shop','sid':None}, got
print('OK panel integrate')
"
```
Expected: 打印 `OK panel integrate`,无异常。

- [ ] **Step 8: Commit**

```bash
git add src/claude_cockpit/panel.py
git commit -m "feat: 会话下拉接进卡片,启动带选中会话,运行中让位实时标题"
```

---

## Task 7: main.py — 刷新下拉、按会话启动、删除会话

**Files:**
- Modify: `src/claude_cockpit/main.py`

- [ ] **Step 1: 导入 sessions**

把 `from . import cc_signals, dialogs, store, winman` 改为:

```python
from . import cc_signals, dialogs, sessions, store, winman
```

- [ ] **Step 2: `start_member` / `on_start` 接受 session_id**

替换 `start_member`:

```python
    def start_member(m, session_id=None) -> None:
        """启动一个成员的控制台(不阻塞 UI):立刻标记「启动中」,
        由 _poll_launching 轮询抓窗口句柄(趁 claude 改标题前),抓到再落盘并置前。
        session_id 非空 → 续接用户在下拉里选的那条会话。"""
        launch(m, session_id)
        launching[m.name] = 0
        _refresh_states()                   # 立刻给「启动中」反馈
```

替换 `on_start`:

```python
    def on_start(name: str, session_id=None) -> None:
        """面板里点「启动」→「确定」后发来 (name, session_id):拉起控制台。
        session_id 为下拉选中的会话(None=新会话)。已运行/启动中忽略。
        没有「全部启动」:只能单个启动,从源头杜绝齐发挤崩 daemon 的团灭。"""
        m = by_name.get(name)
        if not m or name in launching or _live_hwnd(name) is not None:
            return
        start_member(m, session_id)
```

- [ ] **Step 3: 加会话刷新 + 删除处理函数**

在 `on_start` 之后(`panel.member_clicked.connect(...)` 之前)加:

```python
    member_states: dict[str, str] = {}      # 上一轮各成员状态,用于「刚回到未运行」时刷下拉

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
```

- [ ] **Step 4: 在 `_refresh_states` 里「进入未运行态」时刷新下拉**

在 `_refresh_states` 的 for 循环里(`panel.set_message(...)` 之后)追加:

```python
            # 刚回到/初次为「未运行」→ 刷新它的会话下拉(避免每 tick 重扫文件)
            if states[m.name] == "down" and member_states.get(m.name) != "down":
                _refresh_sessions(m.name)
            member_states[m.name] = states[m.name]
```

- [ ] **Step 5: 接信号**

把 `panel.start_requested.connect(on_start)` 保持不变(Qt 会按新签名传两个参数)。在 `panel.open_dir_requested.connect(on_open_dir)` 附近追加:

```python
    panel.delete_session_requested.connect(on_delete_session)
```

> 注:`member_states`/`_refresh_sessions`/`on_delete_session` 定义在 `start_member` 之后、`_persist_and_rebuild` 之前即可(均在 `main()` 闭包内,`_refresh_states` 引用 `member_states` 因闭包延迟求值,运行时已存在)。如担心顺序,把 `member_states: dict ... = {}` 上移到 `launching: dict ... = {}` 附近声明。

- [ ] **Step 6: 重建后清理 member_states**

在 `_persist_and_rebuild` 里 `last_order = []` 附近追加(成员增删改后,旧状态作废,让下拉重新刷):

```python
        member_states.clear()
```

- [ ] **Step 7: 离屏装配自检**(项目惯例:`QApplication.exec` 打桩成返回 0)

Run:
```bash
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -c "
import claude_cockpit.main as M
from PySide6.QtWidgets import QApplication
QApplication.exec = lambda *a, **k: 0    # 打桩:不进事件循环
rc = M.main()
print('assembly rc =', rc)
assert rc == 0
"
```
Expected: 打印 `assembly rc = 0`(装配无异常)。
> 若提示找不到 agents.yaml,先确认项目根有 `agents.yaml`(开发机应已存在)。

- [ ] **Step 8: 全量测试**

Run: `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q`
Expected: 全绿(原 22 + 新增 sessions/launcher 测试)。

- [ ] **Step 9: Commit**

```bash
git add src/claude_cockpit/main.py
git commit -m "feat: main 刷新会话下拉、按选中会话启动、处理删除会话"
```

---

## Task 8: 文档更新(CLAUDE.md)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 launcher 一节的「没有 --resume」**

在 CLAUDE.md「源码地图」里 launcher.py 那行,把 `(ping 拖 ~3s,给抓句柄留窗口;**没有 --resume**)` 改为:

```
(ping 拖 ~3s,给抓句柄留窗口;`--resume` 由面板下拉选会话后经 session_id 传入,不自动)
```

并在源码地图里 panel.py 那行末尾补一句、新增 sessions.py 一行:

```
- **sessions.py** — 扫 `~/.claude/projects/<编码cwd>/*.jsonl` 列成员历史会话(id/标题/最后活跃)、删除会话;标题取最后一条 `ai-title`,回退首条用户消息。
```

在「当前交互行为」里补一条:

```
- **未运行成员**名字下方有个**会话下拉**:默认选中最近一次会话,可点开换/新建/删除(删除二次点确认)。点「启动」→「确定」后按选中项 `claude --resume <id>`(选「新会话」则不带)。运行中该位置换回控制台实时标题。
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 补充会话下拉/续接说明"
```

---

## 验收清单(全部完成后)

- [ ] 未运行成员卡片名字下方显示会话下拉(默认「续:<最近会话标题>」,无历史显示「＋ 新会话」)。
- [ ] 点开下拉:第一行「＋ 新会话」,其下按最近倒序列出会话(标题·日期),每条带删除「×」。
- [ ] 删除「×」二次点确认:第一下变红「确认?」,再点真删,删后下拉刷新。
- [ ] 点「启动」→「确定」:选了会话则新控制台 `claude --resume <id>`;选「新会话」则不带(同现状)。
- [ ] 成员运行中:名字下方换回控制台实时标题(下拉隐藏);跑完回到未运行后下拉重新出现并刷新。
- [ ] `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q` 全绿。
- [ ] 离屏装配自检 rc=0。
- [ ] 硬约束未破坏:无「全部启动」、句柄出生时抓只认 HWND、自动动作不 launch、小青蛙信号双通道不动、无窗用 pythonw。
