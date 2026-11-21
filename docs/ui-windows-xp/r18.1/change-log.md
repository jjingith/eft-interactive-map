# R18.1 变更记录（XP 主题细节修正 / 配装空槽剪影 / 目标护甲分组）

日期：2026-10-24 · 基线版本：R18（Windows XP Luna Blue 全站换肤已完成）
构建标记：`AM_BUILD = "R18.1"`，`index.html` 资源版本 `?v=r18.1`（四个资源同步）
范围：定点改进，未重做全站 UI，未改弹道公式 / 护甲损毁公式 / 数据文件。

---

## 一、配装工作台：空装备槽换成「白底 + 纯黑装备剪影」

### 1.1 素材选择过程（为什么不用现成的 64px 图标）

先按任务要求检查了项目已有的本地素材，结论如下：

| 候选素材 | 实际情况 | 结论 |
|---|---|---|
| `assets/icons-items/{id}.webp` | 上游 `assets.tarkov.dev/{id}-icon.webp` 抓来的 **64×64 不透明**图标，深色底 + 纹理噪点，物品本身也常常是深色 | 需要前景分割，实测不可靠（见 1.2） |
| `assets/slot-glyphs/*.png` | R4 从布局参考图抠出来的透明底**剪影灰**图形，与"指定装备的真实轮廓"无关 | 不满足"按指定装备出剪影" |
| `assets/icons/*.png` | 钥匙 / 箱子 / 贵重品，不是装备 | 不适用 |
| `assets.tarkov.dev/{id}-base-image.webp` | **透明底**大图（127–442 px），Alpha 通道即真实轮廓 | **采用**（构建期下载，运行期只用本地文件） |

### 1.2 被放弃的做法：从 64px 不透明图标做前景分割

`tools/build_slot_placeholders.py` 里保留了这条回退路径（`split_foreground()`），
但**本轮 10 张全部走的是 Alpha 主路径**。记录一下踩到的坑，避免以后重复：

1. 直接按亮度阈值分割 → 得到**整块黑色方块**（任务书明确禁止的结果）。
   原因：背景是带 ±10 抖动的深色纹理，物品暗部亮度与背景只差 5–10 个灰阶。
2. 改用 Otsu 颜色距离 → 头盔面罩、刀身、枪身内部被掏空成**镂空剪影**。
   原因：这些区域的色差低于阈值。
3. 加 Sobel 梯度可达性 → 仍有断口泄漏，枪与匕首断成两截。
4. 最终回退方案 = 中值滤波 + 背景基准中位色 + BFS 区域生长（局部色差 ∧ Otsu 全局距离）
   + 闭运算封口 + 补洞。对 64px 素材仍属"能用但边缘毛糙"，因此**不用于正式产物**，
   只在 `_src` 缺失时兜底，并在 manifest 里如实标 `source: "icons-items-fallback"`。

### 1.3 最终产物

生成器：`tools/build_slot_placeholders.py`（构建期，依赖 Pillow；运行期零依赖）
处理链：Alpha 二值化(>128) → 去孤立碎块(<12px) → 填「被包围且面积<主体 4%」的小孔
→ 等比缩放居中（留白 6%）→ 4× 超采样后 LANCZOS 缩小。

填洞设面积上限是为了**保留大尺度镂空**：耳机头梁内圈、头盔面罩开口、护目镜两片镜片之间、
刺刀挂环都是装备的可辨认特征，填掉之后剪影会退化成难以辨识的黑色团块。

