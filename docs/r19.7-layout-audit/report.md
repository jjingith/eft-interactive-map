# R19.7 枪械工作台第二轮修正 · 验收记录

- 项目：`d:\personal\trae\02-塔科夫\eft-interactive-map`
- 基线：R19.6 结束状态（本轮不新建工作台、不重做 UI、不提交 Git、不覆盖 `release/`）
- 运行服务：`http://127.0.0.1:8787/`（`tools/serve.py`，pid 5124，cwd 为项目目录）
- 运行版本：页面 `#build-rev` 实测 `rev R19.7-04f4d52f`（`/api/build` 按文件 sha256 现算，随每次构建变化）
- 运行期网络：无（全部本地资源，无 CDN / 在线字体 / 外部 API）

## 1. 每个问题实际修改的文件

| 问题 | 修改文件 | 关键改动 |
| --- | --- | --- |
| 基础枪械 / 改装槽位 / 已装配件位置 | `index.html`、`app.js`、`style.css` | 新增画布上方信息条 `#gw-meta`（`renderGunMeta()`），`renderGunStatsV2()` 删掉这三行与「当前预设」；`gunPresetStateText()` 只输出保存状态并回查 refId / buildPresetId（装预设后不再误标「官方默认装配」） |
| 整枪属性状态文字 | `app.js` | `gunStatRowEx()` 只输出名称 + 值，删除 `✓ 实测 / 缺失 / ≈ 估算 / gw-stat-conf / data-tone`，来源说明只保留在 `title` |
| 枪身官方预设文字 | `app.js` | `renderGunTree()` 不再渲染 `gw-hero-tag`「官方预设：…」；`renderGunVisual()` 删除 LOAD VARIANT 行右侧整套摘要盒（vtag + 枪名 + meta + chips） |
| 配件右上角 × | `app.js`、`style.css` | `gwPartCard()` 删除 × 按钮节点，`.gw-part-x` 样式全部移除；右键卸载保留 |
| 战术装置位置 | `app.js` | `gwBuildLayout()` 新增 `GW_TACT` 规则：前握把（无则后握把）左侧优先，越界/被占则整组进入子弹行下方的独立行 |
| 子弹槽位交互 | `index.html`、`app.js`、`style.css` | 删除 `#gw-ammo`；画布子弹格 `gw-part-ammo` 点击进入 `ammoFocus`；右栏切弹药列集；选中写回画布并更新 DPS |
| 隐藏属性下方开发者文本 | `app.js` | 删除 `renderGunAmmo()`（弹药清单 / 伤害穿透公式说明 / 「弹道联动图尚未实现」）；`renderGunFocus()` 不再输出内部槽位路径、allow 数量与已选弹药名 |
| 右栏候选名称不显示 | `style.css`、`app.js` | 名称单元格改弹性布局（图标定宽、名称占满剩余并可省略），`title` 带完整名称 |
| 中栏过宽 | `style.css` | `.gw-buildpage` 中栏由弹性宽改为 `minmax(0, 600px)`；`.gw-canvas` 561px 居中；释放宽度给右栏 |
| 射速 / DPS 小字 | `app.js`、`style.css` | 枪身图专用容器 `.gw-gun-shot` 内叠加 `.gw-gun-overlay`（`800 RPM` 灰黑、`DPS ≈ 680` 红） |
| 版本标记 | `app.js`、`index.html`、`tools/serve.py`、`tests/*` | `AM_BUILD = "R19.7"`、`?v=r19.7`、`rev = "R19.7-" + sha[:8]` |

## 2. 元数据 / 整枪属性 / 隐藏属性的最终展示结构

顺序（实测 DOM 与截图一致）：
`LOAD VARIANT → #gw-meta（信息条）→ 装配画布 → 属性显示条 → 整枪属性 → 隐藏属性`

- `#gw-meta`（画布上方，独立一行，不进入 `#gw-stats`）：
  `基础枪械 | SIG MCX .300 Blackout 突击步枪 | 改装槽位 | 19 | 已装配件 | 12`
  （M4A1：`柯尔特 M4A1 5.56x45 卡宾枪 | 18 | 12`；换枪与装拆件后随之刷新）
- `LOAD VARIANT` 行：`⤓ LOAD VARIANT | 预设 [下拉] | 恢复默认 | 预设：未改动`
  —— 预设保存状态属于预设操作信息，放在这一行，不再混进整枪属性。
  行内只保留「保存状态」（哪份预设由左侧下拉显示），避免长预设名把整行撑出可视区；
  实测 561×30、`scrollWidth 559 / clientWidth 559`（无溢出），`presetClipped = false`。
  下拉限宽 150px，选中项全名在 `title` 中；装载参考预设后标题带「当前：<预设名>」。
  预设装载实测：选择 `… Custom（17 件）` → `改装槽位 18→22`、`已装配件 12→16`、
  属性与成本刷新，状态变为 `预设：未改动`；再点「恢复默认」回到 18/12 并显示 `预设：未改动`。
