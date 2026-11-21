# R19.19 交付报告｜AK 照门槽位修复 + 配件父子布局规则审计

构建标记：**`AM_BUILD = R19.19`**（index.html `?v=r19.19`，serve.py rev `R19.19-*`）
基线：R19.18。全量 pytest：**1160 passed / 1 skipped / 0 failed**。

---

# 第一部分：AK 照门修复（任务 A）

## 1. 修改文件列表

| 文件 | 修改内容 |
|---|---|
| `tools/slotfix.py` | 新增 `R1919_ITEM_SLOT_FIXES`（删除 AKM 照门的 AKMP-only 子槽）+ `R1919_GUN_SLOT_ALLOW_ADDS`（AKMP RS 并入五把 7.62x39 枪的唯一照门槽 allow）+ `apply_gun_slot_allow_adds()` |
| `data/items.json` | ① 删除「AKM 照门」`mod_sight_rear` 子槽（slot id `5a0eda49fcdbcb001912fa61`）；② 五把枪自身的 `mod_sight_rear` allow 并入 AKMP RS（buildTree 读 items.json） |
| `data/gunslots.json` | 五把枪的 `mod_sight_rear` allow 同步并入 AKMP RS（展示/审计数据源与 items.json 一致） |
| `data/gun-layout-calibration.json` | 仅照门相关：5 条照门记录 r1→r2（A1）；5 条 AKMP-only 子槽记录标注失效（A2）。397→397 条，0 删除 |
| `tools/fetch_data.py` | `_item_slots` / `_apply_slot_correction` / `build_gunslots` 挂接 R1919 两张表（下次刷新上游不回退） |
| `tools/r1926_calibmigrate.py` | `STALE_OWNERS` 补 AKM 照门条目（失效分类口径一致） |
| `tools/r1925_engine.js` | AK-74N 合成期望同步 r1→r2（照门记录下移后的正确坐标） |
| `tools/r1926_audit.js` | `akm_akmp_child_slot_kept` 升级为 `akm_akmp_child_slot_gone` + 每把 7.62 枪单槽/含 AKMP 断言 |
| `tools/r1927_datafix.py` / `r1927_calibmigrate.py` / `r1927_audit.js` / `r1927_accept.py` / `r1927_layout_audit.js` | R19.19 新增：数据套用 / 校准迁移 / 引擎审计 / 浏览器验收 / 任务 B 只读探针 |
| `tests/test_r19_19_round.py` | R19.19 专项测试 15 项（A1–A4 + 数据表 + VPO-209 报告锁 + 版本） |
| `tests/test_r19_14_2_nightforce.py`、`tests/test_r19_18_round.py`、`tests/test_r19_17_round.py`（经 r1925_engine） | 5 处旧断言按纪律**升级为更强断言**（详见 §7） |
| `app.js` / `calibrator.js` | **未修改布局逻辑**，仅 `AM_BUILD = R19.19` 版本标记 |

## 2. A1：五把 5.45x39 / 5.56x45 照门槽下移一格

**根因（先核实后修复）**：自动布局**本来就在 r2**（照门带 `rsCol = hasDovetail ? 6 : 8`，行 2）；
把照门钉在 r1 的是**人工校准记录** `mod_sight_rear|mod_sight_rear|`（`source:"manual"`，logicalRow=1），
经 `gwApplyCalibToLayout` 覆盖了自动结果。布局引擎没有「兄弟槽删除后错误上移」的计算——
无需、也没有在引擎里加逐枪硬编码（测试锁死：五把枪 ID 不得出现在 app.js）。

修复：按 A4 授权**只改 AK 照门相关校准记录**，5 条记录 logicalRow 1→2（列不变 c6），备注 `R19.19 A1`。

