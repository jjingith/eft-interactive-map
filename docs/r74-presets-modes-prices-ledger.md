# R74 台账：配装枪械预设 / 模式唯一入口 / 价格两列

host=HOMONAS user=MASTERJJ at=2026-11-05 10:26:40 +08:00

本轮只改前端（`index.html` / `app.js` / `style.css` / `tasks.js` / `tasks.css` / `js/game-mode.js`），
未 git commit。测试数据（`%APPDATA%\EFTMap\weapon-presets.json`）已在验证后还原为空 presets。

---

## A. 配装栏显示配枪预设

### 现状摸查（改前）
- 配枪栏预设存于 `%APPDATA%\EFTMap\weapon-presets.json`（后端 `tools/presets.py`，原子写盘），
  非 localStorage。结构：
  `{"version":1,"kind":"weapon","presets":[{id,name,createdAt,updatedAt,gunId,items:{slotId:itemId}}]}`
  读写接口 `/api/presets?kind=weapon`。
- 枪械槽位 `primary1` / `primary2` / `holster`（`gunref: true`），配装里以 `@wp:<presetId>` 占位引用。
- 配装栏此前**完全没有预设区**，也没有读取 weapon 预设，所以为空——不是结构不匹配，而是没读。

### 改动
- `index.html` 在 `#lw-figure` 与 `#lw-cost` 之间新增 `#lw-gun-presets` 区块（标题 + 计数 + 列表 + 说明）。
- `app.js` 新增 `renderLwGunPresets()`，由 `renderGearSide()` 调用：
  - 有预设：`.lw-gp-item`（`56×30` 缩略图 + 名称 + 摘要「枪名 · N 配件 · 重量 · 24h 价」）。
  - 点击 → `equipGunRef(wp.id)`；再点选中项 = 卸下；非枪械槽当前槽位时给出提示。
  - 选中态 `is-on` + `aria-pressed="true"`，金边高亮。
  - 空态：`还没有保存的枪械预设。` + 「去配枪栏新建」按钮，直接切到 `#view-btn-gun`。
- `style.css` 新增 `.lw-gunpresets` / `.lw-gp-*` 一组样式。

### 验证（真实点击）
- 临时写入 1 条预设 `wp_r74test`「R74 验证 · M4A1 满改」（gunId `5447a9cd4bdc2dbd208b4567`，5 配件）。
- 1440 / 1024 两档截图：区块显示「枪械预设 (1)」，摘要
  `柯尔特 M4A1 5.56x45 卡宾枪 · 5 配件 · 1.41 kg · 162,502 ₽（24h）`。
- 点击后：行 `is-on=true`、`aria-pressed=true`，配装合计 `162,502 ₽`；再点取消选中。
- 空态（还原预设后）：列表 0 项，出现「去配枪栏新建」，点击可跳到配枪视图。
- 缩略图 404：`assets/presets-full/wp_r74test.png` 不存在，回退到 `assets/icons-transparent/<gunId>.png`，
  计数 4 次 404 仅由这条测试预设产生（真实预设保存时会生成缩略图）。

---

## B. 顶部模式切换只留一个

### 改动
- `tasks.js`：删除任务页 scope bar 里的 `tk-seg` 三模式分段按钮，及 `data-tkmode` 事件分支；
  进度表「切换到 X」改为只读文案「当前模式 / 在右上角切换」。
- `tasks.css`：删除 `body[data-view="tasks"] .scope-cluster #game-mode-bar { display:none; }`，
  全局条在任务页保持可见。
- 枪匠面板 `gwGsRender`：原模式按钮组改为只读标签 `.gs-mode-tag`「模式：X（右上角切换）」。
- `js/game-mode.js`：`pvps` 标签去掉「（赛季服）」后缀，仅保留在 long/full 文案里。
- `onGlobalModeChange()` 增补：枪匠面板 mode 跟随 `GWGameMode.get()`；`applyDataScope()` 逻辑未改。

### 验证
- 全页 `.gm-btn` 计数 = 3（PvP 高亮 / PvE / PvPS 普通态），`.tk-seg-btn` = 0，`.gs-mode` = 0。
- 任务数联动：PvP 503 条 vs PvE 499 条（真实切换生效）。
- 切换耗时：任务页 PvP 1089ms、PvE 445ms；click dispatch 61.3ms；body 全程非空，无白屏。
- 三档布局：
  - 1440：无横向溢出。
  - 1024：bar `x=4..325`，按钮高 25，所有 `top=36`，单行不换行，`overflow=false`。
  - 860：同样不换行、无溢出、无遮挡。

### 已知数据缺口（如实标注）
- 地图 POI（物资 / 撤离 / Boss）没有分模式数据文件，PvP 与 PvE 计数完全相同
  （共用撤离 1、PMC 11、Scav 7、转移 3），切换只重算任务点位。
