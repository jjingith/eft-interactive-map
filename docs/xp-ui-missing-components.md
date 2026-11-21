# XP UI 缺件清单（R92 可见元素级）

> 本轮口径：可见元素级（容器、背景层、列表行、卡片、浮层、表头、滚动区都算）。
> 判定标准见 `docs/xp-ui-coverage.md` 第六节。
> 原则：**缺件不硬凑、不整图缩放**；尺寸不匹配一律 `border-image` 九宫格。
> 本清单只收「确实无法用现有素材解决」的项；「有素材但还没接」的项记在覆盖文档的 NEXT ROUND，不在这里重复。

## 一、源图缺件（需要补素材）

> **M1–M8 已由 R93（`ui图标/xp风格ui/20261107补充.png`）全部结案**（2026-11-07 11:01 那板，
> 18 件）。本节不再保留未解决行，以免误导；落地方案、体检数据与证据见
> `docs/xp-ui-coverage.md` §八。
>
> **R94 复核：M1 / M2 重新开案。** 像素级复核证明规格未达成（M1 实际三角 16×11 / 距顶 8；
> M2 常态顶边缺少 hover / pressed 那条深线），重画件并入 §1.2 的 M9–M13；M3–M8 维持结案。

### 1.1 已结案（R93）

| # | 组件 | 结论 | 证据 / 说明 |
|---|---|---|---|
| M1 | 竖向滚动条「向下箭头」hover | R93 不采纳；**R94 重开**（见 §1.2 M9/M10）；**R96 已解决** | 新件把三角烘焙进底板（三角 11×9/54px）。**R94 实测更正**：`scroll-v-glyph-down.png` 画布 20×11、ink 16×11（x=4–19、y=0–10），CSS 置于 `center 8px`；底板亦烘焙了一枚 11×9 三角（顶边 y=9），被 glyph 盖住。可见三角实为 16×11/距顶 8，未达「15×10/距顶 9」规格。**R96**：改用 Pillow 几何件 `scroll-v-arrow-down-normal/hover.png`，三角 15×10、距顶 9 |
| M2 | 横向滚动条滑块常态 | R93 不采纳；**R94 三态成套重画**（见 §1.2 M11–M13） | 新件 44×21 与现有同尺寸但更厚、边框更重（平均像素差 21.8）。**R94 实测**：常态中心列深色行 `[20]`、hover `[0,20]`、pressed `[0,19,20]`，三态顶边权重本就不同，单换常态无法一致 |
| M3 | 通用徽标底板（大，17×17） | **已解决** | `badge-md.png` / `badge-md-hover.png` 已接 `b.gw-card-badge`（163 处）；中心区无文字（luma σ 0.5–1.83、暗像素 0），一位数 13.71×16.99、两位数 19.43×16.99，不裁字。`badge-md-warn.png` 已切但无对应语义状态，**未接** |
| M4 | 通用徽标底板（小，26×11 / 13×16） | **已解决** | `badge-sm.png` → `i.gw-badge-new`（28.17×10.99）；`badge-micro.png` → `span.lw-cl-badge`（12.98×15.98）与 `span.lw-at-badge`（12.98×12.98，9-slice 压到 13×13）；顺带修掉 `.lw-at-heavy` 白字白底 |
| M5 | 开关轨道 28×14 + 滑块 10×10 | **已解决** | 轨道 `switch-track-off/on.png`、滑块 `switch-knob-off/on/hover.png` 接入 54 组；track 27.98×13.99、knob 9.98×9.98、dx=15 / dy=0.98；两态 IoU 0.9973 / 1.0000，切换不跳 |
| M6 | 提示牌底板 120×40 | **已解决** | `tip-plate.png` 4px 九宫格 → `.lw-tip` / `.gw-tip` / `.am-graph-tip` / `.marker-pop`；放大截图无接缝、文字不压边 |
| M7 | 26px 高页签三帧 | **已解决** | `tab-active-26/inactive-26/hover-26.png` → `.am-tab`；三态同高 25.99px，外框 34px 与旧版对齐，不裁字、不顶穿 26px 工具条 |
| M8 | 16px 高紧凑型 range | **已解决** | `range-track-compact.png`（16px 高）+ `range-thumb-compact.png`（10×16）→ `#am-traderlvl`（245×16）/ `#gw-traderlv`（62×16），值域与交互不变 |

