# R19.23 三模式任务数据差异报告（自动生成）

> 生成工具 `tools/diff_tasks.py`；数据 `data/tasks/tasks.{regular,pve,pvps}.json`；生成时间 2026-10-28T11:46:46+0800。
> 口径：按**上游任务 ID** 求差集，绝不按名称合并；同 ID 逐字段比较。

## 一、数据规模

| 项目 | PvP（常规） | PvE | PvPS（赛季服） |
|---|---:|---:|---:|
| 实际收录任务数 | 503 | 499 | 462 |
| 任务目标总数 | 1416 | 1384 | 1304 |
| 前置关系（边） | 222 | 221 | 184 |
| 有前置的任务 | 203 | 202 | 169 |
| 赛季专属任务 | 0 | 0 | 0 |
| Kappa 必需 | 13 | 13 | 13 |
| 阵营限定 | 34 | 34 | 34 |
| 上游端点 | `/regular/tasks` | `/pve/tasks` | `/pvp-season/tasks` |
| 数据时间 | 见 sources.json | 见 sources.json | 赛季 2026-04-17 → 2026-12-07 |

## 二、配对差异汇总

| 检查项 | PvP vs PvE | PvP vs PvPS | PvE vs PvPS |
|---|---:|---:|---:|
| 任务数量（左/右） | 503 / 499 | 503 / 462 | 499 / 462 |
| 仅在左侧模式存在 | 27 | 41 | 38 |
| 仅在右侧模式存在 | 23 | 0 | 1 |
| 同 ID 有差异的任务 | 14 | 4 | 14 |
| 名称差异 | 0 | 0 | 0 |
| 任务目标差异 | 6 | 1 | 5 |
| 前置关系差异 | 3 | 1 | 2 |
| 前置条件差异 | 2 | 1 | 1 |
| 奖励与解锁差异 | 5 | 0 | 5 |
| 商人归属差异 | 0 | 0 | 0 |
| 等级差异 | 2 | 1 | 1 |
| 标记差异（Kappa/阵营等） | 0 | 0 | 0 |
| 失败分支差异 | 0 | 2 | 2 |
| 关系边（左/右） | 222 / 221 | 222 / 184 | 221 / 184 |

## 三、PvP（常规） ↔ PvE 明细

### 只在 PvP（常规） 存在的任务（27）

| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |
|---|---|---|---|---:|
| `66058cb22cee99303f1ba067` | 赚点快钱 - 1（PVP） | Easy Money - Part 1 | 滑雪 | 10 |
| `66058cb5ae4719735349b9e8` | 赚点快钱 - 2（PVP） | Easy Money - Part 2 | 裁判 | 10 |
| `66058cb7c7f3584787181476` | 平衡之力 - 1（PVP） | Balancing - Part 1 | 裁判 | 10 |
| `66058cb9e8e4f17985230805` | 平衡之力 - 2（PVP） | Balancing - Part 2 | 裁判 | 10 |
| `66058cbb06ef1d50a60c1f46` | 惊喜（PVP） | Surprise | 裁判 | 10 |
| `66058cbd9f59e625462acc8e` | 声东击西 - 1（PVP） | Create a Distraction - Part 1 | 裁判 | 10 |
| `66058cbf2f19c31a5a1337ec` | 声东击西 - 2（PVP） | Create a Distraction - Part 2 | 裁判 | 10 |
| `66058cc1da30b620a34e6e86` | 再创新高！- 1（PVP） | To Great Heights! - Part 1 | 裁判 | 10 |
| `66058cc208308761cf390993` | 再创新高！- 2（PVP） | To Great Heights! - Part 2 | 裁判 | 10 |
| `66058cc5bb83da7ba474aba9` | 再创新高！- 3（PVP） | To Great Heights! - Part 3 | 裁判 | 10 |
| `66058cc72cee99303f1ba069` | 再创新高！- 4（PVP） | To Great Heights! - Part 4 | 裁判 | 10 |
| `66058cc9ae4719735349b9ea` | 再创新高！- 5（PVP） | To Great Heights! - Part 5 | 裁判 | 10 |
| `66058ccbc7f3584787181478` | 良心作祟 - 1（PVP） | Against the Conscience - Part 1 | 篱笆 | 10 |
| `66058ccde8e4f17985230807` | 良心作祟 - 2（PVP） | Against the Conscience - Part 2 | 裁判 | 10 |
| `66058ccf06ef1d50a60c1f48` | 两害相权（PVP） | Between Two Fires | 篱笆 | 10 |
| `66058cd19f59e625462acc90` | 两难抉择（PVP） | Decisions, Decisions | 裁判 | 10 |
| `6761f28a022f60bb320f3e95` | 新起点 | New Beginning (Prestige 1) | 拉格曼 | 25 |
| `6761ff17cdc36bd66102e9d0` | 新起点 | New Beginning (Prestige 2) | 拉格曼 | 30 |
| `67e993b1ac26bf29380a320b` | 天降大礼 [PVP ZONE] | Surprise Gift | 灯塔看守 | 35 |
| `67e993f5ed537409f009da75` | 迟来的奖励（PVP） | Postponed Reward | 裁判 | 35 |
| `6848100b00afffa81f09e365` | 新起点 | New Beginning (Prestige 3) | 拉格曼 | 35 |
| `68481881f43abfdda2058369` | 新起点 | New Beginning (Prestige 4) | 拉格曼 | 40 |
| `697877e0c639962b2e0cf24f` | 竞技场差事（PVP） | Arena Business | 裁判 | 10 |
| `69788c2bac719606e40b4e77` | 专业热身 - 1（PVP） | Professional Fitness - Part 1 | 裁判 | 10 |
| `69788db3878a4385d10c0718` | 专业热身 - 2（PVP） | Professional Fitness - Part 2 | 裁判 | 10 |
| `69789418b2187365e70bb947` | 再创新高！- 6（PVP） | To Great Heights! - Part 6 | 裁判 | 10 |
| `697895b6c639962b2e0cf268` | 保持领先（PVP） | Hold the Lead | 裁判 | 10 |

