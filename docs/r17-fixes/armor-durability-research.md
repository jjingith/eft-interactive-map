# R17-A：护甲耐久损毁——研究与修正

## 1. 资料来源（实际访问情况）

| 来源 | 访问方式 | 结果 | 用途 |
|---|---|---|---|
| fandom《Ballistics》 | MediaWiki API（经代理 127.0.0.1:7896，2026-10-23） | **成功**，缓存 `build-cache/boss-wiki/Ballistics.json` | 定性规则 verified |
| 官方论坛《【尼基塔星物理学】塔科夫护甲测试报告》 | WebSearch 摘要（论坛帖子正文未逐页抓取） | 拿到两个实测标定点 | 经验式系数标定（estimated） |
| eft-ammo.vercel.app | 经代理 curl | 200（Next.js SPA，正文未内联公式） | 线索，未取得公式 |
| tarkovaftermidnight.wordpress.com | 经代理 curl | 404（该路径失效） | 未取得 |
| reddit r/EFT lkkdps | 经代理 curl | 403（Cloudflare） | 未取得 |
| api.tarkov.dev/graphql | 经代理 POST | `GraphQL server unavailable` | 未使用 |

## 2. 可核实的机制（fandom Ballistics，verified 定性）

> 「护甲受到的耐久损毁由**弹药穿透力**与**护甲等级**决定，乘以**弹药甲伤百分比**与**护甲材质毁损系数百分比**。
> 单发最低 1 点（含霰弹每颗弹丸）。穿透弹比未穿透弹低约 10–15%。」

材质毁损系数表（wiki，verified）：aramid 0.1875 / uhmwpe 0.3375 / combined 0.375 / titan 0.4125 /
aluminium 0.45 / armorSteel 0.525 / ceramic 0.6 / glass 0.6。

**这份资料只有定性关系，没有给出 f(穿深, 等级) 的显式公式。**

## 3. 社区实测标定（estimated，但有两个数值点）

官方论坛测试帖给出两个实测点（穿透情形）：

| 弹药 | 甲伤(0-100) | 穿深 | 护甲 | 实测损甲 |
|---|---|---|---|---|
| FMJ SX | 41 | 30 | 3 级装甲钢 | 7.7 |
| M80 | 66 | 41 | 4 级钛 | 13.6 |

拟合：`损甲 ≈ 甲伤 × 材质毁损系数 × 穿深 × 0.009`（帖内自带材质系数）。
换算到 wiki 毁损系数口径（帖内系数 ≈ wiki × 4/3）后：**`损甲 ≈ 甲伤 × D_wiki × 穿深 × 0.012`**。

回算验证：
- 41 × 0.525 × 30 × 0.012 = **7.75**（实测 7.7，误差 < 0.7%）
- 66 × 0.4125 × 41 × 0.012 = **13.37**（实测 13.6，误差 < 2%）

两点无法区分「护甲等级」是否独立进入公式（两个点的等级影响可能被耐久与穿透概率吸收）——
**这是本公式最大的不确定点**，按任务要求标为 `estimated`。

## 4. 新实现（combat_sim.js）

> **R19.8 更新**：下面这段 0.012 标定式已被视频（下）5:07 的公式替换，现行实现见 §7。
> 保留本节仅作历史记录，避免旧报告与现行代码混淆。

```
ratio    = pen / (cls × 10)                      // 只用于未穿情形的系数
durBase  = ard × D_material × pen × 0.012        // ard 是 0–100 的百分比值
durMul   = 穿透 ? 0.85                            // wiki：穿透弹低 10–15%
         : clamp(0.55 + 0.55 × min(1, ratio), 0.55, 1.10)
              // 未穿：穿深贴近等级时反而更高（论坛实测「高 1–3 点」）；差距越大越低（论坛定性）
durDmg   = max(1, round(durBase × durMul))        // 单发下限 1（wiki verified）
```

实现细节：
- 日志每层新增 `durBase` / `durMul` / `durConfidence='estimated'`，可审计；
- 0 耐久行为**保留**（无防护、全穿透），但显式标注 `zeroDurConfidence='estimated'`
  与说明文字——不能未经证据确认就把「绝对无防护」当成官方规则；
- 多层护甲：每层独立按上式扣耐久，`dmgToArmor = Σ 各层`（测试锁定不重复计）。

## 5. 修改前后对比（用户案例 + 代表弹药）

