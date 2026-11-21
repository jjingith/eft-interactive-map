# R39 · db4tarkov 实时价格取证 ledger

host=HOMONAS user=MASTERJJ at=2026-11-03T23:05:00+08:00（UTC 2026-11-03T15:05:00Z）

> 范围：只做取证与可行性判断。**本轮未改任何项目代码**（`eft-interactive-map` 下除 `docs/r39-live-price*` 外零改动，未提交 git，未动 `release/`、`dist/`）。

---

## 0. 结论（先看这段）

1. **db4tarkov 的"实时价格"不是实时推送，也不是读游戏客户端。** 它是 **b 类：轮询/聚合第三方公开行情 → 自家 Cloudflare Worker 压成静态 JSON → 前端按需带 ETag 条件请求**。
2. 关键端点（全部匿名可读，不需要 API key / 登录）：
   - `https://eft-cdn.dvcstudiox.workers.dev/json/realtime/market_dev_pvp.json`（PvP，tarkov.dev 口径，3544 项，399 KB）
   - `.../market_dev_pve.json`（PvE，3763 项，424 KB）
   - `.../market_dev_ss.json`（season，3442 项，385 KB）
   - `.../market_tm_pvp.json` / `market_tm_pve.json` / `market_tm_ss.json`（tarkov-market 口径，4218 项，479 KB）
   - `.../json/core/changes.json`（版本变更清单，37 KB，**需要浏览器 UA + `Origin: https://db4tarkov.com`**）
3. **实测刷新间隔 ≈ 70 分钟一次**（15:00:00Z 到 15:01:32Z 之间 ETag 变化 1 次，前一代快照生成于 ~13:50Z）。刷新瞬间数据滞后 **4–13 分钟**，刷新前最长滞后 **50–73 分钟**。所以它对用户的"实时"= **最多约 1 小时滞后**，不是秒级。
4. **前端不轮询**：保持页面打开 240 秒，行情 XHR 请求 0 次；无 WebSocket、无 SSE（只有 Flutter 的静态资源与字体请求）。只在进入/切换模式时条件请求一次，命中 304 就用 GetStorage 里的缓存。
5. **我们完全可以对齐**：db4 的 `dev_*` 就是 `json.tarkov.dev` 的裁剪转发，而我们项目的快照**本来就用同一个上游** `https://json.tarkov.dev/regular/items`。id 命中率 **99.74%–99.94%**。真正差距只在"刷新频率"，不在"能不能拿到"。
6. **发现了需要确认的口径问题**：db4 的 `dev_pvp` 与我们的 `regular` 上游数值 85% 同值、`dev_pve` 与 `regular` 仅 2.3% 同值 → **`json.tarkov.dev/regular/items` 是 PvP（正常模式），不是 PvE**。而项目 `tools/r20_fetch_prices.py` 注释与 `flea-prices.json` 元数据把 `regular` 标成 PvE。这是文档口径错误，需另行确认（本轮未改）。
7. `json.tarkov.dev/pve/items` **现在返回 200**（可作 PvE 数据源），而 `api.tarkov.dev/graphql` 复测仍 422 `GraphQL server unavailable`，`json.tarkov.dev/pvp/items` 仍 404。

---

## 1. 代理与网络实测

| 项 | 结果 |
| --- | --- |
| `Test-NetConnection 127.0.0.1 7896` | `TcpTestSucceeded = True` |
| HTTP/HTTPS 代理 | `http://127.0.0.1:7896` |
| `NO_PROXY` | `localhost,127.0.0.1,::1`（CDP 9222 全程直连） |
| 真实请求验证 | `curl -x 127.0.0.1:7896 https://db4tarkov.com/preset` → **HTTP 200**，落地 60,308 B HTML（Flutter Web 外壳） |
| TLS | 未关闭校验；全部请求正常握手 |
| Node 侧 | 必须 `NODE_USE_ENV_PROXY=1` 才走代理（Node 默认忽略 env 代理），已实测 200 |
| 浏览器侧 | Chrome 以 `--proxy-server=http://127.0.0.1:7896 --proxy-bypass-list=localhost;127.0.0.1;::1` 启动，CDP `127.0.0.1:9222` 直连成功 |

