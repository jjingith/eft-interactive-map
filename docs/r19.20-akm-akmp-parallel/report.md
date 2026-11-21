# R19.20 交付报告｜AKM 照门 / AKMP 并列布局修正

构建标记：**`AM_BUILD = R19.20`**（index.html `?v=r19.20`，serve.py rev `R19.20-*`）
基线：R19.19。全量 pytest：**1170 passed / 1 skipped / 0 failed**。浏览器验收：**全部通过**。

## 1. 修改文件清单与修改点

| 文件 | 修改点 |
|---|---|
| `tools/r1928_datafix.py`（新） | 数据恢复脚本：恢复 AKM 照门的 AKMP 子槽 + 撤回五把枪枪身照门槽 allow 里的 AKMP（items.json / gunslots.json 两处） |
| `data/items.json` | ① 「AKM 照门」恢复子槽 `5a0eda49fcdbcb001912fa61`（sid=mod_sight_rear，allow=[AKMP系统照门装置]）；② 五把枪 `mod_sight_rear` allow 移除 AKMP RS |
| `data/gunslots.json` | 五把枪 `mod_sight_rear` allow 同步移除 AKMP RS（与 items.json 一致） |
| `tools/slotfix.py` | R1919_ITEM_SLOT_FIXES / R1919_GUN_SLOT_ALLOW_ADDS **清空**（R19.20 作废 R19.19 A2 单槽合并；保留表名供 fetch_data 挂接）；R19.18 叶式照门修正不动 |
| `tools/fetch_data.py` | 无需改（挂接点继续生效：AKM 子槽不再被删、allow 不再被并入）——下次刷新上游不回退 |
| `app.js` | ① 新增 `gwIsAkmpPairSlot`（AKMP-only 子槽且父件=AKM 照门；VPO-209 不命中）；② 照门带并列落位：AKMP=照门同行右邻，右侧被占（拉机柄 r2c9）时**整对左移一格**；AKMP 绝不落照门正下方、不进左向队列；③ `AM_BUILD = R19.20` |
| `data/gun-layout-calibration.json` | 仅 5 条 AKMP 子槽记录迁移：r2c6（R19.19 遗留正下方位）→ **r1c7**（照门 r1c6 右邻并列位），身份键不变，失效注记替换为 R19.20 说明。397→397 条 |
| `tools/r1928_calibmigrate.py`（新） | 上述迁移脚本（逐条留痕） |
| `tools/layoutcal.py` | 校验修复：失效注记记录（note 含「不再生效」，R19.18 项目约定）不再参与同格占位——修复 R19.19-A1 遗留的「照门记录 r2c6 与失效子槽记录同格」导致 `/api/layout-calibration` 整包拒绝的问题；活跃记录同格仍拒绝 |
| `tools/r1928_audit.js` / `r1928_accept.py`（新） | R19.20 引擎审计（69 项）+ 浏览器验收 |
| `tools/r1926_calibmigrate.py` | STALE_OWNERS 移除 AKM 照门条目（子槽恢复、记录复活） |
| `tools/r1926_audit.js`、`tools/r1927_audit.js`、`tests/test_r19_18/19/13_round.py` | 冲突断言按纪律**升级为更强断言**（见 §7） |
| `tests/test_r19_20_round.py`（新） | 12 项专项测试 |
| `calibrator.js` | **未修改**（预览/拖动/保存走与主程序同一 applyCalibration，自动继承并列结果） |

## 2. 每把受影响枪械的两个槽位

五把枪结构一致（默认装配均装「AKM 照门」）：

| 枪械 | 枪械 ID | 左槽（AKM 原有照门） | 右槽（AKMP） | 最终坐标 | 自动布局坐标 |
|---|---|---|---|---|---|
| AKM | `59d6088586f774275f37482f` | `mod_sight_rear`（`59d6088586f774275f374836`），父=枪身根级，候选：AKM 照门 / AKMB系统照门 / TT01 / RD Enhanced V2 | `mod_sight_rear/mod_sight_rear`（`5a0eda49fcdbcb001912fa61`），**父=AKM 照门（真实子槽）**，候选：仅 AKMP系统照门装置 | **r1c6 / r1c7**（同行并列） | r2c7 / r2c8（右邻被拉机柄占 → 整对左移） |
| AKMS | `59ff346386f77477562ff5e2` | 同上 | 同上 | r1c6 / r1c7 | r2c7 / r2c8 |
| AKMN | `5a0ec13bfcdbcb00165aa685` | 同上 | 同上 | r1c6 / r1c7 | r2c6 / r2c7（燕尾槽枪自然右邻） |
| AKMSN | `5abcbc27d8ce8700182eceeb` | 同上 | 同上 | r1c6 / r1c7 | r2c6 / r2c7 |
| VPO-136 | `59e6152586f77473dc057aa1` | 同上（无 RD，候选 3 项） | 同上 | r1c6 / r1c7 | r2c7 / r2c8 |

