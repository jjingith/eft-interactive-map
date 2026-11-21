# 多层护甲机制研究与实现依据（R15）

> 结论先行：**没有任何一项多层护甲公式来自官方公布**。本文件把“有明确表格依据的字段”“社区一致定性”“社区/视频估算”分开标注，
> 引擎中每个常数都在 `combat_sim.js` 顶部有同名常量与注释。我们不宣称复刻了游戏服务器的精确计算。

## 1. 研究问题

1. 一发子弹命中被硬插板覆盖的部位时，判定顺序是什么？软内衬是否还参与？
2. 子弹**穿透硬板**后，剩余穿透力与伤害如何变化？软内衬是按新的剩余值再判定吗？
3. 子弹**被硬板挡住**时，人体受到的是钝伤；软内衬是否削减这份钝伤？
4. 连续多发命中同一部位时，硬板与软内衬的耐久是否独立结算？
5. 护甲耐久下降对穿透概率、钝伤有什么影响？
6. 材质如何影响护甲自身的耐久损失？
7. 0 耐久护甲的行为是什么？

## 2. 来源与证据等级

| # | 来源 | 日期 / 版本 | 内容 | 等级 |
|---|---|---|---|---|
| S1 | `https://escapefromtarkov.fandom.com/wiki/Ballistics`（经代理 Chrome 实访） | 页面未标注版本；同期社区版本 1.0.6.5.46221 | `materialDestructibility` 材质毁损系数表（aramid 0.1875 / uhmwpe 0.3375 / combined 0.375 / titan 0.4125 / aluminium 0.45 / armorSteel 0.525 / ceramic 0.6 / glass 0.6）；穿透弹对护甲耐久损伤比未穿透更低；子弹穿过护甲层会损失穿透力与伤害（定性） | 系数表 **verified**；层间损失语义 **estimated** |
| S2 | `https://www.reddit.com/r/EscapeFromTarkov/comments/1j053oy/...`（RSS 正文） | 2025-02 帖 | 芳纶/软层在硬板后仍有作用，讨论集中在钝伤与覆盖区域 | estimated（社区讨论，无原始样本表） |
| S3 | `https://www.reddit.com/r/EscapeFromTarkov/comments/1gdl784/...`（RSS 正文） | 2024-11 帖 | 插板存在时软护甲区域是否还有意义；多数实测反馈“板覆盖区以板为主，板外才靠软层” | estimated |
| S4 | `https://www.reddit.com/r/EscapeFromTarkov/comments/1akc487/`（RSS 正文） | 2024-02 帖 | Killa 前后插板与内衬耐久分别下降的现象描述 | estimated |
| S5 | YouTube `https://www.youtube.com/watch?v=CZwZMV4lqqk` | 旧版本穿透测试（R14 抽帧） | 抵抗系数 ≈ 等级×10+12.5；穿透后伤害随 `穿透力/抵抗` 变化并有 40% 减伤上限；耐久越低钝伤越高 | estimated（视频测试，版本早于当前，仅作模型来源） |
| S6 | `https://pve.tarkov-changes.com/view/218` | 1.0.6.5.46221，2026-08-01 | 数据挖掘显示弹药含 `PenetrationChanceObstacle` / `RicochetChance`；**未公开**护甲逐层公式或材质厚度表 | 字段 **verified**，公式 **missing** |
| S7 | 本地 `data/items.json` | 构建期快照 | 护甲/插板/内衬的 `cl`（等级）、`dur`（耐久）、`mat`（材质）、`bt`（钝伤穿透系数）、`z`（防护区域）、`aps`（插板位与固定软甲） | **verified**（字段语义已在 R10–R13 核实） |

**版本适用性说明**：S2–S4 的帖子发布时间跨越 2024–2025，未标注游戏版本；S5 是更早版本的测试。
因此“先硬板后软内衬”“软内衬削减钝伤”“各层耐久独立”三条采用为**实现依据**，但都只能算 estimated。
当前版本（1.0.6.5.46221）没有找到新的、带完整测试条件的多层护甲实测，故不声称旧结论在最新补丁下完全成立。

