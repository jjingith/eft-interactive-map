# XP UI 素材覆盖盘点（R90）

> 目的：回答「是否所有前端 UI 都换成了像素风 XP 素材」。本轮**只盘点、不改样式**；
> 改动在盘点表发布后按可见度分批进行（见文末「分批替换计划」）。
>
> 测量对象：`index.html`（主页面，配装视图激活，`innerWidth=1834`、`devicePixelRatio=0.6667`）。
> 测量方式：Chrome DevTools 逐元素读取 `borderImageSource` / `backgroundImage` / `appearance`，
> 再按下列口径归类。`?mini=1` 使用同一个 `index.html`，但菜单栏 / 上下文栏 / 状态栏 / 工作区
> 在 mini 下隐藏，本轮新增规则只作用于这些容器内的控件。

## 一、档位口径

| 档位 | 定义 | 判定依据 |
|---|---|---|
| **A** | 已用 `assets/xp-ui/` 素材 | `border-image` 或 `background-image` 命中 `btn/input/select/check/radio/progress/groupbox/plaque/tab/scroll/slider/titlebar/win-*`；range / checkbox / radio 由伪元素或整件背景覆盖也算 A |
| **B** | 纯 CSS 绘制 | 有自定义背景 / 边框 / 渐变 / `appearance:none`，但没有引用任何 XP 位图 |
| **C** | 浏览器原生外观 | `appearance` 不为 `none` 的表单控件（range 轨道、select、checkbox、scrollbar、文件选择按钮等），以及原生 tooltip / 原生下拉列表 / 数字微调箭头 / 浏览器右键菜单 |
| **D** | 完全未被样式覆盖 | 没有任何项目级规则，沿用 UA 默认字体与边框（例如未被主题接管的外来浮层 / 表格） |

> 元素级计数与「行为级」分开统计：下拉展开列表、数字微调箭头、`title` tooltip、浏览器右键菜单
> 不是独立元素，无法计入 A/B/C/D 的元素总数，单独列在 C 档行为项。

## 二、逐区域覆盖表

### 1. 菜单栏与菜单面板

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 菜单栏底板 | `.app-menubar` | B | CSS 双层渐变 + 1px 暗线，无菜单栏底板素材 |
| 品牌块 | `.app-menubar .app-brand` / `.app-brand h1` | B | 蓝色 CSS 渐变；R88 已显式移除 plaque-3 米色牌 |
| 顶层菜单按钮（文件/视图/工具/帮助） | `.app-menu-btn` | B | 纯 CSS 平面按钮，悬停浅蓝、展开系统蓝 |
| 下拉菜单面板 | `.app-menu-panel` | **A** | R91 接入 `app-menu-panel-bg.png` 九宫格 7px stretch；深色弹窗内菜单不受影响 |
| 下拉菜单条目 | `.app-menu-item` | B | 文字按钮，悬停 `--xp-sel`；无条目位图 |
| 模式三选一（PvP/PvE/PvPS） | `.app-menubar .game-mode-bar .gm-btn` | B | CSS 渐变 + 1px 边 |
| 账号版本入口 | `.app-account-btn` | B | CSS 边框按钮（26px 高） |
| 运行版本徽标 | `#build-rev` / `.build-rev` | B | CSS 1px 边 + 白底；**徽标本批不可用（烘焙 EMPTY）** |
| 菜单栏状态提示 | `.app-menu-status` | B | CSS 绿色小条；**徽标本批不可用（烘焙 EMPTY）** |
| 旧菜单按钮（战局与任务 / 保存配置 / 设置） | `.menu-btn` | A | `btn-normal/hover/pressed/focus/disabled`，九宫格 5px stretch |
| 旧下拉面板 | `.menu-panel` | B | CSS 面板；内部 select 为 A |
| 地图下拉 | `#map-list` | A | `select.png` 九宫格 + `select-arrow.png` 整件背景 |
| 菜单内复选 / 单选 | `.menu-panel input[type=checkbox/radio]` | A | `check-off/on/indeterminate`、`radio-off/on` 整件 24×24 |

### 2. 主工具条（菜单栏下一行）

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 工具条底板 | `#menubar` | B | CSS 渐变 + 上下 1px 分隔线 |
| 分组分隔线 | `.view-toolbar .vt-sep` | B | CSS 双色 2px 竖线 |
| 视图按钮·常态 | `.view-toolbar .view-btn` | B | 常态透明，仅悬停/选中/焦点用位图 |
| 视图按钮·悬停 / 选中 / 焦点 | `.view-btn:hover` / `[aria-selected=true]` / `:focus-visible` | A | `btn-hover.png` / `btn-pressed.png` / `btn-focus.png` |
| 视图图标 | `.view-toolbar .vt-ico`（内联 SVG） | B | 手绘 SVG，不是像素素材 |
| 旧菜单按钮 | `.menu-wrap .menu-btn` | A | `btn-normal.png` 五态 |

> 视图按钮的**常态**是唯一没有位图的高频按钮态，属于 B；本批第一批补齐。

### 3. 上下文栏（随视图切换的第三行）

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 上下文栏底板 | `#context-bar` | B | CSS 渐变 + 下边框 |
| 槽 / 分组 / 标签 / 空态 | `.cb-pane` / `.cb-group` / `.cb-label` / `.cb-sep` / `.cb-empty` | B | CSS 文本与分隔线 |
| 地图 / 楼层分组框 | `#context-bar section.block.cb-src-block` | B | 进栏后显式移除 `groupbox.png`，退回一行文本 |
| 地图下拉 | `#context-bar #map-list` | A | `select.png` + `select-arrow.png` |
| 楼层按钮 | `.context-bar .floor-item` | A | `btn-normal/hover/pressed`，24px 高 |
| 楼层复选 | `.context-bar .floor-opts .toggle input` | A | 全局 checkbox 素材 |
| 搜索 / 文本输入 | `.context-bar input[type=search/text]` | A | `input.png` 九宫格，31px 高 |
| 上下文栏下拉 | `.context-bar select` | A | `select.png` + 箭头 |
| 配枪类别 / 射击模式芯片 | `.gw-chip`（上下文栏内） | B | CSS 小芯片 |
| 配装浏览分类 | `.lw-cat`（上下文栏内） | B | CSS 文字按钮 / 选中系统蓝 |
| 弹药价格口径 / 单位按钮 | `.am-chip` / `.am-side-head button` | B（按钮部分为 A） | 芯片 B；RESET 等按钮已由 `.am-workbench button` 接管为 A |
| 窄屏横向滚动条（≤900px） | `#context-bar::-webkit-scrollbar` | B | 7px 自绘窄条，未用横向素材（见缺件说明） |

### 4. 底部状态栏

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 应用状态栏 | `#app-statusbar` | **A** | R91 接入 `statusbar-bg.png` 九宫格 2px stretch（替换原 CSS 渐变） |
| 状态栏单元格 | `#app-statusbar .sb-cell` | **A** | R91 接入 `statusbar-cell.png` 九宫格 1px/2px |
| 任务面板底部状态栏 | `.tk-statusbar` | B | 主题渐变 |
| 侧栏状态条 | `.statusbar` | B | 主题渐变 |
| 版本号 | `.sb-rev` / `#build-rev` | B | Consolas 文本 + CSS 边框；**徽标本批不可用（烘焙 EMPTY）** |

### 5. 侧栏各块

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 侧栏容器 | `#sidebar` / `.panel` | B | CSS 面板底 + 边框 |
| 侧栏分组框 | `#sidebar .panel section.block` | A | `groupbox.png` 九宫格 5px fill |
| 品牌标题 | `.brand h1` | A | `plaque-3.png`，14px 左切片 |
| 任务面板标题 | `.task-panel-head h2` | A | `plaque-2.png` |
| 侧栏收起 / 展开 | `#sidebar > .sidebar-collapse` / `.sidebar-expand` | A | `btn-normal.png` 五态，30×30 |
| 任务面板收起 / 展开 | `.task-panel-collapse` / `.task-panel-expand` | A | `btn-normal.png` 五态 |
| 任务搜索框 | `.task-search-wrap input` | A | `input.png` |
| 搜索重置 | `.task-search-reset` | A | `btn-normal.png` |
| 任务模式 / 标签页 | `.tk-mode` / `.tk-tab` | B | CSS 渐变按钮；未接 `tab-*` 或 `btn-*` |
| 模式条外壳 | `.tk-modebar` | B | CSS 1px 边 + 浅底 |
| 任务行容器 | `.task-row` | B | CSS 白底 + 1px 边；无列表行素材 |
| 任务行主按钮 | `.task-main` | B | 透明文字按钮 |
| 任务行开关 | `.task-switch` / `.task-switch-track` / `.task-switch-knob` | B | CSS 自绘拨动开关；**缺开关素材** |
| 楼层小按钮 | `.task-floor` | B | CSS 渐变按钮 |
| 任务右键菜单 | `.task-context-menu` / `.task-context-item` | **A** | R91 接入 `context-menu-bg.png` 九宫格 6px stretch |
| 空态 / 数据来源 | `.task-empty` / `.task-source` | B | 纯文本，无插图素材 |
| 图层 / 图例复选 | `.legend-*` / `.layer-*` 内 checkbox | A | 全局 checkbox 素材 |
| 侧栏滚动条 | `.panel` / `.task-list` | A | 全局 `scroll-v-track/thumb` + 箭头位图 |

### 6. 地图 HUD / 浮窗 / 气泡

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| HUD 按钮 | `.hud button`（含 `.on` 选中态） | A | `btn-normal/hover/pressed/focus` |
| HUD 缩放滑条 | `#display-block .hud-scale input[type=range]` | A | `track.png` + `thumb.png` 伪元素；拇指单独居中修正 |
| HUD 容器 / 数值 | `.hud` / `.hud-scale-value` | B | CSS 定位与文本 |
| 地图提示气泡 | `.gw-tip` / `.lw-tip` / `.am-graph-tip` | B | CSS 白底 / 深底浮层；**缺 tooltip 底板素材** |
| 地图标记标签 | 地图内 SVG / CSS 文本 | B | 项目自绘，无素材 |
| 原生 title 提示 | 全站 `[title]`（实测 3564 个） | C | 浏览器原生 tooltip，无法用 CSS 换皮 |
| 浏览器右键菜单 | 地图空白处 / 非自定义区域 | C | 浏览器原生菜单 |