| 枪械 | 枪械 ID | 槽位 ID（照门槽） | 父级 | 修复前（最终） | 修复后（最终） | 自动布局 | 记录身份键 |
|---|---|---|---|---|---|---|---|
| AK-105 | `5ac66d9b5acfc4001633997a` | `mod_sight_rear` / `5ac66d9b5acfc40016339982` | 枪身根级（无父件） | r1c6 | **r2c6** | r2c6 | `mod_sight_rear\|mod_sight_rear\|` |
| AK-74 | `5bf3e03b0db834001d2c4a9c` | `mod_sight_rear` / `5bf3e03b0db834001d2c4aa4` | 枪身根级 | r1c6 | **r2c6** | r2c8（无燕尾槽） | 同上 |
| AK-74N | `5644bd2b4bdc2d3b4c8b4572` | `mod_sight_rear` / `5648be944bdc2d3b4c8b4579` | 枪身根级 | r1c6 | **r2c6** | r2c6 | 同上 |
| AKS-74 | `5bf3e0490db83400196199af` | `mod_sight_rear` / `5bf3e0490db83400196199b7` | 枪身根级 | r1c6 | **r2c6** | r2c8（无燕尾槽） | 同上 |
| AKS-74N | `5ab8e9fcd8ce870019439434` | `mod_sight_rear` / `5ab8e9fcd8ce87001943943c` | 枪身根级 | r1c6 | **r2c6** | r2c6 | 同上 |

- 逻辑行=显示行（topPad=0）；「下移一格」=行 +1、列不变。
- 错误的 AKMP 照门槽（R19.18 已删）**仍不存在**（验收逐枪确认单照门槽）。
- 合法候选完整保留（AK-105/AK-74/AK-74M 照门、TT01、RD Enhanced V2、AK-12、RPK-16 照门）。
- 无重复照门槽；校准器预览与主画布一致（均 r2c6）；刷新后保持。
- **单说差异**：AK-74 / AKS-74 无燕尾槽，其自动布局列是 c8 而非 c6——你的记录原在 c6，本次按「下移一格、列不变」只改行；若想让这两把随自动布局落到 r2c8，删掉这两条记录即可（自动布局立即接管）。
- **其他 AK 未受影响**（验收要求）：AK-103 / AK-104 / AKM / AKMS / AKMN / AKMSN / VPO-136 / VPO-209 的照门记录仍在 r1c6，本次**未动**（它们不在 A1 清单内）。它们与五把枪不一致的位置如需统一，请另行指示。

## 3. A2：7.62x39 多余 AKMP-only 照门槽的删除

**来源追踪**（先定源再修）：这个槽**不是**枪身槽，也不是生成层伪造——它是真实数据里
「AKM 照门」（`59d650cf86f7741b846413a4`，AKM 侧轨基座）自带的**子槽**（slot id `5a0eda49fcdbcb001912fa61`，
sid `mod_sight_rear`，allow 只有 `AKMP系统照门装置` `5a0ed824fcdbcb0176308b0d`）。
默认预装 AKM 照门 → 树里同时出现枪身照门槽 + 这个 AKMP-only 子槽 = 两个照门槽。

**修法（数据层等价迁移，非视觉隐藏）**：
1. 从「AKM 照门」物品上**删除**该 AKMP-only 子槽（`tools/slotfix.py` R19.19 表，已接入 fetch_data 防回退）；
2. 把 `AKMP系统照门装置` **并入枪身唯一照门槽 `mod_sight_rear` 的 allow**（items.json + gunslots.json 两处一致）——
   保住 A3 明确的「AKM 系合法使用 AKMP RS」兼容能力（R19.18 问题 7 口径不变），同时只留一个照门安装槽。

| 枪械 | 枪械 ID | 删除的 AKMP-only 槽位 ID | 删除原因 | 保留的唯一照门槽 ID | 并入的候选 |
|---|---|---|---|---|---|
| AKM | `59d6088586f774275f37482f` | `mod_sight_rear/mod_sight_rear`（`5a0eda49fcdbcb001912fa61`） | 游戏内只有一个照门安装槽 | `59d6088586f774275f374836`（mod_sight_rear） | AKMP系统照门装置 |
| AKMS | `59ff346386f77477562ff5e2` | 同上（随 AKM 照门物品） | 同上 | `59ff346386f77477562ff5e9` | 同上 |
| AKMN | `5a0ec13bfcdbcb00165aa685` | 同上 | 同上 | `5a0ec13bfcdbcb00165aa68c` | 同上 |
| AKMSN | `5abcbc27d8ce8700182eceeb` | 同上 | 同上 | `5abcbc27d8ce8700182ecef3` | 同上 |
| VPO-136 | `59e6152586f77473dc057aa1` | 同上 | 同上 | `59e6152586f77473dc057aa8` | 同上 |