- 整枪属性 `#gw-stats`（实测文本，无任何状态后缀）：

  `人机工效 71.5 | 垂直后坐力 82.4 | 水平后坐力 227.8 | 重量 2.72 kg | 精度 MOA 2.75 MOA | 射速 800 rpm | 瞄准距离 100 m | 弹匣容量 30 发 | 初速 — | 整枪成本（含原厂件） 321,716 ₽ | 其中改装件 201,521 ₽`

  初速缺失时只显示 `—`。
  装载与基准不同的预设时会附带该属性相对基准的数值差（如 `人机工效 50.4 -4.6`、`重量 3.93 kg +1.08`）——
  这是纯数值对比，不是「实测 / 缺失」状态文字，R19.6 已有该对比能力，本轮保留。
- 隐藏属性 `#gw-hidden`：仅属性行，下方不再有槽位路径、合法配件数量、弹药清单、公式解释或开发说明。
- 枪身图左下角：`800 RPM`（灰黑 `#55595e`）+ `DPS ≈ 680`（红 `#d02a1e`），两者叠在枪身图内部（实测 overlay 底边 306 < 图片底边 309）。

## 3. 子弹槽位完整流程与 DPS 验证

流程（真实浏览器操作）：

1. 点击画布第五行子弹格（`.gw-part-ammo`）→ `g.ammoFocus = true`，右栏换成弹药列集。
2. 右栏表头实测：`弹药（.300 Blk）▲ | 伤害 | 穿透 | 初速 | 价格 | 状态`，6 条兼容弹药（M4A1：`弹药（5.56x45）`，11 条）。
3. 点击候选弹药行（`.tbl-row`）→ 走同一安装入口 `gunEquip()` 的弹药分支写入 `gunAmmoState()[gunId]`。
4. 画布子弹格实测：`AMMO .300 Blackout AP`（图标 + 简洁名称），未选时仍为 `AMMO` 空槽，不假装装填。
5. 换枪时弹药状态按枪 ID 分开保存，候选按新枪口径重新生成。
6. 未选弹药时 `DPS —`，选中后即时更新：

| 样例 | 弹药 | 伤害 | 射速 | 实测 DPS 文本 | 计算 |
| --- | --- | --- | --- | --- | --- |
| SIG MCX .300 Blk | .300 Blackout AP | 51 | 800 rpm | `DPS ≈ 680` | 51×800÷60 = 680 |
| 柯尔特 M4A1 | 5.56x45 毫米 FMJ | 57 | 800 rpm | `DPS ≈ 760` | 57×800÷60 = 760 |

未选弹药时 `800 RPM` 保留、DPS 显示 `—`，不会沿用上一枚弹药的值。
焦点条在已选弹药时不再重复弹药名（避免在隐藏属性下方重复输出）。

数据缺口说明：`data/items.json` 的弹匣没有真实 `mod_ammo` 槽位。本轮没有把虚构的 `mod_ammo` 写进上游数据，而是把画布子弹格做成独立的「弹药选择槽」（内部 `gw-part-ammo` + `gunAmmoState`），普通配件槽位逻辑未伪造。

## 4. 战术装置的实际位置（1920×919 实测）

| 枪械 | 前握把锚点 | 战术装置实际位置 | 判定 |
| --- | --- | --- | --- |
| R11 RSASS | R3 col4 FOREGRIP | R3 col3 TACTICAL（锚点左侧，同一行） | 正向案例：成功排在前握把左侧 |
| SIG MCX .300 Blk | R3 col6 FOREGRIP（col5 被 MOUNT_001 占） | R5 col1（子弹行 R4 下方独立行），`data-parent = mod_reciever` | 左侧空间不足 → 底行，未落在握把右侧 |
| MP7A1 | 无前握把 | R5 col1–3（子弹行 R4 下方） | 3 个根战术槽位整组入底行 |
| MP7A2 | R3 col7 FOREGRIP | R5 col1–3 | 左侧被其他 lower 卡占住 → 底行 |
| Glock 17 | R3 col6 PISTOL_GRIP | R5 col1 | 左侧被占 → 底行，未排到握把右侧 |

父子关联：有真实父件的（MCX）由 `data-parent` 画连线到对应父卡；无父件的根槽位（MP7 / Glock）按 `lane` 由 `gwDrawLinks()` 连到枪身卡底缘，不会让用户误以为装在其他部件上。
换枪 / 装拆件后布局重算（`gwBuildLayout()` 每次渲染按当前槽位树重排，不残留上一把枪的位置）。

## 5. 右侧候选名称缺失：实际原因与修复

原因在 CSS 布局，不在数据映射：

- 数据层每条候选都有名称（实测 37/40 行名称文本非空），不是字段缺失。
- `.gw-row-name` 原为 `inline-flex`，外层 `.tbl-cell[data-key="n"]` 依靠 `width:0 / min-width:100%` 参与行网格轨道，图标列 `28px + 7px` 固定，名称容器不参与弹性分配（`min-width:auto` 收缩），长名称被压成 0 宽再被 `overflow` 裁掉，于是部分行只剩图标。

修复：

