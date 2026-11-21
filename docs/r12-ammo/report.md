# 第十二轮 · 弹药页面复刻报告

- 日期：2026-10-21
- 参考站：`https://db4tarkov.com/ammo`（Flutter Web / canvas，审计记录见 `reference/audit-notes.md`）
- 目标页面：本地离线项目 `ammo` 视图（顶栏「弹药」）
- 结论：**阶段 A 全部完成并通过验收**，随后进入阶段 B（枪械页面，另见 `docs/r13-gun/report.md`）

---

## 1. 测试基线

| 阶段 | 命令 | 结果 |
| --- | --- | --- |
| 任务开始 | `python -m pytest tests -q` | **691 passed, 1 skipped, 0 failed**（66.56s） |
| 本轮新增 | `python -m pytest tests/test_r12_ammo.py -q` | **14 passed**（0.69s） |
| 任务结束 | `python -m pytest tests -q` | **705 passed, 1 skipped, 0 failed**（50.05s） |

- 新增 14 项测试，全部通过；原有 691 项无删除、无跳过、无弱化。
- 1 项跳过为项目既有跳过项（非本轮引入）。

---

## 2. 交付内容

### 2.1 新增文件

| 文件 | 说明 |
| --- | --- |
| `data/ammo.json` | 构建期生成的弹药数据（200 条，schema 1，含审计块）；由 `tools/build_ammo.py` 产出 |
| `tools/build_ammo.py` | 从本地 `build-cache/items-regular.json`、`items_zh.json`、`data/items.json` 提取弹药与价格，构建期一次性生成，运行期不联网 |
| `tests/test_r12_ammo.py` | 14 项测试：数据完整性 / 弹道模型复算 / 页面接线静态结构 / 离线断言 |
| `docs/r12-ammo/**` | 参考审计、真实浏览器截图、本报告 |

### 2.2 修改文件

| 文件 | 改动 |
| --- | --- |
| `index.html` | 顶栏新增 `data-view="ammo"` 按钮；新增 `<section id="ammo-view">`（工具栏 / 筛选栏 / 表格 / 散点图容器 / 详情弹窗） |
| `app.js` | 新增弹药模块（约 8990–10030 行）：数据加载、筛选状态、列定义、弹道仿真、图表、详情弹窗、事件绑定；`VIEWS` 与 `panes` 加入 `ammo`；**未重写文件** |
| `style.css` | 新增 `.am-*` 作用域样式（2465–2828 行），全部限制在 `.am-workbench` / `.am-modal` 内，不触及地图与配装工作台 |
| `tools/config.py` | **关键修复**：`VIEWS` 白名单由 `("map","loadout","gun")` 扩为 `(..., "ammo")` |

> `tools/config.py` 的修复根因：`_normalize_ui` 会丢弃白名单外的 `view`，合并时旧值（`map`）保留，
> 配置广播（POST 回声 + ConfigWatcher 1s 轮询）会把刚切到的弹药视图切回去。
> 复现现象是「点击弹药后约 1.5 秒被切回地图」。加入 `ammo` 并重启服务后，刷新仍停在弹药视图。

未改动：地图渲染、地图标注、路线、定位、搜索、任务、图标库、枪械预设、人物装备预设、`data/items.json`、`data/gunslots.json`。

---

## 3. 数据审计

### 3.1 弹药来源与范围

- 来源：`data/items.json` 中 `pt == "Ammo"` 的条目，共 **200** 件，与 `data/ammo.json` 的 `ammo` 数组 **数量完全一致，无缺失、无重复**。
- 弹药类型分布：`bullet 180`、`buckshot 13`、`grenade 6`、`flashbang 1`。
- 口径 **31** 个，商人 **16** 个。
- 表格中**只有弹药**，不混入普通物品（测试 `test_r12_ammo.py` 断言 id 集合与 items.json 的 Ammo 子集相等）。

### 3.2 字段覆盖率（200 条为分母）

| 字段 | 覆盖 | 说明 |
| --- | --- | --- |
| `dmg` / `ard` / `pen` | 200 | 伤害 / 护甲伤害 / 穿透力 |
| `v0` / `bc` / `m` / `dia` | 200 | 初速 m/s / 弹道系数 / 质量 g / 口径 mm |
| `frag` / `ric` / `acc` / `rec` / `pc` | 200 | 碎裂 / 跳弹 / 精准度修正 / 后坐力修正 / 配件兼容标记 |
| `stack` / `base` / `w` | 200 | 堆叠 / 基础价 / 重量 |
| `sell` | 200 | 商人收购价 |
| `buy` | **154** | 商人买入报价；其余 46 件 `src` 为 `none`，界面显示「—」 |
| `flea` | **0** | 上游 `avg24hPrice` 全为 null，界面显示「—」并说明，**不按 0 处理** |
| `src` | 200 | `none 46` / `trader 154` / `barter 1` |

买入报价等级分布：LL1 59 / LL2 43 / LL3 27 / LL4 25。

