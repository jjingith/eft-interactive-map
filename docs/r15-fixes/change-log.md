# R15 变更记录（逐项：根因 → 修改 → 验证）

## A. 射速由枪械决定

**原问题**：射击参数里的 RPM 由用户手填，与实际所选枪械无关。

**真实根因**
1. 项目数据管线从未提取枪械射速：`data/gunslots.json` 只有槽位，`data/items.json` 的枪械记录未带 `fireRate`。
2. 因此 R14 的 UI 只能放一个 `data-sim="rpm"` 数字输入框（1–3000），引擎 `cfg.rpm` 直接取这个值。

**修改文件**
- `data/gun-rates.json`（新增，构建期数据）：163 把枪，`missingCount = 0`，每项 `{n, rpm, modes:[{k,n}]}`。
- `app.js`：`ensureSimGunRates()` / `simGunRate(id)` / `renderSimGun()`；`amSimCfgFromUI()` 改为从数据取 `s.rpm`（缺失即 `null`）；`amSimRun()` 在 `rpm` 非正数时阻止模拟并提示，不兜底、不回退手填；删除 RPM 输入框。
- `app.js`：射击模式下拉 `data-sim="gun-mode"` 仅在 `modes.length > 1` 时渲染。

**修复内容**
- 射速只读显示为 `800 rpm · Δt 75.0 ms`；切换枪械立即重算。
- `Δt = 60000 / rpm`。
- 数据缺失/加载失败时：下拉禁用、显示“射速数据加载失败”、模拟按钮被拦截（`rpm required (>0)`）。

**验证**
- 引擎：rpm 600 → 时刻 `[100,200]`；rpm 900 → `[67,133]`；rpm 150 → `[400,800]`；`rpm=0` 与缺失均抛 `rpm required (>0)`。
- 浏览器：`screenshots/r15-02-gun-rpm-readonly.png`（M4A1 800/75ms、AKS-74N 650/92.3ms、PKM 650 全自动）；`screenshots/r15-12-target-hp-1264x705.png` 中亦可见 `800 rpm · Δt 75.0 ms` 且该面板无 RPM 输入框。
- 断言：`#am-sim` 内数字输入框只有 `mag-count / armor-search / w-* / dist / seed / runs`。

**证据路径**：`docs/r15-fixes/screenshots/r15-02-gun-rpm-readonly.png`、`tests/test_r15_fixes.py::test_a_*`

---

## B. 目标血量样式对齐参考图

**原问题**：血量是 7 个横向 chip，不是参考图的“斜角铭牌 + 绿色血条 + 总量”。

**真实根因**
1. R14 的 `amSimHpFigure()` 只输出 `部位名 + 数字` 的横向行。
2. 本轮第一版改成铭牌 + 血条后，`clip-path` 被加在**整块 plate** 上，导致血条右端也被斜切（参考图中血条是矩形）。
3. 底部总量原先左对齐、星号用主题绿、数字用绿色。

**修改文件**
- `app.js` `amSimHpFigure()`：拆成 `.am-sim-hpnameplate`（只有铭牌）与 `.am-sim-hpbar`（矩形血条），血条宽度按 `hp/max` 实时计算。
- `style.css` `.am-workbench .am-sim-hp*`：铭牌 `clip-path: polygon(0 0, calc(100% - 13px) 0, 100% 100%, 0 100%)`；血条 `clip-path: none`、`width: calc(100% - 5px)`（左缩 5px）、高 17px、绿色边框；总量 `justify-content: center`，星号 `#cfe32e`、数字 `#f4f7f4`。

**修复内容**：对照 `ui图标\目标血量 样式.png`（1097×1374）逐项还原——梯形铭牌右端斜切、矩形血条、白字居中 `当前/上限`、底部居中 `✳ 总量 /上限`、7 部位三列骨架排布、血量条随模拟结果实时变化。

**未对齐项（如实记录）**
- 参考图有骷髅人体剪影。项目无该素材的分发授权，且硬约束禁止自绘人形剪影，故未复制；面板使用同色系径向暗底。
- 参考图“头部”铭牌相对“胸腔”右偏约一列；本实现为 3 列对称网格（头部与胸腔同在中列），因为无剪影时右偏会失去视觉锚点。
- 参考图底部还有一个蓝色 `▲14.86` 附加标注（非血量字段），未实现。