保留的合法候选（不变）：AKM 照门、AKMB系统照门、TT01 照门导轨、RD Enhanced V2 AK 照门（VPO-136 为前三者）。

**逐项状态**（验收标准核对，浏览器实测）：

- AK-103 / AK-104：✅ 无 AKMP-only 多余槽（其叶式照门的 AKMP 子槽 R19.18 已删），照门槽恰好 1 个；其 AKMP 能力在 R19.18 已按叶式照门口径移除（AK-103/104 用 AK-74 系叶式照门，游戏内无 AKMP 接口）。
- AKM / AKMS / AKMN / AKMSN / VPO-136：✅ 各恰好 1 个照门槽；AKMP-only 槽从真实树消失（不是画面上藏起来）；AKMP RS 装入唯一照门槽成功、卸下后无残留；装上 AKM 照门后不再生出第二个照门槽。
- 校准器与主程序槽位树一致；刷新/切换枪械不回退。
- **VPO-209（.366TKM）同构问题单列待裁决**：「VPO-209 照门」（`59e8977386f77415a553c453`）也带一个 AKMP-only 子槽（slot id `5a0eeb41fcdbcb098008726f`），当前**保留未动**（A2 声明范围是 7.62x39，且要求不自行推断/批量删除）。若要按同一原则修复（删子槽 + AKMP 并入 `mod_sight_rear` allow of `59e6687d86f77411d949b251`），一行修正表即可，等你指示。

## 4. 校准记录变更（A4）

- 修改前：152 把枪 / **397** 条；修改后：152 把枪 / **397** 条（0 删除、0 重建、0 清空）。
- **变更 10 条**（`docs/r19.19-ak-rear-sight/calibration-migration.json` 逐条留痕）：
  - 5 条 `moved-down-one`：五把枪 `mod_sight_rear|mod_sight_rear|`，r1c6 → r2c6（列不变），备注 R19.19 A1；
  - 5 条 `marked-stale`：AKM 照门子槽记录（owner `59d650cf…`，身份键 `mod_sight_rear/mod_sight_rear|mod_sight_rear|59d650cf…`）标注失效原因，**原坐标保留、不迁移到其他槽位**。
- 其余 387 条记录坐标逐条未动（r1925 全量语料：378 applied + 18 stale + 1 suppressed = 397，exactCoords 378，fallback 0）。
- 备份：`docs/r19.19-ak-rear-sight/backup/`（items / gunslots / calibration / app.js / slotfix + 各文件 SHA-256）；校准 SHA `d969a2c4…6e44` → 新值见 `backup/*.sha256` 与迁移报告。

## 5. 测试与浏览器验收

- **专项**：`tests/test_r19_19_round.py` 15 项全过（A1 坐标/单槽/候选、A2 数据层删除/两处 allow 一致/装 AKM 照门无重复、A3 45·56 无 AKMP / AKM 系保 AKMP / 无 AK-74 照门 / GP-25·SVDS·SKS 不回归、A4 397 条不减/失效不迁移/备份齐、数据表挂接、VPO-209 报告锁、版本）。
- **全量**：**1160 passed / 1 skipped / 0 failed**。
- **引擎审计**（`tools/r1927_audit.js` 56 项 0 失败）+ R19.18 回归审计（`r1926_audit.js` 45+ 项 0 失败）+ R19.17 语料审计（0 失败）。
- **浏览器验收**（`tools/r1927_accept.py`，真实 DOM）：
  - A1 五把枪主画布照门卡均在 r2c6、仅 1 张照门卡 ✅ 截图 `A1-*.png`
  - A2 五把枪：默认 1 槽 → 候选列表含「AKMP系统照门装置」→ 装上（1 槽已装）→ 卸下（1 槽清空），全程无重复 ✅ 截图 `A2-*.png`
  - 刷新后 AK-74N 仍在 r2c6 ✅；校准器（AK-74N）照门卡同为 r2c6，预览与主画布一致 ✅