`data/ammo.json` 的 `audit` 块显式记录了来源、数量、字段覆盖、以及 `unavailable.flea` 的处置方式，
避免后续维护者误以为是遗漏。

### 3.3 口径筹码映射

参考站 32 个口径筹码与本地的对应关系不能按口径名等值匹配：霰弹上游只有 `Caliber12g`，
参考站拆成 `12g Shot`（5 件，`t=buckshot`）与 `12g Slugs`（12 件，`t=bullet`）。

实现方式（`app.js` 的 `amChipMeta()` / `amChipHit()`）：

- chip 数据为 `{k, cal, atyp}`；
- `cal` 存在时按 `a.cal === cal` 匹配；
- `atyp === "buckshot"` 追加 `a.t === "buckshot"`；
- `atyp === "slug"` 追加 `a.t === "bullet"`。

测试断言 32 个 chip 恰好覆盖 200 行（互不重叠、无遗漏）。

---

## 4. 弹道模型与距离衰减

### 4.1 模型

实现在 `app.js` 的 `amSimulate()`，全部使用本地常数，不联网：

- **G1 阻力表**：48 个马赫数节点的阻力系数 `Cd(M)`，线性插值；
- **重力**：`g = 9.81 m/s²`，积分步长 `AM_DT = 0.01 s`，10 m 采样；
- **阻力加速度**：`k = m(kg) × AM_DRAG_C / bc / d(m)²`，`a_drag = k × Cd(v/343) × v`；
- **瞄具几何**：`AM_HOB = 0.06858 m`（瞄具轴线高于枪膛），`AM_ZERO = 50 m`，二分 32 次求归零角；
- **阻力标定系数**：`AM_DRAG_C = 0.0020766`（= 0.0014223 × 1.46）。

### 4.2 与参考站实测表的偏差

用 `docs/r12-ammo/reference/lrnpc-reference-table.json`（LRNPC，`v0=385`、`bc=0.119`、`m=7.2`、`dia=7.85`、`pen=7`、`dmg=66`，51 行）复算核对：

| 指标 | MAE | 最大偏差 |
| --- | --- | --- |
| 弹速 speed | 7.032 m/s | 23.446 m/s |
| 下沉 drop | 4.487 cm | 17.243 cm |
| 飞行时间 tof | 0.0094 s | 0.030 s |

关键点吻合：0 m `drop = -6.858 cm`、50 m `drop ≈ 0`。

**非线性证据**：400 m 时本地模型下沉 `-820.9 cm`，若按 0 m 与 50 m 两点线性外推则为 `-1207.7 cm`，
相差 386.8 cm。曲线不是线性下降，也不是用别的弹药替代的结果。

以上复算逻辑已固化为 `tests/test_r12_ammo.py` 中的 Python 等价实现（从 `app.js` 正则提取真实常数），
断言阈值即上表数值，防止后续改动无声破坏模型。

### 4.3 距离变化的穿透 / 伤害

- 速度衰减因子：`amFactor = 0.5 + 0.5 × v / v0`；
- `DROP pen dmg` 页签在 0/100/…/500 m 各列显示 `round(pen × factor)` 与 `round(dmg × factor)`；
- 穿透概率（C1–C6）：`p = clamp((pen − 0.4 × AV) / (0.8 × AV), 0, 1)`，`AV = 等级 × 10`；
  单元格显示百分比并在 tooltip 写明 AV 与概率。

**未伪造项**：参考站的 0–6 色块评级口径无法从页面确认，本地不使用该评级，改写为概率百分比（已知差异，见第 7 节）。

---

## 5. 页面功能实现

### 5.1 视图与路由

- 复用现有顶栏 `#view-switch`，新增 `弹药` 按钮；`VIEWS`（前端）/ `config.py`（后端白名单）同步加入 `ammo`。
- 切换后写入 `ui.view` 并通过现有 `queuePrefs` → `/api/prefs` 持久化，刷新后停留在弹药视图（**已实测**）。
- 无独立路由系统、无 History API 改造。

### 5.2 四个页签

| 页签 | 内容 |
| --- | --- |
| `BALLISTICS` | **21 列**总表：Caliber / 图标 / Name / Market / Trader / Craft / Barter / Pen / Dmg / ArD / Acc / Recoil / Frag / Speed / Ricochet / C1–C6 |
| `DROP pen dmg` | 距离列 0–500 m（每 100 m），每格上下两行显示穿透 / 伤害 |
| `DROP bullet 3m` | Speed + 0–500 m 下沉值 + 每行迷你曲线 sparkline |
| `BALLISTICS graph` | 散点图：横轴伤害、纵轴可稳定穿透等级；200 个点，图例按等级计数 |

### 5.3 搜索 / 筛选 / 排序

- 搜索：名称、口径、类型（`amRows()` 与表格 `searchKeys` 同语义，保证计数与表格行数一致）。
- 筛选：右侧 5 组 32 个口径筹码 + `RESET`；PEN / DMG / SPEED 区间；RANGE 100/300/500。
- 排序：全部数值列可排序，表头箭头指示方向。
- 计数：`显示数 / 200 件`，随搜索与筛选实时更新。

