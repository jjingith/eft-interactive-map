# db4tarkov.com/market 价格链路取证（R39-b）

> 取证时间：2026-11-08 10:50–11:35（北京时间，UTC+08:00），对应 UTC 02:50–03:35
> 取证对象：`https://db4tarkov.com/market`
> 方式：真实 Chrome + CDP 抓包（新 profile）/ 直接请求接口 / `main.dart.js` 静态分析 / craft-anything 浏览器工具
> 纪律：只读，不改本项目任何代码；请求频率受控（快照全量下载 4 次、HEAD 采样 6 次、上游单物品接口 2 次、路径探测 9 次）
> 标注约定：**【实测】**=本次抓包/请求直接观测到；**【推断】**=依据写明，未直接观测

---

## 0. 结论速览

**它是不是"服务器上定时拉取上游数据、存到自己的库里，再对外提供"？——是，但更准确的说法是"周期性生成静态 JSON 快照 + 对象存储 + CDN 托管"，不是实时透传，也不是带历史查询能力的行情数据库。**

| 问题 | 结论 | 依据等级 |
|---|---|---|
| 是否定时拉取上游并自存 | **是**：`/json/realtime/market_*.json` 是预先落盘的整表快照，ETag 换代可观测；后端确有 Supabase 原始库 + Cloudflare R2 对象库 + GitHub Actions 定时任务 | 实测（HTTP+JS 静态证据）|
| 更新周期 | **约 40–70 分钟一代**（本轮观测到 02:56→03:01 之间换代；上一轮实测两代间隔 ≈70 分钟）。上游本身是 **10 分钟一批** | 实测 |
| 上游是谁 | `dev_*` = **tarkov.dev**（PvP/PvE/Season 公开 JSON）；`tm_*` = **tarkov-market.com**（其独有字段 `avg7daysPrice`）。默认展示源是 **tarkov-market**（`marketPriceSource=3`） | dev 实测；tm 实测字段 + 推断站点 |
| 是否实时透传 | **不是**。/market 首屏拿到的是整表快照（数据截止时间比当前时间早 40–50 分钟）；无 WebSocket / SSE / 轮询 | 实测 |
| 有历史价格库吗 | **没有对外接口**。日期快照路径与 `/json/history/*` 均 404（带合法 UA+Origin）。历史曲线靠**浏览器直连 `json.tarkov.dev/pvp-season/prices/{id}`**，那是上游自己的序列 | 实测 |

一句话：**db4 做的是"把别人的公开行情抄成自己的静态文件，按小时级刷新，用 CDN 分发"**；页面上的"实时感"来自"前端缓存 + 少量上游直连"，而不是自家实时链路。

---

## 1. 页面实际请求了什么

### 1.1 首屏请求清单（全新 profile，空缓存，120 s 观察窗，共 44 个请求）

时间以导航为 0 点。

| t | 方法 | URL | 类型 | 状态 | 说明 |
|---|---|---|---|---|---|
| 0 | GET | `https://db4tarkov.com/market` | document | 200 | Flutter Web 入口 |
| ~0 | GET | `/main.dart.js`、`/flutter.js`、`/flutter_bootstrap.js`、`/canvaskit/chromium/canvaskit.{js,wasm}`、`/assets/FontManifest.json`、字体、图标、`/manifest.json`、`/favicon.png` | script/wasm/font | 200 | 前端运行时 |
| ~254 ms | GET | `https://db4tarkov.com/version.json?v=<ms>` | fetch | 200 | 站点版本探测（每次加载都发） |
| 5.1 s | GET | `https://eft-cdn.dvcstudiox.workers.dev/json/core/changes.json` | fetch | 200 | 物品属性补丁（按游戏版本 `1.1.0.0.46624` 组织） |
| **5.2 s** | GET | `https://eft-cdn.dvcstudiox.workers.dev/json/realtime/market_dev_ss.json` | fetch | 200 | **价格主表 A：tarkov.dev 口径（Season）** |
| **5.6 s** | GET | `https://eft-cdn.dvcstudiox.workers.dev/json/realtime/market_tm_ss.json` | fetch | 200 | **价格主表 B：tarkov-market 口径（Season）** |
| 10.7 s | GET | `https://json.tarkov.dev/pvp-season/traders` | fetch | 200 | **直连上游**：赛季模式交易员 |
| 12–30 s | GET | Firebase（`app/webConfig`、`installations`、`remoteconfig`）、reCAPTCHA、gtag/GA、Cloudflare Insights/RUM | fetch/script | 200/部分失败 | 统计与配置，与价格无关 |

