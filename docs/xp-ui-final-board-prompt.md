# XP UI 最后一板 · 4K 合体生图（提示词 + 坐标表）

> 本轮只产出文档：**不生成图片、不改代码、不提交**。提示词正文可直接整段复制给生图模型。
> 板子沿用上一份 `docs/xp-ui-missing-board-prompt.md` 的写法与禁止项，只改三处口径：**8x 倍数**、
> **键色 #E815EF**、**19 件**。缺口编号接着 `docs/xp-ui-missing-components.md` 的 M 序列，从 M9 起排。
>
> 审计口径：8791 端口实跑，page 1 五视图（地图 / 任务 / 弹药 / 枪匠 / 配装）+ 属性弹窗 / 预设弹窗 /
> 弹药详情；gun、任务、剧情三张详情卡点击后容器未展开（`#gs-detail/#detail/#tk-detail` 均 0×0），
> 只能取容器级样式（transparent / radius 0 / 无阴影），内容级样式未取样，下文相应条目已注明。

---

## 0. 本板口径

| 项 | 取值 | 说明 |
|---|---|---|
| 画布 | **3840 × 2160** 横向 | 单张 4K |
| 绘制倍数 | **8x**（1 逻辑 px = 8×8 源 px） | 最大件 `current-gun-plate` 1x 288 → 2304 ≤ 3200；全部 1x 尺寸均为整数，×8 后可整除 |
| 键色 | **#E815EF = RGB(232, 21, 239)** | 沿用上一板同源实测值，本板不重新采样，避免漂色 |
| 四边留白 | ≥160 px 纯键色 | 实测表内最小左/上边距 160 |
| 元素间距 | ≥128 px 纯键色 | 全表最小间距 128（上一板 64） |
| 件数 | **19** | 见 §1；含 3 件一致性帧（M9 / M12 / M13） |
| 文字 | 全图零文字、零数字、零 logo | 版本号 / 应用名 / 枪名均由 CSS 叠字 |
| 状态 | 多态件同板、同几何 | 箭头 2 态、横向滑块 3 态 |
| 硬边 | 只允许矩形内部的 1 逻辑 px 硬线 | 无外投影、无外发光、无柔边 |

---

## 1. 剩余缺口（M9–M27）

### 1.1 主表

| # | 件名（落盘名） | 1x 尺寸 | 用途 | 落点选择器 | 来源 / 备注 |
|---|---|---|---|---|---|
| M9 | `scroll-v-arrow-down-normal` | **22×27** | 纵向滚动条下箭头**常态**底板（空面，三角由同板烘焙） | `::-webkit-scrollbar-button:vertical:end:increment` 及 6 个容器限定选择器（`.db4-scroll` / `.db4-rail` / `.tbl-scroll` / `.am-side` / `.lw-side` / `.am-sim-cfg`） | 与 M10 成套；接入时撤掉 `scroll-v-glyph-down.png` 叠层 |
| M10 | `scroll-v-arrow-down-hover` | **22×27** | 下箭头 hover（只改高光，三角 15×10、距顶 9，与 M9 逐像素同形） | 同上 `:hover` 分支 | 重画 R93 未采纳件（原因为烘焙三角缩到 11×9） |
| M11 | `scroll-h-thumb` | **44×21** | 横向滚动条滑块**常态** | `::-webkit-scrollbar-thumb:horizontal` | R93 新常态偏厚，未采纳 |
| M12 | `scroll-h-thumb-hover` | 44×21 | 横向滑块 hover（一致性对照帧） | `::-webkit-scrollbar-thumb:horizontal:hover` | 与 M11/M13 同板同几何，一次性成套替换 |
| M13 | `scroll-h-thumb-pressed` | 44×21 | 横向滑块 pressed（一致性对照帧） | `::-webkit-scrollbar-thumb:horizontal:active` | 同上 |
| M14 | `version-plate` | **136×22** | 版本牌（替换 `statusbar-cell.png` 凹槽白格） | `#build-rev.build-rev`、`.tk-build` | 实测 `.build-rev` 134.5×19.2 |
| M15 | `brand-plate` | **120×31** | 应用品牌牌（替换 `plaque-3.png` 183×39 压到 121×31） | `#app-brand.app-brand` | 实测 121.1×31 |
| M16 | `current-gun-plate` | **288×32** | 枪匠顶部「当前配枪」状态条（替换 `plaque-3.png`） | `.gun-workbench #gw-current` | 实测 291×33；9-slice 边 5 / 左 14 |
| M17 | `table-frame` | **64×64** | 表格滚区外框（替换 `groupbox.png` 套框） | `.loadout-workbench .tbl-scroll`、`.gun-workbench .tbl-scroll`、`.am-workbench .am-table .tbl-scroll` | 2px 凹槽 / 切片 2，边框宽度保持 2px 不改布局 |
| M18 | `empty-task` | **48×48** | 任务空态插图（替换通用 `empty-box.png`） | `.task-list > .task-empty::before` | 墨色象形，无底板 |
| M19 | `empty-story` | **48×48** | 剧情空态插图 | `#tk-story-list .tk-story-empty::before` | 同上 |
| M20 | `empty-gun` | **48×48** | 枪匠空态 / 加载态插图 | `#gw-browse .lw-loading::before` | 同上 |
| M21 | `sep-horizontal` | **64×2** | 菜单 / 右键菜单分隔线（上 `#ACA899`、下 `#FFFFFF`） | `.menu-panel section + section::before`；`.task-context-item + .task-context-item::before` | 纯 `::before` 承载，**不动 DOM**（结 D1 / D2） |
| M22 | `sep-vertical` | **2×22** | 状态栏格间竖分隔（左 `#ACA899`、右 `#FFFFFF`） | `#app-statusbar .sb-cell + .sb-cell` 左边框 `border-image` | 纯 CSS 承载，**不动 DOM**（结 D3） |
| M23 | `icon-map` | **16×16** | 视图图标（替换内联 SVG） | `#view-btn-map .vt-ico` | 透明无底板 |
| M24 | `icon-tasks` | 16×16 | 视图图标 | `#view-btn-tasks .vt-ico` | 同上 |
| M25 | `icon-ammo` | 16×16 | 视图图标 | `#view-btn-ammo .vt-ico` | 同上 |
| M26 | `icon-gun` | 16×16 | 视图图标 | `#view-btn-gun .vt-ico` | 同上 |
| M27 | `icon-loadout` | 16×16 | 视图图标 | `#view-btn-loadout .vt-ico` | 同上 |

