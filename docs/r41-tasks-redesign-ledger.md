host=HOMONAS user=MASTERJJ at=2026-11-04T02:00:41+08:00

# R41 任务页复刻（db4tarkov）+ 商人英文名 / 游戏内头像 留痕

> 入口：本文件是 R41 专项留痕；`docs/r34-mapui-ledger.md` 头部已指向本文件。
> 本轮**只改前端与展示数据**（`tasks.js` / `tasks.css` / `data/tasks/traders.json` / 新增测试），
> 未改 `tools/serve.py`、`tools/live_prices.py`、`combat_sim.js`；未动 `release/`、`dist/`；未 `git commit`。

## 0. 结论（先看这里）

1. 任务列表页改成 db4tarkov 的四区结构：**搜索条 → 商人头像条（16 张游戏头像）→ 按商人分组的任务行 → 右侧筛选栏**。
   行内保留「状态勾选 / 任务名 / 英文名 / 等级 / 地图 / 目标 / 物品图标 / exp / Complete」。
2. 视觉令牌按参考站截图逐块量取：底 `#0e0e0e`、面板 `#151515`/`#1b1b1b`、分隔线 `#262626`、
   正文 `#e6e6e6`、次灰 `#9a9a9a`、弱灰 `#6f6f6f`、橙 `#f08a24`、蓝 `#4a90d9`、绿 `#4ad07a`、红 `#e05b5b`。
   右栏是整宽居中按钮、选中反白（`#efefef` 底 / `#111` 字）；行尾 Complete 是**纯文字链接**（无边框无底色）。
3. 原有能力全部保留：目标旁 `◎` 走 `GWMapFocus` 定位（任务 → 地图聚焦）、任务名 → 任务详情、
   `eftmap.tasks.progress.v1` 进度持久化、中英双语搜索（含目标英文与商人家英文名）。
4. 商人主显示名改为游戏内英文名（16/16），中文名保留为副标题 / tooltip；头像 16/16 使用
   `assets/icons-traders/portraits/<traderId>.webp`（上游 `assets.tarkov.dev` 游戏素材，128×128 WebP），
   缺失时回退项目内 `unknown.svg`，无破图、无占位图。
5. 参考站是 Flutter/CanvasKit 应用（DOM 只有 canvas），且在本机启动崩溃（见 §2 限制），
   因此以**已归档的 db4 真实截图**（1600×1000）+ 像素取样为对照基准，而不是伪造「实时复刻」截图。
6. 测试：新增 `tests/test_r41_tasks_ui.py` **18 passed**；全量 `pytest tests -q` 数字见 §7。

## 1. 改动文件与 SHA256

| 文件 | 字节 | SHA256 | 说明 |
| --- | ---: | --- | --- |
| `tasks.js` | 150,561 | `f23312d04695cd576a763452cdbf0b0e0762911b78fa9ebe849e8a8749f4e6f6` | db4 任务板结构、右栏按钮、搜索英文名、默认视图 list、`locateByObjective`；Special 段英文名从 `state.traders` 读取 |
| `tasks.css` | 39,535 | `f74b7d7955bf7fbd4377d2b34ff44cc7a0fdcd5ab856e7324e518b1ecdcd9c48` | R41 深色复刻样式（§698 起），第 4 轮右栏/Complete/头像条 |
| `data/tasks/traders.json` | 9,536 | `1bdb24f6d8b4462bba2da0fdeb8ae6dcfe2a87d25d75c9da814affa091fb9074` | 16 商人 `portrait` 路径 + `nameZhNote`（中文仅 tooltip） |
| `tests/test_r41_tasks_ui.py` | 9,259 | `28e33e3bd12af724fb1fe0e94cd80395cb88aa2cb11167c4b0e73eb0d3061965` | 新增 18 条离线测试 |
| `index.html` | 53,885 | `08ac56ac06274e47c59d80448a885d0794693f18f5bf9234a31de84689370a35` | **本轮未改**（mtime 11-03 22:40） |
| `app.js` | 1,128,529 | `f658aeaa98958b70d6364252038d574912e1e42980e96bd2a5ccc68dd6dca5ad` | **本轮未改**（mtime 11-03 22:40） |

