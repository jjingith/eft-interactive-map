host=HOMONAS user=MASTERJJ at=2026-11-04 14:41:51

# R63：飞行段 / 碎片化 / 技能加成 —— 数据盘点与落地台账

> 范围：只读外部数据；未下载安装、未改打包脚本、未 git 提交、未重建 dist/release。
> 本轮与 R65（后继层只乘 BT）合并实施，R65 单独记于 `docs/r65-blunt-carry-rewrite-ledger.md`。

---

## 0. 结论（先给判断）

| 项 | 能否落地 | 依据 | 关键覆盖率 |
|---|---|---|---|
| **飞行段（距离/速度衰减）** | ✅ 能做，但**只能是近似模型** | 输入字段齐（初速/弹道系数/质量/弹径），但**原文 `Shot` 飞行段没摘到**；现用弹药页同源「G1 阻力 + 50 m 归零」仿真 | `InitialSpeed` 218/218（100%）、`BallisticCoeficient` 218/218、`BulletMassGram` 218/218、`BulletDiameterMilimeters` 218/218；本地 `data/ammo.json` 同样 200/200 |
| **碎片化** | ✅ 能做，但只能做**最保守实现** | 概率字段齐；**「碎片数 → 附加伤害」官方映射未知**，倍率取社区经验 | `FragmentationChance` 218/218、`MinFragmentsCount`/`MaxFragmentsCount` 218/218（本地 195/200，缺 5 条 `6a…`） |
| **技能加成** | ✅ 能做，且可做成 **0–50 级可调项**（默认 0 级 = 无影响） | 仅「重型护甲 → 钝伤」这一条有真值：globals `BluntThroughputDamageHVestsReducePerLevel = 0.004`，原文 `ApplyDamage` 正是 `num2 *= 1 − 技能值`；其余技能无真值 | 1 条链路有真值；Sniper / Assault / Endurance / Strength **0 条** |

**一句话**：三段都能落地；飞行段数值可信度 = 近似、碎片化倍率 = 社区估计、技能 = 仅重甲钝伤一项为真值。三者全部做成**可选、默认不改变 R62 旧结果**。

---

## 1. 字段盘点（字段 → 覆盖率 → 来源）

### 1.1 `data/game-truth/ammo_ballistic.json`（218 条，从 `D:\GAMES\EFT` 实抽）

| 字段 | 覆盖 | 用途 |
|---|---|---|
| `InitialSpeed` | 218/218 | 飞行段初速 |
| `BallisticCoeficient` | 218/218 | 飞行段阻力 |
| `BulletMassGram` | 218/218 | 飞行段（质量） |
| `BulletDiameterMilimeters` | 218/218 | 飞行段（截面） |
| `PenetrationPower` | 218/218 | 终端穿透 |
| `PenetrationPowerDiviation` | 218/218 | 穿透浮动 σ（原文 `N(P, σ)`） |
| `Damage` | 218/218 | 终端伤害 |
| `ArmorDamage` | 218/218 | 甲伤 |
| `FragmentationChance` | 218/218 | 碎片化概率 |
| `RicochetChance` | 218/218 | 跳弹 |
| `MinFragmentsCount` / `MaxFragmentsCount` | 218/218 / 218/218 | 碎片数量区间 |
| `PenetrationChanceObstacle` | 218/218 | 障碍穿透（`ammo_props` 实际存在） |
| `MisfireChance` | **0/218** | 未抽取 → 未做 |
| `HeatFactor` | **0/218** | 未抽取 → 未做 |
| `DurabilityBurnModificator` | **0/218** | 未抽取 → 未做 |

### 1.2 `data/ammo.json`（本地 200 条，界面直接消费）

| 本地键 | 覆盖 | 对应官方字段 |
|---|---|---|
| `v0` | 200/200 | InitialSpeed |
| `bc` | 200/200 | BallisticCoeficient |
| `m` | 200/200 | BulletMassGram |
| `dia` | 200/200 | BulletDiameterMilimeters |
| `pen` / `dmg` / `ard` | 200/200 | PenetrationPower / Damage / ArmorDamage |
| `frag` / `ric` | 200/200 | FragmentationChance / RicochetChance |
| `pch` | 200/200 | PenetrationChanceObstacle |
| `penDev` | **0/200（本地无）** | 运行时从 game-truth join（UI「穿透偏差 σ」） |
| `fragMin` / `fragMax` | 195/200（5 条 `6a…` 缺） | Min/MaxFragmentsCount |

### 1.3 `data/items.json` 的 `aps`

- 结构：`aps` 是**插板槽位表**（`[{zone, plates[], z[]}]`），**不是弹药属性**。199 件装备有 `aps`。
- 护甲弹道属性在**对象顶层**：`bt` 334/344（97.1%）、`at`（Heavy/Light）337/344（98.0%）、`cl` 344/344、`dur` 344/344、`mat` 343/344。
- 与 game-truth 的弹药字段**不存在重叠**；不能从 `aps` 取飞行段或碎片化输入。

