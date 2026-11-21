host=HOMONAS user=MASTERJJ at=2026-11-04 13:36:18 +08:00

# R62 弹道 / 护甲口径重写台账（按 0.13.x 客户端反编译原文）

**权威依据**：`D:\personal\trae\02-塔科夫\逆向参考\r61-eft-decompiled-ballistics.md`
（`CreateShot` / `GetAmmoPenetrationPower` / `SetPenetrationStatus` / `ApplyDamage` / `Deflects` 方法体原文），
真值数据 `D:\personal\trae\02-塔科夫\逆向参考\r58b-game-truth-data.md` + `data/game-truth/`。

**范围**：只改计算口径、前端接入、测试与「关于」文案。
未改打包脚本、未重建 `dist` / `release`、未 git 提交、未改 `data/armor-bt.json` / `data/armor-ricochet.json` 的数值。

---

## 0. 结论：现在能否「和游戏同一套公式」

| 环节 | 与原文一致 | 说明 |
|---|---|---|
| 甲伤 `DamageToArmor` | ✅ 结构一致 | `P × AD × clamp(P / Resistance, 0.5–0.9 / 0.6–1.1) × Destructibility`，`Resistance = 10×AC`，`Max(1, ·)` |
| 减伤 / 穿透伤害 | ✅ 一致 | `clamp(P / (FactorA + 12), 0.6, 1)`；`FactorA = (121 − 5000/(45+2·dur%)) × AC × 0.1`（= 原文 `× Resistance × 0.01`，因 `Resistance = 10×AC`） |
| 未穿钝伤 | ✅ 一致 | `BT × clamp(1 − 0.03·(FactorA − P), 0.2, 1) × Damage` |
| 穿透概率 | ✅ 一致 | `p ≤ a−15 → 0`；`a−15 < p < a → 0.4(a−p−15)²%`；`p ≥ a → 100 + p/(0.9a−p)`（`app.js` 的 `amDesmosChance` 名字叫 Desmos，实际就是这三段原文） |
| 跳弹 | ✅ 一致 | 头盔/插板各自 `RicochetVals`；`DeflectedBy` 后 `Damage/ArmorDamage/Penetration ÷2`，再走挡下分支，仍扣耐久并交付半值钝伤 |
| 穿透浮动 | ⚠️ 分布一致、流不可逐位复现 | 原文 `GetNormalDistributedRandomFloat(seed, P, PenetrationPowerDiviation)`；本实现用 Box–Muller + mulberry32 固定种子，σ 取官方字段 |
| `Shot` 飞行段（速度/穿透距离衰减） | ❌ 缺失 | r61 只摘到 `CreateShot` 调用处，飞行/`Shot` 迭代原文未取到；距离衰减仍用弹药页模型 |
| 碎片化 `TryShatter` | ❌ 未建模 | 原文只出现调用，方法体未取到；`FragmentationChance` 未参与结算 |
| 跳弹后的二次弹道 | ❌ 未建模 | 本实现跳弹即终止并交付半值钝伤（与 `ApplyDamage` 的账一致，但后续飞行不算） |
| 技能 / 重型护甲减伤 / 体力燃烧 | ❌ 未建模 | 原文 `heavyVestsDamageReduction`、`Buff.DamageReduction`、`StaminaBurnRate` 需要角色状态，工具不模拟角色 |

**误差量级**：甲伤是整数（原文 `Mathf.Max(1,…,)` 后 `ApplyDurabilityDamage(num)`），同输入本工具与原文最多差 1 点耐久；
人体伤害在击穿分支与原文浮点级一致（`Damage × clamp(P/(FactorA+12),0.6,1)`）。
**单发跳弹掷点不可复现**——原文用 Unity 随机流（`UnityEngine.Random.Range(0,512)` 做种子，再 `GetRandomFloat(seed)`），
本工具只能对齐**概率曲线**，视频锚点验证的是概率区间与期望值，不是逐发一模一样。

---

## 1. 改动清单（文件 / 行 / 前后）

### 1.1 `combat_sim.js`（核心）

