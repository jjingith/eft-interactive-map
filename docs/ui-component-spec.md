# UI 组件规范：间距 · 字号 · 对比度（可核对版）

> 适用项目：`eft-interactive-map`（Electron + 本地 Web，Windows XP 皮肤）
> 本轮基线日期：2026-11-06
> 上位文档：[design-spec.md](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/docs/ui-system/design-spec.md)（视觉体系与令牌定义）、[ui-baseline-audit.md](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/docs/ui-baseline-audit.md)（本轮只读基线，**实测数据一律以它为准**）
>
> 本文不新建第二套设计系统。本文做三件事：把已有取值**收敛成有限档位**、给出**可执行的判据**、记录**本轮改动台账**。基线审计的测量口径是「可见元素实例」，本文补充的「CSS 声明条数」只用于定位改动落点，两者不混用。
> 依据：`refactoring-ui` skill 的「留白与对比度」部分（`03-layout-spacing`、`04-typography`、`05-color`）。

---

## 0. 范围与例外

**适用**：菜单栏、工具栏、上下文栏、状态栏、左侧图层栏、任务模块、配装/配枪工作台、弹窗、提示条等「页面 UI」。

**不适用（明确例外，禁止拿来当违反规范的借口）**：

| 区域 | 例外内容 | 理由 |
|---|---|---|
| 地图画布 / SVG 地名 | 9px、10px 小字，地图内自绘标签 | 画布是独立视觉层，密度由地图几何决定 |
| `--lw-u` 响应式缩放 | `calc(8 * var(--lw-u))` 等 | 配装画布按容器比例缩放，不是固定间距 |
| 图表刻度 / 弹道坐标轴 | 9px 刻度、`1px` 网格线 | 数据可视化，文字是图形的一部分 |
| 原生控件内部 | 1px、2px 边框/描边 | 属于边框，不是留白 |

**总原则（prime directive）**：已有系统优先。本文所有档位都来自现有 `--ui-space-*` / `--ui-fs-*`，不新增令牌、不静默迁移；存量偏差分批收敛，新增代码必须按本文执行。

---

## 1. 间距阶梯

### 1.1 收敛后的有限档位

单位：px。`✓` 允许新增；`△` 仅限既有代码，新增必须映射；`✗` 禁止。

| 档位 | 令牌 | px | 用途 | 典型现有位置 | 新增 |
|---|---|---:|---|---|---|
| S0 | — | 0 | 无缝拼接：表格单元格、分段控件相邻、贴边图标 | `#context-bar` 上下、表格单元格 | ✓ |
| S1 | — | 2 | 行内微调：图标与文字、2px 分隔缝 | `.cb-pane` gap、`.sb-gap` 内部 | ✓（仅行内） |
| S2 | `--ui-space-1` / `--xp-space-1` | 4 | **块内**最小间距：标签↔值、按钮组内、徽标组 | `.tk-badges` gap、`.tk-side-block h4` margin | ✓ |
| S3 | `--ui-space-2` / `--xp-space-2` | 6 | **块内**标准间距：字段行、工具条控件间距 | `#context-bar` padding、`.app-menubar` padding、`#app-statusbar` padding | ✓ |
| S4 | `--ui-space-3` / `--xp-space-3` | 8 | **块间**：同一分组里相邻块 | `.tk-side-block` margin、面板 section 间距 | ✓ |
| S5 | `--ui-space-4` / `--xp-space-4` | 12 | **分组间**：不同 section、面板内边距、弹窗正文 | `.am-modal-body` 左右、`.lw-preset-form` 左右、`.app-menu-item` 左右 | ✓ |
| S6 | `--ui-space-5` / `--xp-space-5` | 16 | **区块间**：大分组、面板上下留白 | `.am-modal-body` 下边、页面空态 | ✓ |
| S7 | `--ui-space-7` / `--xp-space-7` | 24 | **页面级**：模态大留白、空态、跨模块分区 | 少量既有空态/弹窗 | ✓ |
| — | `--ui-space-6` / `--xp-space-6` | 20 | **历史档位，不在阶梯内** | 既有面板、列表 | ✗ 新增；见 1.3 映射 |

四类角色的取值边界：

| 角色 | 只用 | 判据 |
|---|---|---|
| 块内 | 4 / 6（行内微调可 2） | 同一控件内部，左右或上下 |
| 块间 | 8 | 同一分组内两个块的间隙 |
| 分组间 | 12 / 16 | 不同 section、不同面板 |
| 页面级 | 24 | 模态正文、空态、跨模块大分区 |

