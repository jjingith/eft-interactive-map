host=HOMONAS user=MASTERJJ at=2026-11-04 14:41:51

# R65：前层挡下后，后继层只乘 BT —— 重写台账

> 依据：`D:\personal\trae\02-塔科夫\逆向参考\r65-blunt-softarmor-formula.md`（0.13.x 反编译原文）。
> 未重建 dist/release、未 git 提交、未改数据文件；与 R63 同批实施，测试一次跑完。

---

## 0. 结论

三件事全部改完：

1. **后继层短路**：前层 `blocked/deflected` 后，本层只 `Damage *= BT × (1 − 重型护甲技能)`，**不判穿透、不算甲伤、不扣耐久**（对应 `Player.cs` L27873–27929）。
2. **0.12 遗留 ×0.6**：代码结构保留，**默认停用**（`CS.SOFT_LINER_PLATE_BLUNT_ENABLED = false`），启用会与后继层 BT 形成双重扣减。
3. **甲伤浮点**：`Math.max(1, durBase)`（去掉 `Math.round`），取整只在展示层（`amFmtD`）。

锚点回验（伤害 162.3 / 穿透 36.7 / 5 级 UHMWPE BT 0.155 / 3 级芳纶内衬 BT 0.18）：

| 口径 | 插板钝伤 | 内衬后入体 | 与用户实测 |
|---|---|---|---|
| **A 原文 0.13.x（新，×0.6 停用）** | **14.8957** | **2.6812** | ≈ **15.02 / 2.70** ✅ |
| B 旧 ×0.6（历史对照） | 8.9374 | 1.6087 | 0.12 口径，仅对照 |
| C 新 + 重型护甲技能 Lv50 | 11.9166 | 2.1450 | 技能项 = 0.2 削减 |
| 旧 H1（已删除） | 15.02 | **15.02（直传）** | ❌ 与原文相反 |

> 说明：`0.093 = 0.155 × 0.6` 是旧口径的等效 BT，**不是**原始模板值；因此「15.02 × 0.6 = 9.01」「15.02 / 0.6 = 25.03」两种反推都不成立。原文口径下插板自己只乘一次 BT（0.155），后继内衬再乘自己的 BT（0.18）。

---

## 1. 原文依据（逐条）

| 行为 | 原文位置 | 实现 |
|---|---|---|
| 前层被挡后，后继层**只** `Damage *= BluntThroughput`（Heavy 再 ×(1−技能)），不调用 `ApplyDamage` | `EFT/Player.cs` L27873–27929 `ProceedDamageThroughArmor` | `combat_sim.js` **443–470** |
| `BlockedBy` 非空后，后续层**跳过** `SetPenetrationStatus`（内衬的 96.2% 穿透概率在原文里不存在） | `Player.SetShotStatus` L28082–28096 | 短路分支 `chance=null, roll=null`（451–455） |
| 钝伤 = `Damage × BT × clamp(1 − 0.03×(FactorA − P), 0.2, 1)`，Heavy 时 BT 再 ×(1−技能) | `ArmorComponent.ApplyDamage` L290–330 | 613–625（既有实现，保留） |
| 甲伤 `Durability -= armorDamage`，**无 Round**，仅 `Mathf.Max(1f, ·)` | `ApplyDurabilityDamage` L349–358 | **508 / 573**（`Math.max(1, durBase)`） |
| 0.12 的 `BluntDamageReduceFromSoftArmorMod` 在 0.13 **0 引用** | 交叉版本 dump | **31–32 / 515–517 / 618–623**（默认 false） |

---

## 2. 改动行号（`combat_sim.js`）

| 行 | 内容 |
|---|---|
| 31–32 | `SOFT_LINER_PLATE_BLUNT_MUL=0.6`、`SOFT_LINER_PLATE_BLUNT_ENABLED=false` + 0.12 遗留说明 |
| 39–40 | `HV_REDUCE_PER_LEVEL=0.004`、`HV_MAX_LEVEL=50` |
| 328–332 | `heavyVestsReduce(layer, level)`：仅 Heavy → `clamp(Lv×0.004, 0, 1)` |
| **443–470** | **后继层短路**（`afterBlock`、`chance=null/roll=null`、`durDmg=0`、`durAfter=L.dur`、`bluntFactor=BT×(1−hv)`、`continue`） |
| 507–508 | 跳弹分支甲伤 `Math.max(1, durBase)` |
| 515–517 | 跳弹分支 ×0.6 由 `ENABLED` 控制（默认关） |
| 571–573 | 挡下分支甲伤 `Math.max(1, durBase)` |
| 577–580 | 内衬缩放保持浮点（`linerScaled < 0.01 ? 0`） |
| 607–608 | 穿透分支不再携带 `bluntCarry`（旧「穿透层 bluntFactor=1」已删） |
| 609–641 | 挡下分支：**只有第一层**产出钝伤（`bluntIn=null`），`bluntCarry=bluntOut` 后 `continue` |
| 645–653 | 最终入体：只取钝伤链最后一层 `log.dmgToPart += bluntCarry` |