**验证**
- 7 块铭牌 `nameplateClip` 均为梯形、`barClip` 均为 `none`、铭牌与血条同宽（差值 <1px）。
- 单发命中胸腔后：`胸腔 35/85`、血条宽度 42/100、总量 `390/440`。
- 多窗口：1904×814 与 1264×705 均无横向溢出（`simOverflowX=0`、`pageOverflowX=0`）。

**证据路径**：`screenshots/r15-13-target-hp-before-leftalign.png`（改前）、`r15-10-target-hp-pmc-closeup.png`（改后满血）、`r15-11-target-hp-damaged.png`（受伤）、`r15-09-target-hp-refined-1904.png`（整页）、`r15-12-target-hp-1264x705.png`（窄窗口）。

---

## C. 目标护甲配置与配装工作台统一

**原问题**：模拟器有一套独立手填的“护甲层”表单（名称/类型/等级/耐久/材质），与配装工作台的装备数据、插板兼容规则完全不同源。

**真实根因**
1. R14 为了跑通引擎，直接在 UI 里手填 `armorLayers`，字段是另一套。
2. 引擎也没接入配装工作台的装备模型（`state.items.byId`、`rec.aps`）。

**修改文件**
- `app.js` `renderSimArmor()` / `renderSimHelmet()` / `amSimArmorLayers()` / `amSimGearCatalog(kind, allowed)`。
- 删除手填护甲层表单（不再有“层预设”入口）。

**修复内容**
- 护甲选择复用配装工作台的装备记录：`rec.cl`（等级）、`rec.dur`（耐久）、`rec.mat`（材质）、`rec.z`（防护区域）、`rec.bt`（钝伤系数）、`rec.slot`（helmet/armor/rig）。
- 插板槽来自 `rec.aps` 中 `fx=0` 的插板位，候选**严格取自 `socket.plates`**（不再按物品类型/名称猜测）。
- 软内衬来自 `rec.aps` 中 `fx=1` 的固定软甲，按区域显示为独立 chip（耐久各自独立）。
- 选中装备/插板/内衬后，`amSimArmorLayers()` 生成引擎层：`{name, kind, zones, cls, durMax, dur, material, bluntThroughput}`，插板带自己的 `mat/bt`，缺失时回落父装备。

**验证**
- Killa 的 6B13 M 护甲：安装前/后插板；前插板候选 4 项、后插板候选 3 项（均来自该护甲的 `socket.plates`）；6 块软内衬 chip（前/后 48、左右 10、脖颈 18、前裆 20）；头盔 Maska-1SCh。
- 模拟日志中出现 `plate` 与 `liner` 层，且耐久分别扣减。

**证据路径**：`screenshots/r15-04-barrier-plate-log.png`、`tests/test_r15_fixes.py::test_e_*`

---

## D. Boss 装备池限制

**原问题**：只有一个泛化的“Boss 750 HP”目标，任何全局装备都能装到 Boss 身上。

**真实根因**：项目内不存在 Boss 血量与装备数据；目标预设只有 `combat-targets.json` 的血量条目。

**修改文件**
- `data/bosses.json`（新增）：4 个 Boss（Killa 890 / Reshala 752 / Shturman 812 / Tagilla 1220），含逐部位血量、装备列表、`platesPolicy`、护卫（Reshala/Shturman 有独立血量）。
- `app.js` `ensureSimBosses()` / `amSimTargetPool(s)` / `amSimGearCatalog(kind, allowed)` / `renderSimPoolNote()`。
- `renderSimArmor()` / `renderSimHelmet()`：选择不在池内时清空 `s.armorId`/`s.armorPlates`/`s.helmetId` 并回写 UI。

**修复内容**
- 目标类型：PMC / Scav / Boss / 护卫；选 Boss 后再选具体 Boss。
- 装备候选 = 全局装备 ∩ 该目标装备池（护甲/头盔/面罩）。
- `platesPolicy`：`armor-socket` 走插板槽；`none`（Shturman）不提供插板。
- 切换目标/ Boss 时清理不属于新池的选择。
- 血量、血池、装备池按目标隔离；PMC/Scav 的示例集合 `enforced:false`（不构成强制限制，UI 有说明）。