**为什么保留 2 / 4 / 6**：本项目是 34px 菜单栏、24px 状态栏的高密度桌面工具，最小结构单位是 4/6；砍到教材式 `4/8/12/16` 会让所有 XP 控件对不齐。阶梯的相邻档位增幅：2→4（100%）、4→6（50%）、6→8（33%）、8→12（50%）、12→16（33%）、16→24（50%），全部满足「相邻档 ≥25%」的可感知差。

**为什么删除 20**：16→20 只差 25%，20→24 只差 20%，三档挤在一起无法稳定区分。`20px` 作为存量保留，但不得作为新选择。

### 1.2 现状盘点（以基线审计的可见元素实例为准）

来源：[ui-baseline-audit.md §1.2](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/docs/ui-baseline-audit.md)。共 **17 个非零取值**，常规档 14 个，装饰值 3 个（22/26/42）。

| 值(px) | 实例次数 | 主要出现位置 | 本规范处理 |
|---:|---:|---|---|
| 1 | 316 | 任务小字 `margin-top`、开关 `margin-top`、菜单面板 `margin-top` | 仅允许边框/描边；作为块间距逐步并入 2/4 |
| 2 | 9 | `.menubar` gap、`.cb-pane` gap | 保留（行内档） |
| 3 | 68 | `.floor-list` gap、`.task-floors` gap | → 2 或 4 |
| 4 | 161 | `.task-list` gap、`.cb-sep` 左右 | 保留（块内档） |
| 5 | 316 | `.toggles` gap、`.cb-group` gap、`.task-row` 上下 | → 4 或 6；**最大迁移成本项**，分批做 |
| 6 | 143 | `.hud` gap、`.hud-scale` 列距、`.statusbar` 上下 | 保留（块内档） |
| 7 | 9 | `.block h2` 下、`.toggle` gap | → 8 |
| 8 | 68 | `#app-menubar` gap、`.statusbar` gap | 保留（块间档） |
| 9 | 22 | `.menu-btn` / `.app-menu-btn` 左右 | → 8 |
| 10 | 14 | `section.block` 上、任务筛选左右 | → 12（面板）或 8（控件内） |
| 11 | 12 | XP 位图按钮左右（`.hud button` 等） | → 12（按钮左右） |
| 12 | 18 | `section.block` 左右、`.statusbar` 左右 | 保留（分组档） |
| 13 | 2 | `.credits` 左右 | → 12 |
| 14 | 1 | `.credits` 下 | → 16 |
| 22 / 26 / 42 | 13 | 图例子项缩进 / 标题牌内缩 / 下拉箭头预留 | 装饰值，不参与间距阶梯 |

工程口径补充（仅用于定位源码，不与上表混算）：全部 CSS 中 `padding` 有 192 种声明组合、`margin` 104 种、`gap` 43 种。

结论：**1 / 4 / 5 / 6 是事实上的核心值**；`5px` 的 316 个实例是收敛的最大成本，不能一次性批量迁移。`16px` 令牌已定义但零引用，保留为「区块间」档，本轮未新增用例；同控件左右不对称（菜单栏 4/6、任务头 12/8）中菜单栏已按 §1.4 修正，任务头 12/8 因涉及面板头整体布局，记录为存量。

### 1.3 存量取值映射（迁移时照此执行）

| 旧值 | 新值 | 判定规则 |
|---:|---:|---|
| 1px | 1px 或 2px | 只允许边框 / 焦点环 / 分隔线；作为块间距 → 2 或 4 |
| 3px | 2px 或 4px | 行内微调 → 2；块内边距 / 标题下间距 → 4 |
| 5px | 4px 或 6px | 按钮组内 / 图标↔文字 → 4；字段行 / 工具条 → 6 |
| 7px | 8px | 块间统一归 8 |
| 9px | 8px 或 12px | 按钮左右 → 8；分组框内边距 → 12 |
| 10px | 8px 或 12px | 控件内部 → 8；面板 / 分组边距 → 12 |
| 11px | 12px | 按钮左右统一归 12（XP 位图按钮保持 5px 切片，不在此列） |
| 13px / 14px | 12px 或 16px | 面板内 → 12；页面级 → 16 |
| 20px | 16px 或 24px | 块间 → 16；页面级 / 模态 → 24 |
| 22px / 26px | 24px | 仅装饰性内缩可保留原值，否则归 24 |
| 42px | — | 只允许下拉箭头预留，不作为间距 |

### 1.4 判据（可直接 grep）

