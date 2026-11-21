host=HOMONAS user=MASTERJJ at=2026-11-04T02:04:46+08:00

# R43 账号版本调研 · 网络与取证留痕

配套文档：[r43-account-editions.md](./r43-account-editions.md)

## 0. 声明

- **未改任何代码**：`index.html`、`style.css`、`app.js`、`combat_sim.js`、`tasks.js`、`game-mode.js`、
  `assets/`、`tools/`、`tests/`、`data/` 全部只读，未写入、未删除、未格式化。
- **未写 data**：`data/` 下没有任何文件被创建/修改（见 §6 的 git 现状说明）。
- 本轮**只新增两个 docs 文件**：`docs/r43-account-editions.md`、`docs/r43-account-editions-ledger.md`。
- 未 `git commit`，未动 `release/`、`dist/`、`build/`。

## 1. 代理实测（先测端口，再实测请求）

| 步骤 | 命令/方式 | 结果 |
|---|---|---|
| 端口连通 | `Test-NetConnection 127.0.0.1 -Port 7896` | **TcpTestSucceeded = True** |
| 实际 HTTP 请求（PvP 价格） | `curl -x http://127.0.0.1:7896 https://json.tarkov.dev/regular/items` | **200**，17,344,134 B，响应体为可解析 JSON |
| 实际 HTTP 请求（PvE 价格） | 同上 `/pve/items` | **200**，17,274,460 B，JSON 可解析（`data.items` 下 5498 个 id） |
| 实际 HTTP 请求（PvPS 价格） | 同上 `/pvp-season/items` | **200**，17,136,299 B，JSON 可解析 |
| 真实页面（官网购买页） | 真实 Chrome（browser_use 接管）+ 代理 | **200，页面完整渲染**（Cloudflare 校验通过） |

结论：代理**不是"只设了环境变量"**，上述每个 URL 都拿到了 200 且响应体被实际解析使用
（例如 PvE/PvP 同 id 价格抽样：`5447a9cd4bdc2dbd208b4567` → PvE 11111 / PvP 44415）。

本地地址直连：`NO_PROXY=localhost,127.0.0.1`，未让本地服务走代理。

## 2. 实际成功访问的网址（全部 2026-11-04，Asia/Shanghai）

| # | URL | 方式 | 状态 | 大小/结果 | 用途 |
|---|---|---|---|---|---|
| 1 | `https://www.escapefromtarkov.com/purchase` | 真实 Chrome（非 headless）+ 代理 | 200 | 4 张版本卡渲染成功，逐卡截图 | 在售版本、价格、区域 |
| 2 | `https://arena.tarkov.com/support/knowledge/529` | curl + 代理 | 200 | 281,166 B；正文 2,909 字符 | 5 个版本总览（官方原文） |
| 3 | `https://arena.tarkov.com/support/knowledge/534` | curl + 代理 | 200 | 正文 2,852 字符 | Standard 装备清单 |
| 4 | `https://arena.tarkov.com/support/knowledge/535` | curl + 代理 | 200 | 正文 3,253 字符 | Left Behind 装备清单 |
| 5 | `https://arena.tarkov.com/support/knowledge/536` | curl + 代理 | 200 | 正文 4,030 字符 | Prepare for Escape 装备清单 |
| 6 | `https://arena.tarkov.com/support/knowledge/537` | curl + 代理 | 200 | 正文 7,157 字符 | The Unheard 装备清单 + 附加权益 |
| 7 | `https://arena.tarkov.com/support/knowledge/538` | curl + 代理 | 200 | 正文 5,852 字符 | EOD 装备清单 + 附加权益（含怀旧任务链） |
| 8 | `https://json.tarkov.dev/regular/items` | curl + 代理 | 200 | 17,344,134 B | PvP 价格上游 |
| 9 | `https://json.tarkov.dev/pve/items` | curl + 代理 | 200 | 17,274,460 B | **PvE 价格上游可用性验证** |
| 10 | `https://json.tarkov.dev/pvp-season/items` | curl + 代理 | 200 | 17,136,299 B | PvPS 价格上游可用性验证 |
| 11 | `https://json.tarkov.dev/pve/tasks` | curl + 代理 | 200 | 2,101,689 B | PvE 任务上游 |
| 12 | `https://json.tarkov.dev/pvp-season/tasks` | curl + 代理 | 200 | 1,855,366 B | PvPS 任务上游 |
| 13 | `https://escapefromtarkov.fandom.com/api.php?...` | curl + 代理 | 200 | Trading 页面正文 11,499 字符（39,044 B） | 跳蚤解锁等级 15、税费说明（官方 Wiki） |
| 14 | `https://store.steampowered.com/api/appdetails?appids=3932890` | curl + 代理 | 200 | JSON | Steam 标准版 US$49.99 |
| 15 | `https://store.steampowered.com/api/appdetails?appids=4091290` | curl + 代理 | 200 | JSON | PvE Zone US$29.99 |
| 16 | `https://store.steampowered.com/api/appdetails?appids=4090950/4090970/4090980` | curl + 代理 | 200 | JSON（无价格，捆绑包） | Steam 各 Expansion Pack 上架日期 |
| 17 | `https://store.steampowered.com/bundle/74190/` | curl + 代理 | 200 | 73,394 B | The Unheard Steam Edition 权益与「不含 Season Pass」原文 |
| 18 | `https://store.steampowered.com/api/storesearch/?term=Escape+from+Tarkov` | curl + 代理 | 200 | 2,656 B JSON | Steam 商品清单（含 PVE Zone、TarCoin） |
| 19 | `https://www.escapefromtarkov.com/news` | 真实 Chrome | 200 | 10 条新闻标题/日期 | 佐证站点在 2026 年仍活跃（含 1.3.0.0 于 2026-10-29） |

