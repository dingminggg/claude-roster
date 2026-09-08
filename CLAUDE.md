# claude-cockpit

轻量原生面板(PySide6),用来**管理一批真实的 `claude` CLI 控制台窗口**:谁答完一轮/等你确认就提醒,点一下把那个黑框最大化到眼前。和 desk-buddy(小青蛙)配套,共用其 Claude Code hook 信号基建。

**不是**自绘聊天界面——每个成员就是一个真实独立的 `claude` 控制台(`CREATE_NEW_CONSOLE`)。

## 跑 / 测

```bash
# 启动(无窗后台)
C:\Users\LQ\PhpstormProjects\claude-cockpit\.venv\Scripts\pythonw.exe -m claude_cockpit.main
# 测试(96 个)
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q
# 离屏渲染面板截图自检;GBK 控制台打印 emoji 要加 PYTHONIOENCODING=utf-8
```

desk-buddy 通过环境变量 `CLAUDE_COCKPIT_PY` 指向本项目的 pythonw 来联动启动(开机自启 + 小青蛙右键「启动驾驶舱」)。

## 源码地图(src/claude_cockpit/)

- **config.py** — `Member` 数据类 + `load_config/save_config/validate_member`;成员清单在 `agents.yaml`(面板增删改会写回)。
- **launcher.py** — `window_title(m)="CCKPT:<name>"`;`launch(m)` 用 `CREATE_NEW_CONSOLE` + `cmd /k title CCKPT:x & cd /d ... & ping -n 4 ... & claude <flags>`(ping 拖 ~3s,给抓句柄留窗口;`--resume` 由面板下拉选会话后经 session_id 传入,不自动)。
- **sessions.py** — 扫 `~/.claude/projects/<编码cwd>/*.jsonl` 列成员历史会话(id/标题/最后活跃)、删除会话;标题取最后一条 `ai-title`,回退首条用户消息。
- **winman.py** — Win32(ctypes):`find_by_title / is_window / wait_for_title / is_console_window / bring_to_front / maximize / minimize`。
- **store.py** — `~/.claude/data/claude-cockpit/handles.json`,缓存 `name -> hwnd`,重启 cockpit 复用还活着的窗口。
- **settings.py** — `~/.claude/data/claude-cockpit/settings.json`,面板小设置(目前仅 `sound_enabled`,默认开);与 store 分开各管各的。
- **sound.py** — `play()` 播自带 `assets/guagua.mp3`(从小青蛙搬来,本项目自带不依赖它),用 `QMediaPlayer`,失败回退 `winsound` 蜂鸣,异常全吞。
- **cc_signals.py** — 文件信号,**两条独立通道**(见下)。
- **matching.py** — `match_pending(records, members)` 按规范化 cwd 把信号对到成员;`norm_path`。
- **peers.py** — 读 `~/.claude/sessions/<pid>.json` 探「同机 Claude 会话」:`read_peers()` 拿 cwd/会话名/忙闲,`match_peers()` 按规范化 cwd 对到成员(复用 `matching.norm_path`,与 `match_pending` 同口径)。判活 = `pid_alive()` + `updatedAt` 30min 时效兜底(pid 会被系统复用,光看 pid 会把陈旧残留当活会话);同一 cwd 多会话取 `updated_at` 最大的那个。**那批 json 是 Claude Code 的内部文件、不是公开契约**,所以本模块只读不写、异常全吞:探不到就返回空,面板退回兜底的「运行中」,不影响任何既有功能。
- **panel.py** — 深色面板 UI:成员卡、运行键胶囊(四态+兜底)、内联确认、闪动信封、固定宽 310;导出 `UP_STATES`(起来了的那几个状态,明暗/手型/信封统一按它判断,别再散着写 `== "running"`)。右键菜单由 `_Card.build_menu()` 单独搭出来(不在 `contextMenuEvent` 里现搭——`exec` 阻塞,不抽出来没法单测)。
- **hooks/** — `turn_ended.py`(Stop 写)、`clear.py`(UserPromptSubmit 清)。
- **main.py** — 装配:配置/面板/轮询(1s tick + 200ms 启动轮询 + 550ms 托盘闪)/窗口管理/托盘/单实例。

## 信号双通道(关键设计,别搞混)

两条通道都在 `~/.claude/data/claude-cockpit/` 下,**都由本项目自己的 hook 读写**(已和小青蛙解耦):

| 通道 | 目录 | 写 | 清 | 谁读 |
|---|---|---|---|---|
| 权限确认 | `~/.claude/data/claude-cockpit/pending/` | Notification hook(消息含 "permission") | Stop / UserPromptSubmit | **只有驾驶舱** |
| 答完一轮 | `~/.claude/data/claude-cockpit/turn-ended/` | Stop hook | UserPromptSubmit / 点卡已读 / 超时 prune | **只有驾驶舱** |

> 两通道语义不同:pending=在等你确认权限(Notification 写),turn-ended=答完该你看了(Stop 写)。分开放是因为生命周期/清除时机不同。两者驾驶舱都当「有消息」(信封+托盘闪+提示音)。

`~/.claude/settings.json` 里已挂(全部用 cockpit venv 的 python,**不再引用 desk_buddy**):
- **Stop** → `claude_cockpit.hooks.turn_ended`(写答完 + 顺手清 pending)
- **UserPromptSubmit** → `claude_cockpit.hooks.clear`(清 turn-ended + 清 pending)
- **Notification** → `claude_cockpit.hooks.notify`(消息含 "permission" 时写 pending)

## 当前交互行为

- **启动**:点「启动」→ 原地换成「确定/取消」内联确认(不弹窗)→ 确定才拉起。启动是非阻塞的:立刻显示「启动中」,200ms 快轮询**趁 claude 改标题前**抓 HWND 落盘,再转「运行中」。
- **运行键四态**同宽胶囊(56×22,只换文字配色,右侧始终对齐一列):`启动`(未运行,灰)/ `启动中`(琥珀,还没起来)/ `忙碌中`(蓝,起来了正在干活)/ `空闲`(绿,可以找它了)。忙/闲来自 `peers` 探到的会话状态;**窗口活着但探不到状态时兜底显示 `运行中`(绿),绝不退化成「未运行」**(否则会重复开空白窗口,见硬约束 3)。未运行的卡整张置灰、排后;起来了的点亮、排前——`main._RANK` 里忙和闲**同档**,忙闲切换不会让卡片上下乱跳。
- **右键成员卡**:`复制会话地址`(把该成员的会话名塞进剪贴板,就是会话间发消息用的地址;成员名 ≠ 会话名,成员叫 `fad-2`、会话叫 `fad-backend-2-f3`,不给出来对不上)/ 打开目录 / 编辑 / 删除。探不到地址时该项**置灰而不是隐藏**(隐藏用户会以为功能没了),tooltip 说明原因。
- **有新消息**(答完一轮/等权限):名字后面一个**白色小信封 ✉ 闪烁**(550ms)+ **托盘图标闪** + **响一声提示音**(成员「新进入」pending 时响一声,首个 tick 静默播种避免开机狂叫;托盘菜单「提示音」可关,存 settings.json)。
- **点成员横条**(仅运行中):把它的控制台 **maximize 最大化**弹到眼前 + 标记已读(✉ 消失)+ 停闪。**注意不要用 bring_to_front**——它带 `SW_RESTORE` 会把最大化还原。未运行点横条无反应(只有「启动」键能开)。
- **托盘闪烁** = `cur_pending - acked` 非空才闪;点托盘图标或点任一卡 → ack 停闪(列表里各自的 ✉ 仍在,逐个点掉);新成员答完会重新闪。
- **未运行成员**名字下方有个**会话下拉**:默认选中最近一次会话,可点开换/新建/删除(删除二次点确认)。点「启动」→「确定」后按选中项 `claude --resume <id>`(选「新会话」则不带)。运行中该位置换回控制台实时标题。
- 面板**固定宽 310、无最大化按钮**;单实例(QLocalServer,再启动只把已有面板弹前台);托盘可显隐/退出;深色标题栏(DWM)。

## 硬约束(踩坑换来的,务必遵守)

1. **绝不批量/齐发启动 claude** —— 同时拉起多个交互式 claude 会**挤崩共享的 Claude Code daemon**,导致「团灭」(所有窗口一起关)。所以**没有「全部启动」按钮**,只能单个、由用户按节奏启动。
2. **句柄在出生时抓、之后只认句柄**:窗口标题先被设成 `CCKPT:<name>`,claude 起来后会改标题;务必趁改名前用 `wait_for_title` 抓到 HWND 缓存。之后所有「窗口还在吗」一律用 `IsWindow(hwnd)`(配合 `is_console_window`)判断,**不要再查标题**。
3. **自动动作只碰「缓存里且还活着」的句柄,绝不自动 launch** —— 否则会重复开空白窗口(历史 bug)。
4. **信号通道已自给自足**:pending + turn-ended 两条都由本项目 hook 读写,不再依赖 desk-buddy(小青蛙)。改 hook/信号目录时保持 cockpit 自洽,别又把它接回 desk_buddy。
5. 无窗启动用 **pythonw.exe**(普通 python.exe 会留个黑框,关掉它会连带杀死 cockpit)。

## Git

仓库作者 `dingminggg`。提交信息用中文 + 末尾带 `Co-Authored-By: Claude ...`。改完跑一遍 pytest + 离屏装配自检(`QApplication.exec` 打桩成返回 0)再提交。