> 运行环境机器级已存在 `HTTP_PROXY` 等环境变量；REA 首次连 `127.0.0.1:9222` 报 `endpoint_unreachable` 的原因即为本机代理变量干扰回环地址，改用已确认的直连 + 端口就绪后正常。

---

## 2. 实际成功访问的外部网址（本轮全部经代理实测 HTTP 200）

| URL | 状态 | 大小 | 备注 |
| --- | --- | --- | --- |
| `https://db4tarkov.com/preset` | 200 | 60,308 B | Flutter Web 外壳，落点即 `/preset`，**未登录、未跳转** |
| `https://db4tarkov.com/flutter_bootstrap.js` | 200 | 11,510 B | sha256 `860b2e…` |
| `https://db4tarkov.com/flutter.js` | 200 | 9,553 B | sha256 `a483fd…` |
| `https://db4tarkov.com/main.dart.js` | 200 | 18,570,596 B | sha256 `72e776…` |
| `https://db4tarkov.com/canvaskit/canvaskit.js` | 200 | 86,859 B | sha256 `7361b7…` |
| `…/json/realtime/market_dev_pvp.json` | 200 | 399,379 B | ETag `W/"e7ce7181…"` |
| `…/json/realtime/market_dev_pve.json` | 200 | 424,082 B | |
| `…/json/realtime/market_dev_ss.json` | 200 | 384,997 → 384,987 B | 15:01 刷新后变 `W/"e3aeffc8…"` |
| `…/json/realtime/market_tm_pvp.json` | 200 | 479,430 B | ETag `W/"a170cc88…"` |
| `…/json/realtime/market_tm_ss.json` | 200 | 354,826 B | |
| `…/json/core/changes.json` | 200 | 37,413 B | 仅带 UA+Origin 时 200 |
| `https://json.tarkov.dev/regular/items` | 200 | 17,343,840 B | `Last-Modified: 14:40:34 GMT`、`Age: 589` |
| `https://json.tarkov.dev/pve/items` | 200 | — | PvE 上游现在可用 |
| `https://db4tarkov.com/assets/...`（图标） | 200 | — | 抓包中可见 |
| `https://fonts.gstatic.com/...` | 200 | — | 抓包中可见 |

**仍无法访问 / 被拒的资源**

| URL / 操作 | 结果 | 原因 |
| --- | --- | --- |
| `…/json/core/changes.json`（curl 默认 UA，无 Origin） | **403** | Worker 侧反滥用门禁 |
| 同上 + 浏览器 UA，但 `Origin: http://127.0.0.1:8000` | **403** | Origin 必须是 `https://db4tarkov.com` |
| 同上 + 浏览器 UA + 正确 Origin | 200 | 证明门禁条件 |
| `https://api.tarkov.dev/graphql`（POST 小型查询） | **422** `GraphQL server unavailable. Try again later.` | 与项目 `r20_fetch_prices.py` 记录一致 |
| `https://json.tarkov.dev/pvp/items` | **404** | 上游无该路径 |
| `json.tarkov.dev/items` | **404** | 必须带模式前缀 |
| REA `analyze_web_bundle` | `examined=0 / total=0` | 该工具只接受 `view.kind=javascript-routes`，Flutter 编译产物无路由表，返回空视图 |
| REA `export_web_scripts` | 未执行 | 该工具要求 REA 侧 capture 文件路径；本轮改用「curl 落地原始字节 + SHA256」并与 REA `inspect_web_page` 的 `cdp_hash` 逐一对齐（三份全部一致），等价完成导出取证 |

---

## 3. REA 取证记录