> 落盘统一放 `assets/xp-ui/`，命名与上表一致；`.vt-ico` 当前是 `span > svg`，接入时用
> `.vt-ico { background: url(...) no-repeat center / 16px 16px; }` + `.vt-ico > svg { display: none; }`，
> 属 CSS 覆盖，不改 DOM、不改类名。

### 1.2 M1 / M2 复核（与 R93 结论的差异）

**M1（下箭头 hover）** 实测证据：

- `scroll-v-arrow-down.png`（22×27）内部**烘焙**了一枚 11×9 三角，墨色顶边在 **y=9**。
- `scroll-v-glyph-down.png` 画布 20×11，**ink 实测 16×11**（x=4–19，y=0–10）；CSS 用 `background-size: 20px 11px`、`background-position: center 8px`。
- 两件叠在一起，实际可见三角是 **16×11 / 距顶 8**，且底板那枚 11×9 是被 glyph 盖住的重复件。
- 结论：规格要求「15×10 / 距顶 9」**并未达成**，R93 新件（11×9 / 54px）偏离更大。
  → 本板重画 M9（常态）+ M10（hover）两态，三角同板烘焙；接入时去掉 glyph 叠层，避免双三角。

`docs/xp-ui-missing-components.md` §1.1 里「现有 glyph 是 15×10 / 67px」一句为旧记录，
按本轮实测**更正为画布 20×11、ink 16×11**（见 §5 更新）。

**M2（横向滑块常态）** 实测三态中心列扫描：

| 文件 | 深色行（y） | 浅色行（y） |
|---|---|---|
| `scroll-h-thumb.png` | `[20]` | `[1, 2]` |
| `scroll-h-thumb-hover.png` | `[0, 20]` | `[2]` |
| `scroll-h-thumb-pressed.png` | `[0, 19, 20]` | `[]` |

- 常态**顶边没有**深线，hover / pressed 有 → 三态边框权重本来就不同；
- 因此「只换常态」必然继续不一致，M11+M12+M13 同板成套重画，才是真正一致的解法。

### 1.3 「DOM 限制」「语义不宜换」两类的重新判定

| 原编号 | 结论 | 依据 |
|---|---|---|
| D1 菜单面板分隔线 | **可用素材解决**（M21） | 相邻 `section` 各挂一个 `::before`，不插入元素、不遮挡点击 |
| D2 右键菜单分隔线 | **可用素材解决**（M21） | `.task-context-menu` 只有 `.task-context-item` 两个按钮，用 `+ ::before` 即可 |
| D3 状态栏分隔线 | **可用素材解决**（M22） | `.sb-cell` 已有左边框，用 `border-image` 换皮即可，**无需增列** |
| D4 原生下拉展开列表 | 仍无解 | `option` 列表由 OS 绘制 |
| D5 数字微调箭头 | 仍无解（可 CSS 隐藏） | `input[type=number]` 全站 30 个，箭头不可换皮 |
| D6 系统 tooltip | 不属位图 | 3564 个 `title` |
| D7 浏览器右键菜单 | 仍无解 | 需接管 `contextmenu` |
| §三 图例色点 / 剧情状态点 / 材质签 / 口径块 | **不做素材** | 颜色即语义；只做 CSS 方形化、去圆角、统一 1px 边 |
| §三 枪械照片 / 地图画布 | **保留** | 内容本身，不是控件 |

---

## 2. 风格审计（S1–S19，实测，并非印象）

> 判定来源：`getComputedStyle` 全量扫描 + 逐视图截图目视。只记录「确实不合 Luna」的项；
> 符合的一律不列。`border-radius` / `box-shadow` / 渐变 / 半透明 / 深色 / 色相 / 原生外观 / 字模 / 字号九类。