| 位置 | 改前 | 改后 |
|---|---|---|
| L20–30 | `CS.ARMOR_DMG_COEFF_MODE = 'site'`（默认 `(P/AC)*10`，常见输入恒顶 1.1/0.9）；`DUR_PROTECTION_CAP = 1.2` 参与击穿/挡下两条分支 | 默认 `'decomp'`；`ARMOR_CLASS_PROTECTION = 10`；`DUR_PROTECTION_CAP = 1.2` **仅 `video` 旧口径**使用 |
| L41–45 | 无 | 新增 `CS.armorClassResistance(cls)`：`cls ≤ 0 → 1`，否则 `cls × 10`（原文 `ArmorClass.Resistance`） |
| L50–62 | `armorDamageCoeff` 只有 site/video 两种 | 新增 `decomp`：`pen / armorClassResistance(cls)`，击穿 `clamp(0.5, 0.9)`、挡下 `clamp(0.6, 1.1)`；site/video 保留为对照 |
| L100 | `ceramic: 0.55` | `ceramic: 0.6`（`globals_ballistic.json` 的 `ArmorMaterials.Destructibility`） |
| L119–123 | 无 | 新增 `CS.normalRandom(rng, mean, sd)`（Box–Muller，`u1 = 1 − rng()` 避免 `log(0)`） |
| L167 | `createArmorLayers` 不接收跳弹参数 | 透传 `ricochet: l.ricochet || null` |
| L434–488 | 仅 `L.kind === 'helmet'` 跳弹；跳弹后「扣 1 点耐久、伤害归零、钝伤不结算」 | `helmet` 与 `plate` 都参与；`halfPen = pen/2`、`halfDmg = dmg/2`、`halfArdPct = ard/200`；`coeff = armorDamageCoeff(halfPen, cls, false)`；`durDmg = max(1, round(halfPen × ard/200 × coeff × Destructibility))`；钝伤 `= halfDmg × BT × scale`；记 `stoppedBy='ricochet'`、`penAfter/dmgAfter` 后立即 `return` |
| L802–831 | 穿透浮动：`cfg.penJitter` 时 `rng()*2 − 1`（连续均匀 ±1） | `normal`：`penDev` 优先 `ammo.penDev`（`game-truth`）→ `cfg.penDeviation`（`cfg`）→ `1`（`fallback-sigma1` 降级）；`penRoll = normalRandom(rng, 0, penDev)`；`'uniform'` 只在显式 `penJitter === 'uniform'` 时启用（`legacy-uniform`） |
| L840–845 | 日志只有 `penUsed` | 新增 `penBase / penRoll / penJitterMode / penDev / penDevSource` |

### 1.2 `app.js`（前端接入）

| 位置 | 改动 |
|---|---|
| L20232–20281 | 新增 `AMMO_BALLISTIC_URL = "data/game-truth/ammo_ballistic.json"`、`ensureAmmoBallistic()`；`ensureAmmo()` 完成后按 id 把 `penDev` 挂到每行弹药；加载失败一律降级 σ=1（引擎标 `fallback-sigma1`） |
| L21019 | `AM_ARMOR_DMG_MODE = "decomp"`（旧 `site` / `video` 保留，不默认启用） |
| L22287 | 插板层注入 `ricochet: armorRicochetOf(pid)`（此前插板层没有跳弹字段，原文 `Deflects` 对插板同样生效） |
| L22321 | 头盔层保持 `ricochet: armorRicochetOf(s.helmetId)` |
| L22502 | `armorDamageMode: AM_ARMOR_DMG_MODE` 传入引擎 |
| L24191–24248 | 逐发提示：显示 `N(σ=…, 来源)` → 本发穿透值；跳弹行显示角度 / 概率 / 掷点 / `÷2` 后耐久与钝伤；结果列新增「跳弹（甲/板）」 |
| L24309 | 收束文案改为「跳弹：子弹偏飞，半值伤害按钝伤结算」 |

### 1.3 `index.html`（「关于」面板）

L170–188 新增「弹道与护甲公式（R62）」段：原文公式、跳弹 ÷2、`N(P, PenetrationPowerDiviation)`、
**与 B 站《护甲机制全解析》视频口径的差异**（该视频线性耐久模型 + 1.2 上限，与反编译不符）、
多层钝伤 H1 与第三方 H4 不一致的说明、以及 `Shot` 飞行段缺失 / 碎片化未覆盖等限制。

### 1.4 `tools/r58b_game_truth.py`（提取器扩展）

- L130–150：新增 `AMMO_PROPS`（`Damage / ArmorDamage / PenetrationPower / PenetrationPowerDiviation / …`），
  命中含 `PenetrationPowerDiviation` 的对象时写入 `ammo_props`。
- L248–251 / L332 / L351–355：收集 `ammo_likes` 并输出 `data/game-truth/ammo_ballistic.json`
  （`schema = eftmap.game-truth.ammo-ballistic/1`，`extracted_at = 2026-11-04 12:57:38`，218 条模板）。

