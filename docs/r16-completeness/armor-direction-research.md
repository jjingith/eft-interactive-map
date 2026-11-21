# R16-F：前后插板与方向性命中（研究 + 模型边界）

## 1. 修改前的问题（已复现）

R15 的实现把所有护甲层按 `KIND_RANK = { plate: 0, helmet: 1, liner: 2 }` 排序后**串成一条链**，
每一发都从头走到尾。`plate` 只有"硬插板"一个类别，没有前后之分，所以：

- 正面射击会先算前插板，再算**后插板**，然后才算软内衬；
- 后插板被当成"入体前的第二层防护"，会额外减伤、额外掉耐久。

复现方式（R15 代码 + Tagilla 预设）：正面命中胸腔时，`layers` 里同时出现前板与后板，
后板耐久随正面射击下降。这与用户描述的现象一致。

## 2. 资料与证据

| 来源 | 用法 | 结论强度 |
|---|---|---|
| fandom《Crye Precision AVS plate carrier (Tagilla Edition)》（经 MediaWiki API 读取） | 该胸挂的前后板位与默认插板（Cult Termite 6 级 / Global Armor's Steel 4 级） | verified（页面 + 默认预设交叉验证） |
| fandom《Armor plates》 | 插板有独立防护区（前/后/侧），板与软甲是不同层 | verified（定性） |
| r/EscapeFromTarkov `1akc487`（Killa 前后插板耐久） | 「正面子弹可能让后板掉耐久」的社区观察 | estimated（可能是命中框/顺序问题） |
| r/EscapeFromTarkov `194tg9j` / `1fyz31a` / `1n3j9wc` | 护甲命中框历史问题、板与软甲覆盖关系 | estimated（旧版本案例，不能当官方算法） |
| tarkov.dev 物品默认预设 | 每件护甲默认装哪些板（`containsItems` 顺序） | verified（数据字段） |

> 说明：本轮 `escapefromtarkov.fandom.com` 的 HTML 页面被 Cloudflare 拦截（403 / 安全验证），
> 改用 **MediaWiki API** 成功读取 wikitext；`api.tarkov.dev/graphql` 返回 "GraphQL server unavailable"，
> 未使用 GraphQL 数据。Reddit 正文本轮**未重新抓取**，仅引用用户任务书给出的链接作为线索，
> 因此社区观察一律标 `estimated`。

## 3. 实现的模型

### 3.1 方向作为输入

`CS.simulate(cfg)` 新增 `dir: 'front' | 'back' | 'left' | 'right'`（缺省 `front`）。
每个护甲层可带 `side`：

| kind | side 来源 |
|---|---|
| plate | 插板槽名：`Front_plate → front`、`Back_plate → back`、`Left_side_plate → left`、`Right_side_plate → right` |
| liner（软内衬） | 软甲 zone：`Soft_armor_front/back/left/right` |
| helmet / 头盔内衬 | `all`（与方向无关） |

`side` 缺省 `all`，**保持 R14/R15 场景的旧行为**（未标注侧别的层照旧串联），
所以 R15 的 27 个引擎场景与全部旧测试不需要修改即可通过。

### 3.2 三类计算路径

| 情形 | 实现 |
|---|---|
| 正面命中前插板 | 只把 `side=front` 的板与软甲放进链条；后侧层进入 `layersSkipped`，**不参与任何结算** |
| 正面命中未覆盖区（无前板） | 链条为空（或只剩软甲），人体吃满伤害；不会因为"有后板"产生减伤 |
| 穿过躯干后撞后板 | 作为**独立后续事件**：`exitModel: 'estimate'` 时才计算，发生在入体伤害结算之后，只扣对侧板耐久并单独记账 |

`layersSkipped[].reason = "not-on-shot-direction"`，日志里会打印「本方向未经过：…」。

### 3.3 出口碰撞（可选，默认关闭）

```
cfg.exitModel = 'estimate'
  → 入体后，若对侧存在覆盖该部位的插板：
     ePen = 剩余穿透 × EST_EXIT_PEN_KEEP(0.6)
     eDmg = 剩余伤害 × EST_EXIT_DMG_KEEP(0.35)
     按正常穿透判定扣该板耐久，记录在 log.exit{phase:'after-body', confidence:'estimated'}
  → 人体伤害与 exitModel='off' 时**完全一致**（测试锁定）
```

`EST_EXIT_PEN_KEEP / EST_EXIT_DMG_KEEP` 是**没有依据的估算**，只用于演示"如果发生二次碰撞，
影响会有多大"，不代表游戏公式。

## 4. 明确不声称的部分

- 不声称复刻了游戏的三维躯干路径与出口弹道：本模型没有躯干厚度、没有出口方向、没有命中框。
- 不声称"后插板永远不会参与正面射击"：社区确有正面子弹让后板掉耐久的报告，
  但那可能是命中框/顺序/旧版本问题；本轮只保证**它不会在入体前被当作防护层**。
- 不声称方向性软甲的覆盖范围与游戏一致：`Soft_armor_left/right` 只覆盖侧胸，
  与 7 部位模型（胸/胃）的投影是近似。

## 5. 测试如何验证因果（而不是只查文字）

`tests/test_r16_completeness.py` + `tests/js/combat_sim_r16_test.js`：

| 场景 | 断言 |
|---|---|
| 正面 | `layers` 只有 front 层；back 层出现在 `layersSkipped` |
| 背面 | `layers` 只有 back 层；front 层被跳过 |
| 左侧 | 只有 `左侧板`，前后/右板都被跳过 |
| 正面 + 只有后板 | `layers == []`，`dmgToPart == 50`（满伤） |
| 穿前板 → 前内衬挡住 | 人体只吃内衬钝伤；后板耐久**未被扣** |
| 出口碰撞开/关 | 人体伤害**逐位相等**；只有 `dmgToArmor` 与后板耐久不同 |
| 非法输入 | 引擎抛出 `ammo/magazine not allowed` |
| 旧数据（无 side） | 仍按 plate→liner 串联，R15 不回归 |
| 头盔 | 正面/背面命中头部都经过头盔 |
