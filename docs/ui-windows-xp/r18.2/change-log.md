# R18.2 变更记录（配装图标白底统一 / 完整枪械剪影）

日期：2026-10-24 · 基线：R18.1
构建标记：`AM_BUILD = "R18.2"`，`index.html` 资源版本 `?v=r18.2`（四个资源同步）
范围：只改配装工作台的图标背景与两把枪的空槽剪影；未重做 XP 主题，未动其它页面功能。

---

## 一、右侧装备列表：图标统一白底

### 1.1 白底问题的真实来源

不是 CSS 没写，而是**背景固化在图片像素里**。逐项核实：

| 检查项 | 实测结果 |
|---|---|
| 图标文件 | `assets/icons-items/{id}.webp`，64×64，`mode=RGB`（**无 Alpha**） |
| 背景像素 | 外圈 1px 是统一描边 `rgb(73,81,84)`；内部是带 ±10 抖动的深色纹理（实测不同物品底色从 `rgb(12,12,12)` 到 `rgb(50,50,50)` 不等） |
| 现有 CSS | `.loadout-workbench .tbl-icon { background: transparent }`，元素 30×30、`object-fit: contain` |
| 为什么 `background:#fff` 无效 | 图片是**不透明**的 64×64 方块，`contain` 后铺满 30×30 容器，白底完全被图片盖住 |

### 1.2 为什么没有用「抠图」解决

两条路都试过，都不合格，记录在此避免以后重做：

1. **反解前景色（matting）**：`F = (C − bg·(1−a)) / a`
   → 深色物品（头盔暗部、黑枪、刀身）与深色背景只差 5–10 个灰阶，alpha 被严重低估，
   反解后暗部被推成白色，物品变成「发光残缺」的轮廓。
2. **只把「从边界可达且接近背景色」的区域涂白**、前景区取原像素
   → 区域生长顺着低对比度断口漏进物品内部，物品被大片涂白，只剩碎片。

根因：**深色物品 + 深色背景**在这批 64px 素材上没有可靠的逐像素边界。
按任务要求「不要使用会破坏物品纹理、颜色或轮廓的粗暴阈值处理」，这条路放弃。

### 1.3 采用的方案：用上游本来就有的透明底图重制

`https://assets.tarkov.dev/{id}-base-image.webp` 是透明底（RGBA）的原始渲染图。
抽样 20 件覆盖全部装备类别，**20/20 都有有效 Alpha 轮廓**。

生成器：`tools/build_gear_icons.py`（构建期，依赖 Pillow；运行期零依赖）

```
上游 base-image（RGBA，64×64 ~ 316×379）
  → Alpha 通道裁出主体包围盒
  → 等比缩放到 56×56（画布 64×64，留 4px 边距）
  → 输出 assets/icons-items-white/{id}.png（透明底，物品原色不动）
```

- **白底由 CSS 容器提供**（`background:#fff`），所以普通行 / 悬停行 / 选中行都是纯白图标区，
  且不会出现「白底方块盖住图标」的问题。
- 透明底 PNG 保留上游真实的抗锯齿边缘，没有硬阈值切出来的锯齿或灰边。
- 原始 `assets/icons-items/*.webp` **只读未改**；上游源图缓存在
  `build-cache/gear-icons-src/`（已被 `.gitignore` 排除），映射关系写在
  `assets/icons-items-white/manifest.json`（含来源 URL、原始尺寸、alpha 占比）。

### 1.4 覆盖范围

候选集必须与 `app.js` 的槽位候选规则完全一致。**三种判定都要看**：

| 判定字段 | 说明 | 教训 |
|---|---|---|
| `pt` | 上游 `propertiesType`（Armor / Helmet / ChestRig / Backpack / Glasses / Headphone / Melee / Weapon / ArmorPlate …） | 主路径 |
| `slot` | 上游装备槽字段 | 部分配件用它挂槽 |
| `cat` | 本项目构建期的槽位归类 | **面部装备只靠这一条**：巴拉克拉瓦头套等 `pt` 与 `slot` 都是 `null`，首版只按 `pt`/`slot` 筛选，漏了 108 件（面部列表整列仍是深色方块） |