### 7. 任务面板与任务树

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 任务面板外壳 | `#task-panel` / `.panel` | B | CSS 面板 |
| 任务标题牌 | `.task-panel-head h2` | A | `plaque-2.png` |
| 模式 / 标签页 | `.tk-mode` / `.tk-tab` | B | CSS 渐变按钮 |
| 版本下拉 | `#tk-edition` | **C** | `appearance:auto`，原生 select 外观 |
| 等级区间输入 | `#tk-level-min` / `#tk-level-max`（`.ui-input--num`） | **C** | 原生 number 外观 + 微调箭头 |
| 任务故事搜索 | `#tk-story-search` | **C** | 原生 search 外观（取消按钮 / 内阴影） |
| 任务故事筛选芯片 | `.tk-story-filter` | B | CSS 1px 边按钮 |
| 任务树行 / 开关 / 楼层 | `.task-row` / `.task-switch` / `.task-floor` | B | 见第 5 节 |
| 任务右键菜单 | `.task-context-menu` | **A** | R91 接入 `context-menu-bg.png` 九宫格 6px stretch（同第 5 节） |
| 任务表格钩子 | `.tk-table` / `.tk-tr` / `.tk-td*` | B | 仅结构钩子，无 XP 网格素材 |

### 8. 弹药页

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 工作台外壳 | `.am-workbench` | B | CSS 深色面板 |
| 标签页 | `.am-workbench .am-tab` | A | `tab-inactive.png`；选中 `tab-active.png` |
| 普通按钮 | `.am-workbench button:not(.am-tab)...` | A | `btn-normal/hover/pressed` |
| 分段切换 / 芯片 | `.am-seg-btn` / `.am-chip` | B | CSS 分段控件；无芯片素材 |
| 搜索框 | `.am-workbench .am-search` | A | `input.png` |
| 距离下拉 | `#am-maxdist` / `.am-side select` | A | `select.png` + 箭头 |
| 距离区间数字 | `.am-workbench .am-num` ×6 | **C** | 原生 number 外观 + 微调箭头 |
| 距离下拉（图表区） | `.am-workbench .am-dist select` | **C** | 未纳入 select 素材组，仍是原生下拉 |
| 弹药表格 | `.am-table` / `.am-tr` / `.am-td` | B | CSS 网格；**缺表头 / 网格素材** |
| 图表浮窗 | `.am-graph-tip` | B | CSS 浮窗；缺 tooltip 底板 |
| 徽标 | `.am-badge` 等 | B | CSS 小徽标；本批 badge-md/sm 烘焙 EMPTY，不可用 |
| 空态 / 加载态 | `.am-loading` / 空行 | B | 纯文本，无插图素材 |
| 滚动条 | `.am-side` / `.am-sim-cfg` | A | 全局纵向滚动条素材 |

### 9. 配枪 / 配装页与工作台

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 工作台外壳 | `.gun-workbench` / `.loadout-workbench` | B | CSS 面板 |
| 工作台按钮 | `.gw-btn` / `.lw-clear` | A | `btn-normal/hover/pressed` |
| 模式标签页 | `.gun-workbench .gw-modes-tabs .gw-mode` | B | CSS 透明页签 + 下划线；未接 `tab-*` |
| 枪匠 / Variant 搜索 | `#gs-search` | **C** | 原生 search 外观 |
| FORGE 约束搜索 | `.gun-workbench .gw-forge-search` ×2 | **C** | 原生 search 外观 |
| 候选搜索 | `#gw-cand-search`（`.lw-search`） | A | `input.png` |
| 配装分类 | `.loadout-workbench .lw-cat` | B | CSS 文字按钮 |
| 排序按钮 | `.loadout-workbench .lw-sortbtn` | B | CSS 1px 边小按钮 |
| 配装数字输入 | `.loadout-workbench .lw-num` / `.lw-fl input` | A | `input.png` |
| 配枪等级输入 | `.gun-workbench .gw-lvlnum` | A | `input.png` |
| 配枪下拉 | `.gun-workbench .gw-lvsel select` / `.gw-ref select` | A | `select.png` + 箭头 |
| 表格 / 单元格 | `.lw-table` / `.tbl-head` / `.tbl-row` / `.lw-cell` | **A** | R91 接入表头 / 行底 / 交替行 / 横纵网格（见 §12） |
| 表格滚动条 | `.tbl-scroll` / `.lw-side` | A | 22px 纵向素材（覆盖主题 12px 细条） |
| 进度条框 | `.gun-workbench .gw-bar-track` | A | `progress-frame.png`（仅框） |
| 进度填充 | `.gw-bar-fill` / `.gw-bar-seg` | **A（部分）** | `.blue` 与 `.neutral` 接 `progress-fill(-indeterminate).png`；绿色 `.ok` / 红色 `.red` 保留纯色以保留状态语义 |
| 徽标 / 状态芯片 | `.lw-badge` / `.gw-badge-new` / `.gw-quote-status` | B | CSS 小徽标；本批 badge-md/sm 烘焙 EMPTY，不可用 |
| 个人属性弹窗 | `.gw-prof-box` / `.gw-prof-head` | **A** | 标题栏 `titlebar.png`；R91 底板接 `dialog-box.png` 九宫格 5px |
| 个人属性输入 | `.gw-prof-f input` / `.gw-cand-search` | A | `input.png` |
| 工作台空态 / 加载态 | `.lw-loading` / `.gw-empty` | B | 纯文本，无插图素材 |
| 工作台滚动条 | `.lw-side` / `.am-sim-cfg` | A | 全局纵向素材 |

### 10. 各类弹窗（设置 / 导出 / 详情 / 确认框）

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 通用弹窗底板 | `.lw-modal-box`（app.js 10668 动态创建） | B | CSS 白底 + 1px 边 + 阴影；**缺对话框底板素材** |
| 弹窗标题 / 标题栏 | `.lw-modal-head` / `.lw-modal-title` | A | `titlebar.png` 九宫格 5px，38px 高；与 `.gw-prof-head` / `.am-modal-head` 同一素材 |
| 弹窗按钮 | `.lw-modal-box button` / `.lw-modal-btn` | A | `btn-normal/hover/pressed` |
| 弹窗输入 / 下拉 | `.lw-modal-box input` / `select` | A | `input.png` / `select.png` |
| 确认框（预设管理） | `.lw-preset-box`（app.js 12361） | B | 同 `.lw-modal-box` |
| 弹药详情弹窗 | `.am-modal-box` / `.am-modal-head` | B（标题栏 A） | `.am-modal-head` 用 `titlebar.png`；底板 B |
| 个人属性弹窗 | `.gw-prof-modal` / `.gw-prof-box` | **A** | R91 底板接 `dialog-box.png`（仅浅色 `.gw-prof-box`；深色 `.lw-scope` 内弹窗不接） |
| 校准弹窗 | `.cal-modal` / `.cal-modal-btns` | B | CSS 深色底板；按钮主题自绘（未接 XP 位图） |
| 关闭键 | `.xp-winbtn--close`（gw-prof / am-modal / gs） | B | CSS 重建红色关闭键；橄榄黄三张位图未启用 |
| 遮罩 | `.lw-modal` / `.am-modal` | B | 半透明黑底 |

> 弹窗底板素材在 `assets/xp-ui/` 中不存在（只有 `titlebar.png` 与按钮/输入/分组框）。
> 本批不新造、不缩放糊，保留 CSS 底板并在文末缺件表标注。

### 11. 表单控件（纵向清点）

| 控件 | 覆盖情况 | 档位 |
|---|---|---|
| `input[type=checkbox]` | 全局 24×24 `check-off/on/indeterminate`，117 个 | A |
| `input[type=radio]` | 全局 `radio-off/on`，4 个 | A |
| `input[type=range]` | 全局 `track.png` + `thumb.png` 伪元素，9 个（侧栏 3 + HUD 4 + 弹窗 2） | A |
| `input[type=search]` | 已接 input 素材 8 个；原生 4 个（见 C 档） | A / C |
| `input[type=text]` | 菜单 / 上下文栏 / 工作台均已接 input 素材 | A |
| `input[type=number]` | 已接 input 素材 12 个；原生 8 个（`.am-num` ×6 + `#tk-level-*` ×2） | A / C |
| `select` | 已接 select 素材 13 个；原生 `#tk-edition`；原生 `.am-dist select`；`#tk-special`（B） | A / C / B |
| 文件选择按钮 | 页面内未使用 `input[type=file]` | — |
| 原生 tooltip | 全站 `[title]` 3564 个 | C（行为级） |
| 原生下拉展开列表 | 15 个 select 的 option 列表由 OS 渲染 | C（行为级） |
| 数字微调箭头 | 20 个 number 的上下箭头由浏览器渲染 | C（行为级） |

### 12. 标签页 / 表格 / 列表

| 控件 / 容器 | 出现位置（选择器） | 档位 | 素材或缺口 |
|---|---|---|---|
| 弹药标签页 | `.am-tab` | A | `tab-inactive/active` |
| 任务模式 / 页签 | `.tk-mode` / `.tk-tab` | B | CSS 渐变 |
| 配枪模式页签 | `.gw-mode` | B | CSS 透明页签 |
| 表格表头 / 行 / 网格 | `.tbl-head` / `.tbl-row` / `.tbl-cell` | **A** | R91 接入 `tbl-head/tbl-row/tbl-row-alt/tbl-grid-h/tbl-grid-v`（theme 已是浅色 XP 皮肤，安全替换） |
| 列表行 | `.task-row` / `.tk-story-item` / `.gs-list` 行 | B | CSS 行底 |
| 排序 / 过滤小按钮 | `.lw-sortbtn` / `.tk-story-filter` | B | CSS 1px 边 |

### 13. 滚动条（逐容器）

| 容器 | 选择器 | 档位 | 说明 |
|---|---|---|---|
| 主侧栏 | `.panel` / `.task-list` | A | 22px 纵向素材 + 上下箭头 |
| 任务故事列表 | `.tk-story-list`（全局命中） | A | 同上 |
| 配装侧栏 | `.lw-side` | A | 22px 纵向素材 |
| 配装表格 | `.tbl-scroll` | A | 覆盖主题 12px 细条 |
| 弹药侧栏 / 模拟配置 | `.am-side` / `.am-sim-cfg` | A | 22px 纵向素材 |
| db4 任务滚动区 | `.db4-scroll` / `.db4-rail` / `.db4-strip` | A | 22px 纵向素材 |
| 横向滚动条 | 全局 `::-webkit-scrollbar:horizontal` | **A** | R91 补 `scroll-h-arrow-left/right` 21×21；滑块 hover/pressed 为本批新件，常态沿用上一批 `scroll-h-thumb` |
| 上下文栏窄屏横条 | `#context-bar::-webkit-scrollbar`（≤900） | B | 7px 自绘，未用横向素材 |
| 滚动条箭头 | `scroll-v-arrow-*` + `scroll-v-glyph-*` | **A（5/6）** | 上：normal/hover/pressed；下：normal/pressed；**`scroll-v-arrow-down-hover` 源图漏画**，沿用上一批空白底板（三角 glyph 覆盖，视觉无差） |
| 滚动条滑块 hover/pressed | `scroll-v-thumb-hover/pressed` | A | 纵向齐全 |