| # | 位置（视图 / 选择器） | 当前是什么（实测） | 为什么不符 | 做素材？ | 尺寸 / 动作 |
|---|---|---|---|---|---|
| S1 | 五视图通用：`button.task-floor`×58、`.task-main`×54、`.gw-card`×163、`button.am-chip`×32、`.am-seg-btn`×9、`.am-show`×5、`.gw-chip`×12、`.gw-mode`×4、`.lw-cell`×11、`.lw-cat`×7、`.lw-sortbtn`×5、`.gw-calblock`×30、`.lw-mat-chip`×39、`.lw-board`/`.lw-deco`/`.lw-block`/`.lw-cost`、`input.search`/`select.ui-select` | `border-radius: 2px` 或 `3px` | Luna 控件是直角，圆角属现代 UI | **否** | CSS：`border-radius: 0` |
| S2 | 地图 `span.dot.dot-task`×2、任务 `span.tk-story-dot`×38 | `border-radius: 50%`（恒为圆） | 圆点不是 XP 控件语汇 | **否** | `border-radius: 0`（方形色块 8×8 / 12×12），颜色保留 |
| S3 | 属性弹窗 `div.gw-prof-box`；预设 `div.lw-modal-box.lw-preset-box`；弹药详情 `div.am-modal-box` | `rgba(0,0,0,.35) 0 8 28` / `.6 0 6 26` / `.34 2 2 10` 柔和外阴影 | XP 只有 2px 硬边（已由 `dialog-box` 九宫格提供） | **否** | `box-shadow: none` |
| S4 | 弹药详情 `header.am-modal-head` | 平滑三段蓝渐变 + `rgba(255,255,255,.35)` 高光 + 3px 圆角 | 平滑过渡与圆角都不是 Luna 标题栏 | 否（可选复用 `dialog-head.png`） | 圆角 0；渐变改 3 段硬色标（`#0A3F9E/#1466E0/#4A9BFF`） |
| S5 | 属性弹窗 `button.gw-prof-x`、弹药详情 `button.am-modal-x` | 红色三段渐变 + 3px 圆角 + 白 inset | XP 关钮直角、两段硬色 | **否** | 圆角 0；色标改 2 段 |
| S6 | 预设弹窗 `button.lw-modal-btn`×8、`.lw-preset-row`×6 | 米色渐变 `#FDFDFD→#F1EFE4` + 3px 圆角 | 米色渐变本身合规，圆角不合规 | **否** | 圆角 0 |
| S7 | 配装 `span.lw-cell-label`×9、`span.lw-cell-name`×2 | `rgba(255,255,255,.88)` / `.86` 半透明白底 | 玻璃感 | **否** | 改实色 `#ECE9D8` + `1px #ACA899` |
| S8 | 弹药详情外层 `#am-detail` | `rgba(10,20,40,.45)` 蓝黑遮罩 | 半透明 + 非 Luna 色 | 否（模态遮罩例外） | 改 `rgba(0,0,0,.28)`，禁用 blur |
| S9 | 地图图例 `span.dot.dot-floor`、`legend-ico.dot-hazard`、`span.dot.dot-artillery` | 黄绿 `rgb(198,209,138)` h69 / 红 `rgb(224,108,108)` h0 / 橙 `rgb(177,84,63)` h11 | 三色均不在 Luna 允许范围 | **否**（语义色） | 方形化 + 明度压到 ≤60%，加 1px `#ACA899` 边 |
| S10 | 任务 `span.tk-story-dot`×38（24×24） | 圆形 + 文本 `▶`（由 `tasks.js` 写入） | 圆 + 字模 | **否**（`▶` 在文本节点里，CSS 换不掉） | 方形化；`▶` 保留 |
| S11 | 任务 `span.tk-story-chip`×17、配装 `span.lw-mat-chip`×39 | 紫 `rgb(155,123,179)` h274 等色签 + 2px 圆角 | 紫 / 橄榄属允许色相，圆角与饱和度不符 | **否** | 圆角 0；饱和度 −15% |
| S12 | 枪匠 `div.gw-calblock`×30（40×95） | 直角色条，但配套图例点是圆的（h115 绿 / h0 红 / h257 紫） | 图例点形状与控件语汇不符 | **否** | 只改图例点形状，色条保留 |
| S13 | 全站 30 个 `input[type=number]`（属性弹窗 15 / 弹药 6 / 配装 5 / 枪匠 1 / 其余 3） | 原生上下微调箭头可见 | 浏览器绘制 | **否** | `appearance: none`（滚轮 / 键盘仍可用），或接受现状 |
| S14 | 全站 15 个 `select` 的展开列表 | `option` 列表 OS 绘制 | 无法换皮 | **否** | 见 D4，保留 |
| S15 | 五视图 `.view-btn .vt-ico` 5 个内联 `<svg 16×16>` | 现代扁平矢量（含绿勾 / 铜弹 / 砖红点） | 与 Luna 图标语汇不符 | **是** | **M23–M27，16×16，透明无底板** |
| S16 | 弹药表 `.tbl-cell` 文案 `⛔ 不可装`（6 处）、枪匠 `✕`（Streamer / Silent / Loud / 分享 4 处）、地图 `legend-group-arrow` 的 `▾`×8 | 字符当图标 | 字模边缘随字体变化，不是像素件 | 否（`⛔`/`✕` 在文本节点内） | `▾` 用 CSS 三角（三边 transparent + 上边框着色）；`⛔`/`✕` 改文案（数据侧） |
| S17 | `i.gw-card-cal`/`b.gw-card-badge`/`span.gw-card-fig`/`i.gw-calblock-n`×163、`i.gw-badge-new`、`span.lw-cell-name`、`span.lw-at-badge` | 8px / 9px | 低于 10px 下限 | **否** | 提到 10px |
| S18 | `input`×53 = 13.3333px、`text`×24 = 10.5851px、`h3.am-h3` 15.21px、`h3.lw-h3` 15px、`h2.tk-title` 15px、`h3` 18px | 非 10/11/12/13 | 字号刻度外 | **否** | 归一到 12 / 13 |
| S19 | 表格表头 `span.tbl-sort` 的 `▲ / ▼` | 字符 | 记录项：XP 列表头本来就用三角符号 | 否 | 保留（与 S16 分开记） |