### 只在 PvE 存在的任务（23）

| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |
|---|---|---|---|---:|
| `6834145ebc1f443d7603c8a7` | 赚点快钱 - 1（PVE） | Easy Money - Part 1 | 滑雪 | 10 |
| `6834158f2f0e2a7eb90b62c8` | 赚点快钱 - 2（PVE） | Easy Money - Part 2 | 裁判 | 10 |
| `68341846186efa3c5b07f989` | 平衡之力 - 1（PVE） | Balancing - Part 1 | 裁判 | 10 |
| `68341a0b2f0e2a7eb90b62d4` | 平衡之力 - 2（PVE） | Balancing - Part 2 | 裁判 | 10 |
| `68341b407559f4e6d50bc0ce` | 平衡之力 - 2（PVE） | Surprise | 裁判 | 10 |
| `68341c4babec72d95d0c1260` | 声东击西 - 1（PVE） | Create a Distraction - Part 1 | 裁判 | 10 |
| `68341d7d7559f4e6d50bc0db` | 声东击西 - 2（PVE） | Create a Distraction - Part 2 | 裁判 | 10 |
| `68341eb25619c8e2a9031501` | 再创新高！- 1（PVE） | To Great Heights! - Part 1 | 裁判 | 10 |
| `68341f6fe2e7ef70a3060a0a` | 再创新高！- 2（PVE） | To Great Heights! - Part 2 | 裁判 | 10 |
| `6834202a186efa3c5b07f9a2` | 再创新高！- 3（PVE） | To Great Heights! - Part 3 | 裁判 | 10 |
| `683421515619c8e2a9031511` | 再创新高！- 4（PVE） | To Great Heights! - Part 4 | 裁判 | 10 |
| `68342265a8d674b5740b31f0` | 再创新高！- 5（PVE） | To Great Heights! - Part 5 | 裁判 | 10 |
| `6834233fecd5cf3a440d855b` | 良心作祟 - 1（PVE） | Against the Conscience - Part 1 | 篱笆 | 10 |
| `68342446a8d674b5740b31fc` | 良心作祟 - 2（PVE） | Against the Conscience - Part 2 | 裁判 | 10 |
| `6834254f2f0e2a7eb90b62ef` | 两难抉择（PVE） | Decisions, Decisions | 裁判 | 10 |
| `683425dd8f5b18d29a05d9d1` | 两害相权（PVE） | Between Two Fires | 篱笆 | 10 |
| `683427418f5b18d29a05d9e3` | 天降大礼（PVE） | Surprise Gift | 灯塔看守 | 35 |
| `6834287b7559f4e6d50bc0fa` | 迟来的奖励（PVE） | Postponed Reward | 裁判 | 35 |
| `697878057aa1273126030fb0` | 竞技场差事（PVE） | Arena Business | 裁判 | 10 |
| `69788d4e963f08d9140bce19` | 专业热身 - 1（PVE） | Professional Fitness - Part 1 | 裁判 | 10 |
| `6978907718bd6d7cbd0e8b8e` | 专业热身 - 2（PVE） | Professional Fitness - Part 2 | 裁判 | 10 |
| `697895277d31587eab080266` | 再创新高！- 6（PVE） | To Great Heights! - Part 6 | 裁判 | 10 |
| `69789660b2187365e70bb94a` | 保持领先（PVE） | Hold the Lead | 裁判 | 10 |