非本轮改动 / 非我所为：`index.html`、`app.js`、`style.css` 的最后修改时间分别为 11-03 22:40、22:40、21:21，
早于本轮 R41 开工（11-04 01:2x），**未回退**；另一会话的 `tools/live_prices.py`、`tools/serve.py`
（R42 留痕 `docs/r42-live-prices-ledger.md`）也未触碰。

## 2. REA 取证清单与限制

| 项 | 结果 |
| --- | --- |
| `list_browser_targets` | 命中本机 Chrome/156 target `E76BF5486E821FC025A788301C99D93D`（loopback CDP `127.0.0.1:9333`） |
| `inspect_web_page` | db4 `/tasks` 的 DOM **只有 canvas（Flutter/CanvasKit）**，无 HTML/CSS 可抄；脚本主体 `main.dart.js` ≈ 18.5 MB |
| `export_web_scripts` | 导出后确认任务数据来自站点自有 CDN（`eft-cdn.dvcstudiox.workers.dev`），**不是直接复用 tarkov.dev** |
| 网络 | 页面内 `fetch` 到 `eft-cdn…/json/core/changes.json` 返回 200（带 `Origin`/`Referer`）；curl 裸请求 403，排除「网络层被拦」 |
| 截图 | `docs/site-integration-audit/screenshots/db4-quest.png`（1600×1000）与 `docs/r19.23/ref/db4tarkov-quest.png` 为既有真实抓取；本轮复制为 `docs/r41-tasks-redesign/shots/ref-db4-1024.png` |
| **限制** | db4 页面在本机启动即崩：console `Null check operator used on a null value` @ `main.dart.js:242533`（`at_.aGx`），画布空白。已试 headful、webdriver 掩码、代理 `127.0.0.1:7896`、WebGL2 检测（通过），均无法恢复。**因此无法在本轮重新渲染参考站**，改用归档截图 + 像素取值，限制如实记录，不伪造证据。 |

代理测试：`127.0.0.1:7896` 实测可用（`NO_PROXY=127.0.0.1,localhost` 走本地 CDP）；
头像来自既有构建产物 `assets/icons-traders/manifest.json`（`https://assets.tarkov.dev/<id>.webp`，全部 HTTP 200 时入库），
本轮未关闭 TLS 校验、未用占位图。

## 3. 任务页复刻的结构

| db4 区块 | 本地实现 | 说明 |
| --- | --- | --- |
| 顶部搜索（`Type to search — ESC to clear`） | `.db4-bar > input.db4-search` + 右侧 `503 / 503` 计数 | ESC 清空；搜索域含任务中/英文名、ID、商人英文名、目标中/英文 |
| 商人头像横条 | `.db4-strip`，`Object.keys(state.traders)` 全量 | 32×32 游戏头像；选中橙框 + 下划线，其余灰度压暗；点击只看该商人 |
| 左侧商人列 | `.db4-group > .db4-gutter` | 58px；44px 头像 + 8.5px 大写英文名；`title` 防截断 |
| 任务行 | `.db4-row` | 状态勾选、任务名、英文名、`Lv`、地图、目标行、物品图标列、`exp`、`Complete` |
| 行尾经验 | `.db4-exp`（`EXP` + `+10000`） | 右对齐；数值取 `experience` |
| 行尾完成 | `.db4-complete` | db4 同款**文字链接**；点击切换完成 / 重置 |
| 右筛选栏 | `.db4-rail`，196px | `Status`（All / Uncompleted / Active / Completed / Failed / Available）、`Special`（Kappa / Lightkeeper / 赛季）、`Sort`（Default / By Exp / By Map / By Progress / By Objectives / By Name）、`Display`（全部目标，蓝色拨动开关）、`Reset filters` |
| 空态 | `.db4-empty` | 「没有符合筛选条件的任务」 |
| 窄屏 | `@media (max-width: 980px)` | 右栏 170px、商人列 54px、物品列 108px；参考站 1024 仍保留 196px |