**小结**：风格不符 **19 条**；其中需要位图的只有 **S15 一条 / 5 件**（M23–M27），其余 18 条全是 CSS 或数据侧改动。

**零命中与未取样（避免只报坏消息造成误判）**

- 深色底板：**零命中**。`section.view-pane.lw-scope` 实测 `rgb(236, 233, 216)`（枪匠 / 配装 / 弹药一致），
  浮层也全是米色；只有 `main#stage` 地图画布是刻意深色，属内容而非控件，保留。
- 玻璃容器：**零命中**；只有 S7 两处文字底是半透明白。
- 原生 checkbox（117）/ radio（4）/ select 收起态（15）：已被 R93 位图覆盖，未发现浏览器默认外观。
- 未取样：`#gs-detail`（配枪详情）、`#detail`（任务详情）、`#tk-detail`（剧情详情）点击后高度仍为 0，
  只取到容器级样式（transparent / radius 0 / 无阴影）；内容级样式需下一轮用真实指针事件复核。

---

## 3. 板面分配

### 3.1 为什么是 8x

- 最大件 `current-gun-plate` 1x 宽 288 → 8x = 2304，离 3200 上限还有 896 余量；
- 若上 16x 就是 4608，超出 3840 画布；
- 全部 1x 尺寸（22/27、44/21、136/22、120/31、288/32、64/64、48/48、64/2、2/22、16/16）都是整数，
  ×8 后每个源边都是 8 的倍数，1/8 盒式降采样可得到**零抗锯齿**的 1x 像素。

### 3.2 坐标表（3840×2160，源像素）

| name | x | y | w | h | 1x |
|---|---|---|---|---|---|
| current-gun-plate | 160 | 160 | 2304 | 256 | 288×32 |
| version-plate | 2592 | 160 | 1088 | 176 | 136×22 |
| brand-plate | 160 | 544 | 960 | 248 | 120×31 |
| table-frame | 1248 | 544 | 512 | 512 | 64×64 |
| empty-task | 1888 | 544 | 384 | 384 | 48×48 |
| empty-story | 2400 | 544 | 384 | 384 | 48×48 |
| empty-gun | 2912 | 544 | 384 | 384 | 48×48 |
| scroll-v-arrow-down-normal | 160 | 1184 | 176 | 216 | 22×27 |
| scroll-v-arrow-down-hover | 464 | 1184 | 176 | 216 | 22×27 |
| sep-horizontal | 768 | 1184 | 512 | 16 | 64×2 |
| sep-vertical | 1408 | 1184 | 16 | 176 | 2×22 |
| icon-map | 1552 | 1184 | 128 | 128 | 16×16 |
| icon-tasks | 1808 | 1184 | 128 | 128 | 16×16 |
| icon-ammo | 2064 | 1184 | 128 | 128 | 16×16 |
| icon-gun | 2320 | 1184 | 128 | 128 | 16×16 |
| icon-loadout | 2576 | 1184 | 128 | 128 | 16×16 |
| scroll-h-thumb | 160 | 1528 | 352 | 168 | 44×21 |
| scroll-h-thumb-hover | 640 | 1528 | 352 | 168 | 44×21 |
| scroll-h-thumb-pressed | 1120 | 1528 | 352 | 168 | 44×21 |

**边距 / 间距核对**

- 左 160、上 160、右 `3840-3680=160`、下 `2160-1696=464`；
- 行内最小水平间距 128（2464→2592、1120→1248、2784→2912、640→768、1424→1552、1680→1808…）；
- 行间最小垂直间距 128（416→544、1056→1184、1400→1528）；
- 最大件 2304 ≤ 3200。

### 3.2.1 实际板面实测（R94，坐标表作废）

> 源图 `Create ONE single 4K sprite she_881c048f.png` **不是 3840×2160，而是 2880×2880**，
> 上方坐标表全部失效；实际切图按连通域重测（`tools/xp_final_board_scan.py` /
> `xp_final_board_measure.py`），左右对称、行距一致，但各件并非同一缩放倍数（约 5.6–8.3×）。

