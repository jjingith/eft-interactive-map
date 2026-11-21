# R44 模式选择器 + 在线行情 UI 留痕

host=HOMONAS user=MASTERJJ at=2026-11-04 02:55:15 +08:00

仓库：`d:\personal\trae\02-塔科夫\eft-interactive-map`（前端独占；未改 `tools/`、`tests/` 之外后端文件）

## 1. 现状（动手前查清）

- 模式切换早已存在，唯一状态在 `js/game-mode.js`：`window.GWGameMode.get()`，键值 `regular` / `pve` / `pvps`，
  持久化键 `eftmap.gameMode`，右上角 `#game-mode-bar` 生成三个 `[data-tkmode]` 按钮 + `#game-mode-label`。
  R44 之前**只有任务板自己订阅 GWGameMode**；地图任务点位、配装/弹药价格来源不跟随。
- 快照只有一套：`data/flea-prices.json` 顶层 `gameMode = "regular"`，`source` 指
  `https://json.tarkov.dev/regular/items`，条目在 `items[id]`（`lastLowPrice/avg24hPrice/low24hPrice/high24hPrice`）。
  因此 **PvE 下没有本地 PvE 快照，必须如实显示「快照（PvP，构建期）」**。
- 任务数据按模式分文件：`data/tasks/tasks.regular.json` / `tasks.pve.json` / `tasks.pvps.json`（顶层 `{tasks: {id:…}}`）；
  点位文件 `data/task-points.json` 的 `maps.<mapKey>.tasks[]` 是混合集合。
- 「三模式隔离」= 模式只影响任务集（任务板 + 地图任务点位过滤）与价格来源标注；实时行情只有 `regular|pve`，
  `pvps`（赛季服）没有实时接口，也不得为它联网。

## 2. 本轮实现

### 2.1 显式模式选择器
- 位置：顶栏（`.menubar`）右侧，`#game-mode-bar` 与 `#price-source-badge` 包进 `.scope-cluster`；
  沿用既有 XP 控件（`.game-mode-bar` / `.gm-btn`），没有另起视觉。
- 三按钮：`PvP` / `PvE` / `PvPS（赛季服）`（`data-tkmode=regular|pve|pvps`），右侧 `模式：…` 标签。
- 窄屏：`@media (max-width:1180px)` 整组 `order:20` 换到第二行；`860px` 下整组 `width:100%`、徽标缩到 160px。
  1024 实测模式组换行、地图/配装主流程不被挤压。

### 2.2 统一数据作用域（含版本预留）
- `state.dataScope = { mode: "regular", edition: null }`；`scopeMode()` 永远以 `GWGameMode.get()` 为准。
- `applyDataScope({mode?, edition?})` 是唯一入口：模式变了 → `state.live.seq += 1`（作废旧响应）、
  清 `livePrices`、停定时器、`applyTaskPointMode(mode)`、按需 `fetchLivePrices`、`refreshPriceViews()`、
  重画徽标与设置文案。
- `window.GWDataScope = { get, apply, editions: DATA_EDITIONS.slice() }`；`DATA_EDITIONS = []` 是**空**的版本扩展点：
  没有编造白边/黑边/蓝边枚举，页面也没有版本下拉（等调研结论后再加第二级）。

### 2.3 联动视图
- 任务点位：`attachTaskPoints` 保留 `map.tasksAll`；`applyTaskPointMode(mode)` 用
  `state.taskIdsByMode[mode]`（来自 `data/tasks/tasks.<mode>.json` 的 `tasks` 键集合）过滤后重建 `map.layers.tasks`，
  清掉失效的 `state.taskFocus`，并重画任务面板/图层开关/覆盖层。
- 任务列表与任务树：`tasks.js` 自身监听 `GWGameMode`，切换即刷新。
- 价格视图：`refreshPriceViews()` 按当前页重画配装成本、配枪表/底部、弹药页。
- 切换持久化：模式沿用 `eftmap.gameMode`；在线行情同意沿用新键 `eftmap.livePrices.consent.v1`。

