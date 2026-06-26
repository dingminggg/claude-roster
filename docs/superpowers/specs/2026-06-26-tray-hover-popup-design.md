# 托盘悬停弹出「谁有消息」可点列表

日期:2026-06-26

## 背景与目标

当前有消息时的流程:托盘图标闪烁 → 左键单击 → 打开/还原面板 → 再点成员卡 →
控制台最大化。三步,略繁琐。

目标:**托盘图标有消息时,鼠标悬停其上方 → 直接弹出一个可点小浮层,列出谁有消息;
点一行即等价于现在「点成员卡」的效果(那个控制台最大化弹到眼前、其余最小化、标记已读)。**
跳过「开面板 → 找卡 → 点卡」三步,悬停即看、点即跳。

## 触发方式(已与用户确认)

鼠标**悬停**触发(非左键、非右键菜单)。

技术现实:`QSystemTrayIcon` 在 Windows 上没有原生 hover 事件(只有 tooltip 文本、
左/双击 `activated`、右键菜单)。要实现「悬停弹出可点层」,只能后台定时器轮询
`QCursor.pos()` 对 `tray.geometry()` 命中判定。用户已知悉并接受其唯一局限:
图标被折叠进任务栏「^ 隐藏图标」溢出区时 `tray.geometry()` 可能失准,悬停弹不出。

## 组件设计(单一职责,边界清晰)

### 1. `TrayPopup`(panel.py 新增,纯视图)

- 入参:一组成员 `(name, emoji, color)`(顺序按 members 配置顺序,稳定)。
- 渲染:每行一个可点按钮,内容 `<emoji> @<name>  ✉`。点击发 `picked(str)` 信号(成员 name)。
- 样式:复用现有 `#popup` / `#popitem` 的 QSS,无需新增配色。
- 窗口类型:`Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`,
  并设 `WA_ShowWithoutActivating`(不抢焦点、不把当前前台窗口踢走)。
  **不用 `Qt.Popup`** —— 那种一移开鼠标就当「点了外面」自动关闭,与悬停模型冲突;
  本浮层的显隐完全由 main.py 的悬停定时器控制。
- 无状态同步:每次悬停显示时按当前 pending **重新构建**一个实例(参照 `_SessionPopup`
  的 `WA_DeleteOnClose` 用法,关一个销毁一个,不堆积)。

对外:构造函数接收成员行数据;`picked(str)` 信号。

### 2. main.py 悬停控制器

新增 `hover_timer`(约 150ms)及 `_hover_tick / _show_tray_popup / _hide_tray_popup`:

- `_hover_tick`:
  - `cur_pending` 为空 → 若浮层在显示则隐藏,然后 return(零额外开销)。
  - 取 `QCursor.pos()` 与 `tray.geometry()`:
    - 光标在图标矩形内、且浮层未显示 → `_show_tray_popup()`。
    - 光标既不在图标矩形、也不在浮层矩形(外扩几 px 容差)→ 累计 miss;
      连续 miss 达到阈值(1~2 拍)→ `_hide_tray_popup()`。否则保持。
  - `tray.geometry()` 返回空/无效矩形(溢出区) → 不做悬停判定(已接受的局限)。
- `_show_tray_popup`:
  - 按 members 顺序、筛出在 `cur_pending` 里的成员,构建 `TrayPopup`,
    `picked` 连到 `on_row_click`(并在回调里关闭浮层)。
  - 定位:浮层**贴图标正上方、右边缘对齐**(任务栏在底部场景),夹紧进所在屏幕可见区。
  - 调 `_ack_blink()`(你已经在看了 → 托盘停闪);浮层显隐与闪烁解耦。
- `_hide_tray_popup`:关闭并丢弃当前浮层实例,清 miss 计数。

### 3. `tray_popup_decision(...)` 纯函数(main.py 模块级,可单测)

把「显示 / 隐藏 / 不动」的判定从 Qt 几何里剥离出来,签名形如:

```
tray_popup_decision(has_pending: bool, over_icon: bool, over_popup: bool,
                    visible: bool, misses: int, miss_limit: int) -> str
# 返回 "show" | "hide" | "none"
```

仿照现有 `newly_pending` 的风格,给它写单元测试覆盖各组合;Qt 几何/定位部分留在
控制器里不单测(由离屏装配自检兜底)。

## 数据流

```
hover_timer(150ms) → _hover_tick
   读 cur_pending(tick 每秒刷新)、QCursor.pos()、tray.geometry()、当前浮层状态
   → tray_popup_decision(...) → "show"/"hide"/"none"
       show → _show_tray_popup:建 TrayPopup(按 cur_pending) + 定位 + _ack_blink() + 显示
       hide → _hide_tray_popup:关闭实例
点浮层某行 → picked(name) → on_row_click(name)
   (最大化该控制台 / 其余最小化 / 清 turn-ended / card_read / ack) + 关闭浮层
```

## 门控与既有行为

- 浮层用 **`cur_pending` 非空**门控(有成员有消息就能悬停弹),**不**用「正在闪烁
  (`cur_pending - acked`)」门控 —— ack 停闪后只要还有没看的消息,悬停仍能跳过去。
- 显示浮层时调 `_ack_blink()` 停闪,与现有「点托盘 / 点卡」停闪一致。
- **左键单击托盘**行为保持不变(`_on_tray_activated`:ack + 显示/隐藏面板),与悬停浮层不冲突。
- 点行复用 `on_row_click`:窗口已死时它本就安全 no-op,点完照常关浮层。

## 错误处理 / 边界

- `tray.geometry()` 空或无效 → 跳过悬停判定,不崩(溢出区局限,已接受)。
- 浮层定位夹紧到 `QGuiApplication.screenAt(光标)` 的可见区,避免出屏。
- 成员增删改 / rebuild 不影响:浮层每次现建,读的是当下 `cur_pending` 与 `by_name`。
- 死窗口成员仍可能在 `cur_pending`(权限 pending 不清窗口);点它 `on_row_click` no-op,可接受。

## 测试

- 纯逻辑:`tray_popup_decision` 各组合(has_pending × over_icon × over_popup × visible × misses)。
- 现有 22 个测试照常跑过。
- 离屏装配自检(`QApplication.exec` 打桩返回 0)覆盖 Qt 装配不报错。

## 非目标(YAGNI)

- 不做右键菜单版列表、不做左键弹列表(用户明确选悬停)。
- 不动面板内成员卡的信封/闪烁逻辑。
- 不为溢出区失准做额外补偿(无可靠 API)。