| 件 | 实测 bbox（源 px） | 1x | 换算倍率 | 备注 |
|---|---|---|---|---|
| current-gun-plate | 1751×180 | 288×32 | 6.08 / 5.63 | 中心空白 ✔ |
| version-plate | 798×174 | 136×22 | 5.87 / 7.90 | 宽高比 4.59 ≠ 规格 6.18，靠九宫格吸收 |
| brand-plate | 851×218 | 120×31 | 7.09 / 7.03 | 中心空白 ✔ |
| table-frame | 377×360 | 64×64 | 5.89 / 5.63 | 内圈全透明，`fill` 安全 |
| empty-task / story / gun | 166×200 / 242×192 / 326×111 | 48×48 | — | 图形本身带米色面，外圈全键色 |
| 五视图图标 | 170×149 / 112×139 / 63×153 / 229×80 / 159×152 | 16×16 | — | 纯墨色、无底板 ✔ |
| scroll-v-arrow-down ×2 | 192×222 / 194×222 | 22×27 | 8.7 / 8.2 | 三角 96×56 → 1x 约 11×7（≠15×10），**退回** |
| sep-horizontal | 551×48 | 64×2 | — | 实为 4~5px 三段立体槽，沿长度 20+ 级灰度漂移，**退回** |
| sep-vertical | 44×224 | 2×22 | — | 实为 30px 宽立体条，只有左暗边没有右高光，**退回** |
| 三横向滑块 | 490×174 / 500×174 / 516×174 | 44×21 | 8.3 | 三态宽差 26px（5%），按 100%×100% 铺满后边线一致 |

### 3.3 裁切与接入参数

| 件 | 切片（1x） | `border-image-width` | 接入要点 |
|---|---|---|---|
| version-plate | `4 5 4 5` | `4px 5px` | 与旧 `statusbar-cell` 同切片，布局零位移 |
| brand-plate | `5 5 5 14` | `5px 5px 5px 14px` | 左 14 保证品牌左缩进不变 |
| current-gun-plate | `5 5 5 14` | `5px 5px 5px 14px` | 同上 |
| table-frame | `2` | `2px` | 边框宽度保持 2px，不改表格内宽 |
| 图标 / 空态 | 整件 | 无 | `background-size` 固定 16×16 / 48×48，禁止缩放 |
| 分隔线 | 整件 | 无 | 横线 `background-size: 100% 2px`；竖线 `2px 100%`；禁用 `border-image` 拉伸端点 |

---

## 4. CSS 侧改动清单（不进板）

> 纯换色 / 去圆角 / 去阴影 / 去玻璃，不需要任何位图。本轮只登记，不改代码。

1. **圆角归零**：S1 全表选择器 + S2 + S6 + S11 + S12 → `border-radius: 0`（含 `span.dot`、`tk-story-dot`、`gw-calblock`）。
2. **柔和阴影移除**：`.gw-prof-box`、`.lw-preset-box`、`.am-modal-box` → `box-shadow: none`（保留 `dialog-box` 九宫格硬边）。
3. **标题栏硬化**：`header.am-modal-head` → 圆角 0、三段硬色标；或直接接 `dialog-head.png`。
4. **关钮硬化**：`.gw-prof-x`、`.am-modal-x` → 圆角 0、两段硬色标。
5. **米色按钮去圆角**：`.lw-modal-btn`、`.lw-preset-row` → 圆角 0。
6. **玻璃标签改实色**：`.lw-cell-label`、`.lw-cell-name` → `background: #ECE9D8; border: 1px solid #ACA899; color: #23231b`。
7. **模态遮罩**：`#am-detail` → `rgba(0,0,0,.28)`，删 `backdrop-filter`。
8. **语义色块方形化**：图例点 / 剧情点 / 材质签 / 口径图例点 → 圆角 0、`1px solid #ACA899`、饱和度 −15%（色相不动）。
9. **数字输入**：`input[type=number]` → `appearance: textfield` / 隐藏 `::-webkit-inner-spin-button`（键盘与滚轮不受影响）。
10. **字模替代**：`.legend-group-arrow` → `color: transparent` + `::after` CSS 三角（`border: 4px solid transparent; border-top-color: #3B412F`）。
11. **字号归一**：8/9px → 10px；13.333px → 12px；15/15.21/18px → 13px。
12. **文本内嵌符号**（`⛔`、`✕`）不在 CSS 能力范围，需数据侧改文案，本轮只登记。

### 4.1 落地核对（R94，2026-11-07，逐条实测）

> 全部改在 `assets/xp-ui/xp-ui-app.css` §19.2；不改 DOM / 类名 / 交互。验证脚本
> `tools/xp_ui_r94_verify2.py`（Chrome CDP 读 `getComputedStyle`）。

