# R19.6 布局审计与验收记录

- 开发服务：`http://127.0.0.1:8787/`（`tools/serve.py --port 8787 --no-browser`）
- 服务进程：PID 29936，`cwd` = `D:\personal\trae\02-塔科夫\eft-interactive-map`（与项目目录一致）
- 页面运行版本标记（`<html data-build-rev>` / 页面右下角徽标）：**R19.6-1d5c707f**
  - 指纹由 `/api/build` 对 `index.html / style.css / theme-windows-xp.css / app.js / gun_builder.js / combat_sim.js` 逐文件 sha256 计算
  - 截图时的 `app.js` sha256 = `f033e1707400c882873b0ae68deaaae3f3525ef6526b415807670bfec3f7cd5a`，`style.css` = `38467bca4df575393de85115bd684ab6235279c2adf87ae5b65be7c3853fc796`，均与磁盘一致
- 本轮所有截图都在禁用缓存（`Network.setCacheDisabled`）后导航取得

## 1. 修改文件与实际改动

| 文件 | 改动 |
| --- | --- |
| `app.js` | 新增 R19.6 布局引擎 `gwSidBase / gwLaneOf / gwSlotVisible / gwBuildLayout`；重写 `renderGunTree()` 为 CSS Grid 渲染（`--gw-cols`、`gridRow/gridColumn`、`data-parent/data-lane/data-row/data-col/data-item`）；新增 `gwDrawLinks / gwBindLinksRedraw` 按实测 DOM 位置画父子连接线；`gwPartCard` 空槽标签支持 B.A.D；删除旧 `gwZoneOf / GW_ZONE_ORDER / gwZoneRank / gwFlatten / gwClusterRow` 与整段带式渲染；构建标记 `AM_BUILD = "R19.6"` |
| `style.css` | 末尾新增 R19.6 段（L5017–5132）：三栏 FORGE 收窄、FORGE 内部字号/间距收紧、`.gw-canvas.gw-grid` 网格画布与正方形卡片、枪身 3 列卡、子弹格 |
| `index.html` | 中栏 DOM 顺序改为 LOAD VARIANT → 画布 → 属性条 → 整枪属性 → 隐藏属性 → 其余；删除重复的 `#gw-nodecanvas`；全部资源版本串改 `?v=r19.6` |
| `tools/serve.py` | `/api/build` 的 `rev` 前缀由 `R19.5e-` 改为 `R19.6-`（重启服务后生效） |
| `tests/test_r19_6_round.py` | 新增本轮 7 项回归（FORGE 压缩、中栏顺序、网格布局、槽位状态区分、M4A1 参考行列、交互契约、版本串） |
| `tests/test_r19_5_round.py` | 装配画布断言对齐结构化网格；删除/替换已废弃的带式分区断言（未放宽其它契约） |
| `tests/test_r19_2/19_3/19_4_round.py` | 仅版本标记断言同步到 R19.6 |

未改动：地图渲染、地图图标、路线、任务、配装工作台、弹药数据。未提交/推送 Git，未覆盖 `release/`。

## 2. FORGE 实际尺寸（截图实测，非代码数字）

| 指标 | 修改前（R19.5e） | 修改后（R19.6） | 1920→1384 |
| --- | --- | --- | --- |
| FORGE 栏宽 | 461px | **236px** | 208px |
| FORGE 内边距 | 10px 12px 16px | **6px 8px 10px** | 同 |
| FORGE 基础字号 | 12px | **10px** | 同 |
| 标题字号 / 行高 | 13px | **11px / 1.1** | 同 |
| 副标题字号 / 外边距 | 10px / `2px 0 10px` | **9px / `1px 0 6px`** | 同 |
| 分区下间距 | 12px | **7px** | 同 |
| FORGE 标题块高度 | 20px | **12px** | 同 |
| 三栏列宽 | 461 / 461 / 922 | **236 / 964.8 / 643.2**（`@media ≤1500px`：208 / 691 / 461） | — |

压缩规则全部限定在 `.gun-workbench .gw-forge` / `.gw-buildpage` 内，未改全局样式。

三栏比例变化有明确依据：原 `1fr 1fr 2fr`（1920 下 461 / 461 / 922）里中栏 461px 放不下 9 列网格（9×58 ≈ 522），
因此改为 `minmax(196px,236px) minmax(0,1.5fr) minmax(300px,1fr)`（236 / 965 / 643）。
右栏 643px 仍完整容纳候选表的 6 列，右侧候选功能未受影响（截图可见列头与数据完整）。

## 3. 中栏最终顺序（真实 DOM）

