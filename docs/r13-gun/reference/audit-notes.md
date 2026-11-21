# 第十三轮 · 枪械构建页参考站审计记录（db4tarkov.com/gun）

- 审计日期：2026-10-21
- 参考地址：`https://db4tarkov.com/gun`
- 访问方式：真实 Chrome（CDP 端口 9224），`Page.navigate` 打开页面，`Page.captureScreenshot` 落盘。
  该站与弹药页同为 **Flutter Web（canvas 渲染）**，常规 DOM 选择器拿不到表格行与按钮，
  交互以坐标点击 + 截图反馈驱动；页面文本仅能通过 `flt-semantics-host` 读取部分语义节点。
- 截图文件：与本文件同目录的 `ref-gun-*.png`。
- 记录原则：以下均为截图中可直接确认的内容；无法确认的细节在末节单列，不做推断性补全。

## 1. 初始页：枪械墙（未选中枪械）

对应截图：`ref-gun-initial.png`（1920×1080 视口）。

- 顶栏：`MARKET / SEARCH / QUEST / KEEP? / GUN / AMMO / MAP / BARTER / CRAFT / CHANGES / LOGS`，
  当前页签 `GUN` 高亮为琥珀色；右上为个人菜单与语言切换。
- 左侧筛选轨（自上而下）：
  1. `PRIMARY / HANDGUN` 两个切换；
  2. `CLASS FILTER` 输入框；
  3. `CALIBER FILTER` 输入框；
  4. `Auto / Single / Burst / Bolt / Load` 五个射击模式筹码（可多选，蓝色为已选）。
- 主区为**按口径分组的枪械墙**：左侧竖排口径标签（截图中可见 `300`、`5.8x42`、`5.56x45`、
  `5.45x39`、`4.6x51`、`7.62x39`、`7.62x51`、`7.62x54R`、`300`），
  同一口径的所有枪械在一条横向色带上连续排列。
- 每把枪显示：物品图标 + 短名称（`M4A1`、`AKM`、`AK-74N`、`HK416A5` 等），
  名称右侧跟 1–3 个带颜色的小圆徽标（数字为可改装件/阻断件计数，绿/红/白三色）。
- 整墙没有分页器，长列表纵向滚动；枪械墙是“选枪入口”，不是可编辑区。

## 2. 点击枪械后的 Gunsmith 工作区

对应截图：`ref-gun-after-click.png`、`ref-gun-modpicker.png`、`ref-gun-modpicker2.png`。

点击任意枪械后进入三栏工作区（截图实测：左栏约 240 px、中栏约 512 px、右栏约 807 px，
中/右栏之间为可拖动的分隔条）：

### 2.1 左栏 · FORGE 生成器

- 顶部 `BUILD / LOAD STOCK` 两个页签，其下 `BASIC / ADVANCED` 与 `ABOUT`。
- `GENERATOR SETTINGS` 分组：
  - `SUPPRESSED`：`OFF`；
  - `BUYABLE`：`ON`；
  - `BARREL`：`All / Barrels`；
  - `MASS`：滑杆；
  - `SCOPE`：`CLOSE / MID / RANGE`；
  - `TACTICAL`：`OFF` 开关；
  - `BLOCKED (0)`、`FORGED (0)` 两个可搜索列表；
  - `GENERATE BUILDS` 按钮（灰显，说明当前条件下未生成）。
- 这一栏是**自动配枪生成器**，与手动改装并列；本轮只复刻手动改装路径。

### 2.2 中栏 · 枪械画布与整枪数据

- 顶部工具条：`FORGE`、`Compare`、`Changes`、`Gunsmith`、`Streamer`、`Variant`、`Saved`
  等页签；右上还有 `wolfpack / wagP / WWQ / off / Offal / Trader / Jubilee` 等预设筹码。
  这是参考站自己的**预设/变体体系**。
- 画布：深色网格背景下的枪械俯视/侧视线框渲染，槽位以图标 + `O` 标记叠加在枪体上；
  右侧是配件图标网格。
- 属性区：`Ergonomics` 进度条 + 数值，`Vertical Recoil`、`Horizontal Recoil` 为双向条 + 数值，
  `Modifier` 行；数值随配件实时变化。
- 价格区：左侧为配件价格清单（每件配件名 + `₽` 价格），底部 `Buy ()` / `Sell ()` 两个合计。
- 页面水印 `db4tarkov.com` 固定在中栏右下。

### 2.3 右栏 · Pick a mod

- 未选中槽位时显示空态文案 `Pick a mod`。
- 选中槽位（或点击枪体上的槽位标记）后，右栏变为配件候选表，表头可排序，列为：

