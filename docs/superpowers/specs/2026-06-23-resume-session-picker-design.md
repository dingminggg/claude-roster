# 启动时选会话 / 续接 — 设计

日期:2026-06-23
状态:已与用户确认,待写实现计划

## 背景与目标

claude-cockpit 现在每个成员就是一个真实的 `claude` 控制台,启动时**不带 `--resume`**(见 `launcher.py`,CLAUDE.md 硬约束里有意写明)。用户希望:**启动某个成员时能直接续接它之前的某个会话**,并且要能**一眼看出每个历史会话在干嘛**。

经核实,Claude CLI 的会话数据完全可拿:

- 会话存在 `~/.claude/projects/<编码后的cwd>/<session-uuid>.jsonl`,目录名 = 成员 cwd 把 `:` `\` 全换成 `-`(例:`C:\Users\LQ\PhpstormProjects\claude-cockpit` → `C--Users-LQ-PhpstormProjects-claude-cockpit`)。因此**目录与成员一一对应**。
- 文件名去掉 `.jsonl` = `--resume` 需要的 session-id;文件 mtime = 最后活跃时间。
- 每个 `.jsonl` 内含若干 `type:"ai-title"` 记录(Claude Code 自动生成的人类可读中文标题),随对话演进多次写入,**取最后一条 = 当前标题**。实测标题干净可用(如「优化成员列表点击窗口最大化逻辑」)。本机暂无 `type:"summary"` 记录,不依赖它。
- `claude --resume <session-id> <flags>` 可直接跳进指定会话;不带则开新会话(现状)。

## 交互行为

### 选择器的显示位置与切换
- **未运行(down)** 的成员:名字下方那行(现 `ctitle` 位)显示一个**会话选择器**(下拉),默认选中**最近一次**会话;无任何历史 → 默认「＋ 新会话」。
- **运行中(running)/ 启动中(launching)**:该位置**换回现有的实时窗口标题**(`ctitle`,保持现状完全不变)。
- 选择器与实时标题标签**二选一显示**,由 `set_run_state` 切换可见性。

### 启动流程(沿用现状,不改按钮交互)
点「启动」→ 原地变「确定/取消」内联确认 → 确定。确定时按选择器当前选中项决定命令:
- 选了某会话 → `claude --resume <id> <flags>`
- 「新会话」→ 不加 `--resume`(与现状一致)。

其余启动机制(`CREATE_NEW_CONSOLE`、`cmd /k title CCKPT:x & cd & ping 拖时间 & claude`、200ms 快轮询趁改名前抓 HWND 落盘)**全部不变**。

### 选择器展开后
- 第一行固定「＋ 新会话」。
- 其下按**最后活跃倒序**列出历史会话,**最多 12 条**(超出的老会话不显示,不提供「显示全部」入口 — YAGNI)。
- 每行:`标题 · MM-DD`,右侧一个删除「×」。
- 标题来源优先级:该 `.jsonl` 内**最后一条 `ai-title` 的 `aiTitle`** → 退回**首条用户消息**截断 → 再无则 `(无标题)` + 短 id。
- 点标题区 = 选中该会话并收起浮层。
- 删除「×」= **二次点确认**:第一下把该「×」变红成「确认?」,点浮层别处 / 关闭则复原;再点一次才真删。删除动作 = 移除对应 `.jsonl` 文件,然后刷新列表。
  - 删除只可能发生在未运行成员上(运行中不显示下拉),天然规避「删正在写入的会话文件」。

### 行高
成员行从现在约 40px **略增到约 48–50px**,容下下拉按钮,不显臃肿。

## 代码改动(对照源码地图 src/claude_cockpit/)

### 新增 `sessions.py`(纯逻辑,配 pytest)
- `encode_cwd(path) -> str`:cwd → `~/.claude/projects/` 下的目录名(`:` `\` `/` → `-`)。
- `Session` 数据类:`id: str`、`title: str`、`mtime: float`。
- `list_sessions(cwd, limit=12) -> list[Session]`:扫 `~/.claude/projects/<编码>/*.jsonl`,逐文件解析标题,按 mtime 倒序,截前 `limit` 条。
- `delete_session(cwd, session_id) -> bool`:删对应 `.jsonl`。
- 标题解析需健壮:逐行 `json.loads`,跳过坏行;`ai-title` 取最后一条;无则取首条 `type:"user"` 文本消息截断;再无返回兜底。

### `launcher.py`
- `launch(m, session_id: str | None = None)`:`session_id` 非空时在 claude 命令里插 `--resume <session_id>`;为空时与现状完全一致。

### `panel.py`
- 在卡片左列第二行放一个 `_SessionPicker` 组件:一个按钮(显示当前选中:「续:<标题>」或「＋ 新会话」)+ 一个 `Qt.Popup` 浮层,浮层内自绘每行(标题选择区 + 删除「×」,含二次确认)。
- `_SessionPicker` 与现有 `ctitle` 标签二选一显示;`set_run_state` 切换:down → 显示 picker、藏标题;running/launching → 显示标题、藏 picker。
- 信号变更:
  - `start_requested` 由 `Signal(str)` 改为 `Signal(str, object)`(name, session_id|None)。
  - 新增 `delete_session_requested = Signal(str, str)`(name, session_id)。
- 新方法 `set_sessions(name, sessions: list[Session])`:给指定成员的 picker 灌数据并重置默认选中(最近一条 / 无则新会话)。

### `main.py`
- 接 `start_requested(name, sid)` → `launch(member, sid)`。
- 在成员进入「未运行」态时(构建卡片时、跑完回落 down 时)调用 `sessions.list_sessions` 刷新该成员 picker。
- 接 `delete_session_requested(name, sid)` → `sessions.delete_session(cwd, sid)` 成功后刷新该成员 picker。

## 不做(YAGNI)
- 不在卡片常驻显示会话标题(与运行中实时标题冲突,用户未要)。
- 不做会话搜索 / 重命名 / 置顶。
- 不做删除撤销 / 回收站(二次确认即够)。
- 不做「显示全部」超过 12 条的入口。

## 测试与自检
- `sessions.py` 配纯逻辑 pytest:ai-title 优先、回退首条用户消息、全空兜底;mtime 倒序;`limit` 截断;`encode_cwd` 编码;`delete_session` 删除存在/不存在。
- 改完跑全量 pytest + 离屏装配自检(`QApplication.exec` 打桩返回 0)再提交(项目规矩)。
- 硬约束不变:绝不批量启动;句柄出生时抓、之后只认 HWND;自动动作不 launch;不破坏小青蛙信号双通道;无窗用 pythonw。