| 操作 | 结果 |
| --- | --- |
| `list_browser_targets(http://127.0.0.1:9222)` | 1 个 page：`Database for Tarkov` / `https://db4tarkov.com/preset`（Chrome 156.0.8078.76，CDP 1.3） |
| `inspect_web_page`（含 script sources） | 响应超 10 MiB 预算（`main.dart.js` 18.5 MB），REA 保留 evidence `ev_a6ae0907…`，正文未能内联返回 |
| `inspect_web_page`（不含 script sources，含 json/ws/storage shapes） | 成功；`attach_limited`：DOM/网络只覆盖 attach 之后窗口；storage 有 `firebase.*`、`GetStorage`（`flutter.…cache_…`，即 ETag+body 缓存） |
| `capture_web_screenshot` | 1424×805 PNG，sha256 `06e59a72…`，48 KB → `db4-preset-20261103-144733.png`（页面顶部为 `PVE / PVP` + `SEASON` 切换，右上 `Final Cost: Buy / Sell`） |
| `export_web_scripts`（等价） | `scripts-manifest.json`：4 个脚本 URL + 字节数 + SHA256，其中 3 个与 REA `cdp_hash` 完全一致 |
| 原始网络抓取（CDP `Network.enable` + `Page.reload`，只读不改页面） | capture-A 90 s：51 事件 / 10 条 API-like；capture-B 240 s 被动：51 事件 / **0 条行情请求** |

> 说明：REA 是纯被动观察（不导航、不点击）。为了让「页面加载期」的 XHR 落入观察窗，本轮用本机 CDP 会话对同一 target 做一次 `Page.reload` 并记录 `Network.*` 事件；这不是 REA 提供的动作，已在证据文件中标注（`capture-A-reload-90s.json` 的 `meta.doReload=true`）。

---

## 4. 实时性来源判定（有证据，不是猜）

**结论：b 类（轮询/聚合第三方 API），且叠加 e 类特征（短 TTL 缓存 + 时间戳展示）。**

证据链：

1. **抓包里出现 3 个行情请求，全部是普通 GET，域名是站方自建的 Cloudflare Worker CDN：**
   - `market_dev_ss.json` @ 8.6 s、`market_tm_ss.json` @ 11.1 s（首屏加载期）
   - `changes.json` @ 34.7 s
   - 无 `wss://`、无 `text/event-stream`（capture-A/B 事件里 `webSocket*` 为 0，`EventSource` 为 0）
2. **数据内容就是 tarkov.dev / tarkov-market 的公开行情**：
   - `market_dev_*` 字段 `{id, lastLowPrice, avg24hPrice, updated}`；`market_tm_*` 字段 `{id, lastLowPrice, avg7daysPrice, updated}`
   - 与 `https://json.tarkov.dev/regular/items` 逐 id 比对：`dev_pvp` **3009/3544 同值**，`dev_pve` **仅 86/3763 同值** → dev_pvp 上游就是 regular(PvP)
   - `main.dart.js` 里出现合作伙伴/数据源链接 `tarkov-market.com`，且**未出现 `api.tarkov.dev`（GraphQL 未被使用）**
3. **前端只做条件请求，不做定时轮询**：
   - JS 中存在 `fetchWithEtag`：请求带 `If-None-Match`，304 时从 `GetStorage` 的 `cache_<key>` 取 body，200 时回写 body 与 etag
   - 被动观察 240 s，行情请求 **0 次**；只有切换模式/重新进入才重新请求
4. **不是 a 类（读游戏进程）**：整站是纯 Web（Flutter Web + Cloudflare），没有任何本地代理/插件通道；页面无 WebSocket/SSE，也无「本机端口」请求。
5. **不是 d 类（人工上传/爬 flea 网页）**：数据字段与 id 完全对齐 tarkov.dev 物品库（BSG 模板 id），不是人工录入。
6. **"更新于 N 分钟前" 的实现**：`main.dart.js` 内有格式化函数，输出形如 `"<N> min ago (<HH:MM:SS> <dd/mm/yyyy>)"`，入参即条目自带的 `updated`。即 UI 文案直接来自响应里的 `updated` 字段，没有额外服务端时间。截图中 Preset 页未展开该 tooltip，文案与字段的对应关系由代码证据确认。