## 6. 仍需你在游戏内验证的项目

1. **AKMP RS 并入唯一照门槽**是按「一个照门安装槽 + AKMP 兼容能力保留」做的语义等价迁移（上游数据把 AKMP 建模为 AKM 照门的子槽件）。若游戏里 AKMP 后照门必须先装 AKM 照门才能挂（即子槽语义属实），请告知——我会改回「保留子槽」或改成「装 AKM 照门前 AKMP 置灰」。
2. AK-103 / AK-104 的 AKMP 能力维持 R19.18 口径（叶式照门无 AKMP 接口）；若你实测可装，改 `tools/slotfix.py` 一处。
3. VPO-209 的同构 AKMP-only 子槽（§3 单列）修/不修。
4. AK-74 / AKS-74 照门列 c6 vs 自动 c8（§2 单说差异）。

## 7. 旧断言升级清单（未删除、未弱化）

| 测试 | 旧断言 | 升级后 |
|---|---|---|
| `test_r19_18::test_B_akm_family_uses_akmp_rs` | `akm_akmp_child_slot_kept`（保留 AKMP 子槽） | `akm_akmp_child_slot_gone` + 每把单槽 + AKMP 在唯一槽 allow（R19.19 A2 作废旧口径） |
| `test_r19_18::test_B_new_ak_variant_will_not_regress` | AKM 照门必须保留 AKMP 子槽 | 任何照门件不得带 AKMP-only 子槽；AKMP 一律在枪身照门槽 allow |
| `test_r19_18::test_J_version_sync` | `== "R19.18"` | 跟随 AM_BUILD 动态同步 |
| `test_r19_14_2_nightforce::test_build_pipeline_has_correction_table` | `'return _apply_slot_correction(...)'` 源码标记 | 调用点 + R1918/R1919 两张表均挂接 |
| `tools/r1925_engine.js` akApplied 合成期望 | 照门 r1c6 | r2c6（A1 记录下移后的真实坐标） |

## 8. 任务 A 是否误伤其他布局

已核对（步骤 8）：R19.18 回归审计 45+ 项（SVDS r2c7 / SKS SOCOM r4c3 / GP-25 r4c3 / T-5000 / TKPD / VSK-94 / AS VAL / G28·S12K 行数）全过；
r19.15.x 燕尾槽审计（r2c8 主锚 + SVDS 例外）全过；校准语料 387 条未动记录落点逐条一致。
预期外改动 = 0；所有布局变化均在任务书授权范围内（五把枪照门行 + 7.62 五把枪照门树）。

---

# 第二部分：配件父子布局规则审计（任务 B，只读，未改任何代码/数据）

审计对象：`gwBuildLayout` 全阶段（app.js）、`gwApplyCalibToLayout`、`calibrator.js` 坐标换算、`GW_FIXED_SLOT`/`GW_ANCHOR`。
证据：`tools/r1927_layout_audit.js` 实跑产物 `docs/r19.19-ak-rear-sight/layout-rules-audit.json`（六案例真实坐标 + 全项目 911 个父子格方向分布：上方 113 / 正下方 232 / 同行 225 / 其他 341）。

## 1. 差异对照表