第二次抓包（craft-anything 观察窗，129 条请求）额外观测到：

| 次数 | URL | 说明 |
|---|---|---|
| 48（=24 个物品 × 2） | `https://json.tarkov.dev/pvp-season/prices/{itemId}` | **直连上游的逐物品价格序列**，用于列表内的走势/历史 |

> 该逐物品请求在不同抓包里出现与否不稳定（第一次 120 s 抓包未出现，第二次出现 48 次），属按视口渲染的按需加载，**不影响"主表来自 db4 快照"的判定**。

- WebSocket / SSE：**【实测】0**（CDP `Network.webSocketCreated` 0 条；craft-anything `websockets.connections=[]`）。
- Service Worker：站点有 `icon_cache_sw.js`，但未拦截价格请求。
- Supabase：前端没有直接调用 Supabase REST（0 条），说明 Supabase 只在**写入/管理侧**使用（见 §6）。

### 1.2 为什么"重载"看不到价格请求（解释上一轮异常）

用已有缓存的老 profile 重载 `/market`，75 s 内只有 `version.json`，没有 `market_*`。原因：Flutter 端把整表写入本地存储（`cache_market_dev_ss` 等 key）+ ETag 版本比对，命中本地缓存就不再发请求。**换成全新 profile 才看到首屏真实请求集合。**

---

## 2. 响应结构与价格口径

### 2.1 `market_dev_ss.json`（tarkov.dev 口径）

- 体积 **381,634 B**，物品 **3412** 条，字段只有 4 个：

```json
{"data":{"items":[
  {"id":"5caf1041ae92157c28402e3f","lastLowPrice":66666,"avg24hPrice":50150.64,"updated":"2026-11-08T02:48:07.000Z"}
]}}
```

| 字段 | 口径 |
|---|---|
| `lastLowPrice` | 最近一次的最低挂单价（"最低价"） |
| `avg24hPrice` | 24 小时均价（历史均价，**不是实时价**） |
| `updated` | 上游该物品价格批次的更新时间（UTC，秒级） |

注意：文件**没有** `low24hPrice`/`high24hPrice`/`basePrice`/挂单数/交易员信息；文件名里的 `dev` 指 tarkov.dev，`ss` 指 Season 模式。同类还有 `market_dev_pvp.json`、`market_dev_pve.json`（JS 里三套齐全）。

### 2.2 `market_tm_ss.json`（tarkov-market 口径）

- 体积 **352,571 B**，物品 **3096** 条，**顶层是数组**：

```json
[{"id":"5caf1041ae92157c28402e3f","lastLowPrice":66666,"avg7daysPrice":50150.64,"updated":"2026-11-08T02:48:07.000Z"}]
```

| 字段 | 口径 |
|---|---|
| `lastLowPrice` | 最低挂单价 |
| `avg7daysPrice` | **7 日均价**（tarkov.dev 不提供，这是 tarkov-market 的独有口径） |
| `updated` | 该物品最近一次价格更新时间（逐条不同，跨度可达 2 周） |

### 2.3 价格在界面上怎么用（来自 `main.dart.js` 静态分析）