| 案例 | 旧实现每发损甲 | 新实现每发损甲 | 依据 |
|---|---|---|---|
| **5.56 HP（甲伤22 穿7）vs 5 级陶瓷 50 耐久（未穿）** | **7**（8 发拆完） | **1**（50 发） | base=1.11 → 下限 1 |
| M855A1 类（甲伤47 穿44）vs 5 级陶瓷（未穿） | 47×0.6×0.88≈24.8 | 15（base=14.89×1.034） | 经验式 |
| 同弹药穿透情形 | 旧 ×0.85 ≈ 21 | 7.34×0.85 → **7** | wiki 10–15% |
| 4 弹丸霰弹（ard5 穿2）| 每颗 1 | 每颗 1，共 4 | 下限 1 不变 |

回归测试：`tests/test_r17_fixes.py`（用户案例固化为 `test_user_case_hp_vs_class5_ceramic`）。

## 6. 仍未确认（如实记录）

1. **等级是否独立进入公式**：两个实测点无法判定；若官方以后给出显式公式，只需替换 `durBase` 一行。
2. **0.012 系数的版本适用性**：标定帖未注明游戏版本；当前版本是否有改动未核实。
3. **未穿情形的「贴近等级更高 / 差距大更低」**：只有论坛定性描述，线性插值（0.55→1.10）是实现选择。
4. **0 耐久护甲的真实防护**：保留社区口径并标注 estimated。

## 7. R19.8：按视频公式替换（现行实现）

**来源**：B 站 MAJ_Kelvin《逃离塔科夫-护甲机制全解析（下）》，2026-10-30 发布；
关键画面见 `docs/r19.8-armor-audit/`：
- `down-0334-penetration-vs-protection.jpg`：6 级板 vs 43 穿 M80 → 43÷60 ≈ 71.6%
- `down-0413-protection-drops-with-durability.jpg`：「防护能力会随着耐久损失而下降」
- `down-0507-durability-example.jpg`：45×0.84×0.6×(43÷50) ≈ 20.4，再 ×0.7（穿透补偿）= 14.28
- `user-frame-durability-formula.png`：用户提供的公式画面

**现行公式**：

```
防护能力 = max(1, 等级 × 10 × 当前耐久比例)      // 视频只给满耐久示例，比例项为推定
durBase  = 穿深 × 甲伤% × 材质耐久系数 × (穿深 ÷ 防护能力)
durMul   = 穿透 ? 0.7 : 1                        // 视频 5:07「穿透补偿」
durDmg   = min(剩余耐久, max(1, round(durBase × durMul)))
```

与 R17 旧式的差别：删除了 0.012 标定常数与 0.55–1.10 的未穿插值；等级不再只以
`pen/(cls×10)` 的夹持形式出现，而是通过 `(穿深 ÷ 防护能力)` 直接降低高级甲的甲伤；
穿透折减从 0.85 改为视频标注的 0.7；防护能力随当前耐久下降（旧式常量不随耐久变化）。

**真实数据对照（首发表，满耐久）**：

| 组合 | R17 旧式 | R19.8 现行 | 差异 |
|---|---|---|---|
| M80（43/80/67）vs KITECO 6 级 UHMWPE 45（未穿） | 11 | 7 | 旧式 +57% |
| 同组合（假设穿透） | 10 | 5 | 旧式 +100% |
| M995（53/42/52）vs SAPI III+ 5 级陶瓷 50（穿透） | 17 | 12 | 旧式 +42% |
| 5.45 BT（37/54/44）vs SAPI（未穿） | 11 | 7 | 旧式 +57% |

**仍未确认**：
1. 视频（上）5:05 用 30/60 与 30/30 证明「耐久绝对值」相同则击穿率相同，但（上）6:38
   又说「剩余耐久百分比一致则击穿率一致」——两者自相矛盾；现行穿透概率仍用百分比模型
   （Desmos），本轮**未改**，待游戏内实测。
2. 视频 5:07 的示例算式自身取整不一致：按画面 (43÷50) 计算为 ≈19.5，画面写 ≈20.4
   （按 45÷50 才得 20.4）。本实现采用公式结构，未用该示例数值校准。
3. 防护能力随耐久比例的下降方式（线性）来自 4:13 的定性表述，未给出显式函数 → estimated。
4. 视频未提出「50% 耐久失效阈值」；现行实现也没有该阈值。
5. 旧 R17 的两个论坛标定点（7.7 / 13.6）与新公式不再吻合；标定帖未注明版本，不能据此判定
   新公式错误，但这是已知的版本/来源风险。

