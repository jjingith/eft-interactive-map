# R19.8 枪械工作台完善与 FORGE 筛选功能修复 · 验收报告

- 项目根目录：`d:\personal\trae\02-塔科夫\eft-interactive-map`
- 运行方式：`tools/serve.py` 本地服务 `http://127.0.0.1:8787/`（完全离线，无运行期外部请求）
- 运行版本：`R19.8-9ac753b3`（`/api/build` 每次按当前文件重新计算，页面 `#build-rev` 同值）
- Git：本轮**未提交、未推送**，未覆盖 `release/`，所有既有未提交改动原样保留
- 验收视口：`1920×919`、`1384×805`
- 验收手段：真实 Chrome（CDP）+ 逐项 DOM 测量 + 真实点击/输入/刷新/重新加载 + 截图；自动化测试另行运行

---

## 1. 修改文件与实际改动

| 文件 | 改动 |
| --- | --- |
| `index.html` | LOAD VARIANT 行在「恢复默认」右侧新增 `#gw-save`（文本「保存预设」），保持在 `#gw-preset-state` 左侧；筛选芯片保持 `data-gwkind` / `data-gwfire` 字段，新增 `#gw-filterstate` 状态位 |
| `app.js` | ① 新增保存预设入口与 `gbSaveCurrent`（写入 `eftmap.gunbuilds.v1`，标记 `userPresetId`，刷新后可回显）；② `gunAmmoColumns()` 新增「后坐力 / ACC」列；③ `renderGunStatsV2()` 末尾追加 `div.gw-costrow`（整枪成本 / 改装件成本）；④ `renderGunBottom()` 时间线新增部件图标、商人价与跳蚤价（复用 `buyPriceOf` / `itemPrice`）；⑤ `gwFilteredGuns` / `gwChipClick` / `gwSyncFilterUI` 用真实分类与射击模式字段筛选并同步选中态；⑥ `renderGunForge` 的必需瞄具改为近/中/远 + 具体瞄具，战术设备增加手电/激光；`forgeConstraints()` 把 `scopeId` 与 `features` 接入 `GB.optimize` 与应用终检 |
| `style.css` | 新增/调整仅限 `.gun-workbench`：`.gw-costrow` / `.gw-cost`（第三行并排、金额 8.5px、不省略）、`.gw-tl-icon` / `.gw-tl-price`、`.gw-chip[aria-pressed="true"]` 选中态、`.gw-preset-state` 限宽、`.gw-forge-opts` 列表 |
| `gun_builder.js` | `checkConstraints` 增加 `scopeId` 与 `features` 终检；`optimize` 预装必装瞄具（含一级转接座）、贪心后补装、功能设备补装与终检 |
| `data/forge-constraints.json` | 构建期审计映射：78 件瞄具的倍率分档、26 件战术设备的 `light` / `laser` 布尔；本轮修正 3 条误标（见第 7 节） |
| `tests/test_r19_8_round.py` | 新增 18 条回归断言（按钮顺序、保存链路、弹药字段与列宽、成本第三行、部件价格、筛选数据与选中态、FORGE 约束、审计数据一致性） |

未改动：地图渲染、地图图标、路线、定位、任务、人物装备工作台、枪械预设数据、`data/gunslots.json`。

---

## 2. 保存预设（LOAD VARIANT）

**界面顺序（1920 / 1384 实测一致，无重叠、无裁切）**

`⤓ LOAD VARIANT → 预设下拉 → 恢复默认 → 保存预设 → 预设状态 → 弹性留白`

- `LOAD VARIANT 无元素重叠`：`[]`
- `LOAD VARIANT 无裁切`：`[]`
- 截图：[1920x919-F3-loadvar-save.png](1920x919-F3-loadvar-save.png)、[1384x805-F3-loadvar-save.png](1384x805-F3-loadvar-save.png)

**完整链路（真实浏览器操作）**

1. 改装 M4A1（更换照门、拉机柄、消焰器、准星等，共 12 件）；
2. 点「保存预设」→ `window.prompt` 输入 `R19.8 验收预设 1920x919`；
3. 保存后下拉立即出现 `u:bmvnyfdw1`，文本 `R19.8 验收预设 1920x919（本机 · 12 件）`；
4. `Page.reload({ignoreCache:true})` 后该选项仍存在（同 `u:bmvnyfdw1`）；
5. 选择该预设重新加载，装配映射与保存时逐槽一致（示例：`mod_reciever/mod_sight_rear` → 丰和 20 式折叠式照门、`mod_charge` → 柯尔特 AR-15 拉机柄、`mod_muzzle` → USGI A2 消焰器、`mod_gas_block` → M4 准星）。

