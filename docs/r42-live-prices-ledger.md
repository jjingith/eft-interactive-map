host=HOMONAS user=MASTERJJ at=2026-11-04T03:10:29+08:00

> 本文件第一版落于 `2026-11-04T01:38:00+08:00`；此处为**第二轮（前端接线后的契约修复）**续写。
> 历史内容原样保留，新增内容见文末「## 9. 第二轮修复」及之后。

# R42 可选在线行情（默认离线）留痕

## 0. 结论（先看这里）

1. **修正了模式标注错误**：`json.tarkov.dev/regular/items` 的真实模式是 **PvP（常规）**，不是 PvE。
   旧文档 / 旧脚本 / 旧元数据把它写成 PvE，并把 PvP 写成「无可用上游」，已全部纠正。
   现有 `data/flea-prices.json` 的**价格数值一条未改**，只改写元数据 + 新增模式字段；
   `data/flea-levels.json` 同样只改元数据（`items` / `levels` 经 SHA256 摘要校验与原始一致）。
2. 新增 `tools/live_prices.py`（纯标准库）：`--fetch` 抓 PvP/PvE 两套价格到本地缓存，`--status` 只读状态。
   已在代理 `127.0.0.1:7896` 上完成真实抓取与 304 条件请求验证。
3. `tools/serve.py` 新增只读接口 `/api/live-prices`、`/api/live-prices/status` 与异步刷新
   `POST /api/live-prices/refresh`；**请求线程绝不联网**；服务启动默认不联网。
4. 配置新增 `livePrices` 段，**默认 `enabled=false`**；缺失即关闭（向后兼容）。
5. 新增 22 个离线 pytest，全部通过；全量 `pytest tests -q` = **1646 passed / 1 skipped / 6 failed**，
   6 个失败全是配枪 / 前端用例（`app.js` 正被另一会话改造），与本轮后端改动无关，未修、未跳过、未弱化。

## 1. 改动文件与 SHA256

本轮**没有** `git commit`，**没有**动 `release/`、`dist/`、`build/`（`build/_staging` 仅作为只读恢复源）。

| 文件 | SHA256 | 说明 |
| --- | --- | --- |
| `tools/live_prices.py` | `C177FAF0A30A15B2D371004A3A2AF20BEC41BF307EB1EAAABE77C654C12662BD` | 新增：抓取器 / 状态命令 |
| `tools/serve.py` | `0F06BC29C40F857560B94ECE236F0AF191A5FFF0E6CF9EC401C14ABB5BCA6636` | 新增 3 个接口 + 启动联网改为开关控制 |
| `tools/config.py` | `0DC0323EC8E630C7C489E4E5EA811F6EE4280DA6747C1D3D5A674B9B9FE98E2C` | 新增 `livePrices` 段与收敛逻辑 |
| `tools/r20_fetch_prices.py` | `E4D4D64325E515C50CF6D454F520AE43F4A0E66E298C4FA889A56DF0679B7CF9` | 纠正模式注释 + 未来产物带模式字段 |
| `tools/r20_fetch_flea_levels.py` | `8F59D6EDA6C06408CCAE3D320DCA1936B2F1288B13DCE566B9716FF1D8B6B32B` | 纠正模式注释 + 产物带模式字段 |
| `tests/test_r42_live_prices.py` | `7F9F18760D7A86EC119501602795589A03AF3CA2358147E3A7F53C8BB1C21B38` | 新增 22 个离线测试 |
| `README.md` | `8A727E4C99A2FA6C21D2E8415C175A6FAA839697C2FB006755E978E88D07679C` | 「不使用第三方库」→「运行期不引入」；新增在线行情说明 |
| `docs/USAGE.md` | `F40B62CBDCCBE6D7E4A55F69D4D52DF864190AFE7FA07B2B14879A5FB4DA76A0` | 新增「可选在线行情」章节 |
| `data/flea-prices.json` | `EB5C6708458BB27CCB3FBD9DE06C9D5C7918D1A010ED53791C809B1A04369144` | **仅元数据**：新增 `priceMode=pvp` 等，`items` 5124 条未动 |
| `data/flea-levels.json` | `E7E062595EC50EEF97FD432ACC1D1072296F39BF4E148D1403458A9DF15FF0C6` | **仅元数据**：新增 `priceMode=pvp` 等，`items` 5480 条 / `levels` 汇总未动 |
| `docs/r42-live-prices-ledger.md` | （本文件，不列自身哈希） | 本留痕 |

