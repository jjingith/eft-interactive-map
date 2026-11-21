# R19.1 参考截图审计（DB4Tarkov 配枪页布局依据）

> 截图来源目录：`D:\personal\trae\02-塔科夫\ui图标`（用户指定的本地截图，本轮布局的**主要依据**）。
> 2026-10-24 通过代理 `http://127.0.0.1:7896` 复测参考站可达（上一轮 R19 已完成完整交互走查，
> 本轮以本地截图为准逐区域核对，不重复依赖在线页面）。

## 一、截图清单（全目录扫描结果）

目录共 315 张图片，其中与配枪页相关的在根目录；`src/`（63 张）是钥匙/物资点位图，
`clean/` 是钥匙物品图，`头盔防护部位图/`（8 张）与 `防弹衣防弹胸挂防护部位图/`（9 张）
是护甲防护区图——均与配枪页无关，不计入布局依据。

| 文件 | 尺寸 | 大小 | 判定 |
|---|---|---|---|
| `改枪台界面.png` | 1920×1080 | 726 KB | **db4tarkov /gun 工作台页**（本轮最核心依据） |
| `枪械类型分类.png` | 1920×1080 | 755 KB | **db4tarkov /gun 浏览页（Class 分组）** |
| `枪械口径分类.png` | 1920×1080 | 549 KB | **db4tarkov /gun 浏览页（Caliber 分组）** |
| `枪械详细属性界面.png` | 1920×1080 | 878 KB | **db4tarkov /gun 浏览页（Table 表格视图）** |
| `httpsdb4tarkov.compreset截图.png` | 1920×1080 | 904 KB | db4tarkov **/preset** 页（左装备面板 + 候选大表，价格/配色参考） |
| `头盔配件栏位范例.png` | 508×518 | 106 KB | /preset 左面板细节（Buy/Sell 双栏、ergo 三元组、商人角标） |
| `游戏内布局.png` | 2338×1493 | 3.4 MB | 游戏内仓库界面（配装工作台依据，R18 已用，非配枪页） |
| `右侧装备列表样式-*.png`（7 张） | ~1300×600 | — | 游戏内右侧装备列表（配装页依据，非配枪页） |
| `压子弹弹匣界面.png` | 1246×1377 | 270 KB | 游戏内压弹界面（弹药页参考，非配枪页） |
| `目标血量 样式.png` / `配装参考布局.png` | — | — | 其他页面参考，非配枪页 |

## 二、逐张布局记录（配枪页相关 5 张）

### 1. `改枪台界面.png` — /gun 工作台（选中一把枪之后）

自上而下、自左而右的区域划分（1920 宽下实测比例）：

