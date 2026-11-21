# R20 数据来源追溯文档（data-lineage）

> 生成：2026-10-29。撰写依据：`data/meta.json` 实际结构、各数据文件内部 `source` 字段、
> 生成脚本源码（`tools/fetch_data.py` 等）、`app.js` 消费点、以及 `tools/r20_validate_data.py`
> 的实际校验输出。**只记录，不修改任何数据。**
>
> 原则（任务书 5.3）：不把数据文件自动视为已授权；脚本中的 URL 不等于许可证明；
> 可访问不等于可复制/再分发/商用；推测来源一律标注"推断"；无证据的一律写"未知/待核实"。

---

## 1. 盘点总览

`data/` 目录实际存在 **26 个 JSON 文件**：

- **17 个业务数据文件**（§2 逐一记录；均被 `app.js` 实际加载，见各文件"数据用途"）。
- **9 个备份/快照文件**（§3 清单）。校验器按命名规则排除：
  文件名含 `.bak.json` 或以 `.prev.json` 结尾。

**游戏版本**：`meta.json` 与全部数据文件中**均无游戏版本字段**（已逐文件核实）。
各文件的适用版本**未知**，不得推断为已确认。

**统一哈希契约（重要，决定校验器行为）**：

| 哈希位置 | 语义 | 证据 | 离线可重验？ |
|---|---|---|---|
| `meta.sources[].sha256` | **抓取时上游响应字节**的哈希 | `fetch_data.py:981` 对下载的 `raw` 计算 | 否（需重新下载；本轮禁止联网） |
| `meta.sources[4..7]` 的 `sha256=e3b0c442...` | 空字节哈希 + `bytes:0`，表示"无下载物"（底图 SVG/瓦片/物品图标/自绘图标） | 同上 | 不适用 |
| `meta.items / gunslots / gunPresets` 引用的本地文件 | **R20.3 起首批 3 个文件带本地 `sha256`**（落盘文件字节哈希）| `fetch_data.py` 落盘字节变量 + R20.3 手工填入 | 是——校验器 C5 比对当前文件 |

**本地文件哈希（R20.3 首批建立，覆盖 `items.json` / `gunslots.json` / `gun-presets.json`）**：
落盘文件的 SHA-256，与 `sources[].sha256`（上游响应哈希）**分属两套，语义不同**。
初始基线日期 **2026-10-29**，取自当时磁盘文件的观察值——**这是"文件内容未变"的证据，
不是"内容正确"的证明**：来源许可、游戏版本适用性、历史漂移成因均仍未解决（见 §5）。
其余业务文件（maps/ammo/bosses 等 14 个）仍无本地哈希，属未覆盖项。

---

## 2. 业务数据文件逐项记录（17 个）

> "数据用途"列引用 `app.js` 真实行号（2026-10-29 核实）。
> "获取时间"区分：`generatedAt/updatedAt/fetchedAt`（文件内部记录的生成时间）与文件 mtime。
> "哈希"列只引用现有元数据或校验器实测，不写入原文件。

### 2.1 地图与地图资源

