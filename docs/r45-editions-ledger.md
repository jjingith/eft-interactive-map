# R45 账号版本对照卡 留痕

host=HOMONAS user=MASTERJJ at=2026-11-04 03:29:12 +08:00

仓库：`d:\personal\trae\02-塔科夫\eft-interactive-map`（前端独占）
数据来源：`docs/r43-account-editions.md`（只读，未改）；本轮唯一新增的版本数据是 `data/editions.json`。
未 git 提交；未碰 `tools/`、`release/`、`dist/`、`combat_sim.js`。

## 1. 现状与约束（动手前确认）

- R44 已预留 `state.dataScope = { mode, edition }` + `applyDataScope()`，`edition` 是空值；`DATA_EDITIONS = []`。
- 任务数据按模式分文件（`tasks.regular/pve/pvps.json`），价格快照只有一套（PvP 构建期）；
  R43 调研结论：**版本不改变任务集合与价格**，唯一例外是已停售 EOD 的 Nostalgia 任务链。
- 因此本轮 `edition` 只驱动对照卡与说明文案，**不进入**任务 / 任务点位 / 价格 / 实时行情任何加载路径。

## 2. `data/editions.json`

文件头（可溯源）：

- `source`：`docs/r43-account-editions.md`
- `sources`：官方知识库 KB 529 / 534–538、官方购买页、Steam 商店 API + 捆绑包页
- `fetchedAt`：`2026-11-04T02:02:00+08:00`；`region`：`RU/CIS`
- `priceBasis`（价格口径字典，渲染时按 `price.basis` 取文案）：
  - `checkout-display`：购买页当前结算显示价（RU/CIS，数字非递增，很可能是从 Standard 升级的补差价口径，不是绝对售价）
  - `not-for-sale`：官方已停售，购买页无此卡，无价格

5 个版本（字段：`id / status / channel / stashCells / secureContainer / expBonusPct / traderStanding / extraPerks / price{basis}`）：

| id | 名称 / 别名 | status | 仓库 | 安全容器 | 声望 | 经验 | 价格（口径） |
|---|---|---|---|---|---|---|---|
| `standard` | 标准版 / 白边 | available | 10×30 | Alpha 2×2 | +0 | +0% | 3100 rub.（checkout-display） |
| `left-behind` | 留守版 / 遗落版 | available | 10×40 | Alpha 2×2 | +0 | +7% | 1100 rub.（checkout-display） |
| `prepare-for-escape` | 准备逃离版 / PFE | available | 10×50 | Beta 3×2 | +0.2 | +9% | 2200 rub.（checkout-display） |
| `unheard` | 未闻者版 / 蓝边·金边 / TUE | available | 10×72 | Gamma TUE 3×3 | +0.2（Fence +0.5） | +20% | 9200 rub.（checkout-display） |
| `edge-of-darkness` | 黑暗边缘版 / 黑边 / EOD | legacy-discontinued | 10×68 | Gamma EOD 3×3 | +0.2 | +12% | `null`（not-for-sale） |

- `unheard` 带 `channelVariants`（`official-site` 含 Season Pass / `steam` 不含，note 注明官方原文）；
- `edge-of-darkness` 带 `taskOverrides`：`taskId=5d25e4ad86f77443e625e387`（怀旧之情 / Nostalgia），
  reason 写明「EOD 专属任务链，可拿 PMC Pockets；其他版本没有」。

## 3. 前端接线

- 新面板：顶栏「账号」菜单 → `#account-block.account-panel`（右对齐，沿用 `.menu-panel` 的 72vh 滚动容器）。
  5 张卡，每张：名称 + 别名 + 状态徽标（在售绿 / 停售红）、价格 + 口径说明、仓库 / 安全容器 / 商人声望 / 经验加成、
  渠道差异（仅 TUE）、专属权益、EOD 的「打开任务：怀旧之情 →」。
- 数据链路：`loadEditions()` → `state.editions` → `DATA_EDITIONS = doc.editions` →
  `window.GWDataScope.editions = DATA_EDITIONS.slice()`；持久化键 `eftmap.accountEdition`（坏值会被清除）。
- `applyEdition(id)` → `applyDataScope({ edition })` + `editionChoiceSave` + `renderAccountPanel`
  + `revealCurrentEditionCard()`（把当前卡滚进可视区，面板 72vh 放不下 5 张卡）。
- 文案：面板固定写「任务与价格不随版本变化…唯一例外是已停售的 Edge of Darkness（黑边）附带 Nostalgia 怀旧任务链」；
  Nostalgia 按钮 → `closeAccountPanel()` → `setView("tasks")` → `GWTasks.mount()/open()/openTask(taskId)`，
  500ms 重试 ≤8 次，失败给「本地任务数据里没有找到 …」，成功在面板里回显「已打开任务：怀旧之情」。