1. 同一容器内，`padding` / `margin` / `gap` 的每个方向值必须属于 `{0, 2, 4, 6, 8, 12, 16, 24}`（负值、`auto`、`calc(var(--lw-u))` 除外）。
2. 新增代码出现 `3px / 5px / 7px / 9px / 10px / 11px / 13px / 14px / 18px / 20px` 作为间距 → 失败。
3. 分组间距必须 ≥ 块内间距 × 2；同屏出现 `6px` 块内 + `6px` 分组间 → 失败。
4. 按钮 / 输入框的左右内边距用 `8px` 或 `12px`，不得出现 `0 9px`、`0 11px` 这类奇数值。
5. 同一行左右内边距必须对称（菜单栏、任务面板头、搜索区）；`22 / 26 / 42` 只允许出现在标题牌与下拉箭头的装饰性内缩。

---

## 2. 字号阶梯

字号不新增值，只用现有 `--ui-fs-*` / `--xp-fs-*`。项目有两种阅读场景，档位按场景分开定，不混用。

### 2.1 主界面（高密度）：四档

| 角色 | 令牌 | px | 行高 | 字重 | 颜色 | 用在哪 |
|---|---|---|---:|---|---:|---|---|
| 正文 / 菜单 | `--ui-fs-body` / `--xp-fs-body` | 13 | 1.5（单行控件 1.0） | 400 | `--ui-color-text` | 菜单项、开关行、面板正文 |
| 标签 / 分组标题 / 任务标题 | `--ui-fs-compact` / `--xp-fs-compact` | 12 | 1.5（单行控件 1.0） | 400 / 700 | `#000` / `#204070` | `.block h2`、图例名、任务标题、工具条按钮 |
| 辅助说明 | `--ui-fs-micro` / `--xp-fs-micro` | 11 | 1.5（密集行 1.35） | 400 | `--ui-color-text-muted` / `#69675b` | 计数、单位、状态栏、任务小字 |
| 微字（存量债，新增禁止） | — | 10 | 1.5 | 400 | `#000` / `#4a4a4a` | `.task-floor`、剧情 chip、工作台密集属性表 |

主界面名义只有 **10 / 11 / 12 / 13** 四档；13→12→11 每级只差 1px（−7.7% / −8.3%），**小于 25% 的可感知差**，所以主界面的层级不能只靠字号（见 §4）。`10px` 是存量债，新代码不得使用；空间不足时用截断或换行，不缩字。

### 2.2 弹窗 / 详情 / 工作台（大块阅读）：六档

| 角色 | 令牌 | px | 行高 | 字重 | 用在哪 |
|---|---|---:|---|---:|---|
| 页面标题 | `--ui-fs-title` / `--xp-fs-title` | 18 | 1.25 | 700 | 弹窗标题、任务详情标题、剧情标题 |
| 分组标题 | `--ui-fs-panel` / `--xp-fs-panel` | 15 | 1.25 | 700 | 弹窗 / 工作台 section 标题 |
| 强调正文 | `--ui-fs-strong` / `--xp-fs-strong` | 14 | 1.4 | 700 | 关键值、按钮主标签 |
| 正文 | `--ui-fs-body` | 13 | 1.5 | 400 | 表单正文、说明 |
| 标签 | `--ui-fs-compact` | 12 | 1.25 | 400 / 700 | 表头、字段名、徽标 |
| 辅助 | `--ui-fs-micro` | 11 | 1.5 | 400 | 单位、来源、备注 |

14 / 15 **只允许出现在弹窗、详情页、工作台**，不得回灌到主界面（主界面没有那么大块的阅读区）。

**数值**：12 或 13px、700、`font-variant-numeric: tabular-nums`。18 / 20 / 22 / 30 只能做装饰数字，不得当统计层级。

**同屏规则**：同一视觉分组内最多 **3 档**；每跨一档必须同时改变字重或颜色中的至少一项；11 与 12 不得只靠字号区分。

### 2.3 现状（基线审计实测）

名义 4 档（10 / 11 / 12 / 13），另有 2 个派生值：`10.5851`（`.emk-label`，地图缩放派生）、`10.8333`（`.task-panel-head small`，`<small>` = 0.8333em 派生）。行高只有 3 种机制：**1.0 / 1.35 / 1.5**（另有 `build-rev` 1.4、设置说明 1.55 两个个例）。字重只有 **400 / 700**，没有 500。