回归：`tests/test_r19_8_armor_formula.py` + `tests/js/combat_sim_r19_8_test.js`；
R17 相关断言已同步更新（未删除用例）。

## 8. R19.8b：绝对耐久穿透模型 / 删除 0.9 层损耗 / 头盔跳弹

**穿透概率（app.js `amArmorPenChance`）**
- 用户口径：视频（上）5:05 的 30/60 与 30/30 当前耐久同为 30 → 被穿率必须相同，
  所以耐久项改为**当前绝对值**，不再按 `dur/durMax` 百分比缩放。
- 视频没有给公式，只有 6:07 两张实测表；主模型 `AM_ARMOR_PEN_MODEL="table"`：
  `delta = 穿深 − 等级×10`，在 4 级 27/40/59/80/85%、5 级 52/62/72/84/88% 上分段线性插值，
  再加 `0.004 × (等级×10 − 当前绝对耐久)` 的线性修正，上限 95%。
  4 级/5 级表在满耐久（40/40、50/50）逐点精确命中。
- 备选 `desmosNorm`（保留开关）：`d = 100×当前绝对耐久/(等级×10)` 后套 Desmos 曲线；
  对 5 级表接近（±5 点），但 4 级低穿段高 20+ 点，故不采用。
- 回归：`tests/test_r19_8_pen_model.py` 固化两张表、30/60 == 30/30、绝对耐久单调性。
- 注意：fandom《Ballistics》仍写“remaining durability %”，与视频/用户口径冲突；
  本轮按用户明确要求采用绝对口径，冲突已记录。

**穿透后伤害**
- 删除 `CS.EST_LAYER_DMG_KEEP = 0.9`（主路径与对侧插板路径都不再乘），
  与视频（上）12:08 的减伤公式 `clamp(pen/(cls×10+12.5), 0.6, 1)` 一致；
  穿过护甲的人体伤害因此整体 +11.1%（例：M995 vs SAPI 32.05 → 35.62）。

**头盔跳弹（combat_sim.js）**
- 数据：`data/armor-ricochet.json`（tarkovgunsmith 的 `GetHelmetsDataSheetData` /
  `GetArmorModulesData`，2026-11-02 快照）：`x`=90° 最大概率、`y`=最小角 `z` 的最小概率，
  `z→90°` 线性插值；共 159 条，覆盖本地 77/112 个头盔。
- 规则（fandom “Angles and ricochets”）：只有头盔会跳弹；跳弹等同挡下，几乎无钝伤，
  头盔只掉最低 1 点耐久；其它护甲不受角度影响。
- 实现：`CS.ricochetChance(params, angle)`；`resolveShot` 仅在 `kind='helmet'`、
  `angle>0` 且有参数时判定；跳弹后 `stoppedBy='ricochet'`、`dmgToPart=0`、`durDmg=1`。
- 角度定义：弹道与表面法线的夹角，0=正面、90=掠射（由 gunsmith tooltip 的
  “min angle / 90° perpendicular” 推定，标 estimated）。
- 回归：`tests/test_r19_8_ricochet.py`（40° 边界、50%/90% 端点、不同头盔参数、
  39°/0° 不跳弹、非头盔层不跳弹、跳弹日志字段）。

## 9. R19.8c：用户给定护甲规则 / 三张公式截图落地

> **R19.8e 已全量切换到 tarkovgunsmith Ballistics.cs 公式（见 §10）。**
> 本节及以下 §9.4/§9.5 的线性钝伤 f、耐久斜率 0.5、66–75% 随机、12.5 抵抗系数等
> 均已被废止，仅保留为历史取证记录。

### 9.1 截图逐字转写（`docs/r19.8-armor-audit/formula-*.png`）

**图 1 子弹对护甲耐久伤害**（`formula-durability-damage.png`）：

```
穿透力×护甲伤害百分比 × 材料耐久系数 × (穿透力÷防护能力) × (如果穿透则 ×0.7)
```

**图 2 减伤代码**（`formula-damage-reduction-code.png`）：

```
if didPenetrate {
  let multiplier: Double = (pen / armorResistanceFactor).clamped(to: 0.6...1.0)
  adjustedDamage *= multiplier
```

**图 3 减伤说明**（`formula-damage-reduction-explain.png`）：

