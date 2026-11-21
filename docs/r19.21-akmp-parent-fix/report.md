# R19.21 交付报告｜AKMP 真实父子关系修正 + 校准数据整合

构建标记：**`AM_BUILD = R19.21`**（index.html `?v=r19.21`，serve.py rev `R19.21-*`）
基线：R19.20。全量 pytest：**1179 passed / 1 skipped / 0 failed**。浏览器验收：**全部通过**（含修复后的保存路径复测）。

---

## 1. 三个父照门的实际结构（已与 data/items.json 逐一核对）

| 型号 | 物品 ID | items.json 名称 | pt | AKMP 子槽真实 ID | 子槽 sid / label / allow |
|---|---|---|---|---|---|
| 6P44 Sb.1-30 | `5ac733a45acfc400192630e2` | AK-105 照门 | Scope | `5ac733a45acfc400192630e4` | `mod_sight_rear` / 照门 / `[5a0ed824fcdbcb0176308b0d]`（仅 AKMP） |
| 6P20 Sb.2 | `5ac72e475acfc400180ae6fe` | AK-74M 照门 | Scope | `5ac72e475acfc400180ae700` | 同上 |
| 6P1 Sb.2 | `5649b0544bdc2d1b2b8b458a` | AK-74 照门 | Scope | `5a0ee12cfcdbcb001912fa64` | 同上 |

- 子槽父级=对应照门物品（真实父子关系，随父件安装才生成）；AKMP 系统照门装置 `5a0ed824fcdbcb0176308b0d`（Scope）只出现在这三个子槽的 allow 里。
- **6P1 Sb.2-1 = AKM 照门 `59d650cf86f7741b846413a4` 是不同物品**（名称相近但独立）：其 AKMP 子槽（`5a0eda49fcdbcb001912fa61`）为 R19.20 并列假设的错误建模，已按实测删除（见 §3）。
- 三种照门的子槽在 R19.18 被修正表误删 → 本轮恢复（R19.18 表中三条删除项移除，原始定义取自 `data/items.json.r1918.bak.json`，未新建重复槽位）。

## 2. 使用三种父照门的枪械与逐把验收（浏览器实测）

| 枪械 | 枪械 ID | 默认照门 | 照门显示坐标 | AKMP 子槽 | 关系 | 验收 |
|---|---|---|---|---|---|---|
| AK-74N | `5644bd2b4bdc2d3b4c8b4572` | 6P1 Sb.2 | r2c6 | **r1c6** | 正上方同列 | ✅ |
| AK-74 | `5bf3e03b0db834001d2c4a9c` | 6P1 Sb.2 | r2c6 | **r1c6** | 正上方同列 | ✅ |
| AKS-74 | `5bf3e0490db83400196199af` | 6P1 Sb.2 | r2c6 | **r1c6** | 正上方同列 | ✅ |
| AKS-74N | `5ab8e9fcd8ce870019439434` | 6P1 Sb.2 | r2c6 | **r1c6** | 正上方同列 | ✅ |
| AK-105 | `5ac66d9b5acfc4001633997a` | 6P44 Sb.1-30 | r2c6 | **r1c6** | 正上方同列 | ✅ |
| AK-74M | `5ac4cd105acfc40016339859` | 6P20 Sb.2 | r2c6（auto） | **r1c6** | 正上方同列 | ✅ |
| AK-101 | `5ac66cb05acfc40198510a10` | 6P20 Sb.2 | r2c6（auto） | **r1c6** | 正上方同列 | ✅ |
| AK-102 | `5ac66d015acfc400180ae6e4` | 6P44 Sb.1-30 | r2c6（auto） | **r1c6** | 正上方同列 | ✅ |
| AK-103 | `5ac66d2e5acfc43b321d4b53` | 6P20 Sb.2 | r1c6（记录） | **r0c6**（topPad=1） | 正上方+顶部扩展 | ✅ |
| AK-104 | `5ac66d725acfc43b321d4b60` | 6P44 Sb.1-30 | r1c6（记录） | **r0c6**（topPad=1） | 正上方+顶部扩展 | ✅ |

- 逻辑坐标=显示行−topPad；AK-103/104 父在 r1 → 子槽逻辑 r0，顶部扩展整体下移（正是任务书 §6.C 的示例情形）。
- 每把枪核对项（浏览器）：默认槽位树、子槽正上方同列、候选仅 AKMP、装/卸 AKMP 不动父件、刷新保持。截图 `C-*.png`。
- **条件生成实测（AK-74N）**：卸照门→子槽消失无残留；装 AKM 照门（不支持）→无子槽；换装 AK-74 照门→子槽现于正上方；装 AKMP 入子槽→不动父件；卸 AKMP→子槽保留清空。截图 `B-conditional.png`。

