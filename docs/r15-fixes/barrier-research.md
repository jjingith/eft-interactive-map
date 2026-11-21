# 障碍物 / 掩体穿透研究（R15）

> 与护甲机制**完全分开**：障碍物不使用“护甲等级 × 穿透力”的任何公式，也不消耗护甲耐久、不产生甲损。
> 本节所有材质倍率都是 **estimated**，`data/barriers.json` 的 `source.note` 已明确写出“不是游戏原始数据”。

## 1. 已确认与未确认

| 项目 | 结论 | 等级 |
|---|---|---|
| 弹药是否带“对障碍物穿透概率”字段 | 是，`PenetrationChanceObstacle`（本地 `pch`，200/200 覆盖） | **verified**（字段存在，S6 数据挖掘） |
| 弹药是否带跳弹概率 | 是，`RicochetChance`（本地 `ric`） | **verified**（字段存在） |
| 穿过障碍后是否损失伤害/穿透力 | 是，社区与 fandom 均描述“每穿过一层都会损失” | estimated（定性） |
| 材质 × 厚度 的参数表 | **不存在公开数据** | **missing** |
| 不同材质的具体穿透概率倍率 | 无公开数值，本文件为估算 | estimated |
| 跳弹角/偏转方向 | 无实现，仅按概率终止 | missing |
| 多层障碍的累积规律 | 按逐层独立相乘估算（未验证服务器是否合并） | estimated |

## 2. 来源

| # | 来源 | 日期 / 版本 | 用途 | 等级 |
|---|---|---|---|---|
| B1 | `https://pve.tarkov-changes.com/view/218`（经代理） | 1.0.6.5.46221，2026-08-01 | 确认弹药含 `PenetrationChanceObstacle`、`RicochetChance`；**未给材质×厚度表** | 字段 verified |
| B2 | `https://escapefromtarkov.fandom.com/wiki/Ballistics`（经代理 Chrome） | 页面未标注版本 | 定性：穿层损失穿透与伤害 | estimated |
| B3 | `https://www.reddit.com/r/EscapeFromTarkov/comments/jn9cxx/material_penetration/`（RSS 正文） | 2020-11（旧版本） | 玩家对木板/铁皮/混凝土的穿透观察；社区估算穿后伤害约低 10% | estimated（旧版本，仅作线索） |
| B4 | YouTube `https://www.youtube.com/watch?v=CZwZMV4lqqk` | 旧版本 | 穿透测试视频，仅作线索 | estimated |

**版本限制**：B3/B4 明显早于当前版本，只用来确定“量级”和“方向”（穿后变弱、金属概率低于木材、沙袋吸能）。
没有任何来源给出当前版本各材质的精确倍率，因此本实现是**近似模型**。

## 3. 实现公式

对按用户顺序排列的每一层障碍 `B`：

```
基础概率 base   = 弹药 pch（缺失时用 EST_BARRIER_CHANCE = 0.5）
实际概率 chance = clamp(base × B.penChanceMul, 0, 0.95)
判定            rand()  <  chance  → 通过
通过：dmg ×= B.dmgKeep ； pen ×= B.penKeep
未通过：记 ricochet（概率 = 弹药 ric × B.ricochetMul）或 stop
        → 本发终止，人体伤害 = 0，后续障碍与护甲都不再判定
```

- 障碍层**不**扣护甲耐久，不写 `armorLayers` 日志。
- 通过若干层障碍后进入护甲判定时，使用的是**已被障碍衰减过的** `dmg/pen`（见场景 `fThenArmor`）。
- 每层独立写一条 barrier 日志：`id/name/material/baseChance/chance/roll/passed/penIn/dmgIn/penOut/dmgOut/ricochet/confidence`。

## 4. 数据（`data/barriers.json`，9 条，全部 estimated）

| id | 名称 | 材质 | penChanceMul | dmgKeep | penKeep | ricochetMul | 说明 |
|---|---|---|---|---|---|---|---|
| wood_plank | 木质薄墙 / 木板 | wood | 1.0 | 0.85 | 0.9 | 0.5 | 对步枪弹几乎不阻挡 |
| wood_crate | 木箱 / 木材堆 | wood | 0.85 | 0.8 | 0.85 | 0.5 | 等效厚度更大 |
| metal_sheet | 金属薄板 / 铁皮 | metal | 0.6 | 0.75 | 0.8 | 1.0 | 易跳弹 |
| car_body | 汽车车身 | metal | 0.55 | 0.7 | 0.8 | 0.8 | 多层薄金属按单层等效 |
| brick_wall | 砖墙 | masonry | 0.35 | 0.65 | 0.7 | 0.6 | 低穿弹基本停止 |
| concrete_wall | 混凝土墙 | concrete | 0.25 | 0.6 | 0.65 | 0.4 | 最保守等效层 |
| glass | 玻璃 / 窗户 | glass | 0.92 | 0.9 | 0.95 | 0.2 | 影响小但仍有概率判定 |
| sandbag | 沙袋 | sand | 0.5 | 0.6 | 0.7 | 0.1 | 以吸能为主 |
| bush | 灌木 / 植被 | foliage | 0.99 | 0.98 | 0.98 | 0 | 几乎不影响弹体 |

`thickness` 字段全部为 `null`，并在 `fields.thickness` 注明 `missing`：**不允许按厚度插值**。

## 5. 验收场景（确定性，固定种子）

| 场景 | 输入 | 结果 |
|---|---|---|
| `fBase` | 无障碍，弹药 dmg50 | 人体 50 |
| `fOne` | 木板（dmgKeep 0.85） | 42.5 |
| `fTwo` | 木板 → 铁皮（0.85 × 0.75） | 31.875 |
| `fOrderAB` | 铁皮在前（chance 0.6，roll 0.72） | 0（被挡，`layers=[]`，不进入护甲） |
| `fOrderBA` | 木板在前 | 31.875（顺序改变了结果） |
| `fBlocked` | 混凝土墙挡下 | 人体 0，且不产生护甲日志 |
| `fThenArmor` | 木板 → 插板 → 内衬 | 板：pen 40→36、dmg 50→42.5；板层：36→35、42.5→26.23；内衬后 19.44 |
| `fReproA/A2` | 同种子重跑 | 完全一致 |

## 6. UI 与数据

- 位置：`#am-sim` 内第 3 个配置框，位于**「射击枪械」与「目标类型」之间**（第 1 枪械 → 第 2 弹匣 → 第 3 障碍物 → 第 4 目标类型 → 第 5 目标护甲 → 第 6 命中分布）。
- 数据来源：`data/barriers.json`（结构化，非 UI 硬编码名称）；下拉项由数据生成，`data-testid` 语义为 `data-sim="barrier-add"`。
- 已加入的障碍按顺序显示为可删除的行（`data-sim="barrier-list"`），顺序即作用顺序；「清空」回到无遮挡基准。
- 离线：数据随页面从 `http://127.0.0.1:8787/data/barriers.json` 加载，无外部请求。

## 7. 未解决

1. 各材质的真实 `penChanceMul / dmgKeep / penKeep` 无法核实，当前值是“方向正确、量级合理”的估算。
2. 厚度维度完全缺失，木箱/木板只能靠不同 id 表达。
3. 跳弹只作为“终止原因”记录，没有角度与二次命中。
4. 多层障碍是否应按“等效总厚度”合并，未验证；当前逐层独立相乘。
5. 障碍后进入护甲的入射角修正未实现（垂直于表面处理）。
