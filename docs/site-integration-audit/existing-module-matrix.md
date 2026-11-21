# 现有工程能力盘点（R20 第二阶段 4.1）

> 审计基准：**当前磁盘** `D:\personal\trae\02-塔科夫\eft-interactive-map`，分支 `main`，HEAD `bf438df`，工作区 345 条未提交改动。
> **不采信 R19.29 报告的历史结论**，凡下文标「已核实」的均由本轮重新命令验证。
> 采集命令见每节末尾。

## 0. 工程硬指标（已核实）

| 项 | 值 |
|---|---|
| 代码规模 | `app.js` 19,753 行 / `tasks.js` 3,041 / `gun_builder.js` 1,403 / `calibrator.js` 900 / `combat_sim.js` 679 / `i18n.js` 376 |
| 数据文件 | `data/*.json` 26 个；`items.json` 5.9MB、`maps.json` 2.0MB、`gunslots.json` 381KB、`gun-stats.json` 318KB、`gun-presets.json` 245KB、`gun-layout-calibration.json` 205KB、`gun-compat.json` 162KB、`bosses.json` 134KB、`ammo.json` 89KB |
| 界面视图 | **5 个**：`map` / `loadout` / `gun` / `ammo` / `tasks`（`index.html` `data-view`） |
| 测试 | `tests/*.py` **64 个文件**；完整套件 **1337 passed / 5 failed / 1 skipped**（83.07s，本轮实测） |
| 构建工具 | `tools/*.py` 30+ 个（`fetch_data` `fetch_tasks` `build_ammo` `build_boss_data` `build_gun_stats` `build_weapon_compat` `diff_tasks` `eftlog` …） |
| 数据血缘 | `data/meta.json` 已记录 `schema:8` / `generatedAt` / `sources[]`（含 **license: MIT**、**sha256**、bytes） |
| 离线 | 运行期无外部请求（R19.29 浏览器验收 463 次请求全为 `127.0.0.1`） |

---

## 1. 模块矩阵（对应任务书 4.1）

状态口径：**已实现且有测试证明** / **已实现但验证不足** / **部分实现** / **尚未实现** / **数据缺失** / **需要产品决策**

| 模块 | 状态 | 已核实的事实 | 缺口 |
|---|---|---|---|
| **互动地图** | 已实现且有测试证明 | `map` 视图；`maps.json`（`schema/gameMode/generatedAt/sources/maps`，2MB，来自 tarkov.dev maps.json + json.tarkov.dev 标注，MIT）；`roadnet.json` 11KB、`barriers.json` 4KB；`tools/roadnet`、`test_roadnet.py` 等 | 无「画笔标注」；无「Boss 刷新概率」（见 §3） |
| **任务系统** | 已实现且有测试证明 | `tasks` 视图 + `tasks.js` 3,041 行；`data/tasks/` 按模式分：`tasks.regular/pve/pvps.json`、`guides.*.json`、`index.json`、`diff-report.json`、`raw/`；进度 `localStorage: eftmap.tasks.progress.v1`（按模式隔离）+ 导入/导出 | 无全站「任务树」可视化（只有前置关系数据） |
| **物品数据库** | **部分实现** | `items.json` 5.9MB 是唯一物品真相源；被枪械构建、配装、任务、地图共用；全局搜索框 `输入名称（撤离点 / 物资 / Boss…）` 面向地图 | **没有独立物品浏览页**（无「按部位/类别」列表）；无物品详情面板（详情嵌在构建器/配装里） |
| **弹药数据库** | 已实现且有测试证明 | `ammo` 视图 + `data/ammo.json` 89KB（`tools/build_ammo.py` 构建）；弹药搜索、筛选、图表 `am-graph`、模拟 `am-sim` | 无「距离 × 护甲等级」矩阵（db4 有）；距离衰减需核对数据 |
| **枪械构建器** | 已实现且有测试证明 | `gun` 视图；`gun_builder.js` 1,403 行；`gunslots.json` 163 把；`gun-stats`/`gun-presets`/`gun-compat`/`gun-layout-calibration`；6×9 布局引擎 + 校准器 `calibrator.js` 900 行；`window.GWCalib` 接口 | 视图维度单一（db4 有 Gunsmith/TierMaker/Streamer/Variant/Saved 五视图） |
| **装备配装工作台** | 已实现且有测试证明 | `loadout` 视图；纸娃娃 + 插板/内衬/防护区域；预设存 `%APPDATA%\EFTMap\loadout-presets.json`；`window.GWLoadout` 接口 | 无 Buy/Sell 双口径成本汇总；无「装备前后对比」 |
| **逐发射击模拟器** | 已实现且有测试证明 | `combat_sim.js` 679 行：逐发结算、护甲分层（硬插板→头盔→软内衬）、方向性（front/back/left/right/all）、障碍物、出口模型、约束白名单；**证据分级 verified/estimated/missing** 记录在 `docs/r15-fixes/`、`docs/r16-completeness/` | 无「混压弹匣 + 射速时序」可视化（部分在 `gun-rates.json`） |
| **商人及交易** | **数据缺失** | `app.js` 仅 23 处 `trader`（`traderRec`/`traderName`/`traderIconUrl`），用于任务与物品来源展示 | **无价格表/无等级解锁/无 barter/无 craft/无跳蚤行情**；`data/` 无对应文件 |
| **个人进度** | 部分实现 | 任务进度（localStorage，按模式）+ 配装预设（APPDATA 文件）+ `eftmap.gwmode`/`eftmap.gwsim.v1`；导入导出有校验（格式非法不覆盖） | 进度**分散在 3 套存储**，无统一「我的进度」视图/导出包 |
| **数据更新** | 部分实现 | `data/meta.json` 有 `sources[]`+`license`+`sha256`；`tools/fetch_data.py`、`fetch_tasks.py`、`diff_tasks.py`（产出 `data/tasks/diff-report.json`） | 无「用户可点的更新流程」（对比/确认/回滚）；无更新后回归门禁 |