- 价格快照只有单一 `gameMode`（PvP）；PvE 无独立快照，仅在开启在线行情时可能不同。
- 因此「地图 / 装备 / 价格全部按模式刷新」目前只能证明**任务链路**，其余需补数据源。

---

## C. 配装价格只留两项

### 改动
- `app.js` 删除旧 `priceCol`（商人买入 / 卖出 / 兑换 / 制作 / 跳蚤逐行 sources）、`priceSources`、`cheapestBuy`。
- 新增 `flea24hPrice(rec)`（读 `rec.p.a`，即 `avg24hPrice`）与 `flea7dPrice(rec)`（上游无 `avg7dPrice`，恒 0）。
- 新增两列：
  - `p24`「跳蚤 24h 均价」`132px`，缺价显示 `—`，排序缺价排末尾。
  - `p7d`「跳蚤 7d 均价」`132px`，恒 `—`，单元格 `title` 写明
    「上游 tarkov.dev 快照没有 7 日均价（avg7dPrice）字段……不用 24h 均价冒充」。
- 所有列集 `, priceCol]` → `, p24Col, p7dCol]`；枪械预设候选表末两列同步。
- `LW_COL_DEFAULTS`：`price:148` → `p24:132, p7d:132`；gun 组 `price:96` → `p24:110, p7d:110`。
- `gearTotals` / `renderGearCost`：改用 24h 口径；移除 Buy/Sell 两格（`lw-cost-rows` 计数 0）。
- `#lw-prices` 加 `hidden`（配装页不再显示价格档 pills），`renderLwPrices()` 早退。
- 关于面板文案改为：
  `构建期快照 · 配装价格只显示跳蚤 24h / 7d 均价 · 7d 上游缺失一律「—」 · 运行期不联网`
- 配装页无 CSV/导出入口，无需清理。

### 验证
- 表头末两列 = 「跳蚤 24h 均价」「跳蚤 7d 均价」；24h 实测 `162,502 ₽`；7d 恒 `—` 且有缺失原因标题。
- `#lw-prices` `hidden` 且 `display:none`；`lw-cost-rows` = 0。

---

## 测试

- 新增 `tests/test_r74_presets_modes_prices.py`（3 条）：
  预设区存在 + 空态引导 + `equipGunRef` 接线；模式唯一入口 + `applyDataScope` 保留；
  `p24`/`p7d` 两列 + 7d 缺失原因 + 关于文案。
- 同步既有断言（只改真值，未放宽）：
  `test_loadout_workbench.py`、`test_r6_gun_workbench.py`、`test_r10_armor_table.py`、
  `test_r11_armor_grouping.py`、`test_r32_about.py`、`test_r40_armor_effdur.py`。
- Node 抽函数 harness 增补 `flea24hPrice` / `flea7dPrice`，避免 ReferenceError。
- 结果：`pytest tests -q` → **1743 passed / 1 skipped / 0 failed**。

## 构建

- `build/build.ps1`：清单预检 **13241/13241** 通过；`dist\EFTMap\EFTMap.exe` 2,655,605 B（整包 155.1 MB）。
- `build/build_release.ps1 -SkipBase`（三件套）：

| 产物 | 字节 | 时间 | SHA256 |
|---|---:|---|---|
| `release\EFTMap-Setup-0.1.0.exe` | 133,455,886 | 2026-11-05 10:25:03 | `86fec5197a8d36ed5cdb0be9297a519970d3f27b4b67ebe0d64a70c81d820b01` |
| `release\EFTMap-Portable-0.1.0.zip` | 122,598,332 | 2026-11-05 10:20:42 | `49a5411e449dfa5d5f88a29ecf32eae63d6239e8681defabf3bc2d5612a05718` |
| `release\EFTMap-AppWindow-0.1.0.zip` | 122,598,471 | 2026-11-05 10:24:23 | `e0777f7af1f0550f939e74eb80b39b542eebe7c71bde6532925eaa03c3b5f99b` |
| `dist\EFTMap\EFTMap.exe` | 2,655,605 | 2026-11-05 10:16:30 | `9b462788c258e44c0ce9d6c181254259d5cd59b1ffce8762ae9c23700fb625de` |

- 体积按 MiB 显示：Portable 116.9 MiB / AppWindow 116.9 MiB / Setup 127.3 MiB。

## 截图说明

Chrome DevTools MCP 的 `take_screenshot` 在本次会话中对 `filePath` 全部报
`not within any of the configured workspace roots`，因此所有截图均以**内联**形式呈现在对话里，
未能落盘到 `docs/`。档位经 `resize_page` 按 DPR 0.6667 换算请求：1440→960×600，1024→683×…，860→573×…。

## 控制台 / 网络

- console error：1 类（资源 404）共 21 条，无 JS 异常。
- 网络：444 请求，16 个非 2xx（4 个测试预设缩略图 + 12 个既有枪图缺失：
  `6a15ae2ae5267ba21c07f98f`、`6a78b7f8c2016eb33e0027cd`），无 API 失败。