| 编号 | 场景/配件类型 | 我的预期规则 | 当前实际实现 | 差异 | 涉及函数或文件 | 实际案例 | 是否影响布局结果 |
|---|---|---|---|---|---|---|---|
| 1 | 枪械上半部分配件的子槽 | 正上方一格 | **分链处理**：上置链（瞄具/照门带/MPR45/燕尾槽）子槽确实逐层同列向上（`placeDescendantsUpward`、`placeChainUpward`、父件 row≤2 时 `nearestInRow(row-1)`）；但**照门带是例外**——照门的子槽被塞进 r2c7（同行右侧）而不是正上方；且父件在 r3（如机匣）时子槽向下 | **部分一致** | `gwBuildLayout` 阶段 4.1 照门带 / 4.5 上置链 / 阶段 8（app.js ~L10960 / L11032 / L11480） | 案例 1：TT01 瞄具子槽 r2c7 vs 预期 r1c6 | 是（照门带子槽） |
| 2 | 枪械下半部分配件的子槽 | 正下方一格 | 通用规则即「父件正下方同列」（`findFree(parentRow, parentCol, belowOnly=true)`），弹匣/握把/枪托链均向下 | **一致** | 阶段 8 `findFree(belowOnly)`；阶段 3 枪托链（app.js ~L11330 / L10860） | 案例 2：SCAR-L 伸缩枪托 r4c9（父 r3c9 正下方） | 是 |
| 3 | 枪口配件链 | 优先沿枪口方向（水平）延伸，空间不足再向下 | **只实现回退位**：枪口链同列逐行向下（`mRow+1+ki`），从不尝试水平延伸；对枪口在 c1 的枪（左缘）结果与回退位一致，但「优先沿枪口方向」的判断完全缺席；一体式枪 muzzle 在 c2 时，同行 c1 也不会被尝试 | **部分一致**（回退行为一致，优先级缺失） | 阶段 5 枪口纵向链（app.js ~L11363） | 案例 3：AK-74N 制退器→消音器 r3c2→r4c2（回退位） | 是（对 c1 枪无差异，对 c2 一体式枪有差异） |
| 4 | 枪托配件链 | 优先沿枪托方向（水平）延伸，受限时选合理后备位 | **只实现回退位**：枪托链同列向下 r4c9→r5c9→r6c9，「先判断枪托方向空间」未实现；枪托固定在 c9（右缘）时结果与回退位一致 | **部分一致**（回退行为一致，优先级缺失） | 阶段 3 枪托链（app.js ~L10860，`GW_ANCHOR.stock*`） | 案例 4：缓冲管→枪托→第二枪托槽 r3c9→r4c9→r5c9 | 是（当前无差异，通用化后有） |
| 5 | 托腮板等枪托上方配件 | 位于父配件正上方 | **不一致**：托腮板槽基名归一为 `stock`（`gwSidBase("mod_stock_002")="stock"`），被枪托链当作「下一层枪托」向**下**叠（r6c9）；目前靠人工校准记录钉回 r2c9 才符合你的设想 | **不一致**（自动布局），已被校准记录人工纠正 | 阶段 3 枪托链的沿链条件「子槽基名仍然是 stock」（app.js ~L10874） | 案例 5：SCAR-L 托腮板 auto **r6c9** vs 预期 r2c9（校准记录 r2c9） | 是 |
| 6 | 多个子配件及条件子槽 | 按各自真实类型与方向分别布局 | **分类型但不分方向**：瞄具子链向上、侧分支向右横排、护木附件进第六行、前握把链向下；但通用子槽（阶段 8）一律「父件正下方」，不识别安装方向；同名列可叠多层（枪托链/枪口链） | **部分一致** | 阶段 4.5（纯瞄具/侧分支分流）/ 阶段 6/7/8 | 案例 6：SOCOM 瞄具 r2c3（上）+ 战术 r5c3–c6（下）——但走 `GW_FIXED_SLOT` 硬锚点而非通用分类 | 是 |
| 7 | 空间不足与备用位置 | 先满足方向优先级，再用约定后备位 | 后备位逻辑完整（同列向下→相邻列→findFree 任意空格→exceptions 记录），但**前置的方向优先级**（枪口/枪托水平方向）不存在，直接进入后备位 | **部分一致** | `findFree` / `nearestInRow` / 各链的避让（app.js ~L11322） | 案例 3/4 即「直接走后备位」 | 是 |
| 8 | 人工校准覆盖自动布局 | 只覆盖显示坐标，不改真实父子关系 | **一致**：`gwApplyCalibToLayout` 只改 `L.cells` 的 row/col/role 与派生显示字段；装配、树、allow、兼容判断不经过校准层；身份 `slotPath\|slotId\|ownerItemId` 匹配，非法/冲突回退 | **一致** | `gwApplyCalibToLayout`（app.js，R19.17）；`calibrator.js` previewView 复用同一函数 | 五把 AK 照门记录 r1→r2 即纯显示覆盖 | 是（仅显示层） |