最终：候选 **863** 件 → 生成 **859** 张 → 缺失 **4** 项。

缺失项（上游没有 base-image，本地 `icons-items` 也没有这两件的新物品图标）：

| 物品 id | 名称 | 原因 |
|---|---|---|
| `6a15ae2ae5267ba21c07f98f` | HK 416A5 5.56x45 突击步枪 (RAL 8000) | 上游 `-base-image.webp` 404 |
| `6a78b7f8c2016eb33e0027cd` | FN P90 5.7x28 冲锋枪（灾厄） | 同上 |
| `6aa948d1a7cdc313b50cdd11` | 「杀人鲸」推刃匕首 | 同上 |
| `6aa94a3ca7cdc313b50cdd15` | NKVD 芬卡工具刀 | 同上 |

这 4 件在本地 `assets/icons-items/` 里也没有图标（属于本地数据快照之后新加的物品），
因此页面上是「白底空格子」——比原来显示破损图标占位更干净。不编造图标。

### 1.5 接线改动

| 位置 | 改动 |
|---|---|
| `app.js` 新增 `GEAR_ICON_DIR` / `gearIconUrl()` / `setGearIcon()` | 白底图标 URL + 两级回退（白底 PNG 缺失 → 原 webp → 原图也缺失则 `visibility:hidden`） |
| `renderNameCell()`（名称列图标） | 改用 `setGearIcon` |
| `gearColumns` 的 `ico` 列 | 同上 |
| 枪械预设列表的图标列 | 同上（`row.gunId`） |
| 节点行图标 / 枪械组图标 / 附件小图标 / 插板位缩略图 | 同上（4 处） |
| 卡片板 `lw-cell-icon`（已装备物品的大图标） | 同上 —— 否则卡片是白/浅蓝底、图标却是一块深色方块，与列表割裂 |
| `style.css` `.loadout-workbench .tbl-icon` | `background: transparent` → **`background: #ffffff`** |

**只改配装工作台**：`itemIconUrl()` 保持原样，弹药表、弹药图标、弹道散点图、
配枪页继续使用原 webp，不受影响。

---

## 二、左侧空槽：完整 AK-74 / Glock 17 剪影

### 2.1 「像机匣部件」的根因（逐条排除）

按任务给的五个可能逐项核实：

| 可能原因 | 核实结果 |
|---|---|
| ① 源素材本身就是机匣或枪械部件 | **是** —— 见下 |
| ② 物品 ID 映射错误 | 否。`5bf3e03b0db834001d2c4a9c` = 「AK-74 5.45x39 突击步枪」（`pt=Weapon`），`5a7ae0c351dfba0017554310` = 「Glock 17 9x19 手枪」（`pt=Weapon`），映射正确 |
| ③ 原始完整枪械图被错误裁切 | 否。上游图本身就是这样，不是我们裁的 |
| ④ Alpha 提取或填洞损坏轮廓 | 部分是（见 2.3），但不是「缺枪托」的原因 |
| ⑤ 缩放 / 画布 / object-fit 裁掉枪身 | 否。画布 260×106 与图比例接近，`contain` 无裁切 |

**真正原因**：EFT 里**枪托与握把是可拆的独立配件**（`mod_stock` / `mod_pistol_grip`），
所以枪械**本体**的展示图只渲染「机匣 + 枪管 + 弹匣」，不含枪托。
实测本体 base-image：`5bf3e03b…` 尺寸 253×64，Alpha 包围盒 `(11,7)–(240,56)`，
图里从左到右只有枪口制退器 → 护木 → 机匣 → 弹匣，右端在机匣尾部就被截断。

对照图：`before-after-gun-source.png`（本体图 vs 预设图）、
`before-after-gun-silhouette.png`（旧剪影 vs 新剪影）。

### 2.2 改用「预设」的完整装配图

EFT 物品数据里有 `pt = Preset` 的预设条目，代表**完整装配形态**，图里枪托齐全：

| 槽位 | 槽位代表的装备 | 取图用的预设 | 预设图尺寸 |
|---|---|---|---|
| 主武器 1 / 2 | AK-74 5.45x39 突击步枪 `5bf3e03b0db834001d2c4a9c` | 「AK-74 5.45x39 突击步枪 默认」`5c0c1ce886f77401c119d014` | 316×127 |
| 手枪 | Glock 17 9x19 手枪 `5a7ae0c351dfba0017554310` | 「Glock 17 9x19 手枪 默认」`5a88acfb86f77457fd2c0d8f` | 127×64 |

