# R19.25 变更清单

版本：`R19.23`（任务书基线）→ 实际当前 `R19.24`（上一轮 UI 设计系统）→ **本轮 `R19.25`**
原因：任务书建议的 R19.24 已被上一轮交付占用，两个交付不能共用一个版本号。
同步位置：`app.js` 的 `AM_BUILD`、`index.html` 全部 `?v=`、`tools/serve.py` 的 `rev` 前缀。

---

## 一、新增文件

| 文件 | 职责 |
|---|---|
| `js/task-graph-layout.js` | **布局模块**（纯计算，无 DOM/网络/业务依赖）：建图 → 弱连通分量 → 分层 → 中位数排序 → 分带打包 → 正交折线；输出节点坐标、边折点、分带与质量指标 |
| `tools/r1925_tree_audit.py` | 从真实页面提取节点/边并计算几何指标（交叉、穿节点、重叠、画布、环），用于改造前后对比 |
| `tools/r1925_ref_tree.py` | 参考站 EFTarkov 任务树的几何探针（节点尺寸、连线指令类型、分组节点） |
| `tools/r1925_layout_test.js` | 布局模块的结构性测试（46 条）：唯一性、边完整、无重叠、确定性、菱形/环/长边/脏边、真实数据质量门槛 |
| `tools/r1925_trader_audit.py` | 商人名称审计：16 个商人的 ID/来源/英文名/旧中文名/最终显示名 + 12 个显示位置的代码定位 |
| `tools/r1932_accept.py` | 本轮真实浏览器验收（30 项）+ 12 张截图 |
| `tests/test_r19_25_round.py` | 本轮 pytest 专项（A 布局结构 / B 渲染接入 / C 商人名称 / D 三模式 / E 版本与离线） |
| `docs/r19.25-task-tree/` | `audit.md` `layout-design.md` `change-log.md` `test-report.md` `trader-name-audit.json` `layout-{before,after}.json` `nodes-*.json` `browser-accept.json` `shots/` |

## 二、修改文件

| 文件 | 改了什么 | 为什么 |
|---|---|---|
| `tasks.js` | ① 删除旧 `buildGraph`（最长路径 + 列内按商人排序）与旧连线绘制；改为调用 `GWTaskGraph.layout()` 并按 `mode + 任务数` 缓存<br>② `renderTree` 重写：先画商人分带（带标题=英文名+任务数），再画正交折线（AND/OR/失败/跨商人/环 分别标注），最后画节点<br>③ 新增 `traderEn(rec)` 作为商人显示名的**唯一入口**，替换 12 处中文商人名<br>④ 新增 `clampLabel()`：节点标题截断时不会把中文名截成纯英文<br>⑤ `focusStart()`：默认视角落在第一条商人带（0.72 倍），不再一进来就看不 clean 的全图<br>⑥ 图例加"跨商人依赖"与分带说明 | 布局混乱的根因在旧算法；商人名按要求统一英文 |
| `tasks.css` | 新增 `.tk-band` / `.tk-band-label` / `.tk-band-rule` / `.tk-edge.is-cross|is-long|is-cycle` / `.tk-node.is-crosstrader` / 图例项；颜色走 `--ui-*` 令牌 | 分带与线型需要样式；避免再写裸色 |
| `js/ui-components.js` | 无改动 | 本轮不改设计系统 |
| `index.html` | 新增 `<script src="js/task-graph-layout.js?v=r19.25">`（在 `tasks.js` 之前）；全部 `?v=` 升到 `r19.25` | 布局模块必须先加载 |
| `app.js` | `AM_BUILD = "R19.25"` | 版本标记 |
| `tools/serve.py` | `"rev": "R19.25-"` | 版本标记 |
| `tools/fetch_tasks.py` | 攻略概述改用 `traderEn`（"由 Prapor 发布…"），其余文案仍中文 | 攻略里的商人标识也要英文原名（任务书 §7.2） |
| `data/tasks/guides.*.json`（3 个） | 由 `fetch_tasks.py --offline` 重新生成（**不重新联网抓取**，用的还是同一批 raw 快照） | 概述文本变化 |
| `data/tasks/tasks.*.json`（3 个）、`traders.json`、`index.json`、`sources.json` | 同上一次性重建（内容除生成时间外与 R19.24 一致：503/499/462、边 222/221/184） | 与 guides 同批产物 |
| `data/i18n/ui-zh.json` | `keptEnglish.why` 增加 `traderName` 说明；`entries` 增加 16 个英文商人名 | 把"英文原名"登记为中文化的显式例外，避免后续扫描误报缺口 |
| `tests/test_r19_23_round.py` | 版本断言从写死 `R19.23` 改为"跟随 AM_BUILD 且覆盖全部资源" | 避免每轮改测试；断言更强（覆盖 6 个资源） |