## 3. 失败的资源与具体错误（不掩盖）

| 目标 | 方式 | 错误 | 处理 |
|---|---|---|---|
| `https://www.escapefromtarkov.com/`（及 `/preorder-page`、`/support/knowledge`、`/expansions`、`/api/*`） | PowerShell `Invoke-WebRequest`（.NET TLS 指纹） | **403 已禁止**（服务器直接拒绝） | 改用 `curl.exe` → 200；SPA 页面改用真实 Chrome |
| `https://www.escapefromtarkov.com/purchase` 首轮 | Chrome DevTools MCP（自动化 Chrome） | **Cloudflare Turnstile**「请验证您是真人」，点击勾选后仍停留（Ray ID `a54d30cf5f71e538`） | 改用 browser_use 真实浏览器 → 通过并渲染成功 |
| `https://escapefromtarkov.fandom.com/api.php?...` | PowerShell `Invoke-WebRequest` | **无法连接到远程服务器**（连接层失败） | 改用 `curl.exe -x` → 200 |
| `https://www.escapefromtarkov.com/api/purchase`、`/api/products`、`/api/editions`、`/api/preorder` 等猜测接口 | curl | 403 / 404 | 放弃猜接口；改为浏览器内直接读 DOM |
| 官方站点区域切换（切到北美/亚太） | 真实 Chrome | 无该选项，仅「独联体 / 欧洲」 | 如实记录：本轮只有 RUB 价格 |
| `https://www.escapefromtarkov.com/support/knowledge/534..538` | curl | 200 但返回 SPA 空壳（无正文） | 改用 `arena.tarkov.com` 同编号页面（同一知识库，服务端渲染） |

未关闭 TLS 校验；未用 `--insecure` / `-k`。

## 4. 结论来源分类

| 结论 | 来源类别 |
|---|---|
| 5 个版本、仓库格数、容器型号、经验加成、商人初始声望、EOD 停售、TUE/EOD 附加权益、EOD 怀旧任务链 | **真实官方网页**（arena.tarkov.com KB 529/534–538，抓取 2026-11-04） |
| 在售 4 版、RUB 价格、区域限制 | **真实官方网页**（escapefromtarkov.com/purchase 渲染后 DOM + 截图） |
| Steam US$49.99 / US$29.99 / Steam 版 TUE 不含 Season Pass | **真实官方商店页/API** |
| 跳蚤解锁等级 15、税费公式 | **官方 Wiki**（Fandom Trading，可编辑，属二手权威） |
| 中文俗称「白边 / 蓝边（金边）/ 黑边」 | **社区二手**（gtx950l.github.io 百科、游研社、NGA），非官方译名 |
| 任务数 503/499/462、两两差异 14/4/14、季节信息 | **本地数据**（`data/tasks/index.json`、`data/tasks/diff-report.json`，生成于 2026-10-28） |
| PvE/PvP 价格差异显著 | **本地快照 + 本轮实测上游**（两者一致） |

未把「未实际访问的网页」描述成已核对；所有标注为官方的结论都能对应到上表的 URL。

## 5. 本轮发现但未解决的问题

1. 购买页价格数字（3100/1100/2200/9200 RUB）呈非递增序列，按钮又是「升级游戏版本」/「变更游玩区域」混合，
   **无法确认是绝对价还是升级差价**；已在主文档标注 `basis=checkout-display`。
2. 区域选择器不开放北美/亚太，无法拿到 USD 官网价（Steam USD 已作为交叉来源）。
3. `Escape from Tarkov` 官方站点 SPA 的数据接口未定位（`/api/*` 全部 403），
   若要做自动化价格抓取，需要登录态或浏览器渲染，成本较高。
4. EOD 怀旧任务链的 taskId 未取得（上游无该字段）。
5. 钥匙链：官方 5 份清单均无该条目，「黑边送钥匙链」无法证实。

## 6. git 现状（说明：这些改动不是本轮产生的）

`git status --short` 在 `main` 分支上显示多个文件为 `M`（`app.js`、`index.html`、`style.css`、`tools/*`、`tests/*`、
`data/meta.json`、`data/roadnet.json` 等）。这些是**另外两个并行会话正在进行的前端/后端改动**，本轮全程只读，
未对它们做任何写入。本轮新增的只有 `docs/r43-account-editions.md` 与 `docs/r43-account-editions-ledger.md` 两个文件。