- 默认价格源 = **tarkov-market**：`"marketPriceSource",3`（`main.dart.js` L286561），`if (marketPriceSource===3) → tarkov-market，否则 tarkov.dev`（L163163）；UI 标签为 `"PVP tarkov-market"` / `"PVE tarkov-market"` / `"Season tarkov-market"`（L100357/100408/100458）。
- "均价"只有一个展示槽：`avg24hPrice` 先填，若为空再用 `avg7daysPrice` 补（`if avg7daysPrice!=null && k.d==null → k.d=avg7daysPrice`，L100369/100420/100470）。因此：
  - 选 tarkov.dev → 显示 **24h 均价**；
  - 选 tarkov-market（默认）→ 显示 **7 日均价**；
  - "最低价"两源都是 `lastLowPrice`。
- 页面**不发**"最高价/挂单数/交易员报价"，所以"最低/平均"有，"最高/挂单数"没有（历史接口里才有挂单数）。

### 2.4 `json/core/changes.json`

```json
{"patchChanges":{"1.1.0.0.46624":{"5645bc214bdc2d363b8b4571":{"id":"...","properties":{"ricochetX":0.8,"ricochetY":0.3,"ricochetZ":70}}}},
 "patchNewItems":{...}}
```

按游戏版本号的物品属性补丁，不含任何时间戳 / 价格历史，**不是价格数据源**。

---

## 3. 更新机制判定

### 3.1 HTTP 缓存头（实测）

`GET https://eft-cdn.dvcstudiox.workers.dev/json/realtime/market_dev_ss.json`：

```
HTTP/1.1 200 OK
Date: Sun, 08 Nov 2026 03:06:06 GMT
Content-Type: application/json
Content-Length: 381634
Access-Control-Allow-Origin: *
Access-Control-Expose-Headers: ETag
Cache-Control: no-cache
ETag: "9c0644db0d984edd5b12a6801a01ad08"
Server: cloudflare
CF-RAY: a5715c1d2e24d509-HKG
alt-svc: h3=":443"; ma=86400
```

判定：

- **无 `Last-Modified`、无 `Age`、无 `CF-Cache-Status`** → Cloudflare 边缘**没有缓存**这个对象（动态回源 Worker），Worker 只是把 R2/KV 里的文件吐出来。
- `Cache-Control: no-cache` → 浏览器允许存但每次必须"校验"；配合 ETag 做条件请求。
- **Worker 不支持条件请求**：带 `If-None-Match`（值与当前 ETag 完全一致）仍返回 **200 + 全量 381 KB**，**不返回 304**（实测两次）。前端 `fetchWithEtag` 设计的 304 分支对这个 Worker 实际走不到，ETag 被当作"版本号"而非"免下载凭证"。
- CORS 全开（`Access-Control-Allow-Origin: *`），任何站点都能直接读这两张表——这也是它"容易被抄"的原因。

### 3.2 静态快照路径与历史接口探测（实测，均带浏览器 UA + `Origin: https://db4tarkov.com`）

| 路径 | 结果 | 含义 |
|---|---|---|
| `/json/realtime/market_dev_ss.json` | 200 | 现役整表快照 |
| `/json/realtime/market_dev_ss-2026-11-08.json` | **404** | **没有**按日期归档 |
| `/json/realtime/2026-11-08/market_dev_ss.json` | **404** | 同上 |
| `/json/history/market_dev_pvp.json` | **404** | **没有**历史价格序列接口 |
| `/json/history/market_dev_pvp/2026-11-07.json` | **404** | 同上 |
| `/json/realtime/index.json` | 404 | 没有索引 |
| `/json/`（不带 UA/Origin 时 403） | 403 | 根路径有鉴权门 |

结论：**取不到任意日期快照** → 对外不是"自建历史库"，只有"当前版本覆盖写"的静态文件。历史曲线是浏览器**直连上游** `json.tarkov.dev`（见 §3.4）。

### 3.3 无推送、无轮询（实测）

- 120 s 首屏抓包：`market_*` 各 **1 次**，无重复。
- 90 s craft-anything 观察：WebSocket 连接 **0**、帧 **0**；请求里没有任何定时器式重复。
- 结论：**没有 WebSocket / SSE / 轮询**，价格只随页面加载（或本地缓存失效）拉取。