| 槽位 | 参考装备 | 画布 | 产物路径 |
|---|---|---|---|
| helmet | HighCom Striker ULACH IIIA（黑）`5b40e1525acfc4771e1c6611` | 76×76 | `assets/ui/placeholders/helmet.png` |
| armor | 6B45 防弹衣 `68948a95d8f2b85fb705e2a6` | 106×105 | `assets/ui/placeholders/armor.png` |
| rig | Azimut SS "Zhuk" 胸挂（黑）`603648ff5a45383c122086ac` | 106×105 | `assets/ui/placeholders/rig.png` |
| backpack | Pilgrim 旅行包 `59e763f286f7742ee57895da` | 106×106 | `assets/ui/placeholders/backpack.png` |
| headphones | Peltor ComTac VI（狼棕）`66b5f6985891c84aab75ca76` | 63×61 | `assets/ui/placeholders/headphones.png` |
| glasses | NPP KIASS Condor 护目镜 `603409c80ca681766b6a0fb2` | 63×61 | `assets/ui/placeholders/glasses.png` |
| face | 巴拉克拉瓦头套 `572b7f1624597762ae139822` | 63×61 | `assets/ui/placeholders/face.png` |
| primary1 / primary2 | AK-74 5.45x39 `5bf3e03b0db834001d2c4a9c`（同一文件复用） | 260×106 | `assets/ui/placeholders/primary.png` |
| holster | Glock 17 9x19 `5a7ae0c351dfba0017554310` | 152×106 | `assets/ui/placeholders/holster.png` |
| melee | ER「支点」刺刀 `54491bb74bdc2d09088b4567` | 106×106 | `assets/ui/placeholders/melee.png` |

- 画布尺寸 = `style.css` 里对应卡片的**实际内框**（网格轨道 65/19/33/37/108 列 × 78/107/108 行，
  扣 1px 边框），因此 `object-fit: contain` 后白底正好铺满卡片，不露底色。
- 源素材保留在 `assets/ui/placeholders/_src/{id}.webp`（10 张，296 KB），
  来源 URL 与处理参数记录在 `assets/ui/placeholders/manifest.json`，可复核、可重建。
- 原始 `assets/icons-items/*.webp` 与 `assets/slot-glyphs/*.png` **只读未改**。

### 1.4 接线改动

| 位置 | 改动 |
|---|---|
| `app.js` `SIL_DIR` | `assets/slot-glyphs/` → `assets/ui/placeholders/` |
| `app.js` `LW_SIL_FILE` | 新增 `primary1/primary2 → primary`、`holster → holster`；`torso` 移出该表 |
| `app.js` `silKey()` | 去掉"三者共用 gun"的特判，改为查表 |
| `app.js` `silSrc()` | 新增：`torso`（中列装饰，非装备槽）走旧的 `SIL_DECO_DIR` |
| `app.js` `silImg()` | 删除 `if (key === "face")` 的巴拉克拉瓦物品图标特例，全部走剪影 |
| `style.css` `.lw-sil` | 增加 `background: #fff` 兜底 1px 取整缝隙 |
| `style.css` `.lw-sil-face` | 删除（grayscale + opacity 会把黑剪影二次降饱和） |
| `theme-windows-xp.css` | `.lw-sil { mix-blend-mode: multiply }`（见下） |

**为什么用 `multiply`**：卡片在 XP 主题下是白底，剪影白底与之一致；但选中态
（`data-state="focus"`）卡片底是浅蓝 `#dbe7f7`，白底图会盖出一块白方块。
`multiply` 让白色参与混合后与卡片底色完全一致、黑色保持不变，选中态只呈现
"黑剪影 + 浅蓝卡底"。躯干装饰那张旧剪影是深灰透明底，单独排除在 multiply 之外。

**顺带修的一个回归**：剪影变纯黑之后，R18 已压成深色的槽位名（`#232323`）叠在黑剪影上
几乎看不见（截图里"主武器 1 / 背包 / 手枪"几乎消失）。给 `.lw-cell-label` 加了一层
半透明白底衬（`rgba(255,255,255,.88)` + 3px 横向内边距），黑剪影 / 彩色实物图标 /
浅蓝选中底三种情况都能读，卡片尺寸与剪影位置不变。

---

## 二、XP 主题三处文字对比度

### 2.1 配装左侧装备栏的悬停提示

- **真实背景**：`#ece9d8`（XP 浅米色，R18 把 `.lw-tip` 从 `#0b0e13` 翻过来的）。
- **根因**：R18 同时改了 `.lw-tip-line`（`#b9c2cf` → `#232323`），
  但**漏掉了第一行的 `.lw-tip-head`**，它仍是 `style.css` 里的 `color: #fff`。
  于是"白字 + 浅米底"，实测对比度约 1.15:1。
- **修正**：`html .loadout-workbench .lw-tip .lw-tip-head { color: #000 }`，
  正文行统一 `#232323`。**未使用文字阴影**。
