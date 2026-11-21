# R54 · gunsmith 护甲钝伤系数（BT%）覆盖度与方程反解留痕

host=HOMONAS user=MASTERJJ at=2026-11-04 09:17:50 +08:00

- 项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
- 目标：把 `data/armor-bt.json` 中 9 条 `material-fallback` 的钝伤系数用 gunsmith 站点口径反解补齐。
- 结论：**4 件可反解并已落库（`btSource=gunsmith-inverted`）；5 件 gunsmith 三套数据源均无该 id，按用户要求停止、保留兜底、不伪造。**
- R54b 追加：5 件改由 **tarkov.dev `properties.armorSlots[].bluntThroughput`** 覆盖；4 件反解中 3 件与上游完全一致，Hexgrid 上游无软甲槽 BT、无法用同一字段交叉校验。
- 未 git 提交；未重建 dist/release。

host=HOMONAS user=MASTERJJ at=2026-11-04 09:30:18 +08:00（R54b 追加段）

---

## 1. 数据源与访问方式（取证事实）

| 项 | 值 |
|---|---|
| 站点 | `https://tarkovgunsmith.com/` |
| 后端基址 | `https://api.tarkovgunsmith.com` |
| 抓取接口 | `GET /GetHelmetsDataSheetData`、`GET /GetArmorModulesData`、`GET /GetGetNewArmorStatSheetData` |
| 反解接口 | `POST /GetSingleShotBallisticSimulation` |
| 代理 | `http://127.0.0.1:7896`（先测 TCP 可达，再实际请求；四个请求均 HTTP 200） |
| TLS | 未关闭校验（标准 `urllib` 默认 cafile） |
| 本地后端 | `127.0.0.1:8796` 直连、不走代理（避开 8787–8795，8791 未触碰） |
| 抓取时间 | `2026-11-04T08:53:31+0800` |
| 行数 | helmets 178 / modules 456 / newArmor 340，合计 974 |
| 原始证据 | `docs/r54-armor-bt-inversion-evidence.json`（446257 B，含 `source_rows`/`coverage`/`sim_cache`/`inverted`/`regression_cache`/`regression`） |

前端 `main.js` 中实际调用的就是上面前三个 GET；`GetGetNewArmorStatSheetData` 带 `subRows`，是站点护甲计算器展平后的完整表，9 件缺失项只在它之外另有同族变体。

---

## 2. 覆盖度差集（关键前置）

9 条 `material-fallback` id 与三源全量 id 集合做差：

| id | 本地名称 | 命中 |
|---|---|---|
| `5fd4c474dd870108a754b241` | 5.11 Tactical Hexgrid | ✔ newArmor |
| `609e8540d5c319764c2bc2e9` | NFM THOR 隐蔽型强化防弹背心 | ✔ newArmor |
| `60a283193cb70855c43a381d` | NFM THOR 一体式携行具 | ✔ newArmor |
| `68a89146212dbbeead0d5636` | NFM THOR 隐蔽型（Head Eyes 变体） | ✔ newArmor |
| `69cbfe44897389c1870b2337` | Crye Precision AirFrame（瘟疫侵袭） | ✘ 0 命中 |
| `6a567ae55cbe811cbe0136a8` | Crye Precision AirFrame（慢工出烂活） | ✘ 0 命中 |
| `6a568dda1d89fcfb35010389` | MTEK STRIKE 防弹头盔（碳纤维） | ✘ 0 命中 |
| `6a576f2105af50743903b74c` | ANA Tactical M1 插板胸挂（数码丛林） | ✘ 0 命中 |
| `6a670ae11ab6ac490a0b9a99` | DevTac 浪人面罩（实验室安保） | ✘ 0 命中 |

- `covered_ids`（4）：`5fd4c474…`、`609e8540…`、`60a28319…`、`68a89146…`
- `missing_ids`（5）：`69cbfe44…`、`6a567ae5…`、`6a568dda…`、`6a576f21…`、`6a670ae1…`
- 证据：`coverage.hits` 中上述 5 个 id 对应空数组 `[]`，即 helmets / modules / newArmor 三源全无。

### 同族变体（仅作线索，**未**替代写入）

