# R47 配枪测试失败排查台账

host=HOMONAS user=MASTERJJ at=2026-11-04 05:07:56

范围：`tests/` 中 5 个长期失败的配枪工作台相关用例。
约束遵守：未删除/跳过/放宽任何断言；未新增依赖；未改护甲/弹道公式口径；未改 `tools/installer.py` 与 `build/*.ps1`；未 `git commit`。

## 1. 修改前后总览

| 阶段 | passed | failed | skipped |
|---|---|---|---|
| 修改前 `pytest tests -q` | 1703 | 5 | 1 |
| 修改后 `pytest tests -q` | **1708** | **0** | 1 |

失败用例与分类：

| 用例 | 分类 | 结论 |
|---|---|---|
| `tests/test_r19_1_round.py::test_candidate_columns_match_reference_order` | A 类（harness 过时） | 已修绿 |
| `tests/test_r19_5_round.py::test_zoning_is_generic_semantic_rules` | A 类（harness 过时，误伤注释/物品名） | 已修绿 |
| `tests/test_r19_11_round.py::test_hide_incompat_filters_without_touching_data` | A 类（接口签名变更） | 已修绿 |
| `tests/test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree` | A 类（变量改名） | 已修绿 |
| `tests/test_r6_gun_workbench.py::test_gun_workbench_business_logic` | A 类（沙箱抽取清单过时） | 已修绿 |

C 类（业务数字变化）：**0 个**。5 个失败均不涉及期望业务数值，未改任何期望值。

## 2. 逐个判定与修改证据

### 2.1 test_r19_1_round.py::test_candidate_columns_match_reference_order

原始报错：`AssertionError: 找不到 gunColumns`。

根因：
- `app.js` 的列函数已从 `function gunColumns()` 改为 `function gunColumns(rows)`（R19.28：按候选行组装列、缺失属性整列隐藏），且返回值由 `return [...]` 改为 `return cols;`；
- 列标签随界面本地化为中文：`Ergo → 人机`、`Kg → 重量`、`下级槽 → 子槽`。
- 业务口径未变：首列仍是「配件」，人机仍在重量之前，`尺寸` 列缺数据说明文字仍包含「占格尺寸」。

修改（测试）：改为按花括号提取 `gunColumns` 函数体，检查列常量标签与 `cols` 组装顺序（`COL_ERGO` 在 `COL_W` 之前），保留全部原意断言。

### 2.2 test_r19_5_round.py::test_zoning_is_generic_semantic_rules

原始报错：`assert ('AK-74' not in 'function gw...')`（首个失败项为 `AK-74`，报错信息中对 `5bf3e03b` 的提示是组合断言展开）。

根因（A 类误伤，非布局硬编码）：
- R19.28 在 `gwSidBase` → `gwPartCard` 切片内新增数据字典 `GW_AK_REAR_SIGHT_IDS`，键是**物品 id**，值是中文物品名（如「AK-74 照门」「AK-74M 照门」）；
- 同区注释举例「AKM / AKMS / AK-74 / AKS-74」；
- 真正的枪械判定函数 `gwIsAkRearSightGun(g)` 是按 `mod_sight_rear` 槽位的 `allow` 物品 id 做结构签名，**不看枪名**。

修改（测试）：在扫描前剥离 JS 注释，并单独剔除该物品 id → 中文名数据字典（同时断言该字典存在），再检查无枪名/枪 id；另新增更严格检查：枪名/枪 id 不得作为 `==/===/!=/!==` 比较目标出现在分支条件中。

### 2.3 test_r19_11_round.py::test_hide_incompat_filters_without_touching_data

原始报错：`AssertionError: 切列逻辑保持（列宽不受影响）`。

根因：`refreshGunTable()` 中列计算由 `gunColumns()` 改为 `gunColumns(rows)`（同时仍调用 `state.gunTable.setColumns(...)`）。

修改（测试）：断言字符串由 `"gunColumns()"` 更新为 `"gunColumns("`；`setColumns`、不改 conflict、不清搜索等断言全部保留。

### 2.4 test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree

原始报错：`assert 'var rsCol = hasDovetail ? 6 : 8;' in eng`。

根因：R19.28 将照门锚点条件由 `hasDovetail` 扩展为 `akRearAnchor = hasDovetail || akRearFamily`（AK 照门系结构签名，不看枪名）；`akRearAnchor ? 6 : 8` 语义包含原燕尾槽分支。

修改（测试）：更新为 `var rsCol = akRearAnchor ? 6 : 8;`，并补充断言 `hasDovetail || akRearFamily` 仍在，防止燕尾槽分支被悄悄丢弃。其余 R19.13 锚点断言未改。

### 2.5 test_r6_gun_workbench.py::test_gun_workbench_business_logic

原始报错（Node 沙箱）：`ReferenceError: gunPushHistory is not defined`。

根因：`app.js` 已新增 `gunPushHistory()`（R20.5c 装配历史），`gunEquip`/`clearGunSlot` 调用它；测试 harness 的 `extractFn` 清单未同步。继续补抽取后又暴露 `gunModVal is not defined`，同属 harness 清单缺失（`gunRows` 新增 R20.4/20.5 显示字段）。

修改（测试 harness）：
- 增加抽取 `gunPushHistory`、`gunModVal`、`gunRE3`、`gunSizeText`、`traderMinLevel`；
- 对与 G4 断言无关的 R20 行情/满弹匣重量读取链，在沙箱内以 `gunMagFullWeight`/`fleaQuoteOf` 返回 `null` 的桩替代（G4 只校验 conflict/blocked/conflictText，断言原样保留）。
- 结果：Node 输出 `OK`，Python 断言 `>= 15` 通过。

## 3. 验证命令与结果

- 目标文件：`pytest tests/test_r19_1_round.py tests/test_r19_5_round.py tests/test_r19_11_round.py tests/test_r19_13_round.py tests/test_r6_gun_workbench.py -q` → `48 passed`。
- 全量：`pytest tests -q` → `1708 passed, 1 skipped in 106.56s`。

## 4. 未修 / 风险说明

- 无未修用例。
- 未改动任何生产逻辑；本轮只改测试 harness 的接口引用与抽取清单。
- 未触碰 `tools/installer.py`、`build/build.ps1`、`build/build_release.ps1`（另一会话负责）。
- 未 `git commit`。