- **实测**：标题行 `rgb(0,0,0)` on `rgb(236,233,216)` → **17.21:1**；
  正文行 **12.88:1**。两个不同位置的提示（来源区块 `.lw-src`、插板位 `.lw-plate-cell`）
  都在视口内完整显示，未被侧栏或表格裁切。

### 2.2 弹药页 BALLISTICS graph

- **根因**：散点图用 SVG **presentation attribute** 上色（`fill="#7b8593"` 等），
  R18 已用属性选择器把画布底 / 网格 / 坐标刻度 / 轴标签翻成浅底版；
  漏的是**悬停提示里的弹药名称**：`.am-graph-tip` 底色已翻成 `#ece9d8`，
  但 `.am-graph-tip-row` 仍是 `#dfe6ee`、`.am-graph-tip-name` 无显式颜色（继承行色），
  浅白字落在浅底上等于隐形。
- **修正**：`row` → `#232323`，`name` → `#000` + 700 字重（hover → `#0a3f9e`），
  `meta` → `#4a4a4a`；图例与说明文字统一压到 `#232323`。
- **实测**：坐标轴刻度 `rgb(74,74,74)`（14 个文本节点）、轴标签 `rgb(35,35,35)`、
  绘图区 `rgb(255,255,255)`；悬停提示弹药名 **17.21:1**、次级信息 **7.26:1**。
  散点颜色分类、数据、坐标、公式、图例对应关系、点击交互**均未改动**。

### 2.3 弹药详情弹窗标题栏

- **根因**：标题栏是 Luna 蓝渐变（`#1466e0 → #0a3f9e → #08327c`），
  `.am-modal-title` 已设白字，但 `.am-detail-meta`（口径 · 类型 · 分组，
  即用户看到的 `FMJ.357 · 子弹 · PISTOL/SMG` 后半段）在 R18 被单独设成 `#4a4a4a` 深灰。
- **修正**：`html .am-modal-head .am-detail-meta { color: #ffffff }`，
  与标题、关闭按钮同一套配色，保留蓝渐变与窗口风格。
- **为什么用纯白而不是灰白**：渐变最亮端 `#1466e0` 上，灰白 `#dbe7fb` 只有约 4.4:1，
  纯白全段 ≥ 5.7:1。
- **实测**：四种不同口径/分类（`5.45x39 · RIFLE ROUNDS`、`7.62x25 · PISTOL/SMG`、
  `.357 · PISTOL/SMG`、`12g · SHOTGUN ROUNDS`）的 `meta` 均为 `rgb(255,255,255)`，
  对比度 **5.72:1**；标题 `#ffffff`。

---

## 三、目标护甲 / 插板选择器分组

### 3.1 采用的数据字段

| 选择器 | 分组依据 | 具体字段 | 为什么不是别的字段 |
|---|---|---|---|
| 目标护甲 | **内衬**等级 + 内衬材质 | `items[].aps[]` 中 `fx === 1` 的条目，取 `cl` 最高的一条，用它的 `cl` / `mat` | 与引擎 `amSimArmorLayers()` 的内衬层取数**完全同源**；护甲本体 `cl` 是"本体防护等级"（往往来自可换硬插板），不能当内衬等级 |
| 插板 | **插板自身**防护等级 + 材质 | 插板物品的 `cl` / `mat` | 插在哪个护甲上不影响它自己的等级与材质 |

关键区分（截图中可直接看出）：`Ferro Concepts FCPC V5 插板胸挂 · 本体 5 级` 落在
**`IV · 复合材料 · 内衬`** 组里 —— 本体 5 级、内衬 IV 级，两者确实不同。
分组标签对护甲显式带 `· 内衬` 后缀，条目文本对护甲显式写 `· 本体 N 级`，
避免把"本体等级"读成"内衬等级"。

### 3.2 排序规则

1. 正常组在前 → `无内衬` → `内衬数据未知`（不猜归属）。
2. 等级降序（VI → I）。
3. 同级内材质固定序：`陶瓷 → 钛合金 → 装甲钢 → 超高分子量聚乙烯 → 复合材料 → 铝合金 → 芳纶 → 防弹玻璃`（`AM_SIM_MAT_ORDER`，未知材质排最后）。
4. 同材质组内按名称 `localeCompare("zh-Hans-CN")` 稳定排序。

空组不生成 —— 数据里不存在的等级/材质组合不会凭空出现一个空分组。

