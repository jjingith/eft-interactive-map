# R19.14.2 Nightforce 直接槽位修正 + 瞄具/底座专项审计

日期：2026-10-26
实际版本：`R19.14.2-77dbccba`（`/api/build` 实测）
本轮只修已确认的错误，其余瞄具/底座一律标记「待核实」，不套用 Nightforce 规则。

---

## 一、证据分级（先看这张表）

| 级别 | 内容 |
|---|---|
| **A. 已由真实游戏实测确认** | Nightforce MagMount Multimount 34mm **直接槽位 = 2**（34mm 光学瞄准镜 / 单倍瞄具·单倍瞄具底座）——用户 2026-10-26 游戏内确认 |
| **B. 已由可靠数据核实** | ① 上游快照（`build-cache/r19-upstream/items.json`）对该物品声明 **4 个同名 MOD_SCOPE**，其中 `_002`/`_003` 的 allow 完全重复；② 本地 `data/items.json` 与上游同源（修复前也是 4 个）；③ 163 把枪默认装配共 1867 格，**0 重复路径**（修复后实测） |
| **C. 仅由代码推断（不当作事实）** | 无。未对任何其他瞄具/底座判定「应该有几个槽」 |
| **D. 仍待核实** | 728 个瞄具/底座/转接件的槽位数量与用途；161 个存在「重复 allow 签名」的配件（多为护木多条同规格导轨，是否合理需游戏内确认）；9 个被 `gwSlotVisible` 隐藏同基名空副本的配件 |

> 未把任何未经实测的其他瞄具规则写成「已完成」。

---

## 二、Nightforce 为什么多出 2 个槽位（根因）

```
上游数据（tarkov.dev 快照）
  props.slots = [
    MOD_SCOPE (5aa66c90…c96)  allow = 4 件 34mm 光学瞄具      ← 真实：34mm 槽
    MOD_SCOPE (5aa66c9c…125)  allow = PK-06 + RAPTAR + 5 底座  ← 真实：单倍瞄具/底座槽
    MOD_SCOPE (5aa66cab…d82)  allow = 7 件底座（⊂ 上一条）      ← 游戏中不存在
    MOD_SCOPE (5aa66cb7…e99)  allow = 同上 7 件（互相重复）      ← 游戏中不存在
  ]
```

- 项目此前**没有槽位修正层**，`_item_slots()` 把上游 4 条原样写入 `data/items.json`；
- `gun_builder.buildTree()` 按 `rec.slots` 逐条建节点 → 树上 4 个直接子槽；
- `gwBuildLayout()` 再按树摆放 → 画布 4 个格子。

**不是布局代码重复渲染，而是数据层就多 2 个节点。** 因此修复必须落在数据/建库链，而不是隐藏格子。

### 修复内容

1. **建库链**（`tools/fetch_data.py`）：新增 `OPTIC_SLOT_CORRECTIONS` 显式修正表 + `_apply_slot_correction()`，
   `_item_slots(props, zh, item_id)` 在生成时按表裁剪/重命名；`data/items.json` 与 `data/gunslots.json` 建库时自动生效。
2. **运行期数据**（`data/items.json`）：同步改为 2 槽（保留 `_000`/`_001`，删除 `_002`/`_003`），
   并给两槽打 `fix: "in-game-confirmed"`；`_001` 标签改为「单倍瞄具 / 单倍瞄具底座」。
3. **保留上游 ID**：两槽沿用原 `id`/`sid`，预设与安装路径不需要迁移（实测预设未引用 `_002/_003`）。

---

## 三、方向规则（仅对 Nightforce 生效）

| 规则 | 实现 | 实测 |
|---|---|---|
| 34mm 光学槽沿主光学链向上 | 主链固定 `c5`，逐层 `row-1` | ATACR `r2c5`（底座在 `r3c5`） |
| 单倍槽在 34mm 槽右侧 | 侧分支从 `c6` 起、先铺满 r1 再下一行 | 单倍槽 `r2c6` > `r2c5` |
| 单倍槽内底座的子瞄具槽在底座正上方 | 新增 `placeDescendantsUpward()`：子槽 `parentRow-1` 同列递归 | 底座 `r2c6` → 子槽 `r1c6` |
| 空间不足走顶部扩展，不横移 | `GW_TOP_MAX=4` + `topPad` 整体下移 | 三层时 `rows=7, topPad=1`；移除后回 `6/0` |

> 其他瞄具/底座**不套用**上述结构，仍按各自真实父子关系走通用规则（父件锚定 + 顶部扩展）。

---

## 四、浏览器实测（`browser-check.json`，1920×919，禁缓存）

