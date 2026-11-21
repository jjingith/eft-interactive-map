# R233 · 配装栏提示改成会员引导文案，并真的接通会员云存储

## 用户原话（2026-11-10 22:08）

> 预设保存在 `%APPDATA%\EFTMap\weapon-presets.json`（本地离线文件，不上传）。
> 配装栏有这个提示 我希望提示改成这个 **免费版预设保存在本地 会员享受云存储**
> 然后你看看能不能做到云存储 并实现这个效果

## 能不能做到：能，而且服务端零改动

调研 `eft-cloud` 后确认，**会员鉴权和用户级持久化存储都已投产**：

| 已有能力 | 位置 |
| --- | --- |
| 会员门禁 `_require_member()`（token 有效 + 会员有效，否则 403 `membership_required`） | `eft-cloud/app/service.py:1621` |
| 账号级通用 KV：`sync_meta` + `sync_items(account_id, key, value, hash, version)` | `eft-cloud/app/schema.sql:162-181` |
| 增量同步接口 `/v1/sync/{state,push,fetch}`（rev 版本、hash 跳过、冲突检测、force 覆盖） | `eft-cloud/app/service.py:1638-1767` |
| 客户端「非会员锁死、会员自动同步」链路 | `eft-interactive-map/js/cloud.js` + `tools/cloud.py` |

所以不需要新建账号体系、不需要建表、不需要新增 API。`docs/cloud-service-plan.md` 里预留的
「专用 `/v1/presets` + 专用表」是重方案且标注了「暂不实现」；实际投产的通用 KV 更轻，
预设只是再加两个键：`preset.weapon`、`preset.loadout`（符合云端
`SYNC_KEY_RE=^[a-z0-9][a-z0-9._-]{0,63}$`，单值上限 256KB，键数上限 16 → 现在共 5 个键）。

## 改了什么

| 文件 | 改动 |
| --- | --- |
| `app.js` | ① 配装栏空态提示改成 `免费版预设保存在本地 会员享受云存储`（常量 `PRESET_STORAGE_NOTE`），不再暴露本地路径；悬浮说明按前端唯一会员入口 `isMember()` 显示当前是免费版还是已开启云同步。② `presetPost()` 写成功派发 `gw:presets-saved`。③ 监听 `eftmap:presets-remote-applied` → `reloadPresets()` + 重绘当前视图。 |
| `js/cloud.js` | `collectValues()` 改为 Promise，除原 `progress.*` 三键外读取两类本地预设整包（GET `/api/presets?kind=`）→ `preset.weapon` / `preset.loadout`（值 `{schema:1, presets:[…]}`）；`applyRemote()` 拆成进度 + 预设两部分，远端整包通过 POST `/api/presets action=replace` 写回本地；`syncNow()` 适配 Promise；新增监听 `gw:presets-saved` 复用原有 3s debounce / 15s 最小间隔。 |
| `tools/serve.py` | `/api/presets` 新增 `action="replace"`：只接受 `presets` 数组，交给下面统一的 `presets.save()` 逐条归一化 + 原子写回。 |
| `eft-cloud`（服务端） | **零改动** |

## 行为

- **免费版 / 未登录**：`syncNow()` 第一行 `if (!state.member) return;`、`scheduleSync()` 同样拦截，
  BFF `tools/cloud.py` 再挡一层 `config.is_member()` —— 一个 `/v1/sync/*` 请求都不会发。
  预设照旧只写 `%APPDATA%\EFTMap\weapon-presets.json` / `loadout-presets.json`。
- **会员**：保存 / 删除 / 导入预设 → 3 秒 debounce → 与任务进度一起走同一条增量同步；
  另一台设备的预设回来后整包写回本地文件，再刷新内存缓存与当前视图。
- **本地文件仍是第一事实源**：沿用既有冲突策略（有冲突时保留本地，面板给 force 按钮）；
  磁盘文件损坏时 `presets.save()` 拒绝覆盖，不静默冲掉数据。
- **不静默丢数据**：单个预设包序列化超过 240000 字符（云端 256KB 上限留余量）会跳过该键，
  并在同步消息里明确写「预设 X 超过云端单值上限，已跳过（仍完整保存在本地）」；
  本地预设读不到时跳过该键、任务进度照常同步，绝不拿空数组冒充本地数据去覆盖云端。
- 远端写回走的是 cloud.js 直接 POST，不经过 `presetPost()`，所以不会派发保存事件、不会同步回环。

## 验收（`tools/r233_accept.py`，16/16 PASS）

全程在页面加载前接管 `fetch`，**POST 不落盘，绝不触碰用户真实的 `%APPDATA%\EFTMap` 文件**。

| 检查 | 结果 |
| --- | --- |
| 配装栏提示 | 精确等于 `免费版预设保存在本地 会员享受云存储`；无 `%APPDATA%` / 「不上传」 |
| 悬浮说明 | 按会员态显示「会员云存储已开启…」/「当前为免费版…」 |
| 会员点「立即同步」 | GET 两类预设 → `/api/cloud/sync` 带 5 个键（3 个 `progress.*` + 2 个 `preset.*`）→ 远端整包 POST `/api/presets` `action=replace`，写回的是 `wp_cloud1` |
| 会员同步按钮 | 可用 |
| 免费版 | 同步按钮 disabled；派发 `gw:presets-saved` 并等过 3s debounce 后，零 `/api/cloud/sync` 请求 |
| 不回归 | R228 口径按钮 90px 等宽、R232 表格滚区 `border-image:none` + 1px 白底 |
| JS 异常 | 无 |

## 测试

`tests/test_r233_preset_cloud.py` 9 条：

- 静态契约（旧文案消失 / 新文案精确 / 用 `isMember()` / 两个事件名 / 同步键名 / 免费版拦截 /
  `replace` 分支的入参校验）；
- HTTP 级（真实启动 `serve.create_server`）：整包替换写盘、坏 payload 不覆盖本地文件、
  损坏文件拒绝覆盖返回 409；
- Node harness 实跑 `collectValues()` / `applyPresetRemote()`：正常 5 键、本地读失败跳过、
  超上限跳过并提示、远端整包只发 `action=replace` 并派发刷新事件。

全量 `python -m pytest tests -q --junitxml=build/_pytest_r233.xml` →
**2047 passed / 0 failed / 0 errors / 1 skipped**（合计 2048，171.43 s，
比 R232 多 9 条，正好是本轮新增的 9 条用例）。日志里那段
`ConnectionAbortedError` 是 SSE 测试线程收尾的既有噪音，JUnit 无 failure / error。

## 已知边界

- **真实云端上传没有实跑**：本机没有会员会话，验收用 mock 覆盖了从前端到 BFF 的完整链路；
  服务端 `/v1/sync/*` 是已投产接口（`eft-cloud/tests/test_sync.py` 有服务端用例），
  真实上传要会员账号登录后才会发生。
- **服务端没有同步频率限流**：预设保存走的是既有 3s debounce + 15s 最小间隔，量级与任务进度相同；
  若将来要防刷，需要在 `eft-cloud` 给 `/v1/sync/*` 补限流（服务端改动，超出本轮）。
- 单键 256KB：极端大预设包会跳过并提示，本地仍完整保存。
- 会员开通目前只有 `eft-cloud/app/admin.py` 的 CLI，没有自助购买 HTTP 接口 —— 这不影响同步功能。
