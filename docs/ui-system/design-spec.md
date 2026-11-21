# EFT Interactive Map · 项目级 UI 设计规范（Windows XP Luna 方向）

- 版本：`ui-spec 1.0`（对应构建 `R19.24`）
- 适用范围：全部浏览器端界面（地图 / 配装 / 配枪 / 弹药 / 任务 / 校准器 / 设计系统展示页）
- 前置文档：`docs/ui-system/audit.md`（现状与数字）
- 实现文件：`styles/design-tokens.css`、`styles/ui-components.css`、`js/ui-components.js`
- 组件清单：`docs/ui-system/component-catalog.md`

---

## 一、定位与原则

**一句话**：把 Windows XP Luna 的视觉语言（蓝标题栏、米灰面、凸起按钮、内凹输入、列表视图），
整理成一套适合**高密度数据工具**的现代前端设计系统；不追求像素级复刻，也不改成 SaaS 后台风。

### 1.1 九条硬原则

1. **蓝色是"已发生的事情"，琥珀色是"指针正在做的事情"**。
   蓝 = 选中 / 焦点 / 当前视图；琥珀 = 悬停 / 分段控件的当前项（视觉上像"按下去的按钮"）。
   两者语义不混用：一个控件不可能同时靠颜色表达这两个状态。
2. **层级靠"边框 + 面"，不靠阴影堆叠**。面板 1px 深边 → 白面 → 内凹 1px 亮/暗双线，最多两层立体。
3. **信息密度优先**。行高、字号、内边距服从"一屏能看多少行"，不为美观放大留白。
4. **立体感只在控件上**：按钮凸起、输入凹陷、标题栏渐变。面板与表格保持平。
5. **状态必须"多通道"**：颜色之外还有形状（虚线/实线/下沉位移）、文字（"已完成"）、符号（✓/✕/◐）。
   色盲用户不靠颜色也能分辨。
6. **禁用是真的禁用**：`disabled` + `aria-disabled` + 不可聚焦 + 不改鼠标指针为可点，不能只降低透明度。
7. **焦点永远可见**：键盘 Tab 到任何可交互元素都必须有 1px 蓝色焦点环（或 2px 外描边），
   并且 `:focus-visible` 与鼠标点击后的 `:focus` 要区分。
8. **浮层不被裁切**：下拉、提示、弹窗一律挂到 `body`（portal），定位用 fixed + 视口碰撞翻转。
9. **模块可以有自己的业务布局，但不能有自己的视觉语言**。允许模块决定"放在哪、多大"，
   不允许决定"按钮长什么样、状态用什么颜色"。

### 1.2 与 shadcn/ui 的关系（只借鉴方法，不引入依赖）

| shadcn/ui 的做法 | 本项目怎么用 |
|---|---|
| 语义化 CSS 变量（`--background` / `--primary` / `--border` / `--radius`）驱动全部组件 | 采用。落到 `--ui-*` 令牌（颜色 / 字体 / 间距 / 尺寸 / 层级） |
| 组件的"变体 + 尺寸"用一套受控枚举（variant / size），不给调用方自由写样式 | 采用。`ui-btn--primary`、`ui-btn--sm` 这类修饰类，禁止调用方传颜色 |
| 用 `data-state="open/checked/active"` 之类属性表达状态，而不是散落的 `.on`、`.active` | 采用。统一 `aria-selected` / `aria-pressed` / `aria-expanded` / `data-state` |
| 组件源码直接放进项目、可改，而不是黑盒 npm 包 | 采用。`js/ui-components.js` + `styles/ui-components.css` 就是项目自己的源码 |
| 组合优于配置（`asChild`、插槽式 children） | 部分采用。原生 DOM 下用"容器 + 子元素类名"代替插槽，不做 JSX |
| Tailwind 原子类 + Radix 无障碍原语 + React 运行时 | **不采用**。项目是原生 JS + Python 标准库 HTTP，引入即违反"离线 / 不加运行时依赖"约束 |

> 结论：借它的**组织方式**（令牌 → 变体 → 状态属性 → 可复制源码），不借它的**技术栈**。

### 1.3 明确不做的事

