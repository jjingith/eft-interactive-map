# R232 · 所有表格滚动区统一去掉被拉伸的位图边框

## 用户原话（2026-11-10 21:16）

> 你检查一下 我发现好几个地方都会有而是表格滚动区的边框位图被放大

R231 只修了弹药页。本轮用 CSSOM 逐视图扫描所有「`border-image` 带 `fill` 且容器明显大于位图」的元素，确认同类问题确实不止一处。

## 检查结果：两条 fill 规则、覆盖所有表格滚区

| 规则 | 位图原尺寸 | 作用对象 | 被拉到的尺寸（实测） |
| --- | --- | --- | --- |
| `table-frame.png 2 fill / 2px stretch !important`（xp-ui-app.css 15.7） | **64×64** | `.loadout-workbench .tbl-scroll`、`.gun-workbench .tbl-scroll`，以及各视图共用的隐藏模板 | 配装 1095×559、弹药 1282×715 |
| `groupbox.png 6 fill / 2px stretch`（xp-ui-app.css 15.2 通用组） | **280×154** | 通用 `html body .tbl-scroll` —— 所有不在上述工作台内的表格（任务 / 市场 / 弹窗里的表格） | 随容器，可达数百~上千像素 |

两条都会把位图中间的细内框线 `stretch` 到整块滚动区，形成一圈模糊灰带；表格有行时被行盖住，**筛空后才露出来**，所以用户会在「好几个地方」看到同样的现象。

另外 `style.css` 的 `.tbl-scroll` 基础定义本来就是干净的
`background: var(--ui-color-surface-raised); border: 1px solid var(--xp-input)`，
`theme-windows-xp.css` 对三张工作台也写了 `background:#ffffff; border:1px solid var(--xp-border-dark)`。
也就是说那两条 fill 位图是**多余的覆盖**，删掉即可回到主题本来的口径。

## 修改（`assets/xp-ui/xp-ui-app.css`，纯删除 + 注释，无新增规则）

1. 15.2 的 groupbox 通用组里摘掉 `html body .tbl-scroll`（其它成员保持不变）。
2. 15.7 的 `table-frame.png 2 fill / 2px stretch !important` 整块删除，CSS 声明里不再出现 `table-frame.png`。
3. 保留 R231 给弹药页的 `html body .am-workbench .am-table .tbl-scroll { border:1px … !important; background-color:#fff !important }`——因为 `style.css` 对这个选择器写了 `border:0`，必须显式压住。
4. 工作台外壳的 `menu-panel-bg.png 12 fill / 1px stretch` **不动**：R231 已实测关掉它空态截图毫无变化，且它与枪匠 / 配装 / 任务共用。

## 验收（`tools/r232_accept.py`，10/10 PASS）

逐个切换 6 个视图（地图 / 任务 / 弹药 / 配枪 / 配装 / 市场），枚举全部 9 个 `.tbl-scroll`：

| 检查 | 结果 |
| --- | --- |
| 全部 9 个 `.tbl-scroll` 的 computed `borderImageSource` | 都是 `none`（改前配装 / 枪匠 / 模板是 `table-frame.png`，通用是 `groupbox.png`） |
| 可见滚区（弹药 1282×715、配装 1095×559） | `borderTopWidth=1px`、不透明 `rgb(255,255,255)` 纯色底 |
| CSS 声明里 `table-frame.png` | 已消失；groupbox 通用组不再含 `.tbl-scroll` |
| R231 弹药空态 / R228 90px 等宽 / R230 默认 32 个全亮 | 全部不回归 |
| JS 异常 | 无 |

截图：`docs/r232/view-*.png`（6 个视图）、`loadout-table.png`（配装表格）。

## 体检还查到、但本轮没改的同类 fill

这些也用 `border-image … fill`，但都是 **XP 面板 / 标题栏 / 按钮底板**（位图中间是纯色或渐变，不是细边框线），不会形成「细线被放大成模糊灰带」，且是整套皮肤的基础，改动面大：

| 位图 | 原尺寸 | 典型大容器 |
| --- | --- | --- |
| `titlebar.png` | 719×36 | 菜单栏 / 工具条（正常）；`gw-page` 1582×666、`am-groups` 278×559、`am-range` 278×86（纵向拉得较厉害） |
| `groupbox.png` | 280×154 | `am-side` 300×715、`lw-board` 472×585、`task-list` 327×459、`gw-browse` **1556×3541** |
| `menu-panel-bg.png` | 434×328 | 四个工作台外壳 1584×757（R231 实测关掉无可见变化） |
| `statusbar-bg.png` / `tbl-head.png` | 630×100 / 630×187 | 状态栏（高 24~31）、表头（高 24~32），比例正常 |

如果枪匠页顶部那条渐变带（`gw-page` 的 titlebar 被拉到 666 高）或 `gw-browse` 的长面板也看着像放大图，可以单独再处理——那属于改 XP 皮肤外观，需要用户确认。清单已存进 `docs/r232/report.json` 的 `remainingFillContainers`。

## 测试

`tests/test_r231_ammo_table_frame.py` 断言按 R232 范围**改向不放宽**（7 条）：
全 CSS 声明不得再出现 `table-frame.png`、groupbox 通用组不含 `.tbl-scroll`、
任何以 `.tbl-scroll` 本身为目标的规则不得带 `fill` / `stretch` 位图
（跳过滚动条轨道与 `.tbl-scroll .tbl-head` 这类子元素的 1px 九宫格皮肤）、
弹药页 `!important` 保留、style.css / theme 的纯色 1px 口径仍在、外壳位图不动。

全量 `python -m pytest tests -q --junitxml=build/_pytest_r232.xml` →
**2038 passed / 0 failed / 0 errors / 1 skipped**（合计 2039，138.81 s，
比 R231 多 2 条，正是该文件里新增的两条契约）。