- 逻辑坐标=显示坐标（topPad=0）；最终坐标 = 照门人工记录 r1c6 + AKMP 并列记录 r1c7。
- 候选分离实测（浏览器）：左槽 = AKM 照门(已装)/AKMB/RD/TT01，**无 AKMP**；右槽 = 仅 AKMP系统照门装置。

## 3. 修改前后真实槽位树差异

| 项 | R19.19（修改前） | R19.20（修改后） |
|---|---|---|
| AKM 照门（`59d650cf…`）子槽 | 无（R19.19 删除） | **恢复** `5a0eda49…`（allow=[AKMP RS]，真实父子语义） |
| 五把枪枪身 `mod_sight_rear` allow | 含 AKMP RS（R19.19 并入） | **移除** AKMP RS（候选不混淆） |
| 槽位树照门槽数 | 1 个/枪 | **2 个/枪**（左枪身槽 + 右 AKM 照门子槽） |
| 显示位置 | 单槽 | 同行并列（AKMP=照门右邻；绝不正下方） |
| VPO-209 照门子槽 | 在（r2c6 正下方） | **不变**（范围外保留） |
| 叶式照门（AK-74/AK-74M/AK-105）AKMP 子槽 | 无（R19.18 删除） | 不变（R19.18 口径保留） |

## 4. 校准记录变更清单

- 修改前 152 枪 / **397** 条 → 修改后 152 枪 / **397** 条（0 删除、0 清空、0 重建）。
- 变更 **5 条**（`docs/r19.20-akm-akmp-parallel/calibration-migration.json` 逐条留痕）：

| 身份键 | 枪械 | 修改前 | 修改后 | 原因 |
|---|---|---|---|---|
| `mod_sight_rear/mod_sight_rear\|mod_sight_rear\|59d650cf86f7741b846413a4` | AKM / AKMS / AKMN / AKMSN / VPO-136（各 1 条） | r2c6（R19.19 标失效的正下方遗留位） | **r1c7** | 恢复子槽后记录复活；迁至照门（r1c6）右邻并列位。身份键不变（同槽位同父件），无串位 |

- 照门记录（`mod_sight_rear\|mod_sight_rear\|`，r1c6）**未动**；其余 387 条未动。
- SHA-256：`7d1083c6faae6d773ef662e8fbb73a23f7703db5a141c0d3802eecb797be7535` → `7e2f600fb41b7e23f13de109d19795690b93a2ca964da58f49d14cf1e7368e19`（仅上述 5 条坐标/备注）。
- 备份：`docs/r19.20-akm-akmp-parallel/backup/`（app.js / calibrator.js / items / gunslots / calibration / slotfix + SHA-256）；另有 `data/*.r1920.bak.json`。

**连带修复（必须报告）**：R19.19-A1 把五把 5.45 枪的照门记录移到 r2c6 后，与 R19.18 遗留的失效子槽记录（同格 r2c6）触发 layoutcal「同枪同格拒绝」，`GET/POST /api/layout-calibration` 自 R19.19 起整包拒绝（页面靠静态 JSON 回退所以未显形）。本轮按项目既定失效标记（note 含「不再生效」）让失效记录不参与同格占位，API 恢复正常（152 枪/397 条 ok:true），活跃记录的保存防重叠保护不变。

## 5. 浏览器验收结果（`tools/r1928_accept.py`，全过）

