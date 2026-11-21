# R19.22 交付报告｜任务系统 + 全项目中文化

- 构建标记：`AM_BUILD = "R19.22"`；服务端 `rev` 形如 `R19.22-xxxxxxxx`（`/api/build` 可核验）
- 全量测试：**1214 passed / 1 skipped / 0 failed**
- 浏览器验收：**30 / 30 通过**（`tools/r1930_accept.py`，真实 Chrome + CDP，非静态检查）
- 任务数据：**PvP 503 个任务 / PvE 499 个任务**，目标 **1416 / 1384** 条，依赖边 **222 / 221** 条
- 中文化：界面扫描 **26 232** 个文本/属性节点，唯一英文 **685** 条 → 换成中文 **57**、原文浮窗 **503**、合理保留 **125**、**未覆盖 0**

---

## 第一部分：任务系统

### 1.1 数据来源与日期

| 项 | 内容 |
|---|---|
| 结构数据 | `https://json.tarkov.dev/{regular,pve}/tasks`（tarkov.dev 社区公开数据，非官方） |
| 中文翻译 | `https://json.tarkov.dev/{regular,pve}/tasks_zh`（扁平字典，键 = 英文占位串） |
| 商人 | `{regular}/traders` + `traders_zh` |
| 地图名 | 本地 `data/maps.json` 优先，缺失的新图用 `{regular}/maps_zh` 补齐 |
| 抓取时间 | 2026-10-28（`data/tasks/sources.json` 记录每个端点的 URL / sha256 / 字节数 / 抓取时间） |
| 离线 | 原始快照在 `data/tasks/raw/`，标准化产物在 `data/tasks/*.json`；页面只读本地文件，断网可用 |

> 说明：`api.tarkov.dev/graphql` 当天返回 `GraphQL server unavailable`，因此走静态 JSON（与项目既有 `tools/fetch_data.py` 同源同许可）。上游 `tasks` 的 `name` 字段是占位串 `<id> name`，英文 locale 表（`tasks_en`）**全为空**——英文原名只能从项目既有 `data/items.json` 的 `tasks` 表取到 125 条，其余 378 条用 wiki 链接 slug 还原（`englishSource` 字段标明来源）。

### 1.2 收录规模与商人分布（PvP）

| 商人 | 任务数 | 商人 | 任务数 |
|---|---|---|---|
| 机械师 | 72 | 和平卫士 | 51 |
| 滑雪 | 67 | 裁判 | 20 |
| 大老板 | 66 | BTR 驾驶员 | 19 |
| 猎人 | 64 | 篱笆 | 16 |
| 拉格曼 | 61 | 灯塔看守 | 14 |
| 医生 | 53 | | |

合计 11 位商人在发任务（`data/tasks/traders.json` 收录全部 16 位，含暂未发任务的）。

### 1.3 依赖关系与复杂条件覆盖

| 指标 | PvP | PvE |
|---|---|---|
| 任务 | 503 | 499 |
| 任务目标 | 1416 | 1384 |
| 有前置的任务 | 203 | 202 |
| 前置边（AND） | 222 | 221 |
| 其中「多状态 OR」边 | 13 | 10 |
| 失败条件条目 | 35 | 35 |
| 带可定位区域的任务 | 185 | 185 |
| 目标区域（矩形/多边形） | 431 | 429 |
| 有物品奖励的任务 | 479 | 475 |
| Kappa 必需 | 13 | 13 |
| 阵营限定（BEAR/USEC） | 34 | 34 |

- **AND / OR / 失败分支都保留原始语义**：`prerequisites[].logic`（`all` / `or`）、`statuses[]`（`complete` / `fail` / `active`）、`failedConditions[]` 分别建模，画线时 OR 用虚线箭头，详情页显式标注「需全部满足」或「满足其一（OR）」。
- **非任务型条件单独建模**（`conditions[]`）：角色等级、商人忠诚等级、商人声望、阵营、技能等级、对话、剧情变量（`globalVariable` 168 条）——不会画成任务节点。
- 上游未提供「主线 / 剧情」标记（`taskType`、`isStoryTask` 都不存在），因此**没有做「主线」筛选项**（避免永远筛不到东西的假开关），只保留 Kappa / 灯塔 / 阵营三个有数据支撑的筛选项。