| # | 状态 | 落地选择器（实写） | 实测结果 |
|---|---|---|---|
| 1 圆角归零 | ✅ | `.task-floor` `.task-main` `.gw-card` `.am-chip` `.am-seg-btn` `.am-show` `.gw-chip` `.gw-mode` `.lw-cell` `.lw-cat` `.lw-sortbtn` `.gw-calblock` `.lw-mat-chip` `.lw-board` `.lw-deco` `.lw-block` `.lw-cost` `input.search` `select.ui-select` `span.dot` `.tk-story-dot` `.lw-modal-btn` `.lw-preset-row` `.tk-story-chip` | `border-radius: 0 !important` 全表生效；副作用：`button.task-main`×54 失去唯一装饰，覆盖脚本中从 B 移出（见 §6.1 说明） |
| 2 阴影移除 | ✅ | `.gw-prof-box` `.lw-preset-box` `.am-modal-box` | `box-shadow: none`；底板仍由 `dialog-box.png` 九宫格提供硬边 |
| 3 标题栏硬化 | ✅ | `header.am-modal-head` | 实测 `linear-gradient` 变为 `#0A3F9E 0 33.34% / #1466E0 33.34% 66.67% / #4A9BFF 66.67%` 三段硬色，`border-radius: 0` |
| 4 关钮硬化 | ✅ | `button.gw-prof-x` `button.am-modal-x` | 两段硬色 `#E2917E 0 50% / #B93A28 50% 100%`，圆角 0 |
| 5 米色按钮去圆角 | ✅ | `.lw-modal-btn` `.lw-preset-row` | 圆角 0（渐变保留，本来就合规） |
| 6 玻璃标签改实色 | ✅ | `.lw-cell-label` `.lw-cell-name` | `background:#ECE9D8` + `1px solid #ACA899` + `color:#23231b`，半透明白已消失 |
| 7 遮罩中性化 | ✅ | `#am-detail` | `rgba(0,0,0,.28)`，`backdrop-filter: none` |
| 8 语义色块方形化 | ✅ | `span.dot` `.tk-story-dot` `.tk-story-chip` `.lw-mat-chip` `.gw-callegend-dot` | 圆角 0 + `1px solid #ACA899` + `saturate(.85)` |
| 9 数字微调箭头 | ✅ | `input[type="number"]` 及 `::-webkit-inner-spin-button` `::-webkit-outer-spin-button` | `appearance: textfield`、内/外微调箭头 `appearance:none`；键盘与滚轮不变 |
| 10 `▾` 换 CSS 三角 | ✅ | `.legend-group-arrow` + `.legend-group-arrow::after` | 字符 `color: transparent; font-size: 0`，`::after` 画 `border:5px transparent` + `border-top-color:#3B412F` 的 10×5 三角；折叠态随容器 `rotate(-90deg)` |
| 11 字号归一 | ✅ | 10px：`i.gw-card-cal` `b.gw-card-badge` `span.gw-card-fig` `i.gw-calblock-n` `i.gw-badge-new` `.lw-at-badge` `span.lw-cell-name`；12px：`input` `select` `textarea` `.ui-select`；13px：`h3` `h3.am-h3` `h3.lw-h3` `h2.tk-title` | 实测 `.lw-cell-name` 由 8px→10px（本轮补进 ① 组）、`.app-menu-btn` 12px、`.sb-rev` 11px、`h3` 13px |
| 12 `⛔` / `✕` | ⛔ 不做 | — | 两者在文本节点内（`tasks.js` / 弹药表 / 枪匠），CSS 无法替换；按计划留给数据侧改文案 |

---

## 5. 生图提示词（可直接整段复制）

### 5.1 A 版（垫参考图，优先）