**覆盖率**：本地 `data/ammo.json` 200 条，命中 195 条；缺 5 条（均为 `6a…` 开头的本地新增 ID：
`6a60f36fb3d057447a095aee`、`6a42662fcb506840dd053827`、`6a426637ddc63098d100ae67`、
`6a07208057b2695f9d001e63`、`6a42661705016139300b2085`）。这 5 条走 σ=1 降级并在逐发日志标 `fallback-sigma1`。

---

## 2. 公式前后对照

```
甲伤（耐久伤害）
改前（site，默认）: base = P × AD% × clamp((P / AC) × 10, 0.6–1.1 | 0.5–0.9) × Destructibility
   → 常见输入 (P/AC)×10 ≥ 1.1，恒顶上限，甲伤与穿透力实际脱钩
改后（decomp）    : base = P × AD% × clamp(P / (10 × AC), 0.6–1.1 | 0.5–0.9) × Destructibility
   → 原文 ArmorComponent.ApplyDamage L140 / L146

跳弹
改前: helmet 专属；成立后「耐久 −1、伤害归零、钝伤不结算」
改后: helmet + plate 各自 RicochetVals；成立后 Damage / ArmorDamage / Penetration ÷2
      （原文 L122–127），再走挡下分支 L140–141：扣耐久 + 半值钝伤交人体

穿透浮动
改前: P + rng()*2 − 1（连续均匀 ±1）
改后: P + N(0, PenetrationPowerDiviation)（原文 CreateShot → GetAmmoPenetrationPower L72）
```

**删除/停用**（原文均不存在）：`击穿 ×0.7`、`1.2 封顶`（仅 `video` 旧口径保留）、`66%–75% 随机区间`。
`tests/test_r19_8_armor_formula.py::test_new_formula_constants_and_no_legacy_scale` 断言这些常量已不存在。

---

## 3. 锚点验算

数据：`data/ammo.json`（纸面 P/D/AD%）+ `data/items.json`（等级/耐久/BT/材质）+ `data/game-truth/globals_ballistic.json`（Destructibility）。

### 3.1 M855A1 × 6B23-2（4 级钢插板，满耐久 40）

P44 / D49 / AD47%；钢 `Destructibility = 0.525`；`FactorA = (121 − 5000/245) × 4 × 0.1 = 40.237`

- 甲伤系数：`44 / 40 = 1.1` → 击穿侧 `clamp(0.5, 0.9) = 0.9`
  → `44 × 0.47 × 0.9 × 0.525 = 9.7665` → **10 点**，耐久 `40 → 30`
- 减伤：`clamp(44 / (40.237 + 12), 0.6, 1) = 0.8423` → 人体 `49 × 0.8423 = 41.27`
- 旧口径（site）：系数恒 0.9（同值），差别只在「插板是否参与跳弹」（见 3.4）

### 3.2 M995 × SAPI（5 级陶瓷插板，满耐久 50）

P53 / D42 / AD52%；陶瓷 0.6；`FactorA = (121 − 20.408) × 5 × 0.1 = 50.296`

- 甲伤系数：`53 / 50 = 1.06` → `0.9` → `53 × 0.52 × 0.9 × 0.6 = 14.882` → **15 点**，耐久 `50 → 35`
- 减伤：`clamp(53 / 62.296, 0.6, 1) = 0.8508` → 人体 `42 × 0.8508 = 35.73`
- 旧口径：系数也是 0.9（同值），但陶瓷常量是 0.55 → `13.64 → 14 点`。**本锚点的差来自材质真值，不是比值。**

### 3.3 视频 8 → 1（.308 ME LOKT + Altyn 5 级面罩 10% 耐久 + 2 级面罩）

P24 / D96 / AD55%；第一层 `bt = 7.92%`、材质系数 0.375；第二层 `bt = 9.90%`；H1 口径

- 第一层钝伤 `96 × 0.0792 × scale1 = 7.6032` → UI `toFixed(0)` 显示 **8**
- 第一层甲伤：系数 `24 / 50 = 0.48 → clamp 下限 0.6` → `24 × 0.55 × 0.6 × 0.375 = 2.97` → **3 点**，耐久 `5 → 2`
- 第二层（H1）：`7.6032 × 0.0990 × scale2 = 0.7527` → 显示 **1**
- 若换站点 H4：第二层 `6.0586`（显示 6），**复现不了 8→1** —— 因此保留 H1，并在「关于」写明与第三方计算器不一致。