### 14. 徽标 / 进度条 / 空态 / 加载态

| 控件 | 选择器 | 档位 | 素材或缺口 |
|---|---|---|---|
| 价格来源徽标 | `#price-source-badge` | B | CSS 小条；缺徽标素材 |
| 运行版本徽标 | `.build-rev` | B | CSS 边框文本 |
| 表格徽标 | `.lw-badge` / `.gw-badge-new` / `.am-badge` | B | CSS 小徽标；本批 badge-md/sm 烘焙 EMPTY，不可用 |
| 进度条框 | `.gw-bar-track` | A | `progress-frame.png` |
| 进度填充 | `.gw-bar-fill` / `.gw-bar-seg` | **A（部分）** | R91 接 `progress-fill.png`（`.blue`）与 `progress-fill-indeterminate.png`（`.neutral`）；绿/红状态保留纯色 |
| 空态 | `.task-empty` / `.tbl-empty` / `.gw-empty` | **A（部分）** | R91 任务面板空态接 `empty-box.png` 48×48；`.tbl-empty` 为深色表内行，未加图 |
| 加载态 | `.lw-loading` / `.am-loading` | B | 纯文本，无插图 / 无 spinner 素材 |
| 徽标素材 | `badge-md.png` / `badge-sm.png`（本批） | 不可用 | 素材烘焙了「EMPTY」文字，不做位图替换；徽标继续用 CSS |

## 三、统计与阶段结论

### 3.1 元素级计数（改动前基线快照，共 718 个 button/input/select/textarea）

> **历史对照（口径不同，不可与第六节直接比较）**：本表只统计表单控件，不含容器、列表行、
> 卡片、浮层、表头、分组框、滚动区。当前口径与数字见第六节。

| 档位 | 数量 | 占比 | 构成 |
|---|---:|---:|---|
| **A** | **232** | 32.3% | button 69、checkbox 117、range 9、select 13、search 8、radio 4、number 12 |
| **B** | **473** | 65.9% | button 472、select 1（`#tk-special`） |
| **C** | **13** | 1.8% | search 4、number 8、select 1 |
| **D** | **0** | 0% | 元素级无完全裸奔项 |
| 合计 | 718 | 100% | — |

### 3.2 C 档明细（13 个）

| # | 控件 | 选择器 | 类型 | 原生外观 |
|---|---|---|---|---|
| 1 | 枪匠任务搜索 | `#gs-search` | search | 原生搜索框内阴影 / 取消按钮 |
| 2–3 | FORGE 约束搜索 | `.gun-workbench .gw-forge-search` ×2 | search | 同上 |
| 4 | 任务故事搜索 | `#tk-story-search` | search | 同上 |
| 5 | 任务版本 | `#tk-edition` | select | 原生下拉箭头 |
| 6–7 | 任务等级区间 | `#tk-level-min` / `#tk-level-max` | number | 原生微调箭头 |
| 8–13 | 弹药距离区间 | `.am-workbench .am-num` ×6 | number | 原生微调箭头 |
| 补充 | 弹药距离下拉 | `.am-workbench .am-dist select` | select | 原生下拉箭头（未在 13 个元素统计内，按 B 计但实际外观为 C） |

> 说明：`.am-dist select` 在快照中按“有自定义 CSS 但无素材”计入 B；从**视觉效果**看仍是原生
> 下拉箭头，属于 C 类问题，需要一并修复。因此实际需要处理的 C 类表单控件是 **14 个**。

### 3.3 C 档行为项（非元素，无法计数进 718）

| 行为 | 数量 | 说明 | 临时方案 |
|---|---:|---|---|
| 原生 select 展开列表 | 15 个 select | option 列表由 OS 绘制，CSS 无法换皮 | 不改 DOM 前提下无法替换；只能保证收起态是 XP 素材 |
| 原生 number 微调箭头 | 20 个 number | `::-webkit-inner-spin-button` 由浏览器绘制 | 隐藏箭头（`appearance:textfield` + 隐藏 spin-button），或后续做自定义步进按钮（需 DOM 改动，暂缓） |
| 原生 `title` tooltip | 3564 个 | 悬停提示由系统绘制 | 保留；项目内已有 `.lw-tip/.gw-tip/.am-graph-tip` 自定义浮层可逐步替代高频项 |
| 浏览器右键菜单 | 全站 | 地图/非自定义区域 | 任务卡已有 `.task-context-menu`；其余区域暂不接管 |

### 3.4 D 档明细

**0 个元素**。所有被检查的容器都至少有一条项目级规则；空态 / 加载态虽然只是纯文本，
但字体与颜色由主题变量控制，不算 D。例外风险：`ui-showcase.html` 是组件展示页，不属于主界面，
不在本次覆盖范围。

### 3.5 结论（先发这一版，不等改完）

- 总控件 **718**：**A 232（32.3%）/ B 473（65.9%）/ C 13（1.8%）/ D 0**。
- 用户反馈成立：**三分之二控件仍是纯 CSS 自绘（B）**，另有 13 个表单控件仍是原生外观（C）。
- 最高频的 B 档不是“没人管”，而是“主题用 CSS 画了 XP 外观、但没有接 `assets/xp-ui` 位图”：
  菜单栏、工具条常态按钮、上下文栏、状态栏、任务行/页签、工作台表格、弹窗底板、徽标、空态。
- C 档集中在**搜索框 4 个、数字输入 8 个、版本下拉 1 个**（另有 `.am-dist select` 需一并处理）。
- 素材库确有缺件：菜单/右键菜单底板、对话框底板、tooltip/toast 底板、表头/网格、状态栏底板、
  进度填充、徽标、空态插图、disabled 复选框/单选/下拉、横向滚动箭头、横向滑块 hover/pressed、
  数字微调箭头。缺件不硬凑、不缩放糊，按下表给临时方案。

## 四、分批替换计划（按可见度）

### 第一批（最高频，先做）

1. **菜单栏按钮**：`.app-account-btn`、`.gm-btn`、`.app-menu-btn` → `btn-normal/hover/pressed/focus`。
2. **工具条按钮常态**：`.view-btn` 常态补 `btn-normal.png`（悬停/选中已有位图）。
3. **任务页签 / 楼层 / 排序 / 配枪模式页签**：`.tk-mode`、`.tk-tab`、`.task-floor`、
   `.lw-sortbtn`、`.gw-mode` → 小号 `btn-*` 位图（24px 高，5px 切片）。
4. **输入 / 下拉补齐**：`#gs-search`、`.gw-forge-search`、`#tk-story-search`、`#tk-edition`、
   `#tk-level-min/max`、`.am-num`、`.am-dist select` → `input.png` / `select.png` 素材组。
5. **数字微调箭头**：上述 number 控件隐藏原生 spin-button（素材库无箭头件）。
6. **右键菜单 / 弹窗底板**：缺件，保留 CSS 底板并在此文档标注；不新造素材。

### 第二批（次要）

- 表格表头 / 网格、徽标、进度填充、空态 / 加载态、状态栏底板、菜单栏 / 上下文栏底板：
  首轮缺件，先统一 CSS 外观与字体，不引入缩放位图；**R91 缺件板已补齐，见 §5.5–§5.7**
  （徽标件仍不可用、横向滑块常态仍缺，如实保留）。
- 横向滚动条窄屏 7px 条：保留自绘（22px 素材放不进 36px 上下文栏），标注例外。
- 纵向滚动条已全覆盖（A），无需再改。

### 约束检查清单（第一批）

- [x] 只改 CSS，不动 DOM 结构、交互逻辑、数据流。
- [x] 所有新规则只作用于主界面容器；`?mini=1` 下这些容器隐藏，零影响（实测可见控件数 0）。
- [x] 沿用 `assets/xp-ui/` + `xp-ui-app.css` 的 `border-image` 5px 九宫格约定，不新造素材。
- [x] 间距仍走 `docs/ui-component-spec.md` 的 8 档；字号不降到 10px 以下；对比度不低于阈值。
- [x] 缺件如实标注，不用低质量缩放糊。

## 五、第一批落地记录（R90，已实测）

### 5.1 B / C → A 的控件

| 控件 | 选择器 | 新映射 | 实测 |
|---|---|---|---|
| 账号版本入口 | `.app-account-btn` | `btn-normal.png`，30px | `border-image` 命中 |
| 顶层菜单按钮 | `.app-menu-btn` | `btn-normal/hover/pressed/focus`，30px | 命中；`.open` 为 pressed |
| 模式三选一 | `.app-menubar .game-mode-bar .gm-btn` | `btn-normal`，28px；`.is-on` 为 pressed | 命中 |
| 工具条视图按钮 | `.view-toolbar .view-btn` | 常态补 `btn-normal`，30px | 5 个全部命中 |
| 地图侧栏楼层按钮 | `.floor-item`（地图侧栏） | 补 `btn-normal`；hover/pressed，24px | 6 个命中（原被 `.floor-item` 的 CSS 渐变压住） |
| 配枪工作台按钮 | `.gun-workbench button.gw-btn:not(.gw-hit):not(.gw-card)` | `btn-normal/hover/pressed/disabled/focus`，30px | 12 个命中（原被主题 `gun-workbench button` 规则压住） |
| 通用弹窗标题栏 | `.lw-modal-box .lw-modal-head` | `titlebar.png`，38px；标题文字 `#2c2c22` | 命中（用临时节点实测后移除） |
| 任务模式 / 页签 | `.tk-mode` / `.tk-tab` | `btn-normal`；选中 `btn-pressed`，24px | 命中（`.tk-mode` 受主题 min-height 影响实高 28px） |
| 楼层小按钮 | `.task-floor` | `btn-normal`，24px，字号保持 10px | 58 个命中 |
| 配装排序按钮 | `.lw-sortbtn` | `btn-normal`；`.is-on` 为 pressed，24px | 用 `:not()` 链压过主题按钮规则，5 个命中 |
| 配枪模式页签 | `.gun-workbench .gw-modes-tabs .gw-mode` | `btn-normal`；`[data-on=1]` 为 pressed，24px | 4 个命中 |
| 枪匠搜索 | `#gs-search` | `input.png`，28px，`appearance:none` | 命中 |
| FORGE 约束搜索 | `.gun-workbench .gw-forge-search` ×2 | `input.png`，28px | 命中（面板展开时可见） |
| 任务故事搜索 | `#tk-story-search` | `input.png`，28px | 命中 |
| 任务版本下拉 | `#tk-edition` | `select.png` + `select-arrow.png`，33px | 命中（实测 92×33） |
| 任务等级区间 | `#tk-level-min/max` | `input.png`，24px | 命中 |
| 弹药距离区间 | `.am-workbench .am-num` ×6 | `input.png`，24px | 命中（实测 66×24，行高 24） |
| 弹药图表距离下拉 | `.am-workbench .am-dist select` | `select.png` + 箭头，33px | 命中（实测 93×33） |
| 数字微调箭头 | 主界面全部 `input[type=number]` | 隐藏 `::-webkit-inner/outer-spin-button` + `appearance:textfield` | 已覆盖 20 个数字输入 |
| 搜索取消按钮 | 主界面全部 `input[type=search]` | 隐藏 `::-webkit-search-cancel-button` | 已覆盖 12 个搜索框 |