### 1.4 三个页面

| 页面 | 已实现 |
|---|---|
| **A 全局任务树** | 503 节点全量渲染、222 条真实前置边；拖拽平移、滚轮缩放（0.12–2.6 倍）、放大/缩小/适配全图/重置；中文搜索（任务名/英文名/ID）回车逐个定位；11 类筛选（商人/状态/地图/等级区间/特殊/隐藏已完成/隐藏暂不可接/仅显示筛选结果）；选中节点高亮直接前置（蓝）与后续（绿）；「展开前置链」「展开后续链」；双击进详情；图例（状态用图标+颜色双重表达，不只靠颜色） |
| **B 商人任务中心** | 11 张商人卡片（图标/中文名/任务数/已完成/进行中/可接取/完成率进度条）；任务表（名称/状态/等级/地图/前置数/目标数/后续数/详情）；搜索+状态+地图+等级+特殊筛选；4 种排序；按商人过滤；**任务链**按真实依赖提取（只在「一对一」关系上连链，遇分叉即断开，跨商人前置用 ↗ 标记并附 tooltip） |
| **C 任务详情与攻略** | 基本信息（ID / 原始英文名 / 商人 / 地图 / 阵营 / Kappa / 灯塔 / 可重接 / 经验 / 来源）；前置任务（带状态与 AND/OR 标注，可跳转）；非任务型条件（分类标签）；阻塞原因与「无法自动判定」分开列；**可勾选目标**（勾选即存，必需目标全勾自动完成）；详细攻略（概述/准备/路线/步骤/注意事项/完成后操作/同图并行）；地图定位（目标区域列表 + 「在地图定位」）；后续任务（含额外等级要求）；奖励（经验/声望/物品/报价解锁/商人解锁/成就）；数据来源与核验状态 |
| **D 我的进度**（附加） | 可填「我的等级」用于判可接取；进行中 / 当前可接取 / 暂不可接（附阻塞原因）/ 同图可并行 / 已完成待看后续 / 已失败；导出、导入、清空本模式；进度条与统计卡 |

### 1.5 攻略覆盖率

| 项 | 数值 |
|---|---|
| 有结构化攻略 | **503 / 503**（PvE 499 / 499） |
| 其中「数据派生」`generated` | 503 |
| 其中「人工整理」`curated` | **0** |
| 攻略缺失 `missing` | 0 |
| 含「注意事项」的攻略 | 309 |
| 每份攻略都记录来源 | 是（`guide.source` = tarkov.dev 任务数据派生） |

**必须如实说明**：本轮攻略是**从上游真实字段派生**的结构化文本（目标原文、地图、区域 id、物品与数量、FIR/装备/时间窗/钥匙等限制、奖励、并行建议），**没有逐条人工撰写与游戏内核对**。详情页对此明确标注「攻略由任务数据派生（供参考，待人工复核）」，不会伪装成已完成校对。人工补写的入口已预留：`data/tasks/curated-guides.json`（格式见第四部分），加入后对应任务会自动升级为 `curated` 并保留数据派生的注意事项。

### 1.6 缺失、冲突与待确认清单

1. **英文原名来源**：125 条来自 `items.json`（真实英文名），378 条来自 wiki slug（如 `First in Line`）——上游英文 locale 为空，不是本项目遗漏；浮窗里同时给出任务 ID 便于核对。
2. **未收录的两张地图**：「中心区 21+」（`65b8d6f5…`）与「夜间工厂」（`59fc81d7…`）本地底图没有，任务目标定位时会明确提示「本图未收录，位置待核实」，不会假装跳转成功。
3. **同名不同 ID 共 9 组**（如「猎人之路 - 管理者」「塔科夫神射手 - 5」），校验脚本已列出，界面按 ID 区分，未合并。
4. **「主线」属性缺失**：见 1.3，未做该筛选。
5. **攻略未人工校对**：见 1.5。
6. 任务 `taskType` 上游无字段，一律按「常规任务」显示，不臆造主线/支线分类。

### 1.7 实际运行截图

`docs/r19.22-tasks-i18n/screenshots/`：