截图：[1920x919-03-preset-saved.png](1920x919-03-preset-saved.png)、[1920x919-04-preset-loaded.png](1920x919-04-preset-loaded.png)（1384 同名文件同样保存）。

- 存储键 `eftmap.gunbuilds.v1`（localStorage），写入前序列化枪械 id + 槽位装配，读取时过 `GB.sanitize` 真实槽位兼容校验；
- 「恢复默认」只清空当前选中（`g.userPresetId = ""`），**不删除**任何本机预设；
- 预设状态文字保持短句（`本机 · 未改动` / `本机 · 改 N 件` / `内置 · 已装载` / `未保存（改装中）`），完整预设名放在悬停 `title`，1384 视口不再被省略号截断。

---

## 3. 弹药候选：后坐力与 ACC

| 列 | 字段来源 | 含义 / 单位 | 显示规则 |
| --- | --- | --- | --- |
| 后坐力 | `data/ammo.json` 的 `recoilModifier`（本地字段 `rec`） | 弹药自带后坐力修正，小数比例（`0.1` = +10%），**不是枪械后坐力** | 比例 ×100、保留正负号一位小数；缺失 `—`，0 显示 `0%` |
| ACC | `data/ammo.json` 的 `accuracyModifier`（本地字段 `acc`） | 弹药自带精度修正，小数比例；**正值 = 散布增加（精度下降）** | 同上 |
| 价格 | 上游 `buyFromTrader` 卢布价（`buy.rub`），无则回退 `basePrice` | 商人买入价 / 基础参考价（本地无跳蚤报价） | 千分位 + ` ₽`；缺失 `—` |

列结构（`gunAmmoColumns()`）：`弹药名称 | 伤害 | 穿透 | 初速 | 后坐力 | ACC | 价格 | 状态`；宽度 名称 `minmax(118px,1.8fr)`、伤害/穿透/初速 `50px`、后坐力/ACC `62px`、价格 `86px`、状态 `46px`。

**三种不同弹药实测（1920×919，页面显示 vs 本地数据）**

| 弹药 | 伤害 | 穿透 | 初速 | 后坐力 | ACC | 价格 | 数据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5.56x45 Warmageddon | 88 | 3 | 936 | +10.0% | +10.0% | 243 ₽ | rec 0.1 / acc 0.1 / buy.rub 243 |
| 5.56x45 M995 | 42 | 53 | 1013 | +8.0% | -7.0% | 1,230 ₽ | rec 0.08 / acc -0.07 / base 1230 |
| 5.56x45 SSA AP | 38 | 57 | 1013 | +6.0% | -9.0% | 1,525 ₽ | rec 0.06 / acc -0.09 / base 1525 |

- 全部 200 条弹药逐行与 `ammo.json` 一致（`弹药列表全部行与本地数据一致（含价格档）`）；
- 表头与数值列无裁切（`弹药表头与数值列无裁切: []`），两个视口均无横向溢出；
- 换枪时按新口径重建候选（M4A1 为 5.56x45）；选中后仍写回画布子弹格并更新 DPS（`选中弹药显示在子弹格且 DPS 更新`）。

截图：[1920x919-F6-ammo-rec-acc.png](1920x919-F6-ammo-rec-acc.png)、[1384x805-F6-ammo-rec-acc.png](1384x805-F6-ammo-rec-acc.png)、[1920x919-02-ammo.png](1920x919-02-ammo.png)。

---

## 4. 整枪成本固定在第三行

DOM 顺序（`#gw-stats`）：`整枪属性` 标题 → 9 项指标（5 列网格占满两行）→ `div.gw-costrow`（`div.gw-cost` × 2，末尾追加）。

**实测（两视口一致）**

| 视口 | 各行 y 坐标 | 成本行 y | 两项尺寸 | 金额字号 | 显示 |
| --- | --- | --- | --- | --- | --- |
| 1920×919 | 616 / 631 / 644 / **657** | 657（第三行） | 277×13 各一，x=257 / x=539 | 8.5px | `整枪成本（含原厂件）308,475 ₽`、`其中改装件 216,054 ₽` |
| 1384×805 | 641 / 656 / 669 / **682** | 682（第三行） | 277×13 各一，x=229 / x=511 | 8.5px | 同上 |

