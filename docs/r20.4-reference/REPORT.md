# R20.4 通过参考站仿制 db4tarkov Gun Builder —— 交付报告

> 日期：2026-10-29。项目：`D:\personal\trae\02-塔科夫\eft-interactive-map`。
> 参考站：`https://db4tarkov.com/gun`（**实际经代理打开并操作**，取证截图与语义标签见
> `docs/r20.4-reference/screenshots/` 与 `raw/`）。
> 结论分级：**代码已证实 / 测试已证实 / 静态推断 / 未验证**。

---

## 1. 实际访问的参考页面与操作过的功能

### 1.1 网络路径（任务书第二节）

- 用户指定代理 `http://127.0.0.1:7896`：**端口开放**（socket 实测），经其访问
  `https://db4tarkov.com/gun` → **HTTP 200 / 60,675 bytes / 0.5s**；
  `https://www.eftarkov.com/` → HTTP 200。
- 环境变量里的旧端口 `127.0.0.1:5513` 本轮**已关闭**（与用户指定的 7896 不一致，已按用户指定端口执行）。
- 受控 Chrome 以 `--proxy-server=http://127.0.0.1:7896 --proxy-bypass-list=<-loopback>` 启动：
  **外网走指定代理，本地 127.0.0.1 服务与 CDP 端口直连**（`NO_PROXY` 语义等价，未关闭 TLS 校验）。

### 1.2 实际打开并操作的参考功能

| 操作 | 结果 |
|---|---|
| 打开 `/gun`（Flutter Web + Firebase，canvas 渲染） | 首访需 30–45s 下载数据；DOM 无文本，需点开 `flt-semantics-placeholder` 才拿到语义树 |
| 读取列表页结构 | 语义树给出列头 **Caliber / Class / Table / Gun**；每行语义含**价格、重量、口径、枪名** |
| 截图取证 | `db4-gun-1.png`、`db4-gun-2-semantics.png` |
| 点击 `M4A1` 单元格进入单枪 builder | URL 仍为 `/gun`（SPA 内部切换），截图 `db4-gun-builder.png` |
| 观察 builder 布局 | 左「FORGE BASIC/ADVANCED」生成器面板（BARREL/MASS/SCOPE/TACTICAL/BLOCKED/FORCED）、中栏「LOAD VARIANT」+ **枪身四周槽位（每格带配件属性增减角标如 -3 / +9.5）** + 统计条（Ergonomics / Accuracy / Vertical Recoil / Horizontal Recoil / Velocity）+ Overweight 判定 + 底部 **ITEMS 清单（逐件贡献 + default 标记）** + Buy / Sell 计价；右栏点击槽位后出现 **「Pick a mod」** 候选面板 |
| 顶部页签与价格口径 | Gunsmith / TierMaker / Streamer / Variant / Saved；价格口径 **avg24h / avg7d / TestPrice**；`only FleaMarket` / `only Trader` 勾选 |

**取证留档**：`docs/r20.4-reference/screenshots/`（参考站 3 张 + 本地 6 张）、
`docs/r20.4-reference/raw/db4-gun-labels.json`（语义标签 120 条）。

### 1.3 合规声明

参考站为 **Flutter + Firebase/Supabase + 自有 CDN**，无公开许可且有 App Check 反滥用
→ **未抓取其任何数据、图片或源码**；仅作**功能与布局研究依据**。本地实现全部使用项目自有
`data/*.json` 与 `assets/` 素材，运行期不引用参考站任何资源。

## 2. 修改文件清单与原因

