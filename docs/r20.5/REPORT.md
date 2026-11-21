# R20.5 跳蚤市场价格自动更新与本地缓存 —— 交付报告

> 日期：2026-10-29。项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`。
> 结论分级：**代码已证实 / 测试已证实 / 静态推断 / 未验证**。
> 本轮未提交 Git、未推送；未改动任何业务数据（`data/items.json` 等 sha256 与 R20.3 基线逐字一致）。

---

## 1. 实际测试过的数据源与接口（全部经指定代理 `http://127.0.0.1:7896` 实测）

| # | 接口 | 实测结果 | 结论 |
|---|---|---|---|
| 1 | `https://api.tarkov.dev/graphql`（任务书指定的首选 GraphQL） | HTTP **422**，响应体 `{"errors":["GraphQL server unavailable. Try again later."]}`；POST / GET 均同 | **上游当前不可用**，不能作为数据源 |
| 2 | `https://json.tarkov.dev/regular/items` | HTTP **200**，17,303,281 B；两次抓取内容 sha256 不同（`0fcf8066…` / `bf1543e5…`，随行情变化） | **可用，本轮主数据源** |
| 3 | `https://json.tarkov.dev/regular/items?fields=id,lastLowPrice` | 200，但 `Content-Length` 仍是 17,303,238 → **上游忽略 `fields` 参数** | 按全量下载处理 |
| 4 | `https://json.tarkov.dev/pvp/items` | HTTP **404** | PvP 上游不可用 |
| 5 | `https://json.pvp.tarkov.dev/items` / `https://api.pvp.tarkov.dev/graphql` | 域名**无法解析**（URLError） | PvP 无可用通路 |
| 6 | `https://tarkov.dev/api` | HTTP 200（网页，非数据接口） | 仅作 API 文档参考 |

代理与网络规则：指定代理 7896 **端口开放且实测可用**（两站 200）；localhost/127.0.0.1 一律直连；
**未关闭 TLS 证书验证**；抓取器支持 `--no-proxy` 直连与 `--proxy` 覆盖。

> 未评估 Tarkov Market API（`tarkov-market.com/dev/api`）：它需要 Pro 订阅与 API Key，
> **未经授权不购买、不假定用户已有密钥**（任务书 §二）。

## 2. API 的真实价格字段及含义（实测 + 与项目既有映射交叉核对）

上游响应结构实测为 `{"data": {"items": {<id>: {...}}, ...约 10 个其它块}, "translations": {...}}`
——**物品表在 `data.items` 里**（直接对 `data` 计数会得到 10，这是本轮踩过的坑，已写进代码注释）。

| 上游字段 | 实测非空条数（5480 物品） | 含义 | 项目既有映射（已核实） |
|---|---|---|---|
| `lastLowPrice` | 3518 | **最近一次跳蚤市场最低挂单**（最低价，不是"实时扫描价"） | `items[].p.l` ← 项目既有"最新低价" |
| `avg24hPrice` | 3518 | **跳蚤 24 小时均价**（历史均价） | `items[].p.a` ← 项目既有 24h 均价 |
| `low24hPrice` | 2664 | 24 小时内最低价 | 项目未使用（本次新增进缓存） |
| `high24hPrice` | 2664 | 24 小时内最高价 | 项目未使用（本次新增进缓存） |
| `basePrice` | 全量 | **基础价**（与跳蚤价无关，独立口径） | `items[].p.b` ← 项目既有 BASE 档 |
| 逐条 `updatedAt` | **0** | 上游**不提供**逐条价格时间戳 | — |

**因此**：
- 缓存里的逐条 `fetchedAt` = **本地抓取时刻**（已在缓存 `fieldSemantics` 里写明，不是服务端时间）；
- **7 日均价不可得**（上游无该字段）→ 不做、不伪造；
- **实时挂单明细不可得**（该接口不返回挂单列表）→ 界面不出现"实时价"字样。

## 3. 是否支持 PvP / PvE

**只支持 PvE（`gameMode: "regular"`）**。PvP 上游两处均不可用（404 / 域名无法解析）。
缓存里写有 `gameMode` 字段与 `notAvailable` 明列" PvP 模式价格（无可用上游）"，
**不同模式的价格不会混用**（单测 T7 覆盖）。

## 4. 缓存文件结构与更新时间策略

