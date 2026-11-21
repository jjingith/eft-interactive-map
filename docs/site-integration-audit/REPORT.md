# R20 第一 / 二阶段审计报告（只研究，未开发）

> 项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`
> 时间：2026-10-29
> 范围：**仅第一阶段（MCP 能力 + 两站功能审计）与第二阶段（现有工程盘点 + 映射规划）**。
> **未进入任何功能开发**：没有修改 `app.js` / `index.html` / `css` / `data/*` / `tests/*` 中的任何既有文件，未提交 Git。

---

## 研究摘要（先看这段）

### 已确认（有实测证据）

1. **`rea` 是真正的浏览器能力 MCP**，但它是「CDP 观察器」而非「自动化框架」：截图 ✅、DOM 结构 ✅、脚本清单 ✅、导航 ❌（需外部浏览器）。实测证据见 `mcp-capability-audit.md`。
2. **两个站点都能打开且无需登录即可浏览**；db4tarkov 是 **Flutter(canvas) + Firebase/Supabase**（首次进入需 30–45s 下载数据，DOM 无文本）；eftarkov 是 **nginx 服务端渲染**（DOM 可直接读）。
3. **db4tarkov 有 12 个一级栏目**（MARKET / SEASON / QUEST / KEEP / GUN / PRESET / AMMO / MAP / BARTER / CRAFT / CHANGES / LOGS），全部进入并截图。
4. **eftarkov 有 10 个一级入口、60+ 二级分类页**（任务/任务树/转生/收集/藏身处/地图/商人/Boss/成就/技能/物品×30+ 分类/价格/排行/倒货/交换/制作…），实测 9 个高价值页面。
5. **现有项目的数据来源比参考站更"可合法复用"**：`data/meta.json` 已登记 `sources[] + license + sha256`，其中底图是 **CC BY-NC-SA 4.0（不可商用）**。
6. **工程基线可复现**：`1337 passed / 5 failed / 1 skipped`（83.07s），5 项失败与 R19.29 报告一致且至今未修。
7. **现有项目运行期零外链**：`index.html`/`app.js` 中除 SVG 命名空间与两个 GitHub 署名链接外无外部资源引用（静态核查 + R19.29 运行期 463 请求全本地）。

### 仍未确认（**不要当成已知**）

- db4 的**单枪构建页、详情页**交互（Flutter 导航无法稳定命中，见 `research-limitations.md` L1–L3）
- 两站的**服务条款/robots/license**（未见声明，需人工法务确认，L9）
- **Boss 刷新概率**的可靠数据来源（现有 `bosses.json` 无此字段）
- **弹药距离衰减 / 护甲矩阵**是否已有数据（未逐字段核对）
- 参考站数据相对游戏版本 1.3.0.0 的滞后程度

### 建议优先级（与任务书 P0–P4 的差异已标注）

```
B1  P0-3 数据血缘与校验 + P0-4 模式读取收口      ← 纯基础设施，零 UI 风险
B2  P0-2 物品视图（新建只读模块）+ P0-1 聚合搜索薄层
B3  P0-5 进度只读汇总 + P1-4 收集清单
B4  P3-1 价格表（带时间戳）                      ← 上调：解锁后面两项
B5  P1-2 Buy/Sell 成本 + P1-1 枪械视图补强
B6  P2-1 任务树 + P2-2 地图任务联动
B7  P4-1 混压弹匣时序                            ← 上调：复用既有引擎
B8  P1-3 弹药矩阵（先做数据可行性验证，不通过就降级为"不做"）
B9+ P2-3 藏身处 / P3-2 barter·craft / P3-3 倒货排行（下调）
```

**关键判断**：现有项目缺的不是"页面数量"，而是**商人/价格/配方/藏身处这一整条数据链**。所以真正的第一优先不是抄 db4 的界面，而是**先把数据血缘与更新门禁做扎实**（B1），再补数据（B4）。

---

## 1. 本阶段目标

| 目标 | 完成度 |
|---|---|
| 核实 MCP 真实能力（不凭安装提示推断） | ✅ 8 类能力逐项给出「已测/部分/不可用/未测」 |
| 实测两个参考站的可达性与功能面 | ✅ db4 12 页 + eft 10 页 |
| 建立两站功能清单（含证据、登录、在线依赖、可本地重建性） | ✅ 2 份清单 |
| 盘点现有工程真实状态（不采信历史报告） | ✅ 模块矩阵 + 基线命令 |
| 功能映射表（复用/补足/新建） | ✅ `reuse-vs-rebuild.md` |
| 标记无法验证项 | ✅ `research-limitations.md` 共 11 条站点项 + 4 条 MCP 项 + 6 条方法学项 |
| 分阶段实施方案与优先级 | ✅ B1–B9 |

---

## 2. 已审计的网页与操作步骤

### 2.1 操作步骤（可复现）

```bash
# 1) 启动受控 Chrome（关键：--no-proxy-server，否则 localhost 会被送进系统代理）
chrome --headless=new --remote-debugging-port=9333 --user-data-dir=%TEMP%\r20audit \
       --no-proxy-server --window-size=1600,1000 about:blank

# 2) 单页取证（标题/语义标签/链接/请求/控制台/截图）
python tools/r20_site_probe.py --connect 9333 --url https://db4tarkov.com/gun --name db4-gun --wait 30

# 3) 站内流程取证（加载一次 → 点击 → 截图，用于 SPA）
python tools/r20_flow_probe.py --connect 9333 --url https://db4tarkov.com/gun \
       --labels MARKET,QUEST --points "MARKET:450,66;QUEST:597,66" --prefix db4b --wait 34
```

### 2.2 db4tarkov（12 页，全部截图）

| 页面 | URL | 关键实测信号 |
|---|---|---|
| GUN | `/gun` | 按口径分行的枪械卡片网格；二级 `Caliber/Class/Table/Gun`；`Gunsmith/TierMaker/Streamer/Variant/Saved` |
| MARKET | `/market` | `Last Price / Avg 24h / Avg 7d` + `MARKET/TRADER/CRAFT/BARTER` |
| QUEST | `/quest` | 149 语义标签 / 92 按钮；`Trader level / PMC Setting` |
| KEEP | `/keep` | 371 张图；`Items / Collected / Keys` |
| PRESET | `/preset` | 纸娃娃 8 槽 + `Move/Turn/Ergo` + `Final Cost: Buy()/Sell()` |
| AMMO | `/ammo` | 弹道大表（距离衰减 + 1–5 护甲等级色块）+ 4 组滑杆 |
| MAP | `/map` | `reshala Customs 60% 20% 25% 20%`（Boss 刷新概率矩阵） |
| BARTER | `/barter` | 配方 + 价格口径 |
| CRAFT | `/craft` | 制作利润 |
| CHANGES | `/changes` | `1.2.0.0.47888 2026/10/07` + `34 NEW` |
| SEASON | `/season` | 赛季规则（`NO INSURANCE`/`BLACK DIVISION`…）；请求到 `json.tarkov.dev` |
| LOGS | `/logs` | `SELECT LOGS FOLDER`（本地日志解析，无额外网络请求） |

### 2.3 eftarkov（10 页）

`/`（首页）、`/task`、`/task-tree`、`/hideout`、`/ammo`、`/resale`、`/fabrication`、`/exchange`、`/boss`、`/map/653e6760052c01c1c805532f`。

标题即功能声明（实测）：`任务列表` / `任务树形图` / `藏身处升级` / `子弹` / `倒货排行` / `藏身处制作配方利润` / `商人交换配方利润` / `BOSS资料` / `中心区互动地图`。

---

## 3. MCP 实际使用的能力及限制

| 能力 | 结论 | 备注 |
|---|---|---|
| 截图 | ✅ | 返回内容寻址 PNG（sha256 可核） |
| DOM 结构 | ✅（策略过滤） | 对 Flutter 页拿到 114 节点 + 8 脚本 + 6 资源 |
| 脚本清单 | ✅ | `main.dart.js` 18.5MB；**源码默认不采集** |
| 网络请求 | 🟡 | `requests: []`——观察窗口从 attach 开始；**导航前 attach 才拿得到** |
| 导航 | ❌ | 无 navigate 工具，必须外部 Chrome 先导航 |
| 点击 | 🟡 | `capture_browser_scenario` 未实测；本机 CDP 点击对 canvas 命中不稳 |
| 写文件 | ❌ | 无该工具，审计产物由本地 Python 落盘 |

详见 `mcp-capability-audit.md`（含每项的 `evidence_id` 与具体数字）。

---

## 4. 新增、修改和未修改的文件

### 4.1 新增（3 项，全部为审计工具与文档）

| 路径 | 说明 |
|---|---|
| `tools/r20_site_probe.py` | 单页取证探针（截图/语义/链接/请求/控制台） |
| `tools/r20_flow_probe.py` | SPA 站内流程探针（点击 + 分步截图） |
| `docs/site-integration-audit/` | 8 份文档 + `raw/`（27 JSON）+ `screenshots/`（24+10=34 PNG），共 9.1MB |

### 4.2 修改

**无。** `app.js` / `index.html` / `css` / `data/*` / `tests/*` 本轮一个字节未改。

> 佐证（文件 mtime，本轮审计始于 13:23）：`app.js` 12:58、`index.html` 12:45、`data/meta.json` 2026-10-20，均**早于**本轮审计；本轮新增文件为 13:28 之后的 `tools/r20_*.py` 与 `docs/site-integration-audit/*`。
> 工作区里 `M app.js` 等条目是**本轮之前就存在**的未提交改动（R19.29 交付遗留），不是本阶段产物。

### 4.3 未修改但需知悉

- 运行 `pytest tests -q` 会**就地重生成** `docs/r19.13-layout-audit/*.json`（既有测试行为，非本轮改动）。
- `data/` 目录下有 6 个 `.bak/.prev` 备份文件（`items.json.r1918/1919/1920/1921.bak.json`、`gunslots.json.r1919/r1920.bak.json`、`gun-layout-calibration.json.bak/prev`）——**体积污染**（`items.json.r1919.bak.json` 8.5MB），建议后续清理，本轮不动（审计阶段不删文件）。

---

## 5. 功能复用关系（摘要，完整表见 `reuse-vs-rebuild.md`）

| 参考站能力 | 结论 | 复用/新建 |
|---|---|---|
| 任务列表/前置/进度 | 现有已覆盖且更细（3 模式 + 路线） | **复用**，仅补"任务树可视化" |
| 互动地图/标记 | 现有已覆盖（2MB 数据 + 路网 + 障碍物） | **复用**，补"任务联动筛选" |
| 枪械构建 | 现有已覆盖（163 把 + 兼容矩阵 + 校准器） | **复用**，补视图维度 |
| 装备配装 | 现有更细（插板/内衬/方向） | **复用**，补 Buy/Sell 双口径 |
| 弹药表 | 现有有表 + 模拟 | **复用**，矩阵需先验数据 |
| 逐发模拟 | 现有最强（分层/方向/障碍/证据分级） | **复用**，补混压弹匣时序 |
| 收集清单 | 可派生 | **新建轻页面** |
| 藏身处 / 制作 / 交换 / 价格 / 倒货 | **现有完全没有** | **新建 + 新数据** |
| 物品独立浏览 | 现有只有"嵌在别处"的物品信息 | **新建只读视图** |
| 日志解析 | 现有有离线脚本 `tools/eftlog.py` | **复用脚本**，不搬进浏览器 |

---

## 6. 数据来源及不确定性

| 类 | 内容 |
|---|---|
| 现有数据来源（已登记） | tarkov.dev 生态（MIT / 社区公开）+ **底图 CC BY-NC-SA 4.0** + 项目自绘商人图标 |
| 参考站数据 | **不采用**（db4 无 API + App Check；eft 许可未明） |
| 最大不确定性 1 | Boss 刷新概率：**无可靠来源** |
| 最大不确定性 2 | 弹药距离衰减/护甲矩阵：**数据是否已存在未核实** |
| 最大不确定性 3 | 价格类数据：只能做"历史快照"，**必须带时间戳**，不得伪装实时 |

---

## 7. 测试命令与真实结果（本轮基线，2026-10-29）

| 项 | 命令 | 结果 |
|---|---|---|
| 分支/HEAD | `git branch --show-current` / `git log --oneline -1` | `main` / `bf438df` |
| 工作区 | `git status --porcelain \| wc -l` | **345**（审计前）→ **348**（仅 +3 个未跟踪的审计产物） |
| JS 语法 | `node --check app.js` | ✅ OK |
| 完整测试 | `/c/Python314/Scripts/pytest tests -q --tb=line -p no:cacheprovider` | **5 failed, 1337 passed, 1 skipped in 83.07s** |
| 失败清单 | 同上 | `test_r19_11::test_hide_incompat_filters_without_touching_data`、`test_r19_13::test_row2_anchors_are_driven_by_real_slot_tree`、`test_r19_1::test_candidate_columns_match_reference_order`、`test_r19_5::test_zoning_is_generic_semantic_rules`、`test_r6_gun_workbench::test_gun_workbench_business_logic` |
| 浏览器可用性 | 本机 Chrome 156 headless + CDP | ✅ 可启动，两个外部站点与 `127.0.0.1` 本地服务均可访问 |
| 外链静态核查 | `grep -o 'https\?://…' index.html app.js` | 仅 `w3.org` 命名空间 + 2 个 GitHub 署名链接；**无资源加载型外链** |
| 外部请求（运行期） | R19.29 验收（同一工作区，今日） | 463 次请求 host 仅 `127.0.0.1` |

> 与 R19.29 报告的 `1337/5/1` **完全一致**，说明该数字在本轮复现成立，可作为 R20 的真实基线。

---

## 8. 浏览器验收截图

目录：`docs/site-integration-audit/screenshots/`（34 张，1600×1000 PNG）

| 站点 | 数量 | 代表文件 |
|---|---|---|
| db4tarkov | 24 | `db4-gun.png`、`db4-ammo.png`、`db4-preset.png`、`db4-map.png`、`db4-keep.png`、`db4-logs.png` |
| eftarkov | 10 | `eft-home.png`、`eft-task.png`、`eft-task-tree.png`、`eft-hideout.png`、`eft-ammo.png`、`eft-map.png`、`eft-resale.png`、`eft-fabrication.png`、`eft-exchange.png`、`eft-boss.png` |

配套结构化证据：`raw/*.json`（27 份，含 `aria` / `links` / `requests` / `hosts` / `console`）。

---

## 9. 失败项及原因

| # | 失败/未达成 | 原因 | 影响 |
|---|---|---|---|
| 1 | db4 导航项点击不稳定 | 导航不在 Flutter 语义树中，canvas 命中需精确坐标；本轮 2 次标定未命中 | 单枪构建页/详情页未审计（L1–L3） |
| 2 | db4 首访 30–45s | 客户端需下载大量数据 | 逐页审计成本高（12 页约 8 分钟） |
| 3 | MCP 网络取证为空 | attach 晚于页面加载 | 改用本机 CDP 采集（已解决，但记为能力限制） |
| 4 | 两站许可/ToS 未确认 | 页面未见 license 声明 | 决定"能不能用"的最终依据缺失（L9） |
| 5 | 5 项旧测试仍失败 | R19.28 遗留（实现与旧断言文本不一致） | 新模块"旧测试全绿"门槛不可达（D6） |

---

## 10. 尚未解决的风险

| # | 风险 | 等级 | 缓解建议 |
|---|---|---|---|
| R1 | 把参考站的**历史快照价格**当成实时价展示 | **高** | 强制 UI 显示数据时间戳 + "历史快照"标识（任务书 P3 明确要求） |
| R2 | 为"补齐功能"而**编造数据**（Boss 概率、弹药矩阵） | **高** | 沿用 `bosses.json` 的 `confidence: verified/estimated/missing` + `missing[]` 机制；缺就显示"未知" |
| R3 | 新增 6 个模块导致**导航膨胀**，破坏现有 XP 风格 | 中 | 先按 D1 走"页内二级 Tab"，顶栏保持 5 项 |
| R4 | 新数据引入后**旧数据静默变化** | 中 | B1 先建 schema 校验 + 更新前后 diff + 回滚 |
| R5 | **许可风险**：底图 CC BY-NC-SA 4.0 | **高（若商用）** | 若要商用必须替换底图；否则保持非商业分发 |
| R6 | 参考站改版导致审计结论过期 | 中 | 审计脚本已入库，可随时重跑；报告标注站点版本 `v2026.10.28-0` |
| R7 | Flutter 站点结论强度天然偏弱 | 中 | 已在 `research-limitations.md` 标注"观察到"而非"验证过" |

---

## 11. 下一阶段建议

1. **先确认 6 个决策项**（`reuse-vs-rebuild.md` §3 D1–D6），尤其是 **D1 导航形态** 与 **D2 是否引入价格数据**——这两项决定后续所有排期。
2. **批准后从 B1 开始**（数据血缘与校验 + 模式读取收口）：它不改任何 UI，却能立刻提升后续每个数据模块的安全性。
3. **不建议**直接开始"抄 db4 的 12 个页面"：现有项目缺的是数据链（商人/价格/配方/藏身处），不是界面数量。
4. **建议单开一轮**处理 D6（5 项历史失败），否则"旧测试全绿"永远无法作为交付门槛。
5. 若需要更强的 db4 审计（单枪构建页等），需要一次**有人值守的坐标标定**（约 10 分钟），或改用 `capture_browser_scenario`（需先确认其 canonical schema）。

---

## 附：本阶段产物索引

```
docs/site-integration-audit/
├── REPORT.md                     ← 本文件（总报告）
├── mcp-capability-audit.md       ← MCP 能力矩阵（逐项实测）
├── db4tarkov-feature-inventory.md
├── eftarkov-feature-inventory.md
├── interaction-catalog.md        ← 23 种交互模式 + 4 条反例
├── data-source-audit.md          ← 数据血缘 / 许可 / 离线更新方案
├── existing-module-matrix.md     ← 现有 10 个模块状态矩阵
├── reuse-vs-rebuild.md           ← 功能映射表 + 批次排期 + 6 个决策项
├── research-limitations.md       ← 未验证项与合规声明
├── raw/*.json                    ← 27 份结构化取证
└── screenshots/*.png             ← 34 张界面截图
tools/r20_site_probe.py           ← 单页取证（可复现）
tools/r20_flow_probe.py           ← SPA 流程取证（可复现）
```
