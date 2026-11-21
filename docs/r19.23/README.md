# R19.23 任务系统三模式（PvP / PvE / PvPS 赛季服）交付说明

本目录是 R19.23 的验收与数据证据目录。

| 文件 | 内容 |
|---|---|
| `ref-probe.json` / `ref-probe2.json` | 参考网站（eftarkov.com、db4tarkov.com）真实浏览器的结构探针原始结果 |
| `ref/*.png` | 参考网站截图（含 DB4Tarkov 的 Flutter 画布界面） |
| `diff-report.md` | 三模式差异报告（由 `tools/diff_tasks.py` 自动生成，可随时重跑） |
| `task-validation.json` | 三模式数据校验结果（`tools/validate_tasks.py`） |
| `browser-accept.json` | 真实 Chrome 验收结果（`tools/r1931_accept.py`） |
| `shots/*.png` | 验收截图（见文末清单） |

---

## 一、参考网站实测对照（不是"看图猜"）

用 `tools/r1923_ref_probe.py` + `r1923_ref_probe2.py` 在真实 Chrome 里加载并点击，结论如下。

### eftarkov.com/task（任务列表）

实测：`h1=任务列表`、右上角 `共 510 个任务`；第一行筛选是「全部商人 / 地图 / 搜索框 / 重置」，
下面是 `Kappa 任务 / DSPT 任务 / 已完成任务` 三个勾选项；每行 = 商人头像 + 任务名 + 右侧「地图 · 等级1+ · 未完成」。
模式切换是页头右上角的一个下拉（`data-dropdown="mode"`），展开后是 **PVP / PVE / PVP 赛季** 三项。

采纳：
- 模式切换放页头右上角、三项并列（本项目改为三个常驻按钮，比下拉少一次点击）。
- 「共 N 个任务」的显式计数、商人/地图/等级/状态/Kappa 筛选、已完成任务单独开关。
- 任务行的信息密度：名称 + 商人 + 地图 + 等级 + 状态。

未采纳：**DSPT 任务**筛选。理由：本项目上游任务数据里没有任何 DSPT 字段（`grep -ri dspt data/` 为空），
照抄会得到一个永远筛不到东西的假开关——任务书 §5.1 明确禁止。

### eftarkov.com/task-tree（任务树）

实测：`task-tree-node task-tree-node-task` 共 540 个节点、`is-mode-locked` 63 个（当前模式下不可用的节点会灰掉）、
`task-tree-node-section` 39 个（分组节点）、`task-tree-node-trader` 11 个（商人分组）；
每个节点内部有 `task-tree-card-top` + `task-tree-meta` + `task-tree-objectives`，
其中 `task-tree-objective` 共 1458 条——**目标摘要直接写在节点卡片里**。
工具栏只有 `搜索任务名称 / 定位 / 复位` + 一排商人头像跳转。悬停提示里写着
`PVP / PVE / 赛季服 专属任务`、`BEAR 专属任务`、`USEC 专属任务`。

采纳：
- 节点内显示「商人 · 等级 · 目标数」，并把模式/阵营标记做成节点角标 + 元信息文字。
- 搜索 → 定位 → 复位 的三件套（本项目原有，保留并加了「适配全图」）。
- 节点信息用 `<title>` 承载完整信息（中文名 + 英文原名 + 状态 + 模式 + 失败分支数）。

未采纳：默认把所有节点铺满一屏（本项目首次进入用 0.55 倍落在最左列，点「适配全图」再看全局，
否则 176px 宽的卡片在 1080p 下会缩到看不清字）。

### db4tarkov.com/quest

该站是 **Flutter Web**（`main.dart.js` + `flutter.js`），渲染到画布，`document.body.innerText` 长度为 0、
`canvas` 数量为 0（Flutter 用 `flt-*` 元素），首屏截图曾超时，第二次等 20s 后成功截到界面。
因此它的 DOM 结构**无法**逐元素核对，只能依据截图记录可见信息架构：

- 顶部主导航 + 右上角 `PVE / PVP` 两钮模式切换；
- 左侧一列商人头像做筛选，右侧是极密的单列表格：任务名、目标逐条（带图标）、物品缩略图、XP、等级、状态；
- 右栏筛选：Sort（By Exp / By Map / By Progress / By Objectives Done）、Type（带数量）、
  完成状态（Quest / Failed / Banned / Completed / Uncompleted / **Only-Season** / Only-Kappa /
  Only-Lightkeeper / Only-Available / Only-Unlockitem / Only-Duty-Available）、阵营（BEAR/USEC）开关；
