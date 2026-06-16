# claude-cockpit — 设计文档

日期:2026-06-16
状态:已确认,待实现(v1 范围)

## 背景与动机

claude-groupchat 用 Claude Agent SDK 在网页里渲染各成员的回复气泡。用户的真实诉求是:
**还原真实 claude CLI 的体验**,自己只当一个「总控」——谁需要交互时把那个终端弹到面前,
不需要时缩到一边。SDK + 自定义渲染既丢了 CLI 原汁原味,自动「弹出」也要靠重写。

换思路:每个成员就是一个**真正的 `claude` 控制台窗口**;一个轻量原生面板做总控,
靠 Claude Code 的 hook 信号知道「谁在等你」,把那个黑框弹到前面。用户在真终端里直接打字。

这是一个**新的独立项目**(PySide6 原生应用),与 claude-groupchat 几乎不共用代码,
但复用 desk-buddy 已经做好的 CC hook / 信号机制,并与 desk-buddy 融合(一键同启)。

## 目标

- 按成员清单一键拉起 N 个真 `claude` 控制台(各自 cwd / 模型 / 权限)。
- 某成员的会话需要权限确认时,自动把它的控制台窗口弹到前面,面板亮灯。
- 一个常驻轻量面板:列出成员 + 状态,点一下把对应终端置前。
- 与 desk-buddy 融合:共享信号目录,启动 desk-buddy 时可同时拉起 cockpit。

## 非目标(v1 先不做)

- 完整的「忙/闲」绿红灯(需额外 hook 记录 busy/idle)→ v2。v1 只有「🟡 等你确认 / ⚪ 已启动」。
- 在面板内嵌终端(xterm.js 等)——明确不做,终端是独立 OS 窗口。
- 跨平台;**仅 Windows**。
- 打包 exe(先跑源码,后续可加 PyInstaller,参考 desk-buddy)。

## 架构与组件

新项目 `claude-cockpit`,包结构仿 desk-buddy(`src/claude_cockpit/...`,PySide6)。

### 1. 成员配置 `config.py`
- 复用 `agents.yaml` 概念:`name / cwd / emoji / color / model / permission_mode`。
- 项目自带 `agents.yaml`(或复用用户已有路径,见「开放问题」)。
- 加载 + 校验(name 合法、cwd 存在),仿 claude-groupchat 的 `config.py`。

### 2. 控制台启动器 `launcher.py`
- 每个成员开一个独立控制台窗口,标题唯一:`CCKPT:<name>`。
- 命令形如:
  `cmd /c start "CCKPT:<name>" cmd /k cd /d "<cwd>" ^& claude <flags>`
- flags 由 `model` / `permission_mode` 映射(确切 flag 在实现时对照 `claude --help` 核对;
  如 `--model <m>`、bypass→`--dangerously-skip-permissions` 或 `--permission-mode <mode>`)。
- 记录每个成员对应的窗口标题,供窗口管理按标题查找。
- 启动前判重:已存在同标题窗口则不重开(单实例)。

### 3. 窗口管理 `winman.py`(Win32 / ctypes)
- `find_by_title(needle) -> hwnd | None`:EnumWindows + GetWindowText 匹配(仿 tray.ps1 的
  `CloseByTitle` 思路)。
- `bring_to_front(hwnd)`:`ShowWindow(SW_RESTORE)` + 置前;置前用
  AttachThreadInput / 最小化-还原小技巧绕过 Windows 后台置前限制(**主风险点**)。
- `minimize(hwnd)`:`ShowWindow(SW_MINIMIZE)`。
- 全部异常吞掉,拿不到窗口不崩。

### 4. 信号检测 `cc_signals`(复用 desk-buddy)
- **直接读 desk-buddy 的 pending 目录** `~/.claude/data/desk-buddy/pending/`。
- 复用 desk-buddy 的 `cc_signals.read_pending()` / `poll_pending()`(返回 `{session_id: 显示名}`,
  每条含 cwd)。实现时:把 `desk_buddy.cc_signals` 作为依赖导入,或复制该模块(很小)并指向同一目录。
- pending payload 的 `cwd` → 规范化后与成员 cwd 精确匹配,定位是哪个成员在等你。
- hooks 由 desk-buddy 的 `install_hooks` 提供(Notification/Stop/UserPromptSubmit),cockpit 不再
  自己装 hook(融合的一部分)。若用户没装 desk-buddy 的 hook,面板给出提示引导。