| 缺失项 | gunsmith 同族条目 | BT | 等级 | 耐久 |
|---|---|---|---|---|
| AirFrame 两变体（cls4/dur48） | Crye Precision AirFrame helmet (Tan) `5c17a7ed2e2216152142459c` | 0.1314 | 4 | 48 |
| MTEK STRIKE 碳纤维（cls4/dur40） | MTEK STRIKE Ballistic helmet (Coyote) `67597ceea35600b4c10cea86` | 0.1548 | 4 | 40 |
| ANA M1 数码丛林（本地 cls4/dur194） | ANA Tactical M1 plate carrier (Olive Drab) `5c0e722886f7740458316a57` | 0.33 | 2 | 194 |
| DevTac 浪人实验室安保（本地 cls4/dur180） | DevTac Ronin ballistic helmet `66bdc28a0b603c26902b2011` | 0.22 | 3 | 180 |

等级/耐久与本地条目并不全等（ANA、DevTac 等级不同），所以仅记录线索，不代入、不插值，避免把别款系数当真值。

### 替代来源建议（供后续单独取证）

1. **tarkov.dev GraphQL**：`items { id name bluntThroughput }`，与游戏内 `items.json` 同源，可按 id 精确取。
2. **SPT-AKI（Single Player Tarkov）服务端数据库** `items.json`：离线包，字段含 `BluntThroughput`。
3. **游戏本体 `Aki_Data/.../templates/items.json`**（若本机有安装）：最权威，直接读取。
4. **BSG 官方 item 页 / tarkov-market**：可交叉核对，但只有展示值、无接口时需逐件手抄。

> 按用户指令：这 5 件不在 gunsmith 库内，就此停止反解，保留本地 `material-fallback`（`bt=0.18`）作为兜底，`btSource` 不改。

---

## 3. 反解方法（方程反解，非网格盲扫）

口径与 `combat_sim.js` 的 gunsmith `Ballistics.cs` 实现一致：

```
FactorA    = (121 - 5000/(45 + 2*durPct)) * cls * 0.1
bluntScale = clamp(1 - 0.03*(FactorA - pen), 0.2, 1)
BluntDamage = D * BT * bluntScale        (单层、格挡分支)
=> BT = BluntDamage / (D * bluntScale)
```

固定条件：

- 弹药 5.45x39mm PS：`id=56dff3afd2720bba668b4567`，pen 28 / dmg 56 / armorDamage 40%。
- 部位：胸部（单层、无插板/内衬叠加，保证一次方程只有一个未知量）。
- 三档耐久：满耐久（100%）、50%、接近 0（1%，避免 0 除零）。

接口字段口径：`bluntDamageThroughput` 是**百分数**（站点显示 26 即 BT 0.26），POST 时须传 `bt*100`；首次误按小数传入曾导致结果小 100 倍（回归误差 0.495），已修正。

### 反解结果（4 件，三档全部自洽）

| 护甲 | id | 等级/耐久 | 满耐久 钝伤 / 缩放 / BT | 50% 钝伤 / 缩放 / BT | 近 0 钝伤 / 缩放 / BT | 取整 BT | spread |
|---|---|---|---|---|---|---|---|
| Hexgrid | `5fd4c474…` | 6 / 100 | 2.912 / 0.2 / 0.25999999 | 4.115961 / 0.28268966 / 0.25999998 | 14.56 / 1.0 / 0.25999998 | **0.26** | 2.40e-8 |
| THOR 隐蔽型 | `609e8540…` | 3 / 170 | 17.272766 / 0.93467347 / 0.33000001 | 18.480001 / 1.0 / 0.33000002 | 18.480001 / 1.0 / 0.33000002 | **0.33** | 1.24e-8 |
| THOR 一体式 | `60a28319…` | 3 / 466 | 18.843018 / 0.93467347 / 0.36000002 | 20.16 / 1.0 / 0.36 | 20.16 / 1.0 / 0.36 | **0.36** | 1.64e-8 |
| THOR 隐蔽型 Head Eyes | `68a89146…` | 3 / 170 | 同隐蔽型 | 同隐蔽型 | 同隐蔽型 | **0.33** | 1.24e-8 |

自洽性：

- 三档反解值与公布值的最大偏差 `1.44e-8`（浮点级）；档间 spread 均 ≤ 2.4e-8，远小于 1 点钝伤对应步进 `0.0892857`。
- 未出现取整踩边：接口返回 6 位小数，钝伤值未被整数化；`near-zero` 档 `bluntScale` 已顶到上限 1.0，此刻 BT 直接由 `BluntDamage/D` 决定，仍与另两档一致。
- 与公布值对照：`published` 0.25999999 / 0.33000001 / 0.36000001 / 0.33000001，取整落库 0.26 / 0.33 / 0.36 / 0.33。

