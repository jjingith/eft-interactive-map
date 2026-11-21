# db4tarkov.com 功能清单（R20 第一阶段 3.3）

> 站点：`https://db4tarkov.com/`（Database for Tarkov，v2026.10.28-0，游戏版本标记 1.2.0.0）
> 取证方式：真实 Chrome 逐页进入 + 截图 + Flutter 语义树标签 + 网络请求统计（脚本 `tools/r20_site_probe.py`）
> 结论口径：**已核实**＝本次实测；**观察推断**＝从界面/请求推断未逐项验证；**未知**＝未验证

## 0. 站点技术事实（影响一切结论）

| 事实 | 证据 | 影响 |
|---|---|---|
| **Flutter Web（CanvasKit）渲染** | DOM 含 `FLUTTER-VIEW`/`FLT-CANVAS-CONTAINER`/`CANVAS`，`innerText` 常为 0 | 无法用 DOM 解析取数据；只能截图/语义树 |
| 单页应用，路由为 `/gun` `/market` … | 直接访问 URL 可用，但每次导航都重新初始化并**重新下载数据** | 逐页审计代价高（每页 30–45s） |
| **首次进入需下载数据** | 首屏显示 “caching data / first visit — downloading app assets”；`localStorage` 有 `GetStorage`、`_web_ver` | 属 PWA 形态，有本地缓存 |
| 后端 = Firebase + Supabase + 自有 CDN | `firebase*.googleapis.com`、`*.supabase.co`(gacxmpsnkkizmzmcimlh)、`eft-cdn.dvcstudiox.workers.dev`、`eft-assets.dvcstudiox.workers.dev`、`cdn.db4tarkov.com` | 数据在远端；**有 Firebase App Check 反滥用** |
| 亦消费 tarkov.dev 公开数据 | `/season` 页请求到 `json.tarkov.dev` | 部分数据非自有 |
| 存在外部字体依赖 | `fonts.gstatic.com` / `www.gstatic.com` | 说明它自己也没完全离线 |
| 账号体系 | `accounts.google.com`、右侧 “Login to save your progress” | **浏览免费，登录只为保存进度** |

---

## 1. 一级栏目总览（语义树实测，顺序即导航顺序）

`MARKET(SEASON 角标) · SEASON Kord · QUEST · KEEP · GUN · PRESET · AMMO · MAP · BARTER · CRAFT · CHANGES 1.2.0.0 · LOGS`

右上通用控件：`Game Mode: Kord Breach (Season 1) ends in 38 day(s)`、`PvE / PvP / SS(38d)` 三模式切换、`Change Site Resolution`、`Change Language`、`About Me`、`Discord Server`、`Login to save your progress`。

> **重要**：`PvE / PvP / SS(Season)` 是全局数据域切换——与现有项目 `regular/pve/pvps` 三模式隔离的设计**同构**，可直接对齐。

---

## 2. 逐栏目功能清单

### 2.1 MARKET（跳蚤市场行情）

| 项 | 内容 |
|---|---|
| 页面 | `/market`（截图 `db4-market45.png`） |
| 目的 | 物品价格行情总览与检索 |
| 布局 | 顶部搜索框 + 价格口径切换（`Last Price / Avg 24h / Avg 7d`）+ 数据源开关（`MARKET / TRADER / CRAFT / BARTER`）+ 表格 |
| 用户输入 | 搜索、价格口径、数据源、Trader 等级限制（`onlyTraderLvl`） |
| 输出 | 物品价格表（含多口径价格、涨跌） |
| 数据证据 | 页面文案 `Type to search — ESC to clear`、`Last Price`、`Avg 24h`；请求走自有 CDN/Firebase |
| 需登录 | 否（登录仅保存） |
| 依赖实时 | **强依赖**（跳蚤价格本身是实时/近实时数据） |
| 本地重建 | 可重建 UI 与查询；**数据只能做历史快照**，必须标注「非实时」 |
| 与现有重叠 | 低（现有仅物品 `cost` 静态价，无行情表） |
| 难度/风险 | 中；**风险：把历史快照当实时价格展示** |

### 2.2 SEASON（赛季/Kord Breach）

| 项 | 内容 |
|---|---|
| 页面 | `/season`（截图 `db4-season.png`） |
| 目的 | 赛季规则、限时机制说明 |
| 布局 | 卡片式规则列表 |
| 输出 | 规则条目，如 `NO INSURANCE / BLACK DIVISION / NO FIR FOR HIDEOUT` |
| 数据证据 | 语义标签直接给出上述条目；请求含 `json.tarkov.dev` |
| 本地重建 | 可（纯文案 + 少量参数） |
| 与现有重叠 | 无 |
| 难度/风险 | 低；**风险：赛季文案随版本变化**，需版本化 |

### 2.3 QUEST（任务）