| 区域 | 位置与占比 | 内容 |
|---|---|---|
| 顶部导航 | 全宽，高 ~56px | DB4Tarkov 标志 + 版本号；`MARKET SEASON QUEST KEEP GUN PRESET AMMO MAP BARTER CRAFT CHANGE LOGS`（GUN 高亮）；右侧 PVE/PVP 切换、货币 |
| 视图工具条 | 全宽，高 ~44px | 左：`Caliber │ Class │ Table │ Gun` 四个视图标签（Gun 激活）+ 保存/信息/关闭/刷新圆图标 + `FORGE` `Compare` `Changes` 按钮；右：`Gunsmith Streamer Variant ▾ Saved` + 价格模式切换 `lastPrice(avg24h / avg7d / only Flea lvl / only Trader lvl)` |
| **左栏 FORGE 面板** | x≈0–27%，宽 ~500px | 标题 `FORGE [BETA] BASIC / ADVANCED soon`，副标题 `Firearm Optimization, Ranking & Generation Engine`，右上 ABOUT。`GENERATOR SETTINGS`：`SUPPRESSED: OFF` / `BUYABLE: ON` 两个切换；`MAGS` 芯片 `10 20 30 32 40 60 100`（可多选，30 激活）；`SCOPE` 芯片 `CLOSE MID RANGE` + 三个空槽位；`TACTICAL` `OFF` + 一个空槽位（提示 "Toggle on to force one tactical dev…"）；`BLOCKED (0)` 搜索 "Search an item to blacklist" + CLEAR；`FORCED (0)` 搜索 "Search an item to force-include" + CLEAR；`GENERATION` 区 `GENERATE BUILDS` 大按钮 + "Press ENTER to capture the 3D Pareto frontier." |
| **中栏装配区** | x≈27%–51%，宽 ~460px | 顶行 `Compare │ Changes ▾ │ 🔗 │ ⬇ │ 📷`；`⩗ LOAD VARIANT` 下拉条（右端 (i) 和 × 按钮）；深色网格画布（配件关系树，节点用线连接）；**属性条组**：`Ergonomics [绿色条] 67.5`、`Accuracy [空条] 2.18`、`Ver Recoil [蓝条] (54.6) 54.6 (55.7) 56`、`Hor Recoil [蓝条] (151.9) 151.9 (155) 155`、`Velocity [红条] 842` —— 括号值是基线、右侧彩色值是当前；补充行 `OverSwing: NO`、`EvoErgoDelta (0): 65.2`、`ArmStamina: 32.2s`、`100% Headshot acc: 128m`、`ADS Time (beta): 0.46s`；**配件卡片网格**：已装配件是实体卡片（图标 + 名字 + ergo/后坐力双色角标如 `-8 / -2.5`、绿色 `+0.5` 徽标），空槽是虚线框占位（`TACTICAL` `SCOPE` `MUZZLE` `FOREGRIP` `MOUNT`），中央是武器本体卡（枪名 + `dps 700` + `3.50/3.86 kg`），下方弹药卡（`M856 [18]:60`）；`rail attachments` 分组分隔线；右下 `Final Cost: 159,250` |
| **右栏候选表** | x≈51%–100%，宽 ~900px | 顶部搜索框 `Type to search — ESC to clear`；表头 `Expand │ Ergo │ Size │ Kg │ Price`；行：图标块 + 名字（如 `NcSTAR MPW5 Backup mount`、`SureFire XC1 tactical flashlight`、`L3Harris AN/PEQ-15 tactical device`），列值 `Erg −1`、`Size 1x1`、`Kg 0.04`、`Price 32,500 ₽ + 商人角标（Leg II [5] / IV 等）`；选中/悬停行高亮 |
| **底部时间线** | 中栏下方，宽 ~570px | `Final Cost: 159,250`；页签 `Buy (159,250) │ Ammo Drop │ Sell ()`；子页签 `ITEMS │ BREAK`；改动时间线行：类型图标 + 配件名（`Type 20 buttstock`）+ 两列数值差值（`-23 +5`，绿/红/蓝着色）+ 右侧黄色 `default` 标记；行按改装历史排列 |

### 2. `枪械类型分类.png` — /gun 浏览页（Class 分组视图）

- 工具条：`Caliber │ Class │ Table │ Gun` 中 **Class 激活**；搜索框 `Type to search - ESC to clear`；右侧同上。
- 筛选行：`Primary`（激活）`│ Handgun`；`*Classifier ▾`、`Caliber Filter ▾` 两个下拉；射击模式芯片 **`Auto`（激活）`Single` `Burst` `Silent` `Loud`**。
- 主区：**按武器类别分行的卡片网格**。左侧竖排类别标签（`Assault / Carbine / LMG / DMR / Sniper / Shotgun / SMG / GL`），每行横向排卡片；卡片 = 枪械图标 + 左上口径小字 + 右上槽位数角标 + 下方枪名（如 `AK-74N / AKM / SAVA / MK47 / M4A1 / DT MDR…`）。
- 同一行的卡片等宽等高、间距一致；空位不留白（下一行类别直接接上）。

### 3. `枪械口径分类.png` — /gun 浏览页（Caliber 分组视图）

- 同一页面的另一种分组：左侧变成**彩色口径块**（`300` 青、`5.9x42` 红、`5.56x45` 青、`5.45x39` 青、`6.8x51` 绿、`7.62x39` 红、`7.62x51` 红、`7.62x54R` 暗红、`.368` 绿、`.338` 青），每组一行卡片。颜色大致对应弹药等级/口径族。
- 工具条与筛选行与 Class 视图相同（Caliber 激活）。

### 4. `枪械详细属性界面.png` — /gun 浏览页（Table 表格视图）

- 工具条中 **Table 激活**（其余同上）。
- 表格列（自左向右）：`Caliber`（彩色芯片）│ `Class` │ `Gun`（复选框 + 枪名，如 `Velocityoptor 2-6X28 / MCA / M4A1 / Type 20…`）│ `Erg`（复选框组 + 数值 `2.25 / 1.93 / 2.14…`）│ 后坐力两列（如 `73 / 197`、`47 / 133`，黄绿着色）│ 射击模式图标列 │ 数值列（`600 / 450 / 500 / 550…`，疑似初速/射程相关）│ `Rat. / Weight`（如 `2.21 / 3.50`）│ 价格列（`54,455 ₽ 📌 II`、`35,210 ₽ …`，带商人等级角标）│ 易货列（`99,460 ₽`）。
- 行按口径分组排列，口径芯片每行重复出现，组间有分隔。

