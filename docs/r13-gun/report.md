# 第十三轮 · 枪械构建页面复刻验收报告

- 日期：2026-10-22
- 阶段：B（阶段 A 弹药页已于本轮先行完成，见 `docs/r12-ammo/report.md`）
- 参考站：`https://db4tarkov.com/gun`（Flutter Web / canvas）
- 本地入口：`http://127.0.0.1:8787/` → 顶栏「配枪」视图
- 结论：**阶段 B 通过验收**；全量测试 712 passed / 1 skipped / 0 failed。

## 1. 测试基线

| 时间点 | 结果 | 说明 |
| --- | --- | --- |
| 夜间任务开始 | 691 passed / 1 skipped | 与第十一轮报告一致，本次实跑复核 |
| 阶段 A 完成 | 705 passed / 1 skipped | 新增 `tests/test_r12_ammo.py` 14 项 |
| 阶段 B 完成 | **712 passed / 1 skipped / 0 failed** | 新增 `tests/test_r13_gun.py` 7 项 |

- 新增测试数：阶段 A 14 项 + 阶段 B 7 项 = **21 项**。
- 唯一跳过项为本轮之前就存在的既有 skip，没有删除、跳过或弱化任何旧测试。

## 2. 数据审计（`data/gunslots.json` / `data/items.json` / `data/gun-presets.json`）

| 项目 | 实测值 | 结论 |
| --- | --- | --- |
| `items.json` 物品总数 | 5480 | 未改动 |
| 枪械数（`pt == "Weapon"` 且被 `gunslots` 收录） | 163 | 与 `gunslots.count` 一致 |
| 枪械槽位总数 | 987 | 每枪 6–11 个顶级/子槽不等 |
| 槽位 `allow` 为空 | 3 | AK-102 / AK-104 / AK-105 的 `mod_launcher`（下挂榴弹），上游本身无可用件，候选表显示空态，不伪造配件 |
| `allow` 引用物品是否存在 | 全部存在 | 0 个坏引用（测试断言） |
| 枪械图标 | 163/163 存在 | `assets/icons-items/<id>.webp`，统一 64×64 |
| 内置枪械预设 | 373 | `gunslots.presetCount` 497 为上游原始数量；本地面向构建器的可解析预设 373 |
| 预设未解出 | 25 | 上游预设引用了本地缺失的配件/槽位，已记录在 `gun-presets.unsolved`，**不隐藏、不伪造** |
| 预设配件引用总数 | 3637 | 路径根槽位与配件 id 全部可解析（测试断言） |

- 口径分组为**展示层**行为（30 组），不参与槽位兼容与安装校验；兼容性只认 `slots[].allow` + 上游 `conflictingItems`。
- 口径提取采用“逐字符扫描 + 型号数字守卫 + 评分”：避免 `Glock 19X 9x19` 被识别成 `19X9`，
  也避免把 `7.62x25` 拆出 `2x25`；无法识别的 `FN GL-40` 归入「其它」，固定排在最后。

## 3. 实现内容

改动文件（本轮阶段 B）：

| 文件 | 改动 |
| --- | --- |
| `index.html` | 配枪视图内新增 `#gw-browse`、`#gw-visual` 容器；沿用既有 `#gw-search` / `#gw-results` / `#gw-current` / `#gw-ref` / `#gw-preset` / `#gw-hint` / `#gw-stats` / `#gw-tree` / `#gw-focus` / `#gw-table` |
| `app.js` | 新增口径提取（`GUN_CAL_TOKEN` / `GUN_CAL_TYPE` / `gunCaliberOf`）、浏览墙 `renderGunBrowse`、整枪合计 `gunTotals`、枪械展示 `renderGunVisual`；`renderGun()` 调用链接入；`renderGunStats()` 改用 `gunTotals()`；`el` 增加 `gwBrowse` / `gwVisual` |
| `style.css` | 新增 `.gun-workbench .gw-browse*`、`.gw-visual*` 深色样式；修正展示图为 64×64 原尺寸；既有深色候选表作用域保持不变 |
| `tests/test_r13_gun.py` | 新增 7 项测试（数据完整性 / 口径分组 / 整枪合计 / 页面接线 / 离线） |
| `docs/r13-gun/**` | 参考截图、验收截图、审计记录与本报告 |

复用而非重写：

- 槽位树、动态子槽、候选过滤、冲突拦截、安装/卸除、预设弹窗与后端存储全部复用既有实现
  （`buildGunTree` / `gunRows` / `gunInstallCheck` / `gunEquip` / `clearGunSlot` / `openPresetModal` / `/api/presets`）。
- 未重写 `app.js`，未改动地图渲染、路线、搜索、任务、图标、配装工作台与预设存储。
- 未新增第三方运行期依赖；无 CDN、在线字体或远程 API。

## 4. 真实浏览器验收（Chrome + CDP 9224）

