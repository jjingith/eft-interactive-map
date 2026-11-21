# R19.12 合并开发 · 交付报告

版本：**R19.12**（`app.js` 的 `AM_BUILD = "R19.12"`，`index.html` 资源串 `?v=r19.12`，`/api/build` → `rev R19.12-a94de661`）
工作区：未执行 `git reset` / `commit` / `push`；`release/` 无改动；R19.11 全部功能保留并回归通过。

---

## 1. 枪匠大师：不再输出不兼容组合（最高优先级）

### 1.1 根因（真实数据复现，不是猜测）

`gun_builder.js` 的 `validate()` 只检查「槽位存在 + allow 收录」，**从不检查上游 `conflictingItems`**；
`sanitize()` 因此不会清掉互斥件；`checkConstraints()` 也不查互斥；
贪心 `optimize()` 拿清理后的结果继续打分，于是**互斥的两件同时装着**也会 `constraintOk: true`。

量化复现（修复前口径）：163 把枪 × 默认/极端权重，**978 个方案里 197 个含互斥对（涉及 75 把枪），全部被判有效**。

真实案例（`optimizer-conflicts.json`）：

| 项 | 物品 ID | 名称 |
|---|---|---|
| 握把（一体化枪托） | `5a33e75ac4a2826c6e06d759` | Hera Arms CQR AR-15 一体化枪托 |
| 枪托 | `5947e98b86f774778f1448bc` | Magpul UBR GEN2 AR-15 枪托（黑色） |

上游互斥是**单向**的（Hera 的 conflict 列表含 UBR，UBR 的列表不含 Hera），旧代码只看一方 → 漏判。
同案例还有：SV-98 照门 + Geissele 环形瞄具、10.3″ 枪管 + LVOA-C 护木、Aeroknox 上机匣 + B.A.D 辅助释放杆。

### 1.2 修复（统一一套规则，不在优化器另写一份）

`gun_builder.js`：

- `conflictSet / conflictsWith / conflictPairs()`：**双向**比较整套已装件（不只看正在选的槽位）；
- `validate()` 加互斥检查（同一对只报一次，归咎路径靠后的一件 → `sanitize` 只掉一件，不会两件全清）；
- `candidates()` 与已装件互斥的候选直接 `blocked`（与右栏候选表同一结论）；
- `checkConstraints()` 把「结构不合法 / 装配冲突」与用户约束同级检查；
- `verifyBuild(ctx, gunId, installed, cons, expect)`：**最终整树校验** = 结构 + 双向互斥 + 用户约束 + **声称装了的件是否真的还在**（防 sanitize 静默清理后仍当成功）；
- `optimize()`：
  - 试装结果若自己被清掉、或连带清掉受保护件（必装/锁定/容量槽）→ 该候选作废（`evictsProtected`）；
  - 出方案前独立跑 `verifyBuild`，并把方案相对起始装配的替换/移除记入 `dropped`；
  - `constraintOk=false` 的方案不进有效列表。

`app.js`：应用方案先 `verifyBuild`，**任何一项不过就原地拒绝**（保持当前装配不变）；被兼容链改动过的方案（`dropped.length>0`）也不得静默应用，必须提示"无法原样应用"。

### 1.3 验证结果

- 全量扫描：815 个方案 → **0 个含互斥对**；
- 纯装配合法性（不带用户约束）：**652 / 652 全部 verifyOk**（结构 + 互斥 + 声称件在位）；
- 带 `scope:true` 一轮 652 个：409 有效；243 无效**全部**是「该枪装不上瞄具」这类用户约束未满足（`problemKinds = {scope: 243}`），**没有** structure/conflict；
- 无解案例（`optimizer-no-solution.json`）：
  - AK-74 + 100 发 → 4 个方案全部无效，原因"该枪可选容量：10/20/30/45/60/95 发"；
  - Glock 17 + 100 发 → 全部无效（可选 17/19/21/24/31/33/50）；
  - AK-74 必装 Glock GTL 21 手电 → 全部无效，原因"装配树里没有可安装它的槽位"。
- 浏览器实测（`screenshots/A1..A4`）：M4A1 生成 4 个有效方案，每个带 `✔ 整树校验 13 件 · 0 冲突` 徽标；
  应用后提示"已应用方案：低后坐力（整树终检 13 件通过，0 冲突）"，画布已装件与方案一致；
  AK-74 + 100 发显示"没有满足当前约束的可行方案：…不会用 30 发之类的弹匣凑数"，0 个方案行。

## 2. 固定六行九列画布

`app.js` 的 `gwBuildLayout()` 重写为**固定 6×9 = 54 格**（`GW_GRID_ROWS=6 / GW_GRID_COLS=9`）：