### 同 ID 但字段不同的任务（前 30 条）

| 任务 | 字段 | 左值 | 右值 |
|---|---|---|---|
| 化学品 - 3 `597a0e57` | `prerequisites` | ["597a0b2986f77426d66c0633\|complete,active\|or"] | ["597a0b2986f77426d66c0633\|complete\|all"] |
| 医疗隐私 - 2 `5a68663e` | `objectives[1]` | {"count": 3, "diff": [{"index": 2, "left": {"type": "extract", "descZh": "以幸存状态撤离该区域", "co… | {"count": 2} |
| 一派胡言 `5c0bbaa8` | `objectives[3]` | {"count": 6, "diff": [{"index": 1, "left": {"type": "globalVariable", "descZh": "任务进行期间不得击… | {"count": 6} |
| 维和任务 `5c0d4c12` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "5e035eb586f774756048ec12×1"], "standing": ["5… | {"items": ["5696686a4bdc2da3298b456a×2750", "5e035eb586f774756048ec12×1", "619bdf9cc954664… |
| 古董爱好者 `5c1141f3` | `rewards` | {"items": ["5449016a4bdc2d6f028b456f×400000"], "standing": ["5ac3b934156ae10c4430e83c:1.5"… | {"items": ["5449016a4bdc2d6f028b456f×400000"], "standing": ["5ac3b934156ae10c4430e83c:1.5"… |
| 化学橱柜 `5f04886a` | `objectives[1]` | {"count": 2, "diff": [{"index": 1, "left": {"type": "extract", "descZh": "以幸存状态撤离该区域", "co… | {"count": 1} |
| 战利品 `60e71ccb` | `objectives[1]` | {"count": 2, "diff": [{"index": 2, "left": null, "right": {"type": "shoot", "descZh": "消灭 … | {"count": 3} |
| 无中生有 - 灯塔 `6179b4d1` | `objectives[4]` | {"count": 4, "diff": [{"index": 0, "left": {"type": "mark", "descZh": "在灯塔找到第一辆BRDM装甲车，并使用… | {"count": 2} |
| 反抗 `6179b5ea` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "60098ad7c2240c0fe85c570a×4", "69413241b1ce1e5… | {"items": ["5696686a4bdc2da3298b456a×2750", "60098ad7c2240c0fe85c570a×4"], "standing": ["5… |
| 最烂的差事 `63a9b229` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "619bdfd4c9546643a67df6fa×1"], "standing": ["5… | {"items": ["5696686a4bdc2da3298b456a×2750", "619bdfd4c9546643a67df6fa×1"], "standing": ["5… |
| 人间地狱 - 2 `666314b2` | `minLevel` | 21 | 12 |
| 人间地狱 - 2 `666314b2` | `prerequisites` | ["666314b0acf8442f8b0531a1\|complete,active\|or"] | ["666314b0acf8442f8b0531a1\|complete\|all"] |
| 人间地狱 - 2 `666314b2` | `conditions` | ["角色等级 ≥ 21", "大老板 忠诚等级 ≥ 3"] | ["角色等级 ≥ 12"] |
| 收视灵药 `675c15fb` | `minLevel` | 10 | 0 |
| 收视灵药 `675c15fb` | `prerequisites` | ["66058cb5ae4719735349b9e8\|active,complete\|or"] | [] |
| 收视灵药 `675c15fb` | `conditions` | ["角色等级 ≥ 10"] | [] |
| 引路先驱 `675c3507` | `objectives[1]` | {"count": 1, "diff": [{"index": 0, "left": {"type": "extract", "descZh": "在海关以幸存状态通过“铁路通道”… | {"count": 1} |
| 轻重缓急 `6942b44f` | `rewards` | {"items": ["5449016a4bdc2d6f028b456f×400000", "67600929bd0a0549d70993f6×1"], "standing": [… | {"items": ["5449016a4bdc2d6f028b456f×400000", "67600929bd0a0549d70993f6×1"], "standing": [… |

> 完整 18 条记录见 `data/tasks/diff-report.json` 的 `fieldDiffs`。

## 三、PvP（常规） ↔ PvPS（赛季服） 明细

### 只在 PvP（常规） 存在的任务（41）

| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |
|---|---|---|---|---:|
| `61e6e5e0f5b9633f6719ed95` | 亡羊补牢 - 信任 | Compensation for Damage - Trust | 篱笆 | 0 |
| `61e6e60223374d168a4576a6` | 亡羊补牢 - 赌注 | Compensation for Damage - Wager | 篱笆 | 0 |
| `61e6e615eea2935bc018a2c5` | 亡羊补牢 - 酒保 | Compensation for Damage - Barkeep | 篱笆 | 0 |
| `61e6e621bfeab00251576265` | 亡羊补牢 - 收藏 | Compensation for Damage - Collection | 篱笆 | 0 |
| `66058cb22cee99303f1ba067` | 赚点快钱 - 1（PVP） | Easy Money - Part 1 | 滑雪 | 10 |
| `66058cb5ae4719735349b9e8` | 赚点快钱 - 2（PVP） | Easy Money - Part 2 | 裁判 | 10 |
| `66058cb7c7f3584787181476` | 平衡之力 - 1（PVP） | Balancing - Part 1 | 裁判 | 10 |
| `66058cb9e8e4f17985230805` | 平衡之力 - 2（PVP） | Balancing - Part 2 | 裁判 | 10 |
| `66058cbb06ef1d50a60c1f46` | 惊喜（PVP） | Surprise | 裁判 | 10 |
| `66058cbd9f59e625462acc8e` | 声东击西 - 1（PVP） | Create a Distraction - Part 1 | 裁判 | 10 |
| `66058cbf2f19c31a5a1337ec` | 声东击西 - 2（PVP） | Create a Distraction - Part 2 | 裁判 | 10 |
| `66058cc1da30b620a34e6e86` | 再创新高！- 1（PVP） | To Great Heights! - Part 1 | 裁判 | 10 |
| `66058cc208308761cf390993` | 再创新高！- 2（PVP） | To Great Heights! - Part 2 | 裁判 | 10 |
| `66058cc5bb83da7ba474aba9` | 再创新高！- 3（PVP） | To Great Heights! - Part 3 | 裁判 | 10 |
| `66058cc72cee99303f1ba069` | 再创新高！- 4（PVP） | To Great Heights! - Part 4 | 裁判 | 10 |
| `66058cc9ae4719735349b9ea` | 再创新高！- 5（PVP） | To Great Heights! - Part 5 | 裁判 | 10 |
| `66058ccbc7f3584787181478` | 良心作祟 - 1（PVP） | Against the Conscience - Part 1 | 篱笆 | 10 |
| `66058ccde8e4f17985230807` | 良心作祟 - 2（PVP） | Against the Conscience - Part 2 | 裁判 | 10 |
| `66058ccf06ef1d50a60c1f48` | 两害相权（PVP） | Between Two Fires | 篱笆 | 10 |
| `66058cd19f59e625462acc90` | 两难抉择（PVP） | Decisions, Decisions | 裁判 | 10 |
| `674492b6909d2013670a347a` | 投石问路 | Ask for Directions | BTR 驾驶员 | 0 |
| `6744a4717e3818d5bb0680bb` | 稳定业务 | Stabilize Business | 拉格曼 | 0 |
| `6744a9dfef61d56e020b5c4a` | 电池换新 | Battery Change | BTR 驾驶员 | 0 |
| `6744af0969a58fceba101fed` | 独立的代价 | The Price of Independence | BTR 驾驶员 | 0 |
| `6745cbee909d2013670a4a55` | 独立的代价 | The Price of Independence | BTR 驾驶员 | 0 |
| `6745fae369a58fceba10343d` | 人往高处走 | The Higher They Fly | 滑雪 | 0 |
| `674600a366e6a521aa05eb66` | 偏离路线 | Route Deviation | 滑雪 | 0 |
| `674602307e3818d5bb069489` | 后知后觉 | Hindsight 20/20 | 滑雪 | 0 |
| `6746053b5b555b53460d9896` | 关键伙伴 | Key Partner | 滑雪 | 0 |
| `674605df60a98cad1b0ec799` | 致命论据 | Killer Argument | 滑雪 | 0 |
| `67460662d0fbbc74ca0f7229` | 识时务者为俊杰 | Choose Your Friends Wisely | 滑雪 | 0 |
| `6761ff17cdc36bd66102e9d0` | 新起点 | New Beginning (Prestige 2) | 拉格曼 | 30 |
| `67e993b1ac26bf29380a320b` | 天降大礼 [PVP ZONE] | Surprise Gift | 灯塔看守 | 35 |
| `67e993f5ed537409f009da75` | 迟来的奖励（PVP） | Postponed Reward | 裁判 | 35 |
| `6848100b00afffa81f09e365` | 新起点 | New Beginning (Prestige 3) | 拉格曼 | 35 |
| `68481881f43abfdda2058369` | 新起点 | New Beginning (Prestige 4) | 拉格曼 | 40 |
| `697877e0c639962b2e0cf24f` | 竞技场差事（PVP） | Arena Business | 裁判 | 10 |
| `69788c2bac719606e40b4e77` | 专业热身 - 1（PVP） | Professional Fitness - Part 1 | 裁判 | 10 |
| `69788db3878a4385d10c0718` | 专业热身 - 2（PVP） | Professional Fitness - Part 2 | 裁判 | 10 |
| `69789418b2187365e70bb947` | 再创新高！- 6（PVP） | To Great Heights! - Part 6 | 裁判 | 10 |
| … | 其余 1 条见 diff-report.json | | | |

### 只在 PvPS（赛季服） 存在的任务（0）

无。

### 同 ID 但字段不同的任务（前 30 条）

| 任务 | 字段 | 左值 | 右值 |
|---|---|---|---|
| 一派胡言 `5c0bbaa8` | `objectives[3]` | {"count": 6, "diff": [{"index": 1, "left": {"type": "globalVariable", "descZh": "任务进行期间不得击… | {"count": 6} |
| 外部订单 `673f61a0` | `failedConditions` | ["6744a9dfef61d56e020b5c4a"] | [] |
| 电池换新 `6744a728` | `failedConditions` | ["6744a9dfef61d56e020b5c4a"] | [] |
| 收视灵药 `675c15fb` | `minLevel` | 10 | 0 |
| 收视灵药 `675c15fb` | `prerequisites` | ["66058cb5ae4719735349b9e8\|active,complete\|or"] | [] |
| 收视灵药 `675c15fb` | `conditions` | ["角色等级 ≥ 10"] | [] |

> 完整 6 条记录见 `data/tasks/diff-report.json` 的 `fieldDiffs`。

## 三、PvE ↔ PvPS（赛季服） 明细

### 只在 PvE 存在的任务（38）

| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |
|---|---|---|---|---:|
| `61e6e5e0f5b9633f6719ed95` | 亡羊补牢 - 信任 | Compensation for Damage - Trust | 篱笆 | 0 |
| `61e6e60223374d168a4576a6` | 亡羊补牢 - 赌注 | Compensation for Damage - Wager | 篱笆 | 0 |
| `61e6e615eea2935bc018a2c5` | 亡羊补牢 - 酒保 | Compensation for Damage - Barkeep | 篱笆 | 0 |
| `61e6e621bfeab00251576265` | 亡羊补牢 - 收藏 | Compensation for Damage - Collection | 篱笆 | 0 |
| `674492b6909d2013670a347a` | 投石问路 | Ask for Directions | BTR 驾驶员 | 0 |
| `6744a4717e3818d5bb0680bb` | 稳定业务 | Stabilize Business | 拉格曼 | 0 |
| `6744a9dfef61d56e020b5c4a` | 电池换新 | Battery Change | BTR 驾驶员 | 0 |
| `6744af0969a58fceba101fed` | 独立的代价 | The Price of Independence | BTR 驾驶员 | 0 |
| `6745cbee909d2013670a4a55` | 独立的代价 | The Price of Independence | BTR 驾驶员 | 0 |
| `6745fae369a58fceba10343d` | 人往高处走 | The Higher They Fly | 滑雪 | 0 |
| `674600a366e6a521aa05eb66` | 偏离路线 | Route Deviation | 滑雪 | 0 |
| `674602307e3818d5bb069489` | 后知后觉 | Hindsight 20/20 | 滑雪 | 0 |
| `6746053b5b555b53460d9896` | 关键伙伴 | Key Partner | 滑雪 | 0 |
| `674605df60a98cad1b0ec799` | 致命论据 | Killer Argument | 滑雪 | 0 |
| `67460662d0fbbc74ca0f7229` | 识时务者为俊杰 | Choose Your Friends Wisely | 滑雪 | 0 |
| `6834145ebc1f443d7603c8a7` | 赚点快钱 - 1（PVE） | Easy Money - Part 1 | 滑雪 | 10 |
| `6834158f2f0e2a7eb90b62c8` | 赚点快钱 - 2（PVE） | Easy Money - Part 2 | 裁判 | 10 |
| `68341846186efa3c5b07f989` | 平衡之力 - 1（PVE） | Balancing - Part 1 | 裁判 | 10 |
| `68341a0b2f0e2a7eb90b62d4` | 平衡之力 - 2（PVE） | Balancing - Part 2 | 裁判 | 10 |
| `68341b407559f4e6d50bc0ce` | 平衡之力 - 2（PVE） | Surprise | 裁判 | 10 |
| `68341c4babec72d95d0c1260` | 声东击西 - 1（PVE） | Create a Distraction - Part 1 | 裁判 | 10 |
| `68341d7d7559f4e6d50bc0db` | 声东击西 - 2（PVE） | Create a Distraction - Part 2 | 裁判 | 10 |
| `68341eb25619c8e2a9031501` | 再创新高！- 1（PVE） | To Great Heights! - Part 1 | 裁判 | 10 |
| `68341f6fe2e7ef70a3060a0a` | 再创新高！- 2（PVE） | To Great Heights! - Part 2 | 裁判 | 10 |
| `6834202a186efa3c5b07f9a2` | 再创新高！- 3（PVE） | To Great Heights! - Part 3 | 裁判 | 10 |
| `683421515619c8e2a9031511` | 再创新高！- 4（PVE） | To Great Heights! - Part 4 | 裁判 | 10 |
| `68342265a8d674b5740b31f0` | 再创新高！- 5（PVE） | To Great Heights! - Part 5 | 裁判 | 10 |
| `6834233fecd5cf3a440d855b` | 良心作祟 - 1（PVE） | Against the Conscience - Part 1 | 篱笆 | 10 |
| `68342446a8d674b5740b31fc` | 良心作祟 - 2（PVE） | Against the Conscience - Part 2 | 裁判 | 10 |
| `6834254f2f0e2a7eb90b62ef` | 两难抉择（PVE） | Decisions, Decisions | 裁判 | 10 |
| `683425dd8f5b18d29a05d9d1` | 两害相权（PVE） | Between Two Fires | 篱笆 | 10 |
| `683427418f5b18d29a05d9e3` | 天降大礼（PVE） | Surprise Gift | 灯塔看守 | 35 |
| `6834287b7559f4e6d50bc0fa` | 迟来的奖励（PVE） | Postponed Reward | 裁判 | 35 |
| `697878057aa1273126030fb0` | 竞技场差事（PVE） | Arena Business | 裁判 | 10 |
| `69788d4e963f08d9140bce19` | 专业热身 - 1（PVE） | Professional Fitness - Part 1 | 裁判 | 10 |
| `6978907718bd6d7cbd0e8b8e` | 专业热身 - 2（PVE） | Professional Fitness - Part 2 | 裁判 | 10 |
| `697895277d31587eab080266` | 再创新高！- 6（PVE） | To Great Heights! - Part 6 | 裁判 | 10 |
| `69789660b2187365e70bb94a` | 保持领先（PVE） | Hold the Lead | 裁判 | 10 |

### 只在 PvPS（赛季服） 存在的任务（1）

| 任务 ID | 中文名 | 英文名 | 商人 | 等级 |
|---|---|---|---|---:|
| `6761f28a022f60bb320f3e95` | 新起点 | New Beginning (Prestige 1) | 拉格曼 | 25 |

### 同 ID 但字段不同的任务（前 30 条）

| 任务 | 字段 | 左值 | 右值 |
|---|---|---|---|
| 化学品 - 3 `597a0e57` | `prerequisites` | ["597a0b2986f77426d66c0633\|complete\|all"] | ["597a0b2986f77426d66c0633\|complete,active\|or"] |
| 医疗隐私 - 2 `5a68663e` | `objectives[1]` | {"count": 2, "diff": [{"index": 2, "left": null, "right": {"type": "extract", "descZh": "以… | {"count": 3} |
| 维和任务 `5c0d4c12` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "5e035eb586f774756048ec12×1", "619bdf9cc954664… | {"items": ["5696686a4bdc2da3298b456a×2750", "5e035eb586f774756048ec12×1"], "standing": ["5… |
| 古董爱好者 `5c1141f3` | `rewards` | {"items": ["5449016a4bdc2d6f028b456f×400000"], "standing": ["5ac3b934156ae10c4430e83c:1.5"… | {"items": ["5449016a4bdc2d6f028b456f×400000"], "standing": ["5ac3b934156ae10c4430e83c:1.5"… |
| 化学橱柜 `5f04886a` | `objectives[1]` | {"count": 1, "diff": [{"index": 1, "left": null, "right": {"type": "extract", "descZh": "以… | {"count": 2} |
| 战利品 `60e71ccb` | `objectives[1]` | {"count": 3, "diff": [{"index": 2, "left": {"type": "shoot", "descZh": "消灭 PMC 干员", "count… | {"count": 2} |
| 无中生有 - 灯塔 `6179b4d1` | `objectives[4]` | {"count": 2, "diff": [{"index": 0, "left": {"type": "mark", "descZh": "在灯塔找到第一辆BRDM装甲车，并使用… | {"count": 4} |
| 反抗 `6179b5ea` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "60098ad7c2240c0fe85c570a×4"], "standing": ["5… | {"items": ["5696686a4bdc2da3298b456a×2750", "60098ad7c2240c0fe85c570a×4", "69413241b1ce1e5… |
| 最烂的差事 `63a9b229` | `rewards` | {"items": ["5696686a4bdc2da3298b456a×2750", "619bdfd4c9546643a67df6fa×1"], "standing": ["5… | {"items": ["5696686a4bdc2da3298b456a×2750", "619bdfd4c9546643a67df6fa×1"], "standing": ["5… |
| 人间地狱 - 2 `666314b2` | `minLevel` | 12 | 21 |
| 人间地狱 - 2 `666314b2` | `prerequisites` | ["666314b0acf8442f8b0531a1\|complete\|all"] | ["666314b0acf8442f8b0531a1\|complete,active\|or"] |
| 人间地狱 - 2 `666314b2` | `conditions` | ["角色等级 ≥ 12"] | ["角色等级 ≥ 21", "大老板 忠诚等级 ≥ 3"] |
| 外部订单 `673f61a0` | `failedConditions` | ["6744a9dfef61d56e020b5c4a"] | [] |
| 电池换新 `6744a728` | `failedConditions` | ["6744a9dfef61d56e020b5c4a"] | [] |
| 引路先驱 `675c3507` | `objectives[1]` | {"count": 1, "diff": [{"index": 0, "left": {"type": "extract", "descZh": "在海关以幸存状态通过“铁路通道”… | {"count": 1} |
| 轻重缓急 `6942b44f` | `rewards` | {"items": ["5449016a4bdc2d6f028b456f×400000", "67600929bd0a0549d70993f6×1"], "standing": [… | {"items": ["5449016a4bdc2d6f028b456f×400000", "67600929bd0a0549d70993f6×1"], "standing": [… |

> 完整 16 条记录见 `data/tasks/diff-report.json` 的 `fieldDiffs`。

## 四、无法确认的部分

- 当前上游快照 **没有** 只属于 pvp-season 的任务：PvPS 任务集是 PvP 的真子集，因此「赛季专属任务」计数为 0。本项目不构造虚构赛季任务。
- PvPS 缺少的 41 个任务是上游 pvp-season 端点本身没有下发的，本项目按「该模式不存在」处理，不用 PvP 数据补齐。
- 赛季元信息（赛季名 / 赛季技能名）上游只给占位串与中文描述，界面不显示虚构赛季名。