本地行情缓存（不在仓库内，供 `--status` / 接口读取）：

| 文件 | SHA256 |
| --- | --- |
| `%LOCALAPPDATA%\EFTMap\cache\live-prices-regular.json` | `55D1BFF56765FE8FE107801830AF2604A73012269332D4EDE81B1E53A7158D2D` |
| `%LOCALAPPDATA%\EFTMap\cache\live-prices-pve.json` | `5233FE646508AE7D1EEA40B54C4A2D4367DC2211CDF6A7D873702BE52E3A95CC` |

### 1.1 数据文件为什么只改元数据、不重抓

- 任务要求优先修标注、且默认不要覆盖既有 `flea-prices.json` 数值；重新抓取会顺带改掉价格
  （上游约 10 分钟一版），无法区分「修正标注」和「行情变化」，所以选择**原位只改元数据**。
- 校验方式：改写前后对 `items` 做规范化 JSON 的 SHA256 摘要比较，值完全一致。
- `flea-levels.json` 改写脚本第一版漏拷了 `items` 键（只保留了 `levels` 汇总）；已从
  `build/_staging/data/flea-levels.json` 恢复，并先与 `dist/EFTMap/_internal/data/flea-levels.json`
  逐字节摘要比对一致后才写回，最终 `items` 5480 条与原始完全一致。此过程如实记录，不掩盖。
- 是否应为 PvE 单独产出一份：**应该**，但不在本轮落盘。PvE 与 PvP 价格差异很大，
  混用会误导；已由 `tools/live_prices.py --fetch --mode pve` 支持单独抓取到
  `live-prices-pve.json`，构建期快照仍只保留 PvP 一份（避免仓库体积翻倍、也避免前端误用）。

## 2. 模式标注纠正的证据

2026-11-04 01:10–01:15（本地时间）通过代理实测：

- 5498 个物品 id 同时存在于 `/regular/items` 与 `/pve/items`；
- 其中两侧都有 `lastLowPrice` 的 **3529** 个 id 里，同值仅 **84** 个（**2.38%**）；
- 结论：`regular` = **PvP**，`pve` = **PvE**。若 `regular` 真是 PvE，同值比例应接近 100%。

写进数据的字段（`data/flea-prices.json`）：

```json
"gameMode": "regular",
"gameModeSemantics": "上游路径键：regular(PvP) / pve(PvE)；gameMode 只是路径键，不是游戏模式标签",
"priceMode": "pvp",
"modeLabel": "PvP（常规）",
"modeNote": "……5498 个物品 id 同时存在；两侧都有 lastLowPrice 的 3529 个里同值仅 84 个（2.38%）……",
"modeVerifiedAt": "2026-11-04T01:35:00+08:00",
"modeEvidence": {"method": "...", "commonItemIds": 5498, "commonPricedIds": 3529,
                  "sameLastLowPrice": 84, "samePct": 2.38, "verdict": "regular = PvP"}
```

保留 `gameMode: "regular"` 的原因：前端按这个键取数（`regular` → 「PvP」标签本来就是对的），
改成 `pvp` 会破坏既有契约；因此把它明确为「上游路径键」，另加 `priceMode` 表达真实模式。

## 3. 代理与联网实测

### 3.1 代理

- 用户指定端口：`127.0.0.1:7896`（非 7890）。`Test-NetConnection 127.0.0.1 -Port 7896` → **TcpTestSucceeded: True**。
- 代理方式：`urllib` + `ProxyHandler({http/https: http://127.0.0.1:7896})`；
  本地地址始终直连（`NO_PROXY=localhost,127.0.0.1,::1`），TLS 证书校验保持开启
  （显式 `ssl.create_default_context()`，**未关闭校验**）。

### 3.2 实际访问成功的外部网址

| 网址 | 结果 |
| --- | --- |
| `https://json.tarkov.dev/regular/items` | HTTP 200，17,344,055 B，`ETag: "e869a14442c8766218d23d4f52026841"`，`Last-Modified: Tue, 03 Nov 2026 17:10:34 GMT` |
| `https://json.tarkov.dev/pve/items` | HTTP 200，17,274,431 B，`ETag: "d45bcf7675223f1473d1e58e34235f73"`，`Last-Modified: Tue, 03 Nov 2026 17:11:01 GMT`，SHA256 `c50dccad…0ecfb44` |
| 同上 + `If-None-Match: "e869a14442c8766218d23d4f52026841"` | **HTTP 304**（无响应体），已由 `live_prices.py --fetch --force` 复现，缓存复用成功 |