## 4. 如何证明「切换版本不重载数据」

代码层：`applyDataScope()` 中 edition 分支只调用 `renderAccountPanel()`，且位于 mode 分支之前；
分支内不出现 `applyTaskPointMode / fetchLivePrices / refreshPriceViews / applyDataScope`（`tests/test_r44_mode_live.py` 源码断言）。

运行层（Chrome CDP 实测，1024 与 1440 两次相同）：

| 动作 | `GWTasks.state.order.length` | 价格徽标 | 期间新请求 |
|---|---|---|---|
| 打开面板（未选版本） | 503 | 快照（PvP，构建期） | — |
| 点 Standard | 503 | 快照（PvP，构建期） | `[]` |
| 点 EOD（停售） | 503 | 快照（PvP，构建期） | `[]` |
| 点 Nostalgia 跳转 | 503 | 快照（PvP，构建期） | `[]` |
| 重开面板 | 503 | 快照（PvP，构建期） | `[]` |

全程 `live-prices` 请求 0 条（`LIVE_REQS=[]`）；localStorage 依次写 `standard` → `edge-of-darkness`。

## 5. 布局实测（面板为滚动容器）

| 视口 | 面板 | 卡片宽 | 横向溢出 | 内部溢出 |
|---|---|---|---|---|
| 1424×805（1440 窗） | 500×580，scrollHeight 1227 | 229 | 无 | 无 |
| 1008×805（1024 窗） | 460×580，scrollHeight 1243 | 209 | 无 | 无 |

- `@media (max-width:1180px)` 面板 460；`(max-width:860px)` 面板收进视口、卡片改单列。
- 点选后自动把当前卡 `scrollIntoView({block:"nearest"})`，避免「当前：黑边」但高亮卡在可视区外。

## 6. 测试 / 静态检查

- `python -m pytest tests -q`：**5 failed, 1703 passed, 1 skipped in 101.70s**
  - 5 failed 全部是既有配枪失败：`test_r19_11_round`、`test_r19_13_round`、`test_r19_1_round`、`test_r19_5_round`、`test_r6_gun_workbench`（已知）。
  - 本轮新增 `tests/test_r45_editions.py`：**13 passed**（schema/字段完整性、数值对照、价格口径、TUE 渠道、EOD 唯一 override、taskId 三模式存在、面板与卡片渲染、菜单/启动接线、edition 不重载、持久化校验、Nostalgia 跳转、窄屏 CSS）。
- `node --check app.js / tasks.js / js/game-mode.js`：全部通过。
- ES5 扫描（新增代码区间 440–470 / 560–1305 / 1650–1700 / 1750–1830 / 2355–2380，跳过注释行）：
  `RANGE_ES5_VIOLATIONS=0`（无 let/const/箭头/模板字符串/class/展开）。`tasks.js` 由既有 `test_r41_tasks_ui.py::test_tasks_js_is_es5` 覆盖。

## 7. SHA256（本轮改动文件）

```
app.js                94d478f3baab15518c92d726be2ea1383864c46b31581fcd0f76da1b5a893620
index.html            f0549f6fc2e1417be54980eafd19a267488e41314435ef22b2854f399ebc4ce0
style.css             54a41a4d05afeb6d5b43b89294d8660ba17604a9595a5c83983dc50a402b1fc0
data/editions.json    9e83634c1c244826ff1f476ead13eb87baa128cbe16cb5ffad88fb72dcd3bf05
tests/test_r45_editions.py   bf3dac8631d5cf1f5225952648c149209b3a0ed8966cb42220f46ba892ee2683
tests/test_r44_mode_live.py  b081d34efc6a9c0f1b846f6c1f1cf002a475367681a4e84b8fa2717f02b56598
```

## 8. 截图（`docs/r44-mode-live/shots/`）

- 1024：`1024-10-account.png`（面板首屏，5 卡 2 列）、`1024-11-account-standard.png`、`1024-12-account-eod.png`（EOD 停售卡 + 怀旧之情按钮）、`1024-13-nostalgia.png`（任务详情）、`1024-14-account-reopen.png`
- 1440：`1440-10-account.png`、`1440-11-account-standard.png`、`1440-12-account-eod.png`、`1440-13-nostalgia.png`、`1440-14-account-reopen.png`
- 顶栏 / 窄屏（R45-B）：`1440-16-header.png`、`1024-16-header.png`、`1440-18-header-narrow.png`（860 模拟）、`1440-19-account-narrow.png`
- 刷新实测（R45-B）：`1440-15-live-enabled.png`（202 后）、`1440-15-live-disabled.png`（409 后）