### 1.4 弹药界面此前展示 vs 本轮新增

| 字段 | R62 前 | R63 后 |
|---|---|---|
| 伤害/穿透/护甲伤害/初速/BC/质量/弹径/碎裂概率/跳弹/精准/后坐/堆叠/曳光/价格 | ✅ 已展示 | 保留 |
| 碎片数量（Min–Max） | ❌ 有数据未展示 | ✅ 新增 |
| 穿透偏差 σ | ❌ | ✅ 新增 |
| 障碍穿透概率 | ❌ | ✅ 新增 |

---

## 2. 上游查询（tarkov.dev 技能）

| 请求 | 结果（2026-11-04 复测，14:20 前后） |
|---|---|
| `POST https://api.tarkov.dev/graphql`（`{ __schema { queryType { name } } }`） | **HTTP 422 Unprocessable Entity**（GraphQL server unavailable） |
| `GET https://json.tarkov.dev/` | 404 |
| `GET https://json.tarkov.dev/skills.json` | 404 |
| `GET https://json.tarkov.dev/regular/` | 404 |

→ 上游未取得任何「技能等级 → 数值」表；技能真值改用本地 globals（同一客户端、同一构建）。

### 2.1 本地 `data/game-truth/globals_ballistic.json` → `SkillsSettings.HeavyVests`

| 参数 | 值 | 含义 | 可信度 |
|---|---|---|---|
| `BluntThroughputDamageHVestsReducePerLevel` | **0.004** | 每级钝伤 BT 削减；原文 `ApplyDamage`：`num2 *= 1f − heavyVestsDamageReduction`；按 0–50 级线性 → 满级 0.2 | **确定**（字段名 + 原文一致） |
| `MoveSpeedPenaltyReductionHVestsReducePerLevel` | 0.005 | 每级移速惩罚削减 | 名称可读；与伤害无关 → **未接入** |
| `RicochetChanceHVestsEliteLevel` | 0.05 | 满级（Elite）跳弹加成 | 触发条件未知 → **未知** |
| `RicochetChanceHVestsCurrentDurabilityThreshold` | 0.5 | 当前耐久阈值 | **未知** |
| `RicochetChanceHVestsMaxDurabilityThreshold` | 0.2 | 最大耐久阈值 | **未知** |
| `WearAmountRepairHVestsReducePerLevel` / `WearChanceRepairHVestsReduceEliteLevel` | 0.01 / 0.5 | 修理磨损相关 | 与战斗无关 → 未接入 |

**能否做成 UI 可调项**：能。`0–50 级 → BT × (1 − Lv×0.004)`，且**只对 `ArmorType = Heavy` 的层生效**（原文分支）。默认 0 级不影响旧结果。

---

## 3. 实现改动清单

### 3.1 `combat_sim.js`

| 行 | 改动 |
|---|---|
| 31–32 | `SOFT_LINER_PLATE_BLUNT_MUL=0.6` / `..._ENABLED=false`（R65，见另一台账） |
| 39 | `HV_REDUCE_PER_LEVEL=0.004`、`HV_MAX_LEVEL=50` |
| 328–331 | `heavyVestsReduce(layer, level)`：仅 `armorType==='Heavy'` 返回 `clamp(Lv,0,50)×0.004` |
| 447–470 | R65 后继层短路（只乘 BT，不判穿透/不算甲伤/不扣耐久） |
| 508 / 573 | 甲伤 `Math.max(1, durBase)`（浮点直减，无 Round） |
| 515 / 618 | 0.12 遗留 ×0.6 **默认停用**（开关） |
| 831 / ~930–940 / 974 / 980 | 碎片化计数与 `models` 输出（`flight/fragmentation/fragMinPen/fragExtraMul/heavyVestsLevel/...`） |

碎片化实现（最保守）：`击穿入体（dmgToPart>0）` → `fc = clamp(ammo.frag)`；`pen < 20 → fc = 0`；掷点命中 → `+0.5 × dmgToPart`（按 1 片）。

### 3.2 `app.js`

| 行 | 改动 |
|---|---|
| 20230 | `amFmtD(v)`：展示层 1 位小数（内部仍是浮点） |
| 21579–21581 | 详情新增「碎片数量 / 穿透偏差 σ / 障碍穿透概率」 |
| 21779 | `amSimState` 新增 `flightModel:'approx'、fragOn:false、hvLevel:0` |
| 22479–22487 | `amSimCfgFromUI` 读取距离模型 / 碎片化 / 重甲技能 |
| 22917–22955 | 新面板「可选模型（R63 · 默认不改变旧结果）」+ 来源说明 |
| 24247 | 汇总「碎片化触发 N 次」 |
| 24346 | 层详情 `afterBlock` 分支：「只乘自身 BT ×…（不判穿透 · 不算甲伤 · 不扣耐久）」 |

`amSimArmorLayers` 为每层补 `armorType`（插板 `pr.at`、内衬 `b.at||rec.at`、头盔 `helm.at`、内层 `inner.at`），供技能分支判断 Heavy。