### 5.2 计数变化（元素级，总数仍为 718）

| 档位 | 改动前 | 第一批后 | 第二批后 | 说明 |
|---|---:|---:|---:|---|
| **A** | 232 | 346 | **346** | 第二批覆盖的是**容器**（面板 / 底板 / 表格 / 滚动条），不新增 `button/input/select/textarea` 命中，元素级口径不变 |
| **B** | 473 | 372 | **372** | 同上 |
| **C** | 13 | 0 | **0** | 行为项（原生展开列表 / tooltip / 浏览器菜单）单列在 §5.3 |
| **D** | 0 | 0 | **0** | — |
| 合计 | 718 | 718 | **718** | 718 个表单控件口径；**历史口径，当前统计见第六节** |

> 计分口径说明：本表只统计 718 个 `button/input/select/textarea`。第二批落地的
> `#app-statusbar`、`.sb-cell`、`.app-menu-panel`、`.menu-panel`、`.task-context-menu`、
> `.gw-prof-box`、`.tbl-head`、`.tbl-row`、`.tbl-cell` 都是容器 / 表格行，不在 718 的分子里，
> 所以 A/B/C/D 数字保持不变；它们的档位变化已逐行更新在 §二 的对应区域表中。

### 5.3 仍属于 C 的行为项（保留并标注）

| 行为 | 数量 | 现状 | 说明 |
|---|---:|---|---|
| select 展开列表 | 15 | 原生 OS 列表 | 不改 DOM / 不引入 JS 自定义列表时无法换皮 |
| 原生 `title` tooltip | 3564 | 原生 | 项目内 `.lw-tip/.gw-tip/.am-graph-tip` 可逐项替代高频提示 |
| 浏览器右键菜单 | 全站 | 原生 | 任务卡已有 `.task-context-menu`；其余区域暂不接管 |
| 数字微调箭头 | 20 | **已隐藏** | 素材库无箭头件，如实隐藏原生件，不做缩放糊 |
| 搜索取消按钮 | 12 | **已隐藏** | 同上 |

### 5.4 验证记录

- 主页面实测命中：`.view-btn`、`.app-menu-btn`、`.app-account-btn`、`.gm-btn`、`.tk-tab`、`.tk-mode`、
  `.task-floor`、`.floor-item`、`.lw-sortbtn`、`.gw-mode`、`.gw-btn`、`#gs-search`、`#tk-story-search`、
  `#tk-edition`、`#tk-level-min`、`.am-num`、`.am-dist select` 的 `border-image-source` 均指向
  `assets/xp-ui/*.png`。
- 打开全部视图后重新计数：total **718**，**A 346 / B 372 / C 0 / D 0**。
- 菜单栏 `scrollWidth === clientWidth === 1835`，按钮抬高到 30/28px 后无横向溢出。
- 弹药页：`.am-num` 66×24、`.am-dist select` 93×33；距离区间三行行高均为 24px。
- 任务页：`#tk-edition` 92×33 可见；`.tk-tab` 58×24；`.tk-mode` 52×28（主题 min-height）。
- 配枪页：`.gw-mode` 选中态 `btn-pressed`、未选中态 `btn-normal`；FORGE 搜索框在面板展开时按 28px 渲染。
- `?mini=1`（page 3）：`#menubar`、`#app-menubar`、`#context-bar`、`#app-statusbar` 全部 `display:none`，
  可见 `button/input/select/textarea` 数 = **0**，第一批零影响。

### 5.5 第二批落地记录（R91，缺件板 `20261106补充.jpg`）

**源图实测**：4096×4096 JPEG（非提示词要求的 3840×2160 PNG），坐标表作废，改用键色分割 + 连通域自动 bbox。

**键色实测（四边 20px 条带，非假设值）**：

| 边 | mean RGB | σ |
|---|---|---|
| top | (244.30, 6.24, 246.78) | (1.82, 1.56, 2.39) |
| bottom | (241.54, 7.82, 244.45) | (2.19, 3.54, 3.92) |
| left | (242.86, 7.11, 246.95) | (2.30, 2.03, 2.44) |
| right | (241.15, 4.91, 247.50) | (2.07, 1.33, 1.54) |
| **合并** | **(242.46, 6.52, 246.42) = `#F207F6`** | **(2.44, 2.53, 2.96)** |

> 与旧板逻辑值 `#F51CF7 (245,28,247)` 不同：G 通道实测约 6.5 而非 28，若沿用旧键色容差会把
> 全部键色判成「非键色」。抠图容差取 **45**（切比雪夫逐通道，≈ 17σ），并叠加
> `MedianFilter(3)` 去 JPEG 8×8 块噪 + alpha `MinFilter(5)`（erode=2）收边；
> 1px 倒角靠 erode=2 而不是更大核，未被抹平。

**产出**：清单 44 件 → 出图 **42 件**（2 件源图未绘制）→ 其中 **40 件可用**（2 件徽标烘焙文字不可用）。

### 5.6 逐件实测判定

键色列：`实测值` 为全板共用 `#F207F6`；括号内为该件内部距键色 ≤12 的像素数（紫边风险指标）。

| # | 件名 | 键色实测（≤12 内部像素） | 裁切尺寸（源 px） | 输出尺寸 | 预期 1x | 偏差 | 可用 | 落地 |
|---:|---|---|---|---|---|---|---|---|
| 1 | statusbar-bg | `#F207F6`（2） | 1261×200 | 630×100 | 800×24 | −21.2% / +316.7% | 是 | `#app-statusbar` 九宫格 2px |
| 2 | dialog-box | `#F207F6`（3278） | 1261×938 | 630×469 | 720×480 | −12.5% / −2.3% | 是 | `.gw-prof-box` 九宫格 5px |
| 3 | dialog-head | `#F207F6`（1） | 1261×147 | 630×74 | 720×38 | −12.5% / +94.7% | 是 | 由 `titlebar.png` 承担，本件备用 |
| 4 | tbl-head | `#F207F6`（2） | 1261×374 | 630×187 | 600×32 | +5% / +484% | 是 | `.tbl-scroll .tbl-head` `100% 100%`（横向填满、纵向 187→32 压缩；原图本身是大面积色块，无细线信息损失） |
| 5 | tbl-row | `#F207F6`（0） | 102×180 | 600×24 | 600×24 | 0 / 0 | 是 | `.tbl-row` 整行底图 |
| 6 | tbl-row-alt | `#F207F6`（0） | 102×60 | 600×24 | 600×24 | 0 / 0 | 是 | `.tbl-row:nth-child(even)` |
| 7 | tbl-grid-h | `#F207F6`（0） | 102×6 | 600×1 | 600×1 | 0 / 0 | 是 | `.tbl-row` 上边框 `border-image` |
| 8 | menu-panel-bg | `#F207F6`（1867） | 869×656 | 434×328 | 330×210 | +31.5% / +56.2% | 是 | `.menu-panel` 九宫格 7px |
| 9 | menu-panel-sep | `#F207F6`（0） | 868×6 | 330×1 | 330×1 | 0 / 0 | 是 | **未接入**：DOM 无独立分隔元素 |
| 10 | app-menu-panel-bg | `#F207F6`（1936） | 691×525 | 346×262 | 210×140 | +64.8% / +87.1% | 是 | `.app-menu-panel` 九宫格 7px |
| 11 | context-menu-bg | `#F207F6`（1471） | 473×353 | 236×176 | 146×96 | +61.6% / +83.3% | 是 | `.task-context-menu` 九宫格 6px |
| 12 | context-menu-sep | `#F207F6`（0） | 474×6 | 146×1 | 146×1 | 0 / 0 | 是 | **未接入**：同上 |
| 13 | tbl-grid-v | `#F207F6`（0） | 4×220 | 1×24 | 1×24 | 0 / 0 | 是 | `.tbl-cell` 右边框（色 (157,149,134)） |
| 14 | scroll-v-track | `#F207F6`（6） | 110×986 | 22×171 | 22×171 | 0 / 0 | 是 | `::-webkit-scrollbar-track` 九宫格 |
| 15 | scroll-v-thumb | `#F207F6`（423） | 133×319 | 23×51 | 23×51 | 0 / 0 | 是 | 滑块常态 |
| 16 | scroll-v-thumb-hover | `#F207F6`（517） | 133×322 | 23×51 | 23×51 | 0 / 0 | 是 | `:hover` |
| 17 | scroll-v-thumb-pressed | `#F207F6`（499） | 133×321 | 23×51 | 23×51 | 0 / 0 | 是 | `:active` |
| 18 | scroll-v-arrow-up | `#F207F6`（240） | 160×157 | 22×27 | 22×27 | 0 / 0 | 是 | 上箭头常态 |
| 19 | scroll-v-arrow-up-hover | `#F207F6`（263） | 160×156 | 22×27 | 22×27 | 0 / 0 | 是 | `:hover` |
| 20 | scroll-v-arrow-up-pressed | `#F207F6`（194） | 160×149 | 22×27 | 22×27 | 0 / 0 | 是 | `:active` |
| 21 | scroll-v-arrow-down | `#F207F6`（184） | 160×150 | 22×27 | 22×27 | 0 / 0 | 是 | 下箭头常态 |
| 22 | scroll-v-arrow-down-hover | — | **无** | — | 22×27 | — | **否** | 源图未绘制（只有标签没有图形）；沿用旧空白底板 + 三角 glyph |
| 23 | scroll-v-arrow-down-pressed | `#F207F6`（193） | 160×154 | 22×27 | 22×27 | 0 / 0 | 是 | `:active` |
| 24 | statusbar-cell | `#F207F6`（4） | 556×157 | 120×18 | 120×18 | 0 / 0 | 是 | `.sb-cell` 九宫格 1px/2px |
| 25 | statusbar-sep | `#F207F6`（0） | 27×157 | 2×18 | 2×18 | 0 / 0 | 是 | **未接入**：DOM 无分隔元素 |
| 26 | scroll-h-track | `#F207F6`（3） | 556×148 | 71×21 | 71×21 | 0 / 0 | 是 | 横滚轨道（与旧 `scroll-h-track.png` 同尺寸替换） |
| 27 | scroll-h-thumb | — | **无** | — | 44×21 | — | **否** | 源图只画了 hover/pressed，缺常态；沿用旧 `scroll-h-thumb.png`（同尺寸同色系，非缩放） |
| 28 | scroll-h-thumb-hover | `#F207F6`（868） | 515×149 | 44×21 | 44×21 | 0 / 0 | 是 | `:hover` |
| 29 | scroll-h-thumb-pressed | `#F207F6`（806） | 515×148 | 44×21 | 44×21 | 0 / 0 | 是 | `:active` |
| 30 | scroll-h-arrow-left | `#F207F6`（228） | 159×157 | 21×21 | 21×21 | 0 / 0 | 是 | `:decrement`（蓝色三角） |
| 31 | scroll-h-arrow-right | `#F207F6`（214） | 160×155 | 21×21 | 21×21 | 0 / 0 | 是 | `:increment` |
| 32 | select-disabled | `#F207F6`（2） | 698×187 | 349×94 | 204×33 | +71.1% / +184.8% | 是 | `:disabled` 下拉，九宫格 `10 52 10 10`（右 24px 避开烘焙箭头） |
| 33 | progress-fill | `#F207F6`（0） | 421×104（已剔右端 3px 轨道框） | 197×17 | 200×17 | −3px / 0 | 是 | `.gw-bar-fill.blue`，100% 宽拉伸 |
| 34 | progress-fill-100 | `#F207F6`（1） | 698×120 | 200×17 | 200×17 | 0 / 0 | 是 | 备用（满格端帽） |
| 35 | progress-fill-indeterminate | `#F207F6`（3） | 698×118 | 200×17 | 200×17 | 0 / 0 | 是 | `.gw-bar-seg.neutral` |
| 36 | range-track | `#F207F6`（0） | 260×118 | 208×15 | 208×15 | 0 / 0 | 是 | `range-track.png`（避开中段烘焙拇指） |
| 37 | range-thumb | `#F207F6`（575） | 132×190 | 19×33 | 19×33 | 0 / 0 | 是 | 拇指常态 |
| 38 | range-thumb-hover | `#F207F6`（580） | 132×188 | 19×33 | 19×33 | 0 / 0 | 是 | `:hover` |
| 39 | range-thumb-pressed | `#F207F6`（438） | 132×188 | 19×33 | 19×33 | 0 / 0 | 是 | `:active` |
| 40 | empty-box | `#F207F6`（9555） | 380×420 | 48×48 | 48×48 | 0 / 0 | 是 | `.task-empty::before` 48×48 |
| 41 | badge-md | `#F207F6`（1340） | 284×166 | 28×19 | 28×19 | 0 / 0 | **否** | 图内烘焙「EMPTY」文字，不能当空白徽标底；徽标保持 CSS |
| 42 | badge-sm | `#F207F6`（686） | 176×99 | 20×14 | 20×14 | 0 / 0 | **否** | 同上 |
| 43 | check-disabled | `#F207F6`（63） | 134×135 | 24×24 | 24×24 | 0 / 0 | 是（受限） | 已画入勾号，只用于 `:disabled:checked` |
| 44 | radio-disabled | `#F207F6`（60） | 134×133 | 24×24 | 24×24 | 0 / 0 | 是 | 只有圆环 = `:disabled:not(:checked)` |