抓取时间：`regular` 200 下载后，第二次条件请求 304；`pve` 200 下载。
缓存内 `checkedAt`：`regular 2026-11-04T01:15:25+08:00`、`pve 2026-11-04T01:15:18+08:00`。

### 3.3 失败 / 不可用资源

| 网址 | 结果 |
| --- | --- |
| `https://json.tarkov.dev/pvp/items` | HTTP 404（上游把 PvP 挂在 `regular` 路径下） |
| `https://api.tarkov.dev/graphql` | 422 / GraphQL unavailable，未采用 |
| 通用 UA `Mozilla/5.0` 的请求 | 曾被上游 403 拒绝；改用完整浏览器 UA 后正常（工具内已固定完整 UA） |

未访问 db4tarkov 的 worker / `json/core/changes.json`（无许可声明且存在 UA+Origin 门禁），
只走 tarkov.dev 上游。

## 4. `tools/live_prices.py` 用法

```bash
python tools/live_prices.py --fetch                 # PvP + PvE，TTL 内自动跳过
python tools/live_prices.py --fetch --mode pve      # 只抓 PvE
python tools/live_prices.py --fetch --force         # 忽略 TTL，发条件请求（可拿 304）
python tools/live_prices.py --fetch --no-proxy      # 直连（默认走 127.0.0.1:7896）
python tools/live_prices.py --status                # 人类可读状态（不联网）
python tools/live_prices.py --status --json         # 机器可读状态
```

