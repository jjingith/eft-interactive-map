# R16-E：Boss / 护卫 / 精英单位名单与数据状态

数据文件：`data/bosses.json`（沿用 **schema 1**，只做向后兼容扩展；新增 `revision: "r16"`、
`elites[]`、`followers[]`、`equipment.defaultPlates`）
结构化审计：`docs/r16-completeness/boss-loadouts.json`（逐 Boss 的装备 ID / 页面标题 / 默认插板）

构建脚本：`tools/build_boss_data.py`
数据来源：fandom **MediaWiki API**（`action=parse&prop=wikitext`），缓存 `build-cache/boss-wiki/`（22 个页面，381 KB）
物品名→ID：`tarkov.dev` 物品的 `wikiLink` 精确匹配（**不是名称模糊匹配**）

## 1. 正式 Boss（17）

| # | key | 名称 | 分类 | 总血量 | 血量 | 护甲/头盔/面罩 | 默认插板 | 护卫血量表 |
|---|---|---|---|---|---|---|---|---|
| 1 | killa | Killa | boss | 890 | verified | 3 / 2 / 2 | 前+后 | — |
| 2 | reshala | Reshala | boss | 752 | verified | 20 / 10 / 6 | 前 | 1 |
| 3 | shturman | Shturman | boss | 812 | verified | 10 / 0 / 0 | 前 | 1 |
| 4 | tagilla | Tagilla | boss | 1220 | verified | 2 / 3 / 0 | 前+后（6 级 / 4 级） | — |
| 5 | glukhar | Glukhar | boss | 1010 | verified | 31 / 9 / 2 | 前 | 3（Assault / Scout / Security） |
| 6 | sanitar | Sanitar | boss | 1270 | verified | 12 / 5 / 2 | 前 | 1 |
| 7 | kaban | Kaban | boss | 1300 | verified | 13 / 15 / 6 | 前+后 | 3 |
| 8 | kollontay | Kollontay | boss | 1055 | verified | 24 / 7 / 5 | 前 | 2 |
| 9 | partisan | Partisan | boss | 950 | verified | **0 / 0 / 0** | **无** | — |
| 10 | knight | Knight | goons | 1120 | verified | 1 / 1 / 0 | 前+后 | — |
| 11 | bigpipe | Big Pipe | goons | 910 | verified | 1 / 0 / 0 | 前+后 | — |
| 12 | birdeye | Birdeye | goons | 795 | verified | 2 / 0 / 0 | **无** | — |
| 13 | zryachiy | Zryachiy | boss | 1655 | verified | 1 / 0 / 0 | **无** | 1 |
| 14 | shadowoftagilla | Shadow of Tagilla | special（迷宫） | 1305 | verified | 1 / 1 / 0 | 前+后 | — |
| 15 | vengefulkilla | Vengeful Killa | special（迷宫） | 960 | verified | 2 / 1 / 1 | 前+后 | — |
| 16 | thewedge | The Wedge | special（破冰船） | 880 | verified | 1 / 1 / 0 | **无** | 1 |
| 17 | santaclaus | Santa Claus | event（圣诞） | 1040 | verified | 10 / 0 / 0 | **无** | — |

`verified` 的判定：页面 Health 表的逐项读数之和 == 页面标注的 Total（脚本自动校验，17/17 通过）。

## 2. 精英单位（4，单独目标类型，不与 Boss 混排）

| key | 名称 | 分类 | 总血量 | 装备（护甲/头盔） | 说明 |
|---|---|---|---|---|---|
| cultistpriest | Cultist Priest | elite | 850 | 0 / 0 | 邪教徒祭司；页面只给血量 |
| cultistwarrior | Cultist Warrior | elite | 850 | 0 / 0 | 邪教徒武士；页面只给血量 |
| rogue | Rogue | elite | 775 | 21 / 14 | Lighthouse 的 Rogue |
| blackdivision | Black Division | elite | 790 | 4 / 3 | 破冰船黑色师 |

> `Raiders` 页面是重定向（wikitext 仅 26 字符），没有独立血量表，本轮**不提供** Raider 目标；
> 不拿 Rogues 的数据冒充 Raider。

## 3. 护卫数据的实际情况

- 有独立血量表的：Reshala、Shturman、Glukhar（3 种）、Sanitar、Kaban（3 种）、
  Kollontay（2 种）、Zryachiy、The Wedge → **8 个 Boss**。
- 护卫**装备池未结构化**：页面只给血量、装备以自由文本描述（"heavily armed and armored guards"），
  没有可映射到物品 ID 的清单 → `equipmentConfidence: "missing"`，UI 不提供护卫装备预设。
- 页面偶有「护卫表与本体表数值完全相同」的重复表格（如 The Wedge），脚本判定为页面复用，
  **不采信**，记 `healthConfidence: missing`，避免把本体血量冒充护卫血量。

## 4. 装备池的分层（D1）

| 概念 | 数据字段 | 来源 | 可信度 |
|---|---|---|---|
| 护甲本体兼容池 | `items.json` 的 `aps[].plates` | 游戏数据 | verified |
| Boss 页面列出的装备 | `equipment.armor / helmets / faces / weapons` | wiki Equipment 表 | verified（列表存在）/ estimated（单局组合） |
| Boss 预设装备 | `equipment.defaultArmor` + `defaultPlates`（前/后/左/右） | 该护甲的**游戏默认预设** `containsItems` 顺序 | estimated |
| 允许的变体 | `equipment.plates`（页面明确列出的插板） | wiki | verified（若有） |

UI 最终可选插板 = **护甲兼容 ∩ 该面预设**（`amSimPlatePolicy().bySide`）。
页面没有列出变体时，**每面只保留预设的那一块**，不会把「胸挂能装的其它板」放进 Boss 池。

Tagilla 实例（用户反馈的具体错误）：

```
护甲：609e860ebd219504d8507525  Crye Precision AVS 插板胸挂（Tagilla 版）
前板：656fa99800d62bcd2e024088  Cult Termite 防弹插板       · 6 级 · 65 耐久
后板：656fa0fb498d1b7e3e071d9c  Global Armor’s Steel 防弹插板 · 4 级 · 45 耐久
```

修改前：前/后两个下拉各自列出该胸挂**全部兼容板**（含低等级板）；
修改后：前插板下拉只有 Cult Termite，后插板下拉只有 Global Steel（浏览器实测，
`screenshots/r16-04-boss-tagilla-plates.png`）。

## 5. 未解决 / 缺失（逐项）

1. **护卫装备池**：8 个 Boss 的护卫只有血量，没有可落地的装备清单（missing）。
2. **Killa / Tagilla 护卫**：页面没有独立血量表 → 不提供该护卫目标。
3. **Partisan / Birdeye / Zryachiy / The Wedge / Santa**：页面没有可识别的护甲/插板 →
   `defaultPlates = null`，UI 显示 missing 且不伪造插板。
4. **页面版本**：fandom 页面不标版本；本地数据快照是 1.0.6.5.46221（2026-08-01），
   抓取时间 2026-10-22，**版本漂移未逐项比对**（`data/bosses.json` 的 `source.gameVersion` 已注明）。
5. **单局随机组合概率**：页面只列「可能出现的装备」，没有概率分布 → 组合 `estimated`，
   不做「按概率随机生成 Boss」的模拟。
6. **39 条 wiki 链接无法映射到物品 ID**（`unclassified`，例如 "BOSS cap"、货币、任务物品），
   逐条记录在 `data/bosses.json` 的 `unclassified[]`，**没有被静默丢弃或强行归类**。