| 文件 | 改动 | 原因（对应参考站观察） |
|---|---|---|
| `app.js` | ①新增 `traderMinLevel(rec)`（商人解锁等级解析）②`gunRows()` 行数据增加 `buy` / `lv` ③`gunColumns()` 新增 `COL_BUY`（商人价）、`COL_LV`（解锁）两列，**无数据的整列不渲染** ④`gwGunCard()` 卡片增加价格与重量行（缺数据显式写「价格缺失 / 重量缺失」）⑤`refreshGunTable()` 增加「仅商人可买」显示过滤 ⑥新增 `gwOnlyTrader()` 状态与开关接线 | 参考站列表每格显示均价+重量；候选面板有商人价与解锁等级；顶部有 `only Trader` 过滤 |
| `index.html` | 候选栏增加「仅商人可买」复选框（与既有「隐藏不兼容配件」并列） | 对应参考站 `only Trader` |
| `style.css` | 新增 `.gw-card-fig / .gw-card-price / .gw-card-wt / .gw-card-na` 样式（价格黄字、重量灰字，与参考站一致的信息层级） | 参考站卡片价格/重量为黄色强调字 |
| `tests/test_r20_4_gun_builder.py` | **新增** 15 个用例 | 本轮功能的静态 + 数据层回归 |
| `tools/r204_accept.py` | **新增** 真实浏览器验收脚本（23 项） | 任务书第八节验收要求 |
| `docs/r20.4-reference/` | **新增** 参考站取证截图 + 语义标签 + `browser-accept.json` | 研究留档与验收证据 |

**未改动**：`data/**`（业务 JSON 一个字节未动）、`tasks.js`、`gun_builder.js`、`combat_sim.js`、
地图/任务/配装工作台、`tools/fetch_data.py`、`tools/r20_validate_data.py`、全部旧测试。

## 3. 已实现 / 未实现的功能

### 3.1 本轮已实现（测试已证实）

1. **枪械浏览卡对齐参考站信息密度**：口径标签 + 槽位徽章 + 缩略图 + **均价（当前价格档位，默认 FLEA=跳蚤 24h 均价）** + **枪械本体重量** + 枪名；缺数据显示「价格缺失 / 重量缺失」，**不按 0 计入**（代码已证实）。
2. **候选表新增「商人价」与「解锁」两列**：商人价取 `trade[]` 中 `k=="buy"` 的最低卢布报价（复用既有 `buyPriceOf`），解锁等级取同一批条目里的最小等级（新增 `traderMinLevel`）；两列**整列无数据时不渲染**（沿用 R19.28「缺失属性整列隐藏」约定）。（测试已证实）
3. **「仅商人可买」过滤**：候选栏新增复选框，只影响候选列表显示，**不修改兼容性结论、不触碰装配状态**（代码已证实 + 浏览器实测 79 → 74 行，隐藏 5 个）。
4. **兼容性硬约束保持**：不兼容配件点击后被拒绝并给出可读原因（实测提示「⛔ 无法安装 北方工业 QMK-171A 瞄具基座：与已安装的「AR-15提把式照门」互斥（上游 conflictingItems）（未改动改装）」），装配总数不变。（测试已证实）

### 3.2 复核确认「此前已具备、无需再做」的能力（代码已证实）

参考站 builder 的下列能力，本项目在 R19.x 已实现，本轮复核确认并纳入验收：

- 枪身四周**槽位卡片 + 每件配件的属性增减角标**（`gw-part-b2`：人机增减 / 后坐修正，带方向色）；
- **点槽位 → 右侧候选列表**、**同件再点即卸下**、**换父件自动清理其子槽旧件**（`gunEquip` 的 `dropped` 逻辑）；
- **属性条实时更新**（人机 / 垂直后坐 / 水平后坐 / 精度 / 瞄准距离 / 枪口初速 / 重量 / 射速）+ 整枪属性明细 + 隐藏属性块；
- **口径 / 类别 / 表格 / 工作台** 四视图（对应参考站 Caliber / Class / Table / Gun）+ 射击模式筛选 + 搜索；
- **配件比较**：既有「差额对照」表与「对比」表格（枪械级）。

### 3.3 明确未实现 / 未复刻（及原因）

