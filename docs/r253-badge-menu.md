# R253 · 浮窗 `?` 徽章可点击 → 「选择口径」选单

用户反馈（2026-11-12 15:06）：

> 问号徽章 我觉得可以改成是可以点击的 点击后就是选择口径 的选单

## 一、交互

浮窗里歧义物品（同短名多口径，如 .338 AP vs .300 AP）主价左侧的黄色 `?`
徽章现在**可以点击**：

1. 单击徽章 → 徽章右下方弹出「选择口径」选单（XP Luna 弹出菜单风格：白底、
   蓝边、深蓝标题条）；
2. 每行 = 圆点 + 物品全名 + 右对齐精确卢布价（散装标 `/发`，无价红字）；
   **实心蓝点** = 当前推断口径（`price.name`），空心灰圈 = 其他候选；
3. 点某行 → 该物品价格立即换成所选口径并收起选单；点菜单外任意处 → 仅收起；
   再点徽章 → 收起；
4. 选完徽章保留（黄 `?` 仍在），可再次点开重选。

选中后 `price.manual` 生效：候选只有单价没有历史行情，四种时间口径显示
同一个所选价（切口径按钮不回跳推断价），直到再次手动重选。

## 二、实现（`tools/scan.py`）

- **标签窗（role 0）去掉 `WS_EX_TRANSPARENT`**：它让系统完全跳过该窗口的鼠标
  消息，点了也没用；改用 `WM_NCHITTEST` 精确放行——命中徽章矩形 → `HTCLIENT`，
  其余 → `HTTRANSPARENT`。ULW 位图 alpha=0 的像素本就不参与命中，行为与原先
  「全穿透」等效，仅徽章可点。
- `render_labels(..., badges_out=None)`：传入 list 时收集每件歧义物品的徽章
  矩形（画布坐标），浮窗随位图更新存进 `self.badges`；三种排版分支（下方 /
  上方兜底 / inline 单行）都收集，inline 分支按 fs2 字号。
- **选单窗（role 6）**：新的分层窗（LAYERED / TOPMOST / TOOLWINDOW /
  NOACTIVATE 不抢焦点）。`render_menu()` 画位图并返回行矩形；`open_menu()`
  弹在徽章右下角（clamp 屏幕内）并 `SetCapture`——全屏按下都送进选单窗，
  实现点菜单外关闭；`menu_click()` 行内 → `pick_candidate()`，行外 → 关闭；
  `close_menu()` 时 `ReleaseCapture` + `SW_HIDE`。
- `price_base()` 优先 `price.manual`（正数才生效）。
- 名字过长截断加 `…`，名字与价格间永远留 ≥1.2×字号 空隙（修掉首版
  「FMJ810₽/发」挤在一起的问题）。
- 口径切换按钮（cycle）会先收起选单，避免重绘后选单位置漂移。

## 三、验证

- 单测 `tests/test_r253_badge_menu.py` 8 条：manual 覆盖四种口径 / 徽章矩形
  中心=黄色像素 / 无歧义不收集 / 选单行矩形与蓝点 / 空候选 / 名字价格不重叠 /
  原生链路源码契约（hit_badge/SetCapture/ReleaseCapture/role 6…）。
- 原生冒烟（真实窗口）：show → hit_badge 命中 → open_menu（2 行）→ 点第 2 行
  → `manual=38 / manualName=5.56x45毫米 FMJ` → `price_base=38` → 重开 →
  点外关闭 → close 全部窗口，全程无异常。
- 选单预览 `build/_r253_menu_preview2.png`（标题条 + 蓝点 + 价格右对齐 + 无价红字）。

## 四、边界

- 候选列表来自 BFF（`price.candidates`，R251 生成 ≤6 条），随交接白名单的
  `price` dict 原样传给浮窗；没有候选的物品徽章点了不会弹（保持原样）。
- 选单在游戏全屏上仍不可见鼠标焦点变化（NOACTIVATE），Esc 不可达（窗口不
  聚焦），关闭途径 = 点行 / 点外 / 再点徽章 / 切口径。
- 手动选择不回写 BFF，仅本地浮窗显示；下次框选重新从推断价开始。
- 全量回归：`build/_pytest_r253.xml`。
