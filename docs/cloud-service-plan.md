# 云端服务落地方案（收缩版：付费 = 跨设备进度云备份 + 位置刷新频率）

> 性质：**设计方案，不改源码、不部署**。核查时间 2026-11-08；外部价格/政策均标注来源与抓取日期，取不到的标「待核实」。
> 对象：`d:\personal\trae\02-塔科夫\eft-interactive-map`（客户端 0.2.0，PyInstaller onedir）。
> 本版已并入用户确认的 ECS 规格、网络路线、7×24 前提、大文件走对象存储，以及**会员范围的第二次收缩结论**。

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 架构怎么切 | **账号、权益、进度同步全部跑 ECS**（SQLite + Caddy + 3 Mbps 足够）。范围收缩后**不再需要“本机数据面”**；ZeroTier 只保留运维/应急通道，不在付费链路里。原有“本机数据面”设计仅作为未来功能储备保留。 |
| 3 Mbps 能撑多少 | 只剩进度同步后，**带宽不再是瓶颈**：单次增量 1–10 KB、全量最坏 <200 KB；3 Mbps 足以支撑数千 DAU。原行情场景的 300–800 DAU 估算保留在 §9 作为未来参考。 |
| 哪些必须常驻 ECS | 登录/刷新令牌、权益判定、进度同步、支付回调、更新清单、`/status` 状态页、Caddy。只依赖 SQLite 小库，2 GiB 内存足够。**不在 ECS 跑 Postgres。** |
| 没有域名怎么 TLS | **自签 CA + 客户端内置根证书 pinning**，公网入口 `https://47.96.68.209:8443`。浏览器不直连云端，所有请求由本机 Python BFF 校验固定 CA。 |
| OSS 还是网盘 | **OSS（标准存储 + 公网流出，不上 CDN）**。没有域名就无法接阿里云 CDN；OSS 默认域名可直接用。100/500/1000 GB 月出流量约 ¥50/250/500（忙时价），CDN 方案因无域名不可用。详见 §10。 |
| **两项会员是否站得住** | **仍偏弱，但比单项稍好**：①跨设备进度备份（低频保险）+ ②位置刷新频率（非会员自动截图固定 10 秒/张、定位更新合计 10 秒一次；会员自动截图可调 200–60000ms、定位不限）。第二项是**同一权益的两个面**，不是两个功能。两者都不属于高频刚需，且第二项是“把旧版默认 5 秒拉长到 10 秒再卖回 5 秒/0.2 秒”的收回式卖点（R108 已落地，新装默认已是 10 秒），预计只能把年付转化抬到 10–15%，**仍不足以覆盖人力**（需约 845 个付费用户）。定价维持 **¥6/月、¥72/年**。详见 §11.1、§11.9。 |
| 盈亏平衡 | **ECS 实际续费约 ¥100/年（≈¥8.3/月）**：只算基础设施约 **6–7 个付费用户**打平；计入开发者 ¥5,000/月机会成本约 **845 个付费用户**（再加 ¥1,000 客服则约 **1,013 个**）。截图/定位门控不增加服务端成本，数字不变。详见 §11.5。 |
| 最大风险 | 许可风险**降低但没有归零**；且**第二个付费点是纯客户端门控（本地可绕过），使“软件完全免费”的前提不再成立**，README/协议必须改成“基础功能免费，两项增强付费”。门控只能算产品策略，**不能写进安全承诺**；老用户还会感到“旧版默认 5 秒被拉慢到 10 秒”。付费链路仍不触碰上游素材。其次：免费用户完全失去备份能力、无域名 TLS、支付资质。详见 §14.1、§12.6、§12.9。 |

### 0.1 第二次范围收缩（2026-11-08）

用户已确认：**第一项付费权益为「跨设备进度云备份（任务进度 / 剧情进度）」**，月付 ¥6 / 年付 ¥72。其余四项处理如下：

| 原候选 | 新处理 | 说明 |
|---|---|---|
| 实时行情 | **保持本地免费**，不做云端行情 | 现有 `livePrices` 可选开关不动；不新增 `/v1/market` |
| 云预设同步 | **暂不实现** | 本地预设仍是唯一事实源；不建云端预设表 |
| 公开构筑库 | **暂不实现** | 无发布/浏览/分享码；避免审核与冷启动成本 |
| 数据统计面板 | **暂不实现** | 本地统计保持现状 |
| **跨设备进度云备份** | **付费权益之一（服务端）** | 任务进度 + 剧情进度，月 ¥6 / 年 ¥72；第二项见 §0.2 |

**由此产生的架构简化（建议采纳）**：

- 进度 JSON 极小（典型 10–30 KB，最坏 <200 KB），**直接放在 ECS 控制面**即可；不再需要“本机数据面 + ZeroTier 反代”这条链路。
- 付费功能因此变成 **7×24 常驻 ECS**，本机停电/断网不影响付费权益，退款风险大幅下降。
- ZeroTier 仅保留给运维（SSH/管理后台）或应急，不作为用户请求路径。
- 下文 §3–§10 的“本机数据面、行情、云预设、公开库”内容**保留为未来扩展设计**，但**不在本轮实现范围**；§11 全部按“仅进度备份”重写，§13 只排进度相关里程碑。

### 0.2 第二付费点：位置刷新频率（2026-11-08 最终口径）

用户已拍板：**自动截图间隔 + 定位更新频率是同一个权益的两个面**，非会员统一锁 **10000ms**，会员放开。

| 面 | 非会员（未登录 / 已登录未付费 / 已过期） | 会员（有效） |
|---|---|---|
| 自动截图间隔 | **锁死 10000ms，不可调**（输入框禁用，保存时强制写回 10000） | 可调 **200–60000ms** |
| 定位更新频率 | **自动截图 + 手动按截图键两个来源合计限速：两次定位更新间隔 ≥ 10 秒** | 不限制（受截图实际产生频率约束） |
| 实际含义 | 地图位置最多 10 秒刷新一次 | 有新截图就跟随 |

| 项 | 结论 |
|---|---|
| 权益本质 | **一项权益（位置刷新频率上限），两个表现面**；不是“截图间隔”和“定位”两项独立权益 |
| 服务端成本 | **完全不经过 ECS**；不增加带宽/存储，服务端成本为零 |
| 实现归属 | **纯客户端门控（R108 已在本地落地）**：页面禁用输入 + `config.clamp_interval()` 按 `account.member` 钳制 + 本地 `serve.py PositionTracker` 合并限速；**ECS 不参与、不接收、不校验** |
| 安全边界 | 会员态来自本地配置 `account.member`，可手改；代码可读可改，**本地可绕过；不是防盗版手段，不能写进安全承诺** |
| 依赖阶段 | **本地门控已由 R108 落地**（`account.member` 为唯一判定入口）；接入 M1/M2 后只需把 `isMember()` 的数据源换成云端权益缓存，`clamp_interval` 与 `PositionTracker` 不改 |
| 体验代价 | 以 R108 之前的 **5000ms** 为基线，免费档变慢 2 倍（新装默认已是 10000ms，老配置读取时也会被钳到 10000）；小地图半径 25/50m 档位感知最强（详见 §11.9） |
| 定价影响 | 单价不变（¥6/月、¥72/年），盈亏平衡数字不变；只可能略微提升转化，**不构成涨价理由** |

---

## 1. 已确认的硬约束

### 1.1 ECS

| 项 | 值 |
|---|---|
| 实例 / 规格 | `i-bp19bwhz81xonri9tkyu` / `ecs.e-c1m1.large`（2 vCPU / 2 GiB） |
| 公网带宽 | **3 Mbps 固定带宽**（≈384 KiB/s 持续，理论月流量约 950 GiB / 1,020 GB） |
| 系统盘 | 40 GiB ESSD Entry |
| 系统 | Ubuntu 22.04 64 位，华东1（杭州） |
| 公网 IP / 私网 IP | `47.96.68.209` / `172.18.83.150` |
| 计费 | 包年包月，到期 2027-02-05（续费价以账单为准，待核实） |
| 现有负载 | ZeroTier moon |

### 1.2 网络路线（已选定）

1. **没有域名、不买域名**：客户端直连 `47.96.68.209` + **非标端口**（建议 TCP 8443），避开 80/443，免 ICP 备案。
2. **ZeroTier 只做一条固定隧道**：本机与 ECS 各 1 个节点，共 2 个；不面向终端用户，不触碰免费版节点上限。
3. **业务跑在本机**：本机 7×24 在线（停电/断网除外）；ECS 做流量转发 + 反向代理，相当于「家里游戏服务器的端口映射」，但用 ZeroTier 代替路由器公网映射。
4. **大文件（更新包、图片、地图资源）走 OSS/对象存储**，不占 ECS 3 Mbps。

### 1.3 被否决路线的结论（一句话）

- **A 域名 + 80/443**：要买域名 + ICP 备案（个人/企业主体、周期与材料成本），与「不买域名」的决策冲突 → **否决**。
- **C ZeroTier 面向终端用户**：每个用户都要装客户端并加入 network，免费版有节点上限，获客摩擦与运营成本过高 → **否决**；仅保留「ECS ↔ 本机」这一条固定隧道。

---

## 2. 现状核查（只读代码，方案的事实基础）

### 2.1 已有「在线行情后端」怎么做