- 每行右侧一个 `Complete` 按钮，行内目标可直接勾。

采纳：
- 「按进度 / 按前置数 / 按名称 / 按等级」排序（本项目的排序下拉）。
- 行内直接给状态与勾选入口（本项目在详情页勾目标，列表页给状态与「详情」）。
- 列表里直接看到「模式」归属列（对应它的 Only-Season 过滤思路）。

未采纳：把目标逐条铺在列表行里（本项目列表行的目标摘要放悬停提示，详情页才展开），
因为中文字号比它大，逐条铺开会把行高撑到 60px 以上，反而降低浏览效率。

> 说明：DB4Tarkov 的 DOM 文本不可读，凡是本文档没写的内容，本轮**没有**核实过，不据此下结论。

---

## 二、三个模式的数据情况

数据源：`https://json.tarkov.dev/{gameMode}/tasks`，`gameMode ∈ {regular, pve, pvp-season}`
（端点清单见 `https://json.tarkov.dev/endpoints` 的 `gameModes` 字段）。赛季元信息取 `/pvp-season/season`。

| 项目 | PvP | PvE | PvPS（赛季服） |
|---|---:|---:|---:|
| 实际收录任务数 | 503 | 499 | 462 |
| 任务目标总数 | 1416 | 1384 | 1304 |
| 前置关系（边） | 222 | 221 | 184 |
| 有前置的任务 | 203 | 202 | 169 |
| 赛季专属任务数 | 0 | 0 | **0** |
| Kappa 必需 | 13 | 13 | 13 |
| 阵营限定 | 34 | 34 | 34 |
| 数据更新时间 | 2026-10-28 | 2026-10-28 | 2026-10-28 |
| 上游端点 | `/regular/tasks` | `/pve/tasks` | `/pvp-season/tasks` |
| 数据源完整性 | 完整 | 完整 | 完整（但**是 PvP 的真子集**，见下） |

赛季元信息：id `69e232a764dfe95549003f0f`，英文名 `Kord Breach`，周期 2026-04-17 → 2026-12-07，赛季技能 40 条。
上游中文表里**没有**赛季名的中文译名（返回的就是英文原名），因此界面原样显示并标注
「上游未提供中文译名」，没有自行编造译名。

### PvPS 的数据性质（重要）

- `pvp-season` 是独立端点、独立文件（`data/tasks/tasks.pvps.json`，3.5 MB，哈希与 regular/pve 均不同）。
- 但当前快照里 `pvps` 的任务集合是 `regular` 的**真子集**：41 个 PvP 任务在赛季服不存在，
  0 个任务只在赛季服存在 → **赛季专属任务计数为 0**。
- 本项目据此**不做**「把 PvP 全量复制成 PvPS」的假数据，也不构造虚构的赛季任务线；
  界面上明确写出这条事实（`#tk-mode-note` 的 `.tk-mode-note-warn`）。
- 「赛季专属」筛选项只在真的有赛季专属任务时出现；当前为 0 → 不显示（避免假筛选）。
- 一旦上游下发赛季专属任务，`seasonOnly` / `onlyInModes` 标记与筛选项会自动出现，无需改代码。

---

## 三、三模式差异（详见 `diff-report.md`）

| 检查项 | PvP vs PvE | PvP vs PvPS | PvE vs PvPS |
|---|---:|---:|---:|
| 仅在左 | 27 | 41 | 38 |
| 仅在右 | 23 | 0 | 1 |
| 同 ID 有字段差异 | 14 | 4 | 14 |
| 目标差异 | 6 | 1 | 5 |
| 前置关系差异 | 3 | 1 | 2 |
| 前置条件差异 | 2 | 1 | 1 |
| 奖励差异 | 5 | 0 | 5 |
| 失败分支差异 | 0 | 2 | 2 |
| 商人归属差异 | 0 | 0 | 0 |

典型差异（可在 `diff-report.md` 里逐条核对）：