- 不引入 React / Vue / Tailwind / npm 运行时依赖 / CDN。
- 不用网络字体、在线图标、在线组件库；图标继续用项目已有 SVG 或纯 CSS 图形。
- 不做暗色模式（当前无需求；令牌已按语义命名，将来加暗色只需换 `--ui-color-*` 的映射）。
- 不做移动端响应式重排（桌面工具，最低支持宽度 1280px；见 §7.4）。
- 不改业务逻辑、数据结构、存储键、导入导出格式。

---

## 二、令牌体系

所有令牌定义在 `styles/design-tokens.css` 的 `:root`，前缀统一 `--ui-`。
**新代码只允许使用本节的令牌**；不允许再写裸十六进制色、裸 `13.5px`、裸 `z-index: 9990`。

### 2.1 颜色（语义命名 + 唯一来源）

颜色令牌分两类：

- **桥接令牌**：值等于既有 `--xp-*`（R18/R19.15 建立的 Luna 调色板），如
  `--ui-color-primary: var(--xp-luna-1)`。这样"调色板的唯一来源仍是 `--xp-*`"，
  不会出现第二套近似值；将来合并主题层时只需改桥接方向。
- **新增令牌**：`--xp-*` 里确实没有的角色（凹陷面、遮罩、冲突色、焦点环）。

| 令牌 | 用途 | 值来源 |
|---|---|---|
| `--ui-color-primary` | 主色（标题栏、品牌、主按钮描边） | `--xp-luna-1` `#0a3f9e` |
| `--ui-color-primary-hi` | 主色高光（标题栏渐变上端） | `--xp-luna-2` `#1466e0` |
| `--ui-color-primary-lo` | 主色低光（标题栏渐变下端） | `--xp-luna-3` `#4a9bff` |
| `--ui-color-selected` | 选中填充（列表/表格选中行、当前视图） | `--xp-sel` `#316ac5` |
| `--ui-color-selected-bg` | 选中浅底（当前标签、选中卡片） | `--xp-row-hover` `#eaf3ff` |
| `--ui-color-selected-text` | 选中上的文字 | `--xp-sel-text` `#ffffff` |
| `--ui-color-hover` | 悬停底（按钮/行/菜单项） | `--xp-hover-c` `#ff9933` 系列 |
| `--ui-color-hover-soft` | 悬停底（大面积、弱化） | `--xp-btn-hover-c` `#ffd98a` |
| `--ui-color-hover-border` | 悬停描边 | `--xp-btn-hover-border` `#c97a10` |
| `--ui-color-focus` | 焦点环 | `--xp-link` `#1e63c8` |
| `--ui-color-surface` | 页面/工作面 | `--xp-face` `#ece9d8` |
| `--ui-color-surface-alt` | 次级面（面板、卡片） | `--xp-face-2` `#f7f5ee` |
| `--ui-color-surface-raised` | 抬升面（白底：输入、表格、对话框正文） | `--xp-face-3` `#ffffff` |
| `--ui-color-surface-inset` | 凹陷面（禁用、只读、进度槽） | 新增 `#f2f0e6` |
| `--ui-color-text` | 正文 | `--xp-text` `#000000` |
| `--ui-color-text-muted` | 次要文字 | `--xp-text-dim` `#4a4a4a` |
| `--ui-color-text-disabled` | 禁用文字 | `--xp-btn-disabled-text` `#8d8d8d` |
| `--ui-color-text-inverse` | 深底上的文字 | `#ffffff` |
| `--ui-color-link` | 链接/可点文字 | `--xp-link` `#1e63c8` |
| `--ui-color-border` | 普通边框 | `--xp-border` `#aca899` |
| `--ui-color-border-soft` | 次级分隔 | `--xp-border-soft` `#d6d2c2` |
| `--ui-color-border-light` | 亮边（凸起高光） | `#ffffff` |
| `--ui-color-border-dark` | 暗边（输入框、表格外框） | `--xp-border-dark` `#7f9db9` |
| `--ui-color-success` / `-bg` | 成功 | `--xp-ok` `#0b6b3a` / `#e8f6ec` |
| `--ui-color-warning` / `-bg` | 警告 | `--xp-warn` `#7a5200` / `#fdf7e3` |
| `--ui-color-danger` / `-bg` | 危险/失败 | `--xp-bad` `#a11b1b` / `#fdeaea` |
| `--ui-color-info` / `-bg` | 信息 | `--xp-info` `#0a4fa8` / `#eaf3ff` |
| `--ui-color-conflict` | 冲突（与危险同色系，但配虚线 + 图标） | 新增 `#8a2f00` |
| `--ui-color-scrim` | 弹窗遮罩 | 新增 `rgba(0,0,0,.28)` |