### 2.4 来源徽标（诚实口径）
`priceSourceInfo()` 单一真相，徽标三种主态 + loading：
- `快照（PvP，构建期）` / `快照（PvE，构建期）`：`snapMode` 取自 `state.fleaPrices.gameMode`，**不是**当前模式；
  PvE 且快照仍是 PvP 时，title 追加「本地没有 PvE 快照……这不是 PvE 价格」。
- `实时（tarkov.dev，N 分钟前）`（`ageSec` / `dataAgeSec` 换算；stale 时追加提示）。
- `实时不可用，已回退快照`：区分 `enabled=false` / `error=no-cache` / 手动刷新失败原因。
- PvPS：`快照（PvPS，构建期）` + 明说「PvPS（赛季服）没有实时行情接口，不会为它发起任何联网请求」。
- 覆盖位置：顶栏徽标；配装页按钮/行内（`priceModeNote`）；弹药页 `行情：<short>`（`#quote-status`）；
  弹药注脚 `#am-note` 的 `title`；配枪变体行；`amHint` 开启时追加「价格来源：…」。

### 2.5 在线行情（默认关闭）
- 设置菜单新增「在线行情」区块：`#live-enabled` 复选框（一次点击）、`#live-status`、`#live-refresh`（默认 `hidden`）。
  文案写清：仅访问 tarkov.dev、约 10 分钟一次、失败自动回退快照。
- `canLive()` = 同意 && 模式为 `regular|pve`；关闭时 `fetchLivePrices` 首行直接 return，**绝不发 fetch**。
- 数值仍走快照：`priceFieldsFor` 以 `rec.p.a/l` 为底，命中 `live.prices[id].l/a` 且为正数才覆盖；
  `overlayQuoteFields` 同样只覆盖 `avg24hPrice/lastLowPrice`，缺失/0 值逐条回退，不整片置空。
- 单一定时器：`scheduleLiveTimer()` 仅 `canLive()` 且页面可见时挂一个 `setTimeout`（ttl 默认 600s，最小 60s）；
  `visibilitychange` 隐藏即 `stopLiveTimer()`，恢复再排。
- 请求路径为相对路径 `api/live-prices?mode=regular|pve`，`cache:"no-store"`；`state.live.seq` 守卫丢弃旧代次响应。
- 手动刷新：`POST api/live-prices/refresh`（不带请求体），200/202 → 提示「已请求服务端刷新」并再拉 GET；
  403/409/404/其它/网络失败都给红字可读原因，并在随后的 GET 之后**补回**该原因（避免被 `enabled=false` 清空）。

### 2.6 测试
- 新增 `tests/test_r44_mode_live.py`（15 条）：模式选择器可见/全局单源、任务点位按模式过滤、PvE 不冒充 PvE 快照、
  PvPS 无端点、关闭无请求、实时逐条覆盖/回退、刷新失败可读、版本扩展点为空、单一定时器、窄屏换行。
- 全量：`pytest tests -q` → **5 failed, 1680 passed, 1 skipped**（96.65s）。
  5 个失败即既有配枪失败：`test_r19_11_round` / `test_r19_13_round` / `test_r19_1_round` / `test_r19_5_round` / `test_r6_gun_workbench`，未动。
- `node --check app.js / tasks.js / js/game-mode.js` 全部 exit 0；新增/改动均为 ES5。

## 3. 实测（Chrome CDP，服务 127.0.0.1:8791）

后端直连：
- `GET /api/live-prices?mode=regular` → `ok:true, enabled:false, mode:"regular", source:"snapshot", prices:{}, count:0, cachePath:…`
- `GET /api/live-prices/status` → 开关 false + 两套缓存（regular 3538 条 / pve 2267 条）+ `lastAttempt`
- `POST /api/live-prices/refresh` → **403 `token 无效或未配置`**（桌面壳未注入 `X-EFTMap-Token`；契约写关闭时 409，实际 token 先于 enabled 校验）

