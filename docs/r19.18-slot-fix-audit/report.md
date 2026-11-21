# R19.18 武器槽位 / 配件兼容性 / 校准器编辑能力专项修复 — 交付报告

构建标记：**`AM_BUILD = R19.18`**（index.html 资源版本同步 `?v=r19.18`）
证据目录：`docs/r19.18-slot-fix-audit/`（`engine-audit.json` 引擎审计 · `browser-accept.json` 浏览器验收 · `screenshots/`）

---

## 一、10 项问题逐项完成状态

| # | 问题 | 状态 | 根因 | 修法（数据层 / 应用层） |
| --- | --- | --- | --- | --- |
| 1 | SVDS 缺燕尾槽瞄具槽位 | ✅ 已修 | `gwSlotVisible` 的「同基名兄弟槽已装即隐藏」把 SVDS 的 `mod_mount_000`（燕尾槽基座）当成 `mod_mount_001`（照门固定环）的重复项隐藏了 | 应用层：兄弟槽只在**同基名且 allow 清单完全相同**（真重复）时才互相顶替；新增 `GW_FIXED_SLOT` 固定锚点 → SVDS 燕尾槽落在 **r2c7**（role=dovetailMount） |
| 2 | 5.45/5.56 AK 出现 AKMP RS | ✅ 已修 | 叶式照门（AK-74 / AK-74M / AK-105 照门）上游各带一个 `mod_sight_rear` 子槽（allow 只有「AKMP 系统照门装置」） | 数据层：`tools/slotfix.py` 删除该子槽（3 个物品）；AKM 照门的同名子槽**保留**（AKM 枪族按 AKMP RS 配置） |
| 3 | G28 / S12K 七行无法编辑 | ✅ 已修（实测） | 校准器网格/拖拽边界对 6 行写死的风险点已逐项排查：网格行数随布局动态（`previewRows/curRows`）、画布容器可滚动、拖拽按**逻辑行**换算 | 校准器 + 主程序：G28（`6176aca6…`）与 Saiga-12K（红线）（`6981d72e…`）默认装配均为 7 行，第 7 行 4 个槽位可见/可点/可拖/可撤销重做（浏览器实测） |
| 4 | T-5000 战术槽位过多 | ✅ 已修 | 「Orsis T-5000护木」上游有 4 个导轨位（3 个完全重复），预设又装满 → 4 个战术槽 | 数据层：删掉两个重复导轨位 → 护木只剩 2 个导轨位（长/中导轨位 + 中导轨位），战术设备槽位 4 → **2** |
| 5 | 两把 SKS 缺 SOCOM 槽 | ✅ 已修 | `mod_barrel/mod_mount_001`（UTG SKS SOCOM 导轨基座）被兄弟槽规则隐藏 | 应用层：兄弟规则细化后 SOCOM 槽出现 → 固定 **r4c3**；装上 SOCOM 后条件子槽 瞄具 **r2c3**、战术装置 **r5c3**（其余战术位依次 r5c4–r5c6）；卸下 SOCOM 后条件子槽全部消失 |
| 6 | GP-25 榴弹槽缺失/不一致 | ✅ 已修 | `gwSlotVisible` 里 `base === "launcher"` **无条件隐藏**，所有 AK 的 `mod_launcher` 都不显示 | 应用层：取消全局隐藏 + 新增布局规则（导气管同列下一行）→ 18 把真实兼容的 AK 枪械在 **r4c3**（导气管 r3c3 正下方）显示 GP-25 槽；AK-545 等无此槽的枪械不显示 |
| 7 | AKM 误显示 AK-74 系列照门 | ✅ 已修 | 与问题 2 同源（AK 族照门子槽/兼容表错位） | 同问题 2 的数据修正；AKM 族照门 allow 本就只有 AKM 照门 / AKMB / Taktika / RD Enhanced（已加测试锁死） |
| 8 | VSK-94 出现 VSS/VAL 环形基座 | ✅ 已修 | 「9A-91 9x39 消音器」（VSK-94 用）上游带 `mod_mount` 子槽，allow 只有「Zenit B-3 VSS/VAL 环形基座」 | 数据层：删除该子槽；VSS / AS VAL 一体式枪管上的同名接口**保留** |
| 9 | AS VAL MOD.4 top cover 燕尾槽未隐藏 + 3.5 英寸导轨重复 | ✅ 已修 | ① 套件护木上游有**两个** allow 完全相同的 3.5 英寸导轨位；② 枪身燕尾槽 `mod_mount_004` 与 top cover 的导轨接口互斥，但代码里没有这条互斥 | 数据层：删掉重复导轨位 → 只剩 1 个；应用层：新增 `GW_SLOT_CONFLICTS`（按配件**物品 id** 判定，真实安装状态驱动）→ 装上 top cover 燕尾槽失效（连同候选一起不可用），卸下后自动恢复 |
| 10 | TKPD 多 2 个战术槽 / 少 2 个燕尾槽 | ✅ 已修 | ① 护木上游有左右镜像的两个战术导轨位（allow 仅差一件 Insight AN/PEQ-2）；② 枪身两个燕尾槽 `mod_mount_000` / `mod_mount_002` 被兄弟规则隐藏 | 数据层：删掉护木的两个镜像战术位 → 只剩 1 个真实战术接口（`mod_tactical`）；应用层：兄弟规则细化 → 两个枪身燕尾槽恢复（`mod_mount_000`→r2c8、`mod_mount_002`→r2c2，均可装真实燕尾槽镜/PSO） |