### 3.4 上游逐物品序列（实测）

`GET https://json.tarkov.dev/pvp-season/prices/5caf1041ae92157c28402e3f`：

```json
{"data":[
 {"priceMin":8975,"price":17234,"offerCountMin":1,"offerCount":1,"timestamp":1786406400000},
 {"priceMin":30000,"price":30000,"offerCountMin":1,"offerCount":1,"timestamp":1786579200000}
]}
```

- 时间戳先按 **1 天**步进（86400000 ms），临近当前时间改为 **2 小时**步进；`price`=均价、`priceMin`=最低价、`offerCount`=挂单数。
- 响应头：`Cache-Control: max-age=691200`（**8 天**）、`CF-Cache-Status: HIT`、`Last-Modified: 02:28:35Z`、带 ETag。
- 即：**历史曲线是上游的 CDN 缓存**，db4 没有自建历史库。

### 3.5 换代粒度：两代快照逐项对比（实测，决定性证据）

同一批 3412 个物品，取两代文件：

| 代 | 抓取时间(UTC) | ETag | 物品数 | `max(updated)` |
|---|---|---|---|---|
| A | 02:56 | `"63d2c2e3…"` | 3412 | **02:08:06** |
| B | 03:06 | `"9c0644db…"` | 3412 | **02:48:07** |

逐项 diff：

| 指标 | 数值 | 解读 |
|---|---|---|
| `lastLowPrice` 变化 | **208 / 3412 = 6.1%** | 一次换代只有 6% 的最低挂单变了 |
| `updated` 变化 | **2182 / 3412 = 63.9%** | 上游按批刷新时间戳（哪怕价格没变） |
| 增删物品 | 0 / 0 | 物品集合稳定 |

判定：**是"整批换一代"而不是"连续微变"**——同一代内所有物品的价格是同一时刻的切片；换代时一次性替换。且 A 的数据截止在 02:08（比 A 的抓取时间早 48 分钟）、B 截止 02:48（比 B 早 18 分钟），**说明快照落后上游一个批次以上**。

### 3.6 ETag 采样（低频率，5 分钟一次，共 25 分钟）

对 `market_dev_ss.json` / `market_tm_ss.json` 各做 6 次 HEAD（03:01:40 → 03:26:44），两代 ETag **全程未变**；首末两次各下一份全量，逐物品比对：

| 表 | ETag（25 分钟内） | 最低价变化 | 未变 |
|---|---|---|---|
| `market_dev_ss` | `"9c0644db…"` 恒定 | **0 / 3412** | 3412 |
| `market_tm_ss` | `"4de2962c…"` 恒定 | **0 / 3051**（3051 条有报价） | 3051 |

结合 §3.5（02:56→03:01 刚发生一次换代）：**换代间隔大于 25 分钟**，且换代之间数据完全冻结。三条独立时间点（A 代、B 代、25 分钟观察窗）都指向"整批替换、非连续微变"。

---

## 4. 上游来源推断

### 4.1 `dev_*` = tarkov.dev （实测）

- 字段命名与 `json.tarkov.dev` 官方 JSON 完全一致：`lastLowPrice` / `avg24hPrice` / `updated`。
- 站点**直接**请求 `https://json.tarkov.dev/pvp-season/traders`（实测 200）与 `pvp-season/prices/{id}`（实测 200），同源关系无需推断。
- 结论：**实测同源**。

### 4.2 `tm_*` = tarkov-market.com （推断，依据充分）

依据：

1. `avg7daysPrice` 是 tarkov-market 公开 API 的独有字段，tarkov.dev 不提供；
2. `main.dart.js` 里该数据源的 UI 标签就叫 `"PVP tarkov-market"` / `"PVE tarkov-market"` / `"Season tarkov-market"`；
3. `marketPriceSource` 取值 3 时映射为字符串 `"tarkov-market"`；
4. 逐条 `updated` 跨度达 2 周（与 tarkov-market 的逐物品更新模型一致），而 db4 自己重算会写成同一个抓取时间。