- 缓存目录：`%LOCALAPPDATA%\EFTMap\cache\`（可用 `EFTMAP_CACHE_DIR` / `--cache-dir` 覆盖）。
- 写盘：临时文件 + `os.replace` 原子替换；失败只写 `.last-attempt.json`，旧缓存原样保留。
- TTL 默认 600 秒；缓存内 `checkedAt` 在 TTL 内时 `--fetch` 直接跳过。
- 上游字段：`lastLowPrice→l`、`avg24hPrice→a`、`updated→u`、`basePrice→b`、
  `sellToTrader[].priceRUB` 最大值 `→tb`（商人收购价）、对应商人 id `→tn`。
- 退出码：

| 码 | 含义 |
| --- | --- |
| 0 | 成功（含 304 复用 / TTL 内跳过） |
| 1 | 网络失败（代理不可达 / 连接失败 / HTTP 非 200/304） |
| 2 | 上游数据校验失败（物品数异常 / 无价格字段 / 304 但无本地缓存） |
| 3 | 缓存写入失败 |
| 4 | 另一个抓取进程持锁，本轮跳过 |

## 5. 接口契约（给前端，可直接接 UI）

统一的 `Content-Type: application/json; charset=utf-8`，所有接口都在本机回环。

### 5.1 `GET /api/live-prices?mode=regular|pve`

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | bool | 请求成功且拿到可展示数据。开关关闭时仍为 `true`（因为「显示快照」是正常分支） |
| `enabled` | bool | `livePrices.enabled` 当前值 |
| `mode` | `"regular"` / `"pve"` | 上游路径键（请求参数） |
| `priceMode` | `"pvp"` / `"pve"` | 真实游戏模式 |
| `label` | string | `PvP（常规）` / `PvE` |
| `available` | bool | 是否有可读缓存 |
| `stale` | bool | 见 5.4 |
| `ageSec` | int / null | 距缓存 `checkedAt` 的秒数；无缓存为 null |
| `ttlSec` | int | 当前 TTL |
| `updatedOldest` | string / null | 数据内最旧 `updated`（带时区 ISO 8601） |
| `updatedNewest` | string / null | 数据内最新 `updated` |
| `dataAgeSec` | int / null | 距 `updatedNewest` 的秒数（辅助展示，不参与 `stale`） |
| `count` | int | 返回的条目数（有价格字段的物品数） |
| `prices` | object | `{物品id: {l?,a?,u?}}`；只含存在字段，缺失时省略该键 |
| `source` | string | 开启且可用时为上游 URL；关闭时为 `"snapshot"` |
| `snapshot` | string | **仅关闭时出现**：`"data/flea-prices.json"` |
| `cachePath` | string | 本地缓存绝对路径 |
| `fetchedAt` / `checkedAt` | string / null | 缓存抓取 / 最后校验时间 |
| `error` | string / null | `"no-cache"` / `"unreadable"` / `null` |

示例 A —— **PvP（`mode=regular`，已开启且刚抓取）**：

```json
{
  "ok": true,
  "enabled": true,
  "mode": "regular",
  "priceMode": "pvp",
  "label": "PvP（常规）",
  "available": true,
  "stale": false,
  "ageSec": 58,
  "ttlSec": 600,
  "updatedOldest": "2026-11-03T23:38:05+08:00",
  "updatedNewest": "2026-11-04T01:08:05+08:00",
  "dataAgeSec": 420,
  "count": 3538,
  "prices": {
    "5447a9cd4bdc2dbd208b4567": {"l": 44415, "a": 69408, "u": "2026-11-03T17:08:05.000Z"}
  },
  "source": "https://json.tarkov.dev/regular/items",
  "cachePath": "C:\\Users\\MASTERJJ\\AppData\\Local\\EFTMap\\cache\\live-prices-regular.json",
  "fetchedAt": "2026-11-04T01:15:15+08:00",
  "checkedAt": "2026-11-04T01:15:25+08:00",
  "error": null
}
```

示例 B —— **PvE（`mode=pve`）**：

```json
{
  "ok": true,
  "enabled": true,
  "mode": "pve",
  "priceMode": "pve",
  "label": "PvE",
  "available": true,
  "stale": false,
  "ageSec": 58,
  "ttlSec": 600,
  "updatedOldest": "2026-11-03T23:38:05+08:00",
  "updatedNewest": "2026-11-04T01:08:05+08:00",
  "dataAgeSec": 420,
  "count": 3744,
  "prices": {
    "5447a9cd4bdc2dbd208b4567": {"l": 11111, "a": 63715, "u": "2026-11-03T17:08:05.000Z"}
  },
  "source": "https://json.tarkov.dev/pve/items",
  "cachePath": "C:\\Users\\MASTERJJ\\AppData\\Local\\EFTMap\\cache\\live-prices-pve.json",
  "fetchedAt": "2026-11-04T01:15:18+08:00",
  "checkedAt": "2026-11-04T01:15:18+08:00",
  "error": null
}
```

示例 C —— **开关关闭（默认）**，前端显示「快照」：

```json
{
  "ok": true, "enabled": false, "mode": "regular", "priceMode": "pvp",
  "label": "PvP（常规）", "available": false, "stale": true, "ageSec": null,
  "ttlSec": 600, "updatedOldest": null, "updatedNewest": null, "count": 0,
  "prices": {}, "source": "snapshot", "snapshot": "data/flea-prices.json",
  "cachePath": "C:\\Users\\MASTERJJ\\AppData\\Local\\EFTMap\\cache\\live-prices-regular.json",
  "error": null
}
```

示例 D —— **已开启但无缓存**（`ok=false`，HTTP 200；前端回退快照）：

```json
{"ok": false, "enabled": true, "mode": "pve", "priceMode": "pve", "available": false,
 "stale": true, "ageSec": null, "count": 0, "prices": {},
 "error": "no-cache", "source": "https://json.tarkov.dev/pve/items"}