文件：`data/flea-prices.json`（新增，**独立文件，不覆盖 `items.json`**，避免破坏既有 SHA-256 契约）。

```jsonc
{
  "schema": 1,
  "source": "https://json.tarkov.dev/regular/items",
  "sourceType": "tarkov.dev public JSON (items)",
  "gameMode": "regular",
  "lastSuccessAt": "2026-10-29T17:26:07+08:00",   // 最近一次成功更新（本机本地时间，带时区）
  "localDate": "2026-10-29",                       // 本机本地日期 → 当天判定的唯一依据
  "fieldSemantics": { "lastLowPrice": "跳蚤市场最近一次最低挂单（最新低价）", ... },
  "notAvailable": ["avg7dPrice（上游无 7 日均价字段）", "实时挂单列表…", "PvP 模式价格…"],
  "counts": { "itemsUpstream": 5480, "itemsWithPrice": 5101, "withLastLowPrice": 3518 },
  "items": { "<稳定物品ID>": { "lastLowPrice": 31111, "avg24hPrice": 69347,
                               "low24hPrice": 28600, "high24hPrice": 153333,
                               "basePrice": 18397, "fetchedAt": "2026-10-29T17:26:07+08:00" } }
}
```

**更新时间策略**（本地日期，不与 UTC 混用）：
1. 缓存不存在 → 启动后首次获取；
2. **当天（本机本地日期）已成功** → 直接用缓存，不再下载（实测第二次运行输出 `[skip] 当天（2026-10-29）已成功更新过`）；
3. 当天未更新 → **后台**抓取，**不阻塞**地图与枪械构建器；
4. 更新失败 → 记 `data/flea-prices.last-error.json`，**旧缓存逐字节保留**；
5. 更新成功 → 全量校验 → 转换 → **原子替换**（`.tmp` + `os.replace`），并清除上一轮失败记录；
6. 部分响应 / 无效 JSON / 价格越界 → **一律不写正式缓存**（越界值直接丢弃，不按 0 写入）；
7. 并发保护：锁文件按缓存派生（`data/flea-prices.json.lock`），同一缓存同时只有一个抓取进程。

## 5. 修改文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `tools/r20_fetch_prices.py` | **新增** | 抓取器：下载 → 校验 → 转换 → 原子替换；`--force/--dry-run/--proxy/--no-proxy/--mode`；失败只写错误记录、不动旧缓存 |
| `data/flea-prices.json` | **新增**（生成物） | 行情缓存，5101 条 / 678 KB |
| `tools/serve.py` | 修改 | 新增 `flea_price_status()` / `spawn_flea_refresh()`；`GET /api/prices`、`POST /api/prices/refresh`；启动时检查并**后台**刷新（非阻塞） |
| `app.js` | 修改 | 统一行情读取层 `fleaQuoteOf()` / `fleaState()` / `renderQuoteStatus()`；候选表新增「跳蚤最新」列；启动加载缓存（缺失即降级）；手动刷新按钮 |
| `index.html` | 修改 | 候选栏新增 `#gw-quote-status`（行情状态行）与 `#gw-quote-refresh`（刷新按钮） |
| `style.css` | 修改 | 行情状态行样式（fresh 绿 / stale 黄 / missing 灰） |
| `tests/test_r20_5_flea_prices.py` | **新增** | 17 个用例覆盖任务书 §七 的 10 类场景 |
| `tools/r205_accept.py` | **新增** | 真实浏览器验收脚本（13 项） |

**未改动**：`data/items.json`、`gunslots.json`、`gun-presets.json`、`meta.json`、全部旧测试、地图/任务/配装/模拟器。

## 6. 实际测试命令与结果

| 命令 | 结果 |
|---|---|
| `python tools/r20_fetch_prices.py --dry-run` | 收到 17,303,238 B → 校验通过（5480 → 5101，含最近低价 3518），不写盘 |
| `python tools/r20_fetch_prices.py` | 原子写入成功；**再次运行输出 `[skip] 当天已成功更新过`（不重复下载）** |
| `pytest tests/test_r20_5_flea_prices.py -q` | **17 passed**（含：首次触发、当天跳过、跨天重抓、失败保留旧缓存、无效响应不覆盖、越界价格丢弃、模式不混用、按 ID 建档、并发锁、离线三态） |
| `pytest tests/test_r20_5…r20_4…r20_3… -q` | **54 passed** |
| 枪械/服务相关旧测试（含 `test_fetch_data.py`、`test_r19_7_round.py`） | **206 passed / 5 failed**——5 项与 R20.1/R20.2/R20.3 基线**完全相同**的历史失败，**零新增回归** |
| `python tools/r205_accept.py --base http://127.0.0.1:8805` | **13/13 通过**（真实 Chrome + CDP） |