未证实部分：tm 快照具体从哪个端点、以什么频率抄来（是 tarkov-market 官方 API，还是第三方镜像），**没有直接证据**，标为推断。

### 4.3 不是官方跳蚤抓取、不是社区提交 （推断）

- 无挂单明细、无玩家昵称/ID、无交易员报价、无成交流水；
- 只有聚合值（最低价/均价）+ 逐物品时间；
- 两张表的 `id` 都是 tarkov.dev / tarkov-market 的物品 UUID，不是玩家提交的结构。

若要自建抓蚤引擎，必须能解释挂单级数据，这里完全没有。

---

## 5. 存储与架构线索

### 5.1 分发层（实测）

| 项 | 观测 |
|---|---|
| CDN | Cloudflare（`Server: cloudflare`、`CF-RAY: …-HKG`） |
| 数据域 | `eft-cdn.dvcstudiox.workers.dev`（Cloudflare **Worker**，不是 R2 公开域） |
| 资产域 | `cdn.db4tarkov.com`（R2 桶，路径 `/icon/`、`/image512/`、`/grid/`、`/task/`、`/webp/map/`） |
| 其他 Worker | `eft-assets.dvcstudiox.workers.dev`、`eft-gun-preview.dvcstudiox.workers.dev` |
| 边缘缓存 | 价格 JSON **无** `CF-Cache-Status`（=动态）；上游历史接口有 `HIT` |

### 5.2 写入侧（实测：`main.dart.js` 内的管理端代码字符串）

这是回答"是不是自存"的关键——站点自己的管理界面里写着它的数据管线：

| 位置 | 原文（摘录） | 含义 |
|---|---|---|
| L149554 | `[saveChanges] changes.json uploaded to R2 (… versions, itemsVer: …)` | 管理端把 JSON **上传到 R2** |
| L149650 / L149669 | `R2 items upload …` / `R2 combo … upload …` | 物品/组合数据同样上传 R2 |
| L150258 | `pub run tools/fetch_items_json.dart` | 用 **Dart 工具**从 `json.tarkov.dev` 生成 `items_json.dart` |
| L150295 | `Download raw từ Supabase → upload lên R2 json/core/items.json với X-Items-Version metadata` | **Supabase 原始库 → R2**，并写版本元数据 |
| L150277 | `Kích hoạt GitHub Actions icon-sync → … từ tarkov.dev lên R2 (cdn.db4tarkov.com) ngay, không đợi cron 06:45 UTC. FETCH ITEMS tự gọi cái này khi có item mới.` | **GitHub Actions 定时任务（cron 06:45 UTC）** 从 tarkov.dev 同步资产到 R2；有新物品时手动触发 |
| L150225 | `gh workflow run icon-sync.yml` | 工作流名字与触发方式 |
| L38842 | `https://gacxmpsnkkizmzmcimlh.supabase.co`（另有 anon key，已不摘录） | Supabase 项目（原始数据 + 快照存储） |
| L286561 / L163163 | `marketPriceSource` 默认 3 → `tarkov-market` | 前端默认数据源 |

因此后端形态是：

```
上游公开行情 (json.tarkov.dev / tarkov-market)
        │  定时 / 手动触发（GitHub Actions cron、Dart tools、管理端按钮）
        ▼
Supabase（原始数据/快照）──→ Cloudflare R2（json/… 文件 + X-Items-Version 元数据）
        │
        ▼
Cloudflare Worker（eft-cdn.dvcstudiox.workers.dev）→ 浏览器
```

- 这是**实打实的"服务端拉取 + 自存 + 分发"**，只是"自存"是对象存储/托管数据库，而不是自建行情服务；
- 但它**没有**对外的历史查询 API，也**没有**逐笔成交。

### 5.3 生成周期（实测/推断）