| 参考站能力 | 本地状态 | 原因 |
|---|---|---|
| avg7h / TestPrice 价格口径 | **未实现**（本地仅 FLEA=avg24h 与 BASE 两种档位） | 本地数据无 avg7d 字段（`items[].p` 只有 b/l/a/lo/hi）；**不编造口径** |
| 枪械列表的「Class 等级角标」 | 未实现（本地角标为**可改装槽位数**） | 本地数据无 class 字段；用槽位数作为等价维度 |
| 「Pareto 前沿」3D 生成器（BARREL/MASS/SCOPE/BLOCKED/FORCED） | 未实现 | 属于参考站 Tarkov Optimizer 的**组合优化器**，不是装配构建器本体；本地已有「生成式 FORGE」面板，但未做前沿求解 |
| 鼠标悬停 3D 预览/Overweight 判定 | 未实现 | 本地是 2D 网格画布，无 3D 渲染 |
| TierMaker / Streamer / Saved / Variant 云同步 | 未实现 | 需要账号与在线服务，违反离线约束（2.3） |

## 4. 配件兼容性与父子槽位的实际验证结果（浏览器实测）

以 **M4A1（AR 系）** 与 **AK-74（AK 系）** 两把结构不同的枪械实测：

| 项 | 实测结果 |
|---|---|
| 画布结构 | M4A1 槽位卡片 19 张；AK-74 14 张（结构随真实槽位树变化） |
| 点槽位出候选 | M4A1 `mod_reciever/mod_scope` → 候选 79 行 |
| 装配普通配件 | 槽位 `mod_reciever/mod_scope`：空 → 「FALKE LE 反射式瞄具」（人机 -2.0），属性条随之变化 |
| 装配带子槽配件 | 「Aimpoint Micro H-2 瞄具基座」→ 画布出现 **1 张以 `mod_reciever/mod_scope` 为父的子槽卡片**（`data-parent` 命中） |
| 不兼容配件 | 尝试「北方工业 QMK-171A 瞄具基座」→ **被拒**，提示互斥原因，已装总数 13 → 13 不变 |
| 拆除配件 | 再次点击已装行 → 槽位从「Aimpoint Micro H-2 瞄具基座」变回空，已装 13 → 12 |
| 换枪重置 | 切到 AK-74 → 已装数 12 → 8（官方默认预设），画布按 AK 真实槽位重排 |
| 过滤 | 「仅商人可买」：候选 79 → 74 行，计数提示「已隐藏 5 个」 |

## 5. 属性计算方式与规则可信度

| 量 | 来源 | 可信度 |
|---|---|---|
| 枪械本体人机/垂直后坐/水平后坐 | `gunslots.json` 的 `ergo/rv/rh` | **代码已证实**（构建期上游字段） |
| 配件人机/后坐/精度增量 | `items[].mod.e / mod.r / mod.a` | **代码已证实** |
| `R+E/3` | R 取「正面增益」（减少记正）后 `R + E/3`，保留三位小数 | **代码已证实**（R19.29 任务 C，且已核实 `items.json` 中 945 条 r<0、76 条 r>0 全为弹种） |
| 价格 | `p.a`（跳蚤 24h 均价，**构建期快照，非实时**）；`p.b` 为 basePrice | **代码已证实**，但**时效性有限**，界面已标注 |
| 商人价 / 解锁等级 | `trade[]` 中 `k=="buy"` 条目的 `p`（卢布）与 `l`（等级） | **代码已证实**（真实数据抽样核对 >100 条） |
| 重量 | `items[].w` | **代码已证实** |
| DPS / 射速 | 弹药伤害 × 射速 ÷ 60 | **估算**（未含距离衰减与穿甲，界面已注明） |
| 弹药距离 × 护甲矩阵 | **未实现** | 本地数据是否含衰减字段**未核实**（R20 决策 D4 仍待验证），不编造公式 |

## 6. 实际执行的测试命令与结果