## 3. R19.20 旧并列逻辑的处理

| 项 | 处理 |
|---|---|
| `gwIsAkmpPairSlot` + 照门带并列落位（右邻/整对左移） | **整体移除**（app.js 中已无 `gwIsAkmpPairSlot`/`akmpPair` 痕迹） |
| 新规则 `gwIsAkmpSubSlot` | 按**父件物品 ID**（三种照门，`GW_AKMP_PARENT_SIGHTS`）判定，不看枪名；子槽=父行−1 同列，到顶走顶部扩展（负逻辑行+topPad），不挪右邻不下移 |
| AKM 照门 `59d650cf…` 的 AKMP 子槽 | **删除**（slotfix `R1921_ITEM_SLOT_FIXES`，fetch_data 管线挂接防回退）。**上游差异单列**：tarkov.dev 快照里该子槽存在，与实测确认的三个父照门不符——按你的「以实测为准 + 差异单列」处理；若日后实测推翻，恢复只需移除该表项 |
| VPO-209 照门同构子槽（`5a0eeb41…`） | **保留未动**（未实测确认，历轮口径）；已实测确认其现状（r1c6/r2c6）不被本轮改动 |
| R19.20 五把 AKM 系的并列记录 | 按 §5 标失效留痕，未迁移到任何三父照门记录（不串位） |

## 4. 用户导出校准数据合并报告（`merge-report.json`）

- 导出文件 `gun-layout-calibration (1).json`：**无法从聊天附件直接读取**，但经核对——当前正式文件 `data/gun-layout-calibration.json` 修改前 SHA-256 = **`151e4ad4ab058b6cb5a8302dcb87eb530069f3703beebe5fb33bf734ec84928e`**，与你给出的导出 SHA **字节一致**（schemaVersion=1、toolVersion=R19.16、updatedAt=2026-10-27T21:17:53、152 枪/397 条全吻合）。即：你 21:17 经校准器保存后导出，导出件与正式文件同源——合并即以该文件为权威基线执行 §5 处理，**零冲突、零删除**。
- 你 21:17 手动调整的坐标全部保留未动：AKM/AKMS 照门 r2c6、AK-103/AK-104 燕尾槽基座 r2c7、AKM/AKMS/AKMSN 后握把 r4c8 等（merge-report 逐条留痕）。

## 5. 校准记录变更清单（15 条，身份键不变、不串位）

**A. 复活重算 10 条**（身份键 `mod_sight_rear/mod_sight_rear|mod_sight_rear|<父照门ID>`；原 R19.18 失效注记解除，坐标=父照门最终坐标−1 行同列；旧坐标留痕于 note 与 migration JSON 的 before 字段）：

| 枪械 | 父照门 | 旧坐标 | 新坐标 | 原因 |
|---|---|---|---|---|
| AK-74N / AK-74 / AKS-74 / AKS-74N | 6P1 Sb.2 | r2c6 | **r1c6** | 父 r2c6（记录）→ 正上方 |
| AK-105 | 6P44 Sb.1-30 | r2c6 | **r1c6** | 同上 |
| AK-74M / AK-101 / AK-102 | 6P20/6P44 | r1c6 | **r1c6**（复活） | 父 r2c6（auto）→ 正上方；坐标恰同，注记更新 |
| AK-103 / AK-104 | 6P20/6P44 | r2c6 | **r0c6** | 父 r1c6（记录）→ 正上方=逻辑 r0（顶部扩展） |

**B. 标失效 5 条**（身份键 `mod_sight_rear/mod_sight_rear|mod_sight_rear|59d650cf…`，父件=AKM 照门 6P1 Sb.2-1）：AKM r2c7、AKMS r2c7、AKMN r1c7、AKMSN r1c7、VPO-136 r1c7——坐标原样保留作历史存档，注记 R19.21 写明「并列假设错误建模、不再生效、不得迁移」；**未迁移**为三父照门的任何记录。

- 记录总数 397 → **397**（0 删除、0 清空、0 重建）；变更 15 条；其余 382 条逐条未动。

## 6. 修改前后 SHA-256 / 数据量

