# 数据来源审计（R20 第一阶段 3.3 + 第三阶段 5.x 前置）

> 目标：回答三个问题——**现有数据从哪来、参考站数据能不能用、离线更新怎么做才不越界**。
> 口径：**已核实**＝本轮命令/实测；**未知**＝未验证（不猜）。

---

## 1. 现有项目的数据血缘（已核实）

`data/meta.json`（`schema: 8`，`generatedAt: 2026-10-20T15:10:05Z`，`gameMode: regular`）已具备完整血缘登记，逐条抄录：

| 来源 | 许可 | URL |
|---|---|---|
| tarkov.dev 地图配置（the-hideout/tarkov-dev） | **MIT** | `raw.githubusercontent.com/the-hideout/tarkov-dev/…` |
| tarkov.dev 标注数据（json.tarkov.dev） | tarkov.dev 社区公开数据 | `json.tarkov.dev/regular/maps` |
| tarkov.dev 中文翻译 | tarkov.dev 社区公开数据 | `json.tarkov.dev/regular/maps_zh` |
| tarkov.dev 中文物品名 | tarkov.dev 社区公开数据 | `json.tarkov.dev/regular/items_zh` |
| 底图 SVG（the-hideout/tarkov-dev-svg-maps） | **CC BY-NC-SA 4.0** | `assets.tarkov.dev/maps/svg/` |
| 瓦片底图（实验室/迷宫/破冰船） | tarkov.dev 社区公开数据 | `assets.tarkov.dev/maps/…` |
| 物品图标 | tarkov.dev 社区公开数据 | `assets.tarkov.dev/` |
| 商人图标 | **项目内自绘** | — |

**三条硬约束（来自上表，非本轮新增）**：
1. **底图是 CC BY-NC-SA 4.0** → 项目整体**不可商用**，且分发衍生底图需同协议署名。
2. 物品/商人图标来自 tarkov.dev 社区资源，**再分发需保留出处**。
3. 每条来源都登记了 `sha256` + `bytes` → 已有防篡改基线，应沿用。

其他数据（`gunslots` / `gun-stats` / `bosses` / `ammo` / `tasks`）由 `tools/*.py` 在构建期生成；`bosses.json` 内部自带 `sourcePage: https://escapefromtarkov.fandom.com/wiki/<Boss>` 与 `confidence` 分级（**已核实**：`healthConfidence: verified/estimated/missing`、`missing[]`）。

---

## 2. 参考站的数据可得性

### 2.1 db4tarkov.com

| 维度 | 结论 | 证据 |
|---|---|---|
| 渲染方式 | Flutter Web（CanvasKit），DOM 无文本 | `FLT-CANVAS-CONTAINER`/`CANVAS`，`innerText=0` |
| 数据通道 | 多源：自有 CDN + Firebase(Firestore/RTDB/RemoteConfig) + Supabase + json.tarkov.dev | 请求 host 统计（`raw/db4b-flow.json`） |
| 是否有公开 API | **未发现**；**有 Firebase App Check**（`firebase-app-check-database`、`recaptchaSiteKey`） | `inspect_web_page.storage` + console |
| 可否离线快照 | **不建议**：无稳定接口、有反滥用校验、数据格式私有 | — |
| 许可 | **未发现**任何 license / API 条款声明 | 首页与关于页未见 |
| 合规结论 | **只能作为功能与交互参考**（任务书 2.4 的定位），**不抓数据、不抄素材** | — |

### 2.2 eftarkov.com

| 维度 | 结论 | 证据 |
|---|---|---|
| 渲染方式 | nginx 服务端渲染，HTML 内含业务数据 | 首页 76,970 bytes 含公告/任务/服务器状态 |
| 数据通道 | 全部同域，无第三方接口 | 9 页 host 统计仅 `www.eftarkov.com` |
| 是否有公开 API | **未发现** | 每页仅 1 条统计类 URL |
| 可否离线快照 | 技术上可解析 HTML，但**许可未明** | — |
| 许可 | **未见明确 license**（页脚无声明） | — |
| 合规结论 | **功能形态参考 + 术语中文对照参考**；正文译文与自建图片**不得直接搬运** | 任务书 2.4 |

### 2.3 二者与现有项目的关系

```
现有项目  ──tarkov.dev(MIT/社区)──►  已是合法数据基座
db4tarkov ──参照功能/交互──►  不取数
eftarkov  ──参照功能/中文术语──► 不取数（许可未明）
```

**核心判断（已核实）**：现有项目的数据来源（tarkov.dev 生态）**比两个参考站更"可合法复用"**。参考站的价值在**功能形态**，不在数据。任何"从参考站补数据"的方案都应被否决，正确做法是**回到 tarkov.dev / 官方数据源**补。

---

## 3. 缺口数据与可行来源（第三阶段 5.3 的输入）

| 缺口 | 现有 | 可行来源（需先核许可） | 风险 |
|---|---|---|---|
| 商人（等级/库存/解锁） | 无 | tarkov.dev `traders`（社区公开） | 低 |
| 价格（跳蚤/商人） | 无（仅 `items.cost` 静态） | tarkov.dev `prices`（**有更新频率限制**） | **中：必须标"非实时"并显示时间戳** |
| Barter 配方 | 无 | tarkov.dev `barters` | 低 |
| Craft 配方 | 无 | tarkov.dev `crafts` | 低 |
| 藏身处 | 无 | tarkov.dev `hideout` | 低 |
| Boss 刷新概率 | `bosses.json` **无此字段**（已核实） | 需另找来源；参考站有展示但不可抓 | **高：可能长期只能标"未知"** |
| 弹药距离衰减矩阵 | 未确认含矩阵 | 需按游戏机制推导或找社区表 | **高：属"估算"，必须标 estimated** |

> 原则（任务书 2.4 + 5.2）：**缺就标缺**。`bosses.json` 现有的 `missing[]` + `confidence` 机制应推广到所有新数据，而不是用 0 或推测值填坑。

---

## 4. 离线更新机制建议（第三阶段 5.3）

现有 `meta.json` 已是「来源 + 许可 + sha256 + 生成时间」的雏形，建议**沿用而非另起一套**：

1. **独立更新器**（离线隔离）：`tools/update_data.py --check` 只输出「可用版本/差异」，不写 `data/`。
2. **两级确认**：`--plan` 生成差异报告 → 用户确认后 `--apply` 写入；写入前自动备份到 `data/_backup/<ts>/`。
3. **校验**：每个产物写 `sha256` + `bytes` + `schema`；`--verify` 可离线校验。
4. **回滚**：`--rollback <ts>` 从备份恢复。
5. **门禁**：应用后自动跑 `pytest tests -q` 与 `node tools/r1913_audit.js`，不过则不落盘（或在报告中标注失败）。
6. **运行期零联网**：`index.html`/`app.js` 永不请求外部域（现状已满足，R19.29 验收 463 请求全本地）。

**不建议**：在应用内做「一键联网更新」。任务书 2.3 明确要求「需要联网更新的数据应设计为独立的可选更新流程，与正常离线使用相互隔离」。

---

## 5. 未知项（不猜）

| 项 | 状态 |
|---|---|
| 两站的 robots.txt / ToS 具体条款 | **未逐条核对**（仅确认未见 license 声明） |
| tarkov.dev 各端点的速率限制与稳定性 | **未实测**（仅知现有 `meta.json` 记录的 URL 可用） |
| 参考站数据的游戏版本滞后程度 | **未知** |
| 现有 `ammo.json` 是否含距离衰减矩阵 | **未逐字段核对**（只知道 89KB 规模） |