| 文件 | 内容 |
|---|---|
| 路径 | `data/maps.json` |
| 数据用途 | `app.js:649` 启动即加载；互动地图、撤离点、任务点、容器/物资标注的主数据（13 张地图） |
| 来源 | **已知**：tarkov.dev 地图配置（the-hideout/tarkov-dev，MIT）+ json.tarkov.dev 标注/中文翻译（`meta.sources[0..2]`）+ 文件内 `sources` 字段 |
| 许可 | 地图配置 **MIT**（meta 已记录）；**瓦片底图与 SVG 底图为 tarkov.dev 社区公开数据，非商业**（`meta.sources[4..5]`，其中 SVG 底图明确 **CC BY-NC-SA 4.0**）→ **本项目当前不可商用** |
| 游戏版本 | 未知（无字段） |
| 获取时间 | 文件内 `generatedAt: 2026-10-19T09:35:30Z` |
| 哈希 | 无本地哈希记录；上游快照哈希见 `meta.sources[1]`（离线不可重验） |
| 更新方式 | `tools/fetch_data.py`（另被 `build_poi_zh.py`/`fetch_tasks.py`/`roadnet.py` 等引用） |
| 风险与缺口 | 底图非商业许可是全项目商用约束；上游快照哈希无法离线复核 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/roadnet.json` |
| 数据用途 | `app.js` 加载（路线/寻路网格，按 maps 分表） |
| 来源 | **项目内推导**（`tools/roadnet.py` 从 maps.json 构建路网） |
| 许可 | 项目内派生物；**其上游承袭 maps.json 的底图/标注许可** |
| 游戏版本 | 未知 |
| 获取时间 | 文件内 `generatedAt: 2026-10-29T05:51:53Z`（**本轮审计当天早上生成，非本轮所写**；文件 mtime 早于本轮起点） |
| 哈希 | 无记录 |
| 更新方式 | `tools/roadnet.py` |
| 风险与缺口 | 无 |

### 2.2 任务数据

任务本体（任务列表/前置/目标）**不在 `data/*.json` 中**——由 `tasks.js` 管理，
抓取/校验链路为 `tools/fetch_tasks.py` + `tools/validate_tasks.py` + `tools/diff_tasks.py`。
本轮未逐一定位其落盘位置与结构，**如实标记：任务数据文件未纳入本轮逐项盘点**（待核实）。
`items.json` 内含 `tasks` 字段（任务相关物品引用），见 2.6。

### 2.3 枪械与改装数据

| 文件 | 内容 |
|---|---|
| 路径 | `data/gunslots.json` |
| 数据用途 | `app.js:8750` + `gun_builder.js`；配枪视图槽位树（163 枪 / 398 预设，schema 6） |
| 来源 | **已知**：tarkov.dev 内置预设（`Preset.containsItems`）+ 上游槽位关系构建期还原（meta `gunPresets`/`gunslots` 记录） |
| 许可 | meta 记录为 tarkov.dev 社区公开数据（间接记录于 sources）；**文件级许可声明：无** |
| 游戏版本 | 未知 |
| 获取时间 | 无内部时间字段；未知 |
| 哈希 | **本地 sha256 `29b987b34a931b6a…`（R20.3 填入，与当前磁盘文件一致，校验器 pass）**；`meta.gunslots.bytes=390016` vs 实际 390636（**bytes 仍为生成时刻快照，漂移 warning 保留**） |
| 更新方式 | `tools/fetch_data.py` 写出；`build_gear_icons.py`/`gunpresets.py`/`presets.py`/`r1922_assemble.py` 等多个脚本亦包含该路径（**多写者，风险**） |
| 风险与缺口 | bytes 漂移无法定位内容；多脚本写同一文件 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-compat.json` |
| 数据用途 | `app.js` 加载；配件兼容性（枪械 ↔ 配件允许关系） |
| 来源 | **已知**（文件内 `source`）：items 来自 `json.tarkov.dev/regular/items`，本地 items.json 同源 slots 推导 |
| 许可 | tarkov.dev 社区公开数据（文件内记录，meta 无对应条目）；再分发条款未见原文，**待核实** |
| 游戏版本 | 未知 |
| 获取时间 | 文件内 `source` 记录构建于 2026-10-22 |
| 哈希 | 无记录 |
| 更新方式 | **本轮未定位到单一生成脚本**（`build_weapon_compat.py` 引用该路径，待核实） |
| 风险与缺口 | 许可原文待核实 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-platforms.json` |
| 数据用途 | `app.js` 加载；枪械平台归类（AK/M4/SCAR 等系列映射） |
| 来源 | **项目内人工整理**（文件内 `source`：`build_weapon_compat.py` 的 PLATFORM_RULES 逐枪落表；上游无平台字段） |
| 许可 | 项目内自制 |
| 游戏版本 | 未知（平台归类随游戏新增枪械需人工维护） |
| 获取时间 | 2026-10-22（文件内） |
| 哈希 | 无记录 |
| 更新方式 | `tools/build_weapon_compat.py` |
| 风险与缺口 | 人工映射表，新枪需手工补录 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-stats.json` |
| 数据用途 | `app.js:8766`；枪械基础属性（人机/后坐/精度等） |
| 来源 | **已知**（文件内 `source` + `sourceKind`）：`json.tarkov.dev/regular/items` |
| 许可 | tarkov.dev 社区公开数据（同上待核实原文） |
| 游戏版本 | 未知 |
| 获取时间 | 文件内 `fetchedAt: 2026-10-24` |
| 哈希 | 无记录 |
| 更新方式 | `tools/build_gun_stats.py`（另被 `build_gun_images.py`/`r1922_assemble.py` 引用） |
| 风险与缺口 | 无明显缺口 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-rates.json` |
| 数据用途 | `app.js` 加载；射速/射击模式 |
| 来源 | **已知**（文件内 `source.url`）：`json.tarkov.dev/regular/items` 的 `properties.fireRate/fireModes` |
| 许可 | tarkov.dev 社区公开数据（同上待核实原文） |
| 游戏版本 | 未知 |
| 获取时间 | 2026-10-22（文件内） |
| 哈希 | 无记录 |
| 更新方式 | `tools/fetch_fire_rates.py` |
| 风险与缺口 | 无 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-layout-calibration.json` |
| 数据用途 | `app.js:8794/8797`；**人工校准**的枪械布局记录（R19 系列多轮迭代产物） |
| 来源 | **项目内人工校准**（用户手工调整） |
| 许可 | 项目内自制 |
| 游戏版本 | 不适用 |
| 获取时间 | 文件内 `updatedAt` 字段 |
| 哈希 | 无记录 |
| 更新方式 | 应用内人工校准流程 + `GWCalib` 导入导出；**约束：不得被自动流程改写** |
| 风险与缺口 | 属用户数据，任何自动更新流程必须将其排除 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gun-presets.json` |
| 数据用途 | `app.js` + `gun_builder.js`；枪械出厂/内置预设（373 条，25 条未解） |
| 来源 | **已知**：tarkov.dev 内置预设 + 本地槽位关系还原（meta `gunPresets`） |
| 许可 | tarkov.dev 社区公开数据（待核实原文） |
| 游戏版本 | 未知 |
| 获取时间 | 无内部时间字段 |
| 哈希 | **本地 sha256 `64e29bb5394bbd4a…`（R20.3 填入，校验器 pass）**；`meta.gunPresets.bytes=251064` 与实际 **一致**（无漂移） |
| 更新方式 | `tools/fetch_data.py` |
| 风险与缺口 | `unsolved: 25` 条预设未还原，属已知数据缺口 |

| 文件 | 内容 |
|---|---|
| 路径 | `data/gunsmith.json` |
| 数据用途 | `app.js` Gunsmith 抽屉；枪匠任务（`LV{等级} {任务名}`）的**真实装配约束**：属性要求（`buildAttributes`）、必含类别（`containsCategory`）、必装配件（`containsAll`）及其**装配链**（前端一键装配直接写入 `installed`） |
| 来源 | **直接从构建缓存原始任务数据抽取**（`build-cache/tasks-*.json` 的 objective 含 `buildAttributes`/`containsCategory`），补回了构建后 `data/tasks/tasks.<mode>.json` 漏掉的这两项；类别 id 经 `items.json` 的 `audit.categoryIds` 反查（如 `550aa4cd4bdc2dd8348b456c`→消音器） |
| 许可 | 任务内容同源 tarkov.dev / 上游任务库（沿用既有许可，文件级声明：无） |
| 游戏版本 | 同上游任务数据 |
| 获取时间 | 文件内 `generatedAt` 字段（R20.8 生成） |
| 哈希 | 校验器仅做**语义比对**（`fingerprint` 比较各模式 quest 的 id/objId/name/lvl/trader/gunId/attrs/cats/must），不逐字节（因 `generatedAt` 每次变化）；`build_gunsmith.py --check` 幂等通过 |
| 更新方式 | `tools/build_gunsmith.py`（离线，从 build-cache 读取，不联网）；产出 schema=1，三模式各 30 条共 90 条 |
| 风险与缺口 | `durability/height/width` 三项本地属性引擎无静态数据，校验时标「无法自动校验」；`effectiveDistance` 取 `gun-stats` 的 `eff`（不含枪管修正），已在 UI 注明 |

### 2.4 弹药数据

| 文件 | 内容 |
|---|---|
| 路径 | `data/ammo.json` |
| 数据用途 | `app.js` 加载；弹药库（弹道/穿甲/伤害） |
| 来源 | **推断**：tarkov.dev items 数据由 `tools/build_ammo.py` 构建（依据：`barriers.json.source` 明确引用"本地 data/ammo.json 的 pch，构建期取自 json.tarkov.dev/regular/..."；ammo.json 自身 `source` 字段为空） |
| 许可 | 随上游 tarkov.dev 社区公开数据（**文件内无许可声明，meta 无对应条目 → 待核实**） |
| 游戏版本 | 未知 |
| 获取时间 | 无内部时间字段；未知 |
| 哈希 | 无记录 |
| 更新方式 | `tools/build_ammo.py`（`build_weapon_compat.py` 亦引用该路径） |
| 风险与缺口 | **距离衰减/距离×护甲矩阵字段是否存在未核实**（R20 决策材料 D4 的前置）；许可待核实 |

### 2.5 护甲、装备及兼容性数据

护甲/装备属性存于 `data/items.json`（`pt` 分类 + `mod.*` 属性），**无独立护甲 JSON**。
兼容性见 2.3 的 `gun-compat.json` 与 `forge-constraints.json`。

| 文件 | 内容 |
|---|---|
| 路径 | `data/forge-constraints.json` |
| 数据用途 | `app.js:8819`； forge（配件安装约束：倍率/设备等安装规则） |
| 来源 | **已知**（文件内 `source`）：items.json 倍率标注 + 上游类别；HHS-1 按厂商规格人工核对 |
| 许可 | 项目内派生（上游承袭 items.json） |
| 游戏版本 | 未知 |
| 获取时间 | 2026-10-25（文件内） |
| 哈希 | 无记录 |
| 更新方式 | **本轮未定位到单一生成脚本，待核实** |
| 风险与缺口 | — |

### 2.6 物品数据库

| 文件 | 内容 |
|---|---|
| 路径 | `data/items.json` |
| 数据用途 | `app.js:5127`；全站物品库（5480 条），配装/配枪/弹药/任务引用的数据枢纽；内含 `traders`/`tasks`/`audit` 字段 |
| 来源 | **已知**：`json.tarkov.dev/regular/items`（含中文翻译，`meta.sources[3]`） |
| 许可 | meta 记录 tarkov.dev 社区公开数据；原文条款**待核实** |
| 游戏版本 | 未知（meta 无版本字段） |
| 获取时间 | meta `generatedAt: 2026-10-20T15:10:05Z`；文件 mtime 2026-10-29 13:52（其后仍被 R19 轮脚本修改过） |
| 哈希 | **本地 sha256 `ac81f0aa82ef456f…`（R20.3 填入，与当前磁盘文件一致，校验器 pass）**；`meta.items.bytes=6094867` vs 实际 6093854（**bytes 仍为生成时刻快照，漂移 warning 保留**） |
| 更新方式 | `tools/fetch_data.py` 主写者；**另有 7 个脚本包含该路径**（build_ammo/build_gun_stats/build_weapon_compat/fetch_tasks/r1922_assemble/r1926_datafix/r1929_datafix/slotfix）——**多写者是本文件最大结构性风险** |
| 风险与缺口 | bytes 漂移；多脚本写同一文件；`audit` 字段标注部分字段为推导值（非服务器真值）。**R20.1 实证**：全量 pytest 会经 `test_r19_21_round.py` → subprocess 执行 `tools/r1929_datafix.py` **幂等重写本文件**（json.dump 紧凑格式，字节数不变，mtime 随测试更新）——旧测试行为，未改动 |

### 2.7 Boss、障碍物等模拟器数据

| 文件 | 内容 |
|---|---|
| 路径 | `data/bosses.json` |
| 数据用途 | `app.js` 加载；Boss 名录/刷新池/装备（供地图与模拟器） |
| 来源 | **已知**（文件内 `source.pages`）：escapefromtarkov.fandom.com Wiki（人工整理），**非 tarkov.dev** |
| 许可 | **未知/待核实**：Fandom Wiki 内容通常为 CC BY-SA 系，但项目内**无许可记录**；生成脚本 `build_boss_data.py` 抓取时未记录许可 |
| 游戏版本 | 未知 |
| 获取时间 | 2026-10-22（文件内） |
| 哈希 | 无记录 |
| 更新方式 | `tools/build_boss_data.py`（显式传代理抓取） |
| 风险与缺口 | **许可证据缺失**（2.4 原则：不得默认 wiki 内容可复制再分发）；无刷新概率字段（R20 决策 D3 依据） |

| 文件 | 内容 |
|---|---|
| 路径 | `data/barriers.json` |
| 数据用途 | `app.js` 加载；逐发模拟器的障碍物穿透参数 |
| 来源 | **已知**（文件内 `source`）：ammo.json 的 `PenetrationChanceObstacle`（构建期取自 json.tarkov.dev）+ 其余字段文件内注明 |
| 许可 | 承袭 ammo.json 上游；**文件级待核实** |
| 游戏版本 | 未知 |
| 获取时间 | 2026-10-22（文件内） |
| 哈希 | 无记录 |
| 更新方式 | **本轮未定位到单一生成脚本，待核实** |
| 风险与缺口 | — |

| 文件 | 内容 |
|---|---|
| 路径 | `data/combat-targets.json` |
| 数据用途 | `app.js` 加载；模拟器靶标部位/血量 |
| 来源 | **已知**（文件内 `source.pages`）：escapefromtarkov.fandom.com Wiki（Health system 页面截图人工整理） |
| 许可 | **未知/待核实**（同 bosses.json：Fandom 内容无项目内许可记录） |
| 游戏版本 | 未知 |
| 获取时间 | 无内部时间字段；未知 |
| 哈希 | 无记录 |
| 更新方式 | **本轮未定位到单一生成脚本，待核实** |
| 风险与缺口 | 同 bosses.json |

| 文件 | 内容 |
|---|---|
| 路径 | `data/caliber-groups.json` |
| 数据用途 | `app.js` 加载；口径分组（弹药视图筛选） |
| 来源 | **项目内人工归类**（文件内 `source`：以 gun-compat 实际 29 个口径为全集逐项人工归类；`categoriesFrom: 用户指定`） |
| 许可 | 项目内自制 |
| 游戏版本 | 不适用（口径公称值） |
| 获取时间 | 无内部时间字段 |
| 哈希 | 无记录 |
| 更新方式 | **本轮未定位到单一生成脚本，待核实** |
| 风险与缺口 | 人工维护表 |

### 2.8 元数据

| 文件 | 内容 |
|---|---|
| 路径 | `data/meta.json` |
| 数据用途 | `app.js:650`（失败可容忍，catch null）；数据目录自描述：schema 8、来源清单（8 条）、覆盖率统计、本地文件引用（items/gunslots/gunPresets/icons/traderIcons） |
| 来源 | 项目内生成（`tools/fetch_data.py`） |
| 许可 | 不适用 |
| 游戏版本 | **无该字段**（只有 `gameMode: "regular"`，模式 ≠ 版本） |
| 获取时间 | `generatedAt: 2026-10-20T15:10:05Z` |
| 哈希 | 即哈希契约载体本身（见 §1） |
| 更新方式 | `tools/fetch_data.py`（`_merge_sources` 去重合并来源） |
| 风险与缺口 | 本地文件引用缺 sha256（契约缺口）；无游戏版本字段 |

### 2.9 图标资产（非 JSON，meta 引用）

- `assets/icons-items`（5480 个物品图标）：meta `sources[6]` 记录来自 assets.tarkov.dev，
  **tarkov.dev 社区公开数据（署名 + 非商业）**。
- `assets/icons-traders`（16 个商人图标）：**项目内自绘**，meta `traderIcons.license` 明记
  "项目内自制，无第三方素材与再分发限制"，含 manifest。本轮未逐文件审计（超范围）。

---

## 3. 备份/快照文件清单（9 个，校验器排除）

`gun-layout-calibration.json.bak.json`、`gun-layout-calibration.json.prev.json`、
`gun-layout-calibration.json.r1918.bak.json`、`gunslots.json.r1919.bak.json`、
`gunslots.json.r1920.bak.json`、`items.json.r1918.bak.json`、`items.json.r1919.bak.json`、
`items.json.r1920.bak.json`、`items.json.r1921.bak.json`。

为各轮次改动前的手动快照。**风险**：备份散落在 data/ 业务目录内，与业务文件同层，
易被误当成业务数据；建议未来轮次迁移到独立备份目录（本轮不执行）。

---

## 4. 数据更新流程现状（只记录，不改造）

### 4.1 现有流程

| 脚本 | 输入 | 输出 | 说明 |
|---|---|---|---|
| `tools/fetch_data.py` | json.tarkov.dev 各端点（显式代理参数） | `data/maps.json`、`data/meta.json`、`data/items.json`、`data/gunslots.json` | 主更新器；对上游响应计算 sha256 写入 `meta.sources[]`；`_merge_sources` 做来源去重 |
| `tools/build_boss_data.py` | Fandom Wiki | `data/bosses.json` | 抓取脚本内显式传代理 |
| `tools/build_gun_stats.py` / `fetch_fire_rates.py` | json.tarkov.dev | `data/gun-stats.json` / `data/gun-rates.json` | 显式代理 |
| `tools/build_weapon_compat.py` | items + gunslots | `data/gun-platforms.json`（并引用 ammo/gun-compat） | 平台规则人工维护 |
| `tools/roadnet.py` | maps.json | `data/roadnet.json` | 派生计算 |
| `tools/validate_tasks.py` / `diff_tasks.py` / `fetch_tasks.py` | 任务数据 | 任务链路校验/差异 | 独立子体系 |
| `tools/r20_validate_data.py` | 本地 data/ | 校验报告（docs/r20/） | **本轮新增**；只读 |

### 4.2 现有缺口（任务书 5.4 要求如实记录）

1. **更新前无校验门禁**：`fetch_data.py` 写盘前不跑结构校验；本轮新增的校验器是独立只读工具，未接入任何写流程（接入属后续决策）。
2. **无差异审计**：更新前后无自动 diff 报告；`diff_tasks.py` 只覆盖任务子体系。
3. **备份流程未固化**：`.bak` 文件存在但为各轮手动复制，无统一命名规范与保留策略。
4. **回滚 = 手动恢复 bak**，无工具化回滚。
5. **本地文件哈希只覆盖 3 个文件**（R20.3 首批：items/gunslots/gun-presets）；其余 14 个业务文件仍只能靠 bytes。
   且**旧 datafix 脚本（`r1926_datafix.py` / `r1929_datafix.py`）改写数据后不更新 meta**——
   一旦它们再次改动 items.json，校验器将报 **sha256 不匹配（error）**。这是**有意的暴露**，
   不得为消除该错误而自动刷新哈希（正确处置见 R20.3 报告 §11）。
6. **多写者问题**：items.json / gunslots.json 被 5–8 个脚本读写，漂移责任不可追溯。
7. **许可证据不完整**：bosses/combat-targets（Fandom 来源）与多个 tarkov.dev 派生文件无文件级许可声明。

---

## 5. 来源与许可汇总

| 来源 | 涉及数据 | 许可记录 | 证据强度 |
|---|---|---|---|
| the-hideout/tarkov-dev 地图配置 | maps.json（配置部分） | MIT | **已记录**（meta.sources[0]） |
| json.tarkov.dev（标注/翻译/物品/枪械属性） | maps/items/gunslots/gun-stats/gun-rates/gun-compat/ammo（推断） 等 | "tarkov.dev 社区公开数据"，**原文条款未见** | 部分证据（meta 有记录，原文待核实） |
| assets.tarkov.dev（物品图标/底图） | assets/icons-items、瓦片与 SVG 底图 | **CC BY-NC-SA 4.0 / 非商业**（sources[4] 明记） | **已记录** → 全项目不可商用 |
| escapefromtarkov.fandom.com Wiki | bosses.json、combat-targets.json | **未知** | 仅 URL，无许可记录 → **待核实** |
| 项目内自制/人工整理 | roadnet、caliber-groups、gun-platforms、forge-constraints、gun-layout-calibration、trader 图标 | 项目内自制 | 已记录（文件内 source 字段） |
| db4tarkov / eftarkov | —（未采用） | 未采用：无公开许可 / 许可未明（R20 审计结论） | — |

**明确未验证项**：所有"tarkov.dev 社区公开数据"的**原文许可条款**（是否允许再分发、
是否允许商用、署名要求）本轮未联网核实，一律**不得视为已确认**。

---

## 6. 校验器与本文档的关系（R20.1 复核后）

`tools/r20_validate_data.py` 对上述契约的落地：

**检查项状态语义（R20.1 统一，报告 `checks[].result` 取值）**：

| 状态 | 含义 |
|---|---|
| `pass` | 当前检查通过，没有发现该项问题 |
| `warning` | 存在非阻断问题，需要人工关注（对应 `issues[].severity=warning`） |
| `fail` | 存在硬性错误，或该检查明确无法满足必要条件（对应 `issues[].severity=error`） |
| `skipped` | 因前置条件不满足而未执行 |

汇总 `status`：存在硬性错误 → `fail`（退出码 1）；只有警告无硬性错误 → `pass`（退出码 0，warnings 数保留）。

**C1–C6 与状态的对应**：

- C1 文件解析/顶层类型：解析失败、顶层非 dict → fail（error）；通过 → pass。
- C2 覆盖兜底：白名单外未归类 JSON → **warning**（非阻断，不降级为 fail）。
- C3 schema 标记：缺失 → fail。
- C4 meta 结构：缺必备键 → fail；meta 未解析 → C5/C6 skipped。
- C5 本地引用：引用不可达 / sha256 不匹配 / sha256 格式非法 → **fail**（error，退出码非零）；
  仅 bytes 漂移 → **warning**（不误报硬失败）；**缺 sha256 字段 → warning**
  （"未完成哈希验证"，不得静默当作已通过）；干净 → pass。
- C6 sources：哈希格式非法等硬错误 → fail；仅 name/license/url 缺失 → warning；干净 → pass。

**meta 本地引用的路径契约（R20.1 严格解析）**：必须是形如 `data/<文件名>.json` 的相对字符串；
拒绝绝对路径、盘符、`..`/`.` 路径段、多级子目录、空段与非字符串值；
**不做** `Path.name` 截取——非法引用原样拒绝，不允许丢弃目录部分转换成其他有效文件；
错误信息同时给出原始引用与拒绝原因。符号链接先于 `resolve()` 判定，按保守策略跳过。

**执行的检查**：白名单 17 文件逐一解析 + 顶层类型 + schema 标记；meta 必备键；
meta 本地引用存在性 + bytes 比对 + 若有 sha256 则比对；sources 格式（含无下载物条目识别）；
白名单外 JSON 归类兜底；备份按命名规则显式排除。

**明确不执行**：上游快照 sha256 重验（需联网）、计数字段核对（口径未定位）、图标逐文件审计、
人工校准语义校验（属应用层业务规则）。
