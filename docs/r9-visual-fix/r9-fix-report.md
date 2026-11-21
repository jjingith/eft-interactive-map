# EFT 配装工作台：视觉与装备属性专项修复 交付报告

轮次：第九轮（GLM-5.3-Flash 执行版）
日期：2026-10-21
项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`
参考图目录：`ui图标`；参考网站：https://db4tarkov.com/preset

---

## 1. 修改文件清单

| 文件 | 修改内容 |
|---|---|
| `app.js` | ① `LW_DEBUFF_KEYS` 增加 `backpack: 1`（背包局部减益）；② 名称列与板位格渲染配合（`renderPlateCell` na 态整格空白、内衬 V 块）；③ 回声防护：`SELF_ECHO_GRACE`（初版 500ms，验收中定位到 ConfigWatcher 延迟广播后扩为 **2500ms**）+ `lastOwnPrefPostAt` 时间戳 + `applyUiPrefs` loadout 分支守卫 |
| `style.css` | 面罩/耳机/眼镜三卡统一尺寸变量 `--lw-headcard-w/h`（65×63，仅 `.loadout-workbench` 作用域）；头盔格 grid-area 布局；`.lw-node-group-side` 附件组；名称列 `width:0;min-width:100%` + span ellipsis；`.lw-plate-liner` 内衬 V 块样式 |
| `tests/test_loadout_workbench.py` | T21 改为无硬板位护甲 na+内衬断言；T22 四处列集更新（armor/helmet/glasses/plate 去除 bt、对齐新列序）；`LW_DEBUFF_KEYS` 断言加 backpack；标签断言改「损毁系数」+ bt 残留检查；harness 增加 `armorLiner` 提取；新增 `test_app_js_plate_cell_na_blank_and_liner_block`、`test_app_js_loadout_echo_self_guard` |

未改动：地图渲染/图标/路线/定位/搜索/任务/设置、枪械预设（`gunslots.json` 未触碰）、人物预设存储结构、`tools/serve.py`（回声根因在前端防护窗口，未改服务端）。

## 2. 五问题根因与解决方式

### 问题1：三卡尺寸不一致 + 头盔附件穿模
- **根因**：面罩/耳机/眼镜三类各自硬编码卡片尺寸；头盔格 grid 区域未给附件组留出独立列，附件组与头盔主体发生网格重叠。
- **解决**：统一为共享变量 `--lw-headcard-w: calc(65/63 * var(--lw-u))`（以耳机卡 65×63 为标准）；头盔移至 grid-area `1/2/4/6`，附件组（`.lw-node-group-side`）`flex: 0 0 auto` 独立成列。
- **实测**（`r9-acceptance-measurements.json`）：三卡 `getBoundingClientRect()` 均 **65×63**；Altyn 头盔 `.lw-cell` 78×78 @(230,125)，两附件槽 40×40 @(142/185,144)，重叠计算 `overlapping=[]`（附件位于头盔左侧，零重叠）。
- **右键卸附件**：`prevented=true`，面罩槽 on→empty，**盔罩与头盔 rect 前后不变**（只更新附件槽）。
- 截图：`B-helmet-no-attachment.png` / `B-helmet-attached.png` / `B-helmet-after-unequip.png`（无附件/多附件/卸除后三种状态）。

### 问题2：背包局部减益不显示
- **根因**：两层。① 渲染层 `LW_DEBUFF_KEYS` 白名单缺 `backpack`；② 验收压测中发现的**回声竞态**（见第 3 节）。
- **解决**：白名单加 backpack，复用与防弹衣/弹挂同一套 `slotLocalPen` 机制；回声竞态见第 3 节。
- **实测**：Paratus `-3 / -1 / -5` → RUSH 100 `-5 / -3 / -7`（图标、减益、hint 同步刷新）；右键卸除后 icon/debuff 清空（`prevented=true`）；20 轮压测 20/20 通过。
- 截图：`D-backpack-swap.png` / `D-backpack-unequipped.png`。

### 问题3：长名称撑开表格
- **根因**：名称单元格无宽度约束（`min-width:auto` 默认由内容撑开），整表列被最长行推移。
- **解决**：名称 cell `width:0; min-width:100%; display:flex`，内部 span `overflow:hidden; text-overflow:ellipsis; white-space:nowrap`，完整名称保留在 `title` 悬停浮层。
- **实测**（`C_long_name_korea`）：样本「FORT Redut-M（堡垒-M）防弹衣（韩国林地迷彩）」span `scrollWidth=271 > clientWidth=250` → **clipped=true + ellipsis**；短名称（6B43 数码丛林迷彩）`208≤208` 不裁剪；**长/短名称切换前后表头与行 17 列的 x/w 完全一致（diff={}）**。
- 截图：`C-long-name.png` / `C-short-name.png`。

### 问题4：假插板框 + 内衬错渲染成防护区域
- **根因**：板位列渲染未按当前装备的真实 `armorSlots` zone 生成——无硬板位的装备仍画四格框；内衬（Soft_armor_* 的 fx 固定组件）被映射进插板位。
- **解决**：`armorSocket` 只匹配小写归一后的四种硬板位 zone（front/back/left/right side plate）；`armorLiner` 只匹配 soft zone 且 `fx=1`；`plateSlotState` 的 state 只由硬板位决定，na 且无内衬 → 整格空白（`cell.innerHTML=""`），na 有内衬 → 只画 `.lw-plate-liner` V 块；更换/卸除/加载预设后按当前装备重新生成。
- **实测**（本轮与 `r9rig`/`r9rigplate` 脚本）：ANA M2（4 硬+4 软）四列 empty+V 内衬、可弹窗装板（21 件合法板，装 AR500 后变 on）；TV-110（仅前后硬）左右两列整格空白；6B5-16（无硬位）四列无假框（前后仅 V 块 III T / II T）；PACA（4 软）四列 na+liner。左侧面板无板位/内衬卡片。
- 截图：`E-paca-soft-only.png` / `E-armor-rig-conflict.png`（6B43+ANA M2 双向互斥红行）。

### 问题5：钝击穿透挤掉损毁系数
- **根因**：类别列集把 `bt`（钝击穿透）列加入 armor/helmet/glasses 等，替换了原有 `destr` 列。
- **解决**：移除 `btCol`，恢复 `destrCol`（label「损毁系数」，`fmtNum(d,2)`），列位在装甲材质之后。
- **字段来源证据**：`data/items.json` → `audit.materials[mat].d`（上游 armorMaterials：Aramid 0.1875、Combined 0.375、Titan 0.4125、UHMWPE 0.3375、Ceramic 0.6、ArmoredSteel 0.525、Aluminium 0.45、Glass 0.6）；`app.js materialDestructibility`（L4387-4392）查表；`gearRows` destr（L4986）。**实测核对**：ANA M2（Aramid）表内显示 `0.19` = 0.1875 两位舍入 ✓。未伪造任何数值；空值显示「—」。

## 3. 验收中发现并修复的新问题：换装偶发回滚（回声竞态）

- **现象**：压测中约 1/10 概率，第二次换装（Paratus→RUSH）后界面回滚显示旧装备，但 hint 仍显示「已装上 RUSH 100」（equip 已成功）。
- **根因链**：equipItem → persistLoadout → POST `api/prefs`（含 loadout 快照）→ serve.py 除直发回声外，**ConfigWatcher 轮询线程（1s 周期）发现配置文件 mtime 变化后再次广播同样内容**（serve.py `poll_once` L371-386），比直发回声晚最多约 1.05s；前端 `applyUiPrefs` 对 loadout「值不同就覆盖」，初版 500ms 自回声窗口（SELF_ECHO_GRACE）罩不住延迟广播 → 过期回声把新装备回滚。
- **修复**：`SELF_ECHO_GRACE` 500→**2500ms**（覆盖 2 个轮询周期+余量），app.js L856-862；其余键本有值比对守卫，窗口放宽同样受益。不改服务端。
- **验证**：修复前 1/10 失败（现场证据：hint=RUSH、界面=Paratus）；修复后 **20/20 通过**（Paratus -3/-1/-5 ↔ RUSH -5/-3/-7）。

## 4. 测试结果

- 全量：`pytest tests\` → **676 passed, 1 skipped, 0 failed**（40.31s）。
- 基线对照：上一轮 674 passed / 1 skipped；本轮 +2 = 新增 `test_app_js_plate_cell_na_blank_and_liner_block`、`test_app_js_loadout_echo_self_guard`，原有测试无删除、无跳过、无放宽。
- grace 修改后重跑确认无回归。

## 5. 原站对照（db4tarkov.com/preset）

原站 Preset 页为 **Flutter Web（canvas 渲染）**，DOM 无可交互元素，使用 CDP 坐标点击驱动完成部分对照（截图 `ref-site-*.png`）：

| 对照点 | 原站表现 | 本地 | 结论 |
|---|---|---|---|
| 卡片下方减益 | Headwear/Backpack 卡下方显示 `-1 / -4 / -3`、`-3 / -1 / -5` | 同格式；Paratus 本地 `-3 / -1 / -5` **与原站逐位一致** | 一致 ✓ |
| 表格减益列 | 名称后第一列 `0 / -2 / -3` 格式 | 一致 | 一致 ✓ |
| 长名称 | 原站长名称行（Altyn 变体）列位稳定 | 本地 17 列 x/w 切换不变 | 方向一致 ✓ |
| 头盔附件 | 原站装头盔后左侧**不显示**附件槽（经 Mod Attach 页签/变体行处理） | 本地按 `ui图标` 参考图将附件槽置于头盔左侧 | **差异**，按任务书优先级以本地参考图为准 |
| 损毁系数 | 原站表格无独立损毁系数列（材质+耐久合并如 "Combined 78"） | 本地保留独立列，依据本地历史实现与任务书 | **差异**，以本地为准 |
| 插板/内衬 | 原站防弹衣流程未能完成（见未验证项） | 按 armorSlots 真实 zone | 原站未验证 |

## 6. 未验证项（如实列出）

1. **原站 Mod Attach 页签与防弹衣/插板对照未完成**：Flutter canvas 的坐标点击多次未命中页签/列表关闭按钮，防弹衣装备流程未走通——问题4 的原站侧行为未对照，本地验收完全基于本地数据与参考图。
2. **F 段预设「保存」（覆盖）按钮**未单独验证，采用「另存为→清空→加载」完整流程替代（`r9-acceptance-measurements-bdf.json` F_preset_flow：保存提示、rows=3、加载恢复 RUSH -5/-3/-7 全通过）。
3. **跨浏览器**（Firefox/Edge）与触屏/缩放非 100% 场景未验证；本轮截图统一 1920×909、deviceScaleFactor=1。
4. `ref-site-2/3/preset.png` 三张为同一空装状态（交互未生效时的存档），仅作过程记录。
5. v1 首跑出现过一次 `p1=null` 异常（未复现，判定为脚本时序），后续全部运行未再出现。

## 7. 交付物索引

- 截图与测量：`docs/r9-visual-fix/`（26 个文件）
  - `r9-acceptance-measurements.json`（A 三卡 65×63、B 头盔 78×78、C 长短名称列稳定+省略、D 换装、F 预设弹窗）
  - `r9-acceptance-measurements-bdf.json`（B 附件装/卸全流程、D 右键卸除 prevented=true、F 另存为→清空→加载恢复）
- 测试基线：676 passed / 1 skipped（`pytest tests\` 全量实跑输出）