落库字段（每件）：`bt`、`btSource="gunsmith-inverted"`、`btEvidence{endpoint,ammoId,ammo,armorClass,armorMaterial,maxDurability,published,inverted,selfConsistent,spread,samples[3]}`；`data/armor-bt.json` 的 `source.fetched_at=2026-11-04`，新增 `source.inversion` 记录口径。原 `material-fallback` 5 条保留，语义仍为兜底。

---

## 4. 159 条回归（同一反解流程回算）

对原有 `btSource=gunsmith` 的 159 条，用同一 POST 接口、同一弹药、同样三档耐久各取一次钝伤，再按上式反解：

| 指标 | 值 |
|---|---|
| 条目数 | 159 |
| 样本数 | 477（159 × 3 档） |
| 最大误差 | `6.413e-8` |
| 平均误差 | `4.430e-9` |
| 零钝伤样本 | 0（`regression.zeroBlunt = []`） |
| 1 点钝伤步进 | `1/(56*0.2) = 0.0892857` |

最大误差仅为 1 点钝伤步进的 `7.2e-7` 倍，即**远低于取整单位一个数量级**，说明反解口径与站点一致，未出现系统性偏差。逐条误差见 `regression.perItem`（每件含 `bt`、`maxError`、三档 `errors`）。

---

## 5. 视频锚点（多层二次衰减）

场景：马林杠杆步枪 + 五级自闭头面罩，第一层挡下 **8 点钝伤**；再加二级骷髅面罩后人体应只剩 **约 1 点**。

引擎输出（`tests/js/combat_sim_r19_8b_test.js` 的 `bluntMulti`/`bluntThree`）：

```
layer1 bluntOut = 8            (BT 0.08, bluntScale 1.0)
layer2 bluntIn  = 8  → bluntOut = 8 × 0.18 × 1.0 = 1.44
layer3 bluntIn  = 1.44 → bluntOut = 1.44 × 0.18 × 1.0 = 0.2592
dmgToPart = 1.44（视频显示 1 点，取整一致）
```

结论：**吻合**。8 → 1.44，取整为 1；继续叠加第三层降到 0.2592（取整 0），与“每加一层继续按该层 BT 二次衰减”的实测规律一致。`tests/test_r19_8b_rules.py::test_multilayer_blunt_chains_8_to_1_44` 断言 `1.0 <= dmgToPart <= 1.5`。

---

## 6. 前端确认（真实 Chrome，8796 端口）

- 截图：`docs/r54-armor-bt-frontend.png`（244743 B，2026-11-04 09:08:46）。
- 驱动方式：独立 headless Chrome（调试端口 9345）+ CDP `Page.captureScreenshot` 落盘；MCP 截图因插件 workspace roots 不含项目路径被拒，PowerShell `CopyFromScreen` 在非交互会话报 `The handle is invalid`，均改用 CDP。
- 场景：AK-74N + NFM THOR 隐蔽型强化防弹背心 + 5.45x39 HP（`56dff216d2720bbd668b4568`，dmg 76 / pen 9），三发胸部；界面列钝伤（被挡）`8.9 / 8.9 / 10.1`（底层值 `8.83 / 8.89 / 10.11`），击穿概率 `0.242 / 0.146 / 0.277`，命中时间 `92 / 185 / 277 ms`。
- 核算：图层提示 `钝伤基础 8.75/75.3`，即 `75.3 × 0.33 × 0.356 ≈ 8.84`，与 0.33 相符；若沿用旧兜底 0.26 应约 `6.98`，界面显然不是 0.26 的行为。

### 诚实限制（必须记录的数据流事实）

本次补的 4 件都是**护甲根条目**，而 `app.js` 的 `amSimArmorLayers` 在胸部模拟中只遍历 `aps` 插板（`armorBtOf(pid, pr.bt…)`）与软内衬（`b.bt` 优先，缺失才材质回退）；根条目 BT 仅在头盔/附加内层被直接消费。因此：

- THOR 隐蔽型的 `items.json` 内衬本就带 `bt:0.33`，与反解结果同值 → 根条目改值不改变界面输出；
- Hexgrid 根条目仍为 0.26，同样不进入胸部插板模拟的 BT 读取路径。

即：**根条目的 A/B 变化在胸部模拟里不可观察**，不能用“数值变了”来验收。截图证明的是当前链路输出的系数水平与 0.33 一致（而非旧 0.26），并且这次落库保证根条目自身取值为站点真值，供未来内衬/头盔路径消费。该限制不影响反解结论本身。