### 3.3 测试

- 新增 `tests/test_r63_flight_frag_skills.py`（8 例）：距离单调性、无衰减平直、碎片化同种子可复现、`pen<20` 闸门、技能 Lv0 vs Lv50、轻甲不受影响、UI 静态断言。
- 新增 `tests/js/combat_sim_r63_flight_frag_skills.js`（Node 夹具）。
- 更新 `tests/test_r19_8*`、`tests/test_r62_golden.py`（R65 浮点耐久语义）。

---

## 4. 数值对照

### 4.1 距离衰减（M855A1，弹药页 0–500 m 同源计算）

| 距离 m | 近似 穿透 | 近似 伤害 | 近似 速度 | 无衰减 穿透/伤害/速度 | 伤害差 |
|---|---|---|---|---|---|
| 0 | 44.0 | 49.0 | 945 | 44.0 / 49.0 / 945 | 0.00 |
| 100 | 43.6 | 48.5 | 927 | 44.0 / 49.0 / 945 | −0.50 |
| 300 | 42.7 | 47.5 | 887 | 44.0 / 49.0 / 945 | −1.50 |
| 500 | 41.7 | 46.5 | 848 | 44.0 / 49.0 / 945 | −2.50 |

### 4.2 碎片化（M855A1，固定种子 42，20 发，无护甲）

| 模型 | 触发 | 前 8 发伤害 | 平均/发 |
|---|---|---|---|
| 关闭 | 0 | 49.0 ×8 | **49.00** |
| 开启（+0.5×） | 6 | 49.0 / 49.0 / 49.0 / 49.0 / 73.5 / 49.0 / 73.5 / 49.0 | **56.35** |

> 固定种子可复现：同种子逐发一致，换种子序列不同；`fragCount == Σ触发`。

### 4.3 技能（5 级 UHMWPE 插板 BT 0.155，ArmorType=Heavy，M855A1）

| 技能 Lv | hvReduce | 钝伤系数 BT×clamp | 入体 dmgToPart |
|---|---|---|---|
| 0 | 0 | 0.1257 | **6.1605** |
| 50 | 0.2 | 0.1006 | **4.9284** |

（轻甲层 `ArmorType=Light` 时 Lv50 与 Lv0 完全相同，有测试断言。）

---

## 5. 测试数字

```
python -m pytest tests -q
1736 passed, 1 skipped in 99.12s (0:01:39)   # 2026-11-04
```

新增/关键用例：`test_r63_flight_frag_skills.py` 8 passed；`test_r65_blunt_carry.py` 6 passed（两文件合计 14 passed in 0.55s）。

---

## 6. 截图（真实 Chrome，1440×900，DPR 1）

| 文件 | 内容 |
|---|---|
| `docs/r63-screenshots/01-ammo-detail-new-fields.png` | 弹药详情：碎片数量 2–3、穿透偏差 σ 1.375、障碍穿透概率 55% + 0–500 m 衰减表 |
| `docs/r63-screenshots/02-sim-optional-models.png` | 逐发模拟「可选模型（R63）」：距离模型下拉 / 碎片化复选 / 重甲技能 Lv（默认 approx / off / 0） |
| `docs/r63-screenshots/03-r63-models-compare.png` | 三合一对照：A 距离衰减（近似 vs 无衰减）、B 碎片化（关/开）、C 重甲技能 Lv0/50（页面内 `CS.simulate` 真实输出） |
| `docs/r63-screenshots/04-r65-blunt-carry-anchor.png` | R65 锚点：A 原文 / B 旧 ×0.6 / C 新+技能 Lv50，及逐层日志（见 R65 台账） |

---

## 7. 缺口清单（没做的原因 + 缺哪个字段）

1. **原文飞行段公式缺失** → 距离衰减标注为「近似模型（非官方）」。缺：`Shot` 飞行段积分/衰减实现原文（只有社区 G1 近似）。
2. **碎片数 → 附加伤害映射缺失** → 只做 `+0.5× / 1 片` 最保守实现，标 `estimated`。缺：官方碎片伤害合成规则。
3. **碎片化生效条件未知**（是否仅软组织 / 是否受护甲影响）→ 只在「击穿入体且 `dmgToPart>0`」时判定。
4. **本地 5 条弹药缺碎片数量** → UI 显示「—（模板缺失）」。缺：`MinFragmentsCount/MaxFragmentsCount`。
5. **其它技能无真值** → Sniper / Assault / Endurance / Strength 均未做；重甲也只接了「钝伤」一项。缺：技能等级表（上游 422/404 未取得）。
6. **重甲移速/跳弹/修理参数**有 globals 值但语义不完整 → 未接入，标「未知」。
7. **`MisfireChance / HeatFactor / DurabilityBurnModificator`** 0/218 → 未做。
8. **`items.json.aps`** 是插板槽位而非弹药属性 → 不能作为飞行段/碎片化输入。