---

## 二、修改文件清单

| 文件 | 修改点 |
| --- | --- |
| `tools/slotfix.py`（新） | R19.18 真实槽位修正表（8 个物品 → 12 个子槽），每条带 `evidence`（游戏实测结论） |
| `tools/r1926_datafix.py`（新） | 把修正表套用到当前 `data/items.json`（带备份 + 报告） |
| `tools/fetch_data.py` | `_apply_slot_correction()` 接入 R19.18 修正表 → **下次刷新上游数据不会回退**（原 Nightforce `keep` 逻辑保留并拆出独立函数） |
| `tools/r1926_calibmigrate.py`（新） | 校准数据迁移：给失效记录补 `note`（不改坐标、不删记录、不改挂别的槽位） |
| `app.js` | ① `gwSlotVisible`：取消 launcher 全局隐藏、兄弟槽只在真重复时顶替、新增真实互斥判定；② 新增 `gwSameSlotKind` / `GW_SLOT_CONFLICTS` / `gwSlotConflicted` / `GW_FIXED_SLOT`；③ 布局新增阶段 2.2（用户固定坐标锚点）与 2.3（GP-25 置于导气区域下方）；④ 燕尾槽阶段跳过已落位槽；⑤ `AM_BUILD=R19.18` |
| `tools/r1926_audit.js`（新） | 引擎审计：45 项检查（真实槽位树 + 安装行为），含全量校准回归口径 |
| `tools/r1926_accept.py`（新） | 真实浏览器验收：51 项检查（16 把枪 + 校准器七行拖拽/撤销/重做） |
| `tools/r1926_probe.js` / `r1926_look.py` / `r1926_calprobe.py`（新） | 勘察探针（槽位树 / 主画布 / 校准器） |
| `tools/r1921_assert.js` | 燕尾槽审计增加 SVDS 例外（r2c7），其余仍必须 r2c8 |
| `tools/r1925_engine.js` | 校准回归口径升级：应用 + 失效 + 当前不可用 = 全部记录（不再要求 100% 命中） |
| `tools/serve.py` | rev 标记 → `R19.18-`（接口未改） |
| `data/items.json` | 8 个配件的 12 个多余/错误子槽被删除（备份：`data/items.json.r1918.bak.json`） |
| `data/gun-layout-calibration.json` | **仅**给 15 条失效记录补 `note`（记录数不变，坐标不变） |
| `tests/test_r19_18_round.py`（新） | A–J 十组专项测试（28 项） |
| `tests/test_r19_6_round.py` | 「榴弹槽不占格」断言升级为 R19.18 口径（不得整体隐藏 + 互斥/重复规则必须在） |
| `tests/test_r19_15_1/15_2/15_3_round.py` | 燕尾槽断言升级：SVDS 例外 r2c7，其余仍必须 r2c8（两处同时成立） |

---

## 三、AK 照门兼容性全量审计清单

判定口径：**槽位 allow 清单里是否直接列着「AKMP 系统照门装置」（5a0ed824fcdbcb0176308b0d）**。