---

## 5. 实时性量化（实测窗口 14:43–15:03Z，共 20 分钟）

| 观测项 | 数据 | 说明 |
| --- | --- | --- |
| 首屏加载请求数 | 2 个 dev/local 文件 + 1 个 tm | 一次性，非周期 |
| 被动 240 s 行情请求 | **0** | 无轮询、无推送 |
| 采样 11 轮（14:49–15:03，≈90 s/轮） | ETag 变化 **1 次** | 发生在 15:00:00–15:01:32 之间 |
| 旧快照最新 `updated` | `13:48:06Z`（dev）/ `13:59:53Z`（tm） | 说明旧文件生成于 ~13:50Z |
| 新快照最新 `updated` | `14:48:05Z`（dev）/ `14:56:53Z`（tm） | 说明新文件生成于 ~15:01Z |
| **实测刷新间隔** | **≈ 70 分钟**（13:50 → 15:01） | 仅 1 个区间样本；可确定 >15 分钟 |
| 刷新瞬间数据滞后 | dev **13 min** / tm **4 min** | = 与上游自身 10 分钟刷新周期的差 |
| 刷新前数据滞后 | dev **73 min** / tm **50 min** | 用户最坏情况 |
| 一次刷新内变化量 | `lastLowPrice` 变 **461/3442 = 13.4%**；`updated` 变 2581/3442 | 与刷新间隔内的市场波动一致 |
| 上游自身刷新 | `json.tarkov.dev/regular/items` `Last-Modified 14:40:34Z`、请求时 `Age 589 s` | 上游约 **10 分钟**一版 |
| 本地项目快照 | `flea-prices.json.lastSuccessAt = 2026-11-03T13:51:48+08:00`（=05:51Z） | 取证时已 **约 9 小时**陈旧 |

**结论**：db4 的"实时"上限受自身 ~70 分钟重建周期约束；它并没有比 tarkov.dev 更实时，只是把 17 MB 全量裁成 385 KB 便于前端取用，并用 ETag 省流量。

> 交叉核对：上一轮 `docs/site-integration-audit/raw/db4-*.json` 的抓包里其实已经出现过同两个 `market_*_ss.json` 端点，但当时没有做「刷新周期 / 数据年龄 / PvP-PvE 口径」分析。本轮补齐这三点。

---

## 6. 鉴权 / 配额 / 防护

| 项 | 实测 |
| --- | --- |
| API key / 登录 | **不需要**。所有 `market_*` 端点匿名 GET 即 200；页面也未要求登录 |
| 会员 | `changes.json` 也不需要（带正确 Origin 即 200） |
| `X-RateLimit-*` | **不存在**（响应头无任何 ratelimit 字段） |
| 突发测试 | 连续 8 次 GET `market_dev_pvp` → `200,200,200,200,200,200,200,200`，未见 429 |
| CORS | `market_*`：**反射任意 Origin**。`Origin: http://127.0.0.1:8000` → `Access-Control-Allow-Origin: http://127.0.0.1:8000`；无 Origin 时为 `*`；`Access-Control-Expose-Headers: ETag` |
| 预检 | `OPTIONS` → 204，`Allow-Methods: GET, HEAD, OPTIONS`，`Allow-Headers: x-app-token, user-agent, if-none-match, content-type`，`Max-Age: 86400` |
| `x-app-token` | 出现在允许头里，但 `market_*` 不带它也是 200；`core/changes.json` 带随机值也 200 → **非强校验** |
| Referer / UA 门禁 | 只作用于 `json/core/*`：UA 缺失 → 403；有 UA 但 Origin 不是 `https://db4tarkov.com` → 403；**Referer 不是必要条件**（UA+Referer 仍 403，UA+Origin 才 200） |
| Cloudflare | `Server: cloudflare`、`CF-RAY: …-HKG`；**未触发质询/JS 挑战**（JSON 直连与真实 Chrome 均正常） |
| 缓存头 | `Cache-Control: no-cache` + `ETag`（dev 为弱 ETag `W/…`，ss 为强 ETag）；`core/changes.json` 为 `public, max-age=3600` |