## 3. 当前实现：单发子弹状态机

`combat_sim.js` 的 `resolveShot()` 维护一份可变子弹状态 `st = { dmg, pen }` 与逐层日志：

```
初始：st.dmg = 弹药伤害经距离衰减后的值，st.pen = 距离衰减后的穿透力
① 距离：flightFn(ammo, dist) → { speed, pen, dmg }        （R14 已有）
② 障碍物（可选，按用户列表顺序逐层）：
     chance = clamp(ammo.pch × barrier.penChanceMul, 0, 0.95)
     未通过 → 记录跳弹/停止，整发终止（human 伤害 0）
     通过   → st.dmg ×= dmgKeep；st.pen ×= penKeep
③ 护甲（按 plate → helmet → liner 排序后逐层）：
     若该层 dur <= 0 → 记 degraded，全穿透无减伤（missing，见 §7）
     chance = penChanceFn(st.pen, L.cls, durRatio×100)      （Desmos 模型，R14 保留）
     穿透：
       resist   = L.cls × 10 + 12.5                          (estimated)
       factor   = clamp(st.pen / resist, 0.6, 1.0)           (estimated)
       st.dmg  ×= factor
       st.pen   = max(0, st.pen - 1)                         (estimated)
       st.dmg  ×= 0.9                                        (estimated)
     未穿透：
       blunt = st.dmg × L.bt × (1 + (1 - durRatio) × 0.5)     (estimated)
       若本层是 plate 且其后仍有覆盖该部位的 liner → blunt ×= 0.8  (estimated, Arena 0.2.1.0 社区口径)
       人体伤害 += blunt（int 换算后），整发终止
     耐久：durDmg = max(1, round(ammo.ard × 材质系数 × clamp(pen/(cls×10), 0.5, 2) × (穿透 ? 0.85 : 1)))
④ 未被任何层挡住 → 人体伤害 += st.dmg
```

**关键点**：`st` 在层与层之间真实传递；穿透硬板后，软内衬使用的是**已经衰减过的** `st.pen` / `st.dmg`，
不是弹药初始值。这一点是本轮修复的核心（修改前每层都用同一份初始值判定，只有 `pen-1 / dmg×0.9` 的记账式衰减）。

### 层顺序的依据与不确定性

- 依据：S2/S3/S4 与游戏内护甲界面均把硬插板视为“主防护层”，软内衬是插板后方的内层结构；正面命中先遇到插板。
- 实现：`KIND_RANK = { plate: 0, helmet: 1, liner: 2 }`，同 kind 保持用户配置顺序（`order`）。
- 不确定：真实服务器是否对“侧板/前后板”按命中方向细分、软内衬与插板之间是否存在间隙层，均未确认 → 标 estimated。
- 头盔与头盔内衬：头盔本体按 helmet 处理，其软内衬（若配置）按 liner 处理，位于头盔之后。

### 钝伤的处理

- **情况 A（被硬板挡住）**：人体只承受钝伤，绝不按“已穿透”结算完整伤害。若该部位还有软内衬覆盖，钝伤 ×0.8。
- **情况 B（穿板但被软内衬挡住）**：软内衬用穿板后的剩余 `dmg` 计算钝伤，人体只拿到这份钝伤。
- **情况 C（依次穿过插板与内衬）**：两层都按穿透分支衰减，最终只把剩余 `st.dmg` 计入人体。
- **情况 D（连续多发）**：每发开始时读取各层**当前** `dur`，插板与内衬的 `dur` 独立扣减，某层清零不清空另一层。

## 4. 决定论验证（确定性场景，非硬编码期望）

测试脚本 `tests/js/combat_sim_r15_test.js` 用固定种子与人工构造的层（不使用游戏数据，避免“为示例调参”），
结果由 `tests/test_r15_fixes.py` 断言。关键场景：