---

## 2. 与 R19.29 报告的差异核对（任务书 4 节要求）

| R19.29 报告的说法 | 当前磁盘实际 | 结论 |
|---|---|---|
| 完整测试「1337 passed / 5 failed / 1 skipped」 | 本轮重跑：**1337 passed / 5 failed / 1 skipped**（83.07s） | **一致** |
| 5 项历史失败 | 同 5 项：`test_r19_11` / `test_r19_13::row2_anchors` / `test_r19_1::candidate_columns` / `test_r19_5::zoning` / `test_r6_gun_workbench` | **一致**，至今未修 |
| 「部分布局审计文件仍与当前引擎存在差异」 | `docs/r19.15.3-layout-audit/` 下 3 个旧产物（`ak-dovetail-final` / `ak-dovetail-optic-chain` / `layout-conflicts`）未随引擎重生成 | **一致** |
| 版本 `AM_BUILD="R19.29"` | `grep` 确认 16706 行 `var AM_BUILD = "R19.29"` | **一致** |

> 注意：`AM_BUILD` 行尾注释仍写着「与 index.html 的 `?v=r19.28` 同步改」，属**注释过期**（`index.html` 实际已是 `?v=r19.29`）。属文档瑕疵，本轮不改（审计阶段不动代码）。

---

## 3. 数据资产逐个核对（决定「能复用还是要新建」）

| 文件 | 关键结构（已核实） | 可支撑的新功能 |
|---|---|---|
| `items.json` | 5.9MB，含 `mod.r`（后坐力）、`mod.e`（人机）、`pt`（类别）、`slots`、`allow` | 物品库、搜索、价格列（`cost`） |
| `maps.json` | `maps{}` → 每图含配置/标注，来源 tarkov.dev（MIT） | 地图、标记、任务点 |
| `gunslots.json` | 163 把枪的真实槽位树 `slots[].allow` | 构建器、兼容性 |
| `gun-compat.json` | 162KB 兼容矩阵 | 「这个配件能装哪些枪」反查 |
| `gun-layout-calibration.json` | 397 条人工校准 / 152 把枪 | 布局稳定性 |
| `bosses.json` | `bosses[]` 17 条 + `elites`；每人 `health`（分部位）+ `equipment`（armor/helmets/faces/plates/weapons）+ `confidence` + `missing[]` + `sourcePage`（fandom） | Boss 页、逐发模拟目标 |
| `ammo.json` | 89KB 弹药属性（`tools/build_ammo.py`） | 弹药表、模拟 |
| `gun-rates.json` | 22KB 射速 | 模拟时序 |
| `combat-targets.json` | 2KB | 模拟目标 |
| `barriers.json` / `roadnet.json` | 障碍物 / 路网 | 模拟、路线 |

**缺失的数据（决定新模块必须新建数据，而不是「改改页面」）**：
1. 商人（等级、库存、解锁条件）
2. 价格（跳蚤/商人，任何时间口径）
3. Barter 交换配方
4. 藏身处（区域、等级、材料）
5. Craft 制作配方
6. Boss **刷新概率**（`bosses.json` 无 `spawnChance` 类字段，已核实）
7. 弹药**距离衰减 / 护甲等级矩阵**（`ammo.json` 需核对，未确认含矩阵）

---

## 4. 复用友好度评估（为第四阶段铺路）

| 现有能力 | 复用方式 | 风险 |
|---|---|---|
| `window.GB`（gun_builder） | 新模块直接调用 `GB.compute` / `GB.buildTree` | 低 |
| `window.GWCalib` / `window.GWLoadout` | 已有稳定接口，可被新页面复用 | 低 |
| `items.json` 单真相源 | 新模块只读，不复制 | 低 |
| `data/meta.json` 血缘机制 | 新数据包沿用同结构（`sources[]`+`license`+`sha256`+`generatedAt`） | 低 |
| 5 视图导航 | 新增入口需改 `index.html` 顶栏与 `data-view` 机制 | **中**（任务书 7.2 要求先提最小变更方案） |
| 64 个测试文件 | 新模块加**加性**测试，不动旧测试 | 低 |

---

## 5. 采集命令（可复现）

```bash
git branch --show-current && git log --oneline -1 && git status --porcelain | wc -l
node --check app.js
ls -S data/*.json | head -30
grep -o 'data-view="[a-z]*"' index.html | sort -u
wc -l app.js tasks.js gun_builder.js combat_sim.js i18n.js calibrator.js
/c/Python314/Scripts/pytest tests -q --tb=line -p no:cacheprovider
```