## 7. 浏览器验收结果（真实交互）

| 项 | 结果 |
|---|---|
| 行情状态行 | 「行情：今日快照 2026-10-29 17:26:07」，`data-state="fresh"` |
| 候选表列 | `配件│子槽│后坐力│人机│R+E/3│尺寸│重量│商人价│解锁│**跳蚤最新**│Δ重量│Δ价│FLEA价│状态`——**三种价格口径分列** |
| 过期缓存 | 模拟 `localDate=2020-01-01` → 显示「行情：过期快照（2020-01-01，2493 天前）」，枪械页照常可用 |
| 无缓存（离线） | 临时移走缓存 → 显示「行情：无缓存（仅历史均价）」；地图与枪械构建器**照常可用**；「跳蚤最新」列自动隐藏 |
| 手动刷新 | 按钮存在并进入「刷新中…」态（服务端后台抓取，不绕过校验与锁） |
| 控制台 | **0 错误** |
| 运行期外部请求 | **0**（全部 127.0.0.1；行情只在启动检查或手动刷新时由服务端抓取） |

截图：`docs/r20.5/screenshots/r205-fresh.png`、`r205-stale.png`、`r205-missing.png`；
结构化结果 `docs/r20.5/browser-accept.json`。

## 8. 行情更新失败时的处理方式（实证）

**实测发生过一次真实失败**：17:23:43 手动刷新时，上游返回了**仅含 1 个键的异常载荷**
（不是完整物品表）。处理链路全部按设计工作：

1. 数量校验（`items < 1000`）**拦下**该响应 → **不写正式缓存**；
2. 旧缓存**逐字节保留**（界面继续显示上一份有效快照）；
3. 失败原因写入 `data/flea-prices.last-error.json`；
4. 退出码非零，服务不受影响；
5. 随后改进：错误信息现在附带**上游顶层键 + 载荷样本**（便于判断限流/错误页/响应不完整）；
   **一次成功更新会清除上一轮失败记录**，避免界面长期显示已过期错误。

## 9. 当前显示的到底是哪种价格（口径澄清）

| 界面位置 | 数值 | 真实口径 |
|---|---|---|
| 候选表「**跳蚤最新**」 | 行情缓存 `lastLowPrice` | **最近一次跳蚤最低挂单**（今日/过期快照，**不是实时扫描价**，上游不提供实时挂单） |
| 候选表「**FLEA价**」 | `items.json` 的 `p.a` | **24 小时均价**（构建期快照，历史均价） |
| 候选表「**基础价/BASE**」 | `items.json` 的 `p.b` | **基础价**（与跳蚤价无关） |
| 枪械卡价格 | `items.json` 的 `p.a` | 24 小时均价（构建期快照） |

即：**没有任何一处显示"实时扫描价"**——该数据上游不提供。

## 10. 未实现的功能与数据源限制

| 项 | 原因 |
|---|---|
| 7 日均价（avg7d） | 上游无该字段 |
| 实时挂单 / 实时扫描价 | 该接口不返回挂单明细 |
| PvP 价格 | 两处 PvP 上游 404 / 域名无法解析 |
| 逐条服务端价格时间戳 | 上游不提供逐条 `updatedAt`（用本地抓取时刻代替，已注明） |
| 历史价格曲线 / 涨跌趋势 | 需要持续采样历史快照，本轮未做 |
| Tarkov Market API（更实时的行情） | 需 Pro 订阅与 API Key，**未经授权不购买、不假定存在** |
| 应用内直接联网取价 | 违反离线约束（2.3）与运行时无网络依赖要求；联网只发生在服务端抓取器里 |

## 11. 后续建议（待你决定）

1. **价格口径统一**：目前「FLEA价」仍取构建期 `items.json` 的均价，而「跳蚤最新」取当日缓存；
   若希望候选表默认展示当日均价，可让均价列也读缓存（有缓存时优先）——需你确认口径变更。
