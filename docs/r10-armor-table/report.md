# EFT 配装工作台第十轮交付报告：防弹衣/弹挂装备表重构及交互补全

日期：2026-10-21　|　项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`　|　基线：r9（676 passed, 1 skipped）

本报告覆盖任务书第十一节要求的 9 项内容。原始验收数据见同目录 `verify-results.json`、`measure-6b43.json`、`other-category-cols.json` 与 13 张截图。

---

## 1. 实际修改文件清单

| 文件 | 改动性质 |
|---|---|
| `app.js` | 20 列列模型（`gearColumns` armor/rig 分支 L7352-7361）、插板/内衬分离（`renderPlateCell` L6893-6969）、九内衬列 `LINER_COL_ZONES`（L6573-6584）与 `linerBreakdown`（L6584-6617）、获取方式列 `srcColPrice`（L7329-7333）、左侧角标（`slotCell` L5903-5930 + `maxArmorClassOf` L5961-5977）、面部空槽剪影、防护区域仅图标列 `zoneIcoCol`、无内衬假 0 修复（L6614-6617） |
| `style.css` | `.lw-cl-badge` / `.lw-at-badge`（紫/绿角标）、`.lw-liner-mat`（内衬材质绿色高亮）、`.lw-plate-cell`（插板格三态）、`.lw-src-*`（获取方式徽记）、面部空槽剪影样式，全部限定在 `.loadout-workbench` 作用域内 |
| `tests/test_loadout_workbench.py` | T21/T22/T30 按新列模型更新（旧断言针对已被本轮重构的列集，按任务书要求改为验证新数据映射，未弱化） |
| `tests/test_r10_armor_table.py` | 新增：20 列列序、插板/内衬字段分离映射、6B43 回归（350/1867）、at 分类、右键卸板、角标计算 |

未改动：地图渲染、图标、路线、搜索、任务、枪械预设、`data/items.json`、后端 `tools/serve.py`。

## 2. 六项需求：根因与修复内容

### 需求 1：面部空槽剪影
- **根因**：face 槽 empty 态使用通用装备占位剪影，与面部装备形态不符。
- **修复**：face 槽 empty 占位改用本地已有的巴拉克拉法帽图标（`assets/icons-items/572b7f1624597762ae139822.webp`，灰化 + 半透明处理）。仅视觉占位，`data-state="empty"`、槽位状态/减益/冲突判断零改动，其他槽位占位不变。验收：`s11-regression-final.png`（clear 后 face 槽剪影生效、其余槽不变）。

### 需求 2：防护区域只显示图标
- **根因**：armor/rig 主表原 `zoneCol` 单元格内图标 + 文字混排。
- **修复**：armor/rig 20 列中防护区域改用 `zoneIcoCol`（仅渲染 22×22 本地部位图标），文字标签不再渲染；部位名称保留在 `title` 悬停中；`zones` 数据与图标映射本身未动。头盔等其他类别仍用原 `zoneCol` 文字列，未连带改变。验收：`s1-6b43-table-right.png`（无可见文字，悬停有名称）。

### 需求 3：价格并入获取方式列
- **根因**：价格列（`priceCol`）与来源列（`srcCol`）分离，跳蚤价格独立占一列。
- **修复**：armor/rig 主表与插板候选弹窗统一使用 `srcColPrice`（`renderSrcCell(cell,row,merged)`）：同一单元格内并列渲染跳蚤价 + flea 图标、商人直购价 + 头像 + 罗马等级、兑换配方物品×数量 + 头像 + 等级、藏身处制作图标；多渠道并列不互相覆盖；无渠道红 ✗。独立价格列在这两类表中删除，不存在同一价格两处显示。数据源（`p`/`trade`/`src`）未改动。
- **数据修正**：`src`（构建期判定）与 `trade`（逐笔数据）可能矛盾（6B43 `src=["none"]` 但存在 Prapor IV 兑换）。运行期用 `hasRealTrade`（L5006-5008）检查 `trade` 中是否有真实 flea/buy/barter 记录并修正 `srcKind`，避免漏显示渠道，也避免用卢布价冒充兑换。

### 需求 4：硬质插板与软质内衬彻底分离
- **根因**：r9 采用「无硬板位但有内衬时在插板格显示 V 块」的折中，插板格同时承载两种含义。
- **修复**：`renderPlateCell` 严格三态，判定只依据 `aps` 中真实硬板位定义（zone=`Front_plate`/`Back_plate`/`Left_side_plate`/`Right_side_plate` 且无 `fx`）：
  - `na`（装备无该硬板位）：整格空白，无框、无 V 块、无任何内衬信息；
  - `empty`（有槽位未安装）：显示「未安装」入口，点击打开插板弹窗（`openPlatePicker` L6715-6782），原有左键安装流程保留；
  - `on`（已安装）：显示插板等级 + 耐久 + 图标，右键卸除。
- **右键卸板**：`on` 态单元格 `contextmenu` → `clearGearSlot(st.slotId)`（L6957-6967），复用现有卸除与 `commitLoadoutChange` 链路，只清当前板位键（`rootKey + "/" + zone`），不动其他插板/内衬/本体；卸后刷新插板格、候选、重量、减益、费用并持久化。空槽与 `na` 格不拦截默认右键。预设恢复走 `applyLoadoutPreset`（`state.loadout` 完整替换，含 `armor/Front_plate` 等子槽键）→ `buildSlotTree` → `pruneOrphanSlots`，卸除后 reload/加载预设均不会复活已卸插板。

### 需求 5：armor/rig 专属 20 列表格
- **根因**：原 armor/rig 列集为通用护甲列（材质/毁损/有效耐久/文字防护区等），与任务书 20 列结构不一致。
- **修复**：`gearColumns` 新增 armor/rig 专属分支（L7352-7361），列序严格固定，不随单件装备数据变化；rig 原有 容量/槽位/护甲等级/基础耐久/材质/毁损/有效耐久/文字防护区 列退出主表（避免同字段两处显示），这些属性由 20 列中的插板/内衬/防护区域列承载。冲突列与独立价格列不在这 20 列中：冲突行仍整行标红、原因挂名称悬停。列宽固定管理（`applyColDefaults` + 列宽持久化），名称超长省略（`renderNameCellPlain`），文本长度变化不推移其他列。缺内衬显示「—」，无硬板位整格空白。其他类别列配置实测未变（见 `other-category-cols.json`：helmet 13 列 / backpack 11 列 / primary1 5 列）。

### 需求 6：左侧卡片最高防弹等级 + H/L 角标
- **根因**：左侧卡片无等级/材质可视化标记。
- **修复**：`slotCell` 在 `armor`/`rig` 且有已装备物品时追加两个角标（L5903-5930）：
  - 左下 `.lw-cl-badge`：`maxArmorClassOf`（L5961-5977）取本体 `cl` 与 `LW_HARD_PLATE_ZONES` 过滤出的已安装插板 `cl` 的最高值；换装备/装卸插板/加载预设即时重算；无有效等级不显示；
  - 右下 `.lw-at-badge`：按 `rec.at`（armorType）显示 H（紫底白字）/ L（绿底白字）；`at` 无可靠值（如 `None`）不显示，不伪造。
  - 仅 armor/rig 生效；背包/头盔/耳机/面罩/眼镜等不套用。卸除本体后角标随卡片消失。

## 3. 20 列表格列配置与字段映射

代码：`app.js` L7356-7361（列序）、L7208-7226（插板列）、L6573-6584（内衬 zone 表）、L7244（内衬汇总列）、L7329（获取方式列）。

| # | 列名 | 列 key | 数据来源（全部本地字段） | 默认宽 |
|---:|---|---|---|---|
| 1 | 图标 | `ico` | `itemIconUrl(id)`（本地 `ic`） | 44px |
| 2 | 名称 | `n` | `n`，超长省略（`renderNameCellPlain`） | minmax(200,1fr) |
| 3 | 移动/转身/人机 | `pen` | `z` → `speed/turn/ergo`（`renderPenCell`） | 128px |
| 4 | 前插板 | `plate_front` | `aps` 中 zone=`Front_plate`（无 fx → 硬板位）→ 三态 na/empty/on | 40px |
| 5 | 后插板 | `plate_back` | 同上 zone=`Back_plate` | 40px |
| 6 | 左插板 | `plate_left` | 同上 zone=`Left_side_plate` | 40px |
| 7 | 右插板 | `plate_right` | 同上 zone=`Right_side_plate` | 40px |
| 8 | 内衬材质及内衬总耐久 | `linerSum` | `aps` 中 `fx=1` 软甲：`mat`（材质名，绿高亮）+ Σ显示耐久 / Σ有效耐久 | 118px |
| 9 | 前内衬 | `liner_front` | fx 软甲 zone=`soft_armor_front` → `cl` + 显示耐久 | 64px |
| 10 | 后内衬 | `liner_back` | zone=`soft_armor_back` | 64px |
| 11 | 左内衬 | `liner_left` | zone=`soft_armor_left` | 64px |
| 12 | 右内衬 | `liner_right` | zone=`soft_armor_right` | 64px |
| 13 | 脖颈内衬 | `liner_collar` | zone=`collar` | 64px |
| 14 | 左肩内衬 | `liner_shoulder_l` | zone=`shoulder_l` | 64px |
| 15 | 右肩内衬 | `liner_shoulder_r` | zone=`shoulder_r` | 64px |
| 16 | 前裆内衬 | `liner_groin` | zone=`groin` | 64px |
| 17 | 后裆内衬 | `liner_groin_back` | zone=`groin_back` | 64px |
| 18 | 防护区域 | `zoneIco` | 防护区域图标映射（仅图标，title 保留部位名） | 60px |
| 19 | 重量 | `w` | `w`（两位小数） | 60px |
| 20 | 获取方式 | `srcGroup` | `p`（跳蚤价）+ `trade[]`（逐笔 buy/barter）+ `src`（构建期），`hasRealTrade` 修正 `srcKind` | 200px |

软甲 zone 匹配大小写无关（上游 `armorSlots` 大小写不统一，既有约定）；无法归位九列的内衬组件不会塞进插板列，计入汇总并按既有「待审核」口径处理。

## 4. 6B43 回归样本：350 / 1867 计算过程

本地记录：`545cdb794bdc2d3a198b456a`（6B43 屏障-Sh 防弹衣，数码丛林迷彩）。

**显示耐久总和 350**——8 个真实软甲内衬区域的显示耐久（`aps` 内 `fx=1` 组件的 `dur`）：

```
前 85 + 后 85 + 左 26 + 右 26 + 脖颈 32 + 左肩 28 + 右肩 28 + 前裆 40 = 350
```

**有效耐久 1867**——材质为芳纶（Aramid），毁损系数取 `audit.materials.Aramid.d = 0.1875`（items.json 构建期审计数据）：

```
350 ÷ 0.1875 = 1866.67 → 四舍五入 1867
```

每个内衬区域只计一次；插板耐久（独立硬板组件）不混入内衬耐久。后裆内衬（`groin_back`）本地数据不存在 → 显示「—」，与任务书回归预期一致。

6B43 行实测值（`measure-6b43.json` + `s1-6b43-full.png`）：移动/转身/人机 `-9.0/-5.5/-7.0`；四插板「未安装」入口（本地数据只有硬板位定义、无出厂默认插板——任务书规定「有槽位未安装→保留安装入口」，未硬编码四个插板）；内衬 `芳纶 350/1867`；九内衬列 `III 85 / III 85 / III 26 / III 26 / III 32 / III 28 / III 28 / III 40 / —`；防护区域仅图标；重量 `10.80`；获取方式 `Prapor Ⅳ + 2×地形调查地图 + 1×相位控制继电器`（兑换）。

## 5. H/L 分类规则与最高防弹等级计算规则

**H/L 分类依据**——`rec.at`（armorType）字段。该字段在构建期从上游真实分类提取入库，是本地数据中唯一可验证的重甲/轻甲依据（实测分布：Armor 类 Heavy 13 / Light 32 / None 4；ChestRig 类 Light 33 / Heavy 3 / None 46）。判定规则：
- `at === "Heavy"` → 紫底白字 `H`；`at === "Light"` → 绿底白字 `L`；
- `at` 为 `None`/缺失（如 5.11 Hexgrid 插板背心）→ 不显示角标，不按重量或名称猜测。

**最高防弹等级**——`maxArmorClassOf(id)`：
1. 读取当前装备本体 `cl`；
2. 遍历 `state.loadout` 中 `rootKey + "/" + zone`（zone ∈ `LW_HARD_PLATE_ZONES`）的已安装插板，读取其 `cl`；
3. 取最高值显示于左下角。只算当前装备与当前真实安装的插板；无有效等级不显示数字。

## 6. 获取方式数据来源及六种场景实测结果

数据来源（全部构建期打包进 `items.json`，运行期零网络）：
- 跳蚤市场：`p`（本地价格数据）；
- 商人直购：`trade[]` 中 `k="buy"` 记录（商人、解锁等级、价格）；
- 商人兑换：`trade[]` 中 `k="barter"` 记录（商人、等级、配方物品与数量）；
- 藏身处制作：`trade[]` 中 `k="craft"` 记录——**本地数据 0 条**（见第 9 节缺口）；
- 构建期 `src` 字段 + 运行期 `hasRealTrade` 修正矛盾。

六场景实测（`verify-results.json` scenarios）：

| 场景 | 样本 | 实测结果 |
|---|---|---|
| 跳蚤市场 | Hexgrid / AVS | 63,735 ₽ / 102,263 ₽ + flea 图标 ✓ |
| 商人直购 | Prapor 直售板 | 商人头像 + 罗马等级 + 价格 ✓ |
| 商人兑换 | 6B43 / Cult Locust | 头像 + Ⅳ + 实际配方物品×数量 ✓ |
| 藏身处制作 | 全库检索 | 0 条数据，无法展示（未伪造）✗ 缺口 |
| 多渠道并列 | PACA | 跳蚤 36,721 ₽ + Prapor Ⅰ 直购 36,506 ₽ + 兑换 3×遮脸半面巾，同格并列 ✓ |
| 无渠道 | Cult Termite / ESAPI（插板弹窗） | 红色 ✗ ✓ |

## 7. 测试结果

```
全量：681 passed, 1 skipped, 0 failed（基线 676 passed, 1 skipped；净增 5）
新增：tests/test_r10_armor_table.py（数据与列映射断言，非 CSS 类断言）
更新：test_loadout_workbench.py T21/T22/T30（适配新列模型，未删除/弱化）
```

过程中发现并修复 1 个真实缺陷：`linerBreakdown` 对完全无 fx 内衬的装备（Triton M43 弹挂、Hexgrid）返回 `total=0` 导致汇总列显示假 `0 / 0`——已修复为显示空位符「—」（app.js L6614-6617），修复后全量测试与浏览器双重确认，无回归。

## 8. 真实浏览器验收：步骤、截图与列尺寸

**环境**：`tools/serve.py`（http://127.0.0.1:8787/）+ Chrome 1920×909（CDP，r7shot.py），单标签页隔离（见第 9 节竞态说明）。

**操作步骤**：切换配装视图 → 清空装备（确认面部剪影）→ 依次装备 6B43 / PACA / PLATEminus V2 / Hexgrid / AVS / 6B5-16 / Triton → 安装与右键卸除插板 → 保存/加载预设 → reload 持久化验证 → 逐类别切换表头测量 → r9 右键卸除回归。

**20 列实测**（6B43 行，`measure-6b43.json`）：

- 表头 20 格、数据行 20 格，x 坐标：511 / 555 / 855 / 959 / 999 / 1039 / 1079 / 1119 / 1237 / 1301 / 1365 / 1429 / 1493 / 1557 / 1621 / 1685 / 1749 / 1813 / 1873 / 1933；
- 滚动宽度 1622px > 可视 1402px，宽表水平滚动、真实滑块可拖；
- 列宽实测：图标 44 / 名称 300 / 减益 104 / 四插板各 40 / 内衬汇总 118 / 九内衬各 64 / 防护 60 / 重量 60 / 获取方式 200。

**截图索引**（本目录 13 张，说明见 `verify-results.json`）：`s1-6b43-full.png`（角标 6/H + 面部剪影 + 20 列全览）、`s1-6b43-table-right.png`（最右：防护图标/10.80/Prapor Ⅳ 兑换）、`s2-6b43-plate-on.png`（AR500 已装）、`s2-6b43-plate-persist.png`（reload 持久化）、`s3-paca-high-plate-badge.png`、`s4-rig-20col.png`、`s5-plateminus-cl6-badge.png`（2/L→6/L）、`s6~s9`（rig 角标 4/L、3/H 紫、at=None 不显示）、`s10-preset-restore.png`（预设恢复 6/H）、`s11-regression-final.png`（回归终态）。

**关键交互实测**：插板安装（弹窗 21 候选）→ 右键卸单板（其他板/本体/内衬不受影响）→ reload 持久化 → 预设保存含 `armor/Front_plate` 键 → 清空后加载预设完整恢复；角标随装板升级/卸板回落即时重算；装甲弹挂互斥拦截红字提示正常；其他类别列配置无回归；r9 右键卸除与空槽右键不拦截均通过。

## 9. 尚未验证的项目与证据缺口

1. **藏身处制作渠道无数据**：`items.json` 中 craft 类来源 0 条，该渠道 UI 规则已实现但无真实样本可展示；未伪造数据。属上游构建期数据缺口，需数据管线补充。
2. **armor 主表无红叉样本**：本地所有防弹衣/弹挂至少有一个获取渠道；红 ✗ 场景在共用同一 `renderSrcCell` 的插板弹窗中验证（Cult Termite 等），armor 主表本体无法直接截图红叉。
3. **6B43 默认插板**：本地数据只有硬板位槽定义、无出厂默认插板，按「未安装」入口展示（符合任务书规则），任务书示例中的「默认前/后/左/右插板」无法在真实数据下呈现，未硬编码。
4. **双标签页广播竞态（既有架构行为）**：同源多标签页时旧标签页收到配置广播后会将自身 `state.loadout`（含旧子槽键）整体写回 localStorage，覆盖新标签页预设加载成果。经快照时间线 + 调用栈抓取定位；单标签页环境全链路稳定通过。该行为 r7-r9 已存在（`SELF_ECHO_GRACE=2500ms` 仅防护单页回声），不属于本轮六项需求范围；使用上避免多开本项目标签页。
5. **跨浏览器**：仅 Chrome（CDP 驱动）验证；Firefox/Edge 未做像素级验证。

---

**结论**：六项需求全部实现并通过数据级测试与真实浏览器验收；1 个过程缺陷（无内衬假 0）已修复；上述缺口均为数据侧或既有架构问题，已在交付物中如实记录。代码与测试结果保留，未推送远程、未覆盖正式发布版本。