| 偏差 | 实测 | 处理 |
|---|---|---|
| 12px 一号五用 | 品牌、分组标题、正文标签、任务标题、按钮都用 12px | 靠字重 + 颜色分开（标题 700 + `#204070`，标签 400 + `#000` / 暖灰），不靠字号 |
| 相邻档只差 1px | 13 / 12 / 11 每级 −1px | 不接受「只差字号」的层级，必须叠加第二种手段 |
| `<small>` 派生 10.8333 | `.task-panel-head small` | 显式写 11px |
| 地图派生 10.5851 | `.emk-label` | 画布例外，随缩放动态，不收敛 |
| 10px 存量 | `.task-floor` 58 处、剧情 chip、工作台密集表 | 保留为存量债；新增 10px 即失败 |
| 半像素 8.5 / 9.5 / 10.5 / 11.5 / 12.5 / 13.5 | `tasks.css`、`style.css` 任务/工作台区 | 本轮已归整为 11 / 12 / 13；新增半像素即失败 |
| 行高 1.0 用于多行 | 个别说明文字写成 1.0 | 1.0 只允许单行按钮/标签；多行正文必须 1.35 或 1.5 |

### 2.4 判据

1. 新增 `font-size` / `font` 简写只能引用 `var(--ui-fs-*)` / `var(--xp-fs-*)`。
2. 出现 `.5px` 字号 → 失败。
3. 主界面允许 `10`（仅存量，不新增）/ `11` / `12` / `13`；弹窗、详情、工作台允许 `11 / 12 / 13 / 14 / 15 / 18`。其他值 → 失败（画布 / 图表选择器除外，必须在注释写明「画布例外」）。
4. 相邻两档若只差 1px，必须同时差字重或颜色；只差字号 → 失败。
5. 同一视觉分组内 ≤3 档；18 与 15 之间不得插 16 / 17。
6. 1.0 行高只允许单行控件；两行及以上必须 ≥1.35。

---

## 3. 对比度阈值

工具：`C:\Users\Administrator\.trae-cn\skills\refactoring-ui\scripts\check_contrast.py`（本机用 `python`，不是 `python3`）。

口径：WCAG 2.1。**正文 4.5:1**；大字 3:1 只适用于 ≥18.66px 粗体或 ≥24px。本项目页面文字为 10–13px，18px 标题也不满足「大字」条件，因此**所有文字一律按 4.5:1 验收**；渐变底按暗端、亮端各算一次；图标 / 分隔线等非文字图形按 3:1。

### 3.1 修前实测（基线审计，2026-11-06）

| # | 类别 | 前景 / 背景 | 修前 | 判定 |
|---|---|---|---:|---|
| 1 | 蓝底黑字徽标 | `#000000` / `#0058ee` → `#3d9cf5` | **3.63** / 5.12 / 7.27 | **不足**（暗端） |
| 2 | 侧栏图例名称 | `#7a766a` / `#ece9d8` | **3.72** | **不足** |
| 3 | 侧栏图例计数 | `#8d8a7d` / `#ece9d8` | **2.84** | **不足** |
| 4 | 上下文栏空槽提示 | `#77746a` / `#f4f2e6` → `#e9e6d6` | **4.16 / 3.73** | **不足** |
| 5 | 上下文栏说明 | `#6d6a5c` / `#f4f2e6` → `#e9e6d6` | 4.83 / **4.33** | 暗端边缘 |
| 6 | 禁用态（令牌 / 位图按钮 / 任务上下文项） | `#8d8d8d` / `#ece9d8`；`#8b8b80` / `#fdfdfd`；`#9a978c` | **2.72 / 3.38 / 2.91–2.93** | **不足** |
| 7 | 侧栏地名说明 `base-mode-note` | `#6d6a5c` / `#ece9d8` | **4.45** | 边缘 |
| 8 | 状态栏「定位：连接中」 | `#6a6a6a` / `#f7f5ee` → `#ece9d8` | 4.96 / **4.43** | 暗端边缘 |
| 9 | 输入占位 | `#8d8b78` / `#ffffff` | **3.44** | **不足** |
| 10 | 未选中标签 | `#6d6a5c` / `#ece9d8` | **4.45** | 边缘 |

**修前通过的主要项**：正文 17.21、次要文字 7.26、链接 4.69、选中反白 5.25、状态栏正文 11.58 / 10.36、菜单 20.09 / 17.21、工具栏 15.55 / 11.98、上下文栏标签 6.43 / 5.77、侧栏分组标题 8.48、任务正文 8.86、剧情绿 5.31、任务徽标 17.90 / 16.24、状态徽标 8.46 / 6.75 / 5.92 / 6.46 / 6.96、标题栏反白 9.47。