| 内容 | 固定位置 | 实测（AK-74 / M4A1） |
|---|---|---|
| 枪械本体 | r3 c6–c8（span 3） | `data-row=3 data-col=6 data-span=3` |
| 枪托/缓冲管 | r3 c9 | M4 缓冲管、AK 木托 ✓ |
| 枪托子槽 | r4 c9 → r5 c9 →（更深）r6 c9 | 只沿"基名仍是 stock"的链往下排 |
| 弹匣 | r4 c7 | ✓ |
| 后握把 | r4 c8 | ✓ |
| 子弹槽 | r5 c7 | ✓ |
| 拉机柄 | r2 c9 | ✓ |

第三行主体（按真实槽位树，不看枪名）：
- 标准（有独立枪管槽）：muzzle c1 · gas c2 · barrel c3 · handguard c4 · receiver c5；
- 一体式（无独立枪管槽）：**c1 留空** · muzzle c2 · gas c3 · handguard c4 · receiver c5。

其它规则：
- 固定锚点格先"预留"，普通附件不许漂进去（没弹匣的枪那格就是空的）；
- 附件优先父件正下方同列 → 同行相邻 → 后续行，绝不越出 6×9；
- 前握把仍钉在真实父件正下方同列（父件正下方被锚点占着时沿同列下探，不换列）；
- 空行轨道保留（`grid-template-rows: repeat(6, minmax(0,auto))`），坐标系不随枪/配件变化。

验证：`tools/r1912_layout.js` 全量 163 把枪 **0 违规 / 0 溢出**（无重叠、无越界、不压枪身、固定锚点正确）；
浏览器 6 类案例（M4A1 标准 / AK-74 一体式 / SA-58 多级枪托链 / SCAR-H 一体式+SPEAR 多层 / Glock 手枪）
在 1920×919 与 1384×805 下都是 **cols=9 rows=6**，`scrollWidth === innerWidth`（无横向滚动）。
证据：`layout-grid.json`（含每张卡的 DOM 矩形）、`layout-cases.json`、`screenshots/B-*.png`。

## 3. 默认弹药

`app.js` 新增纯函数 `gwDefaultAmmoRule(list)` + `defaultAmmoForGun(gunId)` + `ensureGunAmmo(gunId, force)`：

1. 只取真实弹头（`t==="bullet"` 且 `pen>0`，排除信号弹/榴弹）；
2. 有 FMJ / 全金属被甲 / Ball 命名的标准弹 → 优先（多枚取穿深最接近中位数的）；
3. 没有 FMJ 类 → 取穿深最接近**该口径中位数**的普通弹（不是最高穿深/最高伤害/最贵）；
4. 平手取更便宜、再按名称排序，结果可复现；没有可用弹头 → `id=null` + 明确写"数据缺口"，不虚构。

应用范围：首次选枪 / 换枪（不兼容的残留弹药被替换）/ 恢复默认配装 / 画布子弹槽 / 整枪初速计算回退 / 逐发模拟（压弹全空时填首发）。预设里合法的自选弹**不会**被覆盖。

全量审计（`default-ammo.json`，163 把有预设的枪）：**159 把有默认弹**（125 把走 FMJ 路径、34 把走中位数路径）；4 把写明数据缺口（2 门榴弹发射器、玩具枪、PP-9 9x18PMM——口径 slug 在本地弹药库无对应弹种）。

指定枪实测：

| 枪 | 默认弹 | 穿深 | 口径中位数 | 路径 |
|---|---|---|---|---|
| 柯尔特 M4A1 | 5.56x45毫米 FMJ | 23 | 31 | FMJ |
| SIG MCX SPEAR | 6.8x51毫米 SIG FMJ | 36 | 36 | FMJ |
| AK-74 | 5.45x39毫米 FMJ | 24 | 28 | FMJ |
| Glock 17 | 9x19毫米 FMJ M882 | 18 | 14 | FMJ |

（Glock 的 FMJ 略高于中位数，因为它是该口径唯一 FMJ 命名弹，规则优先 FMJ 类——理由写在 JSON 里。）

## 4. 动态外观（资源受限下的最佳实现）

**资源审计**（`appearance-assets.json`）：
- `assets/guns-full` 161 张、`assets/presets-full` 368 张 —— 都是**整枪**渲染图，不是分件图；
- `assets/icons-transparent` 5356 个透明底库存图标 —— 唯一可用的"分件图"素材；
- 全目录搜索 **0 个** `.glb/.gltf/.fbx/.obj/.mtl/.blend` 模型或材质文件，也没有 model/mesh 目录。

结论：**没有分件 3D 模型 / 材质 / 安装变换，无法还原游戏内实时 3D。**
实现的是 `renderGunSkin()` 二维示意合成：在真实整枪图上按部件类别锚点叠加真实配件图标（14 类：枪口/消音器/枪管/护木/机匣/枪托/弹匣/后握把/瞄具/导轨/拉机柄/战术设备/前握把/脚架），
完全由 `g.installed`（已过兼容校验的装配）驱动、只读、不改装配；装配签名不变时按缓存跳过重绘（鼠标移动等无关事件不会重建）。
界面上明确标注"外观合成 · N 层"，tooltip 写明这是二维示意合成。