| 文件 | 内容 |
|---|---|
| `01-task-tree.png` | 全局任务树（503 节点，含图例与筛选条） |
| `02-tree-selected.png` | 选中节点后的侧栏摘要 + 前置/后续高亮 |
| `03-task-detail.png` | 任务详情（基本信息 / 前置 / 条件 / 目标 / 攻略） |
| `04-traders.png` | 商人任务中心（卡片 + 表格 + 任务链） |
| `05-progress.png` | 我的进度（统计卡 + 分组列表） |
| `06-pve-tree.png` | 切到 PvE 后的独立任务树（499 节点） |
| `07-map-pin.png` | 从详情跳转地图并在海关底图上钉出目标点（中文地名） |

---

## 第二部分：全项目中文化

### 2.1 扫描的模块与规模

用真实浏览器逐视图采集（`tools/i18n_scan.py`：文本节点 + `title`/`placeholder`/`aria-label`/`alt`，跳过脚本/样式/隐藏元素）：

| 视图 / 页面 | 说明 |
|---|---|
| 主程序 · 地图 | 底图地名、图层、图例、搜索、左侧地图列表、状态栏 |
| 主程序 · 配装 | 表格、分类、价格档、属性面板、Final Cost 区 |
| 主程序 · 配枪 | 浏览列表、对比表、生成配装、槽位卡、属性 |
| 主程序 · 弹药 | 弹道表、筛选 chips、图表轴标签、详情弹窗 |
| 主程序 · 导航面板、战局与任务面板 | 菜单与提示 |
| 配枪 · table / build / class | 三个子页 |
| 校准器（`?layoutCalibrator=1`） | 槽位卡、差异文本、工具条 |
| 任务 · 全局树 / 商人任务 / 详情 / 进度 | 本轮新增模块 |

采集结果：**26 232** 个文本/属性节点，其中纯英文 **1 266** 个；去重后**唯一英文文本 167 条 + 唯一英文属性 518 条 = 685 条**。

### 2.2 覆盖率统计

| 指标 | 数量 |
|---|---|
| 扫描到的英文用户可见文本/属性（去重） | **685** |
| 已建立中文映射并替换显示 | **57**（界面标签、表头、射击模式、地名等） |
| 配置原英文悬停提示（`title` + `data-en-text`） | **503**（任务名 / 商人名的原文浮窗） |
| 归属「合理保留英文」分类 | **125**（型号、口径、罗马数字、版本号、来源标识、槽位 ID、Boss 代号、PvP/PvE） |
| **尚无中文映射（缺口）** | **0** |
| 缺英文悬停提示的已翻译项 | **0**（`zh ≠ en` 时一律写入 `title`；中文与英文同形的不写空浮窗） |
| 无法自动判定是否用户可见 | 视为 0：全部由真实 DOM 文本节点判定，未依赖正则猜代码 |

字典规模（`data/i18n/`）：

| 文件 | 内容 | 条数 |
|---|---|---|
| `ui-zh.json` | 界面文字 en→zh + 2 条模式化规则（`PRESET · N`、`N KG`） | 336 |
| `poi-zh.json` | 地图地名（含撤离点） | **281**（数据里共 292 个英文地名，其余 11 个是 Boss 代号，明确保留） |
| `names.json` | 商人（中英/slug）、任务（英文原名→中文）、地图（id/key→中文）、槽位 id→中文 | 商人 37 / 任务 123 / 地图 26 / 槽位 41 |
| `items-zh.json` | 仍为英文的物品名（弹种为主，型号保留 + 弹种翻译） | 47 |
| `traders.json` | 商人中文名 + 备注（含 5 条待核对） | 16 |

### 2.3 机制（一套，不是每页一套）

`i18n.js`（显示层，原始数据一字不改）：