### 1.2 R94 最后一板（M9–M27，本批结案 15 件 / 退回 4 件）

> 19 件，坐标表见 `docs/xp-ui-final-board-prompt.md` §3.2（8x、键色 `#E815EF`）。
> M9/M10 同板两态，M11–M13 同板三态；其余为单件。
>
> **R94 实测**：板面 2880×2880（非 3840×2160）、键色实测 `#DF2CEB`（非 `#E815EF`）。
> **15 件落盘并接入（M11–M20、M23–M27 ✅）；4 件退回（M9/M10/M21/M22 ❌）**。
> **R96 补充**：退回的 4 件已用 Pillow 几何件在原文件名上重绘达标（不依赖 AI 生图），现已全部接入，见各行。

| # | 件名（落盘） | 1x | 用途 | 落点选择器 | R94 结果 |
|---|---|---|---|---|---|
| M9 | `scroll-v-arrow-down-normal` | 22×27 | 下箭头常态底板（三角同板烘焙 15×10 / 距顶 9） | `::-webkit-scrollbar-button:vertical:end:increment` 及 `.db4-scroll/.db4-rail/.tbl-scroll/.am-side/.lw-side/.am-sim-cfg` 六个容器限定选择器 | **✅ R96 已解决**：AI 件退回后由 Pillow 重绘同文件（22×27，三角 15×10 / 距顶 9），已接 |
| M10 | `scroll-v-arrow-down-hover` | 22×27 | 下箭头 hover（只改高光，三角与 M9 逐像素同形） | 同上 `:hover` 分支 | **✅ R96 已解决**：Pillow 重绘，与 M9 几何逐像素同形，只差高光 |
| M11 | `scroll-h-thumb` | 44×21 | 横向滑块常态 | `::-webkit-scrollbar-thumb:horizontal` | ✅ 已接（490×174 → 44×21） |
| M12 | `scroll-h-thumb-hover` | 44×21 | 横向滑块 hover（一致性对照帧） | `::-webkit-scrollbar-thumb:horizontal:hover` | ✅ 已接（500×174） |
| M13 | `scroll-h-thumb-pressed` | 44×21 | 横向滑块 pressed（一致性对照帧） | `::-webkit-scrollbar-thumb:horizontal:active` | ✅ 已接（516×174） |
| M14 | `version-plate` | 136×22 | 版本牌，替换 `statusbar-cell.png` | `#build-rev.build-rev`、`.tk-build` | ✅ 已接（798×174，中心空白） |
| M15 | `brand-plate` | 120×31 | 应用品牌牌，替换 `plaque-3.png` | `#app-brand.app-brand` | ✅ 已接（851×218，中心空白） |
| M16 | `current-gun-plate` | 288×32 | 「当前配枪」状态条，替换 `plaque-3.png` | `.gun-workbench #gw-current` | ✅ 已接（1751×180，中心空白） |
| M17 | `table-frame` | 64×64 | 表格滚区外框（2px 凹槽 / 切片 2），替换 `groupbox.png` | `.loadout-workbench .tbl-scroll`、`.gun-workbench .tbl-scroll`、`.am-workbench .am-table .tbl-scroll` | ✅ 已接（内圈透明，`fill` 安全） |
| M18 | `empty-task` | 48×48 | 任务空态插图 | `.task-list > .task-empty::before` | ✅ 已接（166×200） |
| M19 | `empty-story` | 48×48 | 剧情空态插图 | `#tk-story-list .tk-story-empty::before` | ✅ 已接（242×192） |
| M20 | `empty-gun` | 48×48 | 枪匠空态 / 加载态插图 | `#gw-browse .lw-loading::before` | ✅ 已接（326×111） |
| M21 | `sep-horizontal` | 64×2 | 菜单 / 右键菜单分隔线（`#ACA899` + `#FFFFFF`） | `.menu-panel section + section::before`、`.task-context-item + .task-context-item::before` | **✅ R96 已解决**：AI 件退回后 Pillow 重绘为纯 64×2 两行线，接右键菜单项 `::before` |
| M22 | `sep-vertical` | 2×22 | 状态栏 / 菜单分组竖分隔 | `.app-menus .app-menu + .app-menu::before` | **✅ R96 已解决**：Pillow 重绘为纯 2×22；状态栏因已有 `statusbar-cell` 整框会成双线，改挂顶部菜单分组之间 |
| M23 | `icon-map` | 16×16 | 视图图标，替换内联 SVG | `#view-btn-map .vt-ico` | ✅ 已接（纯墨、无底板） |
| M24 | `icon-tasks` | 16×16 | 视图图标 | `#view-btn-tasks .vt-ico` | ✅ 已接 |
| M25 | `icon-ammo` | 16×16 | 视图图标 | `#view-btn-ammo .vt-ico` | ✅ 已接 |
| M26 | `icon-gun` | 16×16 | 视图图标 | `#view-btn-gun .vt-ico` | ✅ 已接 |
| M27 | `icon-loadout` | 16×16 | 视图图标 | `#view-btn-loadout .vt-ico` | ✅ 已接 |