| 命令 | 结果 |
|---|---|
| `node --check app.js` | OK |
| `pytest tests/test_r20_4_gun_builder.py tests/test_r20_3_hash_contract.py -q` | **31 passed**（本轮 15 + R20.3 16） |
| `pytest tests/test_r19_1_round.py test_r19_11 test_r19_28 test_r6_gun_workbench test_r19_5 test_r19_13 test_r13_gun test_r19_21 -q` | **62 passed / 5 failed**——5 项与 R20.1、R20.2 基线**完全相同**的历史失败（`gunColumns` 正则、`setColumns/gunColumns()` 文本契约、`gunModVal` 抽块边界、AK id 白名单、`rsCol` 字面），**本轮零新增回归** |
| `pytest tests/test_fetch_data.py -q` | 143 passed |
| `python tools/r204_accept.py --base http://127.0.0.1:8801 --port 9711` | **23/23 通过**（真实 Chrome + CDP） |

**全量 pytest 本轮未跑**：任务书未强制，且已知 `test_r19_21_round.py` 会经 `r1929_datafix.py`
重写真实 `data/items.json`（本轮已单独跑过一次该文件，事后核对三个业务 JSON 的 sha256
与 R20.3 基线**逐字一致**，仅 mtime 变化）。历史基线 `5 failed / 1337 passed / 1 skipped` 保持不变，
本轮**未声称**复现全量基线。

## 7. 本地浏览器验收结果（真实交互，非静态检查）

脚本 `tools/r204_accept.py`，真实 Chrome，产物 `docs/r20.4-reference/browser-accept.json`：

- **23/23 通过**：进入枪械视图 / 163 张卡 / 卡片价格 / 卡片重量 / 搜索有结果 / 选 M4A1 /
  画布 19 格 / 点槽出候选 79 行 / 商人价列 / 解锁列 / 焦点槽定位 / 装普通配件 /
  属性实时更新 / 装带子槽配件 / 子槽展开 / 不兼容被拒 / 不兼容提示 / 拆除配件 /
  仅商人可买过滤 / 切 AK-74 / 换枪重置。
- **控制台错误：0**。
- **外部网络请求：0**（全部指向 127.0.0.1；无 CDN/字体/在线 API）。
- 截图：`local-browse-price-weight.png`、`local-search.png`、`local-m4a1-empty.png`、
  `local-m4a1-installed.png`、`local-candidates-columns.png`、`local-ak74.png`。

## 8. 现有功能是否受影响

- **未受影响**（代码已证实 + 旧测试 + 浏览器实测）：地图、任务、弹药、配装工作台、逐发模拟器、
  枪械布局引擎（`gwBuildLayout`）、人工校准流程、预设/用户配置存储。
- 本轮只改 `app.js` 的**枪械视图分支**（浏览卡、候选列、候选过滤）、`index.html` 的一个复选框、
  `style.css` 的枪械卡片样式；未改任何布局引擎与共享计算（`gunRE3`、`buyPriceOf` 等仅**复用**）。
- 业务数据 JSON **sha256 逐字未变**（items/gunslots/gun-presets 与 R20.3 基线一致）。

## 9. 尚存问题与下一步优先级

1. **P0 待决策**：参考站的 **Pareto 前沿生成器**（FORGE ADVANCED：BARREL/MASS/SCOPE/TACTICAL/
   BLOCKED/FORCED → 3D 权衡前沿）是否要仿制？它是组合优化器而非装配器，工作量与现有
   「FORGE 自动配枪」面板重叠，建议先明确产品形态再动手。
2. **P1**：候选表增加**同一槽位的横向对比**（无需反复装卸即看差异）——当前只能靠
   「差额对照」表间接比较，可做增量列（Δ人机/Δ后坐/Δ重量/Δ价）。
3. **P1**：参考站的**价格口径切换**（avg7d/TestPrice）——需先补上游 avg7d 字段，否则不做。
4. **P2**：弹药距离 × 护甲矩阵（沿用 R20 决策 D4，先做数据可行性验证）。
5. **P2**：参考站「TierMaker/Streamer」等**社区内容页**——涉及在线协作，离线约束下建议不做。
6. **P2**：购物车式「Buy / Sell 总价」——本地已有「改装统计 / Final Cost」，可对齐为
   参考站的单行 Buy/Ammo Drop/Sell 计价条。