```
满耐久的情况下，护甲抵抗系数为：护甲等级×10+12.5
例如，四级甲的护甲抵抗系数是 4×10+12.5=52.5
子弹穿透力 ÷ 护甲抵抗系数 × 子弹肉伤 = 实际伤害
clamped(to: 0.6...1.0)   这步得出的数值只能在 0.6–1.0 之间
（最多减伤 40%，高级弹无额外伤害）
```

### 9.2 与口述规则的冲突处理（以图为准）

| 项 | 用户口述 | 截图 | 本轮实现 |
|---|---|---|---|
| 穿透损伤 | 66%–75% | ×0.7（固定） | **66%–75% 随机**（用户最终决定；截图固定 0.7 作为区间内取值） |
| 穿透力÷防护能力上限 | 最大 1.2 | 公式未画钳制 | 保留 1.2（口述；截图未否定，已记录） |
| 穿透值浮动 | ±1 | 未提及 | 保留 ±1（口述） |
| 减伤 | 与耐久有关 | 只给满耐久 52.5 与 0.6–1.0 | 抵抗系数按耐久比例缩放（推定，见下） |

### 9.3 穿透概率

- 用户指定 Desmos `m8cmsfokkl`；已从 `https://www.desmos.com/calc-states/production/m8cmsfokkl`
  （2026-11-02，HTTP 200）读取表达式：
  - `d`：Armor durability %（0–100）
  - `c`：Armor class（1–6）
  - `n`：Bullet pen（0–78）
  - `a=(121-5000/(45+d*2))*c*10*0.01`
  - `0.4(a-p-15)^2/100 {a-15<p<a}`
  - `(100+p/(0.9a-p))/100 {a<=p}`
- 实现：`d = 100 × 当前耐久 / 出厂原始满耐久`（`durOrig`，缺省 = 纸面满耐久）。
  `app.js amArmorPenChance` 默认 `AM_ARMOR_PEN_MODEL="desmos"`；上一轮 table 模型保留为开关。
- `30/60` 与“维修后上限 30、原始满 60 的 30/30” → d 都是 50% → 概率相同（已回归测试）。

### 9.4 钝伤

- **基础公式**（Tistory，2026-06-05，https://beam-maru.tistory.com/m/406）逐字：
  `블런트 딜 기준값 = 탄 기본 데미지 x 방탄판 BT%`（钝伤基准 = 弹药基础伤害 × 插板 BT%）。
  例：7.62x39 PS（61 伤害）对 Cult Termite 14% → 8.54；GAC 4sss2 26% → 15.86。
- **低穿按比例缩放（R19.8d，estimated）**：用户给定近似
  `f = clamp(穿透力 ÷ (护甲等级 × 10), 0, 1)`，
  `钝伤 = 弹药基础伤害 × 该层 BT% × f × 耐久系数`，多层再逐层衰减。
  依据 gunsmith 工具提示逐字“Low penetration rounds will do proportionally less than higher
  penetration rounds.”；**没有任何官方公式**，本轮按用户近似实现并标 estimated。
  数值示例（合成 5 级板 bt 30%、基础伤害 100）：穿透力 0/5/20/50/60 → f 0/0.1/0.4/1/1，
  钝伤 0/3/12/30/30。高穿弹 f=1 时保留用户示例（面罩 8 → 二级面罩 1.44）。
- **BT% 逐件**：本地 `items.json` 每件护甲/内衬的 `bt` 优先；其次 `data/armor-bt.json`
  构建期快照（gunsmith）；仍缺失时用材质兜底表
  （钛14/钢18/复合18（6级22）/聚乙烯26/陶瓷28/玻璃29/芳纶18/铝18）。
  快照中每条都带 `btSource`：`gunsmith`（逐件实测）或 `material-fallback`（材质兜底），
  后者共 9 件，未伪造逐件值，便于以后补数据（见 9.8）。
- **耐久与钝伤**：未找到公开公式；保留现有线性抬升 `1 + (1-耐久比例)×0.5`（estimated）。
- **多层钝伤**：未找到公开公式。Arena 0.2.1.0（https://arena.tarkov.com/news/patch-0210）逐字：
  “Soft armor under a ballistic plate reduces blunt throughput damage by 20% instead of 40%.”
  实现：第一层挡住后，后续每层继续衰减——软内衬 ×0.8；硬质层 × 自身 BT%×耐久系数。
  用户示例（面罩 8 → 二级面罩约 1）在合成场景得到 8 → 1.44（测试锁定）。