1. **中文优先**：`tr(text)` 精确匹配词表（含 POI 地名），命中即替换节点的 `nodeValue`，保留原有前后空白。
2. **原文浮窗**：被替换元素写入 `title=英文原文` + `data-en-text=英文原文`；元素已有功能提示（如「关闭（Esc）」）时**不覆盖**，原文以 ` · 原文` 追加。
3. **动态内容**：`MutationObserver`（childList + characterData）监听，`requestAnimationFrame` 合并批处理，表格重绘不会逐节点抖动；单点异常不影响其它节点。
4. **不误伤**：跳过 `script`/`style`（含 SVG 内联样式，比较前统一 `tagName.toUpperCase()`）、`data-i18n-skip` 标记；只处理「含拉丁字母且不含汉字」的文本，已有中文不重复翻译，不产生空浮窗。
5. **白名单**：`keptEnglish` 明确登记「不算缺口」的分类与具体词条（Boss 代号 11 个），与 `tools/build_i18n.py` 的判定规则一致。
6. **容错**：字典请求失败时退化为「原样显示」，不阻塞页面（`state.loadError` 只记录不抛出）。

数据驱动名称走同一张表：`GWI18n.nameZh("trader"|"task"|"map"|"item"|"slot", key)`；主程序里 `traderName()` / `taskName()` 已改为调用它，所以价格浮窗里的「任务解锁：XXX」与任务模块显示的是同一个中文名。

### 2.4 中文化前后对比（同一页面）

- **地图**：`docs/r19.22-tasks-i18n/screenshots/07-map-pin.png` —— 底图原本的 `Big Red / Dorms / New Gas / Old Gas / Fortress / Crackhouse / Warehouse 17 …` 现在显示「大红房 / 宿舍 / 新加油站 / 老加油站 / 堡垒 / 毒窝 / 17 号仓库」。
- **弹药**：`reg-ammo.png` —— 表头 `Caliber/Name/Market/Trader/Craft/Barter/Pen/Dmg/ArD/Acc/Recoil/Frag/Speed/Ricochet` → 「口径/名称/市场价/商人价/制作/兑换/穿透/伤害/护甲伤害/精度/后坐力/破片/速度/跳弹」；标签 `BALLISTICS / DROP pen dmg / DROP bullet 3m / BALLISTICS graph / RESET / SHOW` → 「弹道 / 穿透·伤害衰减 / 3 米弹道下沉 / 弹道曲线 / 重置 / 显示」。
- **配枪**：射击模式 `Auto / Single / Burst` → 「全自动 / 单发 / 三连发」；`GENERATE BUILDS / ⤓ LOAD VARIANT / Ergo` → 「生成配装 / ⤓ 载入变体 / 人机工效」；等级输入框占位 `min/max` → 「最小/最大」。
- **配装**：`Final Cost: / Buy / Sell / Kg / PRESET · 6 / FLEA / BASE` → 「总价：/ 买入 / 卖出 / 千克 / 预设 · 6 / 跳蚤 / 基础价」。
- **商人**：`Prapor / Therapist / Fence / Skier / Peacekeeper / Mechanic / Ragman / Jaeger / Lightkeeper / Ref / BTR Driver` → 「大老板 / 医生 / 篱笆 / 滑雪 / 和平卫士 / 机械师 / 拉格曼 / 猎人 / 灯塔看守 / 裁判 / BTR 驾驶员」（悬停显示英文原名）。
- **任务**：默认中文名；悬停显示「英文名 · 任务 ID」；详情页基本信息按任务书 7.2 显式列出「原始英文名」。

### 2.5 保留英文的合理例外（全部有分类与理由）

| 分类 | 例子 | 理由 |
|---|---|---|
| 口径 / 弹种型号 | `.45 ACP`、`.300 Blk`、`20x1mm`、`9x18PMM` | 翻译会失去辨识度，玩家按口径识别 |
| 武器型号 | `Kel-Tec RFB 7.62x51` | 同上 |
| 罗马数字等级 | `II`、`III`、`IV`、`IV · 1 545 ₽` | 商人忠诚等级与价格档的既有写法 |
| 版本号 | `rev R19.22-xxxxxxxx` | 构建核验标识 |
| 来源标识 | `tarkov-dev-svg-maps`、`the-hideout/tarkov-dev` | 地图 / 数据来源署名 |
| 槽位内部 ID | `mod_scope`、`mod_muzzle`、`mod_tactical_000`、物品 ID | 校准器必须按真实 ID 操作与核对 |
| Boss 代号 | `Reshala`、`Killa`、`Tagilla`、`Knight`、`The Wedge` 等 11 个 | 玩家按代号称呼 |
| 游戏模式专名 | `PvP`、`PvE`、`Scav` | 官方术语，中文社区同样使用 |