| 枪械 | 口径 | 修改前 | 修改后 |
| --- | --- | --- | --- |
| AK-74N `5644bd2b…` / AK-74 `5bf3e03b…` / AK-74M `5ac4cd10…` / AKS-74 `5bf3e049…` / AKS-74N `5ab8e9fc…` | 5.45x39 | 有 `mod_sight_rear/mod_sight_rear` 子槽（只收 AKMP RS） | **子槽移除** → 不再出现 AKMP RS |
| AK-105 `5ac66d9b…` / AK-101 `5ac66cb0…` / AK-102 `5ac66d01…` | 5.45x39 / 5.56x45 | 同上 | 同上 |
| AK-103 `5ac66d2e…` / AK-104 `5ac66d72…` | 7.62x39 | 同上 | 同上（这两把按数据口径用 AK-105/AK-74/AK-74M 叶式照门，游戏内没有 AKMP 侧轨接口） |
| AKM `59d60885…` / AKMS `59ff3463…` / AKMN `5a0ec13b…` / AKMSN `5abcbc27…` / VPO-136 `59e61525…` | 7.62x39 | 有 AKMP 子槽（照门基座型） | **保留**（AKMP RS 配置成立） |
| VPO-209 `59e6687d…` | .366 TKM | 照门为「VPO-209 照门」，本就无 AKMP 子槽 | 无变化 |

合法照门（AK-74 照门 / AK-74M 照门 / AK-105 照门 / AKM 照门 / AKMB / Taktika / RD Enhanced）全部保留，未删除任何真实照门槽位。

---

## 四、GP-25 实际兼容枪械清单（18 把，槽位均在 r4c3 = 导气管 r3c3 正下方）

AK-74N、AK-74、AK-74M、AKS-74、AKS-74N、AK-105、AK-101、AK-102（5.45/5.56）·
AK-103、AK-104、AKM、AKMS、AKMN、AKMSN、VPO-136（7.62x39）· VPO-209（.366 TKM）· AK-12、AK-308。
不含该槽的枪械（如 AK-545）不显示，也不出现任何虚假榴弹槽。

---

## 五、G28 / S12K 全自动版第七行实测

| 枪械 | ID | 行数 | 第 7 行槽位 | 实测 |
| --- | --- | --- | --- | --- |
| HK G28 7.62x51 | `6176aca650224f204c1da3fb` | 7（topPad=1） | `mod_reciever/mod_handguard/mod_tactical_000/001/002`、`mod_bipod` | 校准器网格 7 轨、第 7 行卡片可见可点；**拖动 r7c1 → r6c1 生效**，撤销回 r7c1、重做再回 r6c1 |
| Saiga-12K 12 铅径自动霰弹枪（红线） | `6981d72ed009ad83920da43a` | 7（topPad=1） | 4 个槽位 | 主画布与校准器均为 7 行，第 7 行正常渲染 |

---

## 六、校准数据回归（记录数 / SHA-256 / 迁移）

| 项 | 值 |
| --- | --- |
| 记录数 | **397 → 397**（枪械 152 → 152，一条没删） |
| SHA-256（R19.18 前） | `6f75a9015cf3cd080d20d0b66854c1675a5ca94f00d4defd70c305afce8f8914` |
| SHA-256（R19.18 后） | `d969a2c44d5cea6c4e43dfb1ddb13a16a8dca4f2e8cc7612bea43e655b926e44`（差异**仅**来自 15 条记录新增的 `note` 字段） |
| 应用情况 | 397 = **已应用 383** + **失效 13** + **当前不可用 1**（AS VAL MOD.4 的 `mod_mount_004`，装 top cover 时按真实互斥失效，卸下后自动恢复） |
| 失效记录 | 13 条：AK 叶式照门的 AKMP 子槽（10）+ VSK-94 的 B-3 子槽（1）+ AS VAL MOD.4 重复 3.5 英寸导轨位及其战术子槽（2）。全部**保留原坐标**、补 `note` 写明原因，不改挂到别的槽位 |
| 备份 | `data/gun-layout-calibration.json.r1918.bak.json`（迁移前原始字节）、`docs/r19.18-slot-fix-audit/calibration-migration.json` |

---

## 七、测试结果

- **专项**：新增 `tests/test_r19_18_round.py` **28 项全过**（A–J 十组）。
- **全量 pytest**：**1145 passed / 1 skipped / 0 failed**（R19.18 前为 1117 passed / 1 skipped）。
  - 跳过项：需要 node 的用例在无 node 环境下跳过（本机有 node，实际执行）。
  - 升级的旧断言（未删除、未弱化）：`test_r19_6_round.py`（榴弹槽口径）、`test_r19_15_1/15_2/15_3_round.py`（燕尾槽 SVDS 例外）、`test_r19_17_round.py`（校准回归口径）。