### 4.1 布局实测（1904×814 视口，截图原始尺寸）

| 元素 | 实测 |
| --- | --- |
| `.gun-workbench` | 1904×783，深色底 `rgb(14,17,22)` |
| 左栏 `.gw-side` | 300 宽，`rgb(21,26,33)`；`.gw-browse` 279×232 |
| 主栏 `.gw-main` | 1604 宽；`.gw-visual` 1604×81；`.gw-table` 1604×630 |
| 候选表 | 表头高 22、行高 35、单元格字号 11 px、全部左对齐 |
| 浏览墙 | 30 个口径组 / 163 把枪；当前枪 `aria-current="true"` 绿色描边并自动滚入视野 |
| 展示图 | 64×64 本地 webp（`naturalWidth = 64`），4 px 内边距，不放大 |

### 4.2 交互与数值（均来自页面实际读数）

1. **搜索并选中 M4A1**：输入 `M4A1` → 结果 1 条「柯尔特 M4A1 5.56x45 卡宾枪 · 6 个改装槽 · 19 套内置参考预设」→ 点击后
   基础枪重 **0.75 kg**、整枪价 **92,421 ₽**、人机工效 **48.0**、6 个槽位，搜索框自动清空。
2. **安装合法配件**：枪托槽安装「柯尔特 A2 AR-15 缓冲管」→ 槽位 7 个、配件 1 件、
   **0.84 kg / 115,570 ₽ / 人机工效 46.0 / 后坐修正 −1.0%**，并出现动态子槽 `mod_stock/mod_stock`。
3. **冲突拦截（真实上游数据）**：已装缓冲管后进入「手枪式握把」槽，
   「ADAR 2-15木质枪托」与「Hera Arms CQR AR-15 一体化枪托」两行被标为红色，
   文案为「⛔ 与已安装的「柯尔特 A2 AR-15 缓冲管」互斥（上游 conflictingItems）」；
   点击后提示「⛔ 无法安装 …（未改动改装）」，配件数、重量、价格均保持不变。
   （说明：ADAR 木托在上游数据中属于 `pistolGrip` 类且与缓冲管互斥，属真实规则，不是按名称猜测。）
4. **刷新恢复**：刷新页面后视图仍为「配枪」，M4A1 + 缓冲管、0.84 kg、115,570 ₽ 完整恢复；
   `localStorage.eftmap.gun` = `{"gunId":"5447a9cd4bdc2dbd208b4567","installed":{"mod_stock":"68a63c5ce1fb670852024661"}...}`。
   浏览墙仍为 30 组 / 163 把，当前枪高亮正确。
5. **AKM（突击步枪，不同槽位集）**：10 槽、2.09 kg、58,349 ₽、人机工效 28；
   安装「AK-74导气管」→ 2.21 kg / 63,299 ₽；`×` 卸除后回到 2.09 kg / 58,349 ₽；切换到 MP-133 再切回 AKM，未串用 MP-133 的数据。
6. **MP-133（霰弹枪，第三种类型）**：6 槽、1.10 kg、37,999 ₽；
   枪管槽 12 个候选，安装「MP-133 12 铅径 510 毫米枪管」→ **1.90 kg / 177,998 ₽ / 后坐修正 −3.0% / 人机工效 35.0**。
7. **预设**：另存为「夜测 AKM 方案」→ 覆盖保存为 1 件配件 → 「新建」清空 → 「加载」恢复 1 件配件、
   2.21 kg、槽位显示「导气管 · AK-74导气管」；刷新后仍恢复；落盘文件为
   `%APPDATA%\EFTMap\weapon-presets.json`（原子写入，未改动存储机制）。
8. **离线**：配枪页运行时资源 250 条，`external = []`；164 张图片全部来自
   `http://127.0.0.1:8787/assets/icons-items/`，无任何外部域名请求。

### 4.3 截图清单（`docs/r13-gun/`）

| 文件 | 内容 |
| --- | --- |
| `shot-gun-browse.png` | 最终构建：口径分组浏览墙（30 组 / 163 把）+ 当前枪高亮 |
| `shot-gun-selected.png` | 搜索 M4A1 并选中后的工作台全貌 |
| `shot-gun-installed.png` | 安装缓冲管后：1 件配件、0.84 kg、115,570 ₽ |
| `shot-gun-conflict.png` | 冲突行红色标记 + 顶部拦截提示，状态未变 |
| `shot-gun-mp133.png` | MP-133 安装 510 mm 枪管后 |
| `shot-gun-akm.png` | AKM 与枪械预设 |
| `shot-gun-preset.png` | 预设弹窗 |
| `shot-gun-restored.png` | 刷新后从存储恢复 |
| `shot-gun-dark.png` / `shot-gun-layout.png` | 深色候选表与布局实测 |
| `reference/ref-gun-initial.png` | 参考站枪械墙（按口径分组的原始布局） |
| `reference/ref-gun-after-click.png` | 参考站 Gunsmith：左 FORGE / 中枪体+属性+价格 / 右 Pick a mod |
| `reference/ref-gun-modpicker.png` / `ref-gun-modpicker2.png` | 参考站槽位选择与候选表列集 |