> M9/M12/M13 是「一致性帧」：不是独立缺陷，而是为了让两态 / 三态同板同几何、只差面色与高光。
> 接入时 M11–M13 一次性整套替换，旧件保留作回退。
>
> **R96 结案：本表已无缺件。** M9 / M10（下箭头两态）与 M21 / M22（两条分隔线）都由 Pillow
> 按实测规格重绘并在原文件名上覆盖，已接入；不再需要新建素材。

## 二、DOM 限制（补素材也解决不了，需要改结构）

| # | 组件 | 界面 / 选择器 | 为什么用不了 | 现在用什么顶着 | 要解决需要什么 |
|---|---|---|---|---|---|
| D1 | 菜单面板分隔线 | `.menu-panel` 各分区之间 | DOM 里**没有独立的分隔元素**，只有相邻 `section` 的 `border-top` | 沿用 1px CSS 边框 | **R94 已解**：给 `section + section` 挂 `::before` 承载 `sep-horizontal` 64×2，不改 DOM、不遮挡点击（M21） |
| D2 | 右键菜单分隔线 | `.task-context-menu` / 地图右键菜单 | 同上，菜单项之间无独立分隔元素 | 菜单项自身 1px 边框 | **R94 已解**：`.task-context-item + .task-context-item::before` 承载同款 64×2（M21） |
| D3 | 状态栏分隔线 | `#app-statusbar` 各格之间 | 状态栏是平铺 `span`，无分隔元素 | 单元格之间的 1px `border-left` | **R94 已解**：`.sb-cell` 已有左边框，直接 `border-image` 换皮（`sep-vertical` 2×22，M22），**无需 DOM 增列** |
| D4 | 原生下拉展开列表 | 所有 `select`（15 个） | `option` 列表由操作系统绘制，CSS 无法换皮 | 只保证收起态是 `select.png` 素材 | 需改成自定义下拉（`div` + `role=listbox`），属交互/DOM 改动，暂不做 |
| D5 | 数字输入微调箭头 | `input[type=number]`（20 个） | `::-webkit-inner-spin-button` 由浏览器绘制 | 保留原生箭头（功能需要） | 需自定义步进按钮（DOM 改动）；或全局隐藏箭头，靠键盘/滚轮 |
| D6 | 系统 tooltip | 3564 个 `title` 属性 | 悬停提示由系统绘制 | 保留 | 只能改用 M6 的自定义浮层，逐项替换 `title`（工作量在数据侧） |
| D7 | 浏览器右键菜单 | 地图空白处 / 非任务区 | 未接管 `contextmenu` | 保留浏览器菜单 | 需新增自定义菜单（DOM + 事件），任务卡与地图标注已有先例 |

## 三、语义 / 内容类：**建议保留 CSS**，不属于缺件

这些元素的颜色或内容是信息本身，套米色素材会破坏语义：