- `成本标签/金额不省略`：`lc=false, nc=false`（标签与金额都没有 `scrollWidth > clientWidth`）；
- 数值来自 `GB.cost(ctx, gunId, installed, {includeStock:true/false})`，换枪、载入预设、装拆配件后随 `renderGun()` 重算；
- 缺价件只提示「N 件缺价，未按 0 计」，不显示假金额。

截图：[1920x919-F4-stats-cost-row.png](1920x919-F4-stats-cost-row.png)、[1384x805-F4-stats-cost-row.png](1384x805-F4-stats-cost-row.png)。

---

## 5. 逐部件价格明细

结构：`[部件图标 16px] 部件名称 …… 人机 | 后坐 | 默认 | 商人价 | 跳蚤价`。

- 图标：`img.tbl-icon.gw-tl-icon`，`setGearIcon(img, id)` 取该部件自己的本地图标，位于名称左侧；
- 名称长时可省略，`title` 给出完整名称 + 槽位路径；
- 商人价：`buyPriceOf(rec)`（`trade` 中 `k === "buy"` 的最低有效卢布报价）；
- 跳蚤价：`itemPrice(rec, "flea")`（与配装工作台完全同一函数与价格档位，取 `p.a` 24h 均价快照）；
- 缺价显示 `—` 并在 `title` 说明（「不按 0 计」），不顶替其他档位、不混用出售价。

**实测价格列右边缘（行数 8 / 12 均一致）**：1920×919 全部为 `808`；1384×805 全部为 `780` → 价格列严格右对齐。

截图：[1920x919-F5-parts-price.png](1920x919-F5-parts-price.png)（12 行全入镜）、[1384x805-F5-parts-price.png](1384x805-F5-parts-price.png)。

整枪成本汇总（`#gw-stats` 第三行）与逐部件明细（`#gw-bottom` 时间线）为两个独立区域，右侧候选列表未被替代。

---

## 6. 「口径」「种类」分页筛选按钮

修的是真实数据链路，不是 CSS：`gwFilteredGuns()` 用 `items.json` 的 `cats[0]` 经 `GW_HANDGUN_CLASSES` 判定主武器 / 手枪，用 `gun-stats.json` 的 `fm` 经 `gwFireMatch` 判定 Auto / Single / Burst；两组按 **AND** 组合，同组单选、再点已选 = 清除本组，另一组保持。

**实测（两个分页 × 两视口，结果与独立数据计算完全一致）**

| 条件 | 结果 | 状态文字 |
| --- | --- | --- |
| 主武器 | 132 / 163 | `筛选：主武器 · 132 / 163 把` |
| 手枪 | 31 / 163 | `筛选：手枪 · 31 / 163 把` |
| Auto | 89 / 163 | `筛选：Auto · 89 / 163 把（另有 0 把缺射击模式数据…）` |
| Burst | 7 / 163 | `筛选：Burst · 7 / 163 把…` |
| Single | 156 / 163 | `筛选：Single · 156 / 163 把…` |
| 主武器 + Auto | 86 / 163 | `筛选：主武器 + Auto · 86 / 163 把…` |
| 主武器 + Single（种类页） | 125 / 163 | 组合生效，种类条件未被清除 |
| 清除 | 163 / 163 | `全部枪械 · 163 把`，`pressed = 0` |

- 选中态：`aria-pressed="true"` + `data-on="1"` + 底色/描边高亮；未选中保持普通态；`#gw-filterstate` 在 `data-on="1"` 时高亮加粗；
- 空结果会由状态文字直接显示 `0 / 163 把`，不会看起来像按钮失效；
- 本地 163 把枪全部有 `fm`，不存在伪装成可筛选的缺失数据；`Silent / Loud` 因无「内置消音」字段仍保持禁用并注明原因（未伪造）。

截图：[1920x919-F1-filter-caliber-primary.png](1920x919-F1-filter-caliber-primary.png)、[1920x919-F2-filter-class-handgun.png](1920x919-F2-filter-class-handgun.png) 及 1384 同名文件；分页全量见 `03`~`06`。

---

## 7. FORGE 必需瞄具：近 / 中 / 远