- **引擎审计**：`tools/r1926_audit.js` **45 项全过**。
- **浏览器验收**：`tools/r1926_accept.py` **51 项全过**，`failures=[]`，console 无报错。

---

## 八、浏览器实际验收清单（本地 8787 真实运行）

| 枪械 | 检查点 | 结果 |
| --- | --- | --- |
| SVDS `5c46fbd7…` | 燕尾槽槽位存在 / r2c7 / 不重复 / 候选含真实燕尾槽镜 | ✅ |
| AK-74N、AK-74M（5.45） | 无 AKMP RS 子槽 | ✅ |
| AK-101、AK-102（5.56） | 无 AKMP RS 子槽 | ✅ |
| AKM、AKMS | AKMP RS 槽位存在（AKMP 配置） | ✅ |
| G28 | 7 行 + 第 7 行槽位 | ✅ |
| Saiga-12K（红线） | 7 行 + 第 7 行槽位 | ✅ |
| T-5000 | 战术槽 2 个 / 导轨位 2 个 | ✅ |
| SKS、OP-SKS | SOCOM 槽 r4c3 → 装上后瞄具 r2c3 / 战术 r5c3 → 卸下后子槽消失 | ✅ |
| AK-74N、AKM、AK-101 | GP-25 槽 r4c3（导气管下方）+ 候选含 GP-25 | ✅ |
| AK-545 | 无 GP-25 槽（不兼容不得出现） | ✅ |
| VSK-94 | 无 B-3 环形基座槽 | ✅ |
| AS VAL MOD.4 | 状态 A/B/C：3.5 英寸导轨只有 1 个、装 top cover 燕尾槽失效、卸下恢复、条件子槽无残留 | ✅ |
| TKPD | 战术槽 1 个 + 两个燕尾槽位（可装真实燕尾槽镜） | ✅ |
| 刷新 | SVDS 刷新后仍为 r2c7 | ✅ |
| 校准器 | G28 第 7 行卡片可见、拖动生效、撤销/重做正确 | ✅ |

---

## 九、仍未解决 / 需要留意

1. **AK-103 / AK-104（7.62x39）**：本项目数据里它们使用 AK-105 / AK-74 / AK-74M 叶式照门（游戏内无 AKMP 侧轨接口），因此与 5.45/5.56 一样不再出现 AKMP RS。若游戏内实测确认这两把可装 AKMP RS，请在 `tools/slotfix.py` 恢复对应子槽即可（表内已按物品 id 组织，改一处即可）。
2. **T-5000 / TKPD 的导轨位数量**：本轮按用户实测口径把「上游把同一条导轨拆成多个槽位」的多余位删除（T-5000 4→2、TKPD 3→1）。上游 tarkov.dev 快照仍保留原始位（`data/items.json.r1918.bak.json` 可回查），`tools/slotfix.py` 是唯一的口径来源，后续如与游戏实测不符，改这张表 + 重跑 `tools/r1926_datafix.py` 即可。
3. **AK 族「其余变体」**：AK-545 / AK-12 / AK-308 的照门与燕尾槽结构与 AK-74N/AKM 不同，本轮未改动（仅按数据事实显示）。
4. 校准器第七行在 G28 / S12K 上可编辑；超过 7 行时网格仍按布局动态增高（`previewRows`），逻辑行范围仍受保存格式限制（−6..6），与主程序一致。

---

## 十、产物清单

- `docs/r19.18-slot-fix-audit/engine-audit.json` — 45 项引擎检查 + 全量校准回归 + AK/GP-25 明细
- `docs/r19.18-slot-fix-audit/browser-accept.json` — 51 项浏览器检查 + 逐枪坐标快照
- `docs/r19.18-slot-fix-audit/data-fix-report.json` — 8 个物品修正前后槽位对照
- `docs/r19.18-slot-fix-audit/calibration-migration.json` — 校准迁移明细（含 SHA-256 前后值）
- `docs/r19.18-slot-fix-audit/screenshots/` — 各枪验收截图
- 备份：`data/items.json.r1918.bak.json`、`data/gun-layout-calibration.json.r1918.bak.json`