> 「偏差」=（输出宽度/预期宽度 − 1）与（输出高度/预期高度 − 1）。面板类件（#1–#4、#8、#10、#11、#32）
> 尺寸普遍严重偏离预期，但均按九宫格 `stretch` 使用，只取四角与四条边，中间填充由 `border-image` 拉伸，
> **没有整图缩放**。图标类件（#14 之后）全部按预期 1x 等比降到目标尺寸，偏差 0。
>
> 未接入的 4 件中：`menu-panel-sep` / `context-menu-sep` / `statusbar-sep` 是**源图有、但 DOM 里没有
> 对应的独立分隔元素**（不改 DOM 的约束下无法落位）；`scroll-v-arrow-down-hover` 是**源图漏画**。

### 5.7 第二批验证记录（R91）

- `python -m pytest tests -q` → **1767 passed, 1 skipped**。
- CSS 静态校验：括号平衡；全部 `url()` 指向的素材文件均存在（statusbar / menu / context-menu /
  dialog-box / progress / empty-box / check-disabled / radio-disabled / select-disabled / range / scroll-h）。
- 主页面逐视图（ammo → gun → tasks → map → loadout）计数：`total 718 / A 346 / B 372 / C 0 / D 0`
  （A 48.19%，B 51.81%），与第一批后一致（容器级改动不进元素级分子）。
- 容器实测命中 `background-image / border-image-source`：`#app-statusbar`、`.sb-cell`、`.app-menu-panel`、
  `.menu-panel`、`.task-context-menu`、`.gw-prof-box`、`.tbl-head`、`.tbl-row`（含 `:nth-child(even)`）、
  `.tbl-cell`。
- 表格皮肤核对：`theme-windows-xp.css` 在 `xp-ui-app.css` 之前加载，工作台表格本就是**浅色 XP 皮肤**
  （`.tbl-head` 渐变 (253,253,253)→(236,233,216)、行底白/`#f7f5ee`、黑字），故浅色表头/行素材可直接接入；
  `:hover` / `[aria-selected]` 的蓝色选中态由主题规则保留，未被覆盖。
- `?mini=1`（page 3）：`#app-statusbar` 为 `display:none`，可见 `button/input/select/textarea` = **0**，
  横向滚动箭头规则额外用 `html:not(.tk-mini-root) body:not(.tk-mini)` 限定 → **零影响**。
- 深色弹窗（`.am-modal-box`、`.lw-scope` 内 `.lw-modal-box` / `.lw-preset-box`）**未接**浅色底板，
  避免把深色皮肤刷成米色。
  > **R92 更正**：该判断有误。`theme-windows-xp.css` 已把 `.lw-modal-box` / `.am-modal-box` /
  > `.lw-preset-box` / `.cal-modal` 统一改成浅色（`--xp-face-2 #f7f5ee`、边框 `#0a3f9e`），
  > 文章节 15.8 已接 `dialog-box.png` 浅色底板，实测边框完整无裁切。

---

## 六、R92：可见元素级复盘（当前口径）

> 旧 718 口径只统计 `button / input / select / textarea`，把容器、列表行、卡片、浮层、
> 提示条、表头、分组框、滚动区全部排除，导致「数字到顶、观感仍然大片 CSS」。
> 本节改用**可见元素级**：凡是 `rect ≥ 4px`、可见、且有任意装饰（背景图 / border-image /
> 非透明背景 / 可见边框 / box-shadow）或可滚动的元素都计入，容器也算。

### 6.1 计数口径

| 档 | 判定 |
|---|---|
| **A** | 自身 `background-image` 或 `border-image-source` 命中 `/assets/xp-ui/`；range 的伪元素命中同一路径 |
| **B** | 有装饰但未引用任何 XP 位图（CSS 自绘） |
| **C** | `select/input/textarea` 且 `appearance` 不为 `none` |
| **D** | 可见但完全无装饰（透明文本层 / 纯布局容器） |

> 已知测量盲区：Chrome 的 `getComputedStyle(el, "::-webkit-slider-thumb")` 返回 `none`，
> 因此 range 一律被脚本记为 B。地图 `#label-scale / #label-alpha / #icon-scale` 三条已用截图
> 确认渲染为 XP 凹槽轨道 + 米色滑块（见 6.4），实际应计 A。
> 紧凑型 `input#am-traderlvl`（245×16）/ `input#gw-traderlv`（62×16）已在 R93 接入
> `range-track-compact.png` + `range-thumb-compact.png`（见 §八），但受同一伪元素盲区影响
> 脚本仍记为 B，实际应计 A。

### 6.2 分视图「替换前 / 替换后」

| 视图 | 替换前 A/B/C = 总数 | 替换后 A/B/C = 总数 | A 增量 | 替换后 A 占比 |
|---|---:|---:|---:|---:|
| 地图 map | 144 / 271 / 0 = 415 | **372 / 68 / 0 = 440** | +228 | 84.5% |
| 任务 tasks | 31 / 121 / 0 = 152 | **97 / 55 / 0 = 152** | +66 | 63.8% |
| 弹药 ammo | 2484 / 24 / 0 = 2508 | **2507 / 1 / 0 = 2508** | +23 | 99.9% |
| 枪匠 gun | 29 / 558 / 0 = 587 | **223 / 364 / 0 = 587** | +194 | 38.0% |
| 配装 loadout | 489 / 120 / 0 = 609 | **556 / 56 / 0 = 612** | +67 | 90.9% |
| **合计** | **3177 / 1094 / 0 = 4271** | **3755 / 544 / 0 = 4299** | **+588** | **87.3%** |

> 说明：
> 1. 地图总数 415→440 是**渲染差异**：两次盘点时右侧任务列表渲染的卡片数不同（替换前少 25 个），
>    不是新增元素。
> 2. 配装总数 609→612 也是**渲染差异**：第二轮盘点时聚焦条多渲染出 `.lw-focus-tag` 与
>    `.lw-focus-x` 各 1 个（共 +2），另 1 个为列表随数据渲染多出的行，均非新增元素；
>    对应 B 也由 55 变为 56。
> 3. 按 6.1 的 range 修正，地图实际为 **A 375 / B 65**（A 85.2%）。
> 4. 枪匠剩余 364 中，**326 个是不可换的内容件**：`b.gw-card-badge` 163（徽标素材烘焙文字）+
>    `img.gw-card-img` 163（真实枪械照片）。可换的只剩 38 个。

### 6.3 逐视图剩余项（按选择器聚合，均为实测）

**地图（B 68）**

| 选择器 | 形状 | 数量 | 尺寸 | 原因 |
|---|---|---:|---|---|
| `button.task-main` | 按钮 | 54 | 239×37 | 透明文字层，素材在外层 `button.task-floor`（已 A） |
| `label.hud-scale` | 容器 | 3 | 243×46 | 滑条行布局，无独立底板 |
| `span.dot.dot-*` | 图标 | 7 | 9×9 | 图例语义色点 |
| `input#label-scale/#label-alpha/#icon-scale` | 轨道/滑块 | 3 | 135×33 | 脚本伪元素盲区，实际已 A |
| `main#stage` | 面板 | 1 | 1205×1023 | 地图画布，刻意保持深色 |