| 证据 | 观测 |
|---|---|
| 快照换代 | 02:55（ETag `63d2…`）→ 03:01（ETag `9c06…`），5 分钟内发生一次 |
| 换代后数据截止 | A 代 `max(updated)=02:08`，B 代 `02:48` |
| 数据年龄（03:00 时点） | dev 表中位数 **86.6 分钟**、P10 56.6 分钟；tm 表中位数 103 分钟 |
| 25 分钟低频采样 | 03:01–03:26 共 6 次 HEAD，ETag 恒定、3412 条最低价 **0 变化** → 换代间隔 **>25 分钟**（§10） |
| 上一轮实测 | dev_pvp 快照两代间隔 **≈70 分钟**（15:00–15:01Z 换代，前一代 ≈13:50Z） |

判定：**换代周期约 40–70 分钟，非严格等间隔**；上游每 10 分钟刷新一批，db4 落后上游 ≥1 个批次。**不是 10 分钟级，更不是秒级。**

---

## 6. 结论：是不是"服务端定时拉取 + 自存"

**是。**证据链：

1. **文件是可整体替换的快照**：3412 条一张表，一次换代 208 条最低价变化、2182 条 `updated` 变化，集合不变（§3.5）。
2. **快照有明显的数据滞后**：换代文件的数据截止时间比抓取时间早 18–48 分钟（§3.5/§5.3）→ 内容是"某时刻抄下来的"，不是"当次查询算出来的"。
3. **分发层不会算数**：Worker 只吐整文件、`Content-Length` 固定、不支持 304、无 `CF-Cache-Status`（§3.1）→ 没有查询/聚合逻辑，只是文件托管。
4. **写入侧有定时任务和对象库**：管理端代码明确写着 Supabase 原始库、R2 上传、`gh workflow run icon-sync.yml`、`cron 06:45 UTC`（§5.2）。
5. **无推送无轮询**：0 WS / 0 SSE / 单次拉取（§3.3）→ 更新只能靠"重新发布文件"。
6. **页面用本地缓存 + ETag 做版本控制**：同 profile 重载不发请求（§1.2）→ 客户端把快照当"版本化资源"，符合定时发布模型。

**反证 / 需要写明的边界：**

- **不是全部经自家服务器**：页面会直连 `json.tarkov.dev/pvp-season/prices/{id}`（48 次/视口）和 `pvp-season/traders`——这部分"实时"绕过了 db4，直接来自上游。
- **不是完整历史库**：任意日期快照、`/json/history/*` 全部 404（§3.2），历史序列由上游 CDN（8 天 `max-age`）提供。
- **不是自建抓蚤/社区提交**：没有挂单级数据（§4.3）。
- **"自存"是 BaaS + 对象存储**：Supabase + R2，而非自建数据库服务；`updated` 也原样保留上游时间，没有重算。

一句话给结论：**db4tarkov 的 market = "第三方公开行情的整表快照，~1 小时一次发布会，Cloudflare 分发；页面缓存 + 少量上游直连制造实时感"。**

---

## 7. 如果我们自己做实时行情，这套做法哪些可借鉴

结合本项目现状（离线 Python + 原生 JS，运行期不联网，构建期快照 `data/flea-prices.json` / `data/flea-levels.json`）：

### 7.1 可直接借鉴