### 3.4 浏览器同输入新旧对照（真实 Chrome，见 §5 截图）

| 场景 | 旧口径（site，头盔专属跳弹） | 新口径（decomp，甲/板跳弹） |
|---|---|---|
| M855A1 × ESAPI 6 级（陶瓷 0.6） | 甲 −11 / 人 29.8（系数 0.900） | 甲 −9 / 人 29.8（系数 0.7333） |
| M995 × SAPI 5 级 | 甲 −15 / 人 35.7 | 甲 −15 / 人 35.7（两口径此处同值，锚点 B） |
| M855A1 × 6B23-2 4 级 @85°（seed 6） | 穿透 / 人 41.274 / 甲 −10 | **跳弹** / 人 1.997 / 甲 −2，耐久 40 → 38（概率 0.55，掷 0.5257） |
| 穿透浮动 | 均匀 ±1 | `N(44, 1.375)` seed7 → 44.195（来源 `game-truth`） |

---

## 4. 测试新旧数字

`python -m pytest tests -q` → **1722 passed, 1 skipped**（97.06 s，2026-11-04 13:34 实跑）。

### 4.1 失效 fixture 的「旧值 → 新值」（全部重算，未放宽断言）

旧值用**旧默认口径**（site 系数 + 陶瓷 0.55）复跑同一 fixture 得到（临时 harness 只覆盖这两个默认值，不改代码）。

| fixture（`tests/test_r19_8_armor_formula.py`） | 旧值 | 新值 | 为什么变 |
|---|---|---|---|
| M80 × KITECO 6 级未穿 | 甲 −11（45→34），系数 1.1 | 甲 −7（45→38），系数 0.7167 | 分母从 `(P/AC)*10` 改成 `P/(10×AC)`，不再恒顶 1.1 |
| M80 × KITECO 击穿 | 甲 −9（45→36），系数 0.9 | 甲 −7（45→38），系数 0.7167 | 击穿侧同理，不再恒顶 0.9 |
| 同上人体伤害 | 48（`80 × 0.6` 下限） | 48（不变） | 减伤公式未改 |
| M995 × SAPI 击穿 | 甲 −14（50→36） | 甲 −15（50→35） | 陶瓷 `0.55 → 0.6`（globals 真值）；系数两口径都是 0.9 |
| BT × SAPI 未穿 | 甲 −10（50→40），系数 1.1，钝伤 9.738 | 甲 −7（50→43），系数 0.74，钝伤 9.74（不变） | 比值真实生效；钝伤只依赖 FactorA，不受甲伤系数影响 |
| M80 × KITECO 半耐久 | 甲 −11（22.5→11.5），钝伤 15.24 | 甲 −7（22.5→15.5），钝伤 15.24（不变） | 原文甲伤系数与耐久无关；钝伤随耐久变化 |
| M80 连打 3 发 | 甲 11/11/11，耐久 45→34→23→12，钝伤 9.97/11.88/15.05 | 甲 7/7/7，耐久 45→38→31→24，钝伤 9.97/11.08/12.57 | 每发扣耐久从 11 降到 7，FactorA 下降更慢，钝伤序列随之变缓 |

`tests/test_r17_fixes.py`：`penVsUnpen` 量纲改为 **击穿 0.9 / 挡下 1.04**（旧 site 两分支都顶到 1.1/0.9），
`userCase` 系数 0.6、量纲用例 0.8、`low` 0.6；`test_r19_8_ricochet.py` 跳弹由「−1 点耐久、钝伤 0」改为
**甲 −2（40→38）、钝伤 4.438**。

### 4.2 新增用例

| 文件 | 覆盖 |
|---|---|
| `tests/js/combat_sim_r62_golden.js` + `tests/test_r62_golden.py` | (a) P44 对 2–6 级：decomp `1.1/1.1/1.1/0.88/0.7333` vs site 恒 `1.1`；(d1) M855A1×6B23-2；(d2) M995×SAPI；(d3) 视频 8→1（H1） |
| `tests/test_r19_8_ricochet.py` | (b) 头盔与插板都断言 `durDmg = 2`、`dur 40→38`、`dmgToPart 4.438`、`stoppedBy='ricochet'` |
| `tests/test_r19_8b_rules.py::test_penetration_jitter_is_normal_and_seeded` | (c) `normal` + 固定种子可复现、不同种子不同；`penDev = 1.375` 且 `penDevSource = game-truth`；无 σ 时 `fallback-sigma1`；`uniform` 只在显式开关 |
| `tests/js/combat_sim_r19_8b_test.js` | 新增 `jitterDev`（σ1.375）/ `jitterUniform`；coeffCases 增加 decomp |