---

## 7. 测试

```
python -m pytest tests -q
1716 passed, 1 skipped in 102.89s (0:01:42)
```

- 基线 1713 passed / 1 skipped / 0 failed，本次新增 3 条 R54 测试，合计 1716 passed / 1 skipped / 0 failed（`+3`，无回退）。
- 新增文件 `tests/test_r54_armor_bt_inversion.py`：
  - `test_inverted_entries_have_self_consistent_evidence`（4 条证据齐全、三档 spread 与 published 偏差在浮点级）
  - `test_missing_entries_stay_as_material_fallback`（5 条仍为 `material-fallback`，bt 0.18 未被改动）
  - `test_known_bts_regress_within_one_damage_step`（159 条回归误差 < 1 点钝伤步进）

---

## 8. 复现

```powershell
cd "d:\personal\trae\02-塔科夫\eft-interactive-map"
python tools\r54_armor_bt_invert.py --refresh   # 重抓三源 + 三档反解 + 159 回归 + 写库/写证据
python tools\r54_armor_bt_invert.py --no-write  # 只算校验，不动 data/armor-bt.json
python -m pytest tests -q
```

脚本只依赖 Python 标准库；外网走 `127.0.0.1:7896`（可用 `R54_PROXY` 覆盖），本地地址不走代理。目标集合为 `material-fallback` ∪ `gunsmith-inverted`，因此重复运行结果稳定（首次曾因只取 `material-fallback` 导致二次运行目标为空，已修）。

---

# 9. R54b · 上游权威字段补 5 件 + 反解交叉校验

host=HOMONAS user=MASTERJJ at=2026-11-04 09:30:18 +08:00

## 9.1 数据源与访问结果

| 尝试 | 端点 | 结果 |
|---|---|---|
| tarkov.dev GraphQL | `POST https://api.tarkov.dev/graphql`（`items(ids:[...])`，浏览器 UA/Origin/Referer） | **HTTP 422** `{"errors":["GraphQL server unavailable. Try again later."]}`，GET query 同 422 |
| tarkov.dev 静态导出 | `GET https://json.tarkov.dev/regular/items` | **HTTP 200**，17345521 B，sha256 `ae3e723717422d573b14c9985986e18927fbd0771c391957aedb3f5e7cd754d7`，`checkedAt=2026-11-04T09:27:42+0800` |
| 项目离线快照 | `build-cache/tarkovdev/regular/items.json` | 2026-10-30 抓取，字段结构与 live 一致，用于离线复核（`--offline`） |
| 项目蒸馏快照 | `data/items.json` → `aps[].bt` | 与 live 的 `armorSlots[]` 逐件一致，作为第二重校验 |

代理 `127.0.0.1:7896` 实测 TCP 可达；未关闭 TLS 校验；本地文件直连。GraphQL 不可用时按 `静态导出 → 本地快照` 顺序回落，脚本 `tools/r54b_upstream_bt.py` 记录实际使用的端点与 sha256。

> 注意：`json.tarkov.dev` 正确路径是 `/regular/items`，带 `.json` 会 404（本次实测）。

## 9.2 字段口径（关键）

- 上游 armor 根字段 `properties.bluntThroughput` 在 9 件的实测值**全部为 0**，不能直接当 BT 用（会把钝伤算成 0）。
- 真正的逐部位系数在 `properties.armorSlots[].bluntThroughput`：
  - 头盔：`Helmet_top` / `Helmet_back` / `helmet_eyes` / `helmet_jaw` / `Helmet_ears`；
  - 软甲/胸挂：`Soft_armor_front` / `Soft_armor_back` / `Soft_armor_left` / `soft_armor_right`；
  - 纯插板槽（`Front_plate`/`Back_plate`/`Left_side_plate`/`Right_side_plate`）**没有**该字段，表示该层不含内建软甲。
- 同一件内所有带 BT 的槽取值一致（脚本对不一致会直接报错），取该一致值作为逐件系数。

## 9.3 5 件取值（已落库）

