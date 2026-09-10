# claude-cockpit

轻量原生面板(PySide6),用来**管理一批真实的 `claude` CLI 控制台窗口**:界面是一张**办公室平面图**——每个成员一个俯视工位、按部门分区落在地毯上,谁答完一轮/等你确认就屏幕闪着提醒,点一下把那个黑框最大化到眼前。和 desk-buddy(小青蛙)配套(信号通道现已自给自足,见硬约束 4)。

**不是**自绘聊天界面——每个成员就是一个真实独立的 `claude` 控制台(`CREATE_NEW_CONSOLE`)。

## 跑 / 测

```bash
# 启动(无窗后台)
C:\Users\LQ\PhpstormProjects\claude-cockpit\.venv\Scripts\pythonw.exe -m claude_cockpit.main
# 测试(147 个)
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q
# 离屏装配自检(把 QApplication.exec 打桩成返回 0,跑 main() 看 rc 0)。
# ⚠ 跑之前先确认没有 cockpit 在跑:main() 开头的单实例探测发现已有实例会直接
#   return 0,此时 rc 0 的含义是「已有实例」而不是「启动没问题」,自检等于没做
#   (踩过:自检连报三次 rc 0,真机一起就崩)。
# GBK 控制台打印 emoji 要加 PYTHONIOENCODING=utf-8。
# 注意:offscreen 平台没有中文字体,拿它截图看到的全是方框——
# 要肉眼核对画面就别设 QT_QPA_PLATFORM,用默认 windows 平台抓图。
```

desk-buddy 通过环境变量 `CLAUDE_COCKPIT_PY` 指向本项目的 pythonw 来联动启动(开机自启 + 小青蛙右键「启动驾驶舱」)。

## 源码地图(src/claude_cockpit/)