**两处不改的已知限制**（画布 / 材质，不属本轮范围）：

| 项 | 实测 | 说明 |
|---|---|---|
| 地名字 `#b9c0cb` 对深底 | 4.91–11.47 | 通过 |
| 地名字 `#b9c0cb` 对浅底 | **1.04–1.24** | 完全依赖 `rgba(8,10,12,.85)` 描边勾边；描边是文字的一部分，实际可读，保持不改 |
| HUD 主按钮白字 | **2.83**（顶缘）/ 5.24（中段）/ 9.47 | 文字实际落在渐变中段；不改按钮材质，记录为已知限制 |

### 3.2 修后复测（脚本实测，17 组配对全部通过，下表按类别合并）

| 类别 | 新前景 / 背景 | 修前 → 修后 | 判定 |
|---|---|---|---:|---|
| 蓝底黑字徽标（暗端） | `#000000` / `#1a6ff5` | 3.63 → **4.64** | 通过 |
| 蓝底黑字徽标（亮端） | `#000000` / `#3d9cf5` | 7.27 → 7.27 | 通过 |
| 侧栏图例名称 | `#6b675c` / `#ece9d8` | 3.72 → **4.63** | 通过 |
| 侧栏图例计数 | `#69675b` / `#ece9d8` | 2.84 → **4.66** | 通过 |
| 上下文栏空槽（亮 / 暗端） | `#69675b` / `#f4f2e6`、`#e9e6d6` | 4.16 / 3.73 → **5.06 / 4.54** | 通过 |
| 上下文栏说明（暗端） | `#646152` / `#e9e6d6` | 4.33 → **4.97** | 通过 |
| 输入占位 | `#6f6d5c` / `#ffffff` | 3.44 → **5.23** | 通过 |
| 未选中标签 | `#646152` / `#ece9d8` | 4.45 → **5.10** | 通过 |
| 状态栏「连接中」暗 / 亮端 | `#646152` / `#ece9d8`、`#f7f5ee` | 4.43 / 4.96 → **5.10 / 5.71** | 通过 |
| 禁用态（米色面 / 凹陷面） | `#69675b` / `#ece9d8`、`#f2f0e6` | 2.72 → **4.66 / 4.98** | 通过 |
| 禁用态（位图按钮面） | `#69675b` / `#fdfdfd` | 3.38 → **5.59** | 通过 |
| 禁用菜单项 | `#69675b` / `#ffffff` | 2.91 → **5.69** | 通过 |
| 侧栏地名说明 | `#646152` / `#ece9d8` | 4.45 → **5.10** | 通过 |
| 图表描边（非文字） | `#7a766a` / `#ffffff` | 4.54 | 通过（≥3:1） |

### 3.3 判据

1. 每个「文字 / 背景」对必须用脚本实测，不得凭肉眼或设计稿判定。
2. 正文、次要、禁用、占位、标签、状态栏、徽标一律 ≥4.5:1。
3. 禁用态允许比次要文字浅，但不得低于 4.5:1；「看起来像禁用」靠边框 / 底板 / 光标，不靠把字调灰。
4. 蓝底 / 深色底上的文字优先「提亮底色」，而不是把文字改成白色（保留品牌色相）。
5. 状态色（成功 / 警告 / 危险 / 信息）必须「深色字 + 浅色底」，不得深底白字小字。
6. 渐变底必须两端都算；只报一个平均值不算通过。
7. 次要文字只允许 3 级灰：`#000000`、`#4a4a4a`、`#69675b`；`#6a6a6a`、`#77746a`、`#7a766a`、`#8d8a7d`、`#8b8b80` 为存量，禁止新增。

复测命令（把 3.2 的配对写成 matrix JSON 后执行）：

```powershell
python "C:\Users\Administrator\.trae-cn\skills\refactoring-ui\scripts\check_contrast.py" --matrix "C:\path\to\pairs.json"
```

单对快速检查：

```powershell
python "C:\Users\Administrator\.trae-cn\skills\refactoring-ui\scripts\check_contrast.py" --pair "#69675b" "#ece9d8" --size normal
```

---

## 4. 层级手段

基线审计结论：现状**主要靠颜色深浅**分层——字号每级只差 1px、字重只有 400/700、缩进只在图例子项一处，近灰五色（`#4a4a4a` / `#6a6a6a` / `#77746a` / `#7a766a` / `#8d8a7d`）彼此过近，导致「标签 / 计数 / 辅助」三层容易糊成一层。