| id | 名称（上游 normalizedName） | 上游 armorSlots BT | 落库 bt | 上游 class / dur | 槽位 |
|---|---|---|---|---|---|
| `69cbfe44897389c1870b2337` | crye-precision-airframe-helmet-morbus-incorsio | 0.1314 | **0.1314** | 4 / 48 | Helmet_top, Helmet_back |
| `6a567ae55cbe811cbe0136a8` | crye-precision-airframe-helmet-botched | 0.1314 | **0.1314** | 4 / 48 | Helmet_top, Helmet_back |
| `6a568dda1d89fcfb35010389` | mtek-strike-ballistic-helmet-carbon-fiber | 0.1548 | **0.1548** | 4 / 40 | Helmet_top, Helmet_back |
| `6a576f2105af50743903b74c` | ana-tactical-m1-plate-carrier-emr | 0.33 | **0.33** | 4 / 194 | Soft_armor_front/back/left/right（插板槽无 BT） |
| `6a670ae11ab6ac490a0b9a99` | devtac-ronin-respirator-labs-security | 0.1548 | **0.1548** | 4 / 180 | Helmet_top, Helmet_back, helmet_eyes, helmet_jaw, Helmet_ears |

- `btSource` 统一为 `tarkov.dev:armorSlots.bluntThroughput`；`btEvidence` 记录端点、sha256、root BT=0、class/durability/material、全部槽位明细与 `inverted`（即落库值）。
- 兜底保留：每条新增 `btFallback=0.18`、`btFallbackSource="material-fallback"`；**这 5 个 id 不再命中兜底**。全库source计数：`gunsmith 159 / gunsmith-inverted 4 / tarkov.dev:armorSlots 5`，`material-fallback` 归零（168 条不变）。
- 合理性校验：上游 `class/durability/material` 与本地根字段一致（class 4；dur 48/48/40/194/180；Combined/Combined/Combined/Aramid/Combined），无异常。
- 第二重校验：`data/items.json` 的 `aps[].bt` 与上游 `armorSlots[].bluntThroughput` 逐件同值（AirFrame 0.1314、MTEK 0.1548、ANA M1 0.33、DevTac 0.1548）。

## 9.4 4 件反解结果的交叉校验

| id | R54 反解 | 上游 armorSlots BT | delta | 结论 |
|---|---|---|---|---|
| `609e8540…` THOR 隐蔽型 | 0.33 | 0.33 | 0.0 | **一致**（Soft_armor_* cls3/dur25/10） |
| `60a283193…` THOR 一体式 | 0.36 | 0.36 | 0.0 | **一致**（Soft_armor_*/Collar/Shoulder/Groin） |
| `68a891462…` THOR 头眼 | 0.33 | 0.33 | 0.0 | **一致** |
| `5fd4c474…` Hexgrid | 0.26 | —（无软甲槽） | — | **无法用同一字段校验**：上游该背心只有 `front_plate`/`back_plate` 两个插板槽，root BT=0，无内建软甲 BT |

结论：3 件逐位相等，**差异 0，远小于 0.01**；说明 `armorSlots.bluntThroughput` 与 gunsmith 的 per-item BT 是同一物理量（穿透后钝伤比例），R54 反解假设成立。Hexgrid 属于字段口径差异而非数值冲突：gunsmith 给整套背心一个 0.26 的根值，tarkov.dev 对纯插板背心不提供软层 BT（其防护由插入插板的 `bt` 承担）；前端 `amSimArmorLayers` 的胸部路径同样读插板/内衬 BT，因此该根值不参与胸部钝伤。

## 9.5 仍缺失的 id

**无。** 5 个目标 id 全部由上游 `armorSlots[].bluntThroughput` 覆盖；不需要估算，也没有用同族变体代入。
唯一“不可交叉校验”的是 Hexgrid 的 0.26（原因见 9.4，属纯插板背心的字段口径差异，不是缺失）。

## 9.6 复现与测试

```powershell
python tools\r54b_upstream_bt.py                 # 联网抓 live 导出 → 提取 → 写库/写证据
python tools\r54b_upstream_bt.py --offline       # 只用 build-cache 快照
python tools\r54b_upstream_bt.py --no-write      # 只校验不写 data/armor-bt.json
python -m pytest tests -q
```

- 新增脚本 `tools/r54b_upstream_bt.py`（标准库；GraphQL→静态导出→本地快照自动回落；记录 sha256/字节/时间）。
- 取证 `docs/r54b-upstream-bt-evidence.json`（targets 5 件全槽位、crossCheck 4 件判定、planned/written 变更）。
- 测试 `tests/test_r54_armor_bt_inversion.py` 扩到 5 条：反解自洽、gunsmith 覆盖度历史事实、5 件上游覆盖与兜底保留、全库无 material-fallback 命中、4 件交叉校验判定。
- `python -m pytest tests -q` → **1718 passed, 1 skipped, 0 failed**（R54 后基线 1716 + 新增 2 条，无回退）。