**分档规则与数据**（`data/forge-constraints.json`，78 件瞄具，逐条带 `src`）：

- 近：固定 1×（`min == max == 1`）→ 34 件；
- 中：最高 ≤ 4×（含 1–4× 变倍，排除固定 1×）→ 27 件；
- 远：最高 > 4×（含 1–6×、1–8×）→ 17 件。

本轮修正 3 条误标（原按「名称疑似定倍」归入近档）：

| 瞄具 | 修正前 | 修正后 | 依据 |
| --- | --- | --- | --- |
| ELCAN SpecterDR 1x/4x | 1–1× / near | 1–4× / mid | 名称与上游描述的可变倍率，最高 4× |
| ELCAN SpecterDR 1x/4x FDE | 1–1× / near | 1–4× / mid | 同上 |
| Valday PS-320 1x/6x | 1–1× / near | 1–6× / far | 最高 6× > 4× |

复查：全部 78 条 tier 与 min/max 无冲突、名称区间无矛盾、id 与名称均存在于 `items.json`（`badTier=[]`、`nameMismatch=0`、`missing=0`）。

**真实兼容与优化约束（M4A1 实测）**

| 档位 | 当前枪械兼容瞄具数 | 选中样例 | 生成结果 |
| --- | --- | --- | --- |
| 近 | 23 | — | 列表只含 near 档（`bad=[]`） |
| 中 | 17 | Burris FullField TAC30 1-4x24 | 4 个方案全部 `constraintOk`，每行显示 `瞄具：Burris FullField TAC30 1-4x24…` |
| 远 | 17 | — | 列表只含 far 档（`bad=[]`） |

- 选中后 UI 显示 `当前：中 · 1–4× · Burris FullField TAC30 1-4x24 30 毫米 步枪瞄准镜`；点击「清除」恢复不受瞄具限制的优化；
- 选中瞄具通过 `cons.scopeId` 进入 `GB.optimize`：预装必装、允许自动补一级转接座、贪心后补装、应用前再走一次 `checkConstraints`；「应用」后画布上确实装上该瞄具（`应用方案后画布真的装上了所选瞄具`）；
- 若瞄具与枪械不兼容，则该档列表为空并提示「当前枪械在这个档位没有兼容瞄具」，不会静默忽略。

截图：[1920x919-F7-forge-panel.png](1920x919-F7-forge-panel.png)、[1920x919-07-forge-near.png](1920x919-07-forge-near.png)、[1920x919-08-forge-optic-selected.png](1920x919-08-forge-optic-selected.png)、[1920x919-09-forge-result-optic.png](1920x919-09-forge-result-optic.png)。

---

## 8. FORGE 战术设备：手电 / 激光

功能判定来自审计表 `forge-constraints.json` 的显式布尔（26 件设备：手电 13、激光 18、双功能 5），不按名称关键词推断；每件带 `src` 说明。

| 场景 | 结果 |
| --- | --- |
| 仅「手电」 | 4 个方案全部满足，实际设备 `Surefire XC1战术手电` |
| 「手电 + 激光」 | 由单件双功能设备 `Glock GTL 21 战术手电激光组合` 同时满足，4 个方案均通过终检 |
| 无兼容手电的枪械（MP-43-1C） | 4 个方案标红 `gw-forge-bad`，提示 `⛔ 当前枪械没有兼容的手电设备（真实槽位里找不到符合该功能的设备）`，「应用」按钮全部 `disabled` |

- 约束经 `cons.features = [{key,label,ids}]` 传入 `GB.optimize`，搜索与终检共用；允许「一件双功能」或「两件独立设备」两种满足方式；
- 结果行显示当前选中的功能与实际满足设备（`forgeBuildNote`），未满足时明确写「未满足」；
- 取消条件后恢复原优化行为。

截图：[1920x919-10-forge-light.png](1920x919-10-forge-light.png)、[1920x919-11-forge-light-laser.png](1920x919-11-forge-light-laser.png)、[1920x919-12-forge-infeasible.png](1920x919-12-forge-infeasible.png)。

---

## 9. R19.7 既有功能保留