| 场景 | 输入 | 结果 | 说明 |
|---|---|---|---|
| E-B `ePlatePenLinerBlock` | 弹 dmg50 pen40，陶瓷板 cls4 dur40，芳纶内衬 cls3 dur30 | 板穿透：pen 40→39，dmg 50→34.29；内衬未穿透：钝伤 10.29；人体 **10.29** | 穿板后不是 34.29 直达人体 |
| E-B' `ePlatePenNoLiner` | 同上但无内衬 | 人体 34.29 | 对照：说明 10.29 的差额来自内衬层级 |
| E-A `eBluntWithLiner` | 低穿弹打板（板挡住），板后有内衬 | 钝伤 8 | 钝伤 ×0.8 |
| E-A' `eBluntNoLiner` | 同弹无内衬 | 钝伤 10 | 对照 |
| E-C `eThroughBoth` | 高穿弹依次穿板与内衬 | 人体 28.32 | 逐层递减（34.29 → 28.32） |
| E-D `eDurDrop` | 同弹连打两发 | 第 1 发挡板（dur 40→22），第 2 发穿透（durBefore=22） | 第 2 发用的是**当前**耐久 |
| E-D' `eLinerIndependent` | 两发后看两层耐久 | 板 40→25→10；内衬 30→23→16 | 各层独立扣减 |
| 材质 `eMatCeramic` / `eMatAramid` | 同 cls、同耐久，材质不同 | 板耐久损失 18 vs 6 | 材质系数真实生效 |
| 等级 `eClass3` / `eClass5` | 同弹不同等级 | 3 级穿透、5 级挡住 | 等级进入穿透概率与抵抗 |
| 复现 `eReproA/A2` | 同种子重跑 | 完全一致 | 随机流可复现 |

## 5. 穿透概率模型

- 沿用 R14 的 `amDesmosChance(p, c, d)`：Desmos 模型 `m8cmsfokkl`，`p=穿透力`、`c=护甲等级`、`d=耐久百分比 0–100`。
- 本轮**没有替换**该模型（R14 已与视频数据拟合），但明确：它描述的是“单层护甲对子弹的穿透概率”，
  不是官方公式，且不区分材质（材质只影响耐久损失速度）。
- 使用前会把 `st.pen`（穿过障碍/上层之后的**剩余**穿透力）作为输入，这是本轮修正之一。

## 6. 待确认（missing）

1. **0 耐久护甲的服务器行为**：当前实现为“无减伤全穿透”。社区常见说法是“0 耐久仍按软层/无防护处理”，但无官方确认。
2. **层间穿透力损失的精确值**：当前固定 `-1`，未随材质/厚度/入射角变化。
3. **穿透后伤害衰减的官方曲线**：当前 `clamp(pen/resist, 0.6, 1.0)` 来自 S5 的拟合，不是服务器公式。
4. **软内衬对钝伤的精确系数**：`0.8` 来自 Arena 0.2.1.0 社区口径，不是 EFT 本体数据。
5. **同一部位多层软护甲叠加**：当前按层独立计算，未验证是否应该合并。
6. **跳弹角/偏转**：本轮只按概率终止，不计算方向与二次命中。

## 7. 与修改前的差异（影响面）

| 项目 | 修改前 | 修改后 |
|---|---|---|
| 层间状态 | 每层都用初始 dmg/pen，只有记账式 `-1 / ×0.9` | `st` 在层间真实传递，下一层用剩余值 |
| 层顺序 | 配置数组顺序（UI 手填顺序） | 强制 plate → helmet → liner |
| 被硬板挡住 | 只按该层钝伤，忽略后方软内衬 | 判定后方是否有覆盖该部位的 liner，有则钝伤 ×0.8 |
| 逐发日志 | name/cls/chance/roll/durDmg/durAfter | 增加 penIn/dmgIn/penOut/dmgOut/blocked/blunt/softBacking/degraded |
| 耐久 | 单一 dur 字段 | 每层独立 durMax/dur，每发读取当前值 |
| 护甲来源 | UI 手填层表单 | 配装工作台同源装备（本体 + 插板 + 软内衬） |