### 3.3 当前实际覆盖（真实数据，非虚构）

护甲（`pt=Armor` 或 `slot=rig 且 cl>0`，共 108 件）：

| 分组 | 件数 |
|---|---|
| IV · 陶瓷 · 内衬 | 1 |
| IV · 钛合金 · 内衬 | 1 |
| IV · 复合材料 · 内衬 | 2 |
| III · 钛合金 · 内衬 | 1 |
| III · 装甲钢 · 内衬 | 2 |
| III · 铝合金 · 内衬 | 1 |
| III · 芳纶 · 内衬 | 52 |
| II · 钛合金 · 内衬 | 1 |
| II · 芳纶 · 内衬 | 37 |
| 无内衬 | 10 |

- 任务书示例里的 `I · 芳纶 · 内衬` **在真实数据中不存在**（没有 I 级内衬的护甲），
  因此不显示该分组，也未虚构。
- `内衬数据未知` 组当前为空（108 件全部能确定内衬等级与材质）。

插板（被 `aps[].plates` 引用的 38 件）：

| 等级 | 材质组合 |
|---|---|
| VI | 陶瓷 8 / 超高分子量聚乙烯 2 / 钛合金 1 / 装甲钢 1 / 复合材料 1 |
| V | 陶瓷 5 / 装甲钢 3 / 超高分子量聚乙烯 1 / 钛合金 1 / 复合材料 1 |
| IV | 装甲钢 4 / 陶瓷 1 / 超高分子量聚乙烯 1 / 钛合金 1 / 铝合金 1 / 复合材料 1 |
| III | 超高分子量聚乙烯 2 / 复合材料 1 / 装甲钢 1 |
| I | 超高分子量聚乙烯 1 |

- 共 20 个组；`等级或材质缺失` 组当前为空（38 件都有 `cl` 与 `mat`）。
- 数据里没有 II 级插板，因此不显示 `II · ...` 组。

### 3.4 兼容性约束（分组没有放宽任何规则）

分组只改变**展示顺序**，不改变候选集合：

- 护甲候选：`amSimGearCatalog("armor", allowedA)` 先按「根槽位 + Boss 装备池白名单」过滤，
  再交给 `amSimFillGrouped()`；
- 插板候选：`socket.plates`（当前护甲的插板位兼容集合）→ 再按 `platePol.bySide`
  （Boss 预设的前/后/左/右白名单）过滤 → 最后才分组；
- 前/后方向性计算、软内衬与插板独立耐久、已选物品 id / 耐久 / 保护区域、
  更换目标或护甲时的状态重置与合法性校验，全部未改动（`combat_sim.js` 一行未动）。

**实测（Tagilla）**：目标切到 Boss → Tagilla 后，护甲下拉只剩 3 个 option
（2 件 verified 白名单护甲 + "无护甲"，分 2 组）、插板下拉只剩 2 个 option
（1 块插板 + "未安装"，1 组 `VI · 钛合金`）—— 分组没有把全局 20 组插板放出来。

---

## 四、边界与保护

- 地图 / 缩放平移 / 路线 / 标记 / 定位：未改。
- 配装装备兼容性与真实物品图标：未改（选中后仍显示 `assets/icons-items/{id}.webp`）。
- 枪械构建页与配件关系：未改。
- 弹药数据库与弹道图表数据：未改（只改文字颜色）。
- 逐发模拟器命中率 / 随机种子 / 命中分布：未改。
- Top / Loop / Bottom 预设弹匣与拖拽：未改。
- Boss 装备池、前后方向性、多层内衬与插板计算：未改。
- `app.js` 未重写（只改了 `AM_BUILD`、剪影映射/silImg、以及新增分组函数 + 两处渲染调用）。
- `combat_sim.js` 一行未动。
- `theme-windows-xp.css` 仍是集中主题层，本轮新增规则全部带 `html <原作用域>` 前缀，
  只改颜色 / 混合模式，无布局声明。
- 运行期零外部网络请求（Chrome Network 事件实测 0 条外部请求）；
  构建期下载素材走用户指定代理 `http://127.0.0.1:7896`。
- **未提交 Git、未推送、未覆盖 `release/`**；未执行 `git add .`，未清理任何未跟踪文件。