- 中栏顺序：`LOAD VARIANT（含枪身图）→ 基础枪械信息 → 装配画布 → 属性条 → 整枪属性 → 隐藏属性`（实测顺序断言通过）；
- 基础枪械 / 改装槽位 / 已装配件仍在 `#gw-meta`，不混入整枪属性；属性无「实测 / 缺失」后缀，缺失只显示 `—`；
- 枪身图无「官方预设：…」文字；配件卡无右上角 ×（右键卸载保留）；
- 枪身左下角射速 `#55595e` 灰黑、DPS `#d02a1e` 红；未选弹药显示 `DPS —`；
- 战术设备仍按真实槽位布局（前握把左侧，空间不足进入子弹行下方独立末行）；
- 点击子弹格 → 右侧兼容弹药 → 选中写回子弹格 + DPS 更新；隐藏属性下方无内部槽位 ID / 合法数量 / 弹药长列表 / 公式调试文字；
- M4A1 五行九列布局与 `scope 空槽位 ↔ chandle` 对应关系未改动（`07`~`12` 截图与 `01-build` 可见）。

---

## 10. 两视口验收材料与测试结果

**测量文件**

- [1920x919-measure.json](1920x919-measure.json) — 52 步，0 失败，0 错误
- [1384x805-measure.json](1384x805-measure.json) — 52 步，0 失败，0 错误

**截图索引（`docs/r19.8-layout-audit/`）**

| 内容 | 1920×919 | 1384×805 |
| --- | --- | --- |
| 工作台整体 | `01-build.png` | 同 |
| 弹药候选 | `02-ammo.png`、`F6-ammo-rec-acc.png` | 同 |
| 保存预设 / 重新加载 | `F3-loadvar-save.png`、`03-preset-saved.png`、`04-preset-loaded.png` | 同 |
| 成本第三行 | `F4-stats-cost-row.png` | 同 |
| 逐部件价格 | `F5-parts-price.png` | 同 |
| 口径 / 种类筛选 | `F1-filter-caliber-primary.png`、`F2-filter-class-handgun.png`、`05`~`06` | 同 |
| FORGE 瞄具 | `F7-forge-panel.png`、`07-forge-near.png`、`08-forge-optic-selected.png`、`09-forge-result-optic.png` | 同 |
| FORGE 战术设备 | `10-forge-light.png`、`11-forge-light-laser.png`、`12-forge-infeasible.png` | 同 |

**自动化测试**

- `python -m pytest -q` → **952 passed, 1 skipped**（含本轮新增 18 条 `tests/test_r19_8_round.py`）
- `node tests/js/gun_builder_test.js` → **28 passed, 0 failed**
- 真实浏览器（CDP）：两视口各 **52 步全通过**，`rev = R19.8-9ac753b3`

---

## 11. 仍存在的数据缺口（未编造）

1. **弹药无跳蚤报价**：`data/ammo.json` 的 `flea` 全部为空，价格列只能用商人买入价（`buy.rub`）或基础参考价（`base`），tooltip 已明确标注，不冒充跳蚤价。
2. **物品库无倍率 / 功能字段**：`items.json` 没有 `zoom`、`flashlight`、`laser` 字段，瞄具分档与设备功能全部来自 `data/forge-constraints.json` 的审计映射，逐条带 `src`；覆盖范围为项目数据库内 78 件瞄具与 26 件设备，未收录的物品不会被强行塞档。
3. **部件跳蚤价是构建期快照**：来自 `items.json` 的 `p.a`（24h 均价），不是实时行情；缺失时显示 `—`。
4. **部分部件无商人买入报价**：时间线对应行显示 `—` 并在 `title` 说明，不按 0 计入。
5. **Silent / Loud 射击模式**：本地无「内置消音」字段，按钮保持禁用并注明原因，本轮未用名称关键字伪造筛选。
6. 瞄具倍率归类依赖上游名称/描述（如 `1x/4x`、`1-6x`），对无倍率标注且无可靠来源的瞄具不做猜测性归入。

---

## 12. 最终结论

六项要求均已在真实页面操作验证：预设可保存、刷新后仍在、可重新加载并恢复装配；弹药候选显示后坐力与 ACC（来自 `recoilModifier` / `accuracyModifier`）；整枪成本与改装件成本固定在第三行、金额与 `₽` 完整；逐部件价格左图标右价格且与配装界面共用取价函数；口径/种类两组筛选真实生效、选中态与列表结果一致、支持 AND 组合与清除；FORGE 近/中/远选出的具体瞄具确实进入优化结果并可应用，手电/激光约束参与实际优化，无解时明确提示且禁止应用。R19.7 的布局与交互约定全部保留。