本规范把可用手段收成 5 种，**每级至少用 2 种**：

| 手段 | 允许的取值 | 量化差 | 用在哪 |
|---|---|---|---|
| 1 字号 | 主界面 13 / 12 / 11；大块 18 / 15 / 14 / 13 / 12 / 11 | 主界面每档 1px（−7.7% ~ −8.3%，小于 25%）**必须叠加别的**；大块 18→15→13 为跳档 | 标题、正文、辅助 |
| 2 字重 | 400 / 700（二元） | 同字号下 700 vs 400 | 标题 vs 正文 |
| 3 文字明度 | 只有 3 级：`#000`（17.21）/ `#4a4a4a`（7.26）/ `#69675b`（4.66） | 亮度比例 17.2 / 7.3 / 4.7 | 所有文字 |
| 4 面 / 边框 | 凸 `#fff→#f1efe4`、平 `#ece9d8`、凹 `#f2f0e6`；外 1px `#aca899` + 内 1px `#fff` | 面明度差 ≥3 L*；边框 1px（焦点 2px） | 按钮、输入框、分组框、状态栏格 |
| 5 留白 / 缩进 | 块内 4/6、块间 8、分组 12/16、页 24；缩进 0 / 8 / 12 / 22 | 分组间 ≥ 块内 ×2 | 面板、列表、图例子项 |

**四级定义（主界面）**：

| 级 | 代表元素 | 实际组合 | 与下一级的差 |
|---|---|---|---|
| L1 品牌 / 视图标题 | `.app-brand h1`、`.task-panel-head h2` | 12–13 + 700 + 蓝底 / 位图牌 + 34–53px 条 | 与 L2：底色 / 位图 + 位置（2 种） |
| L2 分组标题 | `.block h2`、`.legend-group-title` | 11–12 + 700 + `#204070` + 分组框 + 下方 1px 分隔线 | 与 L3：字重 700→400 + 颜色蓝→黑（2 种） |
| L3 正文 / 标签 | `.toggle` 13/400/`#000`；`.legend-name` 12/400/`#000` | 字号 13–12 + 400 + `#000` + 块内留白 4/6 | 与 L4：字号 −1 + 颜色黑→`#4a4a4a`（2 种） |
| L4 辅助 / 计数 | `.legend-count`、状态栏次要项、任务小字 | 11 + 400 + `#4a4a4a` 或 `#69675b` + 1.35 行高 | — |

**规则**：

1. 相邻两级至少 **2 种**手段不同（字号 / 字重 / 颜色 / 面 / 留白中选 2）；只换颜色 → 失败。
2. 文字只有 3 级；需要第 4 级时改用字号、字重、留白或缩进，**不得再加灰**。
3. 禁止新增近灰；`#6a6a6a`、`#77746a`、`#7a766a`、`#8d8a7d`、`#8b8b80` 只作为存量，新代码必须映射到三级之一。
4. 同屏最多 4 级（L1–L4）；更多就拆面板或加分组框，不继续加层级。
5. 图例子项缩进固定 22px；其他缩进只用 8 / 12，不新造 10 / 13 / 14。
6. 品牌 / 蓝底是最高层级，必须同时满足 ≥4.5:1（本轮 3.63→4.64），不得再出现「层级最高、对比最低」。
7. 选中态 = 底色 + 反白字，且 ≥4.5:1；悬停只可变底色，文字对比不得低于 4.5:1。

---

## 5. 验收清单

| # | 检查 | 通过标准 |
|---|---|---|
| 1 | 新增样式的间距值 | 只出现 `0/2/4/6/8/12/16/24`（或 `--ui-space-*`）；窄屏压缩档除外 |
| 2 | 新增样式的字号 | 只引用 `--ui-fs-*` / `--xp-fs-*`，无半像素，主界面无新增 10px |
| 3 | 对比度 | 3.2 全部 ≥4.5:1（脚本实测，不得肉眼判断） |
| 4 | 层级 | 任意相邻两级至少 2 种手段不同；文字灰 ≤3 级 |
| 5 | 855px 窄屏 | 菜单栏 / 上下文栏无横向溢出，不出现新滚动条 |
| 6 | `?mini=1` | 小地图路径零影响（不得命中 `body.tk-mini` / `.tk-mini-root`） |
| 7 | 全量测试 | `python -m pytest tests -q` 全绿 |
| 8 | 回退 | 台账每条可单独回退；不含 DOM / 交互 / 数据流改动 |

---

## 6. 本轮视觉收口台账

原则：只改间距、字号、颜色明度；不改 DOM、不改交互、不改数据流；每条可单独回退。