`#gw-cmp`（隐藏）→ `#gw-loadvar`（LOAD VARIANT）→ **`#gw-tree`（装配画布）→ `#gw-bars`（属性条）→ `#gw-stats`（整枪属性）→ `#gw-hidden`（隐藏属性）** → `#gw-focus` → `#gw-ammo` → `#gw-bottom`

- 顺序由文档流实现，R19.6 段内没有 `order`、`position: absolute`、负 margin 挪位
- 切换枪械 / 刷新 / `build` 与其它模式来回切换后，顺序不变（6 次截图均为同一 `centerOrder`）

## 4. M4A1 实际行列布局（1-based，数据来自真实槽位树）

默认装配 `柯尔特 M4A1 5.56x45 卡宾枪 Carbine`，画布 9 列 × 5 行。

| 行 | 列 → 内容 |
| --- | --- |
| 1 | 空×7 → **col8 `mod_reciever/mod_sight_rear/mod_scope`**（scope 空槽位）→ 空 |
| 2 | 空×4 → col5 `mod_reciever/mod_scope`（scope 槽位，空）→ 空×2 → **col8 `mod_reciever/mod_sight_rear`（AR-15提把式照门 = chandle）** → col9 `mod_charge`（柯尔特 AR-15 拉机柄） |
| 3 | col1 `mod_muzzle`（USGI A2 消焰器）→ col2 `mod_gas_block`（柯尔特 M4 准星）→ col3 `mod_barrel`（14.5 英寸枪管）→ col4 `mod_handguard`（M4 上护木）→ col5 `mod_reciever`（M4A1 上机匣）→ **col6–8 枪身（占 3 列）** → col9 `mod_stock`（缓冲管） |
| 4 | col1 `.../mod_muzzle/mod_muzzle`（消音器槽位，空）→ 空×2 → col4 `.../mod_handguard/mod_handguard`（M4 下护木）→ 空 → col6 `mod_charge_001`（B.A.D 配件栏）→ col7 `mod_magazine`（弹匣）→ col8 `mod_pistol_grip`（握把）→ col9 `mod_stock/mod_stock_000`（M4SS 枪托） |
| 5 | 空×6 → **col7 子弹格** → 空×2 |

`scope 空槽位 ↔ chandle` 的对应方式：

- 真实数据里 `mod_reciever/mod_sight_rear` 的物品是 **AR-15 提把式照门**，它的子槽 `mod_scope` 就是第一行那个 `SCOPE` 空槽（`data-parent = mod_reciever/mod_sight_rear`）
- 因此第二行的 `mod_sight_rear` 与第一行的 `mod_scope` 在同一列（col8）上下相邻，并有 SVG 连接线相连；不是两个互不相关的瞄具槽
- 规则写在引擎里：`scope` 的父件属于 `sight_rear/sight_front/mount` 时上浮到 `top1` 行，其余留在 `top2`；`charge` 固定在主轴最右列（col9），与 `chandle` 相邻

## 5. 其它枪械验收（结构不同）

### AK-74N（`5644bd2b4bdc2d3b4c8b4572`，8 列）

- 行1：col7 `mod_sight_rear/mod_sight_rear`（照门上的子照门，父件同在 col7）
- 行2：col4 上机匣导轨空槽、col5 独立导轨空槽、col7 照门（已装）、col8 拉机柄（空）
- 行3：枪口 → 导气箍 → 护木（`mod_gas_block` 的子槽，紧贴父件右侧）→ 机匣 → 枪身 col5–7 → 枪托 col8
- 行4：弹匣 col6、握把 col7、枪托垫 col8（`mod_stock` 子槽）
- 行5：子弹格 col6
- 连接线 8 条；无重叠、无不可点击、无横向溢出

### MP5（`5926bb2186f7744b1c6c6e60`，7 列）

- 行1（归一化后）：col3 上机匣导轨空槽、col6 照门（已装）、col7 拉机柄
- 行2：枪口 col1、护木 col2、机匣 col3、枪身 col4–6、枪托 col7
- 行3：消音器空槽 col1（紧贴 `mod_muzzle` 正下方）、弹匣 col5
- 行4：子弹格 col5
- 连接线 5 条；无重叠、无不可点击、无溢出

### Glock-17（`5a7ae0c351dfba0017554310`，7 列）

- 行1：准星 col1、道轨 col4、照门 col6
- 行2：枪口空槽 col1、枪管 col2、套筒 col3、枪身 col4–6、枪托空槽 col7
- 行3：战术灯 col4（道轨下方）、弹匣 col5、握把 col6
- 行4：子弹格 col5
- 连接线 6 条；无重叠、无不可点击、无溢出