---

## 7. 最小字段集与 `items.json` 对齐

**如果我们要接同样数据，最少需要这些字段（以 `market_dev_pvp` 为例）：**

```json
{
  "id": "5447a9cd4bdc2dbd208b4567",
  "lastLowPrice": 36000,          // 跳蚤最低挂单价（核心）
  "avg24hPrice": 67107,           // 24h 均价
  "updated": "2026-11-03T14:38:03.000Z"  // 该条价格时间（用于“N 分钟前”）
}
```

扩展字段（按需）：

```json
{
  "low24hPrice": 29999, "high24hPrice": 122222,  // 24h 低/高
  "basePrice": 18397,                            // 基础价（非市场价，别混用）
  "avg7daysPrice": 0,                            // 仅 tarkov-market 有
  "lastOfferCount": 28                           // 挂单数，来自 tarkov.dev 全量 JSON，db4 未透出
}
```

**与本地 `data/items.json` 的映射（`items` 为以 id 为键的对象，共 5480 项）：**

| 上游字段 | db4 字段 | 本地字段 | 对齐情况 |
| --- | --- | --- | --- |
| `id`（BSG 模板 id） | `id` | 对象的 **key** | **直接对齐** |
| `lastLowPrice` | `lastLowPrice` | `p.l` | 直接 |
| `avg24hPrice` | `avg24hPrice` | `p.a` | 直接 |
| `low24hPrice` / `high24hPrice` | — | `p.lo` / `p.hi` | 直接 |
| `basePrice` | — | `p.b` | 直接 |
| `updated` | `updated` | **未保留** | 需在构建时新增 |
| 商人买价 | — | `trade[]`（`k:"buy"`, `t:traderId`, `p`, `c`, `l`） | 已在本地，无需新源 |
| 挂单数 `lastOfferCount` | — | 未保留 | 可选新增 |

**id 命中率（直接用本地 id 集合去匹配 db4 快照）：**

| 文件 | 条数 | 命中本地 id |
| --- | --- | --- |
| `market_dev_ss` | 3442 | **3433 / 3442 = 99.74%** |
| `market_dev_pvp` | 3544 | **3535 / 3544 = 99.75%** |
| `market_tm_ss` | 3116 | **3114 / 3116 = 99.94%** |
| `market_tm_pvp` | 4218 | **4197 / 4218 = 99.50%** |

未命中的 ~9–21 条是本地 `items.json` 未收录的新物品/活动物品，不影响主流程。

---

## 8. `逆向参考/db4tarkov-local` 核查（只读）

- 目录内**只有一个文件**：`WHITEPAPER.md`（17,127 B），**没有**镜像站点、没有本地 JS、没有价格桩数据、没有配置。
- 文档性质：一份「把 db4tarkov 做成本地离线 exe」的**白皮书草案**（v1.0，2026-10-21，状态：未进入编码），声明数据源为 `api.tarkov.dev/graphql`，并明确"不扒 db4tarkov 站点"。
- 结论：**不能离线复用**。它不含任何可运行代码或价格数据；且其主数据源 `api.tarkov.dev/graphql` 本轮复测仍 422 不可用。

---

## 9. 三方案对比（落到本项目的"运行期不联网"约束）