- **插板钝伤口径（冲突保留）**：gunsmith 工具提示逐字“Plate-collider armor ignores this stat
  and always have 0 blunt damage.”，即插板碰撞体恒 0 钝伤；用户实测口径是插板也产生钝伤，
  且耐久越低钝伤越高。本轮**不采纳 gunsmith 的插板恒 0**，按用户规则保留插板钝伤，
  代码注释标「按用户实测口径」，冲突在此保留记录。
- **口径/穿透**：Tistory 只要求“该弹能被板挡住”；未找到按弹种列出的钝伤表，
  基础量仍由 `弹药基础伤害 × 该层 BT%` 结算，穿透力再通过上面的 f 缩放。

### 9.5 减伤与多层

- 截图：满耐久 `resistance = 等级×10+12.5`，`clamp(pen/resistance, 0.6, 1.0)`，材质无关。
- 耐久项：截图只写“满耐久的情况下”；未找到耐久修正式 → 本实现按
  `resistance = (等级×10+12.5) × 当前耐久/原始满耐久`（estimated，下限 0.01）。
- 多层：每穿透一层，`st.dmg *= clamp(pen/resist,0.6,1.0)`，再 `pen -= 1`；
  第二层重复同一减伤。跨层穿透削减未找到固定公式/数值 → -1 点仍为 estimated。
- `×0.9` 层损耗已于 R19.8b 删除。

### 9.6 初始耐久 / 第二层 / 浮动

- 模拟配置新增：`当前耐久`、`原始满耐久`（作用于所有护甲层）、`附加内层/第二层` 下拉
  （面罩/头盔类，实验性，不做槽位兼容校验）。
- 穿透值 ±1：`cfg.penJitter`（app 默认开启）；每次射击用种子 rng 生成
  `penRoll ∈ [-1,1]`，日志记录 `penBase / penRoll / penUsed`，固定种子可复现。
- 逐层日志新增：减伤系数/抵抗值、钝伤 base→final、衰减层列表、穿透浮动。
- 穿透时甲伤：`CS.armorDamageRoll(rng())` → 0.66–0.75 随机，日志 `durRoll`，同种子可复现。

### 9.8 逐件 BT 数据与校准（R19.8c）

**数据源**
- tarkovgunsmith（2026-11-02，HTTP 200）：
  - `https://api.tarkovgunsmith.com/GetHelmetsDataSheetData`（57 头盔）
  - `https://api.tarkovgunsmith.com/GetArmorModulesData`（456 盔甲模块/插板/内衬）
  - 字段 `bluntThroughput`（0–1，页面显示为 BT%），逐件独立；快照
    `data/armor-bt.json` 共 **168 条 = 159 条 `btSource="gunsmith"` + 9 条
    `btSource="material-fallback"`**（只保留本地 items 存在的 id）。
  - `btSource="material-fallback"` 的 9 件（gunsmith 无逐件值，仅写材质兜底，未伪造）：
    `5fd4c474` 5.11 Hexgrid（6 级 UHMWPE，26%）、`609e8540` NFM THOR 隐蔽型（4 级 UHMWPE，26%）、
    `60a28319` NFM THOR 一体式（6 级 UHMWPE，26%）、`68a89146` NFM THOR 头眼（4 级 UHMWPE，26%）、
    `69cbfe44` AirFrame 瘟疫（4 级 Composite，18%）、`6a567ae5` AirFrame 慢工（4 级 Composite，18%）、
    `6a568dda` MTEK STRIKE 碳纤维（4 级 Composite，18%）、`6a576f21` ANA M1 胸挂（4 级 Aramid，18%）、
    `6a670ae1` DevTac 面罩 实验室（4 级 Composite，18%）。
  - 工具提示逐字：“The amount of blunt damage that is applied from the original damage when
    a non-plate armor collider blocks it. Plate-collider armor ignores this stat and always have
    0 blunt damage. This value is moderated by the armor's current "effectiveness", which depends
    on the AC and current durability out of max durability, vs the penetration value.
    Low penetration rounds will do proportionally less than higher penetration rounds.”
  - 逐件示例：FAST MT 14.31%；Altyn 面罩 7.92%；GAC 3s15m 插板 26%；Kiver-M 21.8%；
    Combined 面罩最低 3.96%，UHMWPE 3.96–50%，陶瓷 4.95/28/29/30%，钛 14/14.31%。