```text
Create ONE single 4K sprite sheet, exactly 3840 x 2160 px landscape, containing EXACTLY 19
UI sprites for a Windows XP (Luna) pixel-art control library. Every sprite sits in its own
rectangle at the exact coordinates in the COORDINATE TABLE below. This is one flat asset
sheet, not a UI mockup, not a screenshot, not a composition.

CANVAS + KEY COLOR (hard requirements)
- Background: one single flat magenta key color, exactly #E815EF = RGB(232, 21, 239).
  Do NOT use #FF00FF, #F0F, #F51CF7, #E815EF-adjacent variants, or any other magenta.
  One uniform color from edge to edge.
- No gradient, vignette, noise, grain, paper texture, lighting or shadow on the background.
- Keep at least 160 px of clean pure key color on all four outer edges.
- Keep at least 128 px of clean pure key color between any two sprites. Rectangles must
  never touch, overlap, merge, share an edge, or cast anything into the key gap.

SCALE + EDGE QUALITY
- The sheet is drawn at 8x: one logical UI pixel = one exact 8x8 block of source pixels.
  Every sprite is therefore a whole multiple of 8 in both width and height.
- Hard edges only. No anti-aliasing, no feathering, no soft blends, no sub-pixel gradients.
- Every sprite is a closed, axis-aligned rectangle with crisp 90-degree pixel corners.
- No drop shadow, no outer glow, no halo outside any sprite rectangle. The only permitted
  shadow is a 1 logical px (8 source px) hard dark line INSIDE the rectangle.

PALETTE (Windows XP Luna; use only these values)
- face / panel             #ECE9D8
- light face               #F7F5EE
- highlight                #FFFFFF
- light bevel              #F5F5EB
- mid shadow               #ACA899
- dark outline             #626355
- pressed face             #D4D4C2
- glyph ink                #3B412F
- accent blue              #316AC5
Do not introduce warm beige/orange tints, olive-green tints, purple tints, cyan, or any
magenta bleed on any bevel or face. No color outside this list except pure key color between
sprites.

NO TEXT / NO GLOSS / NO BAKED STATE
- Draw absolutely no letters, numbers, words, labels, captions, logos, watermarks or rulers.
- version-plate, brand-plate and current-gun-plate must have a COMPLETELY EMPTY center:
  the version string, app name and weapon name are layered later in CSS.
- No glossy plastic shine, no specular sweep, no white fog, no modern Web-2.0 gloss.
- Do not bake any app-level selection glow, blue overlay, hover ring or focus rectangle into
  any sprite. State differences exist only as the separate sprites listed in the table.
- Triangles, bars, ticks and 1 px lines are shapes, not text, and are allowed.

SPRITE CONSTRUCTION

GROUP A - 9-SLICE PLATES (version-plate, brand-plate, current-gun-plate, table-frame)
- Flat cream face, 1 px #FFFFFF highlight on the top and left, 1 px #ACA899 shadow on the
  bottom and right, 1 px #626355 outer outline. Square corners; at most a 1 px corner step,
  never a rounded corner.
- Keep the bevel band uniform on all four sides: at least 5 logical px (2 px for table-frame)
  of identical construction along every edge, and a perfectly uniform middle band, so each
  plate can be stretched as a 9-slice. brand-plate and current-gun-plate additionally keep
  their leftmost 14 logical px visually uniform (that band is sliced at 14 px).
- table-frame is SUNKEN, not raised: 1 px #ACA899 outer line, 1 px #FFFFFF inner line, uniform
  on all four sides, empty middle, no corner decorations.
- Nothing else may be painted inside a plate: no title bar, no icon, no dots, no grip lines.

GROUP B - SCROLLBAR (scroll-v-arrow-down-normal, scroll-v-arrow-down-hover,
scroll-h-thumb, scroll-h-thumb-hover, scroll-h-thumb-pressed)
- Arrow plates are 22x27 raised plates with the same 1 px outline and bevel as the plates.
- Each arrow plate contains ONE solid #3B412F downward triangle, exactly 15 logical px wide
  and 10 logical px tall, horizontally centered (x = 4..18), with its top edge exactly 9
  logical px below the top edge of the plate. Build the triangle from exact 1 px horizontal
  steps (top row 15 px wide, narrowing to a 1 px point). No outline around the triangle.
- The normal and hover plates must be PIXEL-IDENTICAL except for the face and highlight:
  normal face #ECE9D8, hover face #F7F5EE with a brighter top/left highlight. The triangle
  must not move, scale, lighten or change shape in any state.
- Horizontal thumb: 44x21 raised plate, 1 px #626355 outline, 1 px #FFFFFF highlight just
  inside the top and left edges, 1 px #ACA899 line along the top and bottom edges, 3 logical
  px inner margin, and a perfectly uniform middle band (no icon, no dots, no grip marks).
  Normal face #ECE9D8; hover face #F7F5EE; pressed face #D4D4C2 with a 1 px dark inner top
  edge and no white highlight. All three share identical outer geometry: same width, same
  height, same outline position, same bevel thickness.

GROUP C - SEPARATORS (sep-horizontal, sep-vertical)
- sep-horizontal: 64x2, row 0 solid #ACA899, row 1 solid #FFFFFF, uniform along its whole
  length, no end caps, no dots, no border.
- sep-vertical: 2x22, column 0 solid #ACA899, column 1 solid #FFFFFF, uniform along its whole
  length, no end caps, no dots, no border.

GROUP D - EMPTY-STATE PICTORAMS (empty-task, empty-story, empty-gun)
- Ink-only pictograms on transparent key background. NO plate, NO tile, NO frame, NO shadow
  behind them. Ink #3B412F with at most one #316AC5 accent per sprite.
- Keep a 7 logical px margin of pure key color inside the 48x48 rectangle.
- empty-task: a clipboard with three hard 2 px "text" lines (lines only, never letters) and
  a small check mark in the corner.
- empty-story: a stack of two pages / an open book, 1 px ink outline, two hard 2 px text lines.
- empty-gun: a simple side-view rifle silhouette (stock, receiver, barrel, magazine) built
  from flat ink blocks, 1 px outline.

GROUP E - TOOLBAR ICONS (icon-map, icon-tasks, icon-ammo, icon-gun, icon-loadout)
- 16x16 pictograms, ink-only on transparent key background. NO backing plate, NO chamfered
  cream tile, NO border, NO shadow. 1 px hard strokes, no anti-aliasing.
- icon-map: folded map with a small location pin (accent #316AC5 allowed on the pin).
- icon-tasks: clipboard with a check mark.
- icon-ammo: a single cartridge, vertical, with a flat tip.
- icon-gun: a rifle in side view, barrel to the right.
- icon-loadout: a plate carrier / vest with two magazine pouches.
- All five share the same optical weight and the same 1 px stroke, so they read as one set.

REFERENCE IMAGE RULES (only for the A version)
- I provide ONE reference image of my existing XP pixel controls. Borrow ONLY:
  surface material, cream palette, bevel thickness/geometry, and pixel crispness.
- Do NOT copy the reference layout, canvas arrangement, sprite count, grouping, spacing,
  grid, icon set or ordering. The COORDINATE TABLE below overrides the reference completely.
- The reference background color must be IGNORED. Its key color may be a different magenta;
  this output must use exactly #E815EF = RGB(232, 21, 239).

COORDINATE TABLE - 19 sprites, source pixels on the 3840x2160 canvas.
Format: name | x | y | w | h | final 1x size after 1/8 downsample.

current-gun-plate           | 160  | 160  | 2304 | 256 | 288x32
version-plate               | 2592 | 160  | 1088 | 176 | 136x22
brand-plate                 | 160  | 544  | 960  | 248 | 120x31
table-frame                 | 1248 | 544  | 512  | 512 | 64x64
empty-task                  | 1888 | 544  | 384  | 384 | 48x48
empty-story                 | 2400 | 544  | 384  | 384 | 48x48
empty-gun                   | 2912 | 544  | 384  | 384 | 48x48
scroll-v-arrow-down-normal  | 160  | 1184 | 176  | 216 | 22x27
scroll-v-arrow-down-hover   | 464  | 1184 | 176  | 216 | 22x27
sep-horizontal              | 768  | 1184 | 512  | 16  | 64x2
sep-vertical                | 1408 | 1184 | 16   | 176 | 2x22
icon-map                    | 1552 | 1184 | 128  | 128 | 16x16
icon-tasks                  | 1808 | 1184 | 128  | 128 | 16x16
icon-ammo                   | 2064 | 1184 | 128  | 128 | 16x16
icon-gun                    | 2320 | 1184 | 128  | 128 | 16x16
icon-loadout                | 2576 | 1184 | 128  | 128 | 16x16
scroll-h-thumb              | 160  | 1528 | 352  | 168 | 44x21
scroll-h-thumb-hover        | 640  | 1528 | 352  | 168 | 44x21
scroll-h-thumb-pressed      | 1120 | 1528 | 352  | 168 | 44x21

CUTTING
- Cut each sprite at exactly x/y/w/h above, with zero extra padding.
- Downsample each crop by exactly 1/8 with an AREA / BOX filter (8x8 block average) to get
  the final 1x size in the last column. Do not use smooth or bicubic interpolation.
- Keep the cut rectangles exactly as listed; do not trim, rotate, mirror or rescale anything.

HIGH-RISK FAILURE MODES (previous boards failed on these - do not repeat)
1. PLATES MUST NEVER CONTAIN TEXT. Any letter, digit, logo or watermark inside version-plate,
   brand-plate or current-gun-plate is an automatic reject; they are empty shells.
2. MULTI-STATE GEOMETRY MUST BE PIXEL-IDENTICAL. scroll-v-arrow-down-normal vs -hover, and
   scroll-h-thumb vs -hover vs -pressed: identical width, height, outline position and bevel
   thickness. Only face tone / highlight / pressed shading may differ. A 1 px shift or a 1 px
   size change is a reject.
3. ARROW TRIANGLES: exactly 15 x 10 logical px, identical in both states, top edge exactly
   9 logical px below the plate top, horizontally centered. Do not reuse the 11x9 or 16x11
   triangles from older sheets.
4. ICON SPRITES MUST HAVE NO BACKING PLATE: no cream square, no chamfered tile, no 1 px
   border, no shadow. Ink pixels directly on pure key color.
5. SEPARATORS must be perfectly uniform along their long axis, with no caps, no border and
   no dots, so they can be repeated or stretched without seams.
6. MULTI-STATE SWITCH AND TAB FRAMES (not present in this board, keep for future boards):
   off/on tracks, knobs and tab states must share identical geometry and identical corner
   bevels; only the face and glyph change.

NEGATIVE - do not do any of these:
no text, no numbers, no letters, no logos, no digits inside plates, no rounded corners,
no smooth gradients, no glass, no gloss, no specular highlight, no outer glow, no soft shadow,
no anti-aliasing, no magenta fringe or purple halo inside any sprite, no icons baked into
plates, no extra sprites, no overlapping or touching rectangles, no canvas border, no vignette,
no watermark, no copied reference layout, no packed grid tighter than the 128 px key gaps.
```

