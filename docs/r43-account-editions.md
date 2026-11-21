# R43 账号版本（Editions）调研

- 调研时间：2026-11-04 02:00–02:05（Asia/Shanghai）
- 范围：只读调研，未改任何代码 / 前端 / 后端 / data 文件；本文与同名 ledger 是唯一新增产物
- 网络：代理 `127.0.0.1:7896`（实测连通，详见 [ledger](./r43-account-editions-ledger.md)）

---

## 0. 结论速览

1. **当前官方只有 5 个版本**：Standard、Left Behind、Prepare for Escape、The Unheard、Edge of Darkness。
   其中 **Edge of Darkness（黑边）已停售**，官方知识库直接标注 *not available for purchase*；
   其余 4 个仍在购买页上架。官方原文见 [KB 529](https://arena.tarkov.com/support/knowledge/529)（2025-06-11），抓取于 2026-11-04。
2. **中文俗称映射**（社区二手，非官方译名）：
   白边 = Standard；蓝边（也叫金边）= The Unheard；黑边 = Edge of Darkness（EOD，停售）。
   Left Behind 多称「留守版 / 遗落版」，Prepare for Escape 多称「准备逃离版」。
   来源：社区百科 <https://gtx950l.github.io/tarkov-encyclopedia/docs/buying-guide/>、游研社 <https://www.yystv.cn/p/11688>（均为二手，抓取 2026-11-04）。
3. **任务到底有没有差异：基本没有，只有一个历史例外。**
   - 主任务线、地图任务、Kappa 任务在 5 个版本间**完全共用**；官方版本差异清单是穷举式的，里面没有任何「任务集合不同」的条目；
   - 上游 `tarkov.dev` 的任务端点只按**游戏模式**分（`regular` / `pve` / `pvp-season`），**没有**任何按版本划分的任务端点——如果任务按版本不同，上游必须提供 edition 维度；
   - 唯一例外：**EOD（黑边，已停售）附带一条专属「Nostalgia quest chain（怀旧任务链）」，可用来拿 PMC Pockets**（官方原文，KB 538）。The Unheard 则是直接给「Expanded PMC pockets」，不需要做任务。
   - 另一条容易误读为「任务差异」的是 EOD 的 *每天可免费替换 2 个 operational tasks*——这是任务**操作权益**差异，不改变任务集合。
4. **价格/经济：版本不影响跳蚤价格、不影响保险赔付比例、不影响维修价格。** 版本只影响初始仓库、容器、初始装备/技能、商人初始声望、经验加成、DLC/季票、PvE 准入等。
5. **模式（`regular`/`pve`/`pvps`）差异是真实存在的**，且我们三份任务文件已覆盖：503 / 499 / 462 条，见 §4。
6. **数据落地建议：不要在 `tasks.*.json` / `items.json` / `flea-prices.json` 里加 `edition` 字段。**
   版本对这两类数据没有影响，硬加会变成 5 倍冗余且无上游可对账。
   最小方案是**新增一份静态 `data/editions.json`** + 前端只读渲染（见 §3）。

---

## 1. 版本清单

### 1.1 在售状态与价格

官方购买页 <https://www.escapefromtarkov.com/purchase>，区域选择器显示「俄罗斯及独联体国家」，
货币全部为 **rub.**，抓取时间 **2026-11-04 02:02 +08:00**（真实 Chrome，逐卡截图核对）：

| # | 官方名称（英） | 中文俗称 | 是否仍可购买 | 购买页价格（RU/CIS） | 卡片按钮文案 |
|---|---|---|---|---|---|
| 1 | The Unheard Edition | 蓝边 / 金边 / 未闻者版 | 在售 | **9200 rub.** | 升级游戏版本 |
| 2 | Prepare for Escape Edition | 准备逃离版 | 在售 | **2200 rub.** | 升级游戏版本 |
| 3 | Left Behind Edition | 留守版 / 遗落版 | 在售 | **1100 rub.** | 升级游戏版本 |
| 4 | Standard Edition | 白边 / 标准版 | 在售 | **3100 rub.** | 变更游玩区域 |
| 5 | Edge of Darkness Limited Edition | 黑边 / 黑暗边缘版 | **停售** | —（页面无此卡） | — |

**价格口径必须注意（如实记录，不做美化）：**

- 购买页**没有**任何划线原价或折扣角标；
- 但三张高阶卡片的按钮是「**升级游戏版本**」，Standard 的按钮是「**变更游玩区域**」，
  且页面数字呈 3100 → 1100 → 2200 → 9200 的非递增序列。
- 因此这 4 个数字**很可能是「从 Standard 升级的补差价」口径**（即 Left Behind 全价 ≈ 4200、PFE ≈ 5300、Unheard ≈ 12300 ₽），
  而不是四个版本的绝对标价。购买页本身没有给出可交叉验证的全价说明。
- 若要引用「绝对价」，用 Steam 官方商店（BSG 自营，2025-11-15 上架）作为交叉来源：
  - `Escape from Tarkov`（基础/Standard）：**US$49.99**（Steam appdetails `3932890`，2026-11-04 抓取）
  - `Escape from Tarkov: PVE Zone`：**US$29.99**（appdetails `4091290`）
  - `Left Behind Expansion Pack`（DLC，2025-11-15）、`Prepare for Escape Expansion Pack`（DLC，2025-11-15）、
    `The Unheard Steam Edition Expansion Pack`（DLC，2026-05-20）以**捆绑包**形式售卖，Steam 未给单品价；
    The Unheard 捆绑包页面（`store.steampowered.com/bundle/74190/`）当前区域显示 HK$1,450，属区域定价，仅供参考。
- 停售证据双份：官方知识库标题自带 *Edge of Darkness Limited Edition (not available for purchase)*（KB 538）；
  购买页全文检索 `Edge of Darkness` 结果为 0 次匹配。

> 结论：**不要把 1100 / 2200 / 9200 直接写成「版本售价」**。报告中建议写「购买页当前结算价（RU/CIS，升级口径）」。

### 1.2 出处与抓取日期

| 来源 | 类型 | 链接 | 抓取日期 | 用途 |
|---|---|---|---|---|
| 官方知识库「Game editions」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/529> | 2026-11-04 | 5 个版本总览、容器/仓库/经验/声望 |
| 官方知识库「Standard 装备清单」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/534> | 2026-11-04 | 初始装备逐项 |
| 官方知识库「Left Behind 装备清单」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/535> | 2026-11-04 | 同上 |
| 官方知识库「Prepare for Escape 装备清单」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/536> | 2026-11-04 | 同上 |
| 官方知识库「The Unheard 装备清单 + 附加权益」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/537> | 2026-11-04 | 同上 |
| 官方知识库「Edge of Darkness 装备清单 + 附加权益」 | 官方原文 | <https://arena.tarkov.com/support/knowledge/538> | 2026-11-04 | 同上 |
| 官方购买页 | 官方页面（SPA） | <https://www.escapefromtarkov.com/purchase> | 2026-11-04 02:02 | 在售 4 版、价格、区域 |
| Steam 商店 API / 捆绑包页 | 官方商店 | <https://store.steampowered.com/api/appdetails?appids=3932890>、`/bundle/74190/` | 2026-11-04 | USD 交叉价、Steam 版差异 |
| 官方 Wiki（Fandom）「Trading」 | 官方 Wiki（二手性质） | <https://escapefromtarkov.fandom.com/wiki/Trading> | 2026-11-04 | 跳蚤解锁等级 15、税费公式 |
| 社区百科 / 游研社 / NGA | 社区二手 | gtx950l.github.io、yystv.cn/p/11688、bbs.nga.cn | 2026-11-04 | 中文俗称、俗称由来 |

---

## 2. 版本之间到底差什么

证据强度标记：**〔官〕= 官方原文**；**〔官维〕= 官方 Wiki（可编辑，二手但权威）**；**〔控〕= 数据挖掘（上游 JSON 结构证明）**；**〔社〕= 社区二手**。

### 2.1 仓库与容器（全部〔官〕，KB 529 + 534–538）

| 版本 | 仓库（stash） | 安全容器 | 说明 |
|---|---|---|---|
| Standard（白边） | **10×30** | Alpha **2×2** | 基础 |
| Left Behind | **10×40** | Alpha **2×2** | 只加仓库，不加容器 |
| Prepare for Escape | **10×50** | Beta **3×2** | 容器首次升级 |
| The Unheard（蓝边） | **10×72** | Gamma TUE **3×3** | 当前最大 |
| Edge of Darkness（黑边） | **10×68** | Gamma EOD **3×3** | 停售；仓库比 TUE 少 4 格 |

> 注意：TUE 与 EOD 的 Gamma 容器尺寸都是 3×3，但官方给的是不同物品（`Gamma TUE` / `Gamma EOD`）。

### 2.2 初始装备与初始资源（〔官〕，KB 534–538）

| 版本 | 初始货币 | 装备特征（摘要） |
|---|---|---|
| Standard | 500,000 ₽ | 2× AK-74M、2× M9A3、2× MP5、PACA 软甲 ×3、基础医疗/弹药 |
| Left Behind | 500,000 ₽ + $500 | 追加 Mossberg 590A1、AFAK、CMS、12/70 独头弹等 |
| Prepare for Escape | 500,000 ₽ + $500 + €250 | 再加 Tactical glasses、Morphine、Metal fuel tank（金属油桶）等 |
| The Unheard | 1,000,000 ₽ + $1,000 + €500 | 装备最全（Grizzly 医疗包等），并带初始技能：Attention / Hideout Management / Weapon Maintenance / Bolt-action / Pistols 各 3 级 |
| Edge of Darkness | 500,000 ₽ + $1,000 + €500 | 装备接近 TUE，初始技能：Charisma 3 级 |

- **钥匙链 / 钥匙扣**：在 5 份官方清单（含逐件装备表）中**均未出现**「Keybar / 钥匙链」条目；
  也没有「版本赠送钥匙容器」的说法。结论：**钥匙链容量不由账号版本决定**，属于独立容器物品，
  社区流传的「黑边送钥匙链」说法**无法用官方来源证实**，标为〔社/不可证实〕。
- 逐件对比请直接看 KB 534–538 的 BEAR/USEC 双列表（官方原文，含数量）。

### 2.3 商人初始声望 / 等级 / 折扣（〔官〕）

| 版本 | 所有商人初始声望 | Fence 额外 | 其他商人权益 |
|---|---|---|---|
| Standard | 无 | 无 | 无 |
| Left Behind | 无 | 无 | 无 |
| Prepare for Escape | **+0.2** | 无 | 无 |
| The Unheard | **+0.2** | **+0.5** | 跳蚤市场**额外挂单槽位**（Additional slots on the Flea Market） |
| Edge of Darkness | **+0.2** | 无 | 每位商人**个人购买上限 +20%**；每天免费替换 2 个 operational tasks |

- **商人折扣**：没有任何版本直接给「采购折扣」。商人佣金/价格随**声望等级**变化，声望可用任务提升，属普惠机制〔官维 Trading〕。
- 版本给的是「**初始声望跳板**」，不是永久折扣。

### 2.4 保险 / 医疗 / 维修（〔官〕）

| 项 | 版本差异 | 证据 |
|---|---|---|
| 保险 | **仅 EOD** 有「Accelerated return of insured items（加快投保物品返还）」 | KB 538 |
| 医疗 | 无版本差异（战后治疗是 Therapist 普惠服务） | KB 529–538 无相关条目〔官〕 |
| 维修 | 无版本差异（维修是商人普惠服务） | 同上 |
| 特殊制造 | **仅 EOD** 有「Access to special stimulant crafting」 | KB 538 |

### 2.5 任务（重点，证据链三条）

| 结论 | 证据 | 强度 |
|---|---|---|
| 主任务集合全版本相同 | 官方版本差异清单为穷举式（容器/仓库/装备/技能/声望/经验/DLC/附加权益），**无任何任务条目** | 〔官〕KB 529–538 |
| 上游没有「按版本」的任务端点 | `json.tarkov.dev` 的任务端点只有 `/regular/tasks`、`/pve/tasks`、`/pvp-season/tasks`；我们三份 `tasks.*.json` 的字段也只有 `gameMode` / `upstreamGameModes` / `modeScope` / `onlyInModes` / `seasonOnly`，没有 edition 维度 | 〔控〕2026-11-04 实测 3 个端点均 200；字段见 `data/tasks/tasks.regular.json` |
| **唯一例外：EOD 怀旧任务链** | EOD 权益原文：*Nostalgia quest chain with an opportunity to get PMC Pockets* | 〔官〕KB 538 |

补充说明（避免误读）：

- The Unheard 的「Expanded PMC pockets」是**直接给**的，不走任务；
- EOD 的「每天免费替换 2 个 operational tasks」是**日常/运营任务的刷新权益**，不是任务集差异；
- 因此「版本导致任务不同」的正确表述是：**主线和绝大多数支线完全一致；EOD（已停售）多一条专属纪念任务链**。
  新号已经买不到 EOD，所以对**当前可购买的任何版本**而言，任务集合是**完全相同**的。

### 2.6 跳蚤市场（〔官〕+〔官维〕）

| 项 | 结论 | 证据 |
|---|---|---|
| 解锁 | PMC **等级 15** 解锁「自己挂单」；所有版本同一门槛 | 〔官维〕Trading：「After achieving PMC level 15, the player can start adding their own offers」 |
| 手续费 | 同一税费公式，版本无差异 | 〔官维〕Trading「Tax」小节 |
| 版本差异 | **只有 TUE 多给跳蚤挂单槽位** | 〔官〕KB 537 |

### 2.7 其他（DLC / PvE / Arena / 附加权益）

| 权益 | Standard | Left Behind | Prepare for Escape | The Unheard | Edge of Darkness |
|---|---|---|---|---|---|
| PvE Zone（无 wipe 的 PvE 合作模式） | ✗（Steam 单买 US$29.99） | ✗ | ✗ | ✓ | ✓ |
| Season Pass（后续 DLC） | ✗ | ✗ | ✗ | ✓ | ✓ |
| EFT: Arena「Ryzhy Edition」 | ✗ | ✗ | ✗ | ✓ | ✓ |
| 独特 ID / 臂章 / 近战 / 战术服装 | ✗ | ✗ | ✗ | ✓ | ✓（部分标注"未来版本开放"） |
| 合作训练模式 | ✗ | ✗ | ✗ | ✓ | ✓ |
| ETS（早期测试服） | ✗ | ✗ | ✗ | ✓ | ✗ |
| 藏身处「Cultists Circle」模块直给 | ✗ | ✗ | ✗ | ✓ | ✗ |
| 扩大 PMC 口袋 | ✗ | ✗ | ✗ | ✓（直给） | ✓（需怀旧任务链） |
| 经验加成 | 0% | +7% | +9% | **+20%**（组队也 +20%） | **+12%** |
| `Mark of the Unknown` 无线电物品 / 求救信号装置 | ✗ | ✗ | ✗ | ✓ | ✗ |

- **Steam 版差异（重要）**：Steam 的 *The Unheard Steam Edition* **不含 Season Pass**，
  官方在捆绑包页写明原因：*This limitation is caused by Steam platform rules and was taken into account in pricing.*
  即：**同为「蓝边」，官网版与 Steam 版在 DLC 权益上不同**——这一点在数据模型里必须留一个「渠道」维度，否则会错。
  （Steam 原文抓取 2026-11-04，`store.steampowered.com/bundle/74190/`）

---

## 3. 数据层面能否落地（只给方案，不实现）

### 3.1 现状核查：三份数据里没有任何能区分版本的字段

| 文件 | 顶层字段 | 是否有版本维度 |
|---|---|---|
| `data/tasks/tasks.regular.json` / `tasks.pve.json` / `tasks.pvps.json` | `schema, mode, modeLabel, upstreamGameMode, generatedAt, counts, tasks` | **无**。任务条目字段为 `gameMode / upstreamGameModes / modeScope / onlyInModes / seasonOnly`，全部是**模式**维度 |
| `data/items.json` | `schema, count, items, traders, tasks, audit` | **无**。物品字段 `n/sn/pt/ic/gw/gh/w/p/ts/src/trade/dur/cats/hb/mod/slots/sl/ci`，无 version/edition |
| `data/flea-prices.json` | `schema, source, gameMode, priceMode, modeLabel, modeNote, counts, items` | **无**。只有 `gameMode=regular`、`priceMode=pvp`（PvP 快照） |

结论：**版本对任务/物品/价格没有数据影响**，所以不需要在这三处加字段；真正的缺口是「版本权益本身」没有任何本地数据。

### 3.2 最小改动方案（推荐）

**新增 `data/editions.json`（唯一新增数据文件，静态事实表，前端只读）**

```json
{
  "schema": 1,
  "source": "https://arena.tarkov.com/support/knowledge/529 (+534..538)",
  "fetchedAt": "2026-11-04T02:04:46+08:00",
  "region": "RU/CIS",
  "editions": [
    {
      "id": "standard",
      "nameEn": "Standard Edition",
      "nameZh": "标准版",
      "aliases": ["白边", "Standard"],
      "status": "available",
      "channel": "official-site",
      "stashCells": [10, 30],
      "secureContainer": { "name": "Alpha", "w": 2, "h": 2 },
      "expBonusPct": 0,
      "traderStanding": { "allTraders": 0.0, "fenceBonus": 0.0 },
      "pveIncluded": false,
      "seasonPass": false,
      "extraPerks": [],
      "price": { "currency": "RUB", "amount": 3100, "basis": "checkout-display", "checkedAt": "2026-11-04" }
    }
  ]
}
```

建议枚举与字段：

| 字段 | 取值 | 说明 |
|---|---|---|
| `id` | `standard` \| `leftBehind` \| `prepareForEscape` \| `unheard` \| `eod` | 稳定主键 |
| `status` | `available` \| `legacy-discontinued` | EOD 为后者 |
| `channel` | `official-site` \| `steam` | **必须有**，因为 Steam 版 TUE 不含 Season Pass |
| `stashCells` | `[10,30]`…`[10,72]` | 官方格数 |
| `secureContainer` | `{name,w,h}` | Alpha/Beta/Gamma TUE/Gamma EOD |
| `traderStanding` | 数值 | 0.2 / Fence 0.5 |
| `extraPerks` | 字符串数组 | 逐条抄官方原文（跳蚤额外槽、保险加速、ETS…） |
| `price` | `{currency, amount, basis}` | `basis` 区分 `checkout-display`（升级口径）与 `store-list`（Steam US$） |
| `taskOverrides` | `[]` 或 `[{taskId, reason}]` | 仅 EOD 怀旧任务链用，避免改三份大任务文件 |

**为什么不加进 tasks/items/prices：**

- 任务集合与版本无关 → 加字段 = 5 倍冗余，且没有上游可对账；
- 价格与版本无关（版本不改变跳蚤税费公式/物价）→ 加 `edition` 只会制造伪维度；
- 现有的 `gameMode` 与「版本」是**正交的两个轴**，混进同一字段会让 `modeScope` 语义失效。

**若以后要落地「EOD 怀旧任务链」**：在 `editions.json` 的 `taskOverrides` 里登记 taskId 即可（需要先从 KB 538 / 游戏内确认 id；
`tarkov.dev` 上游**没有**该字段，所以无法自动抓取）。这也是当前唯一的「版本→任务」映射缺口。

### 3.3 需要从哪个上游取

- **版本权益**：官方 KB（arena.tarkov.com/support/knowledge/529、534–538）——静态、更新频率极低，适合手工维护 + 记录抓取日期。
- **价格**：官方购买页（区域相关、SPA、需真实浏览器）或 Steam appdetails API（JSON、稳定、USD）。
- **任务/物品/价格行情**：继续用现有 `json.tarkov.dev` 三个模式端点，**不要**引入 edition 维度。

---

## 4. 模式差异（`regular` / `pve` / `pvps`）

### 4.1 任务（本地已有，来自 `data/tasks/index.json` 与 `diff-report.json`）

| 模式 | 上游端点 | 任务数 | 目标数 | 带前置 | 前置边 | 仅此模式独有 |
|---|---|---|---|---|---|---|
| `regular`（PvP） | `/regular/tasks` | **503** | 1416 | 203 | 222 | 26 |
| `pve` | `/pve/tasks` | **499** | 1384 | 202 | 221 | 23 |
| `pvps`（PvPS 赛季服） | `/pvp-season/tasks` | **462** | 1304 | 169 | 184 | 0 |

两两差异（`data/tasks/diff-report.json`，生成于 2026-10-28）：

| 对比 | 公共任务 | 左独有 | 右独有 | 同 id 但内容不同（目标/前置/条件/奖励/等级） |
|---|---|---|---|---|
| regular vs pve | 476 | 27 | 23 | 14（目标 6 / 前置 3 / 条件 2 / 奖励 5 / 等级 2） |
| regular vs pvps | 462 | 41 | 0 | 4 |
| pve vs pvps | 461 | 38 | 1 | 14 |

要点：

- **pvps 是 regular 的子集**（`index.json.modeMeta.pvps.subsetOf = ["regular"]`，只此模式 0 条）；
  和 regular 相比缺 41 条，其中包含 PvP 专属练级任务（如 *Easy Money - Part 1（PVP）*、*Balancing - Part 1（PVP）*）。
- **pve 有 23 条独有任务**（id 以 `6834…` / `6978…` 开头，如「赚点快钱 - 1（PVE）」），
  regular 侧则有 **27 条**在 PvE 中缺失（`index.json` 的 `onlyHere` 记 26，逐对比 `diff-report.json` 记 27，差 1 条为口径差异）。
- 同 id 任务在两模式间**目标条件会变**（14 条），说明「模式差异」不只是开关，而是内容级差异。
- 赛季信息：`data/tasks/season.json` → **Kord Breach**，2026-04-17 ～ 2026-12-07，40 条赛季 perk。
- 顺带发现（**不是本轮修改造成**）：三份任务文件里 `nameEn` 字段的值疑似被污染，
  形如 `"66058cb22cee99303f1ba067 name"`（id + " name"），而 `nameZh` 正常（如「赚点快钱 - 1（PVP）」）。
  这会影响英文界面下的任务名展示，建议由负责 `tools/` 的会话排查。

### 4.2 价格（实测）

| 项 | 结果 | 证据 |
|---|---|---|
| PvP 价格上游 | `/regular/items` → **200**，17,344,134 B | 2026-11-04 实测（curl + 代理） |
| PvE 价格上游 | `/pve/items` → **200**，17,274,460 B，**可用** | 同上；`data.items` 下 5498 个 id |
| PvPS 价格上游 | `/pvp-season/items` → **200**，17,136,299 B | 同上（本轮**未入库**，仅验证可用） |
| 同 id 价格差异 | 例：`5447a9cd4bdc2dbd208b4567` PvE `11111` vs PvP `44415`；`5448bd6b4bdc2dfc2f8b4569` PvE `13000` vs PvP `12000` | 逐 id 抽样 |
| 现有快照 | `data/flea-prices.json` 是 **PvP 快照**（`priceMode=pvp`），**不能**用于 PvE/PvPS 展示 | `data/flea-prices.json` 元数据 |

> 结论：**PvE 价格上游确实可用**，且 PvP/PvE 价差极大（延续 r42 的 2.38% 同值结论）。
> 若前端在 `pve` 模式继续读 `flea-prices.json`，会把 PvP 价格当成 PvE 价格展示——这是当前**真实的误导风险**。

---

## 5. 交互建议（模式 + 版本怎么呈现）

现状：项目已有一个全局模式控件 [`js/game-mode.js`](../js/game-mode.js)（`regular/pve/pvps`，存 `localStorage["eftmap.gameMode"]`，全应用共享），
任务页已按模式换数据。**版本完全可以复用同一套「全局单一状态 + 订阅通知」的写法**，不要另造一套。

### 方案 A（推荐）：两级分离——模式在上、版本在「账号」侧，切换版本不重载

- **模式**：保留顶部 `#game-mode-bar`（现成），它决定任务集 / 价格 / 跳蚤等级等**真实数据**。
- **版本**：放进「账号设置」抽屉（任务页侧栏或页头头像），只影响**权益对照卡 + 少量标记**，
  例如「你的仓库 10×30，安全箱 Alpha 2×2」「商人初始声望 +0.0」。
- **切换版本时不重载任务/价格**（数据相同），只重绘权益卡；同时给出显式提示：
  「任务与价格不随版本变化；版本只影响仓库/容器/初始装备/声望/DLC」。
- 好处：语义正确、改动最小、不会出现「5 个版本 × 3 个模式」组合爆炸；实现上只需要一个
  `window.GWEdition`（照抄 game-mode.js 的 `get/set/subscribe/持久化` 四件套）读 `data/editions.json`。

### 方案 B：单下拉「模式 × 版本」合并（如 `PvP · 白边`）

- 优点：一次选完，视觉简单；
- 缺点：把**正交**的两个轴塞进一个控件，用户会以为「换版本要重新加载任务」，
  且组合数 3×5=15，任何一个维度变化都触发全量重载，容易出现「任务明明没变却闪一下」的错觉。
- **不推荐**。

### 方案 C：版本做「过滤层」——只在任务页多一个 `EOD 专属` 标记

- 做法：`editions.json.taskOverrides` 给出 EOD 怀旧链 id，任务页在该版本下高亮/折叠；
  其它版本不显示。
- 优点：精确表达「唯一的任务差异」；
- 缺点：只覆盖 1 个历史版本的 1 条链，单独做一层 UI 收益很低。
- 可作为**方案 A 的可选增强**（默认关闭），不建议单独上。

### 推荐组合与影响范围

**A 为主 + C 作为可选标记**，并明确三件事：

1. **影响范围提示**：模式切换 = 任务集 / 价格 / 跳蚤等级 / 进度（现有 `progress.modes` 已按模式隔离）都要换；
   版本切换 = 只换权益卡，**不重载**。
2. **数据快照提示**：当模式 = `pve` 或 `pvps` 且仍在使用 PvP 快照时，必须显示
   「当前价格为 PvP 快照，仅供参考」——或者更好：直接置灰/隐藏价格列，直到 PvE/PvPS 快照入库。
3. **首次进入引导**：默认 `regular` + `standard`，且允许「不知道版本」——给一个「不确定 / 稍后再选」选项，
   因为版本只影响对照表，不影响主流程。

---

## 6. 未解决 / 风险

1. **购买页价格口径未证实**：3100/1100/2200/9200 是「绝对价」还是「升级差价」无法从页面本身判定（页面无折扣标记、按钮文案混合）。
   建议在任何展示里标注 `basis=checkout-display`，不要写「官方售价」。
2. **区域限制**：页面区域选择器仅暴露「独联体 / 欧洲」，无法切到北美/亚太；本轮只拿到 RUB 价格。
3. **钥匙链**：官方 5 份清单均无钥匙链条目，「黑边送钥匙链」只有社区说法，无法证实。
4. **EOD 怀旧任务链的 taskId 未取得**：上游 tarkov.dev 无该字段，需游戏内或 KB 538 进一步确认。
5. **Steam 渠道差异**：Steam 版 TUE 不含 Season Pass，若将来做版本对照，必须加 `channel` 维度。
6. **中文俗称均为社区二手**，官方中文站把它译作「未闻者版本」，未使用「蓝边」这种俗称。