- fandom《Ballistics》（2026-11-02，Chrome 200）逐字：“This % is based on the specific
  armor's "blunt throughput" stat, the penetration value of the ammo, and the armor's class
  and remaining durability %. If there is soft armor between hard armor and the body, the
  blunt damage gets decreased.” 但 fandom 没有逐件 BT 表；`/wiki/Body_armor` 仅 2,059 字符，
  全文没有 "blunt/throughput/soft armor/liner" 命中 → 未找到逐件表。
- **按口径/弹种的钝伤表：未找到**。Tistory 的公式是“弹药基础伤害 × 插板 BT%”；
  gunsmith 只有单发计算器输出字段 `Blunt Damage`，没有静态逐弹种表。

**与用户材质系数的冲突**
- 用户材质表（钛14/钢18/复合18（6级22）/聚乙烯26/陶瓷28–29）与“插板级”BT 基本一致；
  但面罩/护垫等逐件 BT 明显更低（3.96–14.85%），不能只用材质表。
- 实现：逐件 `bt` 优先 → `data/armor-bt.json` → 材质兜底；两者都保留并注明来源差异。
- gunsmith 说“plate collider 的 BT 被忽略、钝伤恒 0”，与用户规则（插板耐久越低钝伤越高）
  冲突；本轮**按用户规则**保留插板钝伤，冲突在此记录。

**46.3% → 37.1% 校准**
- 用 Desmos + “-1 点”搜索：全参数域有 489 组可同时命中 46.3%/37.1%；限制为
  插板 4–6 级、内衬 1–3 级、耐久 20–100% 后有 15 组。
- 代表性组合（-1）：插板 4 级 31%、25.5 穿 → 46.58%；内衬 3 级 94%、24.5 穿 → 37.15%
  （差 +0.28 / +0.05 个百分点）。
- 同一组合换成 -10%：内衬 22.95 穿 → 26.16%（差 -10.9 点）。
- 另一组（-10%）：插板 5 级 21%、27.5 穿 → 46.10%；内衬 3 级 99%、24.75 穿 → 37.04%
  （差 -0.20 / -0.06）；同一组合 -1 则为 51.74%（差 +14.6 点）。
- 结论：**无法据此反推削减量**；-1 与 -10% 都能用不同参数组合拟合，数据不足以判别。
  本轮保留 -1 点，-10% 作为待确认备选。

### 9.7 回归

- `tests/test_r19_8b_rules.py` + `tests/js/combat_sim_r19_8b_test.js`：30/60==30/30、
  ±1 浮动与种子复现、耐久减伤、多层钝伤 8→1.44、软内衬 ×0.8、1.2 上限；
  R19.8d 新增低穿 f 测试——f<1（pen 5 / 5 级 → 0.1，8→0.8→0.144）、f=1（高穿弹 8→1.44）、
  边界 0（穿透力 0 → 钝伤 0）与边界 1（pen 50/60 → f 封顶 1）。
- `tests/test_r19_8_armor_formula.py`：真实弹种钝伤期望已带 f
  （M80 vs KITECO：80×0.26×(43/60)≈14.91；BT vs SAPI：54×0.30×(37/50)≈11.99）。
- `tests/test_r19_8_pen_model.py` 已改为 Desmos 主模型（table 仍测）；未删除用例。
- 初始耐久仍为全局输入（当前/原始满作用于所有层），本轮未扩成逐层。

## 10. R19.8e：全量切换 tarkovgunsmith Ballistics.cs（现行实现）

**来源（2026-11-02 实读）**
- GitHub 开源后端：https://github.com/Xerxes-17/TarkovGunsmith
  - `BackEnd/WishGranter/Statics/Ballistics.cs`
  - `BackEnd/WishGranter/Statics/Ballistics/BallisticComputah.cs`
- 反查报告：线上 API 717 组样本复算，最大误差 3.7e-6。
- 下表按原文函数名与公式实现；本项目逐发引擎对「概率」仍用种子掷点，
  而站点是期望值模型（`GetExpectedArmorDamage` 按穿透概率加权），差异在此注明。

### 10.1 穿透概率（PenetrationChance）

```
FactorA = (121 - 5000 / (45 + durabilityPerc * 2)) * armorClass * 0.1
durabilityPerc == 0            → 1
FactorA <= P                   → (100 + P / (0.9*FactorA - P)) / 100
FactorA-15 < P < FactorA       → 0.4 * (FactorA-P-15)^2 / 100
否则                           → 0
```

- `durabilityPerc`：站点 = 当前耐久 / 当前上限 × 100；
  本项目 = 当前耐久 / **出厂原始满耐久** × 100（用户已确认口径，见 §9.3）。
  未维修时相同；维修过的甲在本项目里 % 更低 → 穿透概率更高。