保留但 db4 没有的：任务树 / 商人任务 / 任务详情 / 我的进度四个旧面板、任务 → 地图点位联动、
进度导入导出、三模式（PvP / PvE / PvPS）隔离。未为了「像」而删除。

## 4. 对照差异轮次（截图 → 对照 → 调 CSS → 再截图）

截图目录：`docs/r41-tasks-redesign/shots/`（真实 Chrome，1024×768 / 1440×900，DSF=1）。

### 第 1 轮
- 差异：首行物品图标全部铺开，把行高撑到 ~280px；搜索框被全局 input 规则染成白底。
- 修：物品图标只取当前展示目标，最多 4 个 + `+N`；`flex-wrap: nowrap`；`.db4-board input.db4-search !important` 压回深色。
- 证据：`1024-list.png`（第 1 轮后）→ `crop-local-rows.png`。

### 第 2 轮
- 差异：目标文字 10.5px 且偏灰；地图名被推到行尾远处；目标没有定位入口。
- 修：目标 11px `#c2c2c2`；地图名改为目标行内联；新增 `◎`（`data-db4-loc`）→ `locateByObjective` → `GWMapFocus`。
- 证据：`1024-trader-selected.png`。

### 第 3 轮
- 差异：物品图标换行；商人列 `THERAPIS` 被截断；窄屏右栏过早收窄。
- 修：`flex: 0 0 auto` + `nowrap`；商人列 64→70px、字号 9→8.5px、省略号 + `title`；窄屏断点 1100→980。
- 证据：`1440-list.png`。

### 第 4 轮（2026-11-04）
- 差异（对照 `crop-ref-rail.png` / `crop-ref-right.png` / `crop-ref-gutter.png`）：
  1) 参考站右栏是整宽居中按钮（选中白底黑字），本地是左对齐按钮 + 可见计数；
  2) 参考站 Complete 是纯文字，本地是描边按钮；
  3) 参考站头像条约 26–32px，本地 38px；商人列参考站约 56px，本地 70px；
  4) 参考站行底色接近 `#0e0e0e`，本地偏 `#131313`；物品图标格 `#1b1b1b`。
- 修：右栏按钮 30px 高、居中、`#1b1b1b`，选中 `#efefef`/`#111`；计数移入 `title`；Sort 移到 Special 之后；
  Complete 去边框去底色改为 11px 文字链接；头像条 38→32px；商人列 70→58px、头像 44px 全彩；
  行底 `#101010`；`Display` 复选框改纯 CSS 蓝色拨动开关；深色细滚动条。
- 证据：`1024-list.png`、`1440-list.png`、`compare-1024.png`（参考图 vs 本地并排）。

### 剩余差异（如实记录）
1. **应用外框**：本项目是 WinXP 主题外壳（顶部导航 / 任务树面板为浅色），db4 全站深色；
   本轮只把「任务列表页内胆」压成深色，未改全局主题（超出任务页范围）。
2. **商人列图形**：db4 用游戏内「商人徽章」橙色方块，本项目按目标 B 要求使用**游戏内头像照片**；
   构图不同但同为官方素材，不是占位图。
3. **任务名语言**：db4 英文名单独一行；本项目中文为主 + 英文副标题（既有 i18n 能力保留）。
4. **物品数量**：db4 把数量叠在图标右下角；本项目在目标文案里写 `×N`（避免图标太小看不清数字）。
5. **筛选粒度**：db4 有 Banned / Only-Season / Only-Kappa 等更多开关与 Edition 区；
   本项目提供等价子集（赛季 / Kappa / Lightkeeper），没有的数据不伪造。
6. **参考站无法重新渲染**（Flutter 启动崩溃），对照基准是归档截图；同尺寸、同数据量的并排图为
   `compare-1024.png`（左：db4 1600×1000 参考；右：本地 1008×805 实际窗口）。

