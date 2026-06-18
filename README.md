# claude-cockpit

> 仓库名 `claude-roster`,内部包/窗口/信号仍用 `claude_cockpit` / `CCKPT:` 命名。

Windows 原生轻量面板(PySide6):管理**一批真实独立的 `claude` CLI 控制台窗口**。
谁答完一轮、谁在等你确认权限,面板上就闪个红信封提醒你;点一下把那个黑框最大化到眼前、
其余控制台收起,多屏下也能一眼锁定目标会话。

**不是**自绘聊天界面——每个「成员」就是一个真正独立的 `claude` 控制台
(`CREATE_NEW_CONSOLE` 起的窗口),你只在真终端里打字。和 desk-buddy(桌面小青蛙)
配套,共用其 Claude Code hook 信号基建。

## 安装

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 配置

编辑 `agents.yaml`,每个成员一段(面板里增删改会写回此文件):

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
(bypassPermissions → `--dangerously-skip-permissions`;无 `--resume`)。

## 运行

```
# 无窗后台启动(用 pythonw,关掉黑框不会连带杀死面板)
.venv\Scripts\pythonw.exe -m claude_cockpit.main
```

## 交互

- **运行键三态**(同宽胶囊):`启动`(未运行,灰)/ `启动中`(琥珀)/ `运行中`(绿)。
  未运行的卡置灰排后,运行中点亮排前。
- **启动**:点「启动」→ 原地内联确认「确定/取消」(不弹窗)→ 确定才拉起控制台。
  非阻塞:立刻显示「启动中」,趁 claude 改标题前用快轮询抓到窗口句柄落盘,再转「运行中」。
- **有新消息**(答完一轮 / 等权限):名字后一个**白色小信封 ✉ 闪烁** + 托盘图标闪。
- **会话实时标题**:成员名字下面一行小灰字,显示其控制台的实时窗口标题
  (claude 起来后会改成它当前状态);每秒刷新,过长省略号截断、悬停看全文,
  未运行/仍是启动占位则不显示。
- **点成员横条**(仅运行中):把它的控制台**最大化**弹到眼前、**其余运行中的控制台最小化**,
  并标记已读(✉ 消失、停闪)。未运行点横条无反应——只有「启动」键能开。
- **右键成员**:`打开目录`(用资源管理器打开该成员的 cwd)/ `编辑` / `删除`。
- **托盘**:点图标 ack 停闪;可显隐面板 / 退出(退出不杀控制台)。深色标题栏 / 托盘 / 任务栏
  共用一颗多尺寸透明小青蛙图标(`assets/icon.ico`)。
- 面板**固定宽 310、无最大化按钮**;单实例(再启动只把已有面板弹前台);深色标题栏。

> ⚠️ **没有「全部启动」按钮**:同时拉起多个交互式 claude 会挤崩共享的 Claude Code daemon
> 导致「团灭」(所有窗口一起关)。只能单个、由你按节奏启动。

## 信号双通道

面板的提醒来自 **Claude Code 的 hooks**,走两条**独立**的文件信号目录:

| 通道 | 目录 | 谁写 | 谁读 |
|---|---|---|---|
| 权限确认 | `~/.claude/data/desk-buddy/pending/` | Notification hook(消息含 permission) | 小青蛙 + 驾驶舱 |
| 答完一轮 | `~/.claude/data/claude-cockpit/turn-ended/` | 本项目 Stop hook | **只有驾驶舱** |

「答完一轮」单开一条通道,是为了**不让小青蛙对每轮结束都唠叨**——青蛙永远只管权限提醒。

`~/.claude/settings.json` 里需挂上(用本项目 venv 的 python):

- **Stop** → `desk_buddy.hooks.clear` + `claude_cockpit.hooks.turn_ended`
- **UserPromptSubmit** → `desk_buddy.hooks.clear` + `claude_cockpit.hooks.clear`
- **Notification** → `desk_buddy.hooks.notify`

挂好后**重启 Claude Code** 生效。

## 与 desk-buddy 的关系

- 保持 desk-buddy 运行(青蛙负责出声喊你),cockpit 负责把对的窗口弹到眼前——分工不重叠。
- **一键同启**:给 desk-buddy 设环境变量 `CLAUDE_COCKPIT_PY` 指向本项目 venv 的 `pythonw.exe`,
  启动 desk-buddy 时会顺带拉起 cockpit(开机自启 + 小青蛙右键「启动驾驶舱」);不设就只起桌宠。
- 未挂 hook / desk-buddy 没跑时:cockpit 仍能启动并手动操控控制台,只是没有自动提醒。

## 开发

```
QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe -m pytest -q   # 纯逻辑单测
```

源码地图见 [`CLAUDE.md`](CLAUDE.md)。GUI(panel)与 Win32(winman)走手动验证 + 离屏装配自检。

## 已知限制

- 仅 Windows(Win32 ctypes 抓窗口/置前)。
- Win32 后台置前有系统限制,极端情况下可能退化为任务栏闪烁而非真正置顶。
- 句柄在窗口出生时抓、之后只认句柄(`IsWindow`),不再查标题。
- 面板内**不嵌**终端;每个控制台是独立 OS 窗口。