### 2.6 需要人工核对的翻译（已标注，不当作权威）

- 商人：**塔兰（Taran）**、**无线电台（Radio Station）**、**克尔曼先生（Mr. Kerman）**、**总督（Voevoda）**、**幸存者（Survivor）** —— 均为新商人，社区译名尚未统一（`data/i18n/traders.json` 的 `note` 字段标注「待核对」）。
- 部分街区地名音译：**马列维奇街（Malevecha St.）**、**契卡纳娅街（Chekannaya St.）**、**康科迪亚（Concordia）**、**莱克索斯酒店（Lexos）** 等，按俄语/英语发音直译，建议以游戏内中文或社区叫法为准。
- 立交桥商场品牌（`OLI / IDEA / Goshan / TECHLIGHT / Mantis …`）保留招牌名 + 中文类目（如「OLI 超市」），便于按招牌找店；如需全中文可只改 `poi-zh.json` 一处。

---

## 第三部分：测试结果

### 3.1 任务数据检查（`tools/validate_tasks.py`）

```
regular  tasks=503  objectives=1416  edges=222  or=13 guides=503/503
pve      tasks=499  objectives=1384  edges=221  or=10 guides=499/499
errors=0 warnings=0 -> OK
```

覆盖：ID 唯一、必需字段、前置/后续双向引用、OR 与失败条件保留、目标类型与中文描述、商人引用、攻略状态、模式隔离、重名清单（9 组，仅提示）。产物：`docs/r19.22-tasks-i18n/task-validation.json`。

### 3.2 专项测试（`tests/test_r19_22_round.py`，35 项）

| 组 | 项数 | 关键断言 |
|---|---|---|
| A 数据完整性 | 9 | 校验 0 错误、ID 唯一、引用双向一致、OR ≥ 10 且失败条件存在、目标全有中文与类型、两模式集合不同、攻略全覆盖、商人可解析、来源含 sha256 |
| B 任务树 | 5 | 模块注册（导航/容器/脚本/VIEWS/API）、边来自真实前置且有箭头、Kahn 分层 + 环兜底、浏览器 503 节点 222 边、缩放/平移/搜索/筛选 |
| C 详情 | 4 | 六区块齐全、勾选目标驱动状态、无编造坐标、英文名可作浮窗 |
| D 进度与离线 | 4 | 存储键与模式隔离、导入非法数据不破坏、刷新保留、本地数据与原始快照齐备 |
| E 中文化 | 6 | 未覆盖 0、字典规模（含 POI ≥ 250）、POI 表完整、引擎契约（title/MutationObserver/跳过脚本样式）、原始 ID 与中文名分离、术语一致、浮窗保留英文 |
| F 回归 | 5 | 四视图 + 校准器无错、校准数据未被动（152 枪 / 397 条）、构建标记同步、地图联动走 `worldToSvg`、校验脚本可重复执行 |

### 3.3 浏览器验收（`tools/r1930_accept.py`，30 项全过）

| 组 | 项 | 结果 |
|---|---|---|
| T1 任务树 | 节点 503 / 边 222 / 视图选中 / 状态栏统计 | ✅ |
| T2 交互 | 滚轮缩放改变相机、空白处拖拽平移 | ✅ |
| T3 搜索 | 中文关键词命中并居中 | ✅ |
| T4 筛选 | 商人筛选弱化非命中节点 | ✅ |
| T5 选中/进入 | 侧栏摘要、双击进详情 | ✅ |
| T6 详情 | 六区块、≥6 基本字段、攻略状态、勾选→进行中、必需全勾→自动完成 | ✅ |
| T7 商人页 | 卡片 + 表格 + 任务链、按商人过滤 | ✅ |
| T8 进度 | 统计卡 4 张 + 分组、导出 JSON 合法、非法导入不破坏 | ✅ |
| T9 持久化 | 刷新后状态保留 | ✅ |
| T10 模式隔离 | PvE 499 节点、进度与 PvP 互不影响 | ✅ |
| T11 地图联动 | 详情 → 地图视图、目标钉点出现 | ✅ |
| T12 中文化 | 未覆盖英文 0、字典与名称表就绪 | ✅ |
| T13 回归 | 地图/配装/配枪/弹药四视图可开且无脚本错误、校准器可用 | ✅ |