### 方案 1 · 纯离线（维持快照，缩短构建期刷新周期）
- 做法：保持 `data/flea-prices.json` 为唯一运行时数据源；把 `tools/r20_fetch_prices.py` 的执行频率从"每天最多一次"改为发布前必跑（或 CI 定时跑），并把 `updated` 一并写入快照。
- **实时性上限**：等于"发布/构建频率"。每天构建一次 → 最坏 24 h 陈旧；若每次发版前跑 → 通常 0.5–2 h。永远不可能做到 db4 那种 1 小时内自动更新，除非机器常开定时任务（那已属半在线）。
- 优点：零新增运行时网络；零 ToS 风险（上游 tarkov.dev 为开源公开数据）；完全符合既有约束。
- 代价：实时性完全依赖人工/CI 节奏；用户看不到"数据多旧"。
- 需要新增代码范围（不实现）：`r20_fetch_prices.py` 增写 `updated` 字段；UI 显示快照时间（已有 lastSuccessAt 可直接展示）。
- 与"运行期不联网"冲突：**无**。
- 许可证/ToS：低（tarkov.dev 公开数据）。

### 方案 2 · 可选在线行情（默认离线，用户显式开启）
- 做法：新增"实时行情"开关（默认关）。开启后由本地 Python 侧（不是浏览器）按 **10 分钟**间隔条件请求（`If-None-Match`），命中 304 不下载 body；失败静默回退快照。
- **推荐数据源优先级**：
  1. `https://json.tarkov.dev/regular/items`（17 MB，公开、开源自建上游；建议 30–60 分钟一次，配 gzip 与 last-modified 条件请求）——**合规首选**；
  2. 若要 385 KB 的轻量载荷，可用 db4 的 `market_dev_pvp.json`（**但这是第三方转发端点，见风险 §10**）；
  3. `json.tarkov.dev/pve/items`（PvE，现可用）。
- 实时性上限：受上游 ~10 分钟刷新限制；我们能做的不低于 db4 的 70 分钟。
- 优点：能满足"接近实时"；默认仍离线；可复用现有 `p.*` 字段，不引入新 ID 体系。
- 代价：需要新增网络层、缓存、状态机与 UI 来源标识；17 MB 全量下载对带宽/内存不友好（需裁剪写盘）。
- 需要新增代码范围（不写）：`tools/live_prices.py`（拉取/裁剪/原子写 `data/live-prices-cache.json` + 失败回退）；`tools/serve.py` 增 `/api/live-prices` 只读路由；前端 `app.js` 增「实时/快照」来源徽标 + 开关 + 定时刷新；`data/settings` 增开关项；测试新增离线 guard 断言（未开启时不得发起任何外网请求）。
- 与既有约束冲突：**中**（需明确写成"默认关闭的显式 opt-in"，且 `test_offline_guard.py` 必须仍然通过）。
- 许可证/ToS：tarkov.dev 低；db4 worker / tarkov-market 数据**中–高**。

### 方案 3 · 本地代理 / 读游戏客户端
- 事实基础：**db4 不属于这一类**（无本地进程通道）。若我们要自建"秒级真实时"，只能读游戏日志/内存/挂单流。
- 风险：触及反作弊（BattlEye）与 BSG ToS，可能封号；且与"离线地图工具"定位无关。
- 结论：**不建议**；除非用户明确要求并书面接受账号风险，否则不进入方案池。

| 维度 | 方案 1 | 方案 2（推荐增强） | 方案 3 |
| --- | --- | --- | --- |
| 实时性 | 取决于发版，小时~天 | ≤10 min（上游限制） | 秒级（理论） |
| 新增代码 | 极小 | 中（新网络层+UI+开关+测试） | 大且高危 |
| 离线约束冲突 | 无 | 中（必须 opt-in） | 高（依赖本机游戏进程） |
| ToS 风险 | 低 | 低（用 tarkov.dev）/ 中高（用 db4、tm） | **高** |
| 推荐 | ✅ 基线 | ✅ 作为可选增强 | ❌ |

**推荐组合**：方案 1 作为默认与兜底；方案 2 用 **tarkov.dev 上游**（不要绑 db4 worker）作为可选增强；方案 3 不采纳。

---

## 10. 风险与"会不会变成必须联网"