**用法约束**

- 状态色只用于"状态"：`--ui-color-success` 不能拿来当"开始按钮"的底色。
- 大面积底色只用 `surface*`；状态色只做描边/文字/小色块 + `-bg` 浅底。
- 地图画布内部（SVG 标注、底图）不适用本表，见 §2.5 例外。

### 2.2 字体

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ui-font` | `Tahoma, "Microsoft YaHei UI", "Microsoft YaHei", sans-serif` | 全局（桥接 `--xp-font-family`） |
| `--ui-font-mono` | `Consolas, "Courier New", monospace` | 数字、ID、坐标、种子 |
| `--ui-fs-micro` | 11px | 辅助信息、徽标、图表刻度 |
| `--ui-fs-compact` | 12px | 表格、紧凑控件、工具栏 |
| `--ui-fs-body` | 13px | 正文、详情段落 |
| `--ui-fs-strong` | 14px | 强调正文、面板小标题 |
| `--ui-fs-panel` | 15px | 面板标题 |
| `--ui-fs-title` | 18px | 页面标题 |
| `--ui-fw-normal` / `-bold` | 400 / 700 | 只有两档 |
| `--ui-lh-tight` / `-normal` / `-loose` | 1.25 / 1.5 / 1.7 | 表格紧凑 / 常规 / 长文（详情、攻略） |

**字号规则**

- 只允许 6 档字号。禁止 `10.5px`、`11.5px`、`12.5px`、`13.5px` 这类半像素值。
- 最小可用字号 11px。`9px/10px` **仅限地图画布内标注与散点图刻度**（画布不属于页面 UI）。
- 中文长文（任务攻略、说明）用 `--ui-fs-body` + `--ui-lh-loose`，单行长度建议 ≤ 42 个汉字。

### 2.3 间距、尺寸、圆角、边框、阴影

| 类别 | 令牌 | 值 |
|---|---|---|
| 间距 | `--ui-space-1..7` | 4 / 6 / 8 / 12 / 16 / 20 / 24 px（桥接 `--xp-space-*`） |
| 控件高度 | `--ui-control-h-sm` / `-md` / `-lg` | 22 / 26 / 30 px |
| 按钮内边距 | `--ui-btn-pad-x` / `--ui-btn-pad-x-sm` | 10px / 7px |
| 图标 | `--ui-icon-sm` / `-md` / `-lg` | 12 / 16 / 20 px |
| 边框 | `--ui-border-w` / `--ui-border-w-strong` | 1px / 2px |
| 圆角 | `--ui-radius-panel` / `-control` / `-btn` / `-pill` | 0 / 2px / 3px / 10px |
| 立体 | `--ui-shadow-raised` | `inset 1px 1px 0 #fff, inset -1px -1px 0 var(--ui-color-border)` |
| 凹陷 | `--ui-shadow-sunken` | `inset 1px 1px 0 var(--ui-color-border), inset -1px -1px 0 #fff` |
| 弹窗 | `--ui-shadow-dialog` | `2px 2px 8px rgba(0,0,0,.35)` |
| 焦点环 | `--ui-shadow-focus` | `0 0 0 1px var(--ui-color-focus)` |

**尺寸规则**

- 同一行内的控件必须同高（默认 `-md` = 26px；工具条里允许 22px 紧凑档，但整行统一）。
- 面板内边距：`--ui-space-3`（8px）；面板之间 `--ui-space-3`；页面外边距 `--ui-space-4`（12px）。
- 圆角只有 4 档：面板 0（XP 分组框是直角）、控件 2px、按钮 3px、药丸标签 10px。禁止 4/6/8px。