| 事实 | 证据 |
|---|---|
| 默认关闭，只有 `livePrices.enabled=true` 才可能联网 | [config.py](../tools/config.py#L306-L341) |
| 请求线程绝不联网，只读本地缓存 | [serve.py](../tools/serve.py#L245-L297) `live_price_payload()` |
| 联网发生在独立子进程 `tools/live_prices.py --fetch` | [serve.py](../tools/serve.py#L316-L335) |
| 已实现上游映射、ETag/Last-Modified 条件请求、304 复用、TTL、原子写盘、进程锁、失败记录 | [live_prices.py](../tools/live_prices.py#L289-L603) |
| 上游 PvP=`/regular/items`、PvE=`/pve/items`，约 17 MB、10 分钟一版 | [live_prices.py](../tools/live_prices.py#L8-L17) |
| 归一化只存 `l`（最近低价）/`a`（24h 均价）/`u`（更新时间）/`b`/`tb`/`tn` | [live_prices.py](../tools/live_prices.py#L397-L466) |
| 前端把实时值逐项覆盖快照，缺字段保留快照 | [app.js](../app.js#L686-L714) |
| 前端唯一数据入口 `api/live-prices?mode=…` | [app.js](../app.js#L675-L677) |

**可直接搬到数据面的部分**：上游 URL/模式语义、条件请求与 304、`build_cache()` 的字段收敛与质量闸门（`MIN_ITEMS=1000`、`MIN_PRICED=500`）、失败不覆盖旧缓存、响应形状（`enabled/available/stale/ageSec/prices{mode:{l,a,u}}`）。
**必须改的**：本机代理 `127.0.0.1:7896` 不适用于服务器；请求线程不得联网；本地文件缓存换成「快照表 + 单实例调度」；加鉴权与配额。

### 2.2 配置 / 前端 / 预设 / SSE

- 配置在 `%APPDATA%\EFTMap\eftmap.config.json`，`normalize()` 收敛脏值、读写不抛异常（[config.py](../tools/config.py#L699-L763)）。
- `overlay.*` 是整段白名单结构；`merge_ui()` 逐键白名单合并，空 `ui` 表示「没保存过」（[config.py](../tools/config.py#L641-L696)）。新增 `cloud.*` 必须沿用同样模式，默认关闭。
- 前端是单文件 `app.js`（约 1.2 MB），`js/` 只有 `game-mode.js`、`ui-components.js`、`task-graph-layout.js`、`app-menubar.js`；无构建步骤。
- `?mini=1` 是同一页面的小窗模式（[app.js](../app.js#L1406-L1540)），宿主 `tools/overlay.py` 访问 `127.0.0.1:8810/index.html?mini=1…`；**小窗路径必须完全离线可用**。
- 本地预设：`loadout-presets.json` / `weapon-presets.json`，严格校验 + 原子写盘；损坏默认拒绝覆盖（[presets.py](../tools/presets.py#L167-L232)）。云端同步必须以本地文件为第一事实源。
- 本地服务 `ThreadingHTTPServer` 默认 `127.0.0.1:8787`，API 无鉴权；`/events` 是 SSE（位置无名帧 + `config/state/raid/quest/shot/clean` 命名事件，15 秒心跳）。

---
## 3. 目标架构与职责切分

### 3.1 拓扑

```
用户浏览器/客户端（同一台机器）
  │  http://127.0.0.1:8787   （回环，无鉴权，仅本机）
  ▼
本机 Python 服务（tools/serve.py + tools/cloud.py BFF）
  │  HTTPS 8443，自签 CA + 客户端 pinning
  ▼
公网 47.96.68.209:8443（阿里云安全组仅放行此端口）
  │
  ▼
ECS Caddy（TLS 终止 + 限流）
  └── /v1/auth/* /v1/entitlement /v1/progress* /v1/status /v1/updates/* /v1/pay/*  → 127.0.0.1:9000
                                                                                    控制面（ECS 常驻，SQLite）
  ┈┈ ZeroTier（仅运维 SSH/管理后台；未来数据面才走这里，本轮不用）
         └── 10.147.20.x:8788  本机业务服务（未来）
```

**本轮所有付费请求都在 ECS 内闭环**，不依赖本机在线。

### 3.2 控制面（必须 7×24 常驻 ECS）

| 模块 | 职责 | 理由 |
|---|---|---|
| 账号与令牌 | 注册/登录/刷新/吊销、设备表、会话表 | 密钥与会话状态只能可信保存于服务端；本机停机时仍能登录与续期 |
| **进度同步** | 实体合并、版本号、快照、冲突日志 | **本轮唯一服务端付费功能**，必须 7×24，不能落在会关机的本机 |
| 权益判定 | 订阅状态、到期、赠送、退款、设备数 | 付费用户不能因为本机维护而「无法证明自己是会员」 |
| 支付回调 | 验签、幂等、延长 `expires_at` | 回调需要稳定公网入口；不能落到会关机的本机 |
| 更新清单 | 版本号、OSS 地址、SHA-256、回滚版本 | 更新与 bug 修复承诺免费，不能依赖本机在线 |
| `/status` + 健康检查 | 服务状态、维护公告 | 收费后必须能解释「为什么现在不可用」 |
| 静态兜底 | 异常时返回结构化 503 | 避免 Caddy 默认 502 页面，客户端可识别降级 |

资源预算：Python 单进程 + SQLite，常驻约 60–120 MB；Caddy 30–60 MB；ZeroTier 20–40 MB；系统与 journald 300–450 MB；合计约 450–700 MB，2 GiB 有充足余量。**不安装 Postgres/Redis/Node。**

### 3.3 数据面（未来；本轮不部署）

> 范围收缩后，唯一服务端付费功能（进度同步）在 ECS，本机**不需要任何业务进程**。下表保留为未来行情/预设/公开库的设计储备。

| 模块 | 职责 | 为什么不上 ECS |
|---|---|---|
| 行情聚合 | 10 分钟抓上游、归一化、快照入库、对外发小包 | 抓取与解析是 CPU/IO 活，本机资源更充裕；ECS 只转发结果 |
| 云预设同步 | 版本、墓碑、冲突合并、配额 | 数据量与读写在本机 SQLite，避免 ECS 磁盘与内存压力 |
| 公开构筑库 | 发布、列表、分享码、收藏、审核队列 | 内容读写在本机；公网只暴露只读分页接口 |
| 管理后台 | 审核、封禁、CDK、用户查询 | **只经 ZeroTier 私网访问，不映射到公网路径** |

未来本机业务进程崩溃/重启由本机进程管理器拉起；ECS 侧只感知 `/healthz` 失败并返回 503。

### 3.4 必须留在本地、永不上云

- 地图渲染、图层、缩放、地名、小地图、`?mini=1` 小窗；
- 实时定位（截图文件名坐标）、日志跟随、战局/任务事件；
- 自动截图、自动删除、输入模拟；
- 本地预设读写与原子落盘、`overlay.*`、界面偏好。
  这些是「本地免费版」的根，**未启用云端时除位置刷新门控外必须与现在完全一致**。

### 3.5 为什么权限判断不能留在客户端

1. 客户端可被完全读取/改写：后端是 Python `.pyc`（可解包反编译），前端 `app.js`/`data/*.json` 是明文（[r210-local-anti-crack-plan.md](./r210-local-anti-crack-plan.md#L21-L32)）。`if (paid)` 改成 `if (true)` 只需一分钟。
2. 真正的资产在服务端：进度数据只有服务端有合并后的完整视图，破解版改 UI 也拿不到；若只在客户端判断，等于把同步能力白送（虽然单项价值低，但原则不变）。
3. 订阅是可变状态：到期、退款、封禁、设备数必须单点裁决，客户端缓存只能用于「离线时显示上次状态」。
4. 审计需要服务端日志：撞库、盗号、共享账号只能靠登录/刷新/请求日志发现。

**口径**：客户端只拿权益用于 UI 显隐与**本地限速策略**；每个云端数据请求都由服务端校验 `token + entitlement`。客户端不决定“是否允许云端数据”，只决定“是否显示入口/是否本地限速”。

**例外（必须单独写明）**：**位置刷新频率（截图间隔 + 定位 10 秒）不产生任何云端请求，由本地客户端门控（R108 已落地：页面禁用 + `config.clamp_interval` + `serve.py PositionTracker`），ECS 无法验证。** 它属于产品分层，不属于权限/安全边界；详见 §11.9。不要因为“客户端判断不可信”就把它硬塞给云端——云端只会收到“我是会员”的客户端自述，等于假校验。

---

## 4. API 设计草案

### 4.1 基线与约定

- 入口：`https://47.96.68.209:8443/v1`（自签证书，客户端 pinning；见 §8.4）。
- 版本：URL 版本 `/v1`；只做加法；弃用字段保留至少 2 个客户端版本，并在响应头给 `Sunset`。
- 编码：请求/响应 `application/json; charset=utf-8`；响应 gzip/zstd。
- 请求头：`Authorization: Bearer <access>`、`X-Device-Id`、`X-Client-Version`、`X-Request-Id`（客户端生成 UUID）。
- 响应头：`X-Request-Id`、`Server-Time`、`X-Service-Status: ok|degraded|maintenance`、`ETag`（权益/进度）。
- 统一响应：成功 `{"ok":true,"data":…}`；失败 `{"ok":false,"error":{"code":"…","message":"…","requestId":"…"}}`。
- 本机 BFF 会把云端响应**原样透传**（只补 `offline` 标记），前端不需要感知 ECS/ZT。

### 4.2 端点清单

| 方法 | 路径 | 鉴权 | 权益 | 面 | 说明 |
|---|---|---|---|---|---|
| POST | `/v1/auth/register` | 无 | 无 | 控制 | 注册（邀请码/CDK 可选） |
| POST | `/v1/auth/login` | 无 | 无 | 控制 | 账号密码 + 设备 ID |
| POST | `/v1/auth/refresh` | refresh | 无 | 控制 | 旋转刷新令牌 |
| POST | `/v1/auth/logout` | access | 无 | 控制 | 吊销当前设备 |
| GET | `/v1/auth/devices` | access | 无 | 控制 | 设备列表 |
| DELETE | `/v1/auth/devices/{id}` | access | 无 | 控制 | 踢设备 |
| GET | `/v1/entitlement` | access | 无 | 控制 | 功能清单 + 到期 + ETag |
| POST | `/v1/pay/notify/{channel}` | 签名 | 无 | 控制 | 支付回调（仅渠道 IP） |
| GET | `/v1/updates/manifest` | 无 | 无 | 控制 | 更新清单（免费） |
| GET | `/v1/status` | 无 | 无 | 控制 | 服务状态 + 维护公告 |
| **GET** | **`/v1/progress?sinceRev=…`** | access | **进度同步** | **控制** | **拉取 `rev` 之后的变更 + 当前 `rev`（本轮唯一服务端付费功能组）** |
| **POST** | **`/v1/progress/sync`** | access | **进度同步** | **控制** | **批量提交增量 + 逐实体合并 + 返回 `serverChanges`；内部独立校验权益** |
| **POST** | **`/v1/progress/precheck`** | access | **进度同步** | **控制** | **仅 UI 预检（返回 canSync/到期/配额），不写数据** |
| **GET** | **`/v1/progress/export`** | access | **进度同步** | **控制** | **会员救援导出（UI 不展示常规入口，排障/换机用）** |
| GET | `/v1/market/snapshot?mode=regular\|pve` | access | 实时行情 | 数据 | *未来/暂不实现*；现有本地行情保持免费 |
| GET | `/v1/market/history?itemId=…&days=7` | access | 实时行情 | 数据 | *未来/暂不实现* |
| GET | `/v1/presets?kind=loadout\|weapon&updatedAfter=…` | access | 云同步 | 数据 | *未来/暂不实现* |
| PUT | `/v1/presets/{clientId}` | access | 云同步 | 数据 | *未来/暂不实现* |
| DELETE | `/v1/presets/{clientId}?version=…` | access | 云同步 | 数据 | *未来/暂不实现* |
| GET | `/v1/presets/{clientId}/versions` | access | 云同步 | 数据 | *未来/暂不实现* |
| POST | `/v1/builds` | access | 公开库 | 数据 | *未来/暂不实现* |
| GET | `/v1/builds?sort=hot\|new&cursor=…&q=…` | access | 无（浏览免费） | 数据 | *未来/暂不实现* |
| GET | `/v1/builds/{shareCode}` | access | 无 | 数据 | *未来/暂不实现* |
| POST | `/v1/builds/{shareCode}/copy` | access | 公开库 | 数据 | *未来/暂不实现* |
| POST | `/v1/builds/{shareCode}/report` | access | 无 | 数据 | *未来/暂不实现* |
| POST | `/v1/builds/{shareCode}/favorite` | access | 公开库 | 数据 | *未来/暂不实现* |
| DELETE | `/v1/builds/{shareCode}/favorite` | access | 公开库 | 数据 | *未来/暂不实现* |
| PATCH | `/v1/builds/{id}` | access | 公开库 | 数据 | *未来/暂不实现* |
| GET | `/v1/admin/…` | access+admin | — | 控制 | 仅 ZeroTier 私网 |

### 4.3 鉴权：令牌类型、有效期、刷新

- **Access Token**：JWT（HS256，服务端密钥），有效期 **15 分钟**；载荷 `{uid, deviceId, ent, exp, jti}`；只放内存/本机令牌文件，不放浏览器 `localStorage`。
- **Refresh Token**：64 字节随机串，服务端只存 `sha256(token)`；有效期 **30 天**；**每次刷新旋转**，旧 token 立即失效；检测到旧 token 复用 → 吊销该设备全部会话并记审计。
- **设备绑定**：`X-Device-Id` 由客户端首次生成并持久化；refresh 与 device 绑定；服务端设备数上限默认 3。
- **权益不写进 JWT 做长期依赖**：JWT 只带 `ent` 版本号；真正的功能清单每次由 `/v1/entitlement` 查库，避免退款/封禁后 15 分钟内仍可用。
- **密码哈希**：`hashlib.scrypt(n=2^14, r=8, p=1)`，每用户随机盐；登录失败统一返回 `AUTH_INVALID`，不区分「账号不存在/密码错」。
- **支付回调**：按渠道验签（微信/支付宝），`event_id` 唯一约束做幂等；只在事务里延长 `subscriptions.expires_at`。

### 4.4 请求/响应示例

**注册**

```http
POST /v1/auth/register
Content-Type: application/json

{"email":"a@example.com","password":"…","deviceId":"dev-7f3a…","deviceName":"Windows-Desktop"}
```

```json
{"ok":true,"data":{"userId":"u_01J…","accessToken":"eyJ…","refreshToken":"r_64…","expiresIn":900,
"entitlement":{"plan":"free","features":["progress.local","map.local"],"expiresAt":null}}}
```

**登录**

```json
{"ok":true,"data":{"accessToken":"eyJ…","refreshToken":"r_64…","expiresIn":900,
"entitlement":{"plan":"plus","features":["progress.sync","position.refresh"],"expiresAt":"2027-01-08T00:00:00Z"}}}
```

**刷新（旋转）**

```http
POST /v1/auth/refresh
{"refreshToken":"r_64…","deviceId":"dev-7f3a…"}
```

```json
{"ok":true,"data":{"accessToken":"eyJ…","refreshToken":"r_65…","expiresIn":900}}
```

**权益**

```http
GET /v1/entitlement
Authorization: Bearer eyJ…
If-None-Match: "ent-u-42-v7"
```

```json
{"ok":true,"data":{"plan":"plus","status":"active","expiresAt":"2027-01-08T00:00:00Z",
"features":["progress.sync","position.refresh"],"limits":{"devices":3,"progressSyncPerDay":200,"progressBytes":262144},"version":7}}
```

**进度同步（本轮唯一服务端付费接口组）**

```http
POST /v1/progress/sync
Authorization: Bearer eyJ…
X-Device-Id: dev-7f3a…
Content-Type: application/json

{"baseRev":42,"changes":[
 {"dataset":"tasks","mode":"regular","id":"5e8c…","value":{"status":"completed","objectives":{"obj1":true,"obj2":true},"updatedAt":"2026-11-08T03:00:00Z"},"baseRev":7},
 {"dataset":"stories","mode":"regular","id":"s1","value":{"steps":{"step3":true},"choices":{"k":"A"},"stepTombstones":{"step2":"2026-11-08T02:59:00Z"}},"baseRev":9}
]}
```

```json
{"ok":true,"data":{"rev":43,"accepted":2,
"conflicts":[{"entity":"tasks/regular/t1","field":"status","client":"active","server":"completed","resolved":"completed"}],
"serverChanges":[{"dataset":"stories","mode":"regular","id":"s2","value":{"steps":{"step5":true},"choices":{}},"rev":11}]}}
```

- `baseRev` 与实体 `baseRev` 都是快路径：相等即无并发，直接接受，不读冲突算法。
- 超过 50 个实体返回 `SYNC_BATCH_TOO_LARGE`，客户端改发「全量快照 + 时间戳」。
- 全量快照上限 256 KB（`PAYLOAD_TOO_LARGE`），正常用户远低于此。

> 以下行情/预设/公开库示例属于**未来扩展**，本轮不实现，仅作为接口形状储备。

**行情（ETag / 304）**

```http
GET /v1/market/snapshot?mode=regular
Authorization: Bearer eyJ…
If-None-Match: "mkt-regular-20261108T0310Z-9f2c"
Accept-Encoding: gzip
```

```json
{"ok":true,"data":{"mode":"regular","fetchedAt":"2026-11-08T03:10:00Z","stale":false,"ageSec":42,
"count":5487,"prices":{"5c0e…":{"l":41200,"a":43800,"u":"2026-11-08T03:09:00Z"}}}}
```

未变化时：`304 Not Modified`，空 body（客户端保留旧快照）；这是 3 Mbps 下的关键省流手段。

**预设 upsert（幂等 + 冲突）**

```http
PUT /v1/presets/loadout-abc123
Authorization: Bearer eyJ…
If-Match: "3"
Content-Type: application/json

{"kind":"loadout","name":"AK-103 夜战","updatedAt":"2026-11-08T02:00:00Z",
"payload":{"items":[…]},"deleted":false}
```

```json
{"ok":true,"data":{"serverId":"p_01J…","version":4,"syncedAt":"2026-11-08T02:00:03Z"}}
```

版本冲突返回 `409`：

```json
{"ok":false,"error":{"code":"CONFLICT_VERSION","message":"云端版本 5 高于本地基线 3","requestId":"…",
"data":{"serverVersion":5,"serverUpdatedAt":"2026-11-08T02:01:00Z"}}}
```

**公开库列表**

```http
GET /v1/builds?sort=hot&cursor=eyJvIjoyMH0&limit=20
Authorization: Bearer eyJ…
```

```json
{"ok":true,"data":{"items":[{"shareCode":"AK103NITE","title":"AK-103 夜战低后坐","author":"u_…",
"weapon":"AK-103","likes":128,"copies":57,"updatedAt":"2026-11-07T12:00:00Z"}],"nextCursor":"eyJvIjo0MH0"}}
```

**更新清单**

```json
{"ok":true,"data":{"version":"0.2.1","minVersion":"0.2.0","size":148923456,
"sha256":"9f2c…","url":"https://eftmap-updates.oss-cn-hangzhou.aliyuncs.com/win/0.2.1.zip",
"notes":"修复…","rollbackVersion":"0.2.0","publishedAt":"2026-11-07T10:00:00Z"}}
```

**错误体（统一）**

```json
{"ok":false,"error":{"code":"ENTITLEMENT_REQUIRED","message":"实时行情需要会员","requestId":"req-…"}}
```

### 4.5 错误码约定

| HTTP | code | 含义 | 客户端动作 |
|---|---|---|---|
| 400 | `VALIDATION_FAILED` | 字段缺失/格式错 | 提示，不改本地数据 |
| 401 | `AUTH_REQUIRED` | 无 token | 跳登录 |
| 401 | `TOKEN_EXPIRED` | access 过期 | 静默 refresh 后重试一次 |
| 401 | `AUTH_INVALID` | 账号/密码错 | 统一提示 |
| 401 | `REFRESH_REUSED` | 刷新令牌复用 | 强制重新登录 + 提示安全事件 |
| 403 | `ENTITLEMENT_REQUIRED` | 无会员权益 | 显示升级入口，不报错 |
| 403 | `DEVICE_LIMIT` | 设备数超限 | 让用户选择踢设备 |
| 403 | `QUOTA_EXCEEDED` | 单日配额耗尽 | 显示剩余额度/明日恢复 |
| 404 | `NOT_FOUND` | 构筑/预设不存在或已下架 | 本地回退 |
| 409 | `CONFLICT_VERSION` | 预设版本冲突（未来） | 拉取云端版本，交给合并 UI |
| 409 | `SYNC_BATCH_TOO_LARGE` | 单批实体 > 50 | 改发全量快照 |
| 413 | `PAYLOAD_TOO_LARGE` | 进度全量 > 256 KB / 请求体过大 | 拒绝并提示上限 |
| 429 | `RATE_LIMITED` | 频率超限 | 读 `Retry-After`，指数退避 |
| 503 | `DATA_PLANE_OFFLINE` | 本机数据面不可用（未来） | **静默降级到本地快照/免费功能** |
| 503 | `UPSTREAM_STALE` | 上游行情过期（未来） | 用旧快照 + 标 `stale:true` |

### 4.6 限流与配额（3 Mbps 的护栏）

- 全局：Caddy 层每 IP 30 req/s、每 IP 连接数 10；突发 60。
- **本轮**：每账号进度同步 200 次/天、`GET /v1/progress` 200 次/天、单次 ≤50 实体、单用户存储 3 个历史版本。
- *未来*：行情快照 30 次/小时、历史 60 次/小时、预设同步 200 次/小时、发布 10 次/天。
- 未登录只能访问 `/v1/status` 与 `/v1/updates/manifest`；`/v1/progress/*` 一律要求登录 + 有效权益。
- 单响应体上限：进度全量 256 KB（gzip 后约 5–20 KB）；*未来*行情快照 1 MB。

---
## 5. 数据模型

### 5.1 选 SQLite 还是 Postgres

**结论：ECS 用 SQLite（WAL），不在这台 2 GiB ECS 上跑 Postgres。**（范围收缩后只剩控制面与进度同步，本机数据面暂时不存在。）

理由（针对当前规模）：

1. 用户量级是「几十到几千付费用户」，写操作主要是登录刷新与进度实体 upsert；峰值写入远低于 20 次/秒，SQLite WAL 单写者完全够用。
2. ECS 只有 2 GiB：Postgres 常驻 100–250 MB 起，加上备份/连接开销会挤压 Caddy 与控制面；SQLite 常驻 < 20 MB。
3. 控制面是单进程单写者，天然契合 SQLite；本轮没有多实例/多 worker 需求。
4. 备份简单：`sqlite3 db ".backup out.db"` 或停写快照，复制文件即可；Postgres 需要 pg_dump/PITR 配置。
5. 进度数据按实体存 TEXT、按 `server_rev` 拉增量，没有复杂查询；未来公开库若上线，SQLite FTS5 也足够（< 1 万条）。

**迁移触发条件（满足任一即换 Postgres 16，并升级到 4 GiB 以上或独立 DB 主机）：**

- 付费用户 > 2,000 或 DAU > 1,500；
- 预设/构筑行数 > 100 万，或 FTS 查询 P95 > 200 ms；
- 需要多实例/多 worker 同时写；
- 需要跨机高可用或 PITR。

### 5.2 控制面（ECS，SQLite WAL）

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE users (
  id            TEXT PRIMARY KEY,              -- u_01J…
  email         TEXT NOT NULL UNIQUE,          -- 统一小写
  password_hash TEXT NOT NULL,                 -- scrypt$N$r$p$salt$hash
  email_verified_at TEXT,
  status        TEXT NOT NULL DEFAULT 'active',-- active|disabled
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  last_login_at TEXT
);
CREATE INDEX idx_users_status ON users(status);

CREATE TABLE devices (
  id          TEXT PRIMARY KEY,                -- d_01J…
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_key  TEXT NOT NULL,                   -- 客户端生成的 X-Device-Id
  name        TEXT,
  platform    TEXT,                            -- windows|linux|macos
  created_at  TEXT NOT NULL,
  last_seen_at TEXT,
  revoked_at  TEXT,
  UNIQUE(user_id, device_key)
);
CREATE INDEX idx_devices_user ON devices(user_id, revoked_at);

CREATE TABLE refresh_tokens (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_id   TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,            -- sha256(token)，不存明文
  issued_at   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  rotated_from TEXT,
  revoked_at  TEXT,
  ip          TEXT,
  user_agent  TEXT
);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id, revoked_at);
CREATE INDEX idx_refresh_exp ON refresh_tokens(expires_at);

CREATE TABLE subscriptions (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan          TEXT NOT NULL,                 -- plus_monthly|plus_yearly|lifetime_bundle
  status        TEXT NOT NULL,                 -- active|past_due|canceled|expired|gift
  source        TEXT NOT NULL,                 -- afdian|wechat|alipay|cdk|manual
  external_ref  TEXT,                          -- 渠道订单号
  started_at    TEXT NOT NULL,
  expires_at    TEXT NOT NULL,
  auto_renew    INTEGER NOT NULL DEFAULT 0,
  grace_days    INTEGER NOT NULL DEFAULT 3,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX idx_sub_user_exp ON subscriptions(user_id, expires_at DESC);
CREATE UNIQUE INDEX uq_sub_channel ON subscriptions(source, external_ref)
  WHERE external_ref IS NOT NULL;

CREATE TABLE payment_events (
  id          TEXT PRIMARY KEY,
  channel     TEXT NOT NULL,
  event_id    TEXT NOT NULL,
  user_id     TEXT,
  amount_cents INTEGER,
  raw         TEXT,                            -- 原始回调（脱敏）
  processed_at TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE(channel, event_id)                    -- 幂等
);

CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  user_id    TEXT,
  action     TEXT NOT NULL,                    -- login_fail|refresh_reuse|grant|revoke|refund…
  ip         TEXT,
  detail     TEXT
);
CREATE INDEX idx_audit_user_at ON audit_log(user_id, at DESC);
```

**权益计算（不建冗余宽表，按请求算）：**

```sql
SELECT plan, expires_at,
       CASE WHEN status IN ('active','past_due')
            AND datetime(expires_at, '+' || grace_days || ' days') > datetime('now')
       THEN 1 ELSE 0 END AS entitled
FROM subscriptions
WHERE user_id = ?
ORDER BY expires_at DESC LIMIT 1;
```

### 5.3 进度同步表（ECS，与控制面同库）

```sql
-- 每个实体（任务或剧情）一行；payload 是不透明 JSON，服务端只做合并、不解析业务字段
CREATE TABLE progress_entities (
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dataset     TEXT NOT NULL,              -- tasks|stories
  mode        TEXT NOT NULL,              -- regular|pve|pvps
  entity_id   TEXT NOT NULL,
  payload     TEXT NOT NULL,
  server_rev  INTEGER NOT NULL,           -- 归属用户的递增版本
  client_at   TEXT NOT NULL,              -- 客户端事件时间（合并依据）
  deleted     INTEGER NOT NULL DEFAULT 0, -- 剧情取消/删除的墓碑
  updated_at  TEXT NOT NULL,
  PRIMARY KEY(user_id, dataset, mode, entity_id)
);
CREATE INDEX idx_progress_pull ON progress_entities(user_id, server_rev);

-- 每用户一个全局版本号：GET /v1/progress?sinceRev= 用它做增量游标
CREATE TABLE progress_revs (
  user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  rev        INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

-- 最近 3 个全量快照，用于“恢复误操作”和排障
CREATE TABLE progress_versions (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rev        INTEGER NOT NULL,
  snapshot   TEXT NOT NULL,                -- 全量 JSON（可 gzip）
  created_at TEXT NOT NULL,
  UNIQUE(user_id, rev)
);
CREATE INDEX idx_progress_versions_user ON progress_versions(user_id, created_at DESC);

-- 冲突日志：最近 50 条/用户，客户端可查看并手动修正
CREATE TABLE progress_conflicts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  entity       TEXT NOT NULL,
  field        TEXT,
  client_value TEXT,
  server_value TEXT,
  resolved     TEXT,
  at           TEXT NOT NULL
);
CREATE INDEX idx_progress_conflicts_user ON progress_conflicts(user_id, at DESC);
```

**写入事务（单次 sync）**：`BEGIN IMMEDIATE` → 逐实体 `UPSERT` → `progress_revs.rev += 1` → 写一条 `progress_versions`（仅当跨过全量阈值或每 6 小时）→ `COMMIT`。WAL 下这个事务是毫秒级。

### 5.4 未来数据面（本机，SQLite WAL；本轮不实现）

> 以下 `presets / preset_versions / builds / market_*` 属于未来扩展，保留 DDL 作为设计储备；本轮**不建表、不部署数据面**。

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE presets (
  id            TEXT PRIMARY KEY,              -- 映射本地 clientId
  user_id       TEXT NOT NULL,                 -- 来自控制面令牌
  kind          TEXT NOT NULL,                 -- loadout|weapon
  name          TEXT NOT NULL,
  payload       TEXT NOT NULL,                 -- 原样 JSON，不在服务端解析
  version       INTEGER NOT NULL DEFAULT 1,
  deleted       INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE(user_id, kind, id)
);
CREATE INDEX idx_presets_pull ON presets(user_id, kind, updated_at);
CREATE INDEX idx_presets_alive ON presets(user_id, deleted, updated_at);

CREATE TABLE preset_versions (
  preset_id   TEXT NOT NULL,
  user_id     TEXT NOT NULL,
  version     INTEGER NOT NULL,
  payload     TEXT NOT NULL,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  PRIMARY KEY(preset_id, version)
);

CREATE TABLE builds (
  id          TEXT PRIMARY KEY,
  share_code  TEXT NOT NULL UNIQUE,            -- 8–12 位大写字母数字
  author_id   TEXT NOT NULL,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  weapon      TEXT,
  preset_payload TEXT NOT NULL,                -- 发布时的快照，不跟随作者后续修改
  visibility  TEXT NOT NULL DEFAULT 'public',  -- public|unlisted|hidden
  status      TEXT NOT NULL DEFAULT 'pending', -- pending|ok|rejected
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX idx_builds_feed ON builds(status, visibility, created_at DESC);
CREATE INDEX idx_builds_hot ON builds(status, visibility, copies DESC);
CREATE INDEX idx_builds_author ON builds(author_id, updated_at DESC);

CREATE TABLE build_stats (
  build_id  TEXT PRIMARY KEY REFERENCES builds(id) ON DELETE CASCADE,
  views     INTEGER NOT NULL DEFAULT 0,
  copies    INTEGER NOT NULL DEFAULT 0,
  likes     INTEGER NOT NULL DEFAULT 0,
  reports   INTEGER NOT NULL DEFAULT 0,
  hot_score REAL NOT NULL DEFAULT 0
);

CREATE TABLE build_reports (
  id         TEXT PRIMARY KEY,
  build_id   TEXT NOT NULL,
  reporter_id TEXT NOT NULL,
  reason     TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open',     -- open|done|dismissed
  created_at TEXT NOT NULL,
  UNIQUE(build_id, reporter_id)
);

CREATE TABLE market_snapshots (
  mode        TEXT NOT NULL,                   -- regular|pve
  fetched_at  TEXT NOT NULL,
  etag        TEXT,
  sha256      TEXT NOT NULL,
  item_count  INTEGER NOT NULL,
  status      TEXT NOT NULL,                   -- ok|stale
  PRIMARY KEY(mode, fetched_at)
);

CREATE TABLE market_items (
  mode        TEXT NOT NULL,
  item_id     TEXT NOT NULL,
  last_low    INTEGER,
  avg24h      INTEGER,
  base_price  INTEGER,
  trader_buy  INTEGER,
  trader_name TEXT,
  updated_at  TEXT,
  PRIMARY KEY(mode, item_id)
);

CREATE TABLE market_history (
  mode      TEXT NOT NULL,
  item_id   TEXT NOT NULL,
  hour      TEXT NOT NULL,                     -- 2026-11-08T03
  last_low  INTEGER,
  avg24h    INTEGER,
  PRIMARY KEY(mode, item_id, hour)
);
CREATE INDEX idx_market_history_hour ON market_history(hour);
```

**行情体积控制**：`market_items` 只保留最新值（约 5.5k×2 行）；`market_history` 每小时抽 1 条，30 天约 5.5k×2×720 ≈ 790 万行，按需保留 14 天（约 370 万行）即可；不需要把每 10 分钟的全量快照长期留存。

### 5.5 数据保留与删除

- 账号删除：30 天内软删（`status=disabled`），之后级联删 `devices/refresh_tokens/subscriptions/progress_*`。
- 会员到期：进度实体保留 **180 天**，期间续费可恢复；之后硬删。导出仅对有效会员开放（非会员无导出，见 §12.6）。
- 审计日志保留 180 天；支付记录按法规要求保留（具体年限待核实）。
- `progress_versions` 只保留最近 3 个版本；`progress_conflicts` 只保留最近 50 条。
- *未来*：行情历史 14 天；公开库下架内容 30 天供申诉。

---

## 6. 客户端改造点

### 6.1 硬约束：未启用云端时零影响（位置门控除外）

措施（缺一不可）：

1. `cloud.enabled` 默认 `false`；所有云端代码路径在关闭时直接返回 `disabled`，**启动阶段不产生任何 socket**。
2. `/api/cloud/*` 在关闭时返回 `501 {"ok":false,"error":{"code":"CLOUD_DISABLED"}}`，不影响现有 `/api/*` 与 `/events`。
3. 云端调用只在用户显式点击「登录/连接」后发生；进度同步仅在「已登录 + `progress.sync` 权益 + 用户开启同步」时启动。
4. 所有云端失败（超时/DNS/502/503/证书）都走同一条降级路径：**继续用本地快照或本地功能**，UI 只显示一个可关闭的角标。
5. 新增测试：断网启动、删除令牌文件、服务端 503、证书错误、`cloud.enabled=false` 五种场景下，现有全部 API/SSE/小窗行为不变。
6. **位置刷新门控与 `cloud.enabled` 解耦，且 R108 已在本地生效**：即使从不开启云端，非会员也是 10000ms/定位 10 秒。因此“离线零影响”只对其余功能成立；**免费档从 5000ms 变 10000ms 是已落地的行为变更**，必须在发版前公告（见 §11.9、§13 M3）。

### 6.2 `tools/config.py` 新增键

沿用 `normalize → 白名单 merge` 模式（与 `overlay.*` 一致）：

```json
{
  "cloud": {
    "enabled": false,
    "baseUrl": "https://47.96.68.209:8443",
    "caFile": "assets/cloud-ca.pem",
    "connectTimeoutMs": 3000,
    "readTimeoutMs": 8000,
    "progressSyncEnabled": false,
    "syncDebounceMs": 3000,
    "syncMinIntervalMs": 10000,
    "deviceName": "",
    "entitlementCacheTtlSec": 21600,   // 6 小时；仅用于离线显示
    "lastSyncAt": null
  }
}
```

规则：

- `baseUrl` 只接受 `https://`，拒绝 `http://` 与含用户信息的 URL；端口必须显式。
- `caFile` 必须是包内相对路径，禁止指向用户可写目录（防替换 CA）。
- `progressSyncEnabled` 必须同时满足 `enabled && 有 progress.sync 权益 && 服务端可达`，否则自动回退「仅本地」，不弹错误。
- `syncDebounceMs` 限 1000–10000、`syncMinIntervalMs` 限 5000–60000，`normalize()` 越界即钳制。
- **位置刷新门控复用 R108 的顶层 `account.member` 与现有 `auto_screenshot.interval_ms`**，不新增用户配置键；页面 `merge_ui()` 不写 `account`，会员态由云端权益同步后落到本地缓存/配置。定位侧用 `PositionTracker` 的 10 秒闸门，页面不再二次限速。
- **令牌不写进配置**：单独 `%APPDATA%\EFTMap\cloud-session.json`，权限 0600，内容 `{accessToken, refreshToken, deviceId, expiresAt}`；退出登录即删除。

### 6.3 新增 `tools/cloud.py`（本机 BFF）

- 仅用标准库 `urllib.request` + `ssl`；`ssl.create_default_context(cafile=…)`，**绝不 `verify_mode=CERT_NONE`**。
- 固定超时：连接 3 秒、读 8 秒；单次重试仅对幂等 GET；刷新令牌失败不自动重试。
- 令牌管理：access 过期前 60 秒刷新；刷新失败 → 清除令牌 → 标记「需重新登录」，不阻塞本地功能。
- 熔断：连续 3 次失败后 60 秒内不再请求云端，直接返回 `offline`。
- 所有错误转成内部结构 `{"ok":false,"reason":"offline|auth|entitlement|server|tls"}`，**不向页面泄漏服务端原文**。

本机新增端点（仅回环）：

| 端点 | 作用 |
|---|---|
| `GET /api/cloud/status` | 开关、登录态、权益缓存、最近错误 |
| `POST /api/cloud/login` | 代理登录，写 `cloud-session.json` |
| `POST /api/cloud/logout` | 吊销 + 删本地令牌 |
| `GET /api/cloud/entitlement` | 读缓存 + 后台刷新 |
| `POST /api/cloud/progress/sync` | 接收页面提交的增量，转发 `/v1/progress/sync`，返回合并结果 |
| `GET /api/cloud/progress?sinceRev=` | 代理增量拉取 |
| `GET /api/cloud/progress/export` | 代理全量导出（救援用） |
| `POST /api/cloud/progress/restore` | 用 `progress_versions` 的某个 `rev` 写回本地（需二次确认） |

### 6.4 前端改造

- 新增 `js/cloud.js`：`GWCloud.status/login/logout/entitlement`，只调用本机 `/api/cloud/*`。
- 新增 `js/cloud-progress.js`：读取 `GW.Tasks.progress()/storyProgress()`、算差异、调 BFF、应用 `serverChanges`；不直接发网络请求到 ECS。
- 菜单/设置页新增「云端」区块：登录、到期时间、同步开关、同步状态、错误角标。
- 任务页「我的进度」新增「云同步」状态条：`未登录 / 已同步 / 待上传 N 项 / 冲突 N 条 / 暂停（离线）`。
- `?mini=1` 路径直接跳过 `js/cloud.js` 与 `js/cloud-progress.js`，不显示任何云端 UI。
- *未来*：行情 provider 适配、公开库入口、预设同步徽标；本轮不实现。

**具体「开关包住哪个模块」：**

| 模块 | 改造方式 | `cloud.enabled=false` 时 |
|---|---|---|
| `tasks.js` `saveProgress()` / `saveStoryProgress()` | 成功后 `dispatchEvent("gw:progress-changed")`（新增，只加事件，不改存储） | 无影响；事件没人监听 |
| `tasks.js` 对外接口 | 新增 `GW.Tasks.applyStoryProgress(doc)`；`progress()/storyProgress()` 不变 | 无影响 |
| `js/cloud-progress.js` | **新增文件**；`cloud.enabled=false` 时不加载 | 无影响 |
| `js/cloud.js` | 新增 UI/登录/权益 | 不加载 |
| `tools/cloud.py` | 新增 BFF；`/api/cloud/*` 默认 501 | 原 `/api/*` 照常 |
| `tools/serve.py` | 只加路由挂载，不改现有 handler | 无影响 |
| `tools/live_prices.py` / `tools/presets.py` | **完全不改** | 无影响 |
| `js/game-mode.js` | 不改 | 无影响 |
| `?mini=1` 小窗 | 不加载云端脚本 | 无影响 |
| `tools/config.py` | 新增 `cloud.*` + 归一化 + 白名单 merge | 默认值即关闭 |

`/api/config` 只暴露非敏感 `cloud` 字段（开关、baseUrl、同步状态、到期时间）；**令牌只存在 `cloud-session.json`，永不进配置 payload、不进页面 localStorage、不进日志。**

### 6.5 进度云同步策略（本地 `localStorage` 是主副本）

**关键约束（先写清，避免设计跑偏）**：

- 进度存在**浏览器 `localStorage`**，Python 进程读不到；同步必须由页面 JS 发起（`GW.Tasks.progress()/storyProgress()` 读、`importProgress()/applyStoryProgress()` 写）。
- `localStorage` 按 **origin** 隔离：`127.0.0.1:8787`、`localhost:8787`、`127.0.0.1:8810`（小窗）各是一份。**只同步主窗口 origin 的进度**；小窗不参与同步。
- 页面把增量交给本机 BFF `/api/cloud/progress/sync`，BFF 再加令牌转发 ECS；页面永远不直连公网 IP。
- 同步元数据单独存 `localStorage["eftmap.cloud.sync.v1"]`：`{rev, base, meta, pending}`（结构见 §11.3.2），**不改动现有进度结构**。

**流程**：

1. 启动/登录：`GET /v1/progress?sinceRev=<本地 rev>` → 若云端有变更，弹出「发现云端进度（更新于 X），恢复 / 保留本地」；默认**不自动覆盖**。
2. 任意进度保存 → 3 秒防抖 → 计算差异（§11.3.3）→ `POST /v1/progress/sync`。
3. 收到 `serverChanges` → 先把当前进度备份到 `eftmap.cloud.lastgood.v1` → `importProgress` / `applyStoryProgress` 写回 → 再落盘。
4. 冲突：服务端返回 `conflicts`，客户端只在状态条显示条数，点击查看；不弹模态框打断游戏。
5. 离线：只写 `pending`，不重试登录；网络恢复后按 `at` 顺序重放，最多 3 次指数退避。
6. 到期/无权益：同步入口变灰并提示续费；**本地进度读写完全不受影响**。

### 6.6 权益与离线显示

- 登录成功后缓存 `entitlement`（含 `expiresAt`），最多 6 小时；仅用于 UI 显示「会员有效/即将到期」。
- 离线时：UI 仍显示上次权益，但所有云端数据请求直接走本地降级，不假装成功。
- 到期前 7 天在客户端提示续费；到期后不删除任何本地数据，只是云端入口变为「需要会员」。

---
## 7. 部署形态

### 7.1 ECS 目录与进程

```
/opt/eftmap-edge/
├── bin/                 # 控制面代码（Python 3.10 + venv 或纯标准库）
├── etc/
│   ├── Caddyfile
│   ├── edge.env         # 600，JWT 密钥/DB 路径/渠道密钥
│   └── tls/{ca.pem,server.pem,server.key}
├── data/edge.db         # SQLite（控制面）
├── logs/                # 仅 Caddy access log；应用日志走 journald
└── backup/              # 本地备份暂存，随后上传 OSS
```

| 进程 | 管理方式 | 内存预算（常驻） |
|---|---|---|
| `caddy` | systemd | 30–60 MB |
| `eftmap-edge`（控制面） | systemd，单实例 | 60–120 MB |
| `zerotier-one` | systemd（已有） | 20–40 MB |
| Ubuntu 基础 + journald + sshd + chrony | systemd | 250–450 MB |
| 备份脚本（每日一次） | systemd timer | 运行时 < 30 MB |
| **合计** | | **约 450–700 MB**，2 GiB 余量充足 |

建议加 1–2 GiB swap 文件（40 GiB 盘足够），防止偶发构建/备份峰值 OOM。**禁止在 ECS 跑 Postgres、Redis、Node、Docker 多容器。**

### 7.2 Caddyfile 草案（TLS + 路径路由 + 限流）

```caddyfile
{
    auto_https off          # 只用 8443，不开 80/443
    admin off
}

https://47.96.68.209:8443 {
    tls /opt/eftmap-edge/etc/tls/server.pem /opt/eftmap-edge/etc/tls/server.key

    encode zstd gzip
    log {
        output file /opt/eftmap-edge/logs/access.log {
            roll_size 50MB
            roll_keep 7
        }
        format json
    }

    # 基础限流（Caddy 需 rate_limit 插件；若不用插件则靠应用层）
    # rate_limit {
    #     zone per_ip { key {remote_host} events 30 window 1s }
    # }

    handle /v1/auth/* {
        reverse_proxy 127.0.0.1:9000
    }
    handle /v1/entitlement {
        reverse_proxy 127.0.0.1:9000
    }
    handle /v1/pay/* {
        reverse_proxy 127.0.0.1:9000
    }
    handle /v1/updates/* {
        reverse_proxy 127.0.0.1:9000
    }
    handle /v1/status {
        reverse_proxy 127.0.0.1:9000
    }
    handle /v1/progress* {
        reverse_proxy 127.0.0.1:9000
    }

    # 未来数据面（本轮不启用）：
    # handle /v1/market*   { reverse_proxy 10.147.20.10:8788 }
    # handle /v1/presets*  { reverse_proxy 10.147.20.10:8788 }
    # handle /v1/builds*   { reverse_proxy 10.147.20.10:8788 }

    # 后端不可达时返回结构化 503（客户端可识别并降级）
    handle_errors {
        @unavailable expression {http.error.status_code} >= 500
        header @unavailable Content-Type application/json
        respond @unavailable `{"ok":false,"error":{"code":"SERVICE_UNAVAILABLE","message":"云服务暂时不可用，本地功能不受影响"}}` 503
        respond "Not Found" 404
    }
}
```

> `rate_limit` 不是 Caddy 标准模块；若不想装 xcaddy 插件，把限流放在控制面/数据面应用层（按 IP+用户双桶），Caddy 只做连接数上限与超时。2 GiB 机器不建议自行编译插件。

**nginx 替代（更省内存，10–20 MB）：**

```nginx
server {
    listen 8443 ssl;
    server_name 47.96.68.209;

    ssl_certificate     /opt/eftmap-edge/etc/tls/server.pem;
    ssl_certificate_key /opt/eftmap-edge/etc/tls/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 1m;
    gzip on;
    gzip_types application/json;

    location ~ ^/v1/(auth|entitlement|pay|updates|status|progress) {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header X-Request-Id $request_id;
        proxy_read_timeout 10s;
    }
    # 未来数据面（本轮不启用）
    # location ~ ^/v1/(market|presets|builds) { proxy_pass http://10.147.20.10:8788; }
    location / {
        default_type application/json;
        return 503 '{"ok":false,"error":{"code":"NOT_FOUND"}}';
    }
}
```

**推荐 Caddy**：配置短、自动压缩、错误处理直观；nginx 更省内存但配置冗长。两者在 2 GiB 上都可行。

### 7.3 本机数据面（未来；本轮不部署）

> 范围收缩后，唯一服务端付费功能（进度同步）全部跑在 ECS，**本机不需要跑任何业务进程**。以下内容保留为未来行情/预设/公开库的设计储备。

- 若本机是 Windows：用 NSSM 或「任务计划程序（开机启动 + 失败重启）」把 `eftmap-data.exe`/`python -m tools.data_service` 注册为服务；日志写 `%APPDATA%\EFTMap\logs\data.log`，按天轮转。
- 若本机是 Linux：systemd unit，`Restart=always`，`RestartSec=5`。
- 数据面只监听 ZeroTier 私网地址 `10.147.20.10:8788`（或 `0.0.0.0` + 防火墙仅放行 ZT 网段），**绝不监听公网网卡**。
- 本机路由器**不做任何端口映射**；所有入站只经过 ZeroTier。

### 7.4 证书方案（无域名）

1. 离线生成根 CA（10 年）与服务器证书（3 年，SAN 必须包含 `IP:47.96.68.209`）。
2. 服务器只装 `server.pem/server.key`；根 CA 只导出 `cloud-ca.pem` 打进客户端包（公钥，无风险）。
3. 客户端 `ssl.create_default_context(cafile=cloud-ca.pem)`，Python 会校验证书链与 IP SAN；**不关闭校验、不忽略主机名**。
4. 轮换：新旧两张服务器证书同时部署（Caddy 支持证书链多张），客户端 CA 包同时带新旧根；提前 6 个月发版，避免老客户端被锁死。
5. 私钥只存 ECS `600`，不进 Git、不进客户端、不进备份的明文件（备份加密或排除 tls 目录）。
6. **纯 HTTP 只在 ZeroTier 私网内部允许**（ECS→本机 8788）；公网 8443 必须 TLS，否则 token 和会员数据在链路上裸奔。

### 7.5 备份

| 对象 | 频率 | 方式 | 保留 |
|---|---|---|---|
| ECS `edge.db` | 每日 03:10 | `sqlite3 edge.db ".backup /backup/edge-$(date).db"` | 7 日 + 4 周 |
| 配置/证书 | 变更时 | 手动加密后传 OSS | 永久（离线留一份） |
| *未来* 本机数据面 DB / 预设文件 | 每日 | 同上 | 7 日 + 4 周 |

- **进度数据是唯一服务端付费资产，备份优先级最高**：除每日全量备份外，`progress_versions` 保留最近 3 个版本，误操作可回滚。
- 备份上传到 OSS 私有 Bucket（`backups/`），生命周期 30 天自动删除；对象名带日期与 SHA-256。
- 恢复演练：每季度在另一台机器上恢复一次 `edge.db` 并用测试账号登录。
- **不要**把 `edge.env`（JWT 密钥、支付密钥）明文放 OSS；单独离线保存。

### 7.6 日志与监控

- 应用日志走 journald：`journalctl -u eftmap-edge`；限制 `SystemMaxUse=200M`。
- Caddy access log 只记 `requestId/method/path/status/bytes/duration/ip`，**不记 Authorization、密码、refresh token**。
- 监控：本机每 60 秒请求 `https://47.96.68.209:8443/v1/status`（带 pinning 或用 curl --cacert），连续 3 次失败发飞书/邮件告警；ECS 侧同时探测 `10.147.20.10:8788/healthz`。
- 指标最小集：控制面存活、数据面存活、行情 `ageSec`、磁盘使用率、SQLite 文件大小、429/5xx 比例。

---

## 8. 网络方案（已选定：公网 IP + 非标端口 8443 + ZeroTier 单隧道）

### 8.1 为什么选它

- 没有域名 → 不能用 80/443，也**不能接阿里云 CDN**（CDN 需要域名 CNAME 接入，大陆节点还要求备案）。
- 公网 IP + 非标端口不涉及域名 ICP；用户零安装（不需要装 ZeroTier），比「每人装 ZeroTier 加网络」获客摩擦低得多。
- 3 Mbps 足够承载 API 小包；大文件走 OSS，不挤占这条窄带。
- ZeroTier 只用 2 个节点（ECS + 本机），不碰免费版设备上限。**本轮它只承担运维（SSH/管理后台）与未来数据面**；进度同步走客户端 → ECS，不经过本机。

### 8.2 免备案实操与端口

| 项 | 结论 | 依据/状态 |
|---|---|---|
| 80/443 | 未备案域名解析到大陆 ECS 会被阻断 | 阿里云备案帮助中心（已访问，HTTP 200）：https://help.aliyun.com/zh/icp-filing/ ；具体拦截表现以控制台/工单为准（待核实） |
| 纯 IP 访问 | 不涉及域名 ICP；非 80/443 端口通常可用 | 行业惯例 + 阿里云安全组；**建议开工单确认当前策略（待核实）** |
| 端口范围 | 1024–65535 可选；推荐 **8443/TCP** | 避开 80/443/8080/8888/3128/25/135/139/445/3389 |
| 安全组 | 入方向仅 `8443/TCP 0.0.0.0/0`；SSH 22 仅管理员 IP 或 ZeroTier 网段；其余全部拒绝 | 阿里云控制台 |
| 系统防火墙 | `ufw allow 8443/tcp`；`ufw deny 80,443`；ZT 网段单独放行 | Ubuntu |
| 运营商/公司网络 | 少数企业网/校园网会封非标端口；客户端可配置备用 `9443` | 需真实用户网络验证（待核实） |
| 将来上域名 | 买域名 → 实名 → ICP 备案（个人/企业主体）→ DNS A 记录 → Caddy 自动 Let's Encrypt → 才能接 CDN | 备案材料/周期以阿里云为准（待核实） |

**风险点**：非标端口能降低扫描噪音，但不等于安全；公网 IP 仍会被全端口扫描，必须靠限流、鉴权、最小暴露面。

### 8.3 ZeroTier 单向隧道具体配置（本轮：运维 / 未来数据面）

> **本轮付费链路不经过 ZeroTier**：进度同步是「客户端 → 公网 8443 → ECS」。这条隧道留给 SSH/管理后台与未来的行情/预设数据面；不需要为它做任何用户侧配置。

目标：ECS 能访问本机的 `8788`（未来数据面），本机不需要公网入站。

1. **建网**：ZeroTier Central 新建 Private 网络，网段 `10.147.20.0/24`（**示例；若复用现有 moon 所在网络，按现有网段替换**）。
2. **加入**：
   - ECS：`sudo zerotier-cli join <NETWORK_ID>`，在 Central 授权，分配固定 `10.147.20.1`。
   - 本机：安装 ZeroTier One，`zerotier-cli join <NETWORK_ID>`，授权，固定 `10.147.20.10`。
3. **Moon**：两端都 `zerotier-cli orbit <moon_id> <moon_id>`（复用现有 moon）；`zerotier-cli listmoons` 确认。若两端能 P2P 直连会更快；否则走 moon 中继，延迟增加（实测待核实）。
4. **本机防火墙**：只允许 `10.147.20.1` 访问 `8788`：
   - Windows：入站规则「仅远程 IP 10.147.20.1，TCP 8788，允许」。
   - Linux：`ufw allow from 10.147.20.1 to any port 8788 proto tcp`。
5. **ECS 侧**：Caddy `reverse_proxy http://10.147.20.10:8788`（见 §7.2）；ECS 不需要监听 8788。
6. **验证**：
   - ECS：`curl http://10.147.20.10:8788/healthz`；
   - 本机：`zerotier-cli info`、`ping 10.147.20.1`；
   - 公网：`curl --cacert cloud-ca.pem https://47.96.68.209:8443/v1/status`。
7. **带宽注意（未来数据面才适用）**：本轮进度同步不经过 ZT，公网只计 ECS 出方向。若未来行情/预设走 ZT 反代，真正的隐藏瓶颈会是**本机上行带宽**（100 个并发 × 130 KB ≈ 13 MB 突发），需实测 ≥ 20 Mbps 上行。

### 8.4 TLS 取舍（没有域名）

| 方案 | 可用性 | 风险 | 结论 |
|---|---|---|---|
| 纯 HTTP 8443 | 可以 | token、密码、会员数据明文；任何中间人可改响应 | **禁止用于公网** |
| 自签证书 + 客户端忽略校验 | 可以 | 等于没有 TLS，且违反项目安全底线 | **禁止** |
| **自签 CA + 客户端 pinning** | 可以 | 证书过期/轮换需发版；CA 私钥泄露需全体换 CA | **推荐** |
| Let's Encrypt IP 证书 | 需要 80/443 或 DNS 验证；大陆未备案可能受阻；IP 证书有效期短 | 依赖外部政策，失败即全站不可用 | 不推荐（待核实） |
| Cloudflare Tunnel | 免公网端口，但 quick tunnel URL 随机、不可用于稳定 API | 不稳定、依赖第三方 | 不推荐 |

**落地**：客户端只信任包内 `cloud-ca.pem`，服务器证书 SAN=`IP:47.96.68.209`；Python 标准库即可完成校验。证书 3 年、CA 10 年，轮换前 6 个月双证书并行。

### 8.5 三种拓扑下的出站/入站路径（对照）

| 路径 | 客户端 → 云端 API | 服务端出站请求 | 结论 |
|---|---|---|---|
| A 域名 + 443 | `https://map.example.com/v1/...`，TLS 由 Let's Encrypt 自动 | 可接 CDN；行情可由 ECS 抓取（每月约 73 GB，占 3 Mbps 的 7.7%） | 体验最好，但需域名 + ICP，**已否决** |
| **B 公网 IP + 8443（已选）** | `https://47.96.68.209:8443/v1/...`，自签 CA pinning | **本轮无出站请求**（进度同步不抓上游）；未来行情从本机家庭宽带走 | **选定**：零备案、零客户端安装 |
| C ZeroTier 面向用户 | `http://10.147.20.1:8788/v1/...`（ZT 私网，可纯 HTTP） | 同 B | **已否决**：用户要装客户端、免费版节点上限、无法公开分享 |
| 参照：当前本地版 | `http://127.0.0.1:8787/api/...` | 本机 `live_prices.py` 抓取（可选开关） | 完全离线可用，不改 |

**要点**：本轮云端的**唯一出站流量是支付回调验签**（极少量）；没有任何抓取任务。未来行情若上线，应放在本机聚合，利用「上游 17 MB 整包不经过 ECS」这一点，ECS 只转发客户端要的小包。

---
## 9. 3 Mbps 带宽预算与容量测算

### 9.1 物理上限

- 3 Mbps = 3,145,728 bit/s ÷ 8 = **393,216 B/s ≈ 384 KiB/s** 持续。
- 理论月流量：384 KiB/s × 86,400 × 30 ≈ **949 GiB ≈ 1,020 GB**。
- 工程可用量按 **70%** 计（留 TCP 重传、峰值、监控、SSH）：**约 665 GiB/月 ≈ 714 GB/月**。
- 阿里云只对**出方向**计费/限速；入方向不计。瓶颈在「ECS 出网」与客户端下行。

### 9.2 逐项流量估算（本轮：仅进度同步）

| 请求 | 单次大小 | 频率 | 单用户/天 | 说明 |
|---|---|---|---|---|
| 权益校验 `/v1/entitlement` | 0.4 KB | 4 次 | 1.6 KB | 6 小时缓存，实际更少；支持 ETag |
| 登录 / 刷新 | 1 KB | 2 次 | 2 KB | access 15 分钟、refresh 30 天旋转 |
| 进度增量上传 `sync` | 0.2–5 KB（典型 2 KB） | 10 次 | **约 20 KB** | 3 秒防抖 + 10 秒节流 |
| 进度增量拉取 | 0.2–5 KB | 5 次 | 约 10 KB | 多数为 304 或空变更 |
| 全量恢复/导出 | 10–30 KB | 0.1 次 | 约 3 KB | 仅换机/重装时 |
| `/v1/status`、更新清单 | 1 KB | 2 次 | 2 KB | 更新清单本身很小（下载走 OSS） |
| **合计（典型）** | | | **约 35–40 KB/天** | |
| **合计（最坏）** | | | **< 150 KB/天** | 全量上传 + 频繁同步 |

### 9.3 能撑多少 DAU

| 口径 | 计算 | 结论 |
|---|---|---|
| 带宽上限 | 665 GiB/月 ÷ 35 KB/天 ≈ 1,990 万人·天/月 | 理论上 **数十万 DAU**，**带宽不是瓶颈** |
| 单进程 CPU / SQLite | 单次 sync ≈ 1–3 ms（事务 + 合并）；按 20% CPU 预算 ≈ 70–200 次/秒 | **2,000–5,000 DAU 内单机舒适**（每人每天 ~10 次 sync） |
| 实际建议 | 留余量 + 监控 P95 | **稳跑 2,000 付费 DAU；> 3,000 再考虑升配或换 Postgres** |

**结论**：范围收缩后，3 Mbps 与 2 GiB 都不是瓶颈；真正的上限是「单机 SQLite 与 Python 单进程」和「开发者能维护的复杂度」。这也意味着**不需要为容量做任何架构上的提前优化**。

### 9.4 峰值与并发

- 单次 sync 响应 < 10 KB；100 个并发 ≈ 1 MB，3 Mbps 下约 **2.6 秒**排空，不会雪崩。
- 写路径 `BEGIN IMMEDIATE` 串行化，事务毫秒级；Caddy 限制每 IP 连接数与速率，防止脚本刷。
- 客户端 3 秒防抖 + 10 秒最小间隔 + 每账号 200 次/天，天然削峰。
- **不要**为每个用户生成全量快照响应；按 `sinceRev` 只返回变更。

### 9.5 流量的硬红线

1. 更新包、地图大图、截图、任何 > 1 MB 的文件**不得经过 ECS**；只能 OSS（见 §10）。
2. 进度全量响应上限 256 KB；超限返回 `PAYLOAD_TOO_LARGE`，不静默截断。
3. 没有域名 → **不能接阿里云 CDN**；不要为“省 ECS 带宽”设计依赖 CDN 的方案。
4. *未来*行情若上线：快照必须 gzip、ETag/304、15 分钟抖动轮询；否则 3 Mbps 会被打满（见下表）。

### 9.6 未来参考：行情场景的旧估算（本轮不实现）

| 场景 | 单用户/天 | 665 GiB/月可支撑 | 结论 |
|---|---|---|---|
| 全量快照每 10 分钟、无 304 | 19 MB | 约 1,200 DAU | 不推荐，容易被峰值打爆 |
| ETag + 15 分钟轮询 + 抖动 | 4 MB | 约 5,800 DAU | 带宽不是瓶颈，本机上行才是 |
| 公开库带截图（100 KB/张） | +5 MB | 约 900 DAU | 截图必须走 OSS |
| 更新包走 ECS（150 MB/次） | — | 100 次即 22 GiB | **绝对禁止** |

---

## 10. 大文件分发：OSS 还是网盘

### 10.1 关键事实：OSS/CDN 不占 ECS 那 3 Mbps

OSS 与 CDN 是独立产品、独立计费与独立带宽：客户端从 OSS 默认域名下载时，流量走 OSS 的公网出口，**不经过 ECS 网卡**；ECS 只为「更新清单」付出几 KB。因此把更新包/图片放 OSS 后，3 Mbps 只承载 API 小包。这一条是选择 OSS 的核心理由。

（阿里云 OSS 计费说明：公网流出流量单独计费，上传与内网流量免费；见 §10.2 出处。）

### 10.2 价格与出处（抓取日期 2026-11-08）

| 项目 | 单价 | 出处 | 可信度 |
|---|---|---|---|
| OSS 标准存储（本地冗余） | **0.09 元/GB/月** | 阿里云开发者社区《2026年阿里云OSS最新收费标准价格表》(2026-01-06) | 第三方整理；官网定价页为 JS 渲染，未能机读，**下单前以控制台为准（待核实）** |
| OSS 公网流出（忙时 08:00–24:00） | **0.50 元/GB** | 同上 | 同上 |
| OSS 公网流出（闲时 00:00–08:00） | **0.25 元/GB** | 同上 | 同上 |
| OSS → CDN 回源流出 | **0.15 元/GB** | 同上 | 同上 |
| OSS GET 请求 | 0.01 元/万次 | 同上 | 同上 |
| CDN 中国内地 0–10 TB | **0.24 元/GB** | 阿里云 CDN 定价页（已抓取，HTTP 200）：https://www.aliyun.com/product/cdn/pricing | 高 |
| CDN 10–50 TB | 0.23 元/GB | 同上 | 高 |
| ECS 续费 | **以账单为准** | 用户账户 | **待核实**；测算暂按 ¥120/月（区间 ¥99–200） |

> **CDN 在当前方案不可用**：阿里云 CDN 需要「域名 + CNAME 接入」，大陆节点还要求域名备案（接入要求以阿里云 CDN 文档/工单为准，**待核实**）。用户没有域名，所以只能走 **OSS 默认域名直连**，不能上 CDN；OSS 默认域名是否受未备案限制也建议开工单确认（**待核实**）。上表 CDN 价格仅作为「将来买域名后」的参考。

### 10.3 三档月成本（只算大文件出流量）

按 OSS 公网流出、忙时价 0.50 元/GB（保守，不假设闲时占比）：

| 月出流量 | OSS 直连（0.50） | 若将来有 CDN（0.24 + 回源） | 存储 5 GB | 月合计（OSS） |
|---|---|---|---|---|
| 100 GB | ¥50 | ¥24 + 回源约 ¥0.75 | ¥0.45 | **约 ¥50** |
| 500 GB | ¥250 | ¥120 + 回源约 ¥3.75 | ¥0.45 | **约 ¥250** |
| 1 TB | ¥500 | ¥240 + 回源约 ¥7.5 | ¥0.45 | **约 ¥500** |

- 若流量集中在闲时（00:00–08:00），OSS 成本可降到 **¥25 / ¥125 / ¥250**。
- 更新包按 150 MB/次估算：100 GB ≈ 680 次下载；500 GB ≈ 3,400 次；1 TB ≈ 6,800 次。
- 与 ECS 升级带宽对比：把 3 Mbps 升到 5 Mbps 的月费通常高于 OSS 100 GB 流量费，且仍会被峰值打爆；所以**大文件走 OSS 更划算**（具体升配价待核实）。

### 10.4 网盘的隐性成本

| 维度 | 网盘（百度/阿里云盘/夸克等） | 影响 |
|---|---|---|
| 登录 | 用户必须登录网盘账号，部分还要 App | 每步都可能流失；无法自动化 |
| 限速 | 非会员常见 100–300 KB/s（具体以各产品为准，待核实） | 150 MB 需 8–25 分钟，更新体验差 |
| 直链 | 分享链接会失效、被审核、需要提取码 | 版本清单一夜失效，客服爆炸 |
| 校验 | 无稳定 API 给 SHA-256/版本清单 | 无法自动校验完整性，只能人工比对 |
| 自动化 | 无法脚本化上传/替换/统计 | 每次发版手动操作，易错 |
| 风控 | 个人账号存大量安装包可能被限/封 | 更新通道随时中断 |
| 成本 | 表面 ¥0（或会员费） | 隐性人力 + 失败率 + 用户流失远高于 OSS 的 ¥50–500/月 |

**失败率与操作步骤**：网盘方案每版更新至少 5 步（打开网页→登录→保存→下载→解压→手动覆盖），OSS 方案客户端内 1 步「检查更新」。按 100 次更新、10% 失败率估算，网盘多出约 10 次人工支持；按每次 15 分钟计，≈2.5 小时/百次，已经超过 OSS 月费。

### 10.5 推荐：OSS 直连（不上 CDN）

- Bucket：`eftmap-updates`，华东1（杭州），标准存储本地冗余；开启版本控制与生命周期。
- 目录：`win/{version}/EFTMap-{version}.zip`、`linux/…`、`manifest.json`（也可只由控制面提供）。
- 权限：更新包 **公共读**（不含敏感内容，方便客户端直连）；备份与付费数据用 **私有 + 签名 URL**。
- 不开启静态网站托管、不列目录、不开跨域（客户端是 Python，不需要 CORS）。

### 10.6 客户端更新流程（清单 → 校验 → 回滚）

```
1. GET /v1/updates/manifest            （ECS 控制面，免费，几 KB）
2. 比较 version / minVersion；不需要更新则结束
3. 从 OSS 下载 zip 到 %TEMP%\eftmap-update-{version}.part
   - 支持 Range 续传（可选）；显示进度；3 次重试
4. 计算 SHA-256，与 manifest.sha256 比对
   - 不匹配：删除临时文件，保留当前版本，上报 /v1/updates/report（可选）
5. 解压到 versions/{version}/，校验入口文件存在
6. 原子切换 current 指针；保留上一版本目录
7. 启动失败（10 秒内退出/健康检查失败）→ 自动回滚到上一版本
```

清单字段必须包含：`version / minVersion / size / sha256 / url / notes / rollbackVersion / publishedAt`。**不要**只给一个网盘链接；没有哈希就无法自动校验。

---
## 11. 会员权益边界与定价测算（收缩版：进度云备份 + 位置刷新频率）

> 本节按 2026-11-08 最终口径：**付费权益有两项**——①任务/剧情进度的跨设备云备份（服务端）；②位置刷新频率（非会员自动截图锁 10 秒/张、定位合计 10 秒一次；会员自动截图可调 200–60000ms、定位不限；纯客户端门控）。月付 ¥6、年付 ¥72。实时行情、云预设、公开构筑库、统计面板仍全部不做会员。

### 11.1 权益可行性：实话

**能提供什么**：①把浏览器 `localStorage` 里的任务进度、剧情进度自动备份到服务端，并在另一台设备/重装后恢复；②把非会员的位置刷新频率上限从 10 秒放开（自动截图间隔可调 200–60000ms、定位不限）。

**免费版已经有什么**：

- 任务进度本地永久保存（`eftmap.tasks.progress.v1`），刷新/重开不丢；
- 现有代码有任务导出/导入 JSON（[tasks.js](../tasks.js#L3866-L3943)），但**新口径下免费版将移除该入口**（见 §12.6，属于已决定的产品风险）；
- 剧情进度本地保存，现有代码也没有导出/导入；
- 用户还可以手动拷 `%APPDATA%` 或浏览器配置，或使用浏览器账号同步（如果开启）。

**痛点在哪**：

- 真正会丢进度的场景只有：**换电脑、重装系统、清理浏览器数据、误操作导入覆盖、多人共用电脑**。
- EFT 是 Windows 单机游戏，绝大多数玩家只有一台 PC；「跨设备」是低频需求。
- 「不丢进度」是一次性焦虑，不是每月都发生的持续价值；用户买完第一月后，续费理由很弱。

**结论（明确写出来）**：

> **两项组合后仍不足以支撑一个可持续的订阅业务，但从“单项明显撑不住”变为“可以小规模试一试”。** 它适合作为「低价保险 + 局部体验解锁 + 账号/支付/权益体系的验证产品」，不适合作为主要收入来源。按 ¥6 计算，100 个付费用户月收入 ¥600，**覆盖基础设施（约 ¥33/月）绰绰有余——6 个用户即可打平**；但要覆盖开发者时间需要约 845 个付费用户，而“备份 + 位置刷新”这两个弱需求几乎不可能达到这个量级。第二项的价值在于**挽回重度定位用户的体验**（每天开自动截图、习惯 5 秒/小半径地图的人会在意），而不是拓宽用户群；它同时会把一部分免费用户推成“被降速”的负面感受（详见 §11.9）。

**替代建议（按优先级）**：

1. **只做年付，不做月付**：¥72/年（若做限时促销可用 ¥60，需你确认，不擅自改正式价），定位「一年一次的数据保险」，降低续费频次与支付成本；月付 ¥6 保留为可选，但默认推年付。
2. **把「进度恢复」做成一次性服务**：例如 ¥19.9/次人工协助恢复（含服务端历史版本），不做订阅；适合极低频需求。
3. **免费 + 自愿赞助**：同步免费，靠爱发电赞助；不承诺 SLA，不做法务意义上的“售卖”。
4. **保留账号/权益底座，等未来有第二个持续价值再开订阅**：现在只把 M1（账号 + 权益 + 进度同步）做完，不对外承诺“长期会员”。
5. **增加一个持续价值（若坚持订阅）**：云端历史版本（可回滚到任意一次备份）、进度统计/成就、跨设备自动合并——但这些已超出“进度备份 + 位置刷新”的当前收缩口径，需另行决策。

### 11.2 现状核查：进度到底存在哪、长什么样

| 项 | 事实 | 证据 |
|---|---|---|
| 任务进度键 | `localStorage["eftmap.tasks.progress.v1"]` | [tasks.js](../tasks.js#L21) |
| 任务进度结构 | `{schema:1, modes:{regular:{taskId:{status,objectives:{objectiveId:true/false},updatedAt}}, pve:{…}, pvps:{…}}}` | [tasks.js](../tasks.js#L181-L203)、[r19.27/report.md](./r19.27/report.md#L117) |
| 任务状态枚举 | `none / active / completed / failed` | [tasks.js](../tasks.js#L50-L55) |
| 任务写入路径 | `setStatusRaw` → `setStatus` / `applyStatusBatch`；目标勾选 `toggleObjective`；导入 `importProgress` | [tasks.js](../tasks.js#L320-L339)、[tasks.js](../tasks.js#L370-L390)、[tasks.js](../tasks.js#L392-L410)、[tasks.js](../tasks.js#L3908-L3943) |
| 任务导出 | `exportProgress()` 生成 `kind:"eftmap-task-progress"` 的 JSON，含三模式 | [tasks.js](../tasks.js#L3866-L3893) |
| 剧情进度键 | `localStorage["eftmap.stories.progress.v1"]` | [tasks.js](../tasks.js#L24) |
| 剧情进度结构 | `{schema:1, modes:{regular:{steps:{storyId:{stepId:true}}, choices:{storyId:{key:value}}}, …}}` | [tasks.js](../tasks.js#L4072-L4092)、[tasks.js](../tasks.js#L4343-L4367)、[tasks.js](../tasks.js#L4457-L4466) |
| 剧情写入路径 | `applyStoryStepBatch`（完成/撤销步骤，失败回滚）、`chooseStoryOption`（选项） | 同上 |
| 剧情导出 | **没有导出/导入** | 全文搜索只有任务导出 |
| 三模式隔离 | `regular / pve / pvps` 各自一份，互不影响 | [tasks.js](../tasks.js#L38-L45)、[r86-storyline/ledger.md](./r86-storyline/ledger.md#L151-L152) |
| 数据规模 | 任务 503/499/462 条（三模式）；剧情 10 条故事、266 个步骤 | [r46-package-ledger.md](./r46-package-ledger.md#L71)、本次读取 `data/stories.json` |
| 对外接口 | `GW.Tasks.progress()` / `storyProgress()` 返回深拷贝；`importProgress(text)` 可导入任务进度 | [tasks.js](../tasks.js#L4913-L4923) |
| 来源差异 | localStorage 按 **origin** 隔离：`127.0.0.1:8787` 与 `localhost:8787`、`8810` 小窗各是一份；同步必须由**页面 JS**读取，不能由 Python 直接读浏览器存储 | 浏览器同源策略；`tools/overlay.py` 走 8810 |

**关键结论**：云同步不是“服务端读文件”，而是：

```
页面 JS（GW.Tasks.progress()/storyProgress()）
  → 计算差异
  → 本机 BFF /api/cloud/progress/sync
  → ECS /v1/progress/sync
  ← 返回服务端变更
  → 页面 JS 应用（任务用 importProgress 语义；剧情需新增 applyStoryProgress）
```

**客户端必须补的两个小接口**（设计层面，不本轮改码）：

1. `GW.Tasks.applyStoryProgress(doc)`：把服务端合并后的剧情进度写回 `state.storyProgress` + `saveStoryProgress()`；目前没有这个入口。
2. `GW.Tasks.progressChanged` 事件：在 `saveProgress()` / `saveStoryProgress()` 成功后 `dispatchEvent(new CustomEvent("gw:progress-changed"))`，供同步模块监听；否则只能轮询比对。

**剧情进度缺少 `updatedAt`**：现有结构只有 `steps` 和 `choices`，没有每条记录的更新时间。同步层必须在 `eftmap.cloud.sync.v1` 里维护 `recordMeta`（`storyId → {at, rev}`）和删除墓碑；不改原进度结构，避免影响现有读写。

### 11.3 同步协议与冲突算法（具体，不写空话）

#### 11.3.1 数据单位

| 数据集 | 实体 | 载荷 |
|---|---|---|
| `tasks` | `mode + taskId` | `{status, objectives:{oid:bool}, updatedAt}` |
| `stories` | `mode + storyId` | `{steps:{stepId:true}, choices:{key:value}, stepTombstones:{stepId:at}, choiceTombstones:{key:at}}` |

- 任务删除：现有代码不会删任务记录，`status:"none"` 就是“未开始”；同步把 `none` 当普通值，不产生墓碑。
- 剧情删除：取消勾选会 `delete m.steps[sid][id]`；同步层必须把它转成 **显式墓碑 `false` + 时间戳**，否则另一端会把“取消”误判为“从未完成”。
- 目标取消：`toggleObjective` 会写 `false`；同步层把 `false` 当显式值发送，不省略。

#### 11.3.2 客户端状态

`localStorage["eftmap.cloud.sync.v1"]`（新增，独立于进度）：

```json
{
  "rev": 42,
  "base": { "tasks": { "regular": { "taskId": {"status":"completed","objectives":{}} } },
            "stories": { "regular": { "storyId": {"steps":{},"choices":{}} } } },
  "meta": { "tasks/regular/taskId": {"rev":7,"at":"2026-11-08T03:00:00Z"},
            "stories/regular/storyId": {"rev":9,"at":"2026-11-08T03:01:00Z"} },
  "pending": [ {"dataset":"tasks","mode":"regular","id":"taskId","value":{…},"at":"…","baseRev":7} ]
}
```

- `base` = 上次成功同步后的快照；`pending` = 离线队列；`rev` = 服务端全局版本。
- 首次登录且本地/云端都为空：直接建立 base。
- 首次登录本地有、云端空：全量上传。
- 本地空、云端有：先拉取，提示“检测到云端进度，是否恢复？”；用户确认后再写入本地。
- 两边都有：走 11.3.4 的逐实体合并。

#### 11.3.3 差异计算（客户端）

```text
function diff(dataset, base, current, meta):
  changes = []
  for mode in [regular, pve, pvps]:
    keys = union(keys(base[mode]), keys(current[mode]))
    for id in keys:
      b = base[mode][id]; c = current[mode][id]
      if deepEqual(b, c): continue
      changes.push({
        dataset, mode, id,
        value: c || null,          // null = 删除
        at: nowIso(),              // 本次变更时间
        baseRev: meta[dataset+'/'+mode+'/'+id]?.rev || 0
      })
  return changes
```

- 任务：比较 `status` 与 `objectives` 的每个键（`false` 也算变化）。
- 剧情：比较 `steps`/`choices`；`base` 有而 `current` 无的键 → 生成 `false` 墓碑。
- 防抖：最后一次变更后 **3 秒**合并发送；单批最多 50 个实体；超过则发全量。
- 节流：任意两次上传间隔 ≥10 秒；每 5 分钟至少一次心跳（仅当 `pending` 非空）。
- 触发点：`gw:progress-changed`、登录成功、网络恢复、页面隐藏（`visibilitychange`，`fetch keepalive`）。
- 离线：只写 `pending`，不重试登录；恢复后按 `at` 顺序重放。

#### 11.3.4 服务端合并（逐实体，带版本）

服务端为每个实体保存 `payload / server_rev / client_at / deleted`。

```text
for each change:
  server = load(user, dataset, mode, id)
  if server == null or change.baseRev == server.rev:
      accept(change)                       # 快路径：无并发
  else:
      resolveConflict(server, change)      # 双方都改过
```

**任务冲突（record-level LWW + 完成优先）：**

```text
function resolveTask(server, client):
  if server.status == "completed" and client.status != "completed": return server
  if client.status == "completed" and server.status != "completed": return client
  if abs(client.at - server.client_at) > 60s: return later(client, server)
  # 60 秒内视为时钟抖动/同一操作：
  # 状态优先级 completed > failed > active > none
  if rank(client.status) > rank(server.status): return client
  if rank(client.status) < rank(server.status): return server
  # 状态相同 → objectives 取并集（true 优先，false 不覆盖 true）
  merged.objectives = unionTrue(server.objectives, client.objectives)
  return merged
```

- 完成优先是为了「绝不把用户已完成的进度改回进行中」；代价是极端情况下两台设备同时操作会保留“完成”，冲突写入 `conflicts` 供用户查看。
- 同一任务在两台设备上分别勾选不同目标：`objectives` 取 `true` 并集，不会互相抹掉。
- 一台设备刚取消目标（`false`），另一台在 60 秒内勾上（`true`）→ 取 `true`；超过 60 秒按时间戳，后操作者胜。

**剧情冲突（按 step / choice 粒度）：**

```text
function resolveStory(server, client):
  for stepId in union(server.steps, client.steps, tombstones):
    s = server.steps[stepId] ? true : false; sAt = server.stepAt[stepId] || server.client_at
    c = client.steps[stepId] ? true : false; cAt = client.stepAt[stepId] || client.at
    if s == c: keep
    else if cAt > sAt + 60s: value = c
    else if sAt > cAt + 60s: value = s
    else: value = true            # 60 秒内冲突 → 宁可保留“已完成”
  for key in union(server.choices, client.choices):
    if both changed and timestamps ≤60s: prefer server（避免来回抖动）
    else later timestamp wins
```

- 每个 step 单独 LWW，不是整条 story 一刀切；这样 A 设备完成第 1 步、B 设备完成第 2 步能合并。
- 取消勾选带墓碑和时间戳，避免“并集”把取消操作复活。
- 60 秒内的 true/false 冲突一律 `true`，这是“绝不丢进度”的取舍；在冲突日志里明确标注，用户可手动修正。

**服务端响应：**

```json
{
  "ok": true,
  "data": {
    "rev": 43,
    "accepted": 12,
    "conflicts": [
      {"entity":"tasks/regular/t1","field":"status","client":"active","server":"completed","resolved":"completed"}
    ],
    "serverChanges": [
      {"dataset":"stories","mode":"regular","id":"s1","value":{...},"rev":11}
    ]
  }
}
```

客户端收到 `serverChanges` 后用 `importProgress` / `applyStoryProgress` 写回；**写入前先备份当前 localStorage 到 `eftmap.cloud.lastgood.v1`**，失败可回滚。

#### 11.3.5 上传时机（明确）

| 时机 | 行为 |
|---|---|
| 任意进度保存后 | 3 秒防抖，合并成一批 |
| 登录成功 | 先 `GET /v1/progress` 拉取，再按合并结果上传 |
| 网络恢复 | 重放 `pending`，最多 3 次指数退避 |
| 页面隐藏/关闭 | `fetch(..., {keepalive:true})` 尽力发送，不阻塞关闭 |
| 定时 | 每 5 分钟仅当 `pending` 非空 |
| 手动 | 设置页「立即同步」按钮 |

### 11.4 数据量、存储与安全

| 项 | 估算 | 说明 |
|---|---|---|
| 单任务记录 | 80–130 B | `status` + 3–5 个 objective + ISO 时间 |
| 单模式全完成任务 | 503 × ~100 B ≈ **50 KB** | 最坏情况（全部完成、全部目标勾上） |
| 三模式任务全量 | ≈ **150 KB** | 绝大多数用户只有 1–2 个模式有数据 |
| 剧情全量 | 266 step × ~25 B ≈ **6.7 KB**，三模式 ≈ **20 KB** | 10 条故事 |
| 单用户全量最坏 | **< 200 KB** | gzip 后约 5–20 KB |
| 典型单用户 | **10–30 KB** | 多数任务未开始 |
| 单次增量 | **0.2–5 KB** | 完成一个任务 / 勾几个目标 |
| 1,000 付费用户日流量 | 1000 × 10 次 × 2 KB ≈ **20 MB/天** | 占 3 Mbps 的 0.06% |
| 2,000 用户存储（3 版本） | 2000 × 30 KB × 3 ≈ **180 MB** | 最坏 1.2 GB；40 GiB 盘充足 |

**安全评估**：

- 进度数据只含**任务/剧情 ID、状态、objective/step 布尔值、时间戳**；不含游戏 ID、邮箱、截图、聊天、成就名称。敏感度低，但能推断游玩进度与活跃时间。
- 传输：TLS + 客户端 pinning；服务端数据库文件 `600`，备份加密或至少私有 Bucket。
- 不需要应用层逐字段加密（会给恢复和排障添麻烦）；**不要**在日志里打印 payload，只记 `userId/bytes/rev/conflictCount`。
- 若未来加入游戏 ID / 角色名 / 成就展示，再评估加密或干脆不存。
- 删除：账号删除后 30 天硬删；到期后云端副本保留 **180 天**，期间续费可恢复，之后删除；导出接口仅对有效会员开放（见 §12.6 产品风险）。

### 11.5 成本测算与定价（¥6 档，ECS 按实际续费）

**假设（2026-11-08 更正）**：ECS **¥100/年 ≈ ¥8.3/月**（已确认实际续费口径）；OSS 备份约 ¥5–20/月；支付费率 0.6%；杂项 ¥20/月；不含人力、客服、税费、退款。月付实收 = `6 × (1-0.6%) ≈ ¥5.96`。

| 项目 | 100 付费 | 500 付费 | 2,000 付费 |
|---|---|---|---|
| 月收入（¥6） | ¥600 | ¥3,000 | ¥12,000 |
| 实收（扣 0.6%） | ¥596.4 | ¥2,982 | ¥11,928 |
| ECS 续费摊销 | ¥8.3 | ¥8.3 | ¥8.3 |
| OSS / 备份 | ¥5 | ¥10 | ¥20 |
| 杂项 | ¥20 | ¥20 | ¥20 |
| **月成本** | **约 ¥33.3** | **约 ¥38.3** | **约 ¥48.3** |
| **月毛利** | **约 ¥563（94%）** | **约 ¥2,944（99%）** | **约 ¥11,880（99.6%）** |

**盈亏平衡（重算）**：

- 只算基础设施：固定约 **¥33/月** ÷ ¥5.96 ≈ **5.6 人** → **按 6 人计**（若按 ¥35 保守口径则 7 人）。
- 计入开发者机会成本 ¥5,000/月：`(5,000 + 33) ÷ 5.96 ≈ **845 人**`。
- 再加兼职客服 ¥1,000/月：`(6,033) ÷ 5.96 ≈ **1,013 人**`。
- **结论**：ECS ¥100/年 让“打平服务器”几乎不构成门槛（6 个用户）；真正的门槛仍是**人的时间**。按这两项权益的强度，800+ 付费用户不现实——这也是为什么本方案不把它当主营业务。
- 前提提醒：¥100/年属于当前优惠续费价，若阿里云恢复标准价，基础设施平衡点会上升；届时按新账单重算即可，不影响“人力才是大头”的结论。

**年付是否调价（最终建议）**：

- 现方案 ¥72/年 = 月付 ×12，**没有任何折扣**，用户没有理由预付；结果大概率是绝大多数选月付，支付次数多、流失快。
- **最终建议：正式价维持你定的 ¥72/年，不擅自改价；若要给折扣，只做“限时首发 ¥60”**（等效 ¥5/月，约 16.7% 折扣），活动结束后回到 ¥72。¥66 备选但折扣感弱。
- 若你希望长期年付折扣，再改成 ¥60 正式价；这需要你确认，本文不默认。
- 年付对 ARPU 的影响（按 ¥60 活动价测算）：表面 ARPU 从 ¥6 降到 ¥5，但年付续费率通常高于月付（假设月流失 15%，年续费 60%）：
  - 月付 LTV ≈ 6 / 0.15 = ¥40；
  - 年付 LTV ≈ 60 × (1 + 0.6 + 0.36 + …) ≈ ¥90；
  - **年付更低单价反而带来更高 LTV**，且支付费/客服次数更少。
- **不建议买断**：单一功能买断无法覆盖长期存储与恢复成本，也容易让用户觉得“一次付完就该永久服务”。

### 11.6 免费 / 付费边界如何落地

**免费档（基础功能全开，但有三处限制，其中后两处是同一权益的两个面）**：

- 本地任务/剧情进度保存、刷新恢复；
- 所有地图、任务树、剧情树、配装、ADS、小窗、截图（**截图动作本身免费，手动按截图键永远可用**）；
- **限制 1：免费版将移除任务导出/导入入口**（原 `GW.Tasks.exportProgress/importProgress` 的 UI），免费用户不再有手动备份能力（风险见 §12.6）。
- **限制 2：自动截图间隔锁死 10000ms、不可调**。这**不是“零影响”**：R108 之前的默认是 **5000ms**，老配置读取时会被钳到 10000（新装默认已是 10000），所以老用户会从“5 秒一张”变成“10 秒一张”，是**对旧版本的降速**；原本用 200–5000ms 的用户受影响更大。截图功能本身不关闭，只是频率被限制。
- **限制 3：定位更新合计锁 10 秒一次**。自动截图与手动截图两个来源合并计时；手动按截图键仍会出图、仍会保存，但地图位置最多每 10 秒跟随一次。小地图半径 25/50m 时感知最强（详见 §11.9）。

**付费（¥6/月 或 ¥72/年）**：

- 自动跨设备同步（任务 + 剧情）；
- 服务端备份与重装恢复；
- 冲突合并 + 最近 50 条冲突日志；
- 云端保留 180 天（到期后）；
- 会员专属导出（`GET /v1/progress/export`，仅用于救援，不作为 UI 常规入口）；
- **位置刷新不限速**：自动截图间隔可调 **200–60000ms**；定位随新截图即时跟随，不再做 10 秒合并限速。

**客户端如何知道有没有会员**：

1. 登录后 `GET /v1/entitlement` → 页面缓存 `localStorage["eftmap.cloud.entitlement.v1"] = {plan, expiresAt, features:["progress.sync","position.refresh"], cachedAt}`，最多 6 小时；
2. UI 只根据缓存显示“云同步”开关、截图间隔控件与到期提示；
3. 每次 `/v1/progress/*` 请求由**服务端**校验 token + 权益 + 设备数；客户端不负责放行；
4. **`position.refresh` 只用于本地 UI/限速策略，不参与任何服务端校验**——因为它不产生服务端请求，也无法被服务端验证。
5. 未登录：云同步入口显示“登录后可用”；截图间隔/定位按免费档锁 10 秒，本地地图、任务、剧情浏览完全不变。

**被破解的损失评估**：

- 客户端是 Python/JS，必然可解包；但进度数据在服务端，破解版**只能改 UI 显示，拿不到别人的进度**。
- 最坏情况是一个人用付费账号带多台设备：用 **3 台设备上限 + 每设备 refresh 绑定 + 每账号每日同步配额（如 200 次）** 控制。
- 因此**不值得投入重型 DRM/混淆/反调试**；投入应放在：令牌安全、设备上限、限流、审计。破解收益极低，过度防护只会伤害正常用户。

### 11.7 降级与收费承诺

**未登录 / 离线 / 服务端挂掉**：

- 本地 `saveProgress()` / `saveStoryProgress()` 先行，云端失败不影响本地写入；
- 同步模块进入 `offline`，`pending` 留队列，UI 显示“云同步暂停，本地进度已保存”；
- 服务端 503 时客户端不重试登录、不覆盖本地；恢复后自动重放；
- 页面关闭时不做阻塞式同步，最多 `keepalive` 尽力发送。

**用户协议必须写清**：

1. 「本地 `localStorage` 是进度的主副本；云备份是尽力而为的副本，不承诺 100% 不丢。」
2. 「服务端连续不可用超过 72 小时，按天数顺延会员期；超过 15 天可按剩余天数退款。」
3. 「云备份为尽力而为的副本；**免费版不提供导出/导入**，本地浏览器数据清理后无法自行恢复，请在会员有效期内保持同步。」
4. 「会员到期后云端副本保留 180 天；期间续费可恢复，之后删除；导出仅对有效会员开放。」
5. 「禁止账号共享/转售；设备数超过 3 台时可暂停云同步，本地功能不受影响。」
6. 「**位置刷新频率是本地功能门控**，不依赖云端；服务中断期间按本地权益缓存执行，不因服务中断而顺延或退款；它可被本地修改绕过，不属于安全承诺。」

**不建议承诺**：99.9% 可用性、永久保留、跨版本无限恢复、因服务端故障赔偿间接损失。

---


### 11.9 第二付费点：位置刷新频率（最终口径：非会员 10000ms）

#### 11.9.1 最终口径（已定）

| 来源 | 非会员（未登录 / 未付费 / 已过期） | 会员（有效） |
|---|---|---|
| 自动截图 | **锁死 10000ms，不可调**；输入框禁用，启动/刷新权益时把配置强制写回 10000 | 可调 **200–60000ms** |
| 手动按截图键 | 仍可截图、仍会出图；但它触发的**定位更新**与自动来源**合并计时** | 不限制 |
| 合并规则 | 两次“地图位置更新”之间**至少 10 秒**；关门期间**不扫描、不广播、不排队**，10 秒到点扫最新一张 | 每出现一张新截图就跟随 |

**一句话**：这不是“截图间隔”和“定位”两项权益，而是**同一项权益（位置刷新频率上限）的两个面**。非会员的地图位置最多 10 秒动一次；会员回到“有图就跟”。

#### 11.9.2 现状核查（R108 已在本地落地）

| 层 | 位置 | 现状 |
|---|---|---|
| 锁定值 / 会员判定 | [config.py](../tools/config.py#L48-L54)、[config.py](../tools/config.py#L200-L212) | `SHOT_INTERVAL_LOCKED_MS=10000`；只有 `account.member === true` 才算会员，未登录/缺字段/非 true 一律非会员 |
| 通用钳制 | [config.py](../tools/config.py#L215-L234) `clamp_interval(value, member)` | `member=False` → **固定 10000**（不透传用户值）；`member=True` → 200–60000；`member=None` → 通用区间清洗 |
| 默认配置 | [config.py](../tools/config.py#L159-L181) | 默认 `account.member=false`；默认 `interval_ms=10000`；自动截图默认关闭 |
| 归一化 / 页面合并 | [config.py](../tools/config.py#L678)、[config.py](../tools/config.py#L739) | `merge_ui()` 与 `normalize()` 都按会员态再钳；旧配置里的 5000/200 会被改成 10000 |
| 页面输入 | [index.html](../index.html#L432)、[app.js](../app.js#L1434-L1452) | 非会员 `disabled`、值 10000；`clampShotInterval()` 非会员直接返回 10000 |
| 启动器 | [DesktopShell.cs](../tools/host/src/DesktopShell.cs#L1029)、[DesktopShell.cs](../tools/host/src/DesktopShell.cs#L1065) | 仍按 200–60000 展示/写；落盘后 `normalize()` 再按会员态钳，非会员最终仍是 10000 |
| **执行侧** | [serve.py](../tools/serve.py#L1224) `settings()` | `member=config.is_member()`；非会员固定 10000；实际节流 `now-last < interval/1000`（[serve.py](../tools/serve.py#L1454)） |
| **定位侧** | [serve.py](../tools/serve.py#L915-L1019) `PositionTracker` | `_gate_open()`：非会员 10 秒；关门时**不扫描、不广播、不排队**；开门扫最新一张；战局开始 `force=True` 立即定位；截图目录不存在时不受节流 |
| 页面应用 | [app.js](../app.js#L7437-L7450) `applyPosition()` | 只负责把服务端推来的位置切楼层、跟随视角；**不承担会员判断** |
| 清理侧 | [serve.py](../tools/serve.py#L609-L711) `ShotManifest` / `RaidEndCleaner` | 只删**清单内**的自动图；手动截图不进清单、不自动删 |
| 默认开关 | [config.py](../tools/config.py#L165-L181) | 自动截图 `enabled=false`、战局结束清理 `cleanup_on_raid_end=false` |

**结论：R108 已把“非会员 10000ms + 定位 10 秒”落到本地客户端（页面 UI + 本地 Python 服务），不是停留在设想。** 但会员态只来自本地配置 `account.member`，**本质是客户端自报**：用户改一行配置或改前端代码即可绕过；ECS **看不到、也没有接口校验**。所以它是产品分层，不是安全边界。

#### 11.9.3 实现归属：谁能把这条门控做实

| 面 | 落地位置 | 现状/契约 | 边界 |
|---|---|---|---|
| 自动截图间隔 | 页面输入框 + `config.clamp_interval()` + `serve.settings()` | 双重钳制：页面禁用并显示 10000；配置归一化与执行侧再钳；会员才放行 200–60000 | 只能防“旧配置/脏值/误操作”，**不防手改** |
| 定位更新频率 | 本地 `serve.py` `PositionTracker` | 非会员 `_gate_open()` 每 10 秒放行一次；自动 + 手动合并；关门期间**不扫描/不广播/不排队**，开门直接取最新；战局开始强制放行 | 本地服务也是客户端进程，**不是 ECS 校验** |
| 会员源 | `config.is_member()` / 前端 `isMember()` | 当前读本地 `account.member`；接入云端后**只改这一数据源**（两个读取函数一起换成权益缓存） | ECS 不信任客户端上报的 member |
| 云端（ECS） | `/v1/entitlement` | 只返回 `features:["progress.sync","position.refresh"]` 与到期时间 | **不新增门控端点、不做间隔校验、不接收“我是会员”布尔值** |

**为什么定位门控放在本地 `serve.py` 而不是页面**：`PositionTracker` 是唯一知道“又出了一张新图”的地方；在它这里关门可以**连扫描和 SSE 广播一起省掉**，自动/手动天然合并，且所有消费者（主窗、`?mini=1`）口径一致。代价是它必须读一份“会员态”，而这份会员态只能来自本地配置或权益缓存——**仍然是客户端自报**。不要因为它写在 Python 里就误称“服务端校验”；对 ECS 而言，本机服务就是客户端。

**为什么这不是安全边界**：配置是明文 JSON、`app.js` 是明文、`serve.py` 可反编译；改 `account.member=true`、改 JS、或用外部连发工具都能绕过。门控只用于“正常用户的产品分层”，**不能写成防盗版承诺**；也不值得为它加混淆/反调试。

#### 11.9.4 真实付费吸引力：用移动速度算，而不是拍脑袋

**小地图现状**：视野半径五档 **25 / 50 / 100 / 200 / 300 米**，默认 **100 米**（[app.js](../app.js#L1425)、[app.js](../app.js#L454)）；地图以玩家为中心，所以“10 秒更新”表现为**周围世界与标记滞后**，不是玩家点跑偏。

**速度假设（粗略量级）**：步行 2–3 m/s；负重/战术移动 4–5 m/s；轻装冲刺 6–8 m/s；蹲行 1–1.5 m/s。10 秒对应位移约 20–80 米。

| 半径 | 10 秒位移占半径比例 | 观感 |
|---|---|---|
| 25m | 步行 0.8–1.2R；冲刺 2.4–3.2R | **明显受影响**：冲刺时玩家已跑出圆外，撤离点/门/物资标记全是旧的 |
| 50m | 步行 0.4–0.6R；冲刺 1.2–1.6R | **明显**：冲刺会跑出视野，交火前转点容易看错方向 |
| 100m（默认） | 步行 0.2–0.3R；冲刺 0.6–0.8R | **可感知但不致命**：还在圆内，但周边标记滞后半个屏幕；站桩交火时无影响 |
| 200m | 步行 0.1–0.15R；冲刺 0.3–0.4R | 轻微；主要影响楼层切换与撤离点判断 |
| 300m | 步行 0.07–0.1R；冲刺 0.2–0.27R | 基本可接受 |

**结论（不粉饰）**：

- 10 秒在**默认 100m** 档是“能感觉到的降速”，不是“不能玩”；在 **25/50m** 档（CQC、室内）是真实痛点；在 200/300m 档几乎无感。
- 交火时玩家基本静止，**10 秒限制对枪战无影响**；影响集中在转点、搜刮、上下楼（楼层切换也会最多晚 10 秒）。
- 付费买到的不是“新能力”，而是“**把被拉长的 5 秒/更快的 0.2 秒买回来**”。这是典型的**收回式卖点**，老用户容易产生“先降速再收费”的负面观感。
- 因此：**第二项能提高少数重度定位用户的年付转化，但不会带来新用户，也不构成涨价理由**。维持 **¥6/月、¥72/年**；年付默认推荐；限时 ¥60 仅作促销、需你确认。
- 受众还有一层折损：自动截图默认关闭（[config.py](../tools/config.py#L165-L172)），**不开自动截图的用户只受“定位 10 秒”这一面影响**，对“间隔可调”完全无感。两项相加的实际可感人群比想象中小。

#### 11.9.5 与 5000ms 基线对齐：磁盘、CPU、清理逻辑

以 45 分钟战局、截图按 1–2 MB/张估算（实际以用户分辨率与格式为准）：

| 档位 | 张数（45 分钟） | 占用（1–2 MB/张） | 说明 |
|---|---|---|---|
| 会员 200ms | 13,500 | **13.5–27 GB** | 极端档；必须提示磁盘风险，并建议同时开“战局结束清理” |
| 现状默认 5000ms（R108 之前的基线） | 540 | 0.54–1.08 GB | 老配置/老版本；R108 读取时会被钳到 10000 |
| **非会员 10000ms（R108 现状默认）** | **270** | **0.27–0.54 GB** | 自动截图量与磁盘写入**减半**；新装默认已 10000 |
| 60000ms（仅会员） | 45 | 45–90 MB | 最省 |

- **磁盘/IO**：非会员锁 10 秒后，自动截图张数、磁盘写入、游戏侧截图卡顿都减半；手动截图不受限，想补拍的用户反而可能让总量回升。
- **CPU**：`AutoShotter` 的轮询步长是 0.1 秒（[serve.py](../tools/serve.py#L1155)）不变，发键本身开销可忽略；`PositionTracker` 的 1 秒轮询仍在，但非会员**关门期间不扫目录、不广播**（R108），有效扫描最多 10 秒一次。真正的大头是游戏写截图，10 秒档反而降低了游戏侧压力。
- **到货校验变慢**：`_pending_grace = max(1.2, interval×0.8)`（[serve.py](../tools/serve.py#L1311)），5 秒档是 4 秒，10 秒档变成 **8 秒**；“发了没出图”的提示更晚，连续 2 次失败后切换注入方式约需 20 秒（5 秒档约 10 秒）。
- **清理逻辑（重点）**：`RaidEndCleaner` 只删 `ShotManifest` 清单内的文件，清单只记录“本工具发键后新出现”的图（[serve.py](../tools/serve.py#L1300-L1325)），**手动截图永远不进清单、永远不会被自动删**。10 秒档的影响是：
  1. 清单条目减半，战局结束清理更快、删得更少；
  2. **但手动截图不在清单里**，10 秒限速不会减少手动图的堆积；如果用户为了补定位频繁手按，磁盘占用可能不降反升；
  3. **到货判定窗口从 4 秒拉长到 8 秒**，窗口内恰好发生的手动截图可能被误判为“自动截图到货”并记入清单，之后在战局结束清理时被删——这与“手动截图永不删”的承诺冲突。窗口翻倍会放大该风险；**R108 已启用 10 秒锁，应尽快复核并修正这段归属逻辑**。
  4. 若用户根本不开自动截图，间隔锁不起作用，只剩“定位 10 秒”这一面。

#### 11.9.6 对订阅结论的影响

- 第二项**不增加服务端成本**（不经过 ECS），盈亏平衡仍是 **6–7 人（只算基础设施）/ 845 人（含人力）**。
- 它是“同一权益的两个面”，不要再按两项独立权益去讲故事；对外统一说“**位置刷新频率**”，内部实现拆成截图侧与定位侧。
- 结论从“明显撑不住”变为“**可以小规模试，但仍不足以当主营**”；定价维持 ¥6/月、¥72/年。
- 上线前提：**R108 本地门控已实现**；M1（权益接口）+ M2（把 `isMember()` 数据源换成云端权益缓存）完成后即可联动；**至少提前 30 天公告“R108 之前的默认 5 秒统一为免费 10 秒/会员可调”**（新装默认已是 10 秒，老配置读取即被钳到 10 秒），不要静默降速。

## 12. 交互与接口规格（按钮 / 时序 / 鉴权）

> 本轮只定契约，不写实现。以下文案、颜色为建议值，最终以 UI 稿为准。

### 12.1 口径对齐与按钮位置

- 云端只同步**任务进度 + 剧情进度**；**不上传**配装/配枪预设、截图、界面设置、`overlay.*`。
- 现有「保存配置」按钮若实际保存的是配装预设，需要**改名或拆分**：云端行为只挂在「保存进度」上，避免把预设误送进付费链路。若坚持共用，云端只挑 `tasks/stories` 字段，预设仍只写本地。
- 新增「同步配置」按钮放在「保存配置」**正下方**，同一按钮组，垂直间距 8px；窄屏同列堆叠、宽度 100%。
- 尺寸：高 32px、圆角 6px、字号 12px；主色 `#c8a45c`，文字 `#1b1d20`；禁用底色 `#2b2e33`、描边 `#3a3e45`、文字 `#7d838c`。

### 12.2 按钮五态矩阵

状态判定优先级：**网络不可用 > 未登录 > 会员已过期 > 会员有效 > 已登录非会员**（避免离线时误显示“会员”）。

| 状态 | 判定依据 | 「保存配置」 | 「同步配置」 |
|---|---|---|---|
| **S1 未登录** | 无 `cloud-session.json` / 令牌为空 | **启用**，文案「保存配置」；点击=只写本地，toast「已保存到本地（未登录，未同步）」 | **禁用**，文案「登录后可同步」；灰底、`cursor:not-allowed`、无 hover；点击无请求。右侧 12px 文字链「登录」打开登录弹窗 |
| **S2 已登录·非会员** | 权益缓存 `features` 不含 `progress.sync`，且未过期 | **启用**，文案「保存配置」；点击=只写本地，toast「已保存到本地（会员可自动同步）」 | **禁用**，文案「会员专属」；禁用样式同上；下方文字链「了解会员」打开价格页 |
| **S3 会员有效** | `plan=plus && expiresAt > now` | **启用**，文案「保存配置」；点击=本地保存 → 预检 → 上传，请求中变「保存中…」并禁用 | **启用**，主色实心，文案「立即同步」；请求中变「同步中…」+ 12px spinner，`aria-busy=true` |
| **S4 会员已过期** | `expiresAt <= now` | **启用**，文案「保存配置」；点击=只写本地，toast「会员已过期，仅保存到本地」 | **禁用**，文案「会员已过期」；下方文字链「续费」 |
| **S5 网络不可用** | BFF 熔断 / `navigator.onLine=false` / 最近一次连接超时 | **启用**，文案「保存配置」；点击=只写本地，toast「已保存到本地；网络恢复后自动同步」 | **禁用**，文案「离线，稍后自动同步」；`cursor:not-allowed`；恢复网络后 2 秒内自动切回 S3 |

**禁用态规范（统一）**：

- 背景 `#2b2e33`、1px 描边 `#3a3e45`、文字 `#7d838c`、整体 `opacity .65`。
- `cursor: not-allowed`；无 hover/active 变化；键盘 focus 只保留 2px `rgba(200,164,92,.35)` 外框。
- **禁用按钮不承载“点击后弹错误”**：避免用户反复点击与误以为已同步；解释放在按钮下方 11px 说明文字或文字链。

**加载态规范**：按钮宽度不变（预留 spinner 12px），`pointer-events:none`，文案替换，禁止重复提交。

### 12.3 校验时序（点击「保存配置」/「立即同步」）

```
点击
  │ ① 本地保存（localStorage，<10ms）——先保证不丢
  ▼
POST /api/cloud/progress/precheck  (BFF → ECS /v1/progress/precheck)
  │ 超时 3s，0 重试；401 先 refresh 一次
  ▼  canSync=true, plan, expiresAt, rev
POST /api/cloud/progress/sync       (BFF → ECS /v1/progress/sync)
  │ 超时 8s，网络/5xx 重试 2 次（1s、3s）；401 refresh 一次；409 拉取后重试一次
  ▼  200 {rev, accepted, conflicts, serverChanges}
应用到本地（先备份 lastgood → 写回 → 落盘）
  │
  ▼
回执：状态条「已同步 · rev N · HH:MM」，toast「已同步」
```

| 步 | 动作 | 请求 | 超时 | 重试 | 失败文案 / 行为 |
|---|---|---|---|---|---|
| ① | 本地保存 | 无 | — | — | 写失败（隐私模式/配额满）：toast「本地保存失败，请清理浏览器存储」；**不上传** |
| ② | 预检 | `POST /v1/progress/precheck` | 3s | 0（401 刷新后 1 次） | 401→「登录已过期，请重新登录」；403→「会员已过期或未开通」；5xx/超时→「会员状态暂时无法确认，本地已保存」，**停止上传** |
| ③ | 上传 | `POST /v1/progress/sync` | 8s | 2（仅网络/5xx） | 401→刷新重试一次；403→停止并提示续费；409→拉取最新→合并→重试一次；413→「进度数据过大」 |
| ④ | 应用 | 本地写回 | — | 0 | 写回失败→从 `lastgood` 回滚，提示「同步已取消，本地保持原状」 |
| ⑤ | 回执 | 无 | — | — | 成功 toast；冲突只更新状态条，不弹模态 |

**关键**：②预检只是 UI 层，**不是授权**；即使预检被绕过/伪造，③上传接口仍会独立校验（见 12.4）。

### 12.4 上传接口鉴权（不可绕过）

服务端伪代码：

```python
@app.post("/v1/progress/sync")
def progress_sync(req):
    uid = require_active_membership(req)      # 唯一授权入口
    body = read_json(req, max_bytes=256 * 1024)
    if len(body["changes"]) > 50: raise ApiError(413, "SYNC_BATCH_TOO_LARGE")
    with db.transaction("IMMEDIATE"):
        merged, conflicts = merge_entities(uid, body)
        rev = bump_rev(uid)
    return {"ok": True, "data": {"rev": rev, "conflicts": conflicts, "serverChanges": merged}}

def require_active_membership(req):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): raise ApiError(401, "AUTH_REQUIRED")
    claims = verify_jwt(auth[7:])                  # 校验签名、exp、aud；失败 401
    if req.headers.get("X-Device-Id") != claims.device: raise ApiError(401, "DEVICE_MISMATCH")
    dev = db.device(claims.device)
    if not dev or dev.revoked_at: raise ApiError(401, "DEVICE_REVOKED")
    sub = db.subscription(claims.uid)              # 每次写请求都读库，不用 JWT 里的 plan
    if not sub or sub.status != "active" or sub.expires_at <= now():
        raise ApiError(403, "MEMBERSHIP_REQUIRED")
    if db.active_devices(claims.uid) > sub.device_limit:
        raise ApiError(403, "DEVICE_LIMIT")
    if rate_exceeded(claims.uid): raise ApiError(429, "RATE_LIMITED")
    return claims.uid
```

**防绕过要点**：

1. JWT 只证明“你是谁/哪台设备”，**不把 `plan` 或 `features` 当作长期授权**；写路径每次查 `subscriptions`。
2. 服务端**不信任** `X-Plan`、`X-Is-Member`、请求体里的 `uid/plan`；账号只能来自 token。
3. 预检与上传共用 `require_active_membership` 的只读版本；预检结果不缓存为授权。
4. `X-Device-Id` 必须与 token 绑定；换设备要重新 refresh。
5. 支付回调延长 `expires_at` 后，下一次上传立即生效；退款/封禁立即 403。
6. 时钟偏差容忍 60 秒；token `aud` 固定为云服务标识，防止本机其他服务复用。

**401 / 403 / 409 分工**：

| 码 | 含义 | 客户端动作 | 是否重试 |
|---|---|---|---|
| **401** | 无令牌、令牌过期/签名错、设备被吊销、设备不匹配 | 先 refresh 一次；仍失败→退出登录态、保留本地 | 仅 refresh 后 1 次 |
| **403** | 身份有效但**无有效订阅**、已过期、设备数超限、被封禁 | 停止上传，显示续费/设备管理；**本地照常保存** | **不重试** |
| **409** | `REV_CONFLICT`（`baseRev` 落后）/ 客户端版本与云端分叉 | 先 `GET /v1/progress?sinceRev=` 拉最新，合并后再上传 | 1 次 |
| **413** | 单批 >50 实体 / 全量 >256 KB | 改发全量快照或分批 | 不重试 |
| **429** | 配额/频率超限 | 读 `Retry-After`，退避 | 按响应头 |

### 12.5 自动同步触发时机

| 触发 | 延迟/去抖 | 节流 | 行为 |
|---|---|---|---|
| 登录成功 | 0（立即） | 单次 | 先 `GET /v1/progress?sinceRev=` 拉取；有云端变更先提示「恢复/保留本地」；再上传本地 `pending` |
| 进度变更（`gw:progress-changed`） | **3s 去抖** | 每设备**最小 10s** 一次 | 合并多次变更为一个 diff；>50 实体拆批；无变化不发请求 |
| 应用启动 | JS ready 后 **5s + 0–2s 抖动** | 单次 | 只拉取，不自动覆盖；发现云端更新则提示 |
| 定时心跳 | 每 **5 分钟** | 仅 `pending>0` 时发 | 无待同步则**完全不发请求**，省流量 |
| 网络恢复 | 立即 | 指数退避 1s/3s/9s，最多 3 次 | 重放 `pending`，按 `updatedAt` 排序 |
| 页面隐藏/关闭 | 立即 | 最多 1 次 | `fetch(keepalive)` 尽力发送；不等待结果、不重试 |

手动点击「保存配置/立即同步」**绕过 3s 去抖**，但仍受「10s 内且无变更则提示已是最新」约束，避免连点。

### 12.6 去掉导入/导出后的数据处理（产品风险，已决定执行）

**接口处理**：

- 移除 UI 上的「导出进度 / 导入进度」入口；`GW.Tasks.exportProgress/importProgress` 不再作为公开 UI 能力。
- `importProgress` 保留为**内部函数**，仅供云端 `serverChanges` 写回使用；不暴露菜单。
- `GET /v1/progress/export` 仅对有效会员开放，作为客服/换机救援接口，**不做常规按钮**。

**存量数据**：

- 老用户本地 `localStorage` 进度**原样保留**；首次登录成为会员后，全量上传一次即可。
- 已经导出到磁盘的 JSON 文件：**没有 UI 导入入口后无法通过界面恢复**；只能手动改 `localStorage`（不提供支持）。这是本次决策的直接代价。
- **不做一次性迁移入口**（按你的决定）。若后续改变，最小代价方案是保留 1–2 个版本的「仅导入、不导出」隐藏入口。

**⚠ 产品风险（仅提示，不擅自保留功能）**：

1. **非会员完全失去备份能力**：清理浏览器数据、重装、换机即永久丢失，且无导出自救。
2. 预计客服/差评上升：「我点了保存为什么还是丢了」「换电脑全没了」。
3. 与「免费版功能不减少」的原有承诺冲突，需要在发布说明中明确告知，否则老用户会觉得被剥夺。
4. 数据可携带性下降；用户可能转向仍提供导出的竞品工具。
5. 退款争议：用户可能以「付费前不知道不能导出」为由要求退款；用户协议需显著提示。

### 12.7 降级与 UI 表达

| 场景 | 状态条 | 颜色/图标 | 用户可做什么 |
|---|---|---|---|
| 未登录 | 「仅本地 · 未登录」 | 灰点 | 登录 |
| 会员已同步 | 「已同步 · rev N · HH:MM」 | 绿点 | 无 |
| 有待上传 | 「本地已保存 · 待同步 N 项」 | 琥珀点 | 立即同步 |
| 离线 | 「本地已保存 · 云端未同步（离线）」 | 琥珀点 | 恢复网络后自动 |
| 服务端 5xx | 「云端暂不可用 · 本地已保存」 | 琥珀点 | 重试 |
| 会员过期 | 「会员已过期 · 仅本地」 | 灰点 | 续费 |
| 有冲突 | 「已同步 · N 条冲突」 | 蓝点 | 查看冲突 |

**硬规则**：

- 本地保存**永远先行**，且不依赖网络；云端失败不得回滚本地已保存内容。
- 不用模态框打断游戏；toast 最多 5 分钟一条；错误只进状态条。
- 证书校验失败时**停止同步**并提示「无法验证服务器身份」，绝不降级为不校验。
- 到期/封禁/设备超限都只影响云端同步，**地图/任务/剧情/小窗完全不变**。

### 12.8 错误文案对照

| 错误码 | 用户文案 |
|---|---|
| `AUTH_REQUIRED` / `AUTH_INVALID` | 登录已过期，请重新登录 |
| `MEMBERSHIP_REQUIRED` | 会员已过期或未开通，本地进度不受影响 |
| `DEVICE_LIMIT` | 设备数已达上限，请先在管理页移除旧设备 |
| `RATE_LIMITED` | 同步过于频繁，请稍后再试 |
| `SYNC_BATCH_TOO_LARGE` / `PAYLOAD_TOO_LARGE` | 进度数据过大，已改为分批上传 |
| `REV_CONFLICT` | 云端有新版本，已自动合并，请检查冲突项 |
| 网络不可用 | 网络不可用，本地已保存 |
| 5xx / 超时 | 云端暂不可用，本地已保存 |
| TLS 校验失败 | 无法验证服务器身份，已停止同步（本地不受影响） |

---

### 12.9 位置刷新频率的门控交互（截图侧 + 定位侧）

**控件**：现有 `#mini-shot-interval` 数字输入（[index.html](../index.html#L432)）；定位侧没有独立控件，只在设置区显示提示。

> 说明：R108 已实现“本地 `account.member` 判定 + 非会员 10000ms + 定位 10 秒”。下表的“未登录/会员有效/已过期”是**接入云端权益后的目标状态**；未接云时只有 `account.member` 一个开关（手改即可切换，属已知绕过）。

#### 12.9.1 截图间隔输入框

| 状态 | 输入框 | 文案与样式 | 点击/输入行为 |
|---|---|---|---|
| 未登录 | **禁用** | 值固定显示 **10000**；helper「免费档固定 10 秒/张；登录并开通会员可调 200–60000ms」 | `disabled` + `aria-disabled`；底色 `#2b2e33`、描边 `#3a3e45`、文字 `#7d838c`、`cursor:not-allowed`；点击无反应，helper 文字链打开登录 |
| 已登录·非会员 | **禁用** | 值固定 10000；helper「免费档固定 10 秒/张；会员可调 200–60000ms」 | 禁用；helper 文字链「了解会员」打开价格页 |
| 会员有效 | **启用** | 可编辑范围 200–60000；helper「会员可调 200–60000ms」 | 输入即时校验；失焦/回车钳制后写配置；**不发云端请求** |
| 会员已过期 | **禁用** | 值回落 **10000**；helper「会员已过期，已恢复免费档 10 秒/张」 | 禁用；「续费」文字链 |
| 网络不可用 | **按缓存权益** | 缓存为会员→启用；从未登录/缓存过期→禁用并显示 10000 | 间隔是本地配置，**断网不影响编辑与保存**；不触发云端请求 |

**禁用态细节（与 §12.2 统一）**：`disabled` 属性 + `aria-disabled="true"`；背景 `#2b2e33`、描边 `#3a3e45`、文字 `#7d838c`、`opacity .65`、`cursor:not-allowed`；无 hover/active；保留键盘 focus 外框。

**校验文案**：

- 会员：`允许 200–60000 毫秒`（沿用现有）。
- 非会员：`免费档固定 10000 毫秒，不可调；会员可调 200–60000 毫秒`。

**提交与保存**：

1. 会员改值 → 本地校验 → 失焦/回车 → `clampShotInterval(200, 60000)` → 写配置（`queuePrefs`）。
2. 非会员没有输入入口；**启动、登录、权益刷新、会员到期**四个时机都把 `auto_screenshot.interval_ms` **强制写回 10000**（幂等，值已是 10000 就不写）。
3. **不调用 `/v1/progress/precheck` 或任何云端接口**；间隔是本地配置，与进度同步无关。
4. 若会员在编辑期间到期：下一次保存前把值写回 10000，toast「会员已过期，截图间隔已恢复为免费档 10 秒/张；本地已保存」。
5. 启动时：读本地配置 → 按权益缓存钳制 → 渲染禁用/启用态；**不阻塞页面启动**。

#### 12.9.2 定位更新的 10 秒闸门（R108 已在本地服务实现）

- **闸门位置**：本地 [serve.py](../tools/serve.py#L1016-L1019) `PositionTracker.poll_once()`，不是页面。非会员 `_gate_open()` 未到 10 秒时直接返回：**不扫描目录、不广播、不排队**；解禁后的第一次轮询直接取目录里**最新的一张**，中间截图不会丢，只是延后生效。
- **自动 + 手动合并**：`PositionTracker` 只认“目录里出现了新图”，不区分自动发键还是用户手按，因此两个来源天然合并计时。
- **战局开始强制放行**：进战局时 `request_immediate_poll()` 置 `_force_pending`，下一次轮询 `force=True` 绕过节流，立即定位一次（[serve.py](../tools/serve.py#L989-L1000)）。
- **可用性帧的边界**：截图目录**不存在**时不受节流影响，立刻清坐标并通知页面（[serve.py](../tools/serve.py#L1004-L1014)）；“目录存在但还没图/解析失败”的 reason 更新仍在闸门之后，最多晚 10 秒。
- **会员**：`member=True` 时 `_gate_open()` 恒真，每张新图都跟随。
- **`?mini=1`**：闸门在 SSE 上游，主窗与小窗自动一致；小窗首帧直接显示当前位置，之后按 10 秒节奏。
- **自动截图关闭时**：间隔锁不生效，但定位闸门仍对“手动截图”生效——这正是“同一权益两个面”的体现。
- **页面侧**：`applyPosition()`（[app.js](../app.js#L7437-L7450)）**不再做二次节流**，否则会变成“10 秒 + 页面延迟”的双重等待。

**定位状态提示（现状与建议）**：

- R108 现状：输入框容器已有 CSS 提示 `非会员固定 10 秒截图间隔 · 会员可调间隔`；**定位侧没有单独提示**。
- 建议把提示合并为一句：`非会员：截图 10 秒/张、定位 10 秒/次；会员不限`（改 CSS 文案即可，不改 DOM）。
- 手动按了截图但落在 10 秒窗口内：**不弹 toast、不显示红色错误**；用户下一条截图自然会生效。若担心困惑，可在设置项 helper 中说明“定位最多 10 秒更新一次”，不做小地图倒计时。

**不要做的交互**：

- 不拦截/吞掉用户的截图按键，也不阻止截图文件落盘——那会破坏“截图功能本身免费”的承诺。
- 不在定位被限速时显示“同步失败/错误”类文案；这不是错误，是免费档策略。

#### 12.9.3 服务端与本地执行层的边界

- `tools/config.py` 的 `normalize()/merge_ui()/clamp_interval()` **按会员态钳制**（非会员固定 10000），但会员态来自 `config.is_member()` 读取的本地 `account.member`，**仍是客户端自报**。
- 本地 `serve.py` 的 `settings()` 与 `PositionTracker` 也读同一份本地会员态；它们属于**客户端进程**，不是 ECS。不要把它描述成“服务端校验”。
- **不要新增“校验会员间隔”的云端端点**：ECS 不接收间隔值、不判断真假，避免制造“服务端在管”的错觉；云端只通过 `/v1/entitlement` 提供 `position.refresh` 标志。
- 接入云端后，**只改 `isMember()` / `config.is_member()` 的数据源**（换成权益缓存），`clamp_interval` 与 `PositionTracker` 的 10 秒逻辑不改。
- 已知绕过（接受，不做对抗）：手改 `%APPDATA%\EFTMap\eftmap.config.json` 的 `account.member=true`、改 `app.js`、或外部连发工具；启动器输入框若不做同样禁用，也是一条捷径。**这些都属于本地可绕过的产品门控，不是防盗版。**

---

## 13. 分阶段落地（进度同步 + 位置刷新门控）

工作量单位：**人日**（含开发 + 自测 + 文档，不含法务等待与外部审批）。依赖按顺序满足；总工作量 **16–26 人日**（新增的位置刷新门控约 1 人日）。

### M0 前置（阻塞项，1–3 人日 + 外部等待）

| 项 | 内容 |
|---|---|
| 交付物 | 许可边界评估记录（付费链路零素材 + 本地功能解锁说明）；README 改稿；ECS 安全组仅放行 8443；自签 CA 与 `server.pem`（含 `IP:47.96.68.209`）；支付主体与通道结论；DB/备份目录规划 |
| 依赖 | 上游作者书面答复（周期不可控，非阻塞）；阿里云工单确认非标端口；支付渠道资质 |
| 验收 | 公网 `curl -k https://47.96.68.209:8443/v1/status` 返回 200；客户端用 `cloud-ca.pem` 校验通过；`sqlite3 .backup` 恢复演练成功 |
| 阻塞说明 | 许可边界未记录、README 未改稿前不对外收费；可先做 M1/M2 的内测（免费），但不可挂价格 |

### M1 ECS 控制面 + 进度服务（6–9 人日）

| 项 | 内容 |
|---|---|
| 交付物 | Caddy（TLS + 限流 + 路由）；Python 控制面（单进程 + SQLite WAL）；表 `users/devices/refresh_tokens/subscriptions/payment_events/audit_log/progress_entities/progress_revs/progress_versions/progress_conflicts`；端点 `/v1/auth/*`、`/v1/entitlement`、`/v1/progress`、`/v1/progress/sync`、`/v1/progress/export`、`/v1/status`、`/v1/updates/manifest`、`/v1/pay/notify/{channel}`；CDK/手动授予脚本；每日备份到 OSS |
| 依赖 | M0 的证书与端口；SQLite 文件权限；`edge.env` 密钥 |
| 验收 | ① 设备 1/2 登录，设备 3 触发 `DEVICE_LIMIT`；② access 过期自动 refresh，旧 refresh 复用被拒并吊销；③ 手动授予后 `/v1/entitlement` 立即返回 `progress.sync` + `position.refresh`；④ 两台设备分别修改不同任务后 `/v1/progress/sync` 合并成功；⑤ 已完成任务不被降级为进行中；⑥ 单用户全量 < 200 KB、单次 sync < 10 KB；⑦ 备份可在另一台机器恢复并读出同一 `rev` |
| 资源 | 常驻内存：Caddy 30–60 MB + 控制面 60–120 MB + SQLite <20 MB；3 Mbps 下进度同步占比 < 1% |

### M2 客户端同步引擎、恢复与位置刷新门控（6–9 人日）

| 项 | 内容 |
|---|---|
| 交付物 | `tasks.js`：`saveProgress/saveStoryProgress` 后派发 `gw:progress-changed`；新增 `GW.Tasks.applyStoryProgress(doc)`；`js/cloud-progress.js`（差异、队列、重放、合并应用）；`tools/cloud.py` BFF 四个进度端点；`cloud.*` 配置键与归一化；同步状态条、冲突面板、首次恢复向导、导出/回滚入口；**复用 R108 的本地门控**：只把前端 `isMember()` / `config.is_member()` 的数据源换成云端权益缓存（或同步后的 `account.member`），截图输入框禁用/10000、`clamp_interval`、`PositionTracker` 10 秒逻辑不改 |
| 依赖 | M1 的端点与令牌；包内 CA；`eftmap.cloud.sync.v1` 约定 |
| 验收 | ① 503 任务 + 266 剧情步骤全量上传 < 5 秒；② 断网 3 天后重放不丢、不乱序；③ 同一设备连续修改只发最后状态；④ 双设备并发修改同一任务按 §11.3.4 收敛为 `completed`；⑤ 剧情 A 设备完成第 1 步、B 设备完成第 2 步可合并；⑥ `127.0.0.1:8787` 与 `localhost:8787` 进度不串；⑦ `?mini=1`、断网、删除令牌、服务端 503、证书错误五种场景本地功能零回归；⑧ 会员切换后输入框启用/禁用正确，非会员落盘 10000、会员可存 200/60000、退出登录回落 10000；⑨ 非会员自动 + 手动截图 10 秒内只定位一次，解禁取最新图，战局开始强制放行一次；⑩ 截图目录不存在时立即清坐标，会员不受闸门影响，`?mini=1` 与主窗口径一致 |
| 风险 | 浏览器 `localStorage` 无法由 Python 读写；所有同步逻辑必须在页面 JS，BFF 只转发；位置闸门只能做产品分层，**本地可绕过** |

### M3 灰度、收费准备与承诺落地（3–5 人日）

| 项 | 内容 |
|---|---|
| 交付物 | 10–20 人内测；同步成功率与失败原因看板（只记 `userId/bytes/rev/conflicts`，不记 payload）；到期前 7 天提醒；退款/顺延脚本；用户协议与隐私说明（§11.7 措辞）；客服 FAQ；价格页（月 ¥6 / 年 ¥72，可选限时 ¥60）；**“R108 之前的默认 5 秒统一为免费 10 秒、定位 10 秒/次”的 30 天公告与更新说明**（R108 已实现锁，正式发版前必须完成公告；若已发版则补发公告并说明回滚方式） |
| 依赖 | M1/M2 稳定运行 ≥2 周；许可边界已按 §14.1 落地（付费链路零素材 + README 改稿）；支付通道可用 |
| 验收 | ① 内测两周同步成功率 > 99%；② 无本地功能回归报告；③ 退款/顺延流程各演练一次；④ 30 天价格调整/降速公告与到期提醒可触发；⑤ 服务端连续 72 小时不可用的顺延脚本可执行；⑥ 公告可查且发版说明写明 10 秒锁；未完成公告不得继续扩大灰度 |
| 收费门槛 | 许可边界记录 + 支付通道 + 内测稳定性，三者缺一不可 |

### 未来里程碑（本轮不做）

- **M4 实时行情**：需先证明「历史/双模式」有付费意愿，且上游条款允许；工作量 5–8 人日。
- **M5 云预设同步**：与进度同步同质，单独卖理由弱；建议并入“云同步包”时再做。
- **M6 公开构筑库**：需要审核人力与冷启动内容，且浏览不能收费；优先级最低。
- 触发条件统一为：**许可允许商用 + 出现第二项持续价值 + 付费用户 ≥ 300**。

---

## 14. 风险与代价

### 14.1 许可与「项目自身承诺」：按「为存储服务收费」重估

**用户立场**：收费收的是「云端存储任务/剧情进度」这项服务，与地图素材无关。下面检验两个前提，而不是直接附和。

| 前提 | 是否成立 | 说明 |
|---|---|---|
| 1. 付费只经手用户自己产生的数据（进度），不转售、不设门槛分发上游素材 | **工程上可成立，叙事上需刻意维持** | 云端的唯一读写对象是 `tasks/stories` 进度 JSON；不缓存、不代理、不分发底图/图标/任务文本。但若客户端把地图作为付费页背景、或宣传图使用上游截图，就会被拉回“素材商业化”。 |
| 2. 软件与素材继续免费、不因未付费而受限 | **已部分不成立** | 进度云备份是服务，符合前提；但**位置刷新频率（截图间隔 + 定位）是纯本地门控**，付费解锁直接构成“软件功能墙”。因此“全部本地功能免费”的叙事必须改为“基础功能免费，两项增强付费”，否则 README 与产品自相矛盾。 |

**结论**：

- CC BY-NC-SA 的 NC 限制针对**素材本身的商业使用**，不是禁止作者以外的人经营任何业务。付费服务若不复制、不展示、不再分发素材，也不以素材为卖点，风险**从“明显冲突”降为“可接受但有解释空间”**。
- **第二个付费点改变了风险性质**：从“纯服务收费”变成“本地功能门控”。它**不提高素材许可风险**（截图/定位不使用任何上游素材），但**提高项目承诺风险**——README 旧文案明确承诺“永久免费、不设付费版”，必须同步改，否则就是对老用户的违约。
- **但不能说“零风险”**：整体产品收费仍可能被理解为“借助该作品获利”；最稳的做法是“付费链路完全不触碰上游素材”（见下）。
- 任务/剧情**文本本身也有上游版权**（来自 tarkov.dev/wiki/社区整理）。收费叙事只能写「存储你自己产生的进度数据」和「位置刷新更快」，**绝不能写「付费解锁任务攻略/剧情内容」**，也不能用任务文本截图做付费宣传。
- 建议仍发一封书面询问给底图作者/上游，保留答复；拿不到也不影响先做“只存进度”的内测，但正式收费前应记录风险评估。

**「付费链路完全不触碰上游素材」的落地清单：**

1. 付费页/收银台不出现任何地图截图、任务文本、物品图标；只用纯色/自绘几何背景。
2. 云端只存 `{datasetId, mode, entityId, status, objectives, steps, choices, updatedAt}`，不存名称、描述、图标 URL。
3. 服务端日志/备份/导出不含素材内容；`/v1/progress/export` 只回用户进度。
4. 客户端付费墙只拦「云同步」与「截图间隔/定位刷新」策略，不拦地图/任务/剧情浏览；未付费仍可看全部内容、仍可截图（只是频率受限）。
5. 营销文案统一用「云存储 + 本地增强」，禁止「会员解锁地图/攻略」类表述。
6. 关于页注明：与 Battlestate Games、tarkov.dev 无隶属关系；素材版权归原作者，按原许可证免费提供。

**README 建议文案（替换现有「永久免费/严禁售卖/不设付费版」段）：**

```markdown
## 免费与付费说明

本软件的**基础功能永久免费**：地图、任务树、剧情树、配装、小地图、自动截图（免费档 10 秒/张）、
离线行情等不设门槛；不卖激活码，也不提供「付费优先支持」。若有人向你售卖软件本体，说明你被骗了。

目前有两项可选的付费增强（¥6/月 或 ¥72/年）：

1. **云端进度备份**：把你自己的任务/剧情进度存到服务器，换机或重装后恢复；
2. **位置刷新更快**：免费档自动截图固定 10 秒/张（不可调），定位每 10 秒更新一次（自动与手动合并计时）；
   会员可把截图间隔调到 200–60000 毫秒，定位随新截图即时跟随。

费用仅用于覆盖服务器与开发维护成本，**不涉及任何地图、图标、文本素材的销售或授权**；
不购买也不影响地图、任务、剧情等内容的访问。

本项目与 Battlestate Games、tarkov.dev 无隶属或合作关系；上游素材版权归原作者，
按其原许可证免费提供。
```

同时把原句「本软件永久免费，也不靠它赚钱」改为「**基础功能永久免费；仅可选的云端进度备份与位置刷新增强收取覆盖服务器/开发成本的费用**」。

**可行路径（按代价排序）：**

1. **只对「存储服务」收费**（当前方案）：付费链路零素材，风险可控但不为零。
2. **取得书面授权**：把许可改为允许商用，风险归零；周期不可控。
3. **替换非商业素材**：底图自绘/改用可商用底图，图标自绘或用户导入；工程量大。
4. **维持免费 + 自愿赞助**：不做权益售卖，商业模型重做。

**结论：可以按「只存进度」推进内测与开发；正式收费前建议拿到书面答复或完成素材替换。** 这是本方案唯一的「硬阻塞」，但已从“绝对不可”降为“需控制边界”。

### 14.2 账号安全

| 风险 | 影响 | 缓解 |
|---|---|---|
| 撞库/暴力破解 | 账号被盗、会员被共享 | scrypt + 统一错误 + IP/账号双限流 + 失败 5 次锁 15 分钟 + 可选邮箱验证 |
| 令牌泄露（本机文件/日志/抓包） | 会话被冒用 | access 15 分钟、refresh 旋转 + 复用检测、令牌文件 0600、日志不记 token、TLS pinning |
| 盗号/找回 | 云端进度备份丢失或泄露 | 设备列表 + 主动踢下线 + 邮箱验证；敏感操作二次确认；操作审计 |
| 内部/管理端泄露 | 批量数据外泄 | 管理端只经 ZT、独立账号、操作审计、最小权限 |

### 14.3 支付合规

- 个人直连微信/支付宝通常不可行（需营业执照等资质，待核实）；无资质时走爱发电/CDK，或注册个体工商户。
- 订阅自动续费涉及《电子商务法》《消费者权益保护法》与支付渠道规则；自动续费必须显著告知、可随时取消（具体条款待核实）。
- 退款、发票、税务都要预先设计，别等用户找上门。

### 14.4 UGC 内容审核（未来公开库，本轮不做）

> 本轮没有公开构筑库、没有评论/图片上传，**审核面为零**。以下保留作为未来上线前的风险预案。

- UGC 风险：辱骂、外挂/作弊宣传、政治敏感、侵权构筑（转载他人内容）、诈骗链接。
- 首版**不做图片上传、不做评论、不做私信**，只允许标题/描述/构筑数据，显著降低审核面。
- 必须有的机制：举报、关键词过滤、发布先审或先发后审（建议新账号先审）、下架/封禁、申诉入口、审核日志。
- 人力：按每天 10–50 条发布估算，前期每天 15–30 分钟可覆盖；增长后需要规则化与自动过滤。

### 14.5 DDoS 与带宽耗尽（按“仅进度同步”重估）

- 本轮响应体极小（单次 < 10 KB），**几乎不会打满 3 Mbps**；攻击主要消耗连接数、TLS 握手与 Python CPU。
- 真正的风险是 **Caddy/Python 被连接洪水拖垮**，导致正常用户无法登录/同步。
- 阿里云基础防护可能触发黑洞（整 IP 不可达）；高防 IP 成本高（价格待核实）；没有域名也不能用 CDN/WAF 常规方案。
- 缓解：Caddy 每 IP 连接数/速率限制、应用层按 IP+账号双桶、登录后才可访问进度端点、超时快速失败、监控告警、必要时临时只保留 `/v1/status` 与登录。
- **不要**在被打时无限排队；宁可返回 503 + 客户端降级（本地进度照常），也不要拖垮数据库。

### 14.6 「被破解后损失多大」的现实评估（两项权益）

- 二进制破解：客户端是 Python/JS，必然可解包；破解版只能改「云同步」按钮的显隐，**拿不到服务端数据、也拿不到别人的进度** → 直接损失接近 0。
- **位置刷新门控被绕过 = 预期内**：改本地配置或 `app.js` 就能恢复 200ms/不限定位；这不会泄露任何服务端资产，只是少一个转化点。**不要为它加混淆/反调试**，投入产出比极低。
- 账号共享：唯一实质漏损，估 5–15%；用 3 台设备上限、refresh 绑定、200 次/天配额控制，不建议重型 DRM。
- 服务端被入侵：损失是账号 + 进度数据 + 支付密钥；对策是最小化数据、隔离管理端、密钥不入库、每日备份与恢复演练。
- **结论**：防护投入应集中在账号安全（令牌、限流、审计），而不是客户端混淆/反调试——投入产出比极低。

### 14.7 单点与在线率（按“付费链路全在 ECS”重算）

- **本机停电/断网/休眠不再影响付费用户**：登录、权益、进度同步全部在 ECS；本机只影响运维与未来数据面。
- 剩余单点：**ECS 单机**（阿里云宿主机故障、SQLite 文件损坏、误删、证书过期）。按阿里云可用性，月度中断通常在分钟级（具体 SLA 待核实）。
- 缓解：每日 `.backup` + OSS 异地备份 + 每季度恢复演练；systemd `Restart=always`；证书到期前 90 天告警；`progress_versions` 保留 3 版可回滚。
- 付费承诺按「尽力而为 + 72 小时顺延 + 15 天按比例退款」处理（§11.7），不承诺 99.9%。
- 若未来行情/预设回到本机数据面，则恢复「家庭宽带单点」风险：月度停机估 1–5 小时（待实测），需单独设计只读降级。

### 14.8 隐私与数据合规

- 只收集：邮箱、设备 ID/名称、登录 IP（安全用途）、**任务/剧情进度的实体 ID、状态与时间戳**、必要的支付订单号。
- **不上传**：截图、日志文件、磁盘路径、游戏进程信息、位置坐标、游戏内角色名。
- 进度数据可推断游玩进度与活跃时间，敏感度中低；传输 TLS + pinning，DB 文件 600，日志不打印 payload。
- 隐私政策需说明收集范围、用途、保留期限、删除方式；个人信息保护法与未成年人保护适用需法律意见（待核实）。

### 14.9 上游依赖（本轮无）

- 本轮云端**不抓取任何上游**，`json.tarkov.dev` 停服只影响本地可选行情（现有行为不变）。
- 未来若做云端行情：必须保留「失败不覆盖旧快照 + stale 标记」，并确认上游条款允许商业化使用（待核实）。

---

## 15. 待确认清单（按影响排序）

| # | 待确认项 | 影响 | 当前处理 |
|---|---|---|---|
| 1 | 底图/图标 **CC BY-NC-SA 非商业**；README 旧承诺与新订阅冲突 | 决定收费的**解释空间**（已从“绝对不可”降为“可接受但需控制边界”） | 按 §14.1 做“付费链路零素材” + 改 README；正式收费前尽量拿书面答复 |
| 2 | 阿里云对「未备案 IP + 非标端口」的当前策略 | 是否会被拦截/清退 | 开工单确认；准备 9443 备用端口 |
| 3 | ~~ECS 续费实际价格~~ **已确认 ¥100/年（≈¥8.3/月）** | 成本测算已按此重算 | 到期 2027-02-05 前复核新账单 |
| 4 | 支付主体（个人/个体户/企业）与渠道（微信/支付宝/爱发电） | 能否规模化收款、费率与合规 | 先 CDK/爱发电内测；费率与回调能力待核实 |
| 5 | 用户网络对非标端口的封锁比例（企业网/校园网/运营商） | 是否有用户完全连不上 | 内测收集失败样本；客户端可配 9443 |
| 6 | ¥6/月、¥72/年 的真实接受度（含免费版无导出、5 秒→10 秒降速后的转化） | 定价与转化 | 10–20 人内测 + 问卷；可测“限时 ¥60 年付”意愿；重点观察小半径地图用户 |
| 7 | 单用户真实进度体积与同步频次 | 容量与配额 | 内测埋点（只记 bytes/rev，不记 payload） |
| 8 | 客服/退款处理人力 | 能否持续运营 | 先 FAQ + 自助；退款脚本化 |
| 9 | OSS 具体单价与免费额度 | 大文件分发成本 | 控制台下单页复核（0.50/0.25 为当前抓取值） |
| 10 | 证书轮换与老客户端发版节奏 | 避免老客户端被锁死 | 双证书并行 + 提前 6 个月发版 |
| 11 | 10 秒档的到货宽限变成 8 秒，窗口内手动截图可能被误记入清理清单 | “手动截图永不自动删”的承诺 | R108 已启用 10 秒锁，须复核并修正 `_arm_arrival` 归属逻辑（按时间戳/文件名区分自动与手动） |

---

## 附录 A：ECS systemd 与备份草案

`/etc/systemd/system/eftmap-edge.service`：

```ini
[Unit]
Description=EFTMap control plane
After=network.target

[Service]
Type=simple
User=eftmap
WorkingDirectory=/opt/eftmap-edge/bin
EnvironmentFile=/opt/eftmap-edge/etc/edge.env
ExecStart=/opt/eftmap-edge/bin/venv/bin/python -m edge.app
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/eftmap-edge/data /opt/eftmap-edge/logs

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/eftmap-backup.service` + `.timer`（每日 03:10）：

```bash
#!/bin/sh
set -eu
cd /opt/eftmap-edge/data
sqlite3 edge.db ".backup '/opt/eftmap-edge/backup/edge-$(date +%F).db'"
sha256sum "/opt/eftmap-edge/backup/edge-$(date +%F).db" > "/opt/eftmap-edge/backup/edge-$(date +%F).sha256"
find /opt/eftmap-edge/backup -name 'edge-*.db' -mtime +30 -delete
```

证书生成（离线机器执行，私钥不上传 Git）：

```bash
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
  -keyout ca.key -out ca.pem -subj "/CN=EFTMap Cloud CA"
openssl req -newkey rsa:2048 -sha256 -nodes -keyout server.key -out server.csr \
  -subj "/CN=47.96.68.209"
cat > san.cnf <<'EOF'
subjectAltName = IP:47.96.68.209
extendedKeyUsage = serverAuth
EOF
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -days 1095 -sha256 -extfile san.cnf -out server.pem
```

## 附录 B：上线前验证清单

1. **离线零影响**：断网启动、删令牌、`cloud.enabled=false`、服务端 503、错误证书，五种场景现有功能与 SSE 全通过。
2. **网络**：公网 `curl --cacert cloud-ca.pem https://47.96.68.209:8443/v1/status` 200；80/443 不可达；22 仅管理 IP。
3. **ZT（可选）**：ECS → `10.147.20.10:8788/healthz` 200（仅未来数据面需要）；本轮不验。
4. **鉴权**：token 过期自动刷新；refresh 复用被吊销；第三台设备被拒。
5. **进度同步**：两台设备并发修改同一任务 → 收敛为 `completed`；断网 3 天重放不丢；100 并发 sync P95 < 1 秒。
6. **更新**：OSS 下载 150 MB、SHA-256 一致、篡改后拒绝、回滚可用。
7. **备份**：从每日备份恢复 `edge.db` 后能登录、能读到权益与进度 `rev`。
8. **降级**：服务端 503 时客户端仍可保存/导出进度，UI 明确提示“云同步暂停，本地进度已保存”。

---

*本方案为设计稿，不含任何源码改动；所有外部价格/政策以标注日期与出处为准，落地前需再次核实。*