- 引擎 `L.dur <= 0` 仍走「全穿透、无减伤」分支（等价于站点 `durabilityPerc == 0 → 1`）。

### 10.2 减伤 / 穿透伤害（CalculateReductionFactor / PenetrationDamage）

```
RF = clamp(P / (FactorA + 12), 0.6, 1.0)
穿透伤害 = RF * Damage
```

- 替换旧的 `resistance = (等级×10+12.5) × 耐久比例`。
- 无 `×0.9` 层损耗；减伤与材质无关。

### 10.3 多层传递

- 每穿过一层：`P *= RF`、`D *= RF`（不再固定 `P -= 1`）。
- 下一层用自己的等级与耐久重新计算 FactorA 与 RF。
- 内衬耐久伤害：自身耐久伤害 × **上一层硬质护甲的击穿概率**
  （`expectedSoftDurabilityDamage *= platePenetrationChance`，低于 0.01 记为 0）。
  本项目只在子弹实际穿过插板后才结算内衬；站点是期望值模型，插板未穿时也会按概率扣一点。

### 10.4 钝伤（BluntDamage）

```
bluntScale = median(0.2, 1 - 0.03 * (FactorA - P), 1)
Blunt = BT% * bluntScale * Damage
```

- 废止：线性低穿因子 `f = P/(AC*10)`、耐久斜率 `1 + (1-耐久比例)*0.5`。
- **R19.8f 多层钝伤链（现行）**：第一层挡下后，把该层产出的钝伤作为输入继续送入下一层；
  下一层用自己的 BT%、等级/耐久%、`bluntScale` 再衰减一次；最终只把最后一层输出交给人体。
  穿透层不产生新钝伤，也不终止钝伤链，只做 P/D 减伤。
  ```
  层 1（挡住）：B1 = D × BT1 × scale1
  层 2（挡住）：B2 = B1 × BT2 × scale2
  层 2（穿透）：B2 = B1（不衰减），P2 = P1 × RF2，D2 = D1 × RF2
  人体钝伤 = 最后一层挡下后的 Bn
  ```
- **插板 + 非插板层**：站点口径，插板钝伤 ×0.6（`CS.SOFT_LINER_PLATE_BLUNT_MUL`）。
  Arena 口径（软内衬在插板下衰减 20%/40%）作为备选记录；本项目选站点 ×0.6，
  不再叠加 Arena 系数，避免同一层关系扣两次。
- **头盔 + 面罩**：8 → 二级面罩 `8 × BT2(0.18) × scale2(1)` = **1.44**
  （用户实测约 1–1.5）；三层继续衰减到 0.2592。
- 插板 + 内衬合成场景：插板 30 → ×0.6 = 18 → 内衬 `18×0.18×1` ≈ **3.24**。
  （历史值：R19.8d 24；R19.8e 只结算插板 18；R19.8f 连续链 3.24。）

> R19.8f 改动留痕：`host=HOMONAS user=MASTERJJ at=2026-11-03T09:42:32+08:00 round=R19.8f`

### 10.5 护甲耐久伤害（DamageToArmorBlock / DamageToArmorPenetration）

```
格挡：P * 甲伤% * clamp((P/AC)*10, 0.6, 1.1) * 材质毁损系数，最低 1
击穿：P * 甲伤% * clamp((P/AC)*10, 0.5, 0.9) * 材质毁损系数，最低 1
```

- 这是站点原文的 C# 左结合 `P / AC * 10`，即 `(P/AC)*10`；默认 `site` 模式。
- **风险**：常见输入（P ≥ 0.06×AC）都会顶到 1.1 / 0.9，甲伤几乎不随等级变化。
- 备选 `video` 模式：`clamp(P/(AC*10), 0.5/0.6, 1.2)`，保留用户的 1.2 上限。
  本项目同时实现两种写法，`CS.ARMOR_DMG_COEFF_MODE = 'site'` 为默认。
- 材质毁损系数（服务端 `GetDestructabilityFromMaterial`）：
  Aramid 0.1875 / UHMWPE 0.3375 / Combined 0.375 / Titan 0.4125 /
  Aluminium 0.45 / ArmoredSteel 0.525 / **Ceramic 0.55** / Glass 0.6。
  Ceramic 用 0.55（服务端），废止前端表的 0.6。
- 与站点的差异：站点按穿透概率加权取期望值；本项目按本发实际掷点选格挡或击穿系数。