三把结构不同的枪都按各自槽位树重新计算，未套用 M4A1 模板；连续切换（M4A1 → AK-74N → MP5 → Glock-17）后卡片数为 16/13/9/10，无上一把枪的残留。

## 6. DOM 与计算样式实测

1920×919（`after/m4a1-1920x919.json`）：

- `.gw-buildpage`：`236px 964.797px 643.203px`，`column-gap: 8px`
- 画布：`display: grid`，`grid-template-columns` 9 × 57.78px，`row-gap 10px / column-gap 4px`，rect `566×377`，`scrollWidth 565 / clientWidth 564`（无横向溢出）
- 卡片（16 个槽位卡 + 枪身卡）：全部 58×58，枪身 `span 3`（181×86），行列来自 `grid-row/grid-column`
- 全部卡片内联 style 中 **没有 `left` / `top`**（`absStyles = []`）
- `elementFromPoint` 命中每张卡自身：不可点击 0 个
- 两两矩形重叠检测：0 组；枪身与任何卡片重叠：0 组
- 父子连接线：10 条
- 子弹格：`data-row=5 data-col=7 data-gap=mod_ammo`
- 中栏 `scrollWidth = clientWidth = 950`（无横向溢出）

1384×805（`after/m4a1-1384x805.json`）：

- 三栏 `208px 691.188px 460.797px`
- 画布 rect `x=271, 566×377`，列宽仍 57.78px，无溢出；中栏 `scrollWidth = clientWidth = 676`
- 属性条 / 整枪属性 / 隐藏属性 / 弹药 / 底部依次 y=521 / 593 / 677 / 784 / 843，均完整显示

AK-74N / MP5 / Glock-17 的 `absStyles = 0`、`unclickable = 0`、`bodyOverlap = 0`，画布高度分别为 404 / 360 / 360（按实际行数自然计算）。

## 7. 截图

| 内容 | 路径 |
| --- | --- |
| 修改前 M4A1 / AK-74N / MP5（1920×919） | `before/m4a1-1920x919.png`、`before/ak74n-1920x919.png`、`before/mp5-1920x919.png` |
| 修改前 M4A1（1384×805） | `before/m4a1-1384x805.png` |
| 修改后 M4A1（1920×919 / 1384×805） | `after/m4a1-1920x919.png`、`after/m4a1-1384x805.png` |
| M4A1 完整装配画布（裁剪） | `after/m4a1-canvas-1920x919.png`、`after/m4a1-canvas-1384x805.png` |
| 修改后 AK-74N（1920 / 1384） | `after/ak74n-1920x919.png`、`after/ak74n-1384x805.png` |
| 修改后 MP5 / Glock-17（1920） | `after/mp5-1920x919.png`、`after/glock17-1920x919.png` |
| 画布裁剪（另两把） | `after/ak74n-canvas-1920x919.png`、`after/mp5-canvas-1920x919.png`、`after/glock17-canvas-1920x919.png` |
| 测量数据 | 同名 `.json`（每个视口/枪械一份） |

已实际打开检查：FORGE 左栏明显变窄变紧（标题块 20px→12px，栏宽 461→236）；中栏自上而下为 LOAD VARIANT、画布、属性条、整枪属性、隐藏属性；M4A1 画布呈五行九列、空槽为虚线框带短标签、已装件带角标与 ×，父子槽位上下紧贴。

## 8. 测试与遗留问题

- `python -m pytest tests -q`：**923 passed, 1 skipped**
- `node --check app.js`：通过
- 本轮相关：`test_r19_2/19_3/19_4/19_5/19_6_round.py` 全部通过

数据缺口与处理：

1. **子弹槽位**：本地 `items.json` 中弹匣物品没有 `mod_ammo` 槽位定义，因此第 5 行子弹格不是真实槽位。实现上明确标记 `data-gap="mod_ammo"`，只展示当前弹药，点击滚动到下方「弹药」区，不参与槽位候选过滤。
2. **`mod_gas_block` 显示名**：默认装配里该槽装的是「柯尔特 M4准星」，与任务书第二行/第三行的「M4A1 准星」一致；引擎按真实槽位 ID 判断，不按中文名匹配。
3. 空槽与空白格的区别：空白格是网格中未放卡片的位置（无 DOM）；可安装空槽是虚线卡片 + 槽位短标签；已装件是实线卡片 + 图标 + 角标，三者数据状态与交互均不同（空槽点击 = 选槽看候选，已装件右键 = 卸下）。

未做/未改变：地图与其它工作台；`release/`；Git 未提交、未推送。