```

### 5.2 `GET /api/live-prices/status`

```json
{
  "ok": true, "enabled": false, "mode": "regular", "ttlSec": 600, "source": null,
  "fetcher": "tools/live_prices.py", "cacheDir": "C:\\Users\\MASTERJJ\\AppData\\Local\\EFTMap\\cache",
  "proxy": "http://127.0.0.1:7896",
  "modes": {
    "regular": {"mode": "regular", "priceMode": "pvp", "exists": true, "readable": true,
                "count": 3538, "fileMtimeIso": "2026-11-04T01:15:25+08:00",
                "ageSec": 58, "ttlSec": 600, "inTtl": true, "stale": false,
                "updatedOldest": "2026-11-03T23:38:05+08:00",
                "updatedNewest": "2026-11-04T01:08:05+08:00",
                "lastAttempt": {"at": "2026-11-04T01:15:25+08:00", "ok": true, "status": 304}},
    "pve": {"mode": "pve", "priceMode": "pve", "exists": true, "readable": true,
            "count": 3744, "inTtl": false, "stale": true,
            "lastAttempt": {"at": "2026-11-04T01:15:18+08:00", "ok": true, "status": 200}}
  }
}
```

每个 `modes[mode]` 的字段：`mode/priceMode/label/source/cachePath/cacheDir/exists/readable/fetchedAt/checkedAt/fileMtime/fileMtimeIso/ageSec/ttlSec/inTtl/stale/count/updatedOldest/updatedNewest/dataAgeSec/error/lastAttempt`。

### 5.3 `POST /api/live-prices/refresh`

- 仅接受回环地址（`127.0.0.1` / `::1`），否则 `403 {"ok":false,"error":"refresh 只允许本机"}`；
- 必须带 `X-EFTMap-Token`，与环境里的 `shutdown_token` 一致（`hmac.compare_digest`）；
  未配置或错误 → `403 {"ok":false,"error":"token 无效或未配置"}`（浏览器模式下没有 token，属预期）；
- `enabled=false` → `409 {"ok":false,"error":"disabled","reason":"…默认离线，不发起联网"}`，**不联网**；
- 可选请求体 `{"mode":"regular"|"pve"}`，缺省用配置 `mode`；非法 → `400 bad-mode`；
- 启动成功 → `202 {"ok":true,"started":true,"mode":"…","reason":"已在后台启动在线行情更新（…）","status":{…}}`；
- 启动失败 → `500 {"ok":false,"started":false,…}`。
- 该接口只 `Popen` 子进程，立即返回；真正下载在后台，页面无需等待。

### 5.4 `stale` 判定规则

```
stale = (enabled == false)                      // 关闭时一律按快照处理
        or (无缓存 / 缓存不可读)
        or (ageSec > ttlSec)                    // ageSec = now - checkedAt
```

- `ageSec` 用缓存里最后一次**校验成功**的 `checkedAt`（200 或 304 都会刷新它），不是文件 mtime；
- 上游逐条 `updated` 的分布单独放在 `updatedOldest` / `updatedNewest` / `dataAgeSec`；
  即使 `stale=false`，数据本身也可能滞后（上游约 10 分钟一版、最长滞后 50–73 分钟），
  前端如需「数据新鲜度」应展示 `dataAgeSec`，不要直接拿 `ageSec` 当行情新鲜度。

### 5.5 错误码汇总

| HTTP | body 关键字段 | 场景 |
| --- | --- | --- |
| 400 | `error:"bad-mode"`、`allowed:["regular","pve"]` | 查询参数 / refresh 请求体里的 mode 非法 |
| 403 | `error:"refresh 只允许本机"` | 非回环调用 refresh |
| 403 | `error:"token 无效或未配置"` | refresh 缺 token / token 错误 |
| 409 | `error:"disabled"` | refresh 但开关关闭（不联网） |
| 413 | `error:"请求体过大"` | refresh 请求体超限 |
| 500 | `ok:false, started:false` | 抓取器不存在 / 子进程启动失败 |
| 200 | `ok:false, error:"no-cache" / "unreadable"` | 开关开启但缓存缺失 / 损坏 |

## 6. 配置项

`eftmap.config.json` 新增（缺失即按下表默认值，向后兼容）：

```json
"livePrices": {
  "enabled": false,
  "mode": "regular",
  "ttlSec": 600,
  "source": null
}
```

| 键 | 默认 | 收敛规则 |
| --- | --- | --- |
| `enabled` | `false` | 仅接受真值（`true/1/"true"` 等按现有 `_as_bool`） |
| `mode` | `"regular"` | 只允许 `regular` / `pve`，其它回落 `regular` |
| `ttlSec` | `600` | 钳到 `[60, 3600]`，脏值回落 `600` |
| `source` | `null` | 只接受 `http(s)://` 开头，否则丢弃；仅覆盖配置 `mode` 那一套 |

联网边界：`enabled=false` 时服务启动、页面加载、三个 GET 接口**都不联网**；
只有 `--fetch` 或 `POST /api/live-prices/refresh`（且开关开启）才会访问 `json.tarkov.dev`。

## 7. 测试

- 新增 `tests/test_r42_live_prices.py`：**22 passed**。
  覆盖：缓存解析与 TTL、`updated` 最旧/最新、304 复用（含 `If-None-Match` 断言）、
  304 但无缓存、代理不可达（关闭的本机端口）、HTTP 错误保留旧缓存、
  原子写成功、CLI status、配置默认/收敛、
  接口 `enabled=false`、非法 mode、status、refresh token/回环/关闭/开启、无缓存分支。
  全部使用固定样本 JSON 与假 opener，**不真联网**；时间用显式 `now` 参数，不依赖系统时钟漂移。