| 项 | 内容 |
|---|---|
| 页面 | `/quest`（截图 `db4-quest.png`，92 个按钮 / 149 个语义标签） |
| 目的 | 任务清单与任务详情 |
| 布局 | 左侧任务树/列表 + 右侧详情；`IV`、`+0`、`Trader level / PMC Setting` 等筛选 |
| 用户输入 | 商人/等级/地图筛选、搜索 |
| 输出 | 任务目标、奖励、前置、地图点 |
| 数据证据 | 页面语义含 `Trader level / PMC Setting`；图标大量走 `cdn.db4tarkov.com`(42) |
| 本地重建 | **可**（现有 `data/tasks/*` 已有 3 模式任务数据） |
| 与现有重叠 | **高**——现有任务视图已含列表/前置/进度/路线 |
| 难度/风险 | 低-中；**主要风险是重复造轮子** |

### 2.4 KEEP（收集/藏身处）

| 项 | 内容 |
|---|---|
| 页面 | `/keep`（截图 `db4-keep.png`，168 语义标签，371 张图） |
| 目的 | 需要保留（`Items / Collected / Keys`）的物品清单，服务藏身处与任务 |
| 布局 | 三标签页 + 物品网格 + 收集状态 |
| 用户输入 | 标签切换、勾选已收集 |
| 输出 | 「要留什么」清单 |
| 数据证据 | 语义标签 `Items | Collected | Keys` |
| 需登录 | 勾选状态若保存需登录（文案 “Login to save your progress”） |
| 本地重建 | **可**（本地勾选 + 现有 items 数据） |
| 与现有重叠 | **中**——现有有「任务所需物品」类聚合，但没有「待收集清单」视图 |
| 难度/风险 | 低 |

### 2.5 GUN（枪械浏览与构建入口）

| 项 | 内容 |
|---|---|
| 页面 | `/gun`（截图 `db4-gun.png`） |
| 目的 | 按口径浏览全部枪械，进入单枪构建 |
| 布局 | 顶部二级标签 `Caliber / Class / Table / Gun`；筛选 `Primary / Handgun / Caliber Filter`；射击模式 `Auto / Single / Burst / Shoot / Loud`；`Gunsmith / TierMaker / Streamer / Variant / Saved` 五个视图；**按口径分行的枪械卡片网格**（.300 / 5.8x42 / 5.56x45 / 5.45x39 / 6.8x51 / 7.62x39 / 7.62x51 / 7.62x54R / .308 / .338 / 7.62x25） |
| 用户输入 | 口径/类别筛选、搜索、视图切换 |
| 输出 | 枪械卡片（含槽位数徽标、估价） |
| 数据证据 | 卡片文案形如 `600 3.50 Velociraptor`（价格 + 某指标 + 名称）；97 张图来自 `cdn.db4tarkov.com` |
| 本地重建 | **可**（现有 `gun_builder` + `gunslots` 已覆盖 163 把） |
| 与现有重叠 | **高** |
| 难度/风险 | 低；`Gunsmith / TierMaker / Streamer / Variant / Saved` 是**视图维度**，现有只有单一画布 |

### 2.6 PRESET（装备配装）

| 项 | 内容 |
|---|---|
| 页面 | `/preset`（截图 `db4-preset.png`） |
| 目的 | 纸娃娃式装备搭配 + 成本汇总 |
| 布局 | 左：`Move / Turn / Ergo 0/0/0`、`Kg 0/0` 汇总条 + 纸娃娃槽位（`Headwear`（带眼镜子槽）、`Face Cover`、`Headset`、`Armor`、`Armored Rig`、`Chest Rig`、`Gun`、`Backpack`）+ 底部 `Final Cost: [Buy()] [Sell]`；右：`Choose gear` 选择面板 |
| 用户输入 | 逐槽选装、Buy/Sell 口径 |
| 输出 | 属性汇总（移动/转向/人机/重量）+ 买/卖总价 |
| 数据证据 | 语义标签实测到上述槽位名与 `Final Cost:` |
| 本地重建 | **可**（现有配装工作台已有纸娃娃 + 插板 + 属性汇总） |
| 与现有重叠 | **高**（现有更细：插板/内衬/防护区域） |
| 难度/风险 | 低；**可借鉴点是 Buy/Sell 双口径成本** |

### 2.7 AMMO（弹道表）

| 项 | 内容 |
|---|---|
| 页面 | `/ammo`（标题 `Ballistic`，截图 `db4-ammo.png`） |
| 目的 | 全弹药横向对比 |
| 布局 | 极密表格：`Color / 图标 / Name / Market(价+量) / Trader / Pen / Dmg / 3m / 50m / 100m / 200m / 400m / 800m / 1..5（护甲等级矩阵）`；右侧筛选：`lastPrice / avg24h / avg7d`、`MARKET/TRADER/CRAFT/BARTER`、`onlyTraderLvl`、口径分组 `PISTOL/SMG` `RIFLE ROUNDS` `PDW` `SHOTGUN ROUNDS` `GRENADE LAUNCHER`、`FILTER/RESET` + `RANGE / PEN / DMG / SPEED` 滑杆 |
| 用户输入 | 列拖拽排序（`DROP pen dmg` / `DROP bullet 3m` 语义标签说明列可拖拽）、筛选、滑杆 |
| 输出 | 弹道对比矩阵（含距离衰减与穿甲等级矩阵） |
| 数据证据 | 语义 `BALLISTICS table`、`DROP pen dmg`、`DROP bullet 3m` |
| 本地重建 | **部分**：现有 `data/ammo.json` 89KB 有弹道基础值，但**距离衰减矩阵 / 护甲等级矩阵**需新增数据与算法 |
| 与现有重叠 | **中**（现有弹药视图有表 + 模拟，但无「按距离 × 护甲等级」矩阵） |
| 难度/风险 | 中-高；**数据缺口是主要风险**，不可凭推测补 |