## 5. 商人 → 英文名 → 头像文件 → 来源

英文名来源优先级：上游 `traders` 的 `nameEn`（tarkov.dev `traders.name`）> 官方 Wiki 英文条目名。
头像来源：`assets/icons-traders/manifest.json`（`https://assets.tarkov.dev/<traderId>.webp`，构建期下载）。

| # | 商人 ID | 英文名（主显示） | 中文（tooltip） | 头像文件 | 字节 | 来源 |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1 | `54cb50c76803fa8b248b4571` | Prapor | 大老板 | `assets/icons-traders/portraits/54cb50c76803fa8b248b4571.webp` | 4,020 | tarkov.dev / assets.tarkov.dev |
| 2 | `54cb57776803fa99248b456e` | Therapist | 医生 | `assets/icons-traders/portraits/54cb57776803fa99248b456e.webp` | 4,270 | 同上 |
| 3 | `579dc571d53a0658a154fbec` | Fence | 篱笆 | `assets/icons-traders/portraits/579dc571d53a0658a154fbec.webp` | 998 | 同上 |
| 4 | `58330581ace78e27b8b10cee` | Skier | 滑雪 | `assets/icons-traders/portraits/58330581ace78e27b8b10cee.webp` | 4,014 | 同上 |
| 5 | `5935c25fb3acc3127c3d8cd9` | Peacekeeper | 和平卫士 | `assets/icons-traders/portraits/5935c25fb3acc3127c3d8cd9.webp` | 3,500 | 同上 |
| 6 | `5a7c2eca46aef81a7ca2145d` | Mechanic | 机械师 | `assets/icons-traders/portraits/5a7c2eca46aef81a7ca2145d.webp` | 4,408 | 同上 |
| 7 | `5ac3b934156ae10c4430e83c` | Ragman | 拉格曼 | `assets/icons-traders/portraits/5ac3b934156ae10c4430e83c.webp` | 4,506 | 同上 |
| 8 | `5c0647fdd443bc2504c2d371` | Jaeger | 猎人 | `assets/icons-traders/portraits/5c0647fdd443bc2504c2d371.webp` | 4,310 | 同上 |
| 9 | `638f541a29ffd1183d187f57` | Lightkeeper | 灯塔看守 | `assets/icons-traders/portraits/638f541a29ffd1183d187f57.webp` | 3,242 | 同上 |
| 10 | `68fe15910f29ba3fdbba9d54` | Taran | 塔兰 | `assets/icons-traders/portraits/68fe15910f29ba3fdbba9d54.webp` | 29,236 | 同上 |
| 11 | `68fe15990f29ba3fdbba9d55` | Radio Station | 无线电台 | `assets/icons-traders/portraits/68fe15990f29ba3fdbba9d55.webp` | 25,380 | 同上 |
| 12 | `656f0f98d80a697f855d34b1` | BTR Driver | BTR 驾驶员 | `assets/icons-traders/portraits/656f0f98d80a697f855d34b1.webp` | 20,736 | 同上 |
| 13 | `6617beeaa9cfa777ca915b7c` | Ref | 裁判 | `assets/icons-traders/portraits/6617beeaa9cfa777ca915b7c.webp` | 22,614 | 同上 |
| 14 | `688246518448b05efd61d461` | Mr. Kerman | 克尔曼先生 | `assets/icons-traders/portraits/688246518448b05efd61d461.webp` | 32,238 | 同上 |
| 15 | `688246958448b05efd61d462` | Voevoda | 总督 | `assets/icons-traders/portraits/688246958448b05efd61d462.webp` | 18,960 | 同上 |
| 16 | `69e0d6cc77b63940375b9173` | Survivor | 幸存者 | `assets/icons-traders/portraits/69e0d6cc77b63940375b9173.webp` | 25,600 | 同上 |

