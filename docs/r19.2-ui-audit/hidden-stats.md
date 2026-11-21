# R19.2 隐藏属性调查与实现记录

> 任务要求：对 `OverSwing / EvoErgoDelta / ArmStamina / 100% Headshot acc / ADS Time` 逐项调查，
> 不允许因本地数据缺字段就整体标记"无数据"。本文记录每一项的调查过程、公式、来源、验证方法与结论。

## 调查过程（2026-10-24，全部留痕）

1. **上游数据全键检查**：`build-cache/r19-upstream/items.json`（json.tarkov.dev 2026-10 快照）
   的武器 properties 全键为：allowedAmmo / caliber / cameraSnap / centerOfImpact / defaultAmmo /
   defaultErgonomics / defaultHeight / defaultPreset / defaultRecoilHorizontal / defaultRecoilVertical /
   defaultWeight / defaultWidth / **deviationCurve / deviationMax** / effectiveDistance / ergonomics /
   fireModes / fireRate / maxDurability / presets / repairCost / **recoilAngle / recoilDispersion** /
   sightingRange / slots。
   → **没有** overSwing / armStamina / adsTime / evoErgo 字段。
2. **db4tarkov 官方教程视频转录**（"The Tarkov Weapon Builder You NEED To Try | Evo Ergo Tutorial"）确认：
   - OverSwing 是 yes/no 判定："whether the weapon will have overswing or not"，由其内置
     overswing calculator 算出；
   - **Evo Ergo**（evolved ergonomics）= 人机工效与**重量**的合成指标，用于预测真实 ADS 速度；
   - **EvoErgoDelta** = 当前装配相对"超摆阈值线"的距离；
   - **ArmStamina** = 按右上角设置里的**玩家力量等级**计算（"this then determines your arm stamina
     because that was calculated using the in-game as well"）；
   - **80%/100% Headshot acc** = 用"平均 PMC 头部尺寸 + 精度(MOA)"算出的爆头有效距离。
   → 这些是 **db4tarkov 专有衍生指标**，公式没有公开。
3. **公开社区资料检索**（EFT Wiki Performance modifiers、tarkovkit.com、
   SnailMann/tarkov-weapon-optimizer、namu.wiki 等）：只找到"人机影响 ADS 速度与持枪耐力"的
   定性说明，**没有**带系数的官方公式。

## 逐项结论

| 属性 | 结论 | 实现方式 | 可信度 |
|---|---|---|---|
| **ADS Time** | 已实现（估算） | `ADS(s) = max(0.2, 2.35 − 0.028 × 人机工效)`。锚点校验：db4tarkov AK-74 官方预设截图 ergo=67.5 → 本式 0.460s，db4 显示 0.465s（差 1%）。**仅此一个公开可核对锚点**，系数来自社区拟合而非官方文件 | estimated（单点校验） |
| **100% Headshot acc** | 已实现（估算） | 几何推导：`d = 0.08m(头部半径) / tan(散布角)`，散布角 = 上游 centerOfImpact（度）+ 配件精度修正。假设：头部宽 16cm、散布取满锥半径 | estimated（假设明确） |
| **OverSwing** | 待验证 | db4 专有（Evo Ergo vs 超摆阈值）。公式未公开、无法反算 → 界面显示「待验证」，悬停说明原因 | missing（不填 0） |
| **EvoErgoDelta** | 待验证 | 同上（Evo Ergo = 人机×重量的合成，权重系数未公开） | missing |
| **ArmStamina** | 待验证 | 依赖玩家力量等级输入 + 游戏内拟合，公式未公开 | missing |

### 顺带审计出的其他隐藏值（参考站展示、本地可核实）

| 字段 | 上游来源 | 状态 |
|---|---|---|
| 相机后坐 cameraSnap | `properties.cameraSnap`（AK-74 = 3.5） | ✅ 直接展示原值（verified） |
| 散布偏差上限 deviationMax | `properties.deviationMax`（AK-74 = 23） | ✅ 原值 |
| 后坐散布 recoilDispersion | `properties.recoilDispersion`（AK-74 = 10） | ✅ 原值 |
| 后坐角 recoilAngle | `properties.recoilAngle`（AK-74 = 90） | ✅ 原值（R19.2 新提取进 gun-stats.json） |
| deviationCurve | 曲线数组（散布-距离曲线） | 未展示：与 MOA 换算一样无法核实合成方式，展示原数组没有可读价值 |
| EER（人机/后坐比） | db4 派生（ergo 增量 ÷ 后坐百分比增量） | 未实现：定义已查明（教程视频），但作为配件排序指标而非整枪属性，本轮范围外 |

## 实现位置

- **引擎**：`gun_builder.js` `compute()` 新增字段 `adsTime / headshotRange / overSwing /
  evoErgoDelta / armStamina / cameraSnap / devMax / dispersion / recoilAngle`，
  每个字段带 `conf`（verified / estimated / missing）与 `why`（公式与来源说明）。
- **工作台属性区**：`renderGunStatsV2` 新增「隐藏属性（R19.2 调查）」段落，逐行显示
  当前值（可随配件变化刷新）、与默认装配的差值、可信度徽标与悬停说明。
- **Table 视图**：「扩展属性」开关切换后追加 5 列（ADS 估 / 爆头距离 估 / 相机后坐 / 后坐角 /
  散布偏差），对**裸枪**计算并在列名标注"估"。
- **数据**：`tools/build_gun_stats.py` 补充提取 `recoilAngle → ra`，从本地缓存重建
  `data/gun-stats.json`（无需重新下载）。

## 为什么 ADS 公式只用一个锚点还敢标 estimated 而不是 verified

- 373 条官方预设（data/gun-presets.json）记录了 ergo 真值但**没有** ADS 真值字段，
  无法像人机/后坐那样做多点回归验证；
- 唯一公开锚点是 db4 截图上的一个数（AK-74 预设 0.465s），单点拟合无自由度检验；
- 按任务规则「公式不完整就不要伪造精确值」，标注为 estimated 并写明单点校验事实。