### 10.6 数值变化（旧 R19.8d/R19.8e → 新 site + R19.8f 连续钝伤链）

| 场景 | 穿透状态 | 旧甲伤 | 新甲伤(site) | 旧钝伤 | 新钝伤 |
|---|---|---:|---:|---:|---:|
| M80 vs KITECO（6 级 UHMWPE 45/45） | 未穿 | 7 | **11** | 14.91 | **9.97** |
| M995 vs SAPI（5 级陶瓷 50/50） | 穿透 | ≈12（随机 0.66–0.75 × 17.53） | **14** | 0 | 0 |
| 5.45 BT vs SAPI（5 级陶瓷 50/50） | 未穿 | 7 | **10** | 11.99 | **9.74** |
| 头盔+二级面罩（5 级 bt8 / 2 级 bt18 / dmg100 / 穿60） | 未穿 | — | — | 8（R19.8e 只算第一层） | **1.44** |
| 三层（5 级 bt8 → 2 级 bt18 → 2 级 bt18） | 未穿 | — | — | — | **0.2592** |
| 插板+内衬（5 级陶瓷 bt30 / dmg100 / 穿透力60） | 未穿 | — | — | 24（×0.8） | **3.24**（18×0.6 → 内衬 0.18） |
| M80 vs KITECO（22.5/45） | 未穿 | 12 | **11** | 18.63（旧 f+斜率） | **15.24** |

穿透人体伤害：M80 vs KITECO 穿透时 `RF=0.6` → 80×0.6=48；
M995 vs SAPI 穿透时 `RF=0.8508` → 42×0.8508≈35.73。

### 10.7 site 与 video 甲伤写法对照（真实弹 × 甲）

| 场景 | 穿透状态 | site 系数 | site 甲伤 | video 系数 | video 甲伤 |
|---|---|---:|---:|---:|---:|
| M80 vs KITECO 45/45 | 未穿 | 1.1 | **11**（base 10.70） | 0.7167 | **7**（base 6.97） |
| M80 vs KITECO 22.5/45 | 未穿 | 1.1 | **11** | 0.7167 | **7** |
| M995 vs SAPI 50/50 | 穿透 | 0.9 | **14**（base 13.64） | 1.06 | **16**（base 16.07） |
| 5.45 BT vs SAPI 50/50 | 未穿 | 1.1 | **10**（base 9.85） | 0.74 | **7**（base 6.63） |

结论：`site` 让 M80（6 级）与 BT（5 级）的甲伤系数都顶到 1.1，**甲伤不随等级变化**；
`video` 保留等级/穿透比差异，但同一发高穿弹（M995）反而打出更高甲伤（16 > 14）。
两种写法都不能同时满足「甲伤与等级相关」和「高穿不超上限」，需用户最终决定。
本轮按用户指示默认 `site`。

### 10.8 保留与废止清单

- **废止**：66%–75% 随机、固定 0.7、线性钝伤 f、钝伤耐久斜率 0.5、
  旧 12.5 抵抗系数、固定 `P -= 1`、软内衬 ×0.8、材质 Ceramic 0.6。
- **保留**：穿透值 ±1 浮动（用户口径，estimated；站点是确定性）、头盔跳弹、
  逐件 BT 数据（`data/armor-bt.json` 168 条 = 159 gunsmith + 9 material-fallback）。
- **冲突保留**：站点 V2 插板钝伤恒 0 vs 用户实测有钝伤；本轮按用户口径保留，
  并在插板+内衬时 ×0.6。

### 10.9 回归

- `tests/test_r19_8b_rules.py`：新常数、site/video 系数、FactorA、RF 随耐久、
  多层 P/D 衰减、内衬耐久 ×击穿概率、钝伤 median 上下限、插板+非插板层 ×0.6；
  R19.8f 新增：单层 8、二级面罩 1.44、三层 0.2592、层 2 被穿透不终止链、低穿链 0.157。
- `tests/test_r19_8_armor_formula.py`：M80/M995/BT × KITECO/SAPI 的甲伤与钝伤手算值；
  site 模式下满耐久/半耐久甲伤相同（风险锁定）。
- `tests/test_r17_fixes.py`、`test_r15_fixes.py`：旧公式断言已按新公式重算，用例未删除；
  `test_r15` 的软内衬用例改为「插板 ×0.6 → 内衬再衰减」链式断言。
- 初始耐久仍为全局输入（当前/原始满作用于所有层），本轮未扩成逐层。