规格：16/16 为 **WebP 128×128（个别 127×127，源图裁切）**，RGB；照片类官方头像本身自带背景，
因此没有 alpha 通道（与矢量图标体系的透明 PNG/SVG 不同，属源素材属性）。回退链：
`portrait`（webp）→ `localIcon`（项目内 SVG）→ `assets/icons-traders/unknown.svg`；
`onerror` 只触发一次，不会死循环、不会出现破图。缺失头像：**0**。

## 6. 截图

| 文件 | 字节 | 内容 |
| --- | ---: | --- |
| `shots/ref-db4-1024.png` | 505,619 | 参考站 db4tarkov `/tasks`（归档真实截图 1600×1000） |
| `shots/before-1024.png` | 133,372 | 本轮改造前的任务列表 |
| `shots/1024-list.png` | 149,286 | 1024 列表（第 4 轮后） |
| `shots/1024-trader-selected.png` | 136,151 | 1024 选中 Therapist（`53 / 503`） |
| `shots/1440-list.png` | 155,174 | 1440 列表 |
| `shots/1440-trader-selected.png` | 140,461 | 1440 选中 Therapist |
| `shots/1024-tree.png` / `shots/1440-tree.png` | 117,863 / 147,356 | 保留的任务树（深色外壳内仍可读） |
| `shots/compare-1024.png` | 1,085,790（2860×1034） | **并排对照**：左参考站 / 右本地 |
| `shots/trader-portraits-sheet.png` | 472,504（592×592） | 16 张头像总览（验证无破图） |
| `shots/crop-ref-*.png` / `crop-local-*.png` | — | 参考站与本地 1:1 局部取样（header / rows / rail / gutter） |

## 7. 测试与静态检查

- `node --check app.js`：通过；`node --check tasks.js`：通过（check=0）。
- ES5 扫描（代码行，去注释）：`tasks.js` **0 命中**；`app.js` 5 命中均为**字符串字面量里的反引号**
  （「候选来源：上游 \`ItemPropertiesMelee\`」等展示文案），不是模板字符串，且本轮未改 `app.js`。
  新增/改动的 R41 代码无 `let` / `const` / 箭头函数 / 模板字符串 / `class` / 展开运算符。
- 新增 `tests/test_r41_tasks_ui.py`：**18 passed**（结构、行解剖、右栏按钮、Complete 文字链接、
  默认 list、搜索含英文名、地图联动、进度持久化、ES5、零第三方、16 商人英文名、头像存在/尺寸/回退、无占位图）。
- 全量 `python -m pytest tests -q`：**5 failed, 1665 passed, 1 skipped in 98.15s**（合计 1671）。
  5 个失败全部是既有配枪 / 布局用例，与本轮改动无关，未修、未跳过、未弱化：
  `tests/test_r19_1_round.py::test_candidate_columns_match_reference_order`（找不到 gunColumns）、
  `tests/test_r19_5_round.py::test_zoning_is_generic_semantic_rules`、
  `tests/test_r19_11_round.py::test_hide_incompat_filters_without_touching_data`、
  `tests/test_r19_13_round.py::test_row2_anchors_are_driven_by_real_slot_tree`、
  `tests/test_r6_gun_workbench.py::test_gun_workbench_business_logic`。
- 过程中新测试暴露过一条本轮引入的回归：右栏 `Lightkeeper` 字样写死在 `tasks.js`，导致
  `test_r19_25_round.py::test_C_trader_enums_are_data_driven` 失败；已改为从 `state.traders`
  读英文名（取不到退回「灯塔」），复跑该文件 + R41 = **39 passed**，全量恢复为上述 5 failed。

## 8. 边界

- 未 `git commit`；未动 `release/`、`dist/`；未改 `combat_sim.js`；未改 `tools/serve.py`、`tools/live_prices.py`。
- 参考站无法在本机重新渲染（§2），所有「参考站」图像均为既有归档真实截图，未伪造 REA 实时截图。
- 头像与任务封面来自游戏素材，学术研究 / 非商用；仓库只登记路径，不改变既有许可说明。