- 组合回归：`pytest tests/test_r20_5_flea_prices.py tests/test_r20_6_preset_parity.py tests/test_r42_live_prices.py -q` → **62 passed**。
- 全量：`python -m pytest tests -q` → **1646 passed, 1 skipped, 6 failed**（≈97s）。
  6 个失败：`test_r19_1_round.py::test_candidate_columns_match_reference_order`、
  `test_r19_5_round.py::test_zoning_is_generic_semantic_rules`、
  `test_r19_11_round.py::test_hide_incompat_filters_without_touching_data`、
  `test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree`、
  `test_r19_25_round.py::test_C_trader_enums_are_data_driven`、
  `test_r6_gun_workbench.py::test_gun_workbench_business_logic`。
  均为配枪 / 前端用例（`gunPushHistory is not defined`、找不到 `gunColumns` 等），
  由另一会话对 `app.js` 的改造造成；按约定**未修、未跳过、未弱化**。相对原「已知 5 个」多出的
  `test_r19_11` 同为前端用例，非本轮代码造成。

## 8. 未改前端声明

本轮**未修改**以下任何文件：`index.html`、`style.css`、`app.js`、`combat_sim.js`、`assets/`、
`data/traders.json`（该文件当前不存在）、任务页相关文件。

观察到但未回退的非本轮改动（仅记录）：

- `app.js`（1,128,529 B，2026-11-03 22:40:32）、`index.html`（53,885 B，22:40:50）、
  `style.css`（264,825 B，21:21:24）均被另一会话改动；`git status` 显示为 `M`。
- 全量测试里 6 个配枪失败即由这些改动引起（`gunPushHistory` 未定义等），本轮不介入。

本轮只改 `tools/`（新增 `live_prices.py`、修 `serve.py` / `config.py` / 两个 r20 脚本）、`tests/`、
`docs/`、`README.md`，以及任务明确允许的数据元数据（`data/flea-prices.json`、`data/flea-levels.json`）。

## 9. 第二轮修复（前端接线后的两个后端契约问题）

本轮只改 `tools/serve.py`、`tests/test_r42_live_prices.py`、`docs/USAGE.md`、`README.md`
与本文件；`tools/live_prices.py` **未改动**（缓存/抓取逻辑保持原样）。

### 9.1 问题 1：refresh 鉴权顺序与浏览器模式可用性

**修前（实测现象）**：`POST /api/live-prices/refresh` 先判 `X-EFTMap-Token`，再判开关。
浏览器模式（`启动项目.bat` 起的服务、无桌面壳）没有 token → 永远 **403**，按钮等于不可用，
而且即使 `livePrices.enabled=false`，也要先被 403 而不是先得到 409。

**修后判定顺序**（`serve.py::_handle_live_prices_refresh`）：

1. 先读尽请求体（有界 64 KB，见 9.2）；
2. `livePrices.enabled=false` → **409 disabled**，不联网、不要求 token、不查来源；
3. 来源与凭据 → 非回环 / 凭据不匹配 → **403**；
4. 解析 `mode`（非法 → 400，此时 body 已读完，连接仍可复用）；
5. 合法才 `spawn_live_fetch`，返回 **202**，响应带 `via: "token" | "web"`。

**选用的免 token 方案：b —— 回环 + `X-EFTMap-Client: web` + 同源 `Origin`/`Referer`。**

理由：

- 页面**完全不需要接触 token**：token 是桌面壳持有的秘密，注入到 HTML / 由 `/api/runtime`
  下发都会把它暴露给页面脚本与浏览器扩展，等于取消 token 的意义（方案 a 不选）。
- 自定义头会让**跨站 POST 先触发 CORS 预检**，而本服务对所有 `OPTIONS` 只回 `Allow`、
  **不返回任何 `Access-Control-Allow-*`**，浏览器因此拦下跨站调用；这是浏览器强制的，
  不依赖服务端自觉（方案 c 只靠「回环」判断，任意网页都能用回环地址 POST，不满足 CSRF 要求）。
- 再叠一层同源校验：`Host` 必须是回环名（`127.0.0.1` / `localhost` / `::1`），且
  `Origin`（或 `Referer`）的 `netloc` 必须与 `Host` 完全一致（scheme 只认 http/https）。
  这同时挡住 DNS rebinding（`Host` 被解析成外站域名）与非浏览器脚本伪造（缺 Origin/Referer 直接拒）。