2. **采样与历史**：若要价格曲线，可让服务端每日把缓存快照归档到 `data/flea-history/`。
3. **PvP**：待有可用 PvP 上游或授权后，再按 `gameMode` 分文件扩展缓存。
4. `data/flea-prices.json` 建议纳入版本管理或加入 `.gitignore` 策略——**需要你决定**
   （当前它未提交；`data/` 下其它数据文件是纳入版本管理的）。


---

## 十二、R20.5c：用 rea 复核参考站 → 列表页与工作台再对齐（2026-10-29 续）

### 12.1 本轮用 rea MCP 实测到的参考站事实

- `capture_web_screenshot`：artifact sha256 `4b7fa4ea…`，1664×955，URL `https://db4tarkov.com/gun`。
- `inspect_web_page`：`completeness = policy_filtered`（DOM/console/scripts/resources 段被策略过滤），
  但 **accessibility 段可用**，提取到 **220 条去重标签**，把参考站能力完整列了出来。
- **关键结构事实（本轮据此改造）**：
  - 列表页每个口径分组的**最左侧是一块窄彩色口径块**（.300 / 5.8x42 / 5.56x45 / 5.45x39 / 6.8x51 /
    7.62x39 / 7.62x51 / 7.62x54R / .308 / .338 / 7.62x25），**右侧是连续密集的枪械卡网格**；
  - 枪械卡内容：枪图 + 右上角槽位数徽章 + **价格 + 重量 + 枪名**；
  - 顶部页签：`Caliber | Class | Table | Gun` + `Gunsmith / Streamer / Variant / Saved` +
    `lastPrice / avg24h / avg7d` + `only FleaLvl / only TraderLvl`；
  - 构建器顶部图标：`Save Gun` / `Remove all attachment on Gun 1` / `Rollback Gun 1` /
    `Show the old stats … before the active patch set`；
  - 构建器画布上的**槽位卡 = 图片 + 配件全名 + 人机角标 + 后坐角标 + 短名**；
  - 「Pick a mod」候选表列头实测为：`Expand | Recoil | Ergo | MOA | Vel | Size | Kg | R+E/3 | Price`，
    价格列是「跳蚤价 / 商人价 + 商人等级罗马数字 + 供货人数」双值；
  - 底部 `Buy | Ammo Drop | Sell` 三口径 + `ITEMS` 逐件清单（配件名 | 价 | 增减 | default）。
- 参考站**未抓取任何数据**（Flutter + Firebase + App Check，无公开许可）；本轮只参考结构与布局。

### 12.2 本地原有差距与本轮处置

| 参考站 | 本轮改造前的本地状态 | 本轮处置 |
|---|---|---|
| 左侧彩色口径块 + 密集网格 | 整行标题带（`.gw-browse-hd`）+ 150px 宽卡片，一行仅 8 个 | **已改**：分组改成 flex 行（左侧窄色块 + 右侧网格），卡片收窄到 104px，**实测一行 14 列**（改造前 8 列），横向利用率 +75% |
| 口径块配色 | 无 | **已做**：颜色来自 `data/caliber-groups.json` 的**真实弹药类别**（rifle/pistol_smg/shotgun/pdw/grenade），实测 rifle 15、pistol_smg 8、shotgun 3、pdw 2、grenade 2；判定不了的中性色 + 图例说明，不编造含义 |
| 列表页价格口径切换 | 只有工作台候选栏有 | **已做**：浏览页新增同一套 `PRICE_MODES` pills，**与工作台共用 `state.priceMode`**（不会出现两个页面口径不一致） |
| `Remove all attachment` | 无 | **已做**：工作台新增「清空配件」 |
| `Rollback Gun 1` | 无 | **已做**：工作台新增「回退」（内存态快照栈，最多 30 步；换枪即清空，不写本地存储） |
| `MOA` / `Vel` 两列 | 无 | **不做**：`items.json` 的 `mod` 只有 `e`/`r`/`a`，**无单件 MOA、无单件初速**；本地只在枪级有 `moa`（`gunslots.json`）。没有数据不编造（本地已有注释记录该缺口） |
| `Ammo Drop` 口径 | 只有 改装件/含枪/回收 | **暂不做**：需要弹药逐件价格口径，与 R20.5 的行情缓存口径要一起定，留待下一轮 |
| `avg7d` | 无 | **不做**：上游无该字段 |
| `Silent / Loud` | 已禁用并标注「无数据」 | 维持（本地无消音标记字段） |
| Pareto 前沿图 / FORGE 生成器 | 左栏是 FORGE 自动配枪 UI，无前沿图 | **未做**：属组合优化器 + 产品形态问题（见 §12.4） |