## 5. 新增测试覆盖（`tests/test_r13_gun.py`，7 项）

1. `test_gunslots_cover_all_local_guns`：163 把枪与槽位、`allow` 引用完整性。
2. `test_builtin_presets_reference_real_guns_and_parts`：373 套预设、路径根槽位、配件 id、3637 个配件引用。
3. `test_caliber_grouping_covers_every_gun_without_model_number_fragments`：
   Node 实跑 `gunCaliberOf`，断言 163 总数、30 组、`其它` 仅 FN GL-40、Glock 19X→9x19、TT-33→7.62x25、
   RPK-16→5.45x39、无 `19X9/2x25/2x39/2x51/2x54/3x64/6x45` 碎片。
4. `test_gun_totals_math`：Node 实跑 `gunTotals`，验证件数、重量、价格、缺价计数、人机工效与后坐修正。
5. `test_index_html_has_gun_browse_and_visual_containers`：页面容器接线。
6. `test_render_gun_calls_browse_and_visual`：`renderGun()` 调用链、`其它` 排最后、统计改用 `gunTotals()`。
7. `test_gun_table_dark_scope_and_offline`：深色作用域选择器、无外部 URL、图标走本地相对路径。

## 6. 已知差异与真实缺口（不伪造、不掩盖）

1. **枪体渲染**：参考站是 Flutter canvas 线框枪体；本地只有 64×64 物品图标，没有拆分枪体资产，
   因此只做“图标 + 名称 + 槽位/配件数 + 属性筹码”的展示。这是最大视觉差异。
2. **候选表列集**：参考站有 Market / Trader / Buy / Craft / Barter / C1–C6；
   本地 `items.json` 只有构建期 FLEA 快照价，故合并且缺价单独计数（`missing`），不按 0 处理。
3. **FORGE 自动生成器、Compare、Changes、Variant/Streamer/Saved、射击模式筛选**：未实现（参考站专有或本地无字段）。
4. **切换枪械会清空当前改装**（`selectGun` 既有行为），不保留上一把枪的配件；已实测切换不串数据。
5. **25 套内置预设无法解析**（上游引用缺失），已在数据层记录为 `unsolved`，界面不显示虚假方案。
6. **3 个空 `allow` 槽位**（AK-102/104/105 的下挂榴弹）在候选表中为空态，属上游数据缺口。
7. 第十一轮遗留的 5 张防护区域组合图仍未补齐（弹药/枪械页任务不涉及），本轮仅记录，未生成或伪造。

## 7. 保护性检查

- 未重写 `app.js`；未迁移框架；未新增运行期网络请求、CDN 或第三方依赖。
- 未修改地图渲染、路线、搜索、任务、图标、配装工作台与预设存储逻辑。
- 未覆盖 `items.json` / `gunslots.json`；未覆盖正式发布版本；未推送远端仓库。
- 工作区存在前几轮留下的未提交改动（见 `git status`），本轮仅在上表所列文件上继续增量修改。
  `data/roadnet.json` 的时间戳变化来自服务启动时的既有路网缓存重建，与本轮功能无关。

## 8. 阶段 C 统一回归与交付检查

| 检查项 | 结果 |
| --- | --- |
| 完整测试套件（最终） | `712 passed, 1 skipped in 57.81s` |
| 夜间任务起点 → 当前 | 691 passed / 1 skipped → 712 passed / 1 skipped（+21 项新测试） |
| 阶段 A 产物 | `docs/r12-ammo/report.md`、`reference/audit-notes.md`、`reference/lrnpc-reference-table.json`、13 张验收截图、8 张参考截图 |
| 阶段 B 产物 | 本报告、`reference/audit-notes.md`、4 张参考截图、9 张验收截图 |
| 改动范围 | `index.html`、`app.js`、`style.css`、`tests/test_r12_ammo.py`、`tests/test_r13_gun.py`、`data/ammo.json`、`tools/build_ammo.py`，以及两个 docs 目录 |
| 地图 / 路线 / 任务 / 配装工作台 / 预设存储 | 本轮未改动；对应旧测试全部通过 |
| 运行期网络 | 配枪页 250 条资源全部来自 `127.0.0.1:8787`，外部请求 0 条 |
| 发布版本 / 远端仓库 | 未覆盖、未推送 |
| r11 遗留 5 张防护区域图标 | 仅记录，不生成、不伪造 |

说明：仓库 HEAD（`bf438df`）早于本轮多轮未提交改动，无法用 `git diff` 单独切出本轮差异；
上表“改动范围”为本次执行中实际编辑的文件，其余为前几轮遗留的工作区改动。
