# R19.29 交付报告（定点修复与回归验证）

> 项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`
> 本轮范围：任务 A（光学配件子槽定位）/ 任务 B（战术槽冲突动态避让）/ 任务 C（修正 R+E/3）/ 任务 D（静态审计产物一致性）
> 结论口径：**已核实**（有产物或命令输出）/ **估算**（按规则推算，未逐一实测）/ **未知**（无法验证）——正文逐条标注。

---

## 1. Git 分支与工作区状态

| 项 | 值 | 口径 |
|---|---|---|
| 分支 | `main` | 已核实（`git branch --show-current`） |
| 初始工作区 | 大量未提交改动，`git status --porcelain` 共 345 条（`M app.js` / `M index.html` / `M data/*.json` / `?? docs/r19.29*` / `?? assets/*` 等） | 已核实 |
| 最终工作区 | 同上，仍为 345 条类目（本轮只改文件，未 `git add` / `git commit` / `git push`） | 已核实 |
| 是否执行 reset / clean / 强制检出 | **否** | 已核实 |
| 是否覆盖发布版本（`release/` `dist/` `build/`） | **否** | 已核实 |

> 残留清理：本轮为做「失败归因基线」曾在工程内建过 `.r19_29_baseline/` 临时副本，比对完成后已整目录删除（`rm -rf .r19_29_baseline`），未动任何用户数据。

---

## 2. 修改文件及目的

### 2.1 生产代码

| 文件 | 位置 | 目的 |
|---|---|---|
| `app.js` | `gwBuildLayout` 第 9 阶段后新增 `9.5) R19.29 任务A` IIFE | 光学（scope）子槽若落在父件**同排或下方**，搬回父件同列上方 |
| `app.js` | `gwApplyCalibToLayout` 之前新增 `gwReflowTacticalKids()` + 第 `6.5)` 步调用 | 任务 B：战术类父件的子槽回父件同行右邻格；该格被独立槽位占用时，独立槽位沿本行右移 |
| `app.js` | `gunRE3()` | 任务 C：`Math.abs(r)*100 + e/3` → `(-r)*100 + e/3`（不取绝对值，符号只反转一次） |
| `app.js` | `COL_RE3.render` 的 `title` | 任务 C：标题改为「正面增益」语义（减少为正、增加为负） |
| `app.js` | `AM_BUILD = "R19.29"` | 版本标记 |
| `index.html` | 15 处 `?v=r19.28` → `?v=r19.29` | 静态资源缓存串 |
| `tools/serve.py` | `"rev": "R19.29-" + digest` | 构建标记同步（原停留在 R19.27，导致 4 项旧测试长期红） |

### 2.2 测试与工具（新增，均为加性）

| 文件 | 作用 |
|---|---|
| `tools/r19_29_taska.js`（新） | 任务 A 全量审计：`default` + `filled` 两场景，输出 `docs/r19.29/task-a.json`，打印 `CHECK_TASKA` |
| `tools/r19_29_taskb.js`（新） | 任务 B 全量场景 + 7 组合成用例，输出 `docs/r19.29/task-b.json`，打印 `CHECK_TASKB` |
| `tools/r1933_accept.py`（新） | R19.29 真实浏览器验收（CDP），输出 `docs/r19.29/browser-accept.json` + `shots/*.png` |
| `tests/test_r19_29_round.py`（新） | 8 项专项断言（A/B/C/D 全覆盖），不触碰任何既有用例 |
| `tools/r19_28_unit.js`（上一轮已改，本轮沿用） | 任务 C 单元测试 44 项（含任务书 4 个示例） |
| `tests/test_r19_28_round.py`（上一轮已改） | 由写死 `41/41` 改为「N/N 通过」正则，避免总数写死后误报 |
| `tests/test_r19_15_3_round.py::test_04`（上一轮已改，任务 D） | 用结构签名 `akRearFamily` 区分 AK 照门系（r2c6）与非 AK（r2c8），保留「非 AK 样本 ≥3」的原保护目的 |
| `tools/r1923_audit.js`（上一轮已改，任务 D） | 生成器补 `isAkRearSightGun` + AKMP 子槽「父件正上方」判定，消除 8 条误报 |

### 2.3 静态审计产物

| 文件 | 处理 | 说明 |
|---|---|---|
| `docs/r19.15.3-layout-audit/ak-dovetail-sight-layout.json` | **用现有生成流程重新生成** | 上一轮任务 D 完成；`violations: []`、`akmpAbove: 8`、`rearSightAtC6: 20/20` |
| `docs/r19.13-layout-audit/{slot-mapping,foregrip-chains,muzzle-chains,handguard-extras}.json` | **用现有生成流程 `node tools/r1913_audit.js` 重新生成** | 本轮必须做：任务 A 曾把 Saiga 瞄具子槽上提，导致 `handguard-extras.json` 出现 2 条 spill；修正规则后重生成回到 `spills: []`、`inRow6: 127/130` |
| `docs/r19.15.3-layout-audit/{ak-dovetail-final,ak-dovetail-optic-chain,layout-conflicts}.json` | **未重生成** | 引擎已演进（`dovetailGuns 28→30` 等），重生成会产生大量与本轮无关的差异；按「不确定就记录不删」原则保留旧快照，见 §10 风险 6 |
| `data/gun-layout-calibration.json` | **未改** | 397 条记录 / 152 把枪，`sha256: d0a811f41a95b2dd…`；任务 B 探针每次运行都复核「文件字节未变」 |

---

## 3. 任务 A：光学配件子槽定位

### 3.1 实现

在 `gwBuildLayout` 第 9 阶段（前握把钉位）之后、第 10 阶段（顶部扩展收口）之前插入幂等 IIFE `opticScopeKidsAbove()`：

- **只处理一种确定结构**：`baseOfPath(parent) === "scope"` 且 `baseOfPath(child) === "scope"`（父子关系判定，不看枪名/物品名）。
- 仅当子槽落在**父件同排或下方**（`child.row >= parent.row`）时才搬：目标格 `(parent.row-1-idx, parent.col)`，逐格向上找第一个「非占用且非 reserved 锚点」的格；找不到时写 `exceptions` 诊断，不覆盖任何槽位。
- **明确不动**：`sight_rear`（照门带 r2c6/r2c7 被 R19.15.3 锁定）、`tactical`（本就进第 6 行）、`mount`（燕尾槽/镜座各自链路）。
- **护木链例外**：父件路径以 `mod_handguard/` 开头时**直接跳过**。原因：R19.13 的 `handguard-extras.json` 锁定「护木附件整体留在第 6 行、`spills` 必须为空」，把链上瞄具子槽上提会同时把整卡片顶下一行并记成 spill。两条不变量冲突时保留既有 R19.13 约束。

### 3.2 实际影响面（已核实）

用「同一份源码，去掉 9.5 段 vs 保留」对跑全部枪械：

| 场景 | 坐标差异格数 | 说明 |
|---|---|---|
| `default`（默认预设，100% 枪械） | **0** | 说明修复对现有默认布局**零改动**，不存在回归面 |
| `filled`（给空的瞄具父槽装子槽最多的候选件） | **1** | NL545 (GP)：`d_reciever/mod_handguard/mod_scope/mod_scope` 由 `r6c4`（父件同排右侧）→ `r5c3`（父件 r6c3 正上方），即任务书要求的「明确上下层级」 |

### 3.3 审计结论（`tools/r19_29_taska.js`，205 组 scope→scope 配对）

| 判定 | 数量 | 含义 |
|---|---|---|
| `OK_IMMEDIATE` 紧邻正上方同列 | 82（default 7 / filled 75） | 完全符合任务 A |
| `FAR_UP` 同列但被锚点拉开 | 4 | 列正确、行被子弹/弹匣锚点占位拉开 |
| `DIFF_COL` 上方但异列 | 112 | 顶部锚点列分配（r2c5→子槽 c6/c7）等 R19.15.3 既有设计 |
| `AT_OR_BELOW` 同排或下方（硬违规） | 7 | **全部命中白名单**：Saiga-12K×4（护木链，R19.13 锁定）+ AS「巨浪」MOD.4×3（10 条人工校准决定） |
| **未豁免硬违规** | **0** | ✅ |
| 合规结构种类（default） | **3** | `top-anchor`×4、`receiver-direct`×2、`dovetail-mount`×1 |

> 任务书要求「AK 系 / 燕尾槽 / M10 安装座至少三种结构自动化验证」：本报告用**结构性签名**分类（父件挂载链形态），落到的三类是 `receiver-direct`（机匣直挂瞄具）、`dovetail-mount`（燕尾槽基座）、`top-anchor`（顶部锚点瞄具槽），覆盖 AK 系（AK 类机匣直挂）、燕尾槽（Saiga 红线 r2c8→r1c8）、上机匣/机匣顶导轨链路（G36/MCX/Aklys 等）。**已核实**，非按枪名硬编码。

---

## 4. 任务 B：战术槽冲突动态避让

### 4.1 实现

新增独立函数 `gwReflowTacticalKids(cells, nodes, info)`，在 `gwApplyCalibToLayout` 的第 5 步（显示坐标换算）之后、第 8 步（`byKey` 生成）之前调用（新增 `6.5)` 步）：

**结构前提**：父件基名属于战术类（`tactical|flashlight|laser|devices|emitter`）且落在第 5 行及以下时，它现场生成的子槽结构位 = **父件同行右邻格** `(parent.row, parent.col+1)`。

**三种分支**（均只改 `L.cells` 的 `row/col`）：

1. 右邻格已被**独立槽位**占用 → 让该独立槽位沿本行向右，`col+1 … 9` 逐个试探，取第一个**整段占格都空**的位置（`spanW()` 按 `cells.w` 计算宽度，当前引擎每槽 1 格）；找到则右移并记 `info.reflow`，子槽落到右邻格。
2. 右邻格空着 → 子槽直接回右邻格（避免「右邻空着却挂在别处」）。
3. 行内无空位 → 记 `info.conflicts`（含 `want` / `blockedBy` / 原因），**坐标一律不动**，绝不静默覆盖。

**不让位判定**（保守）：`blocker.fixedAnchor`（`GW_FIXED_SLOT` 固定坐标）、同一挂载链（互为祖先/后代）、同一父件下的兄弟子槽、固定锚点格（body/stock/mag/grip/ammo/charge/stockChild/stockChild2/bad）。

**幂等/不漂移**：每次布局都从「自动布局 + 校准」重新算；同一份 `L` 重复调用时子槽已在结构位，第二遍直接跳过（`B4` 用例与 61 例真实场景均实测 3 次结果一致）。

### 4.2 为什么放在校准之后

真实冲突**全部由人工校准**把父件从第 5 行搬到第 6 行引起（例如 SCAR 系 `mod_tactical_000→r6c1`、`mod_tactical_001→r6c2`、镜座 `mod_mount_001→r6c3`）。纯自动布局不会产生这种同格争用（全枪 `default` 场景 `reflow=0`、`conflict=0`，已核实）。

### 4.3 验证结果（`tools/r19_29_taskb.js`）

| 指标 | 结果 | 口径 |
|---|---|---|
| 真实场景（枪 × 装带子槽配件） | **61 例 / 36 把枪** | 已核实 |
| 子槽落在父件同行右邻格 | **59 / 61**（其余 2 例右邻格被父件自己的安装座占着，属结构限制） | 已核实 |
| 两槽同格 / 同格重复 | **0 / 0** | 已核实 |
| 触发独立槽位右移 | **12 例** | 已核实 |
| 移除配件后完全恢复（逐格比对） | **61 / 61** | 已核实 |
| 重复计算不漂移（连算 3 次 + 同 L 重复套用校准） | **61 / 61** | 已核实 |
| `info.fallback` 污染 | **0**（人工校准统计保持干净，`test_calib_user_adjustments_kept` 仍 397/0） | 已核实 |
| 合成用例（无空间/继续右搜/锚点跳过/兄弟不认/已在上方/空格回位） | **7 / 7** | 已核实 |
| 校准文件字节未变 | **是** | 已核实 |

典型真实结果（与任务书描述逐字对应）：

```
FN SCAR-H  父 r6c1 装[Kiba Arms 25毫米环形基座]
  子槽 mod_flashlight @ r6c2      （占父件同行右邻格）
  mod_tactical_001  r6c2 -> r6c3  （战术槽 2 临时右移）
GL-40      父 r6c1 → 子槽 r6c2，mod_tactical_002 r6c2 -> r6c3
SCAR-L     父 r6c1 → 子槽 r6c2，mod_tactical_000 r6c2 -> r6c4（r6c3 被镜座占用 → 继续向右）
```

---

## 5. 任务 C：修正 R+E/3（不取绝对值）

### 5.1 后坐力字段的真实符号语义（任务书 6.2 强制核实，已核实）

对 `data/items.json` 全量统计（`node -e` 逐条遍历，非抽样）：

| 项 | 数值 |
|---|---|
| 含 `mod.r` 字段的条目 | **1021** |
| `r < 0` | **945 条 —— 全部是「降低后坐力」的枪械配件**（如 SKS ATI Monte Carlo 枪托 `r=-0.35`） |
| `r > 0` | **76 条 —— 全部是弹种（`pt = "Ammo"`），且都没有 `mod.e`** |
| `r == 0` | **0 条** |

⇒ 数据约定：**减少后坐记负数、增加后坐记正数**。因此「正面增益 R = −r×100」，符号只需反转一次。
（76 条正值的弹种因缺 `mod.e`，`gunRE3` 返回 `null`，不参与计算；这也说明「缺失」与「真实 0」是分开处理的。）

### 5.2 修改

```js
// 改前（错的：既对负数取绝对值，又把「加后坐」当正向收益）
return Math.abs(r) * 100 + e / 3;
// 改后
return (-r) * 100 + e / 3;      // R = 正面增益（减少为正、增加为负），符号只反转一次
```

「后坐力」列仍显示**原始字段**（负数为减后坐），不重复反转符号；`R+E/3` 列的 `title` 同步改成 `−r×100 + 人机 / 3 = 结果（R 取正面增益：减少为正、增加为负）`。

### 5.3 输入 / 预期 / 实际（任务书四个示例，逐个断言）

| # | 输入（后坐力 / 人机） | 预期 | 实际 | 结果 |
|---|---|---|---|---|
| A1 | 减 3%（`r=-0.03`）/ 10 | `3 + 10/3 = 6.333` | 6.333 | ✅ |
| A2 | 加 3%（`r=+0.03`）/ 10 | `-3 + 10/3 = 0.333` | 0.333 | ✅ |
| A3 | 加 3%（`r=+0.03`）/ 6 | `-3 + 2 = -1.000` | -1.000 | ✅ |
| A4 | 减 6%（`r=-0.06`）/ -6 | `6 - 2 = 4.000` | 4.000 | ✅ |

另覆盖边界：A5 人机为 0（9.000）、A6 后坐力为 0（2.000）、A7 缺人机 → `null`、A8 缺后坐 → `null`、A9 无 `mod` → `null`、A10 符号只反一次（反向构造验证不会二次取反）、F7 显示与计算一致（用 `gunRE3` 实时值渲染断言 `-1.000`）。
**单测合计 44/44 通过**（`node tools/r19_28_unit.js`），`tests/test_r19_28_round.py` 2/2 通过。

---

## 6. 任务 D：静态审计产物与旧测试一致性

| 核查项 | 结论 | 口径 |
|---|---|---|
| `ak-dovetail-sight-layout.json` 里 AKM 后照门 | 上一轮为 `col=8`（过期，实际已 r2c6）→ **已用现有生成流程重生成**为 `col=6` | 已核实 |
| 生成器是否还会误报 | `tools/r1923_audit.js` 原要求「第二照门严格 r2c7」，把 R19.21 起就存在的 AKMP 子槽「父件正上方 r1c6」判成违规（8 条误报）→ 加 `akmpAbove` 判定后 `violations: []` | 已核实 |
| 旧测试读静态还是实时 | `test_r19_15_3_round.py` **读静态 JSON**；`test_r19_13_round.py::test_handguard_extras_json_row6` 也读静态，但**完整套件里另有工具会就地重生成**，因此静态产物必须与实时引擎一致，否则全套跑完就地变红（本轮实测踩到） | 已核实 |
| 冲突断言处理 | 只改 `test_04` 一项：由「全部 col==8」改为「AK 照门系 col==6、非 AK col==8」，并保留「非 AK 样本 ≥3」的原保护目的；未删除、未跳过任何用例 | 已核实 |
| 本轮重生成 | `docs/r19.13-layout-audit/*`（4 个）用现有 `tools/r1913_audit.js` 重生成；`handguard-extras.json` 恢复 `spills: []`、`inRow6: 127/130` | 已核实 |
| 3 个未重生成的旧产物 | `ak-dovetail-final.json` / `ak-dovetail-optic-chain.json` / `layout-conflicts.json` 保留原样，**记录为已知不一致** | 已核实（见 §10） |

---

## 7. 测试结果

### 7.1 分阶段

| 阶段 | 命令 | 结果 |
|---|---|---|
| 语法 | `node --check app.js`（每步改动后） | 全部通过 |
| 任务 A | `node tools/r19_29_taska.js` | `CHECK_TASKA: PASS`（205 配对，未豁免硬违规 0，结构 3 类） |
| 任务 B | `node tools/r19_29_taskb.js` | `CHECK_TASKB: PASS`（61 真实 + 7 合成） |
| 任务 C | `node tools/r19_28_unit.js` | 44/44 通过 |
| 任务 D | `node tools/r1923_audit.js` + `pytest tests/test_r19_15_3_round.py` | violations 0，用例全绿 |
| 相关旧测试（7 个文件） | `pytest test_r19_15_1/15_2/15_3/19/20/21/28_round.py` | **75 passed** |
| R19.29 专项 | `pytest tests/test_r19_29_round.py` | **8 passed** |
| 完整套件 | `pytest tests -q` | **1337 passed / 5 failed / 1 skipped**（87s） |

### 7.2 修改前后对照

| 时点 | 完整套件 |
|---|---|
| 本轮改动前（R19.28 交付态，工作区已有大量未提交改动） | 未采集到干净基线（工程本身已是脏工作区）；改用「将本轮 4 处改动逐一回退的副本」做归因基线：副本上同样这 5 项失败（另外多出的失败全部是副本缺 `assets/` 造成的 `FileNotFound`） |
| 本轮改动后 | 1337 passed / 5 failed / 1 skipped，失败集合与基线**完全一致** |

### 7.3 5 项失败的原因（均为 **R19.28 遗留**，本轮未引入、也未改写这些用例）

| # | 用例 | 根因 |
|---|---|---|
| 1 | `test_r19_11_round.py::test_hide_incompat_filters_without_touching_data` | 断言 `refreshGunTable()` 源码含 `setColumns` / `gunColumns()`；R19.28 需求四重写了属性表（动态列 `gunColumns(rows)` + `buildGunTable()`），`refreshGunTable` 只剩 `setRows` |
| 2 | `test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree` | 断言引擎含字面 `var rsCol = hasDovetail ? 6 : 8;`；R19.28 需求一改为按 AK 照门 id 白名单锚定 r2c6 |
| 3 | `test_r19_1_round.py::test_candidate_columns_match_reference_order` | 与 1 同源：找不到旧的 `gunColumns()` 文本契约 |
| 4 | `test_r19_5_round.py::test_zoning_is_generic_semantic_rules` | 断言引擎块内不得出现枪械/物品 id 与 `AK-74` 字面；R19.28 需求一的 `GW_AK_REAR_SIGHT_IDS` 白名单含 `"AK-74 照门"` |
| 5 | `test_r6_gun_workbench.py::test_gun_workbench_business_logic` | 测试抽块执行时报 `gunModVal is not defined`：R19.28 把 `gunModVal` 定义在抽块范围之外 |

> 归因方法（已核实）：建工程副本 → 把本轮 4 处改动（9.5 IIFE、`gwReflowTacticalKids` + 调用、`gunRE3`、版本号）逐一回退 → 在同一副本上跑全套。上述 5 项在原样复现，证明与 R19.29 无关。**按约束③，本轮不改写这 5 个用例来「变绿」**，如实记录。
>
> 顺带修复（不属上述 5 项）：`tools/serve.py` 的 `"rev"` 一直停留在 `R19.27-`，导致 `test_r19_7` / `test_r19_26` / `test_r19_27` / `test_ui_system_round::test_F`（4 项）长期红。本轮版本升级时一并同步为 `R19.29-`，这 4 项已转绿（属于「构建标记跟随 AM_BUILD」的原保护目的，不是弱化断言）。

---

## 8. 真实浏览器验收（**已实际完成**）

```bash
python tools/serve.py --port 8799          # 后台
python tools/r1933_accept.py --base http://127.0.0.1:8799 --port 9701
```

真实 Chrome（`--headless=new` + CDP，`--no-proxy-server`）跑 `http://127.0.0.1:8799/index.html`，**12/12 全通过**，产物 `docs/r19.29/browser-accept.json` + `docs/r19.29/shots/*.png`：

| 检查 | 结果 | 实测证据 |
|---|---|---|
| `build = R19.29` | ✅ | `GWCalib.version()` 返回 `R19.29` |
| A1 AKM 后照门 r2c6 | ✅ | DOM：`mod_sight_rear` = `row 2, col 6`，装 `AKM 照门` |
| A2 光学子槽在父件上方同列 | ✅ | G36 / MCX SPEAR 各 1 组 scope→scope 配对，均 `col` 相同且 `row` 更小 |
| B 定位 r6c1 战术槽 | ✅ | `mod_reciever/mod_mount_001/mod_tactical_000` @ r6c1 |
| B1 子槽占 r6c2 | ✅ | 装 Kiba 基座后 `.../mod_tactical_000/mod_flashlight` @ **r6c2** |
| B2 原 r6c2 槽位右移 | ✅ | `mod_tactical_001` 由 **r6c2 → r6c3**，两槽不同格 |
| B3 移除后恢复 | ✅ | 卸掉基座后 `mod_tactical_001` 回到 **r6c2**，子槽消失，全卡坐标与初始一致 |
| C1 候选表含 R+E/3 列 | ✅ | 表头 `配件 / 子槽 / 后坐力 / 人机 / R+E/3 / 尺寸 / 重量 / FLEA价 / 状态` |
| C2 R+E/3 计算/显示/符号一致 | ✅ | 逐行用「后坐力×(−1) + 人机/3」复算 10 行，列值与标题公式全部吻合（例：`-1.5% / 5.0` → `2 + 5.0 / 3 = 3.167`） |
| C3 存在「减少后坐→增益为正」的行 | ✅ | 10/10 行均为减后坐（增益为正） |
| D1 控制台无 JS 异常 | ✅ | 0 条 `error/exception/assert/log` |
| D2 无外部网络请求 | ✅ | 463 次请求，主机只有 `127.0.0.1` |

> 诚实说明（**已核实**）：浏览器验收中**没有出现「增加后坐」的配件行**——因为 `items.json` 里 76 条正后坐条目全部是弹种且无 `mod.e`（见 §5.1），配件永远不会是正后坐。因此「增益为负」的显示只在**单元测试构造值**上验证（A2/A3/A10/F7），浏览器端只验证了「减少为正」这一侧。这一点不夸大。

---

## 9. 与任务书十条约束的逐条对照

| 约束 | 执行情况 |
|---|---|
| ① 先查真实代码/分支/工作区/测试 | 先读 `app.js` 布局引擎、校准叠加、属性表与既有 6 个测试文件，全量扫描枪械后才动手（本轮据此推翻了自己上一轮「109 处违规」的误判） |
| ② 不 reset / clean / 强制检出 / 批量覆盖 | 未执行 |
| ③ 不删/不跳过/不弱化旧测试 | 未删未跳过；唯一改动是上一轮任务 D 的 `test_04`（仅改冲突项、保留保护目的）；5 项 R19.28 遗留失败**如实记录而非改写** |
| ④ 不重写 `app.js`、不做无关重构 | 只加 2 处（9.5 IIFE、`gwReflowTacticalKids`）+ 1 处调用 + 2 处任务 C 改动 |
| ⑤ 保留 R19.28 有效功能 | AK 系照门 r2c6 仍成立（浏览器 A1 实测）；属性表动态列仍在（浏览器 C1/C2 实测） |
| ⑥ 不动地图/路线/任务/配装/弹药库 | 未改这些模块 |
| ⑦ 不改人工校准数据、不把临时修正写进校准文件 | `data/gun-layout-calibration.json` 397 条未变（sha256 已记录）；任务 B 每次运行都复核文件字节未变 |
| ⑧ 不提交、不推送、不覆盖发布版本 | 未执行任何 git 写操作，未动 `release/` `dist/` `build/` |
| ⑨ 不凭单测/旧截图冒充浏览器验收 | §8 全部来自真实 Chrome DOM 实测，并保留截图与 `browser-accept.json` |
| ⑩ 区分已核实/估算/未知 | 全文逐条标注；浏览器只验到「减少为正」一侧也已写明 |

---

## 10. 未解决问题与风险

1. **Saiga-12K（自动霰弹枪）的瞄具子槽仍是「同行右邻」，不是上方同列。**
   冲突根因：R19.13 锁定「护木附件整体留在第 6 行、`spills` 必须为空」。上提会让整卡片顶下一行并记成 spill（实测过：`topPad` 0→1，Saiga 全卡 25 格坐标变动）。两条不变量冲突时保留 R19.13。**需要产品决策**：若允许护木链瞄具上提，须同时改 R19.13 的 spill 口径。

2. **HK G28（2 对）、Milkor（1 对）为「上方但异列」。**
   G28 的第 2/3 个瞄具子槽走顶部锚点 r2c6/r2c7（R19.15.3 已锁定的锚点列）；Milkor 的瞄具父槽被人工校准放在底行 r6c2，子槽按 R19.15.1「子槽向上」落在 r1c7。强行同列会改写已锁定的锚点分配或覆盖人工校准，故未动。

3. **AS「巨浪」MOD.4 在 `filled` 场景仍有 3 对硬违规**，该枪有 10 条人工校准（含 `mod_handguard/mod_mount_002/mod_scope` 系），父件位置由用户决定，按约束⑦不覆盖。

4. **任务 B 对「右邻格被父件自己的安装座占用」的情况不动作**（SCAR-L 2 例，父件在 r6c2、右邻 r6c3 是它的上级镜座）。此时子槽落到 r6c4 或 r5c1，属结构限制；已记为「祖先链路阻挡」，不算冲突也不算缺陷，但视觉上确实不是紧邻。

5. **5 项 R19.28 遗留测试仍红**（§7.3）。它们抵制的正是 R19.28 已交付的实现方式（AK id 白名单 / 属性表重写 / `gunModVal` 抽块边界）。要转绿必须二选一：改旧测试（约束③不允许本轮擅自做）或改 R19.28 实现（超出本轮范围）。建议单开一轮处理。

6. **3 个旧审计 JSON 未重生成**（`ak-dovetail-final.json` / `ak-dovetail-optic-chain.json` / `layout-conflicts.json`），与当前引擎存在漂移（`dovetailGuns 28→30` 等）。已记录，未伪造、未删除。

7. **校准器交互语义变化（需知悉）**：任务 B 是显示级避让。如果用户把某个「独立战术槽」校准到会被子槽征用的格子，校准器预览会看到它被推开一行的位置——记录里仍保存用户填的格子（`info.claimed` 不改）。这是「避让只影响当次计算」的直接后果，不是 bug，但可能让人疑惑，建议后续在校准器上给个提示。

8. **任务 A 的真实收益面很窄**（`default` 场景 0 改动、`filled` 场景 1 格）。这说明布局引擎本身对光学子槽的处理已基本正确，本轮的价值在于「用可复现的审计证明它正确」，而不是大改。

9. **未验证项**：`FAR_UP` 的 4 例（Saiga 等）与 `DIFF_COL` 的 112 例只做了结构归类，未逐例人工核对视觉合理性（**未知**）；浏览器验收只覆盖 5 把枪（AKM / G36 / MCX SPEAR / SCAR-H / 另一把 AKM 表场景），其余 160+ 把枪仅有 node 级布局验证。

---

## 11. 交付物清单

```
app.js                                    任务 A/B/C 实现 + AM_BUILD=R19.29
index.html                                15 处 ?v=r19.29
tools/serve.py                            rev R19.29-
tools/r19_29_taska.js                     任务 A 审计（新增）
tools/r19_29_taskb.js                     任务 B 审计（新增）
tools/r1933_accept.py                     R19.29 浏览器验收（新增）
tests/test_r19_29_round.py                R19.29 专项 8 项（新增）
docs/r19.29/task-a.json                   任务 A 逐对结果 + 白名单
docs/r19.29/task-b.json                   61 场景 + 7 合成用例明细
docs/r19.29/browser-accept.json           12 项浏览器实测结果
docs/r19.29/shots/*.png                   6 张实测截图
docs/r19.13-layout-audit/*.json           用现有流程重生成（spills 恢复为空）
docs/r19.15.3-layout-audit/ak-dovetail-sight-layout.json   上一轮已重生成
```

**本轮到此停止：未提交 Git、未推送远程、未开始 R19.30。**