## 9. 未做 / 边界

- 版本切换不写任务进度、不筛选任务、不改价格，面板中也已如实写明。
- EOD 的 Nostalgia 只是「跳到本地任务详情」的入口，不改任务数据；任务集合本身仍三模式共用。
- 价格仍按「结算显示价」口径展示，未换算全价，未当售价写死。

## 10. R45-B：refresh 鉴权配合 + 顶栏打磨

host=HOMONAS user=MASTERJJ at=2026-11-04 03:52:01 +08:00

### 10.1 两处改动

1. `app.js::refreshLiveNow()` 的 POST 加请求头 `X-EFTMap-Client: web`（同源 fetch 由浏览器自带 `Origin`/`Referer`，未手写）。
   未加 `X-EFTMap-Token`；无请求体仍保持不变，避免 403/409 提前返回时在 keep-alive 连接里留脏数据。
2. 403 分支文案改为 `刷新被拒绝：请从本机同源页面调用。`（不再写「桌面壳令牌 / 浏览器无法触发」）；
   `index.html` 的刷新说明同步改为「刷新需要服务端允许（livePrices.enabled）；本机同源页面可直接刷新，跨站请求会被拒绝」。
3. `tests/test_r44_mode_live.py` 同步锁定：新 403 文案、`"X-EFTMap-Client": "web"` 必须存在、带引号的 `X-EFTMap-Token` 不得出现。

> 本地 8791 服务此前是旧进程，未加载后端修复；本轮重启了它（`python tools/serve.py --port 8791`）后才得到新契约。
> 测试用的 `livePrices.enabled` 只临时改在本机用户配置，测完已恢复原文件（`enabled=false`）。

### 10.2 刷新实测（真实浏览器点击，桌面端 1440）

开启（`livePrices.enabled=true`）：

```
POST api/live-prices/refresh  -> 202  {"via":"web","enabled":true}
GET  api/live-prices?mode=regular -> 200 {"enabled":true,"source":"https://json.tarkov.dev/regular/items"}
徽标：实时（tarkov.dev，16 分钟前）；刷新完成后缓存文件 mtime 03:53:49，条目 3540
```

关闭（`livePrices.enabled=false`）：

```
POST api/live-prices/refresh -> 409 {"error":"disabled","enabled":false}
GET  -> 200 {"enabled":false,"source":"snapshot"}；文案「刷新被拒绝（HTTP 409）：在线行情未启用…」
外网：无。页面请求仅 api/live-prices*；服务端 last-attempt.json mtime 保持上一次成功刷新的 03:53:49 未变。
```

两次都在点击后等 9 秒：`idleRequests=[]`，资源条目数不再增长（无额外请求、无定时器泄漏）。

### 10.3 打磨

- 窄屏（≤860）发现真问题：账号面板挂在「账号」按钮的 `.menu-wrap` 上，`right:0` 相对该按钮而非视口，实测面板 `left=-299` 被推出屏幕。
  改为 `position:fixed; left:8px; right:8px; top:68px; width:auto; max-height:calc(100vh-78px)`，860 实测 `x=8 w=844 right=852`，单列卡片，无横向溢出。
- 价格徽标回退态补上快照模式：`实时不可用，已回退快照（PvP）`（原先只有「已回退快照」，在 PvE/PvPS 下不够明确）；
  PvE / PvPS 的 title 仍分别说明「PvPS 无实时行情接口 / PvE 模式下本地没有 PvE 快照，这不是 PvE 价格」。
- 顶栏实测：1440 单行（menubar 35px），1024 与 860 均为两行（65px），模式组 + 徽标整体换到第二行，无横向溢出、无标签截断；
  账号抽屉与任务页共用同一套 XP 令牌（`.menu-panel`/琥珀高亮/同字号），视觉一致。

### 10.4 测试与静态检查（R45-B 结束时）

- `node --check app.js / tasks.js / js/game-mode.js`：通过。
- ES5 扫描（新增代码区间）：`RANGE_ES5_VIOLATIONS=0`。
- `python -m pytest tests -q`：**5 failed, 1703 passed, 1 skipped in 100.87s**；5 个仍是既有配枪失败（r19_11、r19_13、r19_1、r19_5、r6_gun_workbench）。
- `tests/test_r44_mode_live.py` + `tests/test_r45_editions.py` 合跑：**28 passed**。
- 未 git 提交；未碰 `tools/`、`release/`、`dist/`、`combat_sim.js`。
