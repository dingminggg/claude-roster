# claude-cockpit

Windows 原生轻量面板:把每个「成员」拉起成一个**真正的 `claude` 控制台窗口**,
一个置顶小面板做总控——谁需要权限确认时,自动把它的黑框弹到面前;你只在真终端里打字。

不在网页里渲染对话(那是 claude-groupchat 的做法)。这里追求**还原真实 claude CLI**,
面板只负责「启动控制台 + 谁喊你就把谁置前 + 状态一眼可见」。

## 安装

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 配置

编辑 `agents.yaml`,每个成员一段(name / cwd / emoji / color / model / permission_mode):

```yaml
agents:
  - name: shop
    cwd: C:\path\to\project
    emoji: "🏪"
    color: "#2980b9"
    permission_mode: default      # default / acceptEdits / plan / bypassPermissions
    # model: opus                 # 可选,留空用 CLI 默认
```

启动命令按 `model` / `permission_mode` 映射成 `claude --model ... --permission-mode ...`
(bypassPermissions → `--dangerously-skip-permissions`)。

## 运行

```
.venv\Scripts\python.exe -m claude_cockpit.main
# 或装好后直接:claude-cockpit
```

- 面板列出成员;点「▶ 全部启动」给每个成员开一个 `CCKPT:<name>` 控制台(各在其 cwd 跑 claude)。
- 点成员行 → 把对应控制台置前;若没开则开。
- 某成员的会话**等权限确认**时,~1 秒内自动把它的控制台弹到前面,面板该行变 🟡;答复后回 ⚪。
- 托盘:显示/隐藏面板、退出(退出不杀控制台)。

## 与 desk-buddy 的关系

「谁在等你确认」的信号来自 **Claude Code 的 hooks**,与 desk-buddy 共用同一信号目录
`~/.claude/data/desk-buddy/pending/`。所以:

1. 先在 desk-buddy 里安装 hooks:
   `desk-buddy\.venv\Scripts\python.exe -m desk_buddy.install_hooks`,然后**重启 Claude Code**。
2. 保持 desk-buddy 运行(青蛙负责出声喊你),cockpit 负责把对的窗口弹到前面——分工不重叠。

**一键同启**:给 desk-buddy 设环境变量 `CLAUDE_COCKPIT_PY` 指向本项目 venv 的 python
(`...\claude-cockpit\.venv\Scripts\python.exe`),启动 desk-buddy 时会顺带拉起 cockpit;
不设就只起桌宠。

未装 hook / desk-buddy 没跑时:cockpit 仍能启动和手动置前控制台,只是没有「自动弹出」。

## 已知限制(v1)

- 仅 Windows。
- Win32 后台置前有系统限制,极端情况下可能退化为「任务栏闪烁」而非真正置顶。
- 状态只有 🟡(等你确认)/ ⚪(已启动)。完整的「忙/闲」绿红灯需要再加一条 hook,留 v2。
- 面板内**不嵌**终端;控制台是独立 OS 窗口。

## 开发

```
.venv\Scripts\python.exe -m pytest -q        # 纯逻辑单测:config / 匹配 / 启动命令 / 状态机
```

GUI(panel)与 Win32(winman)走手动验证。