| 验收点 | 结果 |
|---|---|
| ① 直接槽位严格 2 个 | **通过** — `directSlotCount: 2`，sid = `mod_scope_000` / `mod_scope_001`，无 `_002/_003` |
| ② 两槽用途与兼容正确 | **通过** — 34mm 槽选中 ATACR；单倍槽选中 Aimpoint Micro 底座；候选列表分别出 4 / 8 件 |
| ③ 底座子瞄具槽在正上方 | **通过** — `childAboveBase: true`（底座 r2c6 → 子槽 r1c6） |
| ④ 多层顶部扩展 | **通过** — 三层 `rows 7 / topPad 1`；移除后 `6 / 0` |
| ⑤ 已核实物品槽位数与数据一致 | **通过** — G36 瞄具基座直接格 4 = 声明 4（修复前 6，重复格已去重） |
| ⑥ 空坐标隐藏仍正常 | **通过** — `phantomCount: 0`，真实空槽 4 个且可点 |
| ⑦ 安装/卸载/预设/枪匠大师同树 | **通过** — 预设后 `slotCount 7 = treeSlots 7`；枪匠大师生成后 `9 = 9`，挂载点仍恰好 2 个子槽；全程无 `_002/_003` |
| ⑧ B.A.D / MPR45 / 六行 / 扩展 | **通过** — B.A.D `r4c6`；MPR45 链 `r3c4→r2c4→r1c4` 同列；基准 6 行，扩展正常 |

截图：`screenshots/N1`（仅 2 个空槽）、`N2`（ATACR + 右侧底座 + 底座上方空槽）、`N3`（三层顶部扩展）、`N4`（移除后回 6 行）、`N5`（MPR45 链）、`N6`（枪匠大师生成后）。

---

## 五、审计产物

| 文件 | 内容 |
|---|---|
| `nightforce-direct-slots.json` | 物品 ID、2 个直接槽位（ID/sid/用途/allow 全量）、2 个被移除节点及原因 |
| `nightforce-tree-before-after.json` | 修复前上游 4 槽证据、修复后声明/树/布局三处均为 2；装件后的树与坐标 |
| `optic-slot-audit.json` | 729 个瞄具/底座/转接件：声明槽数、上游槽数、树子节点数、画布格数、重复 allow 组、证据与核实状态 |
| `optic-slot-issues.json` | `fixed`（Nightforce 4→2、G36 重复格 6→4）+ `duplicates`（161 项待核实）+ `mismatchDeclaredVsTree`（9 项，均标注为既有可见性规则）+ `notes` |
| `browser-check.json` | 上述 8 项浏览器实测原始数据 |

### 审计发现的其他问题（未擅自修改）

1. **161 个配件存在「重复 allow 签名」**：多为护木上的多条同规格导轨（如 QBZ-191 护木 2 条 `mod_mount_000`）。
   `pb` 是否为真实多槽位，需游戏内确认；**未改动**，标记 `pending-verification`。
2. **9 个配件的画布直接格数比声明少 1**：原因是既有 `gwSlotVisible()` 在「同基名兄弟槽已装一件时隐藏其余空副本」。
   属既有设计，非本轮数据错误，已在 JSON 中标注 `hiddenByVisibilityRule`。
3. **G36 瞄具基座重复格（已修）**：同一槽位路径被顶部锚点阶段与子槽阶段各推一条记录，画布出现 6 格而数据只有 4 槽。
   修复方式：`gwBuildLayout()` 的 `cell()` 增加同路径去重（保留首次落位），全 163 枪复测 0 重复。

---

## 六、测试

- 新增 `tests/test_r19_14_2_nightforce.py`（11 项）：两槽数据、用途/allow、建库修正表、去重与向上规则、四个审计 JSON、浏览器 8 项、全枪去重。
- 旧布局探针（`r1910_layout.js` / `r1912_layout.js` / `r1913_audit.js`）改为 **topPad 感知**：
  行上界 = `6 + topPad`，锚点行号 = 基准行 + `topPad`，基准行数仍锁 6（`grid.baseRows === 6`）。
  这不是放宽断言——同时新增「baseRows 必须为 6」的校验。
- 全量：**1030 passed / 1 skipped**。

---

## 七、仍然待你实测确认的清单

| 项 | 原因 |
|---|---|
| 其他 728 个瞄具/底座/转接件的直接槽位数与用途 | 只有上游单一来源，无游戏内实证 |
| 161 个「重复 allow 签名」配件 | 可能是真实多槽位（护木导轨），也可能是上游冗余 |
| Nightforce 单倍槽 allow 中的 `Wilcox RAPTAR ES 战术测距仪` | 该件是否真能装在此槽，未逐项实测；当前沿用上游 allow |

以上三项在 `optic-slot-audit.json` / `optic-slot-issues.json` 中均为 `pending`，未按 Nightforce 规则改动。