- `化学品 - 3`（PvP）：前置 `complete OR active`；PvE/PvPS：只要 `complete`（AND 语义不同）。
- `收视灵药`：PvP 要求等级 ≥10 且有前置；PvPS 无等级要求、无前置。
- `外部订单` / `电池换新`：PvP 有失败分支（某个任务状态会让它失败），PvPS 没有。
- `维和任务` / `古董爱好者` / `反抗`：PvE 奖励物品比 PvP 多一件。
- 只在 PvP 存在的 41 个任务里包含「亡羊补牢」「赚点快钱 - 1（PVP）」等竞技场/模式限定任务。

---

## 四、如何维护（下一版游戏更新时）

```bash
# 1) 重新抓三模式数据（失败会自动保留上一次快照并标记 stale）
python tools/fetch_tasks.py

# 2) 只重建标准化文件（不动 raw 快照）
python tools/fetch_tasks.py --offline

# 3) 数据校验（三模式 ID/引用/AND-OR/失败分支/来源/赛季证据/差异报告一致性）
python tools/validate_tasks.py

# 4) 重算三模式差异报告
python tools/diff_tasks.py            # 写 data/tasks/diff-report.json + docs/r19.23/diff-report.md
python tools/diff_tasks.py --check    # 只看汇总

# 5) 中文化扫描（未覆盖必须为 0）
python tools/build_i18n.py

# 6) 真实浏览器验收（三模式切换 / 进度隔离 / 回归）
python tools/r1931_accept.py --port 9761

# 7) 全量测试
python -m pytest -q
```

### 防混淆检查清单

1. `validate_tasks.py` 会在以下情况**直接报错**（退出码 1）：
   - 某模式任务数为 0（拒绝空数据覆盖）；
   - `tasks.<mode>.json` 的 `upstreamGameMode` 与预期端点不符；
   - `modeScope` / `onlyInModes` 与实际任务集合不一致；
   - `seasonOnly` 标记出现在非 pvps 模式；
   - PvP 与 PvPS 任务集合完全一致（复制数据的典型症状）；
   - `sources.json` 里某模式来源 URL 不指向其上游端点。
2. `diff_tasks.py` 按**任务 ID** 求差集，`onlyLeft/onlyRight` 与真实集合差逐一对照；
   同名不同 ID 的任务不会被合并（测试 `test_C_no_merging_by_name` 守着这一点）。
3. 赛季专属任务的判定方式：`presence[taskId] == {pvps}` → `seasonOnly=true`。
   上游一旦改名/合并任务 ID，这里会立刻反映为集合变化，而不是静默沿用旧标记。
4. 赛季结束后：本地进度保留历史记录，但界面明确提示「不要拿旧赛季完成状态当新赛季进度」；
   新赛季若换了任务 ID，旧记录会自然失效（不匹配任何任务），不会被误算成新赛季已完成。

### 补赛季专属任务的正确姿势

- 只从 `https://json.tarkov.dev/pvp-season/tasks` 取；不要手工往 `tasks.pvps.json` 里加任务。
- 若上游迟迟不下发，但社区有可靠来源：把来源写进 `data/tasks/sources.json`，
  在 `data/tasks/curated-guides.json` 里补攻略文本，**不要**伪造目标/前置/奖励字段。
- 判断是否"真的赛季专属"：该 ID 只出现在 pvps 集合里。仅名称带"赛季"字样不算证据。

---

## 五、截图清单（`shots/`）

| 文件 | 内容 |
|---|---|
| `01-mode-switch.png` | 任务树 + 右上角 PvP / PvE / PvPS（赛季服）三按钮 + 模式说明条 |
| `02-pvp-tree.png` | PvP 任务树（503 节点 / 257 条边） |
| `03-pve-tree.png` | PvE 任务树（499 节点 / 256 条边） |
| `04-pvps-tree.png` | PvPS 赛季服任务树（462 节点 / 197 条边） |
| `05-traders.png` | 商人任务中心（含「模式」列） |
| `06-detail-completed.png` | 详情页（PvP，勾满目标后状态=已完成） |
| `07-mode-status-diff.png` | 同一任务在 PvPS 显示「未开始」（PvP 已完成）→ 进度隔离 |
| `08-progress-isolation.png` | 我的进度：三模式对照表 |
| `09-pvps-season-note.png` | PvPS 模式的赛季周期与「无赛季专属任务」说明 |
| `10-i18n-detail.png` | 详情页中文化 + 原始英文名字段 + 当前模式/模式归属 |
| `reg-*.png` | 地图 / 配装 / 配枪 / 弹药 / 校准器回归截图 |