**验证**
- Killa 池：护甲 1 项、头盔 1 项；Tagilla 池：护甲 2 项、头盔 2 项。
- 在 Killa 选好护甲后切到 Tagilla：旧护甲被清空（`stillInPool:false`），不会带进新 Boss。
- 逐发日志中的装备名/耐久与所选 Boss 装备一致。

**证据路径**：`screenshots/r15-03-boss-pool-tagilla.png`、`tests/test_r15_fixes.py::test_d_*`

---

## E. 多层护甲重新核验

**原问题**：被硬插板挡住后仍按“已穿透”结算完整伤害；软内衬几乎不参与；层与层之间没有真实状态传递。

**真实根因**
1. `resolveShot()` 在循环里对每层都用同一份初始 `st.dmg/st.pen` 判定，只在穿透时做 `pen-1 / dmg×0.9` 记账。
2. 被挡住时直接按该层钝伤结算，**看不到后方还有软内衬**。
3. 层的顺序完全取决于 UI 配置顺序，没有 plate→liner 的物理顺序。

**修改文件**：`combat_sim.js`（`resolveShot`、`sortArmorLayers`、`hasSoftBacking`、`createBarriers`、日志字段）。

**修复内容**
- 单发状态 `st` 在障碍层、护甲层之间真实传递，被挡即终止。
- `KIND_RANK = {plate:0, helmet:1, liner:2}` 固定顺序。
- 被硬板挡住时若后方有覆盖该部位的 liner → 钝伤 ×0.8。
- 每层独立 `durMax/dur`，每发读取当前值。
- 每层日志新增 `penIn/dmgIn/penOut/dmgOut/blocked/blunt/softBacking/degraded/durBefore/durAfter`。

**验证**：见 `armor-layer-research.md` §4 的确定性场景表（情况 A/B/C/D、材质、等级、复现）。

**证据路径**：`screenshots/r15-04-barrier-plate-log.png`、`tests/js/combat_sim_r15_test.js`、`tests/test_r15_fixes.py::test_e_*`

---

## F. 障碍物位置与穿透机制

**原问题**：障碍物选择藏在护甲层表单之后，且复用“护甲等级 × 穿透力”的思维。

**真实根因**：R14 把障碍物当作护甲层的一个子项处理，UI 顺序与数据结构都没有独立。

**修改文件**
- `data/barriers.json`（新增，9 条，全部 `estimated`）。
- `app.js` `ensureSimBarriers()` / `renderSimBarriers()` / `simBarrierById()`；`amSimBuildEngineCfg()` 把 `s.barrierIds` 映射为引擎 `barriers`。
- `combat_sim.js` `createBarriers()` 与障碍判定分支。

**修复内容**
- 面板顺序固定为：枪械 → 弹匣 → **障碍物** → 目标类型 → 目标护甲 → 命中分布。
- 障碍物与护甲分开：概率 = `pch × penChanceMul`，通过后 `dmg×dmgKeep`、`pen×penKeep`，不扣护甲耐久。
- 支持多层按顺序叠加；未通过即终止本次命中（不进入护甲、不伤人体）。
- 逐层 barrier 日志（概率、掷点、通过与否、前后穿透/伤害、是否跳弹）。
- 修复下拉框一直显示“正在加载障碍物…”：原判断 `if (!sel.options.length)` 被占位 option 卡住，改为按 `options.length !== arr.length` 重建并保留当前值。

**验证**：`fBase/fOne/fTwo/fOrderAB/fOrderBA/fBlocked/fThenArmor/fRepro` 场景全部通过；浏览器中木板→铁皮与铁皮→木板的首层概率分别为 60% 与 36%，结果不同。

**证据路径**：`screenshots/r15-01-panel-order.png`、`r15-08-barrier-multilayer-order.png`、`tests/test_r15_fixes.py::test_f_*`

---

## 附带修复

| 问题 | 根因 | 修复 |
|---|---|---|
| 障碍物下拉永远是“正在加载障碍物…” | `renderSimBarriers()` 用 `options.length` 判断是否已填充，占位 option 使长度恒 ≥1 | 按数量差重建，并保留 `keepVal` |
| 死亡样式与存活类名冲突 | `.am-sim-hpdead` 同时用于血池行与整图 | 拆为 `.am-sim-hpfigdead` |
| 手动护甲层 UI 与配装装备双轨 | 两套数据同时存在 | 删除手填层，统一走配装装备 |