**任务（B 55）**

| 选择器 | 形状 | 数量 | 尺寸 | 原因 |
|---|---|---:|---|---|
| `span.tk-story-dot` | 图标 | 38 | 24×24 | 完成度语义圆点 |
| `span.tk-story-chip` | 图标 | 17 | 32×17 | 语义色签 |

**弹药（B 1）**

| 选择器 | 形状 | 数量 | 尺寸 | 原因 |
|---|---|---:|---|---|
| `input#am-traderlvl` | 轨道/滑块 | 1 | 245×16 | 紧凑型 range：16px 高度与 33px 拇指冲突，待单独处理 |

**枪匠（B 364）**

| 选择器 | 形状 | 数量 | 尺寸 | 原因 |
|---|---|---:|---|---|
| `b.gw-card-badge` | 图标 | 163 | 17×17 | 缺空白徽标底（M3） |
| `img.gw-card-img` | 图片 | 163 | 64×42 | 真实物品图，不可换 |
| `div.gw-calblock` | 色块 | 30 | 40×95 | 口径分类语义色 |
| `section#gun-view` | 面板 | 1 | 1835×1023 | 视图外框，内部工作台已 A |
| `i.gw-badge-new` | 图标 | 1 | 26×11 | 缺小徽标（M4） |
| `input#gw-traderlv` | 轨道/滑块 | 1 | 62×16 | 紧凑型 range，同 ammo |
| `i.gw-callegend-dot` | 图标 | 5 | 9×9 | 口径图例色点 |

**配装（B 56）**

| 选择器 | 形状 | 数量 | 尺寸 | 原因 |
|---|---|---:|---|---|
| `span.lw-mat-chip.mat-*` | 色签 | 39 | 13 高 | 材质语义色（combined 18 / aramid 8 / armoredsteel 7 / uhmwpe 5 / titan 1；见缺件清单第三节） |
| `span.lw-cell-label` | 文本 | 9 | 28×14 / 48×14 | 槽位标签文字 |
| `span.lw-cell-name` | 文本 | 2 | 75×22 | 槽位名称 |
| `section#loadout-view` | 面板 | 1 | 1835×1023 | 视图外框 |
| `span.lw-cats-note` | 文本 | 1 | 163×15 | 分类说明文字 |
| `span.lw-cl-badge` / `span.lw-at-badge` | 徽标 | 2 | 13×16 / 13×13 | 缺空白徽标（M4） |
| `div.lw-deco` | 装饰 | 2 | 78×92 | 纯装饰块，无素材 |

### 6.4 本轮实际替换（R92，全部为 CSS 改，无 DOM / 类名 / 数据流改动）

| 批次 | 区域 | 换成什么 |
|---|---|---|
| 15.1 | 菜单栏 / 上下文栏 | `titlebar.png` 9-slice（2px 边） |
| 15.2 | 侧栏、任务树、配装/枪匠侧栏、表格滚区等 18 个容器 | `groupbox.png` 3px 凹槽 |
| 15.3 | 三个工作台外壳 | `menu-panel-bg.png` |
| 15.4 | 11 条面板头 / 工具条 / 页签行 | `titlebar.png` |
| 15.5 | 底部状态条 | `statusbar-bg.png` |
| 15.6 | 任务行、枪械卡、配装槽位、剧情节点、浏览行 | `tbl-row` / `groupbox` / `btn-hover` / `btn-pressed` |
| 15.7 | 芯片、分段、页签 | `btn-normal/hover/pressed` |
| 15.8 | 四类弹窗底板 + 配装预设行 | `dialog-box.png`（**重新判定为浅色并接入**） |
| 15.9 | 三处空态 | `empty-box.png` 48×48 |
| 15.10 | 上下文栏芯片、图例行、模式条、表格竖网格 | `btn-*` / `tbl-row` / `menu-panel-bg` / `tbl-grid-v` |
| 15.11 | 枪匠芯片/价格胶囊、表格滚区、`#gw-current` | `btn-*` / `groupbox` / `plaque-3`（修 theme 简写重置） |
| 16.1 | 任务行开关（54 组） | `range-track` + `progress-fill` + `range-thumb`（近似件 M5） |
| 16.2 | 顶部品牌牌 | `plaque-3.png` |
| 16.3 | 版本徽标 / 任务构建号 | `statusbar-cell.png` |
| 17.1 | 配装区块 `section.lw-block` | `groupbox.png`（修 theme 简写重置） |
| 17.2 | 费用清单外壳 / 行 | `groupbox.png` / `tbl-row.png` |
| 17.2a | 配装费用行（第二轮复查） | 去掉 `.lw-cost-list` 第二层框，只留行底 `tbl-row`，消除双框接缝 |
| 17.3 | `#lw-preset`、`.lw-ci-x`、`.lw-focus-tag`、`.lw-focus-x` | `btn-normal/hover/pressed`（`.lw-focus-x` 为第二轮盘点新出现，41×22） |
| 15.11a | 表格滚区外框（第二轮复查） | 边框 `1px → 2px`，`groupbox.png` 四角完整、无毛边 |

### 6.5 旧 718 表（历史对照，**口径不同，不可直接比较**）

| 档位 | 旧口径（718） | 新口径（4299） | 说明 |
|---|---:|---:|---|
| A | 232（32.3%） | 3755（87.3%） | 旧口径不含容器；新口径含所有可见装饰元素 |
| B | 473（65.9%） | 544（12.7%） | 同上 |
| C | 13（1.8%） | 0（0%） | 新口径 `appearance:none` 已覆盖全部表单 |
| D | 0 | 0 | — |

> 旧表的 232/473/13 仍保留在 §3.1，作为 R90 基线的历史快照。

### 6.6 验证

- `python -m pytest tests -q` → **1767 passed, 1 skipped in 98.75s**（第二轮复查改完后 09:56 复跑，exit 0）。
- `?mini=1`（page 3，reload 后等 2.5s）：`ctrlTotal=468`、`ctrlVisible=0`；
  `#app-statusbar` / `#app-menubar` / `#context-bar` / `#sidebar` 均为 `display:none`；
  `html.className = tk-mini-root`、`body.className = tk-mini`，仅 `#map-view` 可见 → **零影响**。
- 弹窗实测：`.gw-prof-box` 720×315，`border-image-source = dialog-box.png`，四角无裁切。
- 视觉副作用复核（第二轮，截图裁切放大 + computed 尺寸）：
  - 品牌牌 `#app-brand` 121×31，`clientWidth = scrollWidth = 112`，文字不压边；
  - 版本徽标 `#build-rev` 135×19，`clientWidth = scrollWidth = 129`，无裁切；
  - 枪匠 `#gw-current` 221×33、`button.gw-chip` 103×23、`button.gw-price-pill` 41×21，均 `clientWidth = scrollWidth`；
  - 任务开关 54 组：蓝色 `progress-fill` 轨道 + 米色 `range-thumb` 滑块，无拉伸/接缝（近似件 M5）；
  - 配装费用行：去掉双层框后单层 `tbl-row` 行底，无接缝；表格滚区 `groupbox` 2px 外框四角完整；
  - 动态新出现的 `button.lw-focus-x`（41×22）已由 17.3 覆盖，`borderImageSource = url(.../xp-ui/...)`。

### 6.7 NEXT ROUND

> 断点：**R93（2026-11-07 11:01 补充板）已落地**，M1–M8 全部结案（M1/M2 不采纳、保留现有方案，
> 理由见 §八）。本轮无新遗留可换项；下一轮需等新增素材或需求变化后再开。
>
> R92 第二轮的计数与验证已归档在 6.2 / 6.6；R93 的计数、体检与接线见 §八。
>
> 仍未解决（全部在缺件清单，**不要重复尝试**）：
> 1. D1–D7：三条分隔线、原生下拉展开列表、数字微调箭头、系统 tooltip、浏览器右键菜单。
> 2. 语义类保留 CSS：图例/剧情/材质色点、口径色块、枪械照片、地图画布、文本标签。
> 3. 枪匠 200 个 B 中 163 个为真实枪械照片（`img.gw-card-img`）+ 30 个口径语义色块，
>    非样式缺口；R93 前占 326 的徽标底 163 已解决。

---

## 七、R92 第二轮变更摘要（本轮收尾）

| 项 | 结果 |
|---|---|
| 五视图合计 | A 3755 / B 544 / 0 = 4299（A 87.3%） |
| 相对替换前 | A +588（3177 → 3755） |
| 本轮修掉 | 费用行双层框、表格外框过薄、`.lw-focus-x` 漏覆盖 |
| 本轮新增替换 | 无（除 `.lw-focus-x` 补覆盖） |
| 新增缺件 | M8（16px 紧凑型 range）——**R93 已解决，见 §八** |
| mini | 可见控件 0，零影响 |
| pytest | 1767 passed / 1 skipped |

---

## 八、R93：`20261107补充.png` 补充板落地（M1–M8，18 件）

> 源图 `ui图标/xp风格ui/20261107补充.png`（2880×2880，4,841,505 B，11:01 写入）。
> 管线 `tools/xp_ui_slice_20261107.py`（可复现）；逐件报告 `docs/xp-ui-20261107-slice-report.json`；
> 拒收件落在 `D:\Temp\3\rejected\`。**未提交 git。**

### 8.1 键色实测（不沿用规格色）

| 项 | 实测 |
|---|---|
| 键色均值 | **RGB(232, 21, 239) = `#E815EF`**（与用户给的 `#F207F6` / `#F51CF7` 均不同） |
| 四边 20px 条带均值互差 | **[1.07, 1.31, 0.63]** /通道（阈值 ±4 → 背景干净） |
| 最大单边 σ | 2.05 |
| 抠图容差 | `tol = 12`；`spill = min(r-g, b-g)`；`trim_weak_edges`（外圈 max alpha < 191 的行/列直接裁掉） |

### 8.2 检测与匹配（不信坐标表）

键色分割 + 连通域：**正好 18 个连通域**，全部按尺寸 / 宽高比 / 相对位置独立匹配成功，
与件名一一对应（左列 5 件、右列 13 件，y 序与提示词顺序一致），**无强行指派**。
坐标表仅作参考：实测 bbox 与表内值有系统性偏移（如 `range-track-compact` 实测 x 254 而非 200），
以实测为准。

### 8.3 逐件体检（离线像素验证）