**追加行 9（发现的规则冲突，需你裁决）**：

| 9 | 照门带子槽 vs 规则 1 | 规则 1：子槽在父件正上方 | R19.15.3 任务书把「照门带」定为 r2c6/r2c7（第二个照门相关槽位严格 r2c7）——这是你此前的硬性验收坐标 | **两条规则互相冲突**（R19.15.3 照门带 vs R19.19 规则 1） | 阶段 4.1 照门带（`rsQueue` 逻辑，app.js ~L10990） | 案例 1 | 是 |

## 2. 六个具体实例（`layout-rules-audit.json` 实测，逻辑坐标）

**案例 1｜上半部子槽：AK-74N（`5644bd2b4bdc2d3b4c8b4572`）+ TT01 照门导轨**
- 父：`mod_sight_rear`（装 TT01 照门导轨 `5649d9a14bdc2d79388b4580`）@ **r2c6**
- 子：`mod_sight_rear/mod_scope`（TT01 的瞄具槽，37 候选）@ **r2c7**（role=rearSight2）
- 规则 1 预期：**r1c6**（正上方）；实际算法：照门带把「照门相关槽位」排 r2c7（R19.15.3 规则）
- 校准覆盖：无（照门记录 r2c6 与自动一致）
- 差异归因：阶段 4.1 `rsQueue`（照门子件并入照门带，同格右移而非上移）→ 见追加行 9 的规则冲突

**案例 2｜下半部子槽：SCAR-L（`6184055050224f204c1da540`）**
- 父：`mod_stock`（FN SCAR 折叠式聚合物枪托 `61816734d8e3106d9806c1f3`）@ **r3c9**
- 子：`mod_stock/mod_stock_001`（伸缩枪托槽）@ **r4c9**
- 规则 2 预期：正下方 r4c9；实际：r4c9 ✅ 一致
- 校准覆盖：无

**案例 3｜枪口链：AK-74N + Hexagon Reactor 制退器（`615d8f5dd92c473c770212ef`）**
- 父：`mod_muzzle`（制退器）@ **r3c2**（一体式枪，muzzle 列 c2）
- 子：`mod_muzzle/mod_muzzle`（Wafflemaker 消音器槽）@ **r4c2**
- 规则 3 预期：优先水平沿枪口方向（c1 同行），不足再 r4c2；实际：直接 r4c2（回退位）
- 差异归因：阶段 5 只实现「同列向下」，无水平方向尝试（对 c2 枪，r3c1 理论上可试但被主体行护栏排除）

**案例 4｜枪托链：柯尔特 AR-15 卡宾枪缓冲管（`5649be884bdc2d79388b4577`）**
- 父：`mod_stock`（缓冲管）@ **r3c9**
- 子 1：`mod_stock/mod_stock_000`（枪托槽）@ **r4c9**；子 2：`mod_stock/mod_stock_003` @ **r5c9**
- 规则 4 预期：优先沿枪托方向（右）延伸；c9 右缘无空间 → 回退向下；实际：r4c9/r5c9（回退位）✅ 结果一致但未做方向判断
- 校准覆盖：无