### 6.1 颜色明度（对比度）

| # | 文件 / 位置 | 改前 → 改后 | 依据 |
|---|---|---|---|
| 1 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L583) `.app-brand` 渐变起点 | `#0058ee → #1a6ff5` | §3.2 3.63→4.64 |
| 2 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L203) `#search::placeholder` | `#8d8b78 → #6f6d5c` | §3.2 3.44→5.23 |
| 3 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L959) `.cb-empty` | `#77746a → #69675b` | §3.2 4.16/3.73→5.06/4.54 |
| 4 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L334) 未选中 tab、上下文说明 | `#6d6a5c → #646152` | §3.2 4.45/4.33→5.10/4.97 |
| 5 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L98) 位图禁用按钮文字 | `#8b8b80 → #69675b` | §3.2 3.38→5.59 |
| 6 | [xp-ui.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui.css#L11) `--xp-ink-dim` | `#8b8b80 → #69675b` | §3.3-7 三级灰 |
| 7 | [xp-ui.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui.css#L409) `.xp-tab` 文字 | `#6d6a5c → #646152` | §3.2 4.45→5.10 |
| 8 | [theme-windows-xp.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/theme-windows-xp.css#L51) `--xp-btn-disabled-text` | `#8d8d8d → #69675b` | §3.2 2.72→4.66 |
| 9 | [theme-windows-xp.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/theme-windows-xp.css#L733) `.statusbar .pos-off` | `#6a6a6a → #646152` | §3.2 4.43→5.71 |
| 10 | [theme-windows-xp.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/theme-windows-xp.css#L1623) 图例关态 `.legend-name` | `#7a766a → #6b675c` | §3.2 3.72→4.63 |
| 11 | [theme-windows-xp.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/theme-windows-xp.css#L1627) 图例关态 `.legend-count` | `#8d8a7d → #69675b` | §3.2 2.84→4.66 |
| 12 | [theme-windows-xp.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/theme-windows-xp.css#L1591) 弹药散点描边 | `#8d8a7d → #7a766a` | §3.2 4.54（非文字 ≥3:1） |
| 13 | [style.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/style.css#L542) `.task-context-item:disabled` | `#9a978c → #69675b` | §3.2 2.91→5.69 |
| 14 | [design-tokens.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/styles/design-tokens.css#L45) `--ui-color-text-disabled` 回退值 | `#8d8d8d → #69675b` | §3.2 禁用态统一 |
| 15 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L998) `.db4-search::placeholder` 回退值 | `#8d8d8d → #69675b` | §3.2 占位统一 |

### 6.2 间距

| # | 文件 / 位置 | 改前 → 改后 | 依据 |
|---|---|---|---|
| 16 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L566) `.app-menubar` 内边距 | `0 6px 0 4px → 0 6px` | §1.4-5 左右对称 |
| 17 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L621) `.app-menu-btn` | `0 9px → 0 8px` | §1.3 9→8 |
| 18 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L730) `.app-account-btn` | `0 9px → 0 8px` | §1.3 9→8 |
| 19 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L124) 弹药工作台工具按钮 | `0 9px → 0 8px` | §1.3 9→8 |
| 20 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L640) `.app-menu-panel` | `3px → 4px` | §1.3 3→4 |
| 21 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L649) `.app-menu-item` | 内边距 `4px 10px 4px 22px → 4px 12px 4px 24px`；gap `10px → 8px` | §1.3 10→12、22→24；gap 归 8 |
| 22 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L940) `.cb-group` / `.cb-src-block` | gap `5px → 6px` | §1.3 5→6 |
| 23 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L842) 视图按钮、楼层开关 | gap `5px → 4px` | §1.3 5→4（图标↔文字） |
| 24 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L1197) `.sb-cell` | `0 5px → 0 6px` | §1.3 5→6 |
| 25 | [xp-ui-app.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/assets/xp-ui/xp-ui-app.css#L288) `.panel section.block` | `10px 12px 12px → 12px` | §1.3 10→12 |
| 26 | [style.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/style.css#L616) `.block`；`.block h2` 下距 | `10px 12px 13px → 10px 12px`；`7px → 8px` | §1.3 13→12、7→8 |
| 27 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L309) `.tk-side-title`；`.tk-h3` / `.tk-h4` | 下距 `3px → 4px`；h3 `padding-bottom 0 → 4px`；h4 `margin → 8px 0 4px` | §1.3 3→4；块间 8 |
| 28 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L1289) `.tk-story-main` | 下内边距 `28px → 24px`，左右 `16px` 保持 | §1.3 页面级 24 |