### 5.4 详情弹窗

- 点击任意行打开居中弹窗，不跳转独立页面；
- 内容：17 项属性（口径、类型、伤害、穿透、护甲伤害、初速、BC、质量、直径、碎裂、跳弹、精准、后坐、堆叠、基础价、商人报价、跳蚤市场），缺失项显示「—」；
- 左侧 **Drop 面积图**（0–500 m，纵轴 0 ~ -250 cm，超出裁切），右侧 **51 行距离表**（`m / Pen / Dmg / Speed / Drop / TOF`，每 10 m 一行）；
- 关闭：右上角 × 或 Esc；关闭后列表筛选与滚动状态保持；
- 切换：关闭后点击另一行，标题、属性、51 行表与曲线全部切换（已实测 AP → CBJ：Pen 48→43、初速 635→725）。

---

## 6. 真实浏览器验收（Chrome CDP，1920×1080）

| # | 操作 | 实测结果 | 截图 |
| --- | --- | --- | --- |
| 1 | 切到弹药视图 | 200 行、21 列、5 组 32 筹码；`200 / 200 件`；表格 1652×746；筛选栏 252 px | `shot-list-1920.png` |
| 2 | 搜索 `M995` | 2 行 | `shot-search-M995.png` |
| 3 | 搜索 `BS` | 3 行，计数 `3 / 200 件` | `shot-search-BS.png` |
| 4 | 点选 `5.45x39` 口径 | 13 行，chip 高亮 | `shot-filter-545.png` |
| 5 | 点选 `12g Shot` | 5 行（霰弹 buckshot） | `shot-filter-12g-shot.png` |
| 6 | 点 `Pen` 降序 | 62 → 9 | `shot-sort-pen.png` |
| 7 | 再点 `Pen` 升序 | 9 → 62 | `shot-sort-pen-asc.png` |
| 8 | 点开 5.45 HP 详情 | 弹窗打开，属性 + 51 行表 + Drop 图 | `shot-detail-545HP.png` |
| 9 | 切换 300 AP | 字段与曲线变化 | `shot-detail-300AP.png` |
| 10 | `DROP pen dmg` | 6 个距离列，双层数值 | `shot-tab-drop-pen-dmg.png` |
| 11 | `DROP bullet 3m` | Speed + 下沉 + sparkline | `shot-tab-drop-bullet.png` |
| 12 | `BALLISTICS graph` | 散点 200 点 + 图例 | `shot-tab-graph.png` |
| 13 | 关闭弹窗 / Esc | 列表可继续操作 | — |
| 14 | 刷新页面 | 仍停在弹药视图，列表与功能正常 | `shot-after-refresh.png` |

### 离线核验

`performance.getEntriesByType('resource')` 全部 250 项均指向 `127.0.0.1:8787`，
筛选外部域名结果为 `[]`。页面、数据、图标、曲线均由本地服务提供。

---

## 7. 已知差异与处理（不伪造）

| 项 | 参考站 | 本地 | 处理 |
| --- | --- | --- | --- |
| Market 价格 | 多数弹药显示跳蚤价 | 全部「—」 | 上游 `avg24hPrice` 为 null，审计块写明「不得按 0」 |
| C1–C6 | 0–6 色块评级 | 穿透概率 % | 评级阈值口径无法确认，改用可复算概率并在 tooltip 说明 |
| Craft | 部分显示制作来源 | 「—」 | 本地无 craft 数据记录 |
| Barter | 具体交换项 | 仅有/无标记 | 交换项未收录，不编造价格 |
| 行底色 | 按口径整行染色 | 口径列色条 + 分组排序 | 视觉差异，不影响功能 |
| 散点图 | 含点名与虚线基准 | 仅散点 + 图例计数 | 未获知参考基准线取值，不臆造 |

---

## 8. 阶段 A 完成门槛核验（A6）

| 门槛 | 状态 | 证据 |
| --- | --- | --- |
| 页面结构已对照原网站 | 通过 | `reference/audit-notes.md` + `ref-ammo-*.png` |
| 列表覆盖审计后的全部本地弹药 | 通过 | 200 = `items.json` Ammo 子集 200，测试断言 |
| 详情弹窗可实际打开与关闭 | 通过 | 第 6 节 #8–#13 + 截图 |
| 弹道与距离衰减有真实数据支撑 | 通过 | 第 4 节标定 + 复算测试 |
| 无伪造曲线、缺失字段、虚构价格 | 通过 | 第 7 节逐项登记 |
| 搜索 / 筛选 / 排序通过测试 | 通过 | `tests/test_r12_ammo.py` |
| 真实浏览器交互通过 | 通过 | 第 6 节 14 项 |
| 完整测试套件通过 | 通过 | 705 passed / 1 skipped |
| 截图与测试结果已归档 | 通过 | `docs/r12-ammo/` |