| 场景 | 结果 |
|---|---|
| 1 默认状态 | 五把枪均：左 `mod_sight_rear` r1c6（AKM 照门）/ 右 `mod_sight_rear/mod_sight_rear` r1c7（AKMP 槽）✅ 截图 `pair-*.png` |
| 2 槽位数量 | 每枪恰好 2 个照门槽并列，无纵向重复、无多余卡 ✅ |
| 3 兼容性 | 左槽候选 AKM 照门/AKMB/RD/TT01（无 AKMP）；右槽仅 AKMP系统照门装置 ✅ `candidates.png` |
| 4 安装 | 右槽装入 AKMP成功；左槽物品未被改动；并列保持 ✅ `after-install.png` |
| 5 拆卸 | 卸下 AKMP后右槽清空、并列保持、卡片数复原、无残留 ✅ `after-remove.png` |
| 6 刷新 | 刷新后仍 r1c6/r1c7 并列 ✅ `reload.png` |
| 7 校准器 | 双卡并列显示；AKMP 卡独立拖到 r1c8（照门卡纹丝不动）；撤销还原 r1c7 ✅ `calibrator-drag.png` |
| 8 回归 | AK-74N 照门 r2c6 单槽 ✓；VPO-209 现状保留（r1c6 + 子槽 r2c6）✓ `regression-vpo209.png` |

## 6. 测试结果

- **专项** `tests/test_r19_20_round.py`：12 项全过（并列/候选/装卸/数据恢复/父子语义/校准记录/范围保护/版本）。
- **引擎审计** `tools/r1928_audit.js`：**69 项 0 失败**（含 AUTO 与 FINAL 双路径并列断言、装 AKMP 无重复、VPO-209/5.45/AK-103·104 范围锁）。
- **全量 pytest**：**1170 passed / 1 skipped / 0 failed**。
- R19.18/R19.17/R19.15.x 各审计随断言升级后全绿。

## 7. 旧断言升级清单（未删除、未弱化）

| 位置 | 旧断言（R19.19 单槽口径） | 升级后（R19.20 并列口径） |
|---|---|---|
| `r1926_audit.js` / `test_r19_18::test_B_akm_family_uses_akmp_rs` | `akm_akmp_child_slot_gone` | `akm_akmp_child_slot_restored` + 每把两槽 + AKMP 不入枪身 allow |
| `test_r19_18::test_B_new_ak_variant_will_not_regress` | 任何照门件不得带 AKMP 子槽 | 仅 AKM 照门带 AKMP 子槽（真实语义）；叶式照门不得带；AKMP 不入枪身 allow |
| `test_r19_19::test_A2_*`、`r1927_audit.js` A2 块 | 单照门槽 + AKMP 并入 allow | 并列双槽 + 候选分离 + 同行右邻 + 非正下方 |
| `test_r19_19::test_slotfix_*` | R1919 表含删除/并入项 | 两表已作废清空 + R19.18 表仍生效 |
| `test_r19_19::test_A4_akmp_only_records_stale_not_migrated` | 5 条记录标失效 | 5 条记录复活并迁至 r1c7 |
| `test_r19_13::test_row2_anchors_*` | `take(2, rsCol, rs, true)` | `take(2, sightCol, …)` + 并列规则在照门带内 |

## 8. 未解决 / 仍需游戏内确认

1. **AKMP 只在装了「AKM 照门」后出现**（真实父子语义：AKMP 挂在 AKM 照门上）——空照门槽或装 AKMB/TT01 时右侧不显示 AKMP 槽。若游戏内 AKMP 是与 AKM 照门完全无关的独立枪身槽（不需要 AKM 照门即可装），请告知，我会把它提升为独立枪身槽。
2. **AKMB系统照门**无 AKMP 子槽（上游数据如此）——装 AKMB 时右槽消失。若游戏内 AKMB 也能挂 AKMP，需补数据。
3. VPO-209 同构子槽（r2c6 正下方）按本轮范围保留现状，待你实测后决定是否套用并列规则。
4. 自动布局（无校准记录时）AKM 系照门带因拉机柄占 r2c9，整对落在 r2c7/r2c8（与校准位 r1c6/r1c7 不同行）——左右关系一致；若你希望自动布局也用 r1 行，请指示。

## 产物索引

`docs/r19.20-akm-akmp-parallel/`：本报告、engine-audit.json、browser-accept.json、data-fix.json、calibration-migration.json、backup/（SHA-256 齐）、screenshots/（pair×5 / candidates / after-install / after-remove / reload / calibrator-drag / regression-vpo209）