### 2.4 层级（z-index）

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ui-z-raised` | 10 | 卡片抬升、粘性表头 |
| `--ui-z-sticky` | 90 | 页面内粘性工具条（沿用旧值，避免回归） |
| `--ui-z-dropdown` | 900 | 下拉面板、自动完成列表 |
| `--ui-z-overlay` | 9000 | 弹窗遮罩（与既有 `.am-modal`/`.cal-overlay` 同层） |
| `--ui-z-dialog` | 9100 | 弹窗本体 |
| `--ui-z-menu` | 9500 | 右键菜单、上下文菜单 |
| `--ui-z-tooltip` | 9600 | 提示框（必须在弹窗之上） |
| `--ui-z-toast` | 9800 | 全局提示条 |

禁止在业务代码里写裸 `z-index`。已知历史遗留：`.am-sim-ammodlg` (9990) 高于 `--ui-z-tooltip`，
属待收敛项，不在本轮改动范围（记录于 `component-catalog.md` 的"已知偏差"）。

### 2.5 例外（允许脱离令牌的场景，必须写注释说明）

| 场景 | 允许 | 理由 |
|---|---|---|
| 地图画布内部 | 深色底、9–10px 标注、任意 rgba 叠加 | 底图与彩色标注需要暗底；属"画布像素"而非页面 UI |
| 散点图/图表绘制 | 图例与刻度用 `--ui-fs-micro`，但坐标轴像素位置可任意 | 图表由 canvas/SVG 精确摆放 |
| 业务数据可视化（属性条、进度条宽度） | JS 内联 `style.width` | 值来自数据，不是样式决策 |
| 图标内部路径 | SVG 的 `fill` 可写死 | 图标是资源，不是主题元素 |

---

## 三、状态语义（所有交互控件共用）

| 状态 | 触发 | 视觉表达（必须同时满足） | 语义属性 |
|---|---|---|---|
| Default | 无 | 凸起面 + 1px 深边 | — |
| Hover | 指针悬停 | 底色转琥珀 `--ui-color-hover-soft`、描边转 `--ui-color-hover-border`；光标 pointer | — |
| Active/Pressed | 按下 | 底色加深、`translateY(1px)`、立体阴影翻转为凹陷 | `:active` |
| Focus | 键盘聚焦 | 1px 蓝色焦点环（`--ui-shadow-focus`）+ 不影响布局 | `:focus-visible` |
| Selected | 被选中/当前 | 蓝底白字 **或** 浅蓝底 + 蓝左边条 3px；**不得**只用琥珀 | `aria-selected="true"` / `aria-pressed="true"` |
| Disabled | 不可用 | 灰面 + 灰字 + 去立体 + `cursor: not-allowed` | `disabled` + `aria-disabled="true"` |
| Error | 校验失败 | 红描边 2px + 红色说明文字 + `aria-invalid="true"` | `aria-invalid` |
| Loading | 进行中 | 控件内左侧 12px 旋转指示 + 文案改"处理中…" + 禁止重复点击 | `aria-busy="true"` |
| Conflict | 业务冲突（如槽位占用） | 红虚线描边 + ⚠ 图标 + 文字说明；**并且逻辑上不可选** | `data-state="conflict"` + `disabled` |

**硬约束**

- Hover 与 Selected 不能同色：`--ui-color-hover-soft`（琥珀）vs `--ui-color-selected`（蓝）。
- 分段控件（视图切换、模式切换）的"当前项"使用琥珀底 + 深色字 + 内凹阴影（像被按下），
  与"选区"（蓝）区分；这是 XP 按钮组的心智模型，属于**唯一**允许用琥珀表达"当前"的组件。
- 危险操作（删除、清空、覆盖）必须有二次确认，确认按钮用 `ui-btn--danger`，默认焦点落在"取消"。
- 动效时长 ≤ 140ms；`prefers-reduced-motion: reduce` 时全部动效归零。

---

## 四、组件规范

命名：CSS 用 `ui-` 前缀 + BEM（`ui-panel__head`）；JS 用 `GWUI.xxx()`。
每个组件都必须支持"额外类名"参数（`className`），用于兼容既有测试钩子，但**不允许**用额外类名改变视觉。

### 4.1 Button

- 结构：`<button class="ui-btn ui-btn--primary ui-btn--md">文字</button>`，可含 `<span class="ui-btn__icon">`。
- 变体：`--primary`（主操作，蓝底白字）、`--default`（默认凸起）、`--danger`（危险，红字红边）、
  `--ghost`（无底无边，工具栏图标按钮）、`--link`（文字按钮）。
- 尺寸：`--sm`(22) / `--md`(26，默认) / `--lg`(30)。
- 状态：见 §3；按下必须有 1px 下沉。
- 可访问性：图标按钮必须 `aria-label`；切换型按钮用 `aria-pressed`；菜单触发用 `aria-haspopup` + `aria-expanded`。
- 禁止：用 `<div>` 冒充按钮；按钮里嵌套交互元素；用 `outline: none` 去掉焦点。

### 4.2 Input / Select / Checkbox / Radio

- Input：`--ui-control-h-md`，白底，`--ui-shadow-sunken`，聚焦换蓝边 + `--ui-shadow-focus`。
  数字输入右对齐（`--num`）。错误态见 §3。
- Select：原生 `<select>` 外观定制，**保留原生下拉**（离线、可键盘、无 portal 问题）；
  自定义下拉（`ui-select--custom`）仅在需要显示图标/分组时才用，且必须挂 portal。
- Checkbox/Radio：`label.ui-check` 包 `input + span.ui-check__box + span.ui-check__label`，
  框 13×13，选中用 CSS 勾（不用字符），禁用灰化且不可聚焦。
- 所有控件支持"标签 + 说明 + 错误文字"三段结构（`ui-field`）。

### 4.3 Tabs（含分段控件）

- `ui-tabs` + `ui-tab[role=tab][aria-selected]`；当前项：琥珀底 + 内凹 + 加粗。
- 键盘：左右箭头切换、Home/End 到首尾；`tabindex` 只留当前项可聚焦（roving tabindex）。
- 分段控件（视图切换/模式切换）复用同一套，但容器用 `ui-tabs--segmented`。

### 4.4 Panel / GroupBox

- `ui-panel` > `ui-panel__head`（可选 `__title` / `__actions`）+ `ui-panel__body` + 可选 `__foot`。
- `ui-panel--group`：XP 分组框，1px 深边 + 4px 内缩标题（标题压在边框上）。
- 嵌套最多两层；第三层改用"小标题 + 分隔线"。
- 折叠：`ui-panel--collapsible` + `aria-expanded`，折叠时只保留标题条。

### 4.5 Toolbar / Statusbar / Titlebar

- `ui-toolbar`：高 30px，`--ui-space-2` 间距，分组用 `ui-toolbar__sep`（1px 竖线）。
- `ui-titlebar`：Luna 渐变（`--ui-color-primary-hi` → `--ui-color-primary`），高 26px，
  左图标（16px）+ 标题（`--ui-fs-compact` 加粗白字）+ 右侧操作区。
  **不是**给 div 涂蓝：必须有渐变、1px 内亮边、圆角仅上两角 3px、标题带省略号。
- `ui-statusbar`：高 24px，米灰面，上边 1px 深边，右侧可放计数。

### 4.6 Table

- `ui-table` > `ui-table__head` / `ui-table__row` / `ui-table__cell`；
  表头白→米灰渐变 + 1px 深边；行交替色；悬停浅琥珀；选中蓝底白字；粘性表头。
- 行状态：`.is-selected`（`aria-selected`）、`.is-disabled`、`.is-conflict`（红虚线 + ⚠）。
- 列宽：调用方以 `--ui-table-cols`（`grid-template-columns` 字符串）声明；禁止用 `style.width` 逐格设置。
- 空态：`ui-table__empty`（居中灰字 + 说明），不能只留空白。

### 4.7 Badge

- `ui-badge` + `--ok/--warn/--danger/--info/--muted`；高 16px，圆角 10px，`--ui-fs-micro`。
- 必须带文字（不能只有色块）；状态含义不能只靠颜色。

### 4.8 Dialog

- 结构：`ui-dialog__scrim`（点击关闭，可 `data-static` 禁止）+ `ui-dialog__box`
  > `ui-dialog__head`（`__title` + `__close`）+ `ui-dialog__body` + `ui-dialog__foot`。
- 行为：打开时记录并锁定焦点、焦点环在框内循环、`Esc` 关闭（除非 `data-static`）、关闭后焦点回到触发元素、
  `body` 加 `ui-scroll-lock`。
- 层级：scrim `--ui-z-overlay`，box `--ui-z-dialog`。
- 危险操作：标题带 ⚠，确认按钮 `--danger`，默认焦点在"取消"。
- 禁止：一个页面挂多个同 id 的 dialog；用 `alert()`/`confirm()` 代替（新代码）。

### 4.9 Menu / Dropdown

- `ui-menu` 挂 body，`position: fixed`；锚点矩形 + 视口翻转（下→上、左→右）。
- 项：`ui-menu__item[role=menuitem]`，支持 `disabled`、`aria-checked`（多选型）、分隔线 `ui-menu__sep`。
- 键盘：↑↓ 移动、Enter 触发、Esc 关闭、Home/End；打开时焦点进入第一项。
- 关闭：点击外部、Esc、选择后；不得在滚动父容器里被裁切。

### 4.10 Tooltip

- 仅用于"补充说明"，不得承载必须信息（必须信息要写在界面上）。
- 触发：hover 300ms 延迟、focus 立即；离开 100ms 后隐藏。
- 定位：fixed + 8px 间距 + 视口碰撞翻转；最大宽 320px，长文自动换行（`--ui-lh-normal`）。
- 与 `title` 的关系：**保留** `title` 作为可访问名与 i18n 英文原文（R19.22 约定），
  自定义 tooltip 只在需要富文本/换行时使用，且不得与 `title` 同时出现在同一元素上造成双提示
  （做法：使用 tooltip 的元素不设 `title`，改用 `aria-describedby`）。

### 4.11 Toast（轻量）

- `ui-toast` 右下角堆叠，3 秒自动消失，`--ui-z-toast`；用于"已保存/已复制"这类非阻断反馈。
- 不得用于错误必须被阅读的场景（那要用 dialog 或行内 alert）。

---

## 五、页面布局规范

统一项：页面外边距 `--ui-space-4`；工具条高 30px；标题 `--ui-fs-title`；面板间距 8px；
所有页面共用 `ui-toolbar` / `ui-panel` / `ui-table` / `ui-statusbar`。

| 页面类型 | 结构 | 要点 |
|---|---|---|
| 地图类 | 左栏（筛选表 + 列表）+ 右画布 + 底部状态栏 | 画布保持深色；左栏用 `ui-panel` + `ui-table`；HUD 用 `ui-panel--floating` |
| 工作台/构建器 | 顶工具条 + 左槽位/中画布/右候选 三栏 | 三栏都用 `ui-panel`；列间 8px；不允许每栏自造按钮 |
| 数据表格页 | 工具条 + 筛选行 + `ui-table`（粘性表头）+ 状态栏 | 列宽 `--ui-table-cols`；空态必须有说明 |
| 任务树页 | 头部（标题+分段控件+筛选）+ SVG 画布 + 右侧摘要 | 画布内节点是业务图形，不受组件样式约束，但状态色取自令牌 |
| 仿真器页 | 左参数栏 + 右结果区 + 底部执行条 | 参数用 `ui-field`；执行条 sticky（`--ui-z-sticky`） |
| 表单/配置页 | 单列表单，`ui-field` 垂直排布，宽度 ≤ 640px | 标签在上、说明在下、错误红字替换说明 |
| 说明/文档页 | 标题 + 段落 + 代码块（`ui-code`） | 长文 `--ui-lh-loose`，最大宽 760px |

---

## 六、允许 / 禁止模块自决

| 内容 | 模块可自决 | 必须遵守 |
|---|---|---|
| 布局（分栏、栅格、滚动区域） | ✅ | 间距用 `--ui-space-*` |
| 业务专用可视化（槽位板、散点图、任务树节点） | ✅ | 状态色取自令牌；不新造按钮/输入样式 |
| 颜色 | ❌ | 只能用 `--ui-color-*`；确需新色必须先进令牌 + 更新本文档 |
| 字号/字重 | ❌ | 只能用 6 档字号 + 2 档字重 |
| 圆角/边框/阴影 | ❌ | 只能用 §2.3 的档位 |
| 控件外观（按钮/输入/下拉/表格…） | ❌ | 必须用 `ui-*` 组件 |
| 层级 z-index | ❌ | 只能用 `--ui-z-*` |
| 动效时长 | ❌ | 80/140ms 两档 |
| 图标 | 部分 | 尺寸用 `--ui-icon-*`；新增图标放 `assets/ui/`，必须内联 SVG 或本地文件 |

---

## 七、落地与迁移

### 7.1 文件组织

```
styles/design-tokens.css     ← 令牌（唯一颜色入口）
styles/ui-components.css     ← 组件样式（只读令牌，不写裸色值）
js/ui-components.js          ← 组件工厂 window.GWUI
ui-showcase.html             ← 设计系统展示页（本地交互，非业务）
ui-showcase.js               ← 展示页脚本（只调 GWUI）
docs/ui-system/*.md          ← 审计 / 规范 / 组件清单
tests/test_ui_system_round.py← 静态 + 令牌一致性测试
tools/ui_accept.py           ← 真实浏览器验收（含截图、离线检查）
```

加载顺序（固定在 `index.html`）：

```html
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="theme-windows-xp.css">
<link rel="stylesheet" href="styles/design-tokens.css">   <!-- 令牌在主题之后：桥接 --xp-* 一定已定义 -->
<link rel="stylesheet" href="styles/ui-components.css">   <!-- 组件层放在最后：新组件优先于旧模块样式 -->
<link rel="stylesheet" href="calibrator.css">
<link rel="stylesheet" href="tasks.css">
<script src="js/ui-components.js"></script>
```

> `ui-components.css` 放在模块样式之前会输给模块的高特异性选择器；
> 放在之后则赢，但这正是我们要的：**组件说了算**。模块若需微调，只能改布局属性，不能改视觉属性。

### 7.2 迁移策略（渐进，不全局替换）

不采用"一次性全局替换 CSS"。顺序：

1. **新功能**：一律用 `ui-*`（本轮起生效）。
2. **试点模块**（本轮）：任务模块「商人任务中心」——工具条、卡片、表格、徽标、迁移到 `ui-*`；
   同时接入 `ui-dialog`（数据说明）与 `ui-tooltip`（模式归属）。旧类名保留作为测试钩子但不再带样式。
3. **下一批**（未执行，仅建议）：弹药页表格与两个弹窗 → 配装工作台工具条 → 配枪 → 地图左栏 → 校准器。
4. **最后**：把 `theme-windows-xp.css` 的第 12/13/14 节（自动映射/修正/终层）逐块删除，
   删一块跑一次全量测试 + 浏览器截图对比。

### 7.3 新增页面的检查清单

- [ ] 只用 `ui-*` 组件，没有新建 `.xxx-btn` 这类私有控件样式
- [ ] 没有裸十六进制色 / 裸字号 / 裸 z-index
- [ ] 每个可交互元素有可见焦点，且键盘可达
- [ ] 禁用态用 `disabled` + `aria-disabled`，不是只用透明度
- [ ] 危险操作有二次确认，确认按钮为 `--danger`
- [ ] 浮层挂 body、能被 Esc 关闭、不被父容器裁切
- [ ] 长中文文本在 1280px 宽下不溢出、不挤爆按钮
- [ ] 无外链资源（字体/图标/样式/脚本全部本地）

### 7.4 断点与密度

- 最低支持宽度 1280px；1440/1920 下同布局，只放宽弹性列。
- 不引入移动端重排；窄于 1280px 时允许横向滚动，但工具条按钮不得换行挤压。
- 高 DPI：不使用半像素字号/边框（0.5px 会渲染成 1px 或消失），统一 1px 整数。

---

## 八、版本与变更流程

- 令牌或组件行为变更 → 必须同步更新本文档 + `component-catalog.md` + 跑 `tools/ui_accept.py`。
- 新增颜色/字号档位属于**破坏性变更**，需要单独评审；不得由业务模块顺手加。
- 设计系统展示页（`ui-showcase.html`）必须始终覆盖全部组件与状态，新增组件先加展示再加使用。