- **config.py** — `Member` 数据类 + `load_config/save_config/validate_member`;成员清单在 `agents.yaml`(面板增删改会写回)。`dept` 是可选的部门(画布上的地毯分区,留空 → 「未分配」),老 yaml 缺字段读成空。
- **launcher.py** — `window_title(m)="CCKPT:<name>"`;`launch(m)` 用 `CREATE_NEW_CONSOLE` + `cmd /k title CCKPT:x & cd /d ... & ping -n 4 ... & claude <flags>`(ping 拖 ~3s,给抓句柄留窗口;`--resume` 由面板下拉选会话后经 session_id 传入,不自动)。`launch` 传 `env=child_env()` 剔除 `CLAUDE_CODE_CHILD_SESSION`——cockpit 若从 Claude 会话里启动会继承该标记,透传给成员窗口会让 claude 把自己当嵌套子会话、不保存 transcript(无法 resume)。
- **sessions.py** — 扫 `~/.claude/projects/<编码cwd>/*.jsonl` 列成员历史会话(id/标题/最后活跃)、删除会话;标题取最后一条 `ai-title`,回退首条用户消息。
- **winman.py** — Win32(ctypes):`find_by_title / is_window / wait_for_title / is_console_window / bring_to_front / maximize / minimize`。
- **store.py** — `~/.claude/data/claude-cockpit/handles.json`,缓存 `name -> hwnd`,重启 cockpit 复用还活着的窗口。
- **settings.py** — `~/.claude/data/claude-cockpit/settings.json`,面板小设置(`sound_enabled` 默认开、`always_on_top`)+ `office` 段(画布布局:地毯位置尺寸 / 工位偏移 / 窗口尺寸 / 缩放,由 `layout.py` 读写);与 store 分开各管各的。
- **sound.py** — `play()` 播自带 `assets/guagua.mp3`(从小青蛙搬来,本项目自带不依赖它),用 `QMediaPlayer`,失败回退 `winsound` 蜂鸣,异常全吞。
- **cc_signals.py** — 文件信号,**两条独立通道**(见下)。
- **matching.py** — `match_pending(records, members)` 按规范化 cwd 把信号对到成员;`norm_path`。
- **peers.py** — 读 `~/.claude/sessions/<pid>.json` 探「同机 Claude 会话」:`read_peers()` 拿 cwd/会话名/忙闲,`match_peers()` 按规范化 cwd 对到成员(复用 `matching.norm_path`,与 `match_pending` 同口径)。判活 = `pid_alive()` + `updatedAt` 30min 时效兜底(pid 会被系统复用,光看 pid 会把陈旧残留当活会话);同一 cwd 多会话取 `updated_at` 最大的那个。**那批 json 是 Claude Code 的内部文件、不是公开契约**,所以本模块只读不写、异常全吞:探不到就返回空,面板退回兜底的「运行中」,不影响任何既有功能。
- **layout.py** — 办公室画布的布局账本(纯逻辑,不 import Qt):`parse/dump` 读写 settings.json 的 `office` 段、`ensure` 补齐缺省、`dept_of` 归属兜底(空部门 → `UNASSIGNED="未分配"`)。**地毯坐标是绝对值 `[x,y,w,h]`,工位坐标是「相对所属地毯」的偏移 `[x,y]`**(工位是地毯的 Qt 子项,整块挪动时不用重算)。新地毯按人数铺成最多 3 列的网格(不然 13 个成员会被一个个向右撑成一条两千多像素的窄带)。坏数据一律丢弃回默认、绝不抛(与 `peers.py` 同口径:布局是便利功能,不能因为它打不开面板)。
- **office/theme.py** — 画布的**全部配色**(白模风:桌椅地面近乎全白,**颜色只留给屏幕和人**;层次从底到顶 画布 → 地毯 → 桌面,靠明度分层)。**改颜色只改这一个文件**,别再散回图元里;`mix()` 用来给工位地面染状态色。
- **office/seat_item.py** — `SeatItem`:一个工位的 **3/4 斜视**自绘(名字 / 桌子 / 显示器 / 椅子和人 / 底部只读状态行)。工位尺寸 `SEAT_W/SEAT_H` **从 `layout.py` import**(布局算账和绘制各持一份必然对不上)。**屏幕色 = 运行状态,有新消息则整张工位罩一层状态色光晕**(浅底上不能用「变亮」表示闪——那只会变淡、更看不见)。导出 `UP_STATES`(起来了的那几个状态,明暗/手型/闪烁统一按它判断,别再散着写 `== "running"`)。工位上只剩朗读小喇叭一个可点的小东西(`r_speaker`),别处一律当「点工位」——按钮都搬去右键菜单了。字体是模块级常量:`paint` 是「每个工位 × 每次 tick/闪烁/悬停」都跑的,每帧新建 `QFont` 要走字体匹配查找。`moved` 只在**真拖动过**才发(否则点一下按钮就写一次盘)。
- **office/dept_area.py** — `DeptAreaItem`:部门地毯(圆角矩形 + 虚线边 + 部门名 + 右下角拉伸角)。整块可拖,工位作为子项跟着走;抓拉伸角时只改尺寸不挪位置,收缩下限 = `max(layout.AREA_MIN, 装得下现有工位)`。
- **office/view.py** — `OfficeWindow`:场景装配、按部门落座、Ctrl+滚轮缩放、**右键菜单(全部操作的唯一入口:启动 / 续接会话 / 删会话记录 / 复制地址 / 打开目录 / 编辑 / 删除)**、布局存盘(400ms 防抖 + `closeEvent` 兜底)、`refit_scene`(sceneRect 跟着内容长,否则「无限画布」是假的)、`focus_content`(**只在首次装配**时把镜头对准办公室左上角——`rebuild` 每次增删改成员都会跑,每次都对准会把用户拖好的视角弹回去;窗口尺寸同理)。**方法名和信号名与退休的 `panel.Panel` 完全一致**,所以 `main.py` 只需换构造类;`set_order` 是空操作(位置由用户摆,排序无意义)。右键菜单由 `build_menu()` 单独搭出来(不在 `contextMenuEvent` 里现搭——`exec` 阻塞,不抽出来没法单测)。`set_always_on_top` 有守卫:值没变就 return、只有本来可见才 `show()`(无条件 show 会把托盘里隐藏着的窗口硬弹出来)。
- **tray_popup.py** — `TrayPopup`:托盘悬停时弹出的无边框小浮层,列出有消息的成员。原住在 `panel.py`,卡片列表退休时搬出来单过。
- **assets.py** — 自带资源路径(`ICON_PATH`)。图标既给托盘也给窗口用,不该继续挂在某个具体界面模块下面。
- **hooks/** — `turn_ended.py`(Stop 写)、`clear.py`(UserPromptSubmit 清)。
- **main.py** — 装配:配置/面板(`OfficeWindow`)/轮询(1s tick + 200ms 启动轮询 + 550ms 托盘闪 & 工位屏幕闪)/窗口管理/托盘/单实例。

## 信号双通道(关键设计,别搞混)

两条通道都在 `~/.claude/data/claude-cockpit/` 下,**都由本项目自己的 hook 读写**(已和小青蛙解耦):

| 通道 | 目录 | 写 | 清 | 谁读 |
|---|---|---|---|---|
| 权限确认 | `~/.claude/data/claude-cockpit/pending/` | Notification hook(消息含 "permission") | Stop / UserPromptSubmit | **只有驾驶舱** |
| 答完一轮 | `~/.claude/data/claude-cockpit/turn-ended/` | Stop hook | UserPromptSubmit / 点卡已读 / 超时 prune | **只有驾驶舱** |

> 两通道语义不同:pending=在等你确认权限(Notification 写),turn-ended=答完该你看了(Stop 写)。分开放是因为生命周期/清除时机不同。两者驾驶舱都当「有消息」(工位屏幕闪 + 托盘闪 + 提示音)。

`~/.claude/settings.json` 里已挂(全部用 cockpit venv 的 python,**不再引用 desk_buddy**):
- **Stop** → `claude_cockpit.hooks.turn_ended`(写答完 + 顺手清 pending)
- **UserPromptSubmit** → `claude_cockpit.hooks.clear`(清 turn-ended + 清 pending)
- **Notification** → `claude_cockpit.hooks.notify`(消息含 "permission" 时写 pending)

## 当前交互行为

- **启动**:右键工位 →「启动(新会话)」或「续接会话 ▸ 某条」。**工位上没有任何按钮**,所有操作都在右键菜单里;已经在跑的成员菜单里没有启动项(防重复启动)。启动是非阻塞的:立刻显示「启动中」,200ms 快轮询**趁 claude 改标题前**抓 HWND 落盘,再转「运行中」。
- **主视图是一张办公室平面图**(不再是竖排卡片列表):可滚动、Ctrl+滚轮缩放的画布(背景是 60px 的地砖,棋盘式隔一块深一档——纯网格线读起来像方格纸),上面是**部门地毯**(按 `Member.dept` 分,没填的进「未分配」),地毯上摆着**工位**。工位 200×166,**3/4 斜视**画法(参考腾讯 Marvis 办公室那种白模风):从**人的背后**看:名字 → 桌子(梯形桌面 + 前沿板厚 + 两条腿)→ 显示器(**屏幕朝下、正对着座位**)→ 椅子和人(在桌子前面,看到的是后脑勺和椅背)→ 底部一行只读状态。人坐桌前、屏幕对着人,朝向才对——把人摆在桌子后面等于让他盯着显示器背面。正俯视画出来所有东西像贴纸,而且显示器只能画背面、认不出是电脑。**颜色只给两样**:屏幕(=状态)和人(=成员配色),其余全白模,场景才不花。
- **状态看屏幕**:显示器屏幕面按状态上色;**没上班就是空椅子 + 黑屏**(比「整张工位灰掉」直觉得多)——`启动中`(琥珀,还没起来)/ `忙碌中`(蓝,起来了正在干活)/ `空闲`(绿,可以找它了)/ 未运行(灭,整张工位置灰)。**状态只用屏幕颜色表达,画面上不写字**(文字版挂在工位 tooltip 上,悬停查得到)。忙/闲来自 `peers` 探到的会话状态;**窗口活着但探不到状态时兜底显示 `运行中`(绿),绝不退化成「未运行」**(否则会重复开空白窗口,见硬约束 3)。
- **有新消息**(答完一轮/等权限):**整张工位闪**(550ms 半拍罩一层状态色的光晕;颜色仍是状态色,所以「谁在忙」和「谁在叫你」不打架)+ **托盘图标闪** + **响一声提示音**(成员「新进入」pending 时响一声,首个 tick 静默播种避免开机狂叫;托盘菜单「提示音」可关,存 settings.json)。**未运行的工位一律不闪**——没窗口就没有「在等你」这回事。
- **点工位**(仅运行中):把它的控制台 **maximize 最大化**弹到眼前 + 标记已读 + 停闪。**注意不要用 bring_to_front**——它带 `SW_RESTORE` 会把最大化还原。未运行点工位无反应(只有「启动」键能开)。
- **托盘闪烁** = `cur_pending - acked` 非空才闪;点托盘图标或点任一工位 → ack 停闪(其余工位的屏幕仍在闪,逐个点掉);新成员答完会重新闪。
- **工位底部那行是只读的**:只有控制台实时标题(没上班时显示上次会话)。选哪条会话续接、删哪条会话记录,都在右键菜单的子菜单里(`claude --resume <id>`;选「新会话」则不带)。
- **右键工位**(操作的唯一入口):没上班时第一档是 `启动(新会话)` / `续接会话 ▸` / `删除会话记录 ▸`,然后才是 `复制会话地址`(把该成员的会话名塞进剪贴板,就是会话间发消息用的地址;成员名 ≠ 会话名,成员叫 `fad-2`、会话叫 `fad-backend-2-f3`,不给出来对不上)/ 打开目录 / 编辑 / 删除。探不到地址时该项**置灰而不是隐藏**(隐藏用户会以为功能没了),tooltip 说明原因。**右键画布空白处** = 新增成员。图元的 `mousePressEvent` **只处理左键**,右键一律 `ignore()` 交给菜单——不挡的话右键会顺带把控制台弹到眼前(踩过)。菜单里的子菜单必须用 `QMenu(标题, 父菜单)` 显式建、再 `addMenu(子菜单)` 挂上去:直接调父菜单的 `addMenu(标题字符串)`,返回的 QMenu 在 Python 侧没人持有,会被回收掉、点开就报 `Internal C++ object already deleted`(踩过)。
- **布局是用户自己摆的**:工位在地毯上自由拖动(不吸附),地毯整块可拖(名下工位跟着走)、右下角可拉伸——收缩下限是 `max(layout.AREA_MIN, 装得下现有工位)`(工位是拖出来的,可能贴在右下角,光按固定下限会把地毯缩到工位底下)。位置/尺寸/缩放存 `settings.json` 的 `office` 段,400ms 防抖落盘、关窗兜底存一次。**部门归属只认 `agents.yaml` 的 `dept`**——把工位拖到别的地毯上不会改部门,要换部门得改配置(右键「编辑」里有「部门」一栏)。
- 面板窗口**可自由缩放**(不再是固定宽 310);单实例(QLocalServer,再启动只把已有面板弹前台);托盘可显隐/退出;标题栏明暗跟随画布配色(DWM,现在是浅色)。

## 硬约束(踩坑换来的,务必遵守)

1. **绝不批量/齐发启动 claude** —— 同时拉起多个交互式 claude 会**挤崩共享的 Claude Code daemon**,导致「团灭」(所有窗口一起关)。所以**没有「全部启动」按钮**,只能单个、由用户按节奏启动。
2. **句柄在出生时抓、之后只认句柄**:窗口标题先被设成 `CCKPT:<name>`,claude 起来后会改标题;务必趁改名前用 `wait_for_title` 抓到 HWND 缓存。之后所有「窗口还在吗」一律用 `IsWindow(hwnd)`(配合 `is_console_window`)判断,**不要再查标题**。
3. **自动动作只碰「缓存里且还活着」的句柄,绝不自动 launch** —— 否则会重复开空白窗口(历史 bug)。
4. **信号通道已自给自足**:pending + turn-ended 两条都由本项目 hook 读写,不再依赖 desk-buddy(小青蛙)。改 hook/信号目录时保持 cockpit 自洽,别又把它接回 desk_buddy。
5. 无窗启动用 **pythonw.exe**(普通 python.exe 会留个黑框,关掉它会连带杀死 cockpit)。

## Git

仓库作者 `dingminggg`。提交信息用中文 + 末尾带 `Co-Authored-By: Claude ...`。改完跑一遍 pytest + 离屏装配自检(`QApplication.exec` 打桩成返回 0)再提交。