| 列 | 语义 |
| --- | --- |
| DBBS | 配件名称；与当前槽位不兼容的项前置红色 `✕` |
| Market | 跳蚤市场价（`₽`，部分为空） |
| Trader | 商人等级与价格（图标 + 价格） |
| Buy | 购买价 |
| Craft | 制作来源 |
| Barter | 以物易物 |
| Pen / Dmg / ArD | 穿透 / 伤害 / 护甲伤害（枪械页对部分配件列为空） |
| Acc / Recoil / Frag | 精准度 / 后坐力 / 碎裂 |
| Speed / Ricochet | 初速 / 跳弹 |
| C1 … C6 | 对 1–6 级护甲的评级色块 |

- 选中候选后即安装，枪体槽位标记、属性条、价格清单与 `Buy/Sell` 合计同步刷新。
- 再次点击已安装槽位可更换；参考站通过页签/按钮卸载，未见右键菜单。

## 3. 与本地实现的对照结论

| 参考站行为 | 本地实现 | 说明 |
| --- | --- | --- |
| 按口径分组的枪械墙 | 有（`#gw-browse`，口径分组 + 名称排序 + 当前枪高亮） | 口径尾缀统一（如 `7.62x39`），与参考站左侧口径标签同义 |
| 枪械搜索 | 有（`#gw-search`，按名称/短名，最多 24 条） | 参考站搜索在筛选轨；本地放在顶栏 |
| 左栏槽位树 | 有（`#gw-tree`，父子槽 + 动态子槽 + `×` 卸除） | 参考站的槽位叠加在枪体上，本地为文本树 |
| 中栏枪械展示 | 有（64×64 本地物品图标 + 名称/槽位/配件数 + 重量/价格/人机工效/后坐筹码） | **不复制参考站 canvas 渲染**：项目离线且无 3D 资产，见第 5 节 |
| 整枪属性 | 有（基础数值 + 配件增量 + 后坐修正合计） | 数据来自 `data/gunslots.json` 与 `data/items.json` 的 `mod.e` / `mod.r` |
| 价格清单 / Buy / Sell | 部分（整枪 FLEA 快照合计 + 缺价计数） | 本地无商人实时价、无 Sell 报价，不伪造 |
| 右栏候选表 | 有（深色表格：配件 / 重量 / FLEA 价 / 人机工效增减 / 后坐修正 / 可扩展槽 / 状态） | 列集按本地可用字段裁剪，见第 5 节 |
| 不兼容项标红拦截 | 有（`tbl-conflict` + `⛔ 互斥` 文案 + 点击被拒） | 依据上游 `conflictingItems`，双向校验 |
| 预设保存 / 加载 | 有（复用项目既有预设弹窗与 `%APPDATA%\EFTMap\weapon-presets.json`） | 参考站的 Variant/Streamer/Saved 体系未照搬 |
| FORGE 自动生成 | 无 | 属参考站独有生成器，非本轮任务范围 |
| C1–C6 护甲评级 | 无 | 参考站未公开算法，不伪造 |
| Compare / Changes / 变体 | 无 | 同上 |

## 4. 参考站可确认的交互顺序

1. 初始墙 → 点击枪械 → 进入 Gunsmith（枪体 + 槽位 + 属性 + 价格）。
2. 点击槽位标记 → 右栏 `Pick a mod` 变成候选表。
3. 点击候选 → 安装；属性条、价格清单、Buy/Sell 合计同步变化。
4. 点击另一把枪 → 中栏枪体与右栏内容整体替换，不保留上一把枪的配件。
5. 顶部 `Saved` / 预设筹码 → 载入参考站自己的方案。

以上第 1–4 步在本地均有对应实现；第 5 步以项目既有预设体系等价实现。

## 5. 无法确认 / 未照搬的部分（如实记录）

1. **枪体渲染**：参考站为 Flutter canvas 绘制的线框枪体；本地无对应 3D/2D 拆分资产，
   只展示本地 `assets/icons-items/<id>.webp`（统一 64×64），按原尺寸显示避免放大糊化。
   这是本轮最大视觉差异，已记录为已知缺口。
2. **Market / Trader / Buy / Craft / Barter 分列**：本地只有构建期 FLEA 快照价，
   商人等级/制作/以物易物字段未打包，故合并为单列 FLEA 价并对缺价单独计数。
3. **C1–C6 穿透评级**：参考站未给出计算式，本地不输出该列。
4. **FORGE 生成器、Compare、Changes、Variant/Streamer/Saved**：均为参考站专有功能，
   不属于“可交互枪械构建器”的必需项，本轮未实现。
5. **射击模式筛选（Auto/Single/Burst/Bolt/Load）**：本地 `gunslots.json` 未打包射击模式字段，
   不按名称猜测，故未实现；口径筛选由浏览墙分组承担。
6. 参考站素材（图标、字体、枪体图）均未复制进项目；本地只使用项目自有图标与字体。