- 桌面壳路径**原样保留**：带 `X-EFTMap-Token` 时仍走 `hmac.compare_digest` 校验，
  成功返回 `via:"token"`；token 错仍 403。token 优先于网页路径。

**鉴权矩阵（全部为真实本地 socket 测试覆盖）**：

| `enabled` | 来源 | 凭据 / 头 | 结果 |
| --- | --- | --- | --- |
| false | 任意 | 任意（含错误 token、含 body） | **409 `disabled`**，不启动抓取 |
| true | 非回环（如 10.1.2.3） | 任意 | **403** |
| true | 回环 | `X-EFTMap-Token` 正确 | **202**，`via:"token"` |
| true | 回环 | `X-EFTMap-Token` 错误（非空） | **403** `token 无效` |
| true | 回环 | 无 token + `X-EFTMap-Client: web` + 同源 `Origin` | **202**，`via:"web"` |
| true | 回环 | 无 token + `X-EFTMap-Client: web` + 同源 `Referer`（无 Origin） | **202**，`via:"web"` |
| true | 回环 | 无 token + `X-EFTMap-Client: web` + 外站 `Origin` | **403**（跨站） |
| true | 回环 | 无 token + `X-EFTMap-Client: web` + 无 Origin/Referer | **403** |
| true | 回环 | 无 token、无网页头 | **403**（缺 token 或网页头） |
| true | 回环 | 带 token，同时 Origin 为外站 | **202**（token 路径不变，桌面壳不是浏览器） |

**为什么不会被任意站点触发联网抓取**：

1. 跨站请求带自定义头 → 浏览器先发 `OPTIONS` 预检；本服务返回 204 + `Allow`，
   **没有 `Access-Control-Allow-Origin` / `-Headers`** → 预检失败，真正的 POST 不会发出。
2. 即使绕过预检（非浏览器客户端），服务端仍要求回环来源 + 同源 `Origin`/`Referer`；
   伪造 `Origin` 为 `http://127.0.0.1:<port>` 需要先知道端口（页面同源自然知道，外部站点不知道），
   且 `Host` 必须是回环名，DNS rebinding 也会被同源比对挡住。
3. `enabled=false` 时联网路径根本不进入（409 在鉴权之前），默认离线立场不变。

### 9.2 问题 2：keep-alive 下提前返回导致 501

**修前**：POST 带 JSON body、服务端在 403/409 直接返回时**没有读完请求体**，
残留字节被 `BaseHTTPRequestHandler` 当成下一条请求行 → 同一 keep-alive 连接上的下一次 GET
收到 **501 Unsupported method**。前端当时只能靠「不带 body」规避，根因仍在。

**修后**：新增 `_read_request_body(limit)`，`_handle_live_prices_refresh` **第一步**就调用它：

| 请求形态 | 处理 | 连接 |
| --- | --- | --- |
| `Content-Length` 正常 | `rfile.read(length)` 读尽并丢弃 | 保留（keep-alive 可复用） |
| 无 `Content-Length` | 按 0 处理，**不阻塞** | 保留 |
| `Transfer-Encoding`（分块） | 411 | **显式 `Connection: close`** |
| `Content-Length` 非法 / 负数 / 截断 | 400 | **显式 `Connection: close`** |
| `Content-Length` > 64 KB | 413 | **显式 `Connection: close`** |

因此 400/403/409 及 mode 解析失败的提前返回都是「读完再回」，同连接下一次 GET 正常 200；
读不干净的情况（411/413/非法长度/截断）主动关连接，两侧都不留脏数据。
`_send_json` 增加 `close_connection` 参数（发 `Connection: close` 并置 `self.close_connection=True`）。

**`OPTIONS` 与缺 `Content-Length` 不会卡死**：新增 `do_OPTIONS`（204 + `Allow: GET, POST, OPTIONS`，
无 CORS 允许头），预检立即返回；缺 `Content-Length` 的 POST 按 0 长度处理，不做任何 `read`。

### 9.3 一并核对

- `GET /api/live-prices?mode=...` 在 `enabled=false` 时仍是 **HTTP 200**、`source:"snapshot"`、
  `prices={}`、`stale=true`；前端按此接，未改动。
- `stale` 与 `dataAgeSec`：`stale = ageSec(基于缓存 checkedAt) > ttlSec`（或没有缓存）；
  `dataAgeSec = now - updatedNewest`（上游逐条 `updated` 的最新值），表示价格数据本身的年龄。
  前端「实时（tarkov.dev，N 分钟前）」用的是 `dataAgeSec`，与实现在语义上一致。
  本次**只改文档**（`docs/USAGE.md` 补齐 `dataAgeSec` 定义与 304 时 `checkedAt` 刷新、
  `dataAgeSec` 不变的说明），**未改任何字段语义或数值**。