三态实测（`appearance-tests.json` / `screenshots/C1..C3`）：
- 默认装配：10 层（含 muzzle「柯尔特USGI A2 消焰器」）；
- 换枪口为 USGI A1 三叉消焰器：仍是 10 层，muzzle 图层**换成新件**；
- 卸下枪口装置：9 层，muzzle 图层消失。

未实现（数据/资源缺口，不虚报）：游戏内 3D 渲染与枪身旋转、配件在枪身照片上的像素级对位、材质/涂装变化。

## 5. R19.11 功能回归

全部保留并通过（`test_r19_11_round.py` 16 条 + 新增回归锚点测试）：
100 发弹匣硬约束（`enforceMagCapacity`）、属性条实心/斜纹 + 基线/改装/技能三值、
个人属性弹窗（`eftmap.profile.v1` 持久化）、右栏顶部当前槽位、隐藏不兼容复选框、
整条红色斜纹（`repeating-linear-gradient` + `pointer-events:none`）、M4 一体式枪托/缓冲管结构判定、
SPEAR 逐发模拟 6 个真实兼容弹匣（`gunMagIds` 与改枪界面同源）。

浏览器实测（`screenshots/D1/D2`）：装 Hera 一体化枪托时直接装会被拒（"与已安装的「…枪托」互斥"）；
卸下枪托后再装，枪托槽 17 个候选里 **11 个整条红斜纹**、行内写明互斥原因、`pointer-events:none`；
SPEAR 弹匣下拉 6 项可选。

## 6. 证据与工具

`docs/r19.12-canvas-audit/`：

| 文件 | 内容 |
|---|---|
| `optimizer-conflicts.json` | 真实互斥案例（修复前口径 + 单向声明）与修复后结论、全量扫描 0 复发 |
| `optimizer-final-validation.json` | 652 方案的整树校验档案（纯装配 652/652；带约束的 problemKinds） |
| `optimizer-no-solution.json` | 3 个无解案例与可读原因 |
| `layout-grid.json` | 1920/1384 的 6×9 网格尺寸与每张卡 DOM 坐标 |
| `layout-cases.json` | 六类枪械布局验证（含无独立枪管槽、枪托链） |
| `default-ammo.json` | 163 把枪默认弹药 ID/穿深/理由/兼容性 |
| `appearance-assets.json` | 图片/模型/材质资源审计 |
| `appearance-tests.json` | 默认/换件/卸件三态图层对比 |
| `screenshots/` | A 枪匠大师 4 张、B 布局 8 张、C 外观 3 张、D 回归 2 张 |
| `_accept.json` / `_layout.json` | 浏览器与引擎原始测量 |

工具：`tools/r1912_engine.js`（冲突/终检/无解探针）、`tools/r1912_layout.js`（固定网格全枪探针）、
`tools/r1912_ammo.js`（默认弹药审计）、`tools/r1912_accept.py`（浏览器验收）、`tools/r1912_probe.py`（网格快照）。

## 7. 自动化测试

`993 passed, 1 skipped`（`C:/Python314/python.exe -m pytest -q`）。
新增 `tests/test_r19_12_round.py` 13 条：
互斥规则单一口径、真实互斥组合被判无效、优化器方案全部整树合法、无解显式返回、
应用入口同一校验、固定网格常量与全枪不变量、默认弹药规则（FMJ 优先/中位数兜底/数据缺口）、
外观由真实装配驱动 + 缓存 + 资源审计结论、R19.11 回归锚点。

迁移（未弱化，只改到新规范）：
- `test_r19_5`：装配布局仍禁绝对坐标，但**外观图层**允许百分比锚点（并新增断言）；
- `test_r19_6/7/10`：从"随枪变化的行列"改为固定 6×9 锚点常量 + 全枪不变量（探针换成 `r1912_layout.js`）；
- R19.11 的 `test_m4_stock_buffer_tube_structure`：明确"一体化握把 + 独立枪托必须互斥"（腾空握把后合法）。

## 8. 未解决问题与数据缺口

1. **技能公式**仍为社区数据、待官方核验（R19.11 既定，本轮未改）。
2. **上游冲突数据不完整**：例如部分缓冲管不在 Hera 一体化枪托的 conflict 列表里（Strike Industries 先进机匣延长缓冲管等），
   这类"物理上互斥但上游没声明"的组合**不会**被臆造规则拦截，已在 `optimizer-conflicts.json` 注明。
3. **3D 外观**：无模型/材质，只能做二维示意合成（见第 4 节）。
4. `gun-compat.json` 的 `cls` 偏粗（上游快照限制），技能类别改读物品真实 `cats`。
5. 画布第 1 行（r1）多数枪为空轨（高度 0），固定坐标系保留但视觉上不可见。
6. `release/` 仍为旧版本，未按要求更新。