1. **两层数据模型**（最值得学）：整表快照负责"列表/排序/搜索"，单物品历史序列负责"详情/走势"，两者解耦。我们不必给 5480 个物品都存历史，只给详情页按需带一条序列即可。
2. **快照要自证新鲜度**：现在我们的 `flea-prices.json` 只写 `lastSuccessAt` + `fetchedAt`，**丢掉了上游逐条 `updated`**。建议补 `sourceUpdatedMax`（本次抓取里 `max(updated)`）与 `generatedAt`，前端就能显示"数据截止 xx:xx"，用户不会误以为是实时。
3. **按模式拆文件**：db4 拆成 `dev/tm × pvp/pve/ss`；我们只需要 `pvp` / `pve` 两套（正好对应上游 `regular` / `pve`），单文件更小、缓存更友好，也避免上一轮那种"regular=PvE"的口径混淆。
4. **版本化 + 条件请求**：给 `data/flea-prices.json` 生成一个内容哈希（或 ETag 文件），前端在线刷新时带 `If-None-Match`。注意：**要真支持 304**（db4 的 Worker 没做，导致每次全量下载 381 KB，这是它的短板）。
5. **字段级回退**：一个"均价"槽位，`avg24h` 缺失时退回 `avg7days`（db4 L100369 的做法）。我们只接 tarkov.dev 时没有 7 日口径，应该**明确显示"无 7 日均价"**而不是拿别的字段冒充（`r20_fetch_prices.py` 已经这样做了，保持）。
6. **定时任务放构建期**：db4 用 GitHub Actions cron；我们可以在发布流水线里跑 `tools/r20_fetch_prices.py`，产出静态 JSON 提交/发布，**运行期依旧完全离线**，与项目约束不冲突。
7. **数据年龄做成 UI 元素**：db4 的做法会让用户看到价格却不显示"多久前"。我们可以做得更好——显示"最近更新：xx:xx（上游 xx:xx）"。

### 7.2 不建议照搬

1. **不要抄它的整表体积**：381 KB × 4 个变体，移动端首屏成本高。我们只发布自己需要的字段（`b/l/a/lo/hi`），体积可控。
2. **不要在前端逐物品拉上游**：db4 一次视口 48 个请求，是它"实时感"的来源，但对离线项目是灾难（也容易被上游限流）。
3. **不要自建 Supabase/R2 那套**：我们一个静态文件 + 现有 `tools/serve.py` 就够；确有需要时再上对象存储。
4. **不要做"伪实时"**：如果快照是 1 小时前的，就应该写 1 小时前。db4 的 `no-cache` + 全量下载其实是成本，不是本事。

### 7.3 建议的落地方案（不改运行期约束）

| 步骤 | 内容 |
|---|---|
| 1 | 构建期：`r20_fetch_prices.py` 同时保留上游 `updated`，写 `meta.generatedAt`、`meta.sourceUpdatedMax` |
| 2 | 发布：生成 `data/flea-prices.pvp.json` / `data/flea-prices.pve.json` + `data/flea-prices.pvp.etag.txt` |
| 3 | 运行期：优先读本地快照；如用户手动点"刷新"，带 `If-None-Match` 取一次（支持 304 的静态服务器我们可控） |
| 4 | UI：显示数据截止时间与来源；均价缺失时不回退到不同口径 |
| 5 | 历史：仅在详情页按需展示"过去 7 天最低价"（可选，从上游 `prices` 接口预生成进快照，或干脆不做） |

---

## 8. craft-anything 实际上手体验（一两句 + 明细）

**能用，但要走 CLI，且只适合"看结构"，不适合"做缓存取证"。**

- **MCP 侧不可用**：`list_toolsets` 正常（core 36 个工具、browser 22 个），`enable_toolset("browser")` 返回 `visible_tools: 58`，但本客户端的工具表/ToolSearch 里**始终搜不到**这 22 个 browser 工具（只能看到 `core_*` 与 `assets_*`）。所以本轮改用它同一套引擎的 CLI：`craft-anything-cli`。
- **CLI 侧好用**：`--deep web-page-show --cdp-endpoint http://127.0.0.1:9223` 给出脚本数、资源、存储键名、frame origins、console 计数；`--deep web-page-watch --cdp-endpoint … --watch-ms 90000` 在导航后抓到 **129 条请求 outline**、**0 WebSocket**、544 条 console 事件。它自己拉 Chrome、能直连站点（本机直连 `db4tarkov.com` 实测 200，无需代理）。
- **比普通抓包强在哪**：一条命令出结构化 JSON，且**默认做数据最小化**——不固化 cookie / Authorization / 正文，只留"outline"，适合当证据留档；WebSocket、frame、storage 一并给出。
- **明显限制**：（1）**纯被动**——必须在页面加载前挂上，attach 后再 reload 也看不到应用层缓存导致的"零请求"；（2）**响应头只有名字、没有值**（`cf-cache-status=`、`cache-control=` 全被清空），做缓存/CDN 取证必须回到 CDP/curl；（3）**不返回响应体**，价格字段只能另抓；（4）MCP 工具没接进客户端，实际只能用 CLI。