### 5. 轮询 + 联动 `app.py`
- QTimer 每秒 `poll_pending()`:
  - 新出现 pending 且能对到成员 → 该成员状态置「🟡 等你确认」,**自动 `bring_to_front` 其控制台**,
    面板对应行高亮。
  - pending 消失 → 状态回「⚪ 已启动」(不强制最小化,避免打断;可配置)。
- 防抖:同一成员的 pending 只在「从无到有」时置前一次,不重复抢焦点。

### 6. 面板 `panel.py`(PySide6)
- 一个常驻、可置顶的小窗(frameless / 简洁),每个成员一行:`emoji  @name  状态点`。
  - 点某行 → `bring_to_front` 该成员控制台。
  - 「🟡」表示等你确认(由信号驱动)。
- 顶部按钮:`▶ 全部启动`(拉起所有成员控制台)、`刷新`。
- 系统托盘图标:显示/隐藏面板、退出。
- 退出 cockpit 不杀控制台(终端是用户的);提供可选「关闭所有控制台」。

### 与 desk-buddy 融合
- **共享信号**:两者读同一 `~/.claude/data/desk-buddy/pending/`,hooks 只装 desk-buddy 那一套。
  分工:桌宠负责「喊你回来(青蛙+声音)」,cockpit 负责「启动控制台 + 把对的窗口置前 + 状态面板」。
- **一键同启**:给 desk-buddy 加一个**可选**集成点——启动时若检测到/配置了 cockpit,就
  `subprocess` 拉起 `python -m claude_cockpit.main`(无窗)。desk-buddy 改动最小、可关闭;
  cockpit 也能完全独立运行。具体落点在实现时定(desk-buddy 的 `main()` 末尾或托盘菜单项)。

## 数据流

1. 面板「▶ 全部启动」/ desk-buddy 同启 → launcher 为每个成员开 `CCKPT:<name>` 控制台跑 claude。
2. 用户在某控制台里对话;该会话要权限确认 → Claude Code `Notification` hook(desk-buddy 的)
   写 `pending/<sid>.json`(含 cwd)。
3. cockpit 每秒 `poll_pending()` 读到新 pending → 按 cwd 对到成员 → `bring_to_front` 其控制台
   + 面板该行亮 🟡;desk-buddy 桌宠同时喊你。
4. 用户在该终端答复 → `UserPromptSubmit`/`Stop` hook(desk-buddy 的 clear)删掉 pending →
   cockpit 下一轮轮询发现消失 → 该行回 ⚪。

## 错误处理

- 找不到控制台窗口(用户手动关了)→ 面板该行标「未运行」,点击=重新启动。
- pending 的 cwd 对不上任何成员(用户的其它 claude 会话)→ 忽略(只认本群 cwd)。
- desk-buddy 未运行 / hook 未装 → 信号目录为空,cockpit 仍能启动/置前控制台,只是没有自动弹出;
  面板提示「未检测到 CC hook,请在 desk-buddy 里安装 hook」。
- Win32 置前失败 → 退化为闪任务栏(系统默认),不崩。
- 所有 Win32 / 文件 IO 异常吞掉并记日志,不阻断面板。

## 测试(手动验证清单)

- 配 2 个成员(不同 cwd)→ 面板列出 2 行;「▶ 全部启动」→ 弹出 2 个 `CCKPT:` 控制台,各在对应 cwd。
- 点面板某行 → 对应控制台被置前。
- 在某控制台触发权限确认(default/plan 模式跑个要批准的操作)→ 该控制台自动弹到前面 + 面板该行 🟡。
- 答复后 → 面板该行回 ⚪。
- 手动关掉某控制台 → 面板该行「未运行」,点击重启。
- desk-buddy 未跑时 → cockpit 仍可启动/置前,提示未检测到 hook。
- desk-buddy「同启」开关开 → 启动 desk-buddy 时 cockpit 自动起来。

## 开放问题(实现前确认或实现时定)

- `agents.yaml` 路径:cockpit 自带一份,还是直接读 claude-groupchat 那份?(默认自带,可配置路径)
- claude CLI 的确切启动 flag(`--model` / 权限模式)以 `claude --help` 为准。
- 面板是常驻小窗为主、还是托盘为主?(v1 两者都有,以小窗为主视图)

## 复用清单

- desk-buddy:`cc_signals`(信号读写/prune)、`install_hooks` + 三个 hook、PySide6 栈、
  托盘/图标/AppUserModelID 套路、pyinstaller spec 套路。
- claude-groupchat:`agents.yaml` 格式与 `config.py` 校验思路、tray.ps1 的「按标题找窗口」Win32 思路。