### 12.3 本轮改动文件与验证

**改动（3 个既有文件）**
- `app.js`：`renderPricePills()` 抽成通用渲染（浏览页 + 工作台共用口径与状态）；
  新增 `ensureCaliberGroups / caliberCatOf / gwGroupColorKey / renderCalLegend`（口径配色，懒加载 4 KB 本地 JSON，失败只影响配色）；
  浏览分组由「标题带」改为「左侧色块 + 网格」；
  新增 `gunPushHistory / gunUndo / clearGunAll / syncGunHistoryUi`（清空与回退）。
- `index.html`：浏览页新增 `#gw-browseprices`（价格口径）与 `#gw-callegend`（配色图例）；
  工作台 LOAD VARIANT 行新增 `#gw-clearall`、`#gw-undo`。
- `style.css`：新增口径色块/图例/密集网格样式（追加在文件末尾，优先级最高）。

**新增（3 个文件）**
- `tools/r205c_accept.py`（真实浏览器验收，11 项）
- `tests/test_r20_5c_browse_parity.py`（21 项）
- `docs/r20.5/browser-accept.r20.5c.json`（验收产物）

**验证结果**

| 项 | 结果 |
|---|---|
| 真实浏览器验收 `tools/r205c_accept.py` | **11/11 通过**（色块 30 个、配色按真实类别、5.56x45=rifle、网格 14 列、切换口径价格 79,045₽→63,453₽、清空 7→0、回退 0→7、控制台 0 错、外部请求 0） |
| 新增 pytest `test_r20_5c_browse_parity.py` | **21 passed**（与 R20.3/4/5 合计 **75 passed**） |
| 枪械相关旧测试（9 个文件） | **66 passed / 5 failed**——5 项与 R20.1、R20.2 基线**完全相同**的历史失败，**零新增回归** |
| 复跑 `tools/r204_accept.py` | **29/29 通过**（无回归） |
| 复跑 `tools/r205_accept.py` | **13/13 通过**（无回归） |
| 业务数据 sha256 | `items.json ac81f0aa…` / `gunslots.json 29b987b3…` / `gun-presets.json 64e29bb5…`，**与 R20.3 基线逐字一致**（本轮未触碰数据） |

### 12.4 仍未解决 / 需要你定夺

1. **Pareto 前沿 + FORGE 生成器**：参考站左栏是「生成器」，能一键算出 3D Pareto 最优解并画出前沿图。
   本地左栏是 FORGE 自动配枪 UI（有约束条件与方案列表），但**没有前沿图**。
   这是当前与参考站**最大的结构性差距**，也是唯一需要新增算法（组合优化）的一项——工作量与产品形态都需要你先定。
2. **`Ammo Drop` 口径**：参考站 Buy / Ammo Drop / Sell 三档，本地只有 改装件/含枪/回收。
   建议与 R20.5 的行情缓存口径一起定（弹匣内弹药按哪一档计价）。
3. **候选表 `MOA` / `Vel` 两列**：需要上游单件 MOA / 初速数据，当前本地没有；
   若要补，需先确认数据来源与许可（与 R20 决策材料 D2 同类问题）。
4. **画布槽位卡短名**：参考站每张卡下方有配件短名（如 `USGI A2`、`STANAG`）。
   本地 `items[].sn` 是**翻译键**不是短名，若要显示只能用启发式截断，可能误导——暂不做。
5. **中栏顺序**：参考站把属性条放在画布**上方**，本地在下方；但 `test_r19_5_round.py` /
   `test_r19_6_round.py` 把「LOAD VARIANT→画布→属性条→整枪属性→隐藏属性」锁为不变量，
   **本轮未改**（改了就破坏旧测试）。

### 12.5 流程说明

- 本轮开始时已按约定**关闭上一轮后台进程**（8805 服务）；本轮服务在 **8806**，
  验收结束后**保持运行供你测试**：`http://127.0.0.1:8806/`。
- 下一轮开始时会关闭它。未提交 Git、未推送。