产物：`docs/r19.22-tasks-i18n/browser-accept.json`（含每项 detail 与来源视图）。

### 3.4 全量回归

```
1214 passed, 1 skipped, 0 failed
```

- 旧的「VIEWS 必须精确等于四个视图」断言按纪律**升级**为「四个既有视图必须在，且允许扩展」，不是删除；
- 任务模块所有 DOM 操作都做了空值判断，node 探针环境（无 `window`）里 `traderName()`/`taskName()`/`GWMapFocus` 均不抛错（`typeof window !== "undefined"` 守卫）；
- 校准数据 `data/gun-layout-calibration.json` 未被本轮触碰（152 枪 / 397 条，测试断言锁定）。

### 3.5 未能验证 / 未做的部分（如实记录）

1. **攻略未逐条人工校对**（0 条 curated）——上线标注为「数据派生，待复核」。
2. **两张地图未收录**，其任务目标只能提示「位置待核实」。
3. **英文原名 378 条来自 wiki slug**，不是官方英文名（上游英文 locale 为空）。
4. 任务树在「整图适配」时缩放到 0.2 倍左右，字会偏小——因此首次进入用 0.55 倍落在最左列，需要全局视图时点「适配全图」（这是取舍，不是 bug）。
5. 触屏手势未做（桌面项目；触屏下中文仍完整可读，只是没有双指缩放）。

---

## 第四部分：后续维护说明

### 4.1 刷新任务数据（联网时）

```bash
python tools/fetch_tasks.py              # 走 http://127.0.0.1:7896 代理抓取并标准化
python tools/validate_tasks.py           # 必须 errors=0
python tools/build_i18n.py               # 重建名称表 + 覆盖率报告
```

- 只重建不联网：`python tools/fetch_tasks.py --offline`（用 `data/tasks/raw/` 快照）。
- 产出：`data/tasks/tasks.{regular,pve}.json`、`guides.{…}.json`、`traders.json`、`index.json`、`sources.json`。
- 刷新后要做三件事：
  1. 看 `docs/r19.22-tasks-i18n/task-validation.json` 的 `warnings`（新任务中文名缺失会以「（未翻译）」暴露）；
  2. 跑 `tools/build_i18n.py`，`未覆盖` 必须为 0（新英文界面文字会在这里报出来）；
  3. 如果新增了**地图 POI**，`python tools/build_poi_zh.py` 会直接列出缺译地名（`MISSING:`），补进脚本里的 `ZH` 表即可。

### 4.2 补充 / 校对任务攻略

新建或编辑 `data/tasks/curated-guides.json`（键 = 任务 ID）：

```json
{
  "597a0b2986f77426d66c35a4": {
    "source": "https://escapefromtarkov.fandom.com/wiki/Chemical_-_Part_2（2026-10 核对）",
    "notes": [
      "三处化学品位置在宿舍 3 楼与 2 号楼，建议带 2 个 4 格容器",
      "交任务前不要把化学品放进安全箱以外的地方"
    ]
  }
}
```

重新 `python tools/fetch_tasks.py --offline` 后，该任务的 `guide.status` 自动变成 `curated`，`notes` 会与数据派生的注意事项合并（去重），详情页标签变「攻略已人工整理」。

### 4.3 新增商人 / 地图

- **商人**：`data/i18n/traders.json` 增加 `{ normalizedName: { nameEn, nameZh, note } }` → 重新 `fetch_tasks.py`，`traders.json`、`names.json` 会带上中文名与本地图标路径（图标缺省用 `unknown.svg`）。
- **地图**：仍走既有 `tools/fetch_data.py`；任务侧只认 `data/maps.json` 的 `id` 与 `worldToSvg`。新图未收录时任务定位会提示「本图未收录」，不会乱跳。

### 4.4 补充中文翻译