### 2.8 MAP（互动地图 + Boss 刷新）

| 项 | 内容 |
|---|---|
| 页面 | `/map`（截图 `db4-map.png`） |
| 目的 | 地图标记与 Boss 刷新率 |
| 布局 | 地图画布 + 左侧标记/筛选；语义标签出现 `cultists Ground Zero 2% 40%`、`reshala Customs 60% 20% 25% 20%` —— **Boss 按地图的刷新概率矩阵** |
| 用户输入 | 地图切换、图层筛选 |
| 输出 | 标记点 + Boss 概率 |
| 数据证据 | 上述语义标签为实测；`supabase.co` 2 次请求出现在本页 |
| 本地重建 | **可**（现有 `data/maps.json` 2MB + 图层/路线已很强） |
| 与现有重叠 | **高**；**差异点 = Boss 刷新概率**（现有 `data/bosses.json` 需核对是否含概率） |
| 难度/风险 | 低 |

### 2.9 BARTER（商人交换）

| 项 | 内容 |
|---|---|
| 页面 | `/barter`（截图 `db4-barter.png`） |
| 目的 | 以物易物配方与「值不值」 |
| 布局 | 搜索 + `lastPrice / avg24h` 口径 + 配方列表 |
| 输出 | 交换配方（用什么换什么）+ 成本对比 |
| 数据证据 | 语义 `Type to search` `lastPrice` `avg24h` |
| 本地重建 | **数据缺失**：现有项目 `data/` 无 barter 配方表 |
| 与现有重叠 | 无 |
| 难度/风险 | 中；**需要新数据源**（tarkov.dev 公开数据可覆盖，需核对许可） |

### 2.10 CRAFT（藏身处制作）

| 项 | 内容 |
|---|---|
| 页面 | `/craft`（截图 `db4-craft.png`） |
| 目的 | 制作配方与利润 |
| 布局 | 同 barter 的搜索/口径 + 配方卡片（145 个按钮） |
| 本地重建 | **数据缺失**（现有无 craft 配方） |
| 与现有重叠 | 无 |
| 难度/风险 | 中 |

### 2.11 CHANGES（版本变更追踪）

| 项 | 内容 |
|---|---|
| 页面 | `/changes`（截图 `db4-changes.png`） |
| 目的 | 按游戏版本列出物品/属性变动 |
| 布局 | 版本选择 `1.2.0.0.47888 2026/10/07` + 分类计数（`34 NEW / OTHERS`）+ 变更列表 |
| 本地重建 | **可**（对本地 `data/` 做 diff 即可生成） |
| 与现有重叠 | 无（现有只有 `data/tasks/diff-report.json` 的任务差异） |
| 难度/风险 | 低；**这是「数据更新流程」天然的验收面** |

### 2.12 LOGS（本地日志解析）

| 项 | 内容 |
|---|---|
| 页面 | `/logs`（截图 `db4-logs.png`） |
| 目的 | 读取玩家本机 EFT 日志，统计战局（`OPS / LOG SCAV / READY / IDLE`） |
| 布局 | `SELECT LOGS FOLDER` 按钮 + `Log settings` + 状态标签 |
| 数据证据 | 语义标签实测；**无网络请求增加**（纯本地） |
| 本地重建 | **可且合规**：只读用户本机日志文件；但需要文件系统访问（浏览器需目录选择/File System Access API） |
| 与现有重叠 | 无 |
| 难度/风险 | 中；**风险：浏览器沙箱下目录访问受限**，且属「读用户私有数据」，需明确征得同意 |

---

## 3. 未覆盖项（诚实声明）

| 项 | 状态 |
|---|---|
| 单枪构建页（`/gun` 点进某把枪）的完整交互（选槽、装件、属性对比、保存） | **未逐项实测**，只从列表页与一级导航推断其存在 |
| 任务详情页、物品详情页的具体字段 | **未实测**（列表页证据） |
| 登录后的「保存进度/云同步」行为 | **未实测**，未登录 |
| `Gunsmith / TierMaker / Streamer / Variant / Saved` 五个视图各自的内容 | **未实测**（只读到标签） |
| Boss 刷新概率的完整数据面（是否分 PvE/PvP） | **未知** |
| 是否有官方公开 API | **未发现**；且 App Check 存在，**不尝试绕过**（任务书 2.4） |