### 6.3 字号

| # | 文件 / 位置 | 改前 → 改后 | 依据 |
|---|---|---|---|
| 29 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L225) `.tk-node-name` | `11.5 → 12` | §2.4-2 半像素 |
| 30 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L309) `.tk-side-title` | `13.5 → 13` | §2.4-2 |
| 31 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L312) `.tk-badge` | `11.5 → 11` | §2.4-2 |
| 32 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L365) `.tk-trader-counts` | `11.5 → 11` | §2.4-2 |
| 33 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L412) `.tk-detail-title` | `17 → 18` | §2.2 页面标题 |
| 34 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L416) `.tk-detail-status-label` | `11.5 → 11` | §2.4-2 |
| 35 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L544) `.tk-sumcard-x` | `11.5 → 11` | §2.4-2 |
| 36 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L576) `.tk-h3` | `13.5 → 13` | §2.4-2 |
| 37 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L580) `.tk-h4` | `11.5 → 12` | §2.4-2 |
| 38 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L607) `.tk-cond-kind` | `11.5 → 11` | §2.4-2 |
| 39 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L652) `.tk-card-num` | `20 → 18` | §2.2 数值不用 20 |
| 40 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L653) `.tk-card-label` | `11.5 → 12` | §2.4-2 |
| 41 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L658) `.tk-group-title` | `11.5 → 12` | §2.4-2 |
| 42 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L1291) `.tk-story-title h3` | `17 → 18` | §2.2 页面标题 |
| 43 | [tasks.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/tasks.css#L1044) `db4` 子树（名称 / 英文 / 徽标 / 经验 / 分段 / 标签 / 导航） | `8.5 / 9.5 / 10.5 / 11.5 → 11 / 12` | §2.4-2、§2.1 微字存量归 11 |
| 44 | [style.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/style.css#L4512) `.am-sim-ztitle` | `11.5 → 12` | §2.4-2 |
| 45 | [style.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/style.css#L7441) `.price-source-badge` | `10.5 → 11` | §2.4-2 |
| 46 | [style.css](file:///d:/personal/trae/02-%E5%A1%94%E7%A7%91%E5%A4%AB/eft-interactive-map/style.css#L7576) `.acc-alias / .acc-perks / .acc-none / .acc-channel` | `10.5 → 11` | §2.4-2 |

### 6.4 明确保留（存量债与例外）

| 项 | 数量 / 位置 | 为什么不改 |
|---|---|---|
| 5px 间距 | 316 个可见实例（`.task-row` 上下、`.task-row-head` gap 等） | 统一会改变 54 行任务列表的总高，牵连滚动位置；分批做，本轮不动 |
| 1px 间距 | 316 个实例（任务小字 `margin-top`、开关 `margin-top`） | 作为「缝 / 描边」使用，允许保留；只有作为块间距时才并入 2/4 |
| 工作台 8 / 8.5 / 9 / 10px | `style.css` 配枪 / 配装 / 弹药密集属性表 | 密度由表格列宽决定，属独立数据区；本轮不动 |
| 地图 9 / 10px、`.emk-label` 10.5851 | 地图画布 | 画布例外，随缩放动态 |
| 地名浅底 1.04–1.24、HUD 顶缘 2.83 | 地图 / HUD | 依赖描边与渐变材质，已知限制 |
| ≤900px 压缩档 | `.app-menubar` gap 5、`.app-menu-btn` 7、`#build-rev` 5 / 10px | 为 855px fit 服务，非常规阶梯；改动会横溢 |
| `#app-menubar-right` 的 `margin-left: auto` | 菜单栏 | 非设计值，是实现手段 |

### 6.5 验证记录

| 项 | 结果 |
|---|---|
| `python -m pytest tests -q` | **1767 passed, 1 skipped**（93.73s） |
| 1280 宽 | 菜单栏 34 / 上下文栏 36 / 状态栏 24；`docOverflow` 0 |
| 855 宽 | 同一组高度；无横向滚动条 |
| `?mini=1` | 仅地图视图；`#app-menubar` / `#context-bar` / `.app-brand` 均 0×0 |
| 控制台 | 0 错误 |
| 对比度脚本 | 17 / 17 通过（见 §3.2） |

> 台账每条独立可回退：颜色条目只改一个十六进制值；间距条目只改单个 `padding` / `gap` 的数值；字号条目只改一个 `font-size`。均不涉及选择器结构、DOM、事件或数据。