- `GET /api/live-prices/status`、启动默认离线、`/api/overlay`、`/api/prices` 等既有行为未变。

### 9.4 测试

新增 10 条（原 22 → 32）：

- 409 优先于 403（`enabled=false` + 无凭据 / 错误 token 都是 409，且不 spawn）；
- 浏览器同源路径可用（Origin / 仅 Referer 两种都 202，`via:"web"`）；
- 跨域被拒（外站 Origin、无 Origin/Referer、无凭据三种 403）；
- 桌面壳 token 路径不变（正确 202 `via:"token"`，错误 403）；
- 真实 socket keep-alive：409 带 body 后同连接 GET 200（非 501）、403 带 body 后同连接 GET 200；
- 413 显式 `Connection: close`；
- 非法 `Content-Length`（`abc`）→ 400 + `Connection: close`；
- 缺 `Content-Length` 不卡死且连接可复用；
- `OPTIONS` 预检无 `Access-Control-Allow-*`。

数字（最终一次）：

- `python -m pytest tests/test_r42_live_prices.py -q` → **32 passed in 12.73s**
- `python -m pytest tests -q` → **1702 passed, 1 skipped, 6 failed in 101.57s**

失败构成：5 个既有配枪 / 前端用例（`test_r19_1`、`test_r19_5`、`test_r19_11`、`test_r19_13`、
`test_r6_gun_workbench`，均由另一会话对 `app.js` 的改造引起），外加 `test_r45_editions`
（读 `data/editions.json` 的账号版本卡文案，也是另一会话的并发改动）。按约定**未修、未跳过、未弱化**；
本轮测试在另一会话持续改前端期间运行，失败数在 5–7 之间浮动，与本轮后端改动无关。

### 9.5 本轮改动文件 SHA256

| 文件 | SHA256 |
| --- | --- |
| `tools/serve.py` | `F677B61FC1611030860615B7151D5EC16F34620D47CDB364FD5875F4105350DB` |
| `tools/live_prices.py`（未改） | `C177FAF0A30A15B2D371004A3A2AF20BEC41BF307EB1EAAABE77C654C12662BD` |
| `tests/test_r42_live_prices.py` | `B535019149757162E529BE3164544B3E7AE2294263594ACD6F778D0F4F0227C5` |
| `docs/USAGE.md` | `8C28508F53D407AD5CEA6DB5E7C4B04FC76EB43C055AD5C1EA0E304960FFC49A` |
| `README.md` | `08A4745A412065745A2251E97399E8FDD248361A74F02AF22C0A05B5B8535D1E` |

（本文件自身不断被续写，SHA256 随写入变化，不列自摘要。）

### 9.6 未改前端声明

本轮**未修改任何前端文件**：`index.html`、`style.css`、`app.js`、`combat_sim.js`、`gun_builder.js`、
`assets/`、`data/traders.json`、任务页相关文件均未触碰；也未 `git commit`、未动 `release/`、`dist/`。

**前端需要配合的精确清单（供转交前端会话）**：

1. `app.js` 的 `POST api/live-prices/refresh` 增加请求头 `X-EFTMap-Client: web`。
   同源 `fetch` 会由浏览器自动带 `Origin`（部分环境至少带 `Referer`），无需手工设置；
   服务端两者任一存在且同源即放行。
2. **不要**再自己加 `X-EFTMap-Token`（浏览器模式没有该 token）；带错误 token 会被判 403。
3. 请求体可继续不带（`method:"POST"` 即可）。即使带 JSON body，服务端也已读尽，
   不会再污染 keep-alive 连接；但「不带 body」仍是更省的选择。
4. 403 的提示文案需要改：删除「该接口需要桌面壳的 token、浏览器直连无法触发」的说法，
   改为「刷新被拒绝：请通过本机同源页面调用，或桌面壳 token 无效」。
5. 409 仍是「在线行情未启用（`livePrices.enabled=false`）」，判定已先于鉴权，文案不用改。
6. GET `/api/live-prices` 的字段与展示逻辑无需改动（`enabled=false` → `source:"snapshot"`、
   `dataAgeSec` 用于「N 分钟前」）。