7. **遗留**：5 项历史测试失败仍待单独一轮处理（本轮未触碰，也未弱化）。

## 10. 文件与状态声明

- **本轮修改**：`app.js`、`index.html`、`style.css`。
- **本轮新增**：`tests/test_r20_4_gun_builder.py`、`tools/r204_accept.py`、
  `docs/r20.4-reference/`（参考站截图与语义标签、本地验收截图与 `browser-accept.json`、本报告）。
- **本轮未修改**：任何 `data/**` 业务数据、`tools/fetch_data.py`、校验器、全部旧测试、
  地图/任务/配装/模拟器相关文件。
- **未提交 Git、未推送、未覆盖发布版本**；未进入其它任务。


---

## 十一、R20.4b 补完：用 rea MCP 复核参考站 → 再对齐（2026-10-29 续）

### 11.1 用 rea MCP 实际观测到的参考站能力

本轮按要求改用 **rea MCP**（`capture_web_screenshot` / `inspect_web_page`）观测参考站：

- `capture_web_screenshot` 成功产出 artifact（sha256 `eab81936…`，1584×905，URL `https://db4tarkov.com/gun`）；
  结果体积极大（33 万字符，base64 图像数据占 33.1 万），已落盘后做结构化提取。
- `inspect_web_page` 返回 **completeness = policy_filtered**（DOM / console / scripts / resources 段被策略过滤，
  网络请求段因 attach 时机未捕获——与 R20 审计轮结论一致）。其 **accessibility 段可用**，
  提取到 **213 条去重标签**，完整暴露参考站能力清单：
  - 枪械页签：`Gunsmith / TierMaker / Streamer(24) / Variant / Saved`；
  - 价格口径：**`lastPrice` / `avg24h` / `avg7d`**；
  - 商人筛选：**`only FleaLvl` / `only TraderLvl`**、`Trader level / PMC Setting`；
  - 列表过滤：`Primary / Handgun / Class Filter / Caliber Filter / Auto / Single / Burst / Silent / Loud`；
  - 搜索：`Type to search — ESC to clear`；
  - 顶栏模块：`MARKET / SEASON Kord / QUEST / KEEP / GUN / PRESET / AMMO / MAP / BARTER / CRAFT / CHANGES 1.2.0.0 / LOGS`；
  - 游戏模式：`PvE / PvP / SS (38d)`；站点版本 `DB4Tarkov v2026.10.28-0`，游戏版本 **1.2.0.0**。
- 补充事实：`https://db4tarkov.com/` **会重定向到 `/gun`**——参考站首页即枪械页；
  资源全部来自 `db4tarkov.com` 自有域（flutter.js / canvaskit.wasm / main.dart.js / favicon / splash），
  无第三方 CDN；控制台为 Flutter TrustedTypes 初始化日志，无错误。

### 11.2 差距表与本轮处置