---

## 5. 浏览器截图（本机 Chrome，真实页面）

页面：`http://127.0.0.1:8790/`（`python tools/serve.py --port 8790`，本地直连，`/` 与
`data/game-truth/ammo_ballistic.json` 均 200）。截图由 Chrome DevTools MCP 控制的独立 Chrome 实例渲染，
再经 `PrintWindow` 落盘（窗口 1400×1000，`devicePixelRatio = 0.667`）。

| 文件 | 内容 |
|---|---|
| `docs/r62-screenshots/r62-old-vs-new.png` | 同输入新旧对照面板：3 个场景 + 穿透浮动采样；即 §3.4 表格 |
| `docs/r62-screenshots/r62-about.png` | 「关于」面板 R62 公式段全文（跳弹 ÷2、N(P,σ)、与 B 站视频差异、H1 与 H4、限制清单） |

截图里可读到的关键数字：`甲 −11 → −9`（系数 `0.900 → 0.733`）、`甲 −10 穿透 → 跳弹`（`人 41.3 → 2.00`）、
`N(σ=1.375) 44 → 44.195`。

---

## 6. 与原文核对的两项专项

1. **`Resistance × 0.01` 的位置**：原文 `num4 = ArmorClass.Resistance`（未乘 0.01），
   `num5 = (121 − 5000/(45+2·dur%)) × num4 × 0.01`。本实现 `armorFactorA = (…) × AC × 0.1`，
   在 `Resistance = 10×AC` 时可逐位等价（本次真值确认 0–6 级均为 `10×AC`，0 级为 1）。
   **偏差仅存在于 0 级护甲**（原文 `0.01×1`、本实现 `0.1×0 = 0`）——本地没有 0 级护甲物品，属未触发分支。
2. **耐久分母口径**：原文 `Repairable.Durability / Repairable.TemplateDurability * 100`（**出厂满耐久**），
   本实现 `dur / durMax`，`durMax` 取 `data/items.json` 的出厂耐久，一致。
3. **B1（挡下分支不削减 P/D）核对**：原文 L138–154 的 `if (BlockedBy == Id || DeflectedBy == Id)` 分支
   只做 `Damage *= bt × clamp(1 − 0.03(R − P))`，**不乘 `num6`**；只有 else（击穿）分支才
   `Damage *= num6` 且 `PenetrationPower *= num6`。→ **上一轮 B1 的口径与原文一致，未改动**。

---

## 7. 遗留限制

1. `Shot` 飞行段（速度衰减 / 穿透距离衰减）原文未取到：`CreateShot` 之后的对象迭代在 `_EC26` 里，
   r61 未摘录；本工具继续用弹药页的距离衰减模型（`estimated`）。
2. 碎片化（`TryShatter` / `FragmentationChance` / `MinFragmentsCount`）未建模。
3. 跳弹后的二次弹道（偏飞方向、二次碰撞）未建模；跳弹即终止，只交付半值钝伤。
4. 技能 / 重型护甲减伤（`heavyVestsDamageReduction`）、`Buff.DamageReduction`、`StaminaBurnRate` 未建模。
5. 随机流不同：Unity `Random` + `GetNormalDistributedRandomFloat` 不可逐位复现，只能固定种子复现**本工具**的浮动。
6. 甲伤取整：原文 `ApplyDurabilityDamage(num)` 的方法体未取到，本实现用 `Math.round`；与原文可能差 1 点耐久。
7. 5 条本地新增弹药在 0.13.x 资源里查不到 σ，按 σ=1 降级（日志标 `fallback-sigma1`）。
8. 多层钝伤保留 H1（视频锚点），与站点/部分第三方计算器（H4）不一致，已在「关于」写明。
9. `data/armor-ricochet.json` 里 6 条取值差异按用户要求本轮不动。

---

## 8. 复现命令

```powershell
# 全量测试
python -m pytest tests -q

# 只跑 R62 相关
python -m pytest tests/test_r62_golden.py tests/test_r19_8_armor_formula.py `
                 tests/test_r19_8_ricochet.py tests/test_r19_8b_rules.py -q

# 重新提取弹药真值（需要本机 resources.assets）
python tools/r58b_game_truth.py extract

# 本地页面
python tools/serve.py --port 8790
```