| 文件 | 修改前 | 修改后 |
|---|---|---|
| `data/items.json` | `460b992c…cc939` | `ac81f0aa…a6191`（三子槽恢复 + AKM 错误子槽删除） |
| `data/gunslots.json` | `29b987b3…e3e` | `29b987b3…e3e`（**未变**） |
| `data/gun-layout-calibration.json` | `151e4ad4…928e`（=用户导出） | `d0a811f4…d15d`（仅 §5 的 15 条） |
| `app.js` | `d5c74146…69e5` | `0eac6e5b…0aa2`（并列规则→正上方规则 + AM_BUILD） |
| `calibrator.js` | `cd7117ae…1595` 前身（R19.20 版） | `cd7117ae…1595`（**保存陈旧值 bug 修复**，见 §7.3） |

备份：`docs/r19.21-akmp-parent-fix/backup/`（全部源文件 + 各自 SHA-256）；`data/items.json.r1921.bak.json`。校准记录 152 枪/397 条 → 152/397。

## 7. 测试与浏览器验收

**7.1 专项** `tests/test_r19_21_round.py` 12 项全过（A 父照门数据 / B 条件生成 / C 布局 / D 合并+记录 / E 自动布局 / F 回归+管线幂等）。
**7.2 全量 pytest**：**1179 passed / 1 skipped / 0 failed**；引擎审计 `tools/r1929_audit.js` **91 项 0 失败**；R19.18/19.17/15.x 各审计随断言升级后全绿（对照 §7.4）。
**7.3 浏览器验收**（`tools/r1929_accept.py`，两轮复测均 pass）：
- C：10 把枪子槽全部「父件正上方同列」（含 AK-103/104 顶部扩展）✅ 截图 `C-*.png`
- B：装/换/卸照门的子槽条件生成五态 + AKMP 装卸 ✅ `B-conditional.png`
- D：校准器双卡独立选中/拖动（拖子槽不动父件）、保存→刷新位置保持、与主画布一致、测试坐标已还原 ✅ `D-calibrator.png`
- F：AKM 单照门槽、VPO-209 现状保留 ✅ `F-vpo209.png`
**7.3.1 连带发现并修复的校准器 bug**：`buildGunPayload` 对「拖回自动位」的槽位跳过后又回落 `S.saved` 旧坐标——「拖回自动位+保存」会把上一次保存值原样写回（界面与落盘不一致）。已改为：本次碰过的槽位一律按当前坐标落盘并保留旧注记。该 bug 由本轮 D 测试的还原步骤暴露，修复后复测通过（落盘=界面）。
**7.4 冲突断言升级清单**（未删除、未弱化）：`test_r19_18` B 组三处（5.45/5.56 有 AKMP 子槽 / AKM 系无 AKMP / 三照门必须带子槽）、J 处（失效必留痕语义化）、`test_r19_19` A1/A2/A3/A4 五处、`test_r19_20` 整体重写为 R19.21 真值、`test_r19_13` 照门带标记、r1925/r1926/r1927 各审计期望（AKMP 仅经父照门子槽、AKM 系单槽、AK-74N 语料 3 条全应用 14 格等）。

## 8. 尚未确认清单（待你游戏内实测）

1. **VPO-209 照门**（`59e8977386f77415a553c453`）的 AKMP 子槽（`5a0eeb41fcdbcb098008726f`）——同构结构但未列入本轮三父照门，现状保留（r2c6 正下方显示）。若实测确认它也是 AKMP 父照门（或确认应删），改 `tools/slotfix.py`/`GW_AKMP_PARENT_SIGHTS` 一处即可。
2. **AKMB系统照门**（`5a0eb980fcdbcb001a3b00a6`）无任何子槽（上游如此）——若实测 AKMP 也能挂 AKMB，需补数据。
3. **AKM 系（AKM/AKMS/AKMN/AKMSN/VPO-136）**：按本轮确认模型（AKMP 父照门=三种叶式照门，AKM 照门槽不收叶式照门）**不再具备 AKMP 安装能力**。若游戏内 AKM 系可装 AKMP（例如经 AKMB 或直接入照门槽），请指示兼容路径。
4. 其他照门（TT01/RD/RS 系列基座等）均未自动获得 AKMP 子槽（审计锁死）；如有实测例外请逐件指示。

---

## 产物索引

`docs/r19.21-akmp-parent-fix/`：本报告、engine-audit.json（91 项）、browser-accept.json、data-fix.json、calibration-migration.json（逐条 before/after）、merge-report.json、backup/（SHA 齐）、screenshots/（C×10 / B / D / F-vpo209）