| 检查项 | 结果 |
|---|---|
| 徽标中间是否空白 | badge-md / -hover / -warn / -sm / -micro 中心区 luma σ 0.5–1.83、暗像素(<120) **0 个** → 未烘焙文字，通过 |
| 底边完整 | 全部 17 件底部 alpha rowmax 248–255，无上批「U 形缺底边」 |
| 开关两态几何 | track off/on alpha IoU **0.9973**；knob off/on/hover IoU **1.0000** → 切换不跳 |
| 三个页签 | 均 120×26、alpha IoU ≈ 1.00、浏览器实测高 25.99px 且 top 全为 114.91；仅 hover 左上圆角比 active/inactive 大 1–2px（高光态差异，不顶穿 26px 工具条） |
| down 箭头 hover | **不通过**：新件把三角烘焙进底板（三角 11×9 / 54px），现有常态是 `scroll-v-glyph-down.png`（15×10 / 67px）叠在空底板上；整件替换会让 hover 三角横向缩 21% 并下移 1px → 不是「只有高光差异」，**保留现状** |
| 洋红残留 | 17 件四边 `min(r-g, b-g)` 最大 ≤ 40 → 紫边 0；8x 图里的粉边是暖灰底 + 深灰背景混色 |

### 8.4 采用与接线

| 缺件 | 素材 | 接线选择器 | 结果 |
|---|---|---|---|
| M1 | `scroll-v-arrow-down-hover.png`（已切） | `::-webkit-scrollbar-button:vertical:end:increment:hover` | **不采纳**，保留「空底板 + `scroll-v-glyph-down`」叠层（原因见 8.3） |
| M2 | `scroll-h-thumb.png`（已切，拒收） | `::-webkit-scrollbar-thumb:horizontal` 常态 | **不采纳**：新件更厚、边框更重（平均像素差 21.8），会与现有 hover/pressed 两态不统一 |
| M3 | `badge-md.png` / `-hover` | `b.gw-card-badge`（163 处）+ `.gw-card:hover` | 已接；一位数 13.71×16.99、两位数 19.43×16.99，`scrollWidth == clientWidth` 不裁字；`badge-md-warn` 无对应语义状态，**未接** |
| M4 | `badge-sm.png` / `badge-micro.png` | `i.gw-badge-new`、`span.lw-cl-badge`、`span.lw-at-badge` | 已接；NEW 28.17×10.99；CL 12.98×15.98；AT 12.98×12.98（13×16 素材 9-slice 压到 13×13），均不裁字，并顺带修掉 `.lw-at-heavy` 白字白底 |
| M5 | `switch-track-off/on` + `switch-knob-off/on/hover` | `span.task-switch-track` / `span.task-switch-knob`（54 组，替掉 range-thumb 近似件） | 已接；track 27.98×13.99、knob 9.98×9.98、dx=15 / dy=0.98。**踩坑**：`style.css` 的 `input:checked + .task-switch-track`（0,3,1）用 `background` 简写把 `background-size` 重置为 `auto`，低优先级规则顶不住 → 改 longhand + `!important` 锁定 |
| M6 | `tip-plate.png` | `.lw-tip` / `.gw-tip` / `.am-graph-tip` / `.marker-pop` | 已接 4px 九宫格；实测 4 类均 `borderImageSource = tip-plate.png`、padding 3px 6px（图表提示 3px 5px），放大截图无接缝、文字不压边 |
| M7 | `tab-active-26/inactive-26/hover-26` | `.am-tab`（26px 高） | 已接；三态同高 25.99px，外框宽 8+9=34px 与旧版对齐，无文字裁切 |
| M8 | `range-track-compact.png` + `range-thumb-compact.png` | `#am-traderlvl` / `#gw-traderlv` | 已接；input 245×16 / 62×16，轨道 16px、拇指 10×16（`margin-top:0`），可拖动值域不变 |

### 8.5 重扫计数（R93 后，口径同 6.1）

| 视图 | A / B / C = 总数 | A 占比 | 变化 |
|---|---:|---:|---|
| 地图 map | 372 / 68 / 0 = 440 | 84.5% | 不变（本板无地图项） |
| 任务 tasks | 97 / 55 / 0 = 152 | 63.8% | 不变（开关原就用 xp 素材，仍计 A） |
| 弹药 ammo | 2507 / 1 / 0 = 2508 | 99.9% | 计数不变（range 属伪元素盲区，实际已 A） |
| 枪匠 gun | **387 / 200 / 0 = 587** | **65.9%**（上轮 38.0%） | A **+164**：徽标底 163 + `badge-new` 1 |
| 配装 loadout | **534 / 54 / 0 = 588** | **90.8%** | A 含新接 2 个徽标；总数比上轮 612 少 24，是本轮盘点时装备槽渲染更少（`.lw-cell` 11 个），B 明细逐项一致（材质签 39 + 槽位文字 11 + 说明 1 + 外框 1 + 装饰 2 = 54），非样式回退 |
| **合计** | **3897 / 378 / 0 = 4275** | **91.2%** | A 增量 +166（其中 164 为枪匠徽标） |

> 枪匠剩余 200 个 B：`img.gw-card-img` 163（真实照片）+ `div.gw-calblock` 30（口径语义色）
> + 口径图例点 5 + 视图外框 1，**全部不可换**。配装剩余 54 个 B 同理（材质色签 / 文本 / 装饰块）。

### 8.6 验证

- 浏览器实测（`innerWidth=1834`、`devicePixelRatio=0.6667`）：
  - `.am-tab` ×5 全部 25.99px 高、top 一致，`scrollWidth == clientWidth`；
  - 开关 54 组全部可见、track 27.98×13.99 / knob 9.98×9.98 / dx=15 / dy=0.98；
  - 徽标 163 + 1 + 2 处尺寸见 8.4，全部不裁字；
  - 4 类提示气泡与两个紧凑滑条用 `zoom` 放大截图确认无接缝、无文字压边、拇指可见；
  - 临时探针（zoom / transform / 追加 harness）已全部还原，页面无残留。
- `?mini=1`（page 3）：`.am-tab`(5) / `.task-switch-track`(54) / `.task-switch-knob`(54) /
  `.gw-badge-new`(1) / `#am-traderlvl`(1) / `#gw-traderlv`(1) 等 13 个目标选择器
  **可见数全部为 0** → 零影响。
- `python -m pytest tests -q` → **1767 passed, 1 skipped in 100.24s**（exit 0）。未提交 git。

---

## 九、R94：最后一板（`Create ONE single 4K sprite she_881c048f.png`，19 件）

> 板面实测 2880×2880（非 3840×2160）；键色实测 **#DF2CEB = RGB(223,44,235)**，
> 四边 20px 条带均值互差 ≤1.2/通道、σ ≤1.7 —— 与规格写的 `#E815EF` 相比**绿通道差 23**，
> 以实测为准。19 件按连通域 bbox 重测后匹配，**15 件落盘并接入，4 件退回**。

### 9.1 逐件结果

| # | 件 | 落盘 | 接入选择器 | 体检结论 |
|---|---|---|---|---|
| 1 | `current-gun-plate` 288×32 | ✅ | `.gun-workbench #gw-current`（`5 5 5 14 / 5px`） | 中心 40% 区域非米色像素 **0** ✔ |
| 2 | `version-plate` 136×22 | ✅ | `#build-rev` + `.tk-build`（`4 5 4 5 / 4px 5px`） | 中心空白 ✔；宽高比 4.59≠6.18，九宫格吸收 |
| 3 | `brand-plate` 120×31 | ✅ | `#app-brand.app-brand`（`5 5 5 14 / 5px`） | 中心空白 ✔；实测 122×30 渲染，左 14px 缩进不变 |
| 4 | `table-frame` 64×64 | ✅ | `.loadout-workbench .tbl-scroll` / `.gun-workbench .tbl-scroll` / `.am-workbench .am-table .tbl-scroll`（`2 fill / 2px`） | 内圈全透明，`fill` 不产生色块；实测配装滚区 1316×735 |
| 5–7 | `empty-task` / `empty-story` / `empty-gun` 48×48 | ✅ | `.task-list > .task-empty::before`、`#tk-story-list .tk-story-empty::before`、`#gw-browse .lw-loading::before` | 整件 48×48 不缩放；图形自带米色面但外圈全键色，无底板方块 |
| 8–12 | `icon-map/tasks/ammo/gun/loadout` 16×16 | ✅ | `.view-toolbar #view-btn-* .vt-ico`（内联 SVG 置 0） | 纯墨色、**无底板** ✔；实测 16×16 一一对应 |
| 13–15 | `scroll-h-thumb` / `-hover` / `-pressed` 44×21 | ✅ | `::-webkit-scrollbar-thumb:horizontal` 三态 | 三态同高 174、宽 490/500/516；1x 后 1px 暗边 + 1px 高光，边线一致 |
| 16 | `scroll-v-arrow-down-normal` | ❌ | — | 三角 **96×56 → 11×7**，规格要求 15×10；距顶 88px → 10.4，规格 9 |
| 17 | `scroll-v-arrow-down-hover` | ❌ | — | 同上（96×55），两态几何一致但都不达标；保留现有 `scroll-v-glyph-down` 叠字方案 |
| 18 | `sep-horizontal` | ❌ | — | 实为 **551×48 的三段立体槽**（暗 5px + 白 6px + 面），非 64×2 两行线，沿长度有 20+ 级灰度漂移 |
| 19 | `sep-vertical` | ❌ | — | 实为 **44×224 立体条**（暗 6px + 米面 17px + 暗 6px），只有左暗边、无右高光，无法拆出 2×22 |

> 四条退回件均按「不可用就保留现状」处理，`xp-ui-app.css` §19 只登记不接线；
> 现有分隔线仍是 CSS 双色 2px，数字微调/滚动箭头仍是 `scroll-v-glyph-down.png` 叠字。

### 9.2 重扫计数（R94 后，脚本 `tools/xp_ui_coverage_scan.py`）

| 视图 | A / B / C = 总数 | A 占比 | 其中引用本板新件 |
|---|---:|---:|---:|
| 地图 map | 392 / 10 / 0 = 402 | 97.5% | 7（品牌 1 + 版本 1 + 图标 5） |
| 任务 tasks | 544 / 3788 / 0 = 4332 | 12.6% | 8（品牌 1 + 版本 2 + 图标 5） |
| 弹药 ammo | 2512 / 0 / 0 = 2512 | 100% | 8（+ 表格外框 1） |
| 枪匠 gun | 392 / 199 / 0 = 591 | 66.3% | 8（+ 当前配枪铭牌 1） |
| 配装 loadout | 562 / 54 / 0 = 616 | 91.2% | 8（+ 表格外框 1） |
| **五视图合计** | **4402 / 4051 / 0 = 8453** | **52.1%** | **39 次引用 / 11 个唯一元素** |