页面（1024 与 1440 结果一致）：
| 步骤 | 结果 |
|---|---|
| 默认（未勾选） | 徽标 `快照（PvP，构建期）`；`#live-refresh` hidden；`live-prices` 请求 **0** |
| 勾选 | 仅 1 次 `GET api/live-prices?mode=regular`；徽标 `实时不可用，已回退快照`；状态「服务端未开启（livePrices.enabled=false）…已回退快照」；按钮出现 |
| 点「刷新行情」 | `POST /api/live-prices/refresh` → 403，随后 1 次 GET；红字保留「刷新被拒绝（HTTP 403）：需要桌面壳的 X-EFTMap-Token…」；徽标仍 fallback |
| 取消勾选 | 立即回 `快照（PvP，构建期）`；按钮重新隐藏；再等 8s，新增 `live-prices` 请求 **0** |
| 切 PvE | 任务面板/任务点位切到 PvE（PvP 503 → PvE 499）；徽标仍 `快照（PvP，构建期）`，title 明说这不是 PvE 价格 |

## 4. 后端契约问题（只记录，未改后端）

1. `POST /api/live-prices/refresh` 在未带 token 且 `enabled=false` 时返回 **403**（先校验 token），
   与任务书「关闭时 409」不一致；UI 对 403/409 都给了可读文案，不依赖单一状态码。
2. `refresh` 若带 JSON 请求体，服务端在 403/409 提前返回前未读取 body，同一 keep-alive 连接上的下一次 GET 会得到
   **HTTP 501**。UI 已改为不带请求体的 POST（契约只要求 POST + 回环 + token），规避该问题；
   根治应在 `serve.py` 提前返回前 drain body 或回 `Connection: close`。
3. `enabled=false` 时 `GET` 仍返回 `ok:true`、`count:0`、`prices:{}`，UI 以 `enabled` 判断而不是 `ok`，符合契约。

## 5. SHA256

```
A791CC9075CA785FFB2D3DACF58B3CB60F3B0F779BDD0AB71B8F4E60727DDAE0  app.js
A84965CEAF7F59FD8C2AD2158E16CA181C62B6BC6380C5CB4D6F5677668851B9  index.html
A127F4DB5655FCF19D485701F68EA1E76BA0B979E8BB3925F5FC39F5BA21307B  style.css
F23312D04695CD576A763452CDBF0B0E0762911B78FA9EBE849E8A8749F4E6F6  tasks.js（未改，与 R41 一致）
042B642AD0F0412CF16C3032DFDB355ED4DB5E80F9EB48DECD6D446F5331DE17  js/game-mode.js（未改）
D8DAC51ACA2AB40BA8339C92B5918099A1EB373ACEBD63B4D215547E550B4425  tests/test_r44_mode_live.py（新增）
```

## 6. 截图

`docs/r44-mode-live/shots/`（1024 与 1440 各 11 张）：
- `*-00-header` 顶栏默认态（PvP + 快照徽标）
- `*-01-settings` 设置面板：在线行情默认未勾选、刷新按钮隐藏
- `*-02-loadout` 配装页价格来源行
- `*-03-ammo` 弹药页「行情：快照（PvP，构建期）」
- `*-04-tasks` 任务板（PvP）
- `*-05-pve` 切 PvE：按钮高亮、任务面板 499、徽标仍 PvP 快照
- `*-06-map` 切回地图（点位按 PvP 过滤）
- `*-07-live-off` / `*-07-live-on` 在线行情关/开
- `*-08-live-refresh-error` 手动刷新 403 红字
- `*-09-live-closed` 关闭后回快照、无新请求

## 7. 未做 / 边界

- 未实现任何「版本 edition」选择器；`DATA_EDITIONS` 为空，等调研结论。
- 未改 `tools/serve.py`、`tools/live_prices.py`、`combat_sim.js`、`release/`、`dist/`；未 git 提交。
- 未新增外网请求；tarkov.dev 仅在用户勾选且服务端 `livePrices.enabled=true` 时才由服务端访问。