`tools/build_slot_placeholders.py` 的 `SLOTS` 增加了第 6 列「取图用的物品 id」，
manifest 里同时记录 `itemId`（槽位代表的真实装备）与 `assetItemId`/`assetItemName`
（实际取图的预设）+ `assetReason`，两者不混淆。

### 2.3 顺带修掉的填洞缺陷

原 `fill_holes(max_ratio=0.04)` 会把「被包围且面积 < 主体 4%」的孔填实。
实测 Glock 的**扳机护圈**孔约占主体 3.8%，正好被填平 —— 剪影退化成一块实心黑，
这也属于「损毁可辨认轮廓」。

阈值下调到 **1.5%**（`max_ratio=0.015`）：小噪点仍被填，扳机护圈、刺刀挂环、
耳机头梁内圈、头盔面罩开口全部保留。新测试用「画布边界泛洪后的内孔面积」做断言
（`primary` 71 px、`holster` 211 px）。

### 2.4 结果

| 剪影 | 内容 | 墨迹占比 | 内孔 | 横向跨度 |
|---|---|---|---|---|
| `primary.png`（260×106） | 枪口制退器 / 准星 / 护木 / 机匣 / 弹匣 / 握把 / 扳机护圈 / 木制枪托 | 17.8% | 71 px | 88.1% |
| `holster.png`（152×106） | 套筒 / 准星照门 / 握把 / 扳机护圈 / 弹匣底板 | 36.5% | 211 px | 85.5% |

其余 8 个槽位的剪影与 R18.1 一致（未改），头盔 / 耳机 / 眼镜 / 刺刀的大尺度镂空保留。

---

## 三、修改的文件

| 文件 | 性质 |
|---|---|
| `app.js` | 新增白底图标 URL 与两级回退；8 处图标调用改用它；`AM_BUILD` → `R18.2` |
| `style.css` | `.loadout-workbench .tbl-icon` 背景改纯白 |
| `index.html` | 四个资源版本 `?v=r18.1` → `?v=r18.2` |
| `tools/build_gear_icons.py` | **新增**：白底图标生成器 |
| `tools/build_slot_placeholders.py` | 支持「取图物品 ≠ 槽位装备」；填洞阈值 4% → 1.5%；fetch 补 UA/Referer |
| `tools/r182_accept.py` | **新增**：本轮真实浏览器验收脚本 |
| `tools/r182_compare.py` | **新增**：前后对照图生成（证据，可复现） |
| `tests/test_r18_2_round.py` | **新增**：13 个测试 |
| `tests/test_r18_1_round.py` | 轮次断言改为 `R18\.\d+`（不写死具体版本） |
| `assets/icons-items-white/` | **新增**：859 张白底图标 + `manifest.json` |
| `assets/ui/placeholders/` | `primary.png` / `holster.png` 重制；`_src` 增加 2 张预设图；manifest 记录来源 |
| `docs/ui-windows-xp/r18.2/` | **新增**：19 张截图 + 2 份报告 |
| `docs/STARTUP.md` | 构建标记由 R18.1 更新为 R18.2 |

**未改**：`combat_sim.js`（一行未动）、弹药 / 护甲 / Boss 任何计算、装备兼容与配装逻辑、
地图与配枪页、`assets/icons-items/*.webp`（原始素材只读）、`release/`。

---

## 四、Git 状态

- 未 `git add` / `commit` / `push`，未删除任何未跟踪文件。
- 新增未跟踪内容：`assets/icons-items-white/`（6.5 MB）、`tools/build_gear_icons.py`、
  `tools/r182_accept.py`、`tools/r182_compare.py`、`tests/test_r18_2_round.py`、
  `docs/ui-windows-xp/r18.2/`。
- `build-cache/gear-icons-src/`（18 MB 上游源图）已被 `.gitignore` 排除，不进仓库；
  需要重建时 `python tools/build_gear_icons.py` 会重新下载。