1. **ToS/版权**：db4 的 Worker 端点没有任何公开许可声明，且对 `core/*` 做了 UA+Origin 门禁 —— 说明作者有反程序化访问意图。我们直接把它当"免费 API"长期依赖，属于把第三方基础设施当上游，随时可能被限流/改路径/加 token，也可能违反其条款。**tarkov-market 是商业数据（官方 API 要 key），更不应绕过**。合规路径只有 tarkov.dev 的公开 JSON。
2. **不能把离线工具变成必须联网**：所有在线能力必须 (a) 默认关闭、(b) 失败 5 秒内静默回退到本地快照、(c) 启动流程不等待网络、(d) 由 `tests/test_offline_guard.py` 守护"未开启时零外网请求"。
3. **UI 必须标源**：显示"实时（tarkov.dev，更新于 N 分钟前）"或"快照（构建于 YYYY-MM-DD HH:mm）"，避免再次出现"看起来实时其实是快照"的误导。
4. **口径风险**：`regular` 到底是 PvP 还是 PvE，本轮证据指向 **PvP**（见 §0.6）。若不先修正口径，方案 2 可能把 PvP 价标成 PvE。
5. **数据年龄不可控**：db4 自身 70 分钟才重建一次，说明"接第三方转发"并不等于更实时；追求更实时应直连 tarkov.dev 上游。

---

## 11. 证据文件（`docs/r39-live-price/`）

| 文件 | 内容 |
| --- | --- |
| `db4-preset-20261103-1520.html` | 重新落地的 `/preset` 外壳 HTML（60,308 B），用于复核首屏 | 
| `capture-A-reload-90s.json` | CDP 全量网络事件（含首屏 3 个行情请求、headers 去敏、响应体前 6 KB） |
| `capture-B-passive-240s.json` | 240 s 被动观察（0 条行情请求，反证"不轮询"） |
| `market_dev_pvp.json` / `.headers.txt` | 399 KB 快照 + 响应头 |
| `market_dev_pve.json` / `.headers.txt` | PvE 快照 |
| `market_dev_ss.json`、`market_dev_ss-t2.json`、`market_dev_ss-after1501.json` | 刷新前/中/后三份，用于量化 |
| `market_tm_pvp.json` / `market_tm_ss.json` + headers | tarkov-market 口径 |
| `upstream-json-tarkov-dev-items.json`（17.3 MB）+ headers | 上游全量，用于同源比对 |
| `core-changes.json`（403 体）、`core-changes-retry.json`（200 体）+ headers | 门禁对比 |
| `probe-notes.txt` | 403/200、CORS、限流、突发等逐条探测记录 |
| `probe-api-tarkov-dev-graphql.json` | GraphQL 422 原始响应 |
| `db4-preset-20261103-144733.png` | REA 截图（页面与 PVP/SEASON 切换） |
| `rea-inspect-web-page-20261103.json` | REA `inspect_web_page` 完整 evidence |
| `scripts-manifest.json` + `main.dart.js.full`、`flutter.js`、`flutter_bootstrap.js`、`canvaskit.js` | 脚本字节 + SHA256（3 份与 REA `cdp_hash` 一致） |
| `sampler-15min.jsonl`、`sampler-30min-after1500.jsonl` | 90 s/120 s 采样日志（ETag、Date、maxUpdated） |

---

## 12. 未改动声明

- **本轮未改任何项目代码**：`tools/`、`data/`、`web/`、`tests/`、`build/` 均未修改。
- 仅新增 `docs/r39-live-price/` 证据目录与 `docs/r39-live-price-ledger.md`。
- 未执行 `git commit`/`git add`；未触碰 `release/`、`dist/`。
- 注：该仓库进入本轮前**已有大量未提交改动**（`git status --short` 466 行）。本轮新增内容仅 `docs/r39-live-price/` 与 `docs/r39-live-price-ledger.md`，未改 `app.js`、`index.html`、`style.css`、`tools/*.py`、`data/*`。
- 对 `逆向参考/db4tarkov-local` 只读，未改未删。