| 参考站能力（rea 证据） | 本地状态（复核前） | 本轮处置 |
|---|---|---|
| 价格口径 `lastPrice` | 无该口径（仅 跳蚤24h均价 / 基础价） | **已补**：`PRICE_MODES` 新增 `LAST` 档（取上游 `p.l` = lastLowPrice，构建期快照，已在 note 标明非实时） |
| 枪械页价格口径切换控件 | 枪械视图无（只有配装视图有 pills） | **已补**：枪械候选栏新增价格口径 pills（跳蚤/LAST/PvP禁用/Scav禁用/基础价） |
| `only TraderLvl` / 商人等级门槛 | 仅「仅商人可买」（无等级条件） | **已补**：候选栏新增「商人等级 ≤ Lv1..Lv4」下拉；实测 Lv1 时候选 79 → 15 行，且可见行最高解锁等级=1 |
| 槽位/候选的属性增减差异（builder 角标 + ITEMS 差异清单） | 只能靠底部「差额对照」间接看 | **已补**：候选表新增 `Δ人机 / Δ后坐 / Δ重量 / Δ价` 四列（候选 − 当前已装件），无基准或缺属性时整列不渲染 |
| `avg7d` 价格口径 | 本地无该字段 | **不做**（`items[].p` 只有 b/l/a/lo/hi；不编造口径） |
| `Silent / Loud`（消音）过滤 | 本地 `gunslots.json` **无消音器槽位**（消音器是枪口附件而非独立槽） | **不做**（本地无对应槽位数据，不能凭猜测造筛选） |
| `Class` 等级角标 | 本地无 class 字段 | **不做**（改用"可改装槽位数"角标） |
| `Trader level / PMC Setting`（PMC 档位） | 本地只有模式切换（PvE/PvP/SS），未做统一读取收口 | **不做**（属 R20 决策材料 P0-4，需你批准后单独一轮） |
| `CHANGES 1.2.0.0` / 游戏版本标识 | 本地数据**无游戏版本字段** | **不做**（属数据层缺口，见 R20.2 审计 §8） |
| MARKET / BARTER / CRAFT / QUEST / KEEP 等整站模块 | 本地无 | **不做**（需要价格/商人/配方数据集，属 R20 决策材料 D2 未决项） |
| Pareto 前沿生成器 / 3D / Overweight | 本地无 | **不做**（组合优化器与 3D 渲染，建议先定产品形态） |
| Buy / Ammo Drop / Sell 计价条 | **本地已有**（R19.2 的改装件/含枪/回收 三口径页签 + Final Cost） | 复核确认为已对齐，无需再改 |

### 11.3 本轮改动文件

- `app.js`：`PRICE_MODES` 增 `LAST` 档；新增 `renderGunPrices()`（枪械页价格口径 pills）；
  新增 `gwTraderLvLimit()` 与商人等级过滤；`gunRows()` 计算 `dErgo/dRecoil/dW/dPrice`（相对当前已装件）；
  `gunColumns()` 新增 `COL_DERGO/COL_DREC/COL_DW/COL_DPRICE`（无基准时整列不渲染）；状态 `gwTraderLv` 与接线。
- `index.html`：候选栏新增 `#gw-prices` 与 `#gw-trader-lv`。
- `style.css`：新增 `.gw-cands-filters / .gw-prices / .gw-price-pill / .gw-lvsel` 与差额列方向色。
- `tests/test_r20_4_gun_builder.py`：新增 6 个用例（LAST 档、价格 pills、等级筛选、差额列等）。
- `tools/r204_accept.py`：验收项由 23 扩到 **29**（新增价格口径 2 项、差额列 2 项、等级筛选 1 项）。

### 11.4 本轮验证结果

| 项 | 结果 |
|---|---|
| 真实浏览器验收 `tools/r204_accept.py` | **29/29 通过**（含 I1/I2 价格口径、J1/J1b/J2 差额列、K1 等级筛选）；控制台错误 **0**，外部网络请求 **0** |
| pytest `tests/test_r20_4_gun_builder.py` + `test_r20_3_hash_contract.py` | **37 passed** |
| 枪械相关旧测试（含 `test_fetch_data.py`） | **195 passed / 5 failed**——5 项与 R20.1/R20.2 基线完全相同的历史失败，**零新增回归** |
| 业务数据 | `data/items.json`、`gunslots.json`、`gun-presets.json` 的 sha256 与 R20.3 基线**逐字一致**（未触碰） |

**已知的数据缺失行为（非缺陷）**：若当前槽位已装件缺后坐属性（如 `FALKE LE 反射式瞄具` 的 `mod` 只有 `e=-2`），
`Δ后坐` 列会整列隐藏——沿用项目既定「缺失属性整列隐藏」约定，验收项 J1b 已断言此时已装行的「后坐力」单元格为「—」。

**未提交 Git、未推送**；本轮只改 `app.js`/`index.html`/`style.css` 与两个测试/验收脚本。