## 三、删除 / 替换（逐条说明影响）

| 删除项 | 位置 | 影响 |
|---|---|---|
| `buildGraph()` 旧实现（约 60 行） | `tasks.js` | 位置改由布局模块计算；`state.graph` 的对外形状（`nodes[id].x/y`、`width/height`、`ids`）保持不变，`centerOnTask` / `fitTree` / `refreshVisible` 无需改 |
| 旧节点渲染里的 `clampText(rec.nameZh, 15)` | `tasks.js` | 换成 `clampLabel(..., 14)`，语义相同但不会截成纯英文 |
| 旧图例里"空心箭头=可选/失败条件"一句 | `tasks.js` | 换成 4 条独立线型 + 分带说明，避免一条文案描述三种线 |
| 画布内 `rank/row` 概念 | `tasks.js` | 对外不再暴露（审计脚本已兼容读取），内部层级改为分量内 `layer/order` |

## 四、未改动（明确保留）

- 三模式数据管线（`tools/fetch_tasks.py` 的抓取/标准化/差异工具）与三套数据文件结构；
- 进度存储键 `eftmap.tasks.progress.v1` 与三模式隔离逻辑；
- 任务详情、攻略、导入导出、地图联动；
- `data/gun-layout-calibration.json`（未读未写）；
- `release/` 目录（未触碰）；
- UI 设计系统（`styles/*`、`ui-showcase*`）—— 上一轮成果保持原样。

---

## 五、R19.25.1 补充改动（量化验收约束）

| 文件 | 改动 | 原因 |
|---|---|---|
| `js/task-graph-layout.js` | v1.1：分量并入失败分支；孤立任务密集网格；块顶母线路由；通道/走廊分道；`edgeNodeHits` / `segmentCrossings` / `segmentOverlaps(±Long)` / `bends` / `isolated` 指标 | 零穿卡 + 可量化 |
| `tasks.js` | `traderNameById()` 统一奖励/解锁商人名；商人卡片 tooltip 不再塞中文机翻；分带标题标注跨商人线；布局缓存键加入数据生成时间 | §5 商人英文名全覆盖 |
| `tools/r1925_tree_audit.py` | 提取 DOM 真实 path，统计段交叉 / 重叠 / 穿卡 / 转折 | 不许只凭截图宣称改善 |
| `tools/r1925_trader_audit.py` | 显示位点 12 → 14（补奖励·声望 / 奖励·解锁） | 审计覆盖真实显示面 |
| `tools/r1932_accept.py` | E2 硬门槛升级；新增 H1 稳定性 / H2 正交硬门槛 / H3 tooltip / H4 奖励英文名 | 真实浏览器验收 |
| `tools/r1925_layout_test.js` | +33 条：穿卡 0、失败分支不参与分层、分量不拆、键序稳定、孤立任务紧凑、依赖边逐条对账 | 结构正确性 |
| `tests/test_r19_25_round.py` | +1 条正交硬门槛（读验收报告） | 防回退 |
| `tests/test_r19_23_round.py` / `tests/test_ui_system_round.py` | 版本正则允许补丁号（R19.25.1） | 断言改为跟随 AM_BUILD 后的必要放宽，其余不变 |
| `app.js` / `index.html` / `tools/serve.py` | `AM_BUILD=R19.25.1`、`?v=r19.25.1`、rev 同步 | 缓存失效与指纹 |
| `docs/r19.25-task-tree/layout-metrics-compare.json` 等 | 三列指标对照 + 本附录 | 可复核 |

未改动：`data/tasks/*`（数据管线与三模式进度隔离）、`gun_builder.js`、`app.js` 业务逻辑（仅版本号）、`release/`。