| 组件 | 选择器 | 现状 | 说明 |
|---|---|---|---|
| 地图图例色点 | `span.dot.dot-*`（9×9） | CSS 纯色圆点 | 颜色 = 图例含义（危险区/炮击/标注等），不能用位图替换 |
| 剧情状态圆点 | `span.tk-story-dot`（24×24，38 处） | CSS 圆点 + 数字 | 颜色/数字表示完成度，属于数据可视化 |
| 剧情语义小标签 | `span.tk-story-chip`（32×17，17 处） | CSS 色签 | 前置/分支/限时等语义色 |
| 配装材质标签 | `span.lw-mat-chip`（13px 高，多种配色） | CSS 色签 | 材质类别靠颜色区分 |
| 枪匠口径色块 | `div.gw-calblock`（40×95） | CSS 色条 | 口径分类色，属图例语义 |
| 枪械照片 | `img.gw-card-img`（64×42，163 处） | 真实 `<img>` | 物品图标，不能换成 UI 素材 |
| 地图画布 | `main#stage` | 深色底图 | 浅色会破坏地图可读性，刻意保持深色 |
| 文本标签 | `.lw-cell-label` / `.lw-cell-name` / `.lw-cats-note` / `.hud-scale` 文字行 | 纯文字 | 无独立底板；`.lw-cell-label` / `.lw-cell-name` 另有一层半透明白底（`rgba(255,255,255,.88/.86)`），属 CSS 玻璃感，R94 改实色，**不做素材** |

## 四、近似顶替（有临时件，未来应补正式件）

> **R94 已把本表五项全部入板**：版本牌 M14、品牌牌 M15、当前配枪 M16、表格外框 M17、
> 空态插图 M18–M20（见 §1.2）。下表保留原偏差记录，作验收对照。

| 组件 | 现用素材 | 偏差 | 建议正式件 |
|---|---|---|---|
| 任务行开关 | ~~`range-track` + `progress-fill` + `range-thumb`~~ → `switch-track-off/on` + `switch-knob-off/on/hover` | **R93 已解决**，不再是近似件 | — |
| 版本徽标 | `statusbar-cell.png` | 凹槽白格，不是专用版本牌 | **136×22** 九宫格版本牌（R94 M14） |
| 应用品牌牌 | `plaque-3.png` | 183×39 的铭牌压到 121×31，左侧 14px 缩进偏大 | **120×31** 专用品牌牌（R94 M15） |
| 当前配枪状态条 | `plaque-3.png` | 同上，291×33 拉伸后中段偏空 | **288×32** 九宫格（R94 M16） |
| 表格滚区外框 | `groupbox.png` | 分组框凹槽套在表格外，四角略厚 | **table-frame 64×64**（2px 凹槽 / 切片 2，R94 M17；4px 凹槽会抬内宽，弃用） |
| 空态插图 | `empty-box.png`（48×48） | 通用空盒，不同空态无区分 | **empty-task / empty-story / empty-gun 各 48×48**（R94 M18–M20） |

## 五、汇总：如果要一次补齐，建议尺寸

> **R93（`20261107补充.png`）已交付并结案**：17×17 / 26×11 / 13×16 / 28×14×2 / 10×10×3 /
> 120×40 / 26px 高×3 / 16px 高 + 10×16 全部到位并接入；21×21 箭头 hover 与横向滑块常态
> 各收到 1 张但因几何/厚度不一致未采纳（见 §1.1）。以下为 **R94 最后一板**的完整清单。

- 滚动条：`scroll-v-arrow-down-normal` / `-hover` 各 22×27；`scroll-h-thumb` /
  `-hover` / `-pressed` 各 44×21（M9–M13）
- 铭牌类：`version-plate` 136×22、`brand-plate` 120×31、`current-gun-plate` 288×32、
  `table-frame` 64×64（M14–M17）
- 空态：`empty-task` / `empty-story` / `empty-gun` 各 48×48（M18–M20）
- 分隔线：`sep-horizontal` 64×2、`sep-vertical` 2×22（M21–M22，均不改 DOM）
- 视图图标：`icon-map` / `icon-tasks` / `icon-ammo` / `icon-gun` / `icon-loadout`
  各 16×16（M23–M27，透明无底板）
- 生图口径与坐标表：`docs/xp-ui-final-board-prompt.md`（8x、3840×2160、键色 `#E815EF`）

> 纯 CSS 可解、**不占素材位**的项（换色 / 去圆角 / 去阴影 / 去玻璃 / 字号归一）见
> `docs/xp-ui-final-board-prompt.md` §4「CSS 侧改动清单」。