### 5.2 B 版（无参考图，纯文字降级）

把 A 版里的 `REFERENCE IMAGE RULES (only for the A version)` 整段替换为：

```text
REFERENCE IMAGE RULES
- No reference image is provided. Build material, bevels and palette from the PALETTE and
  SPRITE CONSTRUCTION sections only.
- The output must still use exactly #E815EF = RGB(232, 21, 239) as the single key color.
```

---

## 6. 高频翻车点（中文速查）

| 翻车点 | 本板涉及件 | 判据 |
|---|---|---|
| 徽标 / 铭牌里写了字 | M14 version / M15 brand / M16 current-gun | 中心必须纯米色，任何字符 = 废 |
| 多态几何不一致 | M9/M10 箭头、M11/M12/M13 滑块 | 外框逐像素同形，只允许面色与高光不同 |
| 箭头三角尺寸漂移 | M9/M10 | 必为 15×10、距顶 9、水平居中；不要沿用旧板的 11×9 / 16×11 |
| 页签三态不同高（未来板） | — | 同高、同倒角、同外框 |
| 图标带底板 | M23–M27 | 16×16 区域只允许墨色像素，不许米色方块 / 圆角瓦片 / 边框 |
| 分隔线两端带端点 | M21/M22 | 长轴完全均匀，可无限重复 |
| 面板件不可拉伸 | M14–M17 | 四边同厚倒角 + 中段纯色，才允许九宫格 |
| 烘焙选中态 / 外发光 / 光泽 | 全部 | 一律禁止 |