---

## 9. 证据文件清单

`docs/r39-live-price/` 下（本轮新增）：

| 文件 | 说明 |
|---|---|
| `market-firstload-120s.json` | 全新 profile 首屏 CDP 抓包（44 请求 / 120 s），含请求头、响应头、响应体预览 |
| `market-capture-A-reload-75s.json` | 老 profile 重载抓包（仅 `version.json`，证明本地缓存生效） |
| `market_dev_ss-latest.json` | A 代快照（02:56，ETag `63d2…`，3412 条） |
| `market_dev_ss-0305.json` + `.headers.txt` | B 代快照（03:06，ETag `9c06…`）+ 完整响应头 |
| `market_tm_ss-latest.json` | tarkov-market 口径快照（3096 条） |
| `upstream-pvp-season-price-sample.json` | 上游逐物品历史序列样本（`priceMin/price/offerCount/timestamp`） |
| `craft-page-show-market.json` | craft-anything `web-page-show` 结果 |
| `craft-page-watch-market.json` | craft-anything `web-page-watch` 结果（129 请求 outline，0 WS） |
| `etag-sampler-market.jsonl` / `.first.json` / `.last.json` / `.compare.json` | 低频 ETag 采样与首末两代逐项比对 |
| `core-changes-retry.json` | `changes.json` 样本（按游戏版本组织） |

---

## 10. 采样记录（ETag / 价格变化）

低频采样：每 5 分钟一次 HEAD，共 6 次，跨 25 分钟（`etag-sampler-market.jsonl`）。

| # | 采样时间 (UTC) | `market_dev_ss` ETag | `market_tm_ss` ETag |
|---|---|---|---|
| 1 | 03:01:40.166Z | `"9c0644db0d984edd5b12a6801a01ad08"` | `"4de2962c7881d6835b7edda0b486a661"` |
| 2 | 03:06:41.872Z | 同上 | 同上 |
| 3 | 03:11:42.472Z | 同上 | 同上 |
| 4 | 03:16:43.079Z | 同上 | 同上 |
| 5 | 03:21:43.734Z | 同上 | 同上 |
| 6 | 03:26:44.346Z | 同上 | 同上 |

首末两次各下全量，逐物品比对（`etag-sampler-market.compare.json`）：

```json
{"dev_ss":{"changed":0,"same":3412,"added":0,"removed":0},
 "tm_ss": {"changed":0,"same":3051,"added":0,"removed":0}}
```

解读：

- **25 分钟内 ETag 未变、两张表所有商品的最低价 0 变化** → 这段时间内**没有发生换代**，数据完全冻结。
- 结合 §3.5 观测到 02:56→03:01 之间恰有一次换代（`63d2…`→`9c06…`），可确认：**更新是"冻结—整批替换—再冻结"的离散换代，间隔大于 25 分钟**（上一轮 dev_pvp 实测两代 ≈70 分钟）。
- 反过来说：若数据是实时透传或分钟级刷新，25 分钟内 3412 个物品的最低价不可能一条不变 → 这是"服务端定时生成快照"的直接反证式证据。

---

## 11. 未做 / 未证实清单

- 未取到 tm 快照的**生成侧证据**（哪个端点、什么频率抄入），只到字段级与标签级证据 → 推断。
- 未验证生成任务的**真实调度器**（GitHub Actions 另有哪些 workflow、market 快照由哪条 workflow 产出）；JS 里只看到 `icon-sync.yml` 与 `cron 06:45 UTC`。
- 未对 `/market` 做像素级 UI 核对（价格列的确切取整/单位换算未逐项比对）。
- 逐物品历史接口是否**始终**在首屏触发，取决于视口与渲染时机，两次抓包结果不一致（0 次 / 48 次）。