> **为什么不能和 8.5 的 3897/4275 直接相减**（如实说明，不是回退）：
> 1. 本板 §4 第 1 条把 `button.task-main`×54 等元素的 `border-radius` 归零，这些元素原本**只靠圆角**
>    满足「有装饰」判定，改完后落进「无装饰」不计入 —— 地图 B 由 68 变 10 主要来自这里；
> 2. 任务视图本次默认渲染 `article.db4-row` 表格 **503 行**（R93 盘点时是任务树状态），
>    分母从 152 变 4332，A 占比因此被稀释到 12.6%，属渲染状态差异；
> 3. 本板真实 A 增量 = **11 个唯一元素**（品牌牌 1、版本牌 2、当前配枪铭牌 1、表格外框 2、视图图标 5），
>    按 R93 分母 4275 折算 **A 占比 91.2% → 91.4%**；空态 3 件只在空态出现、滑块 3 态属滚动条伪元素，
>    元素级无法计入。

### 9.3 验证

- `tools/xp_ui_r94_verify2.py`（Chrome CDP，1834×1030）实测：
  `#app-brand` 122×30 → `brand-plate.png`；`#build-rev` 137×21 → `version-plate.png`；
  `#gw-current` 222×34 → `current-gun-plate.png`；`.tbl-scroll` 1316×735 → `table-frame.png`；
  五图标 16×16 → `icon-*.png`；`.lw-cell-name` 8px → 10px。
- `?mini=1`：本轮新增规则全部作用于菜单栏 / 视图工具条 / 工作区，mini 下命中元素数 **0**（A 0 / B 1）。
- `python -m pytest tests -q` → 见 9.4。未提交 git。

### 9.4 测试

- `python -m pytest tests -q` → **1767 passed, 1 skipped in 96.60s**（exit 0）。未提交 git。

## 十、R97：6 处 `background-size: 100% 100%` 拉伸收尾

> 本轮只处理「位图被整图拉伸」的 6 处，不改 DOM / 类名 / 交互；`?mini=1` 零影响。
> 验收脚本：`tools/xp_ui_r96_verify.py`（Chrome CDP，1834×1030，deviceScaleFactor=1）。

### 10.1 逐处改法与实测

| # | 选择器 | 原素材 → 实测盒 | 改法 | 两档实测 |
|---|---|---|---|---|
| 1 | `html body .tbl-scroll .tbl-row` / `:nth-child(even)` | `tbl-row.png` / `tbl-row-alt.png` 600×24 → 1302×78 | 纯色 `#FAF6ED` / `#CDC5B5`（取素材均值），网格线仍由 `tbl-grid-h` 的 1px 切片负责 | 24 / 48px 顶底边线最大差 **0/通道**，`background-image=none` |
| 2 | `html body .task-list .task-row` | `tbl-row.png` 600×24 → 行高随标题换行 | 纯色 + 1px 四向凹槽边（`#D5D3C4` / `#8B8876` / `#F8F6EB` / `#FBFAF5`，取自 groupbox 实测） | 24 / 56px 边线最大差 **0/通道** |
| 3 | `html body .gun-workbench .gw-browse-gun`（三态） | `tbl-row.png` / `btn-hover.png` / `btn-pressed.png` 95×42 | **降级为纯 CSS 三态**：`#FAF6ED` / `#F7F5EE` / `#D4D4C2` + 1px 双色边（见 10.2） | 该选择器当前 DOM 命中数 **0**（死规则，见 10.3） |
| 4 | `html body #layers-block .legend-item` / `.legend-sub` | `tbl-row.png` 600×24 | 纯色 + 1px 四向凹槽边（同上） | 24 / 42px 边线最大差 **0/通道** |
| 5 | `html body .loadout-workbench .lw-cost-item` | `tbl-row.png` 600×24 → 483×24 | 纯色 `#FAF6ED`，hover `#F7F5EE` | 24 / 42px 边线最大差 **0/通道** |
| 6 | `html body .gun-workbench .gw-bar-fill.blue` / `.gw-bar-seg.neutral` | `progress-fill(-indeterminate).png` 197/200×17 → 5px 高 | `border-image: … 2 1 2 1 fill / 2px 1px stretch` + `box-sizing:border-box`：上 2 行亮带 / 下 2 行暗带 1:1 保留 | 段 138×5，逐行均值 (75,83,113) / (42,99,186) / (53,119,218) / (40,96,182) / (80,89,117)：亮带−暗带 = 72，双带未压扁 |

### 10.2 降级说明（`gw-browse-gun`）

`btn-hover.png` / `btn-pressed.png` 是 95×42 的**整图圆角按钮**，铺进高度不定、宽度 300–1300px 的列表行时圆角被拉成椭圆，且会盖住行内文字。按任务书允许的方式降级为纯 CSS 三态 + 1px 双色边，不引用任何会被拉伸的位图；底色与同屏列表行 `#FAF6ED` 一致，hover 用 `#F7F5EE`、选中用 `#D4D4C2`。该选择器在当前 DOM 里已无命中（浏览页卡片改用 `.gw-browse-grid > .gw-card`），保留规则但不再产生拉伸。

### 10.3 死规则核实

- `.gw-browse-gun`：`document.querySelectorAll` = 0；当前 DOM 用 `.gw-browse-grid > .gw-card`。
- `.gw-bar-fill`（含 `.blue` / `.ok` / `.red`）：命中 0；当前属性条只用 `.gw-bar-seg`（app.js L18989 动态生成，`neutral` 等分段）。
- 两者此前在盘点里被计为「已接但会拉伸」，本轮改为纯 CSS / 九宫格后即使将来重新启用也不会拉伸。

### 10.4 40 行长列表

`#gear-table .tbl-scroll` 超视口整表截图 1316×3152，40 行 × 78px；逐行扫描竖向色带变化点 45 个，相邻行只有 1px 网格线（`(234,226,211)`）过渡，行内为单一纯色，**无接缝、无糊边**。

### 10.5 验证

- `python -m pytest tests -q` → 见下方 10.6。
- `?mini=1`：`html.class=tk-mini-root`，`#app-menubar` / `#app-statusbar` 均 `display:none`，右键菜单项 2 个。
- 未提交 git。

### 10.6 测试

- `python -m pytest tests -q` → **1767 passed, 1 skipped**（exit 0）。未提交 git。

## 十一、R98：还剩什么（五视图 + 六类弹窗实扫）

> 口径不变（6.1）。数据：`tools/xp_ui_coverage_scan.py`（五视图，1834×1030）＋同族离屏探针
> （六类弹窗，真实类名与子结构，读完即删）。素材引用范围 = 实际加载的 18 个 css/js/html。

### 11.1 计数

| 范围 | A | B | C | D | total | A% |
|---|---:|---:|---:|---:|---:|---:|
| 五视图合计 | 4302 | 4151 | 0 | 12277 | 8453 | 50.9 |
| `?mini=1` | 0 | 1 | 0 | 3523 | 1 | 0 |

> 任务视图 B=3788 里 3018 来自 `.db4-row` / `.db4-tick` / `.db4-name` / `.db4-exp-val` /
> `.db4-complete` 各 503（任务总表 503 行），其余是 `.db4-map` / `.db4-lv` / `.db4-item` 等
> 文本与缩略图单元。这些是**纯平表格**，XP 原生就是白底行 + 1px 网格，属 CSS 正解。

### 11.2 弹窗实扫（六类 + 校准）

| 弹窗 | 根底板 | A/B/C/D | 结论 |
|---|---:|---:|---|
| 应用菜单 `.app-menu-panel` | `app-menu-panel-bg.png` | 1/0/0/3 | 根 A；`.app-menu-item` 无边框、hover 走 CSS 蓝底 |
| 任务右键 `.task-context-menu` | `context-menu-bg.png` | 1/0/0/2 | 根 A；分隔线走 `::before` + `sep-horizontal.png` |
| 提示气泡 4 类 | `tip-plate.png` | 1/0/0/0 | 全部 A |
| 通用弹窗 `.lw-modal-box` / `.lw-preset-box` | `dialog-box.png` + `titlebar.png` | 2/2/2/1 | 根/标题 A；**按钮与输入框回落到主题渐变**（11.3） |
| 弹药详情 `.am-modal-box` | `dialog-box.png` | 2/2/0/1 | 根 A；按钮 A（`btn-normal.png`）；标题是 R94 刻意硬化的三段色标 |
| 个人属性 `.gw-prof-box` | `dialog-box.png` + `titlebar.png` | 2/1/0/2 | 根/标题 A；底部按钮同 11.3 |
| 校准 `.cal-modal` | `dialog-box.png` | 1/2/0/1 | 根 A；两个按钮同 11.3 |

### 11.3 实测发现（CSS 侧，不是缺素材）

`theme-windows-xp.css` 的 `html .loadout-workbench button:not(...)`（0,2,2）压过
`xp-ui-app.css` 的 `html body .lw-modal-box button`（0,1,3），所以通用弹窗 / 个人属性 / 校准
弹窗里的按钮渲染成**主题渐变**而不是 `btn-normal.png`；同理 `input` / `select` 也被主题的
1px 蓝灰边规则盖住。素材齐、落点齐，只需提高选择器特异性。

### 11.4 素材库盘点

`assets/xp-ui/` 共 132 个 png，实际加载文件中未被引用 **37 个**，分四类：

| 类别 | 数量 | 处置 |
|---|---:|---|
| 可接但当前没落点 | 13 | `win-btn-close/min/max` 9 + `win-glyph-close/min/max` 3（弹窗关闭键目前 CSS 重绘）、`dialog-head.png`（备用标题栏） |
| 无对应语义/状态 | 7 | `badge-md-warn`（无 warn 态）、`progress-fill-100`（无满格态）、`plaque-1`（旧铭牌）、`slider-v-*` 4（无竖向 range） |
| 已被新件取代 | 14 | `scroll-h-thumb/hover/pressed` 3、`scroll-v-thumb/hover/pressed` 3、`scroll-v-arrow-down` / `-down-pressed` / `-up-pressed` / `glyph-down` 4、`tab-active/inactive` 2、`tbl-row/-alt` 2（R97 退役） |
| DOM 无独立元素 | 3 | `context-menu-sep` / `menu-panel-sep` / `statusbar-sep`，已由伪元素与 Pillow 件替代 |

**结论：无「没素材但需要位图」的缺口。** 剩余 B 类全部是语义色、真实照片、文本或纯平表格，
不需要新建位图。未创建 `docs/xp-ui-final-board2-prompt.md`。未提交 git。