| 要翻译的东西 | 改哪里 | 校验 |
|---|---|---|
| 界面标签 / 表头 / 按钮 | `data/i18n/ui-zh.json` 的 `entries` | `python tools/build_i18n.py`（未覆盖为 0） |
| 带数字的模式化文案 | 同上 `patterns`（正则 + `$1` 占位） | 同上 |
| 地图地名 / 撤离点 | `tools/build_poi_zh.py` 的 `ZH` 表 | `python tools/build_poi_zh.py --check` |
| 物品英文名（弹种等） | `tools/build_i18n.py` 的 `PROJECTILE` / `ITEM_OVERRIDES` | 同上 |
| 商人 | `data/i18n/traders.json` | `tests/test_r19_22_round.py::test_E_terms_consistent` |

**翻译规则**：只改显示层，**不改** `data/items.json`、`data/gunslots.json`、任务数据里的 id / 字段名；中文名与英文原名分开存（`nameZh` / `englishName` / `title`）。

### 4.5 检查新增文字是否都有中文与英文浮窗

```bash
python tools/i18n_scan.py     # 真实浏览器逐视图扫描 → docs/r19.22-tasks-i18n/i18n-inventory.json
python tools/build_i18n.py    # 覆盖率：mapped / originalTooltip / kept / missing
python -m pytest tests/test_r19_22_round.py -q
```

判定口径（三选一，缺一即报 missing）：

1. 在 `ui-zh.json` / `poi-zh.json` 里有中文映射；
2. 是我们自己写入的原文浮窗（形如 `English Name · <24 位任务 ID>`）；
3. 命中白名单（型号/口径/罗马数字/版本号/来源/槽位 ID/Boss 代号/PvP·PvE），白名单条目必须写明分类。

### 4.6 验证新数据不会破坏旧进度

- 任务进度按 **任务 ID** 存在 `localStorage["eftmap.tasks.progress.v1"]`，与任务数据文件分离；刷新数据不清进度（只有「清空本模式进度」会清）。
- 导入格式：`{ schema: 1, kind: "eftmap-task-progress", modes: { regular: {...}, pve: {...} } }`；导入前全量校验，任何一步失败都**不落盘**。
- 数据更新后，已被删除的任务 ID 仍保留在进度里（下次导出仍在），不会把进度错配到同名新任务上——因为键是 ID 而不是名称。
- 回归检查：`python -m pytest -q`（当前 1214 passed / 1 skipped）。

### 4.7 本轮改动的文件清单

| 文件 | 作用 |
|---|---|
| `tasks.js`（新增） | 任务模块：任务树 / 商人中心 / 详情 / 进度，约 1 400 行 |
| `tasks.css`（新增） | 任务模块样式（沿用 XP 令牌） |
| `i18n.js`（新增） | 全项目中文显示层（词表 + 原文浮窗 + MutationObserver + 覆盖率） |
| `data/tasks/*`（新增） | `tasks.{regular,pve}.json`、`guides.…`、`traders.json`、`sources.json`、`index.json`、`raw/` 快照 |
| `data/i18n/*`（新增） | `ui-zh.json`、`poi-zh.json`、`names.json`、`items-zh.json`、`traders.json` |
| `tools/fetch_tasks.py`（新增） | 任务数据抓取 + 标准化 + 攻略派生 |
| `tools/validate_tasks.py`（新增） | 数据完整性校验 |
| `tools/build_i18n.py`（新增） | 名称表生成 + 覆盖率报告 |
| `tools/build_poi_zh.py`（新增） | 地图 POI 译名表生成与完整性检查 |
| `tools/i18n_scan.py`（新增） | 真实浏览器文字盘点 |
| `tools/r1930_accept.py`（新增） | 浏览器验收（30 项） |
| `tests/test_r19_22_round.py`（新增） | 专项测试（35 项） |
| `index.html` | 新增「任务」导航与 `#task-view` 容器，引入 `tasks.css/js`、`i18n.js`，版本号 → `r19.22` |
| `app.js` | `VIEWS` 增 `tasks`、`el.taskView`、`setView` 挂载任务模块、`traderName()/taskName()` 走中文名表、新增 `GWMapFocus` 地图联动与任务钉点、`#tasks` 深链、`AM_BUILD=R19.22`、占位符中文 |
| `tools/serve.py` | `rev` → `R19.22-<digest>` |
| `tests/test_r12_ammo.py` | VIEWS 断言升级（允许扩展，四个既有视图必须在） |