### 5. `httpsdb4tarkov.compreset截图.png` — /preset 页（布局风格参照）

- 左侧装备面板：顶部 `Move/Turn/Ergo -8.6 / +3.7` 与 `Kg 15.53 KG`；装备槽卡片网格（头盔/面罩/护甲/胸挂/背包/枪）；`Final Cost: 259,264`；下方 `Buy (259,264) │ Sell` 双页签价格表：每行 物品名 + 重量 + 三列 ergo 差值（如 `-1.5 / -0.5 / -1.5`，红色负值、白色 0）+ 价格（`178,264 ₽`）+ 商人等级角标（`El IV` 等，红/蓝色块）。
- 右侧候选大表：`Type │ Name │ Mod Ergonomics（如 -1 / 0 / 0，红色负/白色零）│ Armor Class │ 网格列 │ Price ₽ │ cells`；表头有 `Min.Versatility` 排序；顶部工具条含一组预设快捷键（`UGLY / UseOnly / BaldestPreset / Standard Preset / MadnessPresets…`）+ `Type to search item to proceed` 搜索 + `reset / again` 按钮。
- 该页不是配枪页，但它的 **Buy/Sell 双栏价格表、ergo 差值着色、商人角标样式** 是 /gun 页底部与候选表的同一套视觉语言。

## 三、截图 ↔ 本地组件对应关系

| 参考区域 | 本地现有组件 | 差异 |
|---|---|---|
| 顶部导航 `GUN` 页签 | `index.html` 主菜单 `data-view="gun"`（配枪页签） | ✅ 已有 |
| 视图工具条 `Caliber/Class/Table/Gun` | **无** —— 本地只有搜索框下拉 | ❌ 缺：需新增 4 个视图模式 |
| 筛选行 Primary/Handgun + Auto/Single/Burst/Silent/Loud | **无** | ❌ 缺：Auto/Single/Burst 有数据（gun-stats.json `fm`）；Silent/Loud 无数据（上游无内置消音标记），做禁用态+说明 |
| Class/Caliber 分组卡片网格 | `gw-browse` 是平铺文字列表 | ❌ 布局不符：需改为分组卡片网格 |
| Table 表格视图 | **无** | ❌ 缺 |
| FORGE 面板 | `GB.optimize()` 引擎在、无 UI | ❌ 缺 UI：按截图做左栏面板 |
| LOAD VARIANT / 内置预设 | `gw-ref` 下拉 | ⚠️ 有功能、位置不同（参考站在中栏顶部） |
| 属性条（基线括号 + 当前值） | `gw-stats` 文字行 | ⚠️ 需改成条形 + 括号基线样式 |
| 配件卡片网格（含空槽虚线框） | `gw-tree` 是缩进树列表 | ⚠️ 功能等价、形态不符：改为卡片网格（递归保留） |
| 弹药卡（dps） | **无** | ❌ 缺：用 `da`（defaultAmmo）+ 本地弹药数据显示 |
| 右栏候选表（Expand/Ergo/Size/Kg/Price + 商人角标） | `gw-table` 在主区**下方**长表 | ❌ 位置错误：移到右栏常驻面板 |
| 底部 Buy/Ammo Drop/Sell + 改动时间线 | `gw-stats` 里的成本文字行 | ❌ 缺：新增底部成本页签 + 时间线 |
| Final Cost | 属性面板一行文字 | ⚠️ 移到参考站位置（中栏右下 + 底部页签） |

## 四、布局对照结论（实施要点）

1. **工作台三栏**：左 FORGE（~27%）/ 中装配（~26%）/ 右候选（~47%）。候选表从"主区下方"移到右栏。
2. **浏览页分组**：口径 / 类别两种分组 + 表格视图，一个切换器管三种；枪卡带口径小字与槽位角标。
3. **属性条**：五行条形（Ergonomics 绿、Accuracy、Ver/Hor Recoil 蓝、Velocity 红），括号基线值。
4. **底部时间线**：Buy/Sell 页签 + 每配件一行的差值时间线（default 标记）。
5. **配色沿用 XP Luna 主题**：参考站的深色底、青色高亮只决定"布局与信息层级"，颜色全部走现有 `--lw-*` / XP 变量。
