# R19.1 布局对照（参考截图 ↔ 本地实现）

> 参考截图目录：`D:\personal\trae\02-塔科夫\ui图标`（详见 `reference-screenshots.md` 的逐张记录）。
> 本地截图：真实浏览器（Chrome headless + CDP），1920×1080 与 1264×705 两种窗口。
> 配色差异（参考站深色 / 本地 XP Luna 浅色）是**任务要求保留**的主题差异，不作为布局差异计。

## 1. 工作台（/gun Gun 视图）

- 参考：`ui图标\改枪台界面.png`
- 本地：`screenshots\1920-05-builder.png`、`layout-comparison\ref-gun-builder-vs-local.png`（1264 版 `ref-gun-builder-vs-local-1264.png`）
- 对照结论：
  | 参考区域 | 本地对应 | 状态 |
  |---|---|---|
  | 顶部导航 GUN 页签 | 主菜单「配枪」页签 | ✅ 一致（站点级导航本地是地图/配装/弹药主菜单，不逐项复刻 db4 的 MARKET/SEASON 等——那是它站内其他页） |
  | `Caliber│Class│Table│Gun` 视图页签 | `gw-modes` 四页签（口径/类别/表格/工作台） | ✅ |
  | 左栏 FORGE 面板 | `gw-forge`：FORGE BETA 标题、优化目标芯片、GENERATE BUILDS | ✅（简化：无 SUPPRESSED/MAGS/SCOPE/BLOCKED/FORCED，见差异） |
  | 中栏 LOAD VARIANT | `gw-visual` + `gw-ref` 内置参考预设下拉 | ✅（位置在顶栏，非中栏顶部） |
  | 属性条（括号基线） | `gw-bars` 五条：人机工效/散布角/垂直后坐/水平后坐/初速 | ✅ 人机/后坐verified；初速=弹药×(1+修正%)estimated |
  | 配件卡片网格+虚线空槽 | `gw-tree` 卡片（实体卡/虚线空槽/ergo+后坐角标/子槽分组） | ✅（递归树改为卡片形态，纵向排列；参考站是画布树+卡片网格两种形态，本地取卡片网格） |
  | 弹药卡（dps） | `gw-ammo`：弹种下拉+伤害/穿透/初速/dps | ✅ 数据来自本地弹药库 |
  | 右栏候选表（Expand/Ergo/Size/Kg/Price） | `gw-cands`：配件│Ergo│下级槽│Kg│价│后坐│状态 + 搜索框 | ✅（Size 列本地无占格数据 → 换成「下级槽」并注明） |
  | 底部 Final Cost + Buy/Sell + 时间线 | `gw-bottom`：Final Cost + 时间线（配件名+ergo/后坐差值+default 标记） | ⚠️ 缺 Buy/Ammo Drop/Sell 三页签与 ITEMS/BREAK 子页签（本地把成本明细放在属性面板：整枪成本/改装件两行） |

## 2. 浏览页 Caliber 视图

- 参考：`ui图标\枪械口径分类.png`
- 本地：`screenshots\1920-01-caliber.png`、`layout-comparison\ref-gun-caliber-vs-local.png`
- 对照：口径分组 + 组头标签 + 卡片墙（口径小字/槽位角标/名称）✅；筛选行 Primary/Handgun + Auto/Single/Burst ✅（Silent/Loud 禁用+「无数据」注明）；参考站口径块的**弹药等级配色**未复刻（本地统一主题色）——数据缺口：本地无口径→等级映射。
- 差异：参考站组头是彩色大块，本地是主题色横条；参考站卡片带成交价小字，本地卡片无价格（价格在表格视图与候选表里）。

## 3. 浏览页 Class 视图

- 参考：`ui图标\枪械类型分类.png`
- 本地：`screenshots\1920-02-class.png`、`screenshots\1264-02-class.png`
- 对照：类别分组（突击步枪/卡宾枪/冲锋枪/精确射手/栓动狙击/机枪/霰弹/手枪/左轮/榴弹）✅；卡片结构同上 ✅。
- 差异：参考站另有 `*Classifier ▾` / `Caliber Filter ▾` 两个下拉；本地的口径筛选通过「口径视图」本身实现，未单独做下拉。

## 4. 浏览页 Table 视图

- 参考：`ui图标\枪械详细属性界面.png`
- 本地：`screenshots\1920-03-table.png`、`screenshots\1264-03-table.png`
- 对照：表格列（口径│类别│枪械│人机│垂直后坐│水平后坐│射速│改装槽│参考价）✅ 全部来自已验证数据。
- 差异：参考站的 Rat./Weight/商人角标/易货价列未做——本地单价数据只有一套快照（无商人等级价/易货），不编造；排序为默认排序（参考站表头可点击排序，本地为固定口径+名称排序）。

## 5. /preset 页（价格/角标风格参照）

- 参考：`ui图标\httpsdb4tarkov.compreset截图.png`、`头盔配件栏位范例.png`
- 本地：无对应页面（本地 preset 功能由 /gun 的装配预设承担）
- 采纳元素：Final Cost 位置（右下）、ergo 差值着色（负红/正绿）、商人等级角标样式（本地无等级数据，未用）。

## 6. FORGE 交互对照

- 参考（改枪台截图左栏）：SUPPRESSED/BUYABLE 切换、MAGS 10–100、SCOPE CLOSE/MID/RANGE、TACTICAL、BLOCKED/FORCED 黑白名单、GENERATE BUILDS。
- 本地（`screenshots\1920-07-forge.png`、`1920-08-forge-applied.png`）：优化目标四芯片（低后坐力/高人机工效/轻量化/性价比，所选目标权重加倍）+ GENERATE BUILDS + 结果列表（人机/后坐/成本 + 应用按钮，应用前过 GB.sanitize 兼容校验）。
- 差异（逐项如实标注）：MAGS/SCOPE/TACTICAL/BLOCKED/FORCED 未做——本地优化器没有弹匣容量约束与消音强制逻辑，硬做会产出「看似有约束、实际无效」的假控件；SUPPRESSED 同理（无消音标记数据）。3D Pareto frontier 可视化未做（引擎输出多方案列表，无三维绘图）。

## 7. 双枪比较

- 参考站 Compare 为并排双栏（R19 审计截图 14-compare.png）。
- 本地：对比表（默认装配/快照 vs 当前）保留，位置在装配区顶部 `1920-06` 系列截图可证。未改为参考站的左右双栏（需要两套独立装配状态机，本轮未做，见 feature-matrix）。