**案例 5｜托腮板：SCAR-L（重点差异）**
- 父：`mod_stock`（折叠枪托）@ **r3c9**
- 子：`mod_stock/mod_stock_002`（FN SCAR托腮板槽 `6181679e6ef05c2ce828f1ab`）@ **auto r6c9**（被当枪托层向下叠）
- 规则 5 预期：**r2c9**（父件正上方）；实际算法：r6c9 ❌
- 校准覆盖：**有**——记录 `mod_stock/mod_stock_002|mod_stock_002|61816734…` = r2c9（你在校准器里手动纠正到上方）
- 差异归因：阶段 3 枪托链按「子槽基名=stock 向下叠」，托腮板 sid `mod_stock_002` 归一后也是 stock；视觉角色层没有「托腮板向上」的判定

**案例 6｜多层嵌套条件子槽：SKS（`574d967124597745970e7c94`）+ UTG SKS SOCOM 导轨基座（`593d1fa786f7746da62d61ac`）**
- 父：`mod_barrel/mod_mount_001` @ **r4c3**（R19.18 固定锚点）
- 子：`mod_scope` @ **r2c3**（上）、`mod_tactical_000..003` @ **r5c3/r5c4/r5c5/r5c6**（下、横排）
- 规则 7 预期：按类型/方向分别布局 → 瞄具在上、战术在下 ✅（结果符合）
- 差异归因：`GW_FIXED_SLOT` **硬编码锚点**（R19.18 你指定的坐标），不是通用的「按类型分方向」逻辑；换一把枪的同类结构不会自动得到这种排列
- 校准覆盖：无（锚点即最终坐标）

## 3. 分类汇总

- **一致**：规则 2（下半部子槽向下）、规则 6（校准只覆盖显示层）。
- **部分一致**：规则 1（上置链向上 ✓，照门带/机匣层例外）、规则 3（只实现回退位）、规则 4（只实现回退位）、规则 7（瞄具/战术分链 ✓，通用子槽不分方向）、规则 7 表行（后备位 ✓，前置方向缺失）。
- **不一致**：规则 5（托腮板自动向下，靠人工校准兜底）。
- **规则冲突待裁决**：追加行 9（R19.15.3 照门带 r2c7 vs R19.19 规则 1 正上方）。
- **尚未验证**：规则 3 的「沿枪口方向」语义（水平向左？还是枪口列内延伸？）——两种读法下结论不同，等你明确后才能判定实现是否该改。

## 4. 若要实现你的设想：建议修改点与影响面（仅建议，未实施）

1. **规则 5（托腮板）**：在阶段 3 枪托链里给「托腮板类子槽」（可用 allow 含托腮板物品/role=cheek 判定，或沿用视觉角色层）单独走「父件正上方」。影响：SCAR-L/H、G28（HK 枪托垫→托腮板链）、Magpul UCS、SMC-90 等带托腮板的枪托（约 6-10 把），当前它们多数已有人工校准记录在 r2c9 一带——改自动规则后这些记录不再覆盖（同坐标）或需清理。
2. **规则 1 泛化**：把「父件 row≤2 子槽向上」扩展为「父件位于本体上半部（row≤3 且 lane=top*）即向上」；照门带是否例外需要先裁决追加行 9。影响：机匣导轨/镜座类配件的子槽方向，估计 30+ 把枪的上部附件链。
3. **规则 3/4 方向优先级**：在枪口链/枪托链加「水平方向找位」步骤（枪口向左 c-1、枪托向右 c+1），失败再走现有向下逻辑。影响：所有带枪口链/枪托链的枪（100+），但因网格边缘（c1/c9）大部分结果不变，主要影响 muzzle=c2 的一体式枪与枪托不在 c9 的枪。
4. **规则 7 分方向**：为通用子槽引入「安装方向」分类（沿用 allow 的 pt/基名），替代一律向下。影响面最大，涉及阶段 8 的全部 300+ 个父子格，需配合回归全量校准语料（397 条记录不受影响，但未校准格会重排）。

以上均为只读建议；按任务 B 约束，未改任何布局代码/数据/校准。

---

## 产物索引

- `docs/r19.19-ak-rear-sight/`：本报告、engine-audit.json、browser-accept.json、calibration-migration.json、data-fix.json、layout-rules-audit.json、backup/（SHA-256 齐）、screenshots/（A1/A2/刷新/校准器 12 张）