- 名称单元格改 `display:flex; align-items:center; overflow:hidden`，图标 `flex:0 0 auto`。
- 名称容器 `flex:1 1 auto; min-width:0; overflow:hidden`；名称与副标题 `display:block; max-width:100%; text-overflow:ellipsis; white-space:nowrap`。
- 额外给名称容器 `title` 带完整名称（`丰和 20 式手枪式握把（配件）` 实测），长名称悬停可读全；不依赖 tooltip 补位（名称本身已可见）。

实测：1920 与 1384 下 MCX（握把候选 37 行）、M4A1（40 行）`candNamesMissing = 0`，名称列宽 451px，长名以省略号显示。

## 6. 两种视口下的实际宽度

| 视口 | FORGE | 中栏 | 右栏候选 | 画布 | 画布列模板 |
| --- | --- | --- | --- | --- | --- |
| 1920×919 | 236px（x0） | 600px（x244） | 1008px（x852） | 561×374（x256） | `236px 600px 1008px` |
| 1384×805 | 208px（x0） | 600px（x216） | 552px（x824） | 561×374（x228） | `208px 600px 552px` |

- 中栏 600px = 画布 561px + 左右内边距 12/12 + 少量余量，画布居中，无大块多余横向空白。
- 两种视口画布均无横向溢出 / 裁切 / 重叠；释放的宽度全部给右栏（1920 右栏 1008px）。
- LOAD VARIANT 行 561×30，`scrollWidth 559 / clientWidth 559`（无溢出、无子元素越界），`presetClipped = false`，预设下拉 150px 未裁切（全名在 `title`）。
- 枪身射速取当前枪械数据、未写死：MCX/M4A1 800 RPM、MP7A1/MP7A2 950 RPM、R11 RSASS 700 RPM、Glock 17 30 RPM（各截图中实测），DPS 随所选弹药即时更新。

## 7. 修改前后截图、测试结果与剩余限制

截图目录：`docs/r19.7-layout-audit/`

- `before/`：R19.6 结束状态（`docs/r19.6-layout-audit/after/` 原样复制，注明来源）：`ak74n-1920/1384`、`glock17-1920`、`m4a1-1920/1384`、`mp5-1920` 及画布局部图。
- `after/`（本轮真实浏览器截图 + DOM 测量 JSON）：
  - `mcx-1920x919.png/.json`、`mcx-1384x805.png/.json`、`mcx-canvas-*`
  - `mcx-ammo-open-*`（点击子弹格后右栏弹药候选）、`mcx-ammo-picked-*`（选中 AP 后画布 + `DPS ≈ 680`）
  - `m4a1-1920x919.png/.json`、`m4a1-1384x805.png/.json`、`m4a1-canvas-*`
  - `m4a1-ammo-open-*`、`m4a1-ammo-picked-*`（FMJ，`DPS ≈ 760`）、`m4a1-unloaded-1384x805.png`（右键卸载后 `已装配件 12 → 11`）
  - `mp7a1-1920x919.*`、`mp7a2-1920x919.*`、`rsass-1920x919.*`、`glock17-1920x919.*`（战术装置位置验证）

测试：

- 全量 `pytest -q`：**934 passed / 1 skipped**（`node --check app.js` 也通过）。
- 新增 `tests/test_r19_7_round.py`（12 条）：meta 信息条、属性无徽标、枪身无官方预设叠加 + RPM/DPS 颜色字号、DPS 公式与空态、弹药交互链路、焦点条无内部路径、× 删除但保留右键、战术装置规则、中栏 600px / 画布 566px 上限、候选名称 CSS、版本串 r19.7。
- 既有 R19.1–R19.6 测试全部保留并通过（含 `test_loadout_workbench.py` 右键监听计数更新为 4：新增的一处仍是子弹格上单格 `preventDefault`，未做全局拦截）。

已确认 M4A1 保留项（实测网格）：R1 col8 `SCOPE`；R2 col5 `SCOPE`、col8 `chandle`、col9 拉机柄；R3 枪口 / 准星 / 枪管 / 上护木 / 上机匣 / BODY 占三格 / 缓冲管；R4 消音器槽 / 下护木 / B.A.D / 弹匣 / 握把 / 枪托；R5 col7 子弹格。

剩余限制 / 已知缺口：

- 弹匣无 `mod_ammo`：弹药槽是画布独立槽，不参与上游槽位树校验（已在上文说明，不作为完成理由）。
- 隐藏属性沿用 `gun_builder.js` 的原始英文键（`TrueErgoDelta` / `OverSwing` / `ArmStamina`），属既有属性名，本轮未改。
- 1384 视口右栏 552px，长名称以省略号显示（悬停可见全名）。
- DPS 为粗估：`弹药伤害 × 射速 ÷ 60`，不冒充实测。
- R19.6 审计未截 MCX，故 `before/` 只有 4 把枪；MCX 的本轮前后差异以 `before/m4a1-*`（同一中栏结构）与本轮 `mcx-*` 对照。
- 未提交 / 未推送 Git，未覆盖 `release/`。