`app.js` 展示层：`amFmtD`（20230）对所有耐久/钝伤做 1 位小数显示；层详情 `afterBlock` 分支（24346）显示「前层已挡下：只乘自身 BT ×…（不判穿透 · 不算甲伤 · 不扣耐久）」。

---

## 3. 数值对照（同一场景）

场景：伤害 162.3、穿透 36.7、甲伤 52%、固定命中胸部、`penChanceFn → 0`（恒被挡下）、种子 7、单发。
护甲栈：5 级 UHMWPE 插板（40/40，BT 0.155，Heavy）→ 3 级芳纶内衬（40/40，BT 0.18，Light）。

| 层 | 口径 A（新） | 口径 B（×0.6） | 口径 C（A + 技能 Lv50） |
|---|---|---|---|
| 插板 钝伤 | 14.8957 | 8.9374 | 11.9166 |
| 插板 甲伤（浮点） | 4.7275839 | 4.7275839 | 4.7275839 |
| 插板 耐久 after | 35.2724161 | 35.2724161 | 35.2724161 |
| 内衬 判定 | `afterBlock`，`chance=null`、`roll=null` | 同左 | 同左 |
| 内衬 钝伤 in | 14.8957 | 8.9374 | 11.9166 |
| 内衬 系数 | 0.18 | 0.18 | 0.18 |
| **最终入体 dmgToPart** | **2.6812** | **1.6087** | **2.1450** |

对照用户实测：**15.02 → 14.8957（−0.8%）**、**2.70 → 2.6812（−0.7%）**，差异来自 BT 取模板近似值 0.155。

### 3.1 「96.2% 穿透概率」消失

R65 前：内衬层仍走穿透判定 → `chance ≈ 96.15%`（`FactorA=30.178, P=36.7` 走第三段），掷点穿透后 `bluntFactor=1`，15.02 原样进人体。
R65 后：内衬层 `afterBlock=true`、`chance=null`、`roll=null`、`durDmg=0`、`durAfter=40`，日志文案为「前层已挡下：只乘自身 BT ×0.18」。UI/日志里不再出现 96.2%。

### 3.2 视频锚点 8→1（必须仍复现）

`.308 ME LOKT + Altyn 5 级面罩 10% 耐久 + 2 级面罩`：

- 第一层钝伤 `7.6032`（界面显示 **8**）✅
- 第二层钝伤 `0.7527`（界面显示 **1**）✅
- 第一层甲伤 `2.97`（float，展示 3）✅

（`tests/test_r62_golden.py::test_d3_video_anchor_8_to_1_keeps_h1`）

---

## 4. 测试

```
python -m pytest tests -q
1736 passed, 1 skipped in 99.12s (0:01:39)

python -m pytest tests/test_r65_blunt_carry.py tests/test_r63_flight_frag_skills.py -q
14 passed in 0.55s
```

R65 新增 6 例：

| 用例 | 断言 |
|---|---|
| 默认 ×0.6 停用 | 源码 `SOFT_LINER_PLATE_BLUNT_ENABLED = false` |
| 锚点 A | 插板 14.8957、内衬 2.6812（≈15.02 / 2.70） |
| 后继层语义 | `afterBlock=true`、`chance/roll is None`、`durDmg=0`、`durAfter=40` |
| 旧口径 B | 8.9374 / 1.6087 |
| 甲伤浮点 | 4.7275839 非整数；三发累减一致 |
| 无内衬 | 插板 14.8957 全量入体 |

同批更新的既有用例（R65 语义）：`test_r62_golden.py`（M855A1 9.7713 / M995 14.8824、视频锚点 2.97）、`test_r19_8_armor_formula.py`（三发浮点耐久与 FactorA 漂移）、`test_r19_8_ricochet.py`、`test_r19_8b_rules.py`（后继层不再有 chance）、`test_r15_fixes.py`（软内衬不再额外 ×0.6）。

---

## 5. 截图

| 文件 | 内容 |
|---|---|
| `docs/r63-screenshots/04-r65-blunt-carry-anchor.png` | 同一场景三口径（A/B/C）+ 逐层日志（内衬 `afterBlock`、`chance=null`、甲伤 0、耐久 40） |
| `docs/r63-screenshots/03-r63-models-compare.png` | 技能 Lv0 vs Lv50（Heavy 插板）差异 |

（1440×900，真实 Chrome + 真实 `CS.simulate`；面板为页面内渲染，未改打包产物。）

---

## 6. 已知限制 / 缺口

1. **重型护甲技能**只接入了「钝伤 BT 削减」一项（`0.004/级`）；移速、跳弹、修理相关 globals 参数语义不全 → 标「未知」未接。
2. **技能等级曲线**：字段名是 per level，本项目按 0–50 线性；游戏是否有递减/精英额外加成未知。
3. **BT 精确值**：锚点用 0.155（5 级 UHMWPE 常用值）与 0.18（芳纶兜底），与用户实测 15.02/2.70 有 <1% 偏差；如需完全对齐，应取该件装备模板的 `BluntThroughput` 实测值。
4. **旧 H1（内衬被穿透 → bluntFactor=1）**已按原文删除，无法再用开关复现；只能通过 ×0.6 开关对照 0.12 口径。
