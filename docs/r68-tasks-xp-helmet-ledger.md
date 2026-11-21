# R68 台账：任务页去「商人任务」入口 + XP 主题 + 头盔多层 + 耐久字段定性

host=HOMONAS user=MASTERJJ at=2026-11-04 19:40:38

## 0. 范围与非目标

- 只改源码：`tasks.js` / `tasks.css` / `app.js` / `combat_sim.js` / `style.css` / `index.html` / `tests/test_r41_tasks_ui.py`。
- **不重建 `dist/` 与 `release/`**，不改打包脚本；R67 的未提交改动全部保留。
- 不 git 提交。

---

## 1. 任务界面：隐藏「商人任务」选单

### 做法（为什么不是 `display:none`）

从 **DOM 不渲染**，而不是 `display:none`：

- 页签数组改为 `任务树 / 任务列表 / 任务详情 / 我的进度`（[tasks.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tasks.js#L919)）。
- 删掉 `paneTraders` 的创建与 `body.appendChild`，现在只创建 `tk-pane-list`（[tasks.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tasks.js#L1045)）。
- `cacheEls` 不再缓存 `#tk-traders`；`restoreMode` / `loadUi` / `setView` 的视图白名单缩为四项；`setView`、`renderAll`、`tk-sort` 分支删除 `renderTraders()` 调用。
- `renderTraders()` 函数体保留但宿主恒为 `null`（早期 return），属死代码，未删除以免影响 R41 的历史断言。

**理由**：`display:none` 的元素仍会进入 Tab 顺序与无障碍树，焦点可能落到不可见控件上；不渲染则彻底没有残留入口，也不会留下空栏/空占位，布局宽度由 `task-list` 独占（实测无横向溢出）。

### 实测（真实 Chrome，127.0.0.1:8800）

| 检查项 | 结果 |
| --- | --- |
| `document.getElementById("tk-traders")` | `false`（DOM 不存在，`getBoundingClientRect` 无从为 0 而是不存在） |
| 页签「商人任务」DOM | `false` |
| 页签数 | 4（任务树 56px / 任务列表 67px / 任务详情 67px / 我的进度 67px） |
| 任务行 | 503 行 |
| 商人分组列 | 11 个（Prapor/Therapist/Fence/Skier/Peacekeeper/机修区/Ragman/Jaeger/Lightkeeper/BTR Driver/Ref） |
| `×N` 角标 | 14 个 `.db4-item-more` |
| 快捷搜索 | 输入 `Punisher` → 6 行；清空 → 恢复 503 行 |
| 三档横向溢出 | 0 / 0 / 0 |

---

## 2. 任务页主题：db4 深色 → 全局 XP 风

### 做法

- 以仓库已有的 `theme-windows-xp.css` 为唯一色板，不新增配色。
- `.db4` 令牌改为引用 XP 变量（[tasks.css](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tasks.css#L703)）：
  - `--db4-bg → var(--xp-face)`，`--db4-panel → var(--xp-face-2)`，`--db4-line → var(--xp-border-soft)`，
    `--db4-line2 → var(--xp-border)`，`--db4-text → var(--xp-text)`，`--db4-dim → var(--xp-text-dim)`，
    `--db4-orange → var(--xp-btn-hover-border)`，`--db4-blue → var(--xp-link)`，
    `--db4-green → var(--xp-ok)`，`--db4-red → var(--xp-bad)`。
- 标题色改为 `var(--xp-sel)`；字体统一 `var(--xp-font-family)`（修正了旧代码引用的不存在变量 `--xp-font`）。
- 逐块覆盖：头部 Luna 渐变、页签/模式按钮 XP 渐变与橙色选中态、搜索条白底 `#7f9db9` 边框、商人头像条浅色底、
  商人列浅暖通栏渐变、任务行白底 + hover `--xp-row-hover`、完成态浅绿、失败态浅红、
  物品格白底 + 角标 `rgba(255,255,255,.92)` + `#aca899` 边、经验胶囊 XP 蓝、`Complete` 保留蓝色语义、
  右栏 XP 按钮 + 拨动开关、空态 dim、滚动条 `#c1bbaa`/`#f2f0e6`。
- 未开 XP 时：`theme-windows-xp.css` 是全局加载，页面本身即 XP 风；`.db4` 只是消费同一套变量，不会再落回深色。

### 实测（三档，真实 Chrome，单位 CSS px）

| 视口 | `innerW × innerH` | 可见元素 | 深色残留采样（`#0e0e0e~#1a1a1a`） | 白字浅底 | 横向溢出 | `docW` |
| --- | --- | --- | --- | --- | --- | --- |
| 1440×900 | 1440×900 | 9417 | 0 | 0 | 0 | 1440 |
| 1024×768 | 1024×768 | 9417 | 0 | 0 | 0 | 1024 |
| 860×720 | 859×720 | 9417 | 0 | 0 | 0 | 859 |

- 任务行底色 `rgb(255,255,255)`，任务名 `rgb(0,0,0)`，标题 `rgb(49,106,197)`。
- 截图：
  - [r68-tasks-1440.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r68-tasks-xp-helmet/smoke/r68-tasks-1440.png)
  - [r68-tasks-1024.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r68-tasks-xp-helmet/smoke/r68-tasks-1024.png)
  - [r68-tasks-860.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r68-tasks-xp-helmet/smoke/r68-tasks-860.png)

---

## 3. 逐发模拟：头盔附加面罩/护耳/护颈多层

### 做法

- 新增 `amSimHelmetMounts(hrec, items)`（[app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L22465)）：
  - 只读**该头盔自己的** `items.json → slots[].allow`，再过滤 `cl > 0 && dur > 0 && z 非空` 的「装甲附加件」；
  - 导轨、夜视、耳机等没有护甲字段的挂件不进入模拟，避免凭空造 0 耐久层；
  - 同一槽位多件（同款涂装）按中文名排序，保证顺序稳定；
  - 槽位名按物理外→内取词：护目 → 护颚 → 护耳 → 护颈 → 头部 → 头顶 → 后脑。
- `amSimArmorLayers` 在头盔本体之后追加这些层，`kind="face"`（[app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L22431)）：
  - 只接受该头盔当前槽位 `allow` 内的选择（`slot.ids.indexOf(mid) < 0` 直接忽略）；
  - 缺防护区 / 缺耐久时不静默补 0，直接跳过该层。
- 层序：`combat_sim.js` 的 `KIND_RANK = { face: 0, plate: 1, helmet: 2, liner: 3 }`（[combat_sim.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/combat_sim.js#L302)），
  即「面罩/护目 → 硬插板 → 头盔本体 → 软内衬」，与物理命中顺序一致；`plate` 与 `helmet` 的相对次序保持不变，原有「护甲 + 插板 + 内衬」链路不受影响。
- 跳弹条件放宽到 `face / helmet / plate`，但仍要求该层有 `ricochetParams` 且入射角 > 0（[combat_sim.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/combat_sim.js#L491)）。
- UI：`renderSimHelmet` 为每个兼容槽位生成 `select[data-sim=mount-pick]`，选项为「未安装 + 兼容件」；
  换头盔时清空挂件选择（旧件不再兼容）。

### 兼容数量（`items.json` 实测）

| 指标 | 数值 |
| --- | --- |
| 头盔总数 | 112 |
| 有 ≥1 个装甲附加槽的头盔 | 56 |
| 装甲附加槽位总数 | 93 |
| 不同装甲附加件 | 78 |
| 无任何可兼容装甲附加件 | 56（占一半，见局限） |
| Altyn（`5aa7e276e5b5b000171d0647`） | 槽 0：2 件面罩（`5aa7e373…`、`6a82dbbf…`）；槽 1 仅盔罩（无护甲字段）→ UI 显示 1 个槽位、3 个选项 |

### 前后对照（真实 Chrome，固定种子 12345，SSA AP 5.56x45，命中头部，3 发）

**安装 Altyn 面罩（`5aa7e373e5b5b000137b76f0`）**

- 第 1 发：面罩 50→39.3（穿透，掷 0.484，概率 94.1%，甲伤 10.7，减伤 0.875）
  → 头盔 81→71.1（挡住，甲伤 9.9）→ 钝伤 5.07 → `Helmet_top` 0.84 → `Helmet_back` 0.14 → `Helmet_ears` 0.02 → 人体 0.02。
- 第 2 发：面罩 39.3→28.6（穿透）→ 头盔 71.1→61.2（穿透）→ `Helmet_top` 27→20.2（挡住，甲伤 6.8）。
- 终态：面罩 18.13 / 头盔 51.46 / top 13.15 / back 27 / ears 27。

**未安装面罩**

- 第 1 发：头盔 81→70.3（穿透）→ `Helmet_top` 27→17.7（挡住，钝伤 5.07→0.84→0.14→人体 0.14）。
- 第 2 发：头盔 70.3→59.6（穿透）→ `Helmet_top` 17.7→8.5（穿透）→ `Helmet_back` 27→19.7（挡住）。
- 第 3 发：头盔 59.6→49.1；`Helmet_top` 8.5→0（击毁）。
- 终态：头盔 49.13 / top 0 / back 10.89 / ears 27。

差异：面罩层替头盔本体吸收了前两发的甲伤，头盔本体多保留 2.33 耐久，`Helmet_top` 从 0 提升到 13.15；
钝伤链每层输出一致（面罩层自身 BT 0.0792 在首层生效后才进入本体）。

- 截图：
  - [r68-helmet-fields.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r68-tasks-xp-helmet/smoke/r68-helmet-fields.png)（头盔附加件下拉 + 右侧逐发日志/层链）
  - [r68-dur-fields.png](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/docs/r68-tasks-xp-helmet/smoke/r68-dur-fields.png)（「当前耐久 / 原始满耐久」字段位置）

---

## 4. 「当前耐久 / 原始满耐久」先定性

### 定性结论

**不是数值错，也不是两个字段重复；是「内部字段命名 / 展示口径」误导 + 缺少『修复后当前上限』字段。**

证据链：

1. `items.json` 每个护甲只有一条出厂满耐久 `dur`；没有「维修后当前上限」字段。
2. `durPair(base)`（[app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L22338)）返回 `{ dur: 当前耐久, durMax: 出厂满, durOrig: 出厂满 }`——
   `durMax` 是历史字段名，值与 `durOrig` 相同，**实际不是「当前上限」**。
3. UI 两个输入：`当前耐久 → s.armorDur`、`原始满耐久 → s.armorOrig`；这两个标签本身正确。
4. 穿透概率分母使用 `durOrig`（[app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L21108)），口径 ÷ 出厂原始满耐久，与视频一致。

因此 R56 审计指出的「`durMax` 存出厂 `orig`、UI 却标『原始满耐久』」是**标签错位（历史字段名）**：
展示值没错，是 `durMax` 这个名字容易被读成「上限」。

### 最小修复

- 结果胶囊文案：`耐久 <当前> / 出厂满 <出厂>`（[app.js](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L24377)），不再写「上限」。
- `durPair` 与 `amArmorPenChance` 加注释，明确 `durMax` 是历史字段名、等于出厂 `durOrig`，本项目没有「维修后当前上限」数据。
- **未改公式**（分母仍是 `durOrig`）；「修复后当前上限」只记录为缺口，未自行造字段。

---

## 5. 测试

- 全量：`python -m pytest tests -q` → **1736 passed, 1 skipped**（基线 1736 passed / 1 skipped）。
- 因本次主题改动同步了 2 条断言（均在 `tests/test_r41_tasks_ui.py`）：
  1. `test_rail_is_centered_buttons`：旧断言要求右栏选中态 `background: #efefef; color: #111`（深色/参考站口径）；
     现改为校验 `.db4-rail-btn.is-on` 块内有 `font-weight: 700`（XP 橙色渐变选中态）。**直接对应第 2 项主题切换。**
  2. `test_db4_tokens`：旧断言要求深色令牌 `#121212/#151515/#262626/#e6e6e6/#f08a24` 存在；
     现改为校验 `--db4-*` 引用 `--xp-*` 变量，并反向断言这 5 个深色值不得残留。**直接对应第 2 项。**

---

## 6. 局限

1. **并非所有头盔都能挂装甲件**：112 顶头盔中 56 顶没有任何兼容的装甲附加件（如大量纯布帽/耳机帽），UI 会显示「该头盔没有可兼容的装甲附加件」。这是数据事实，不是 bug。
2. **缺少『维修后当前上限』**：`items.json` 无该字段，当前口径为 ÷ 出厂满耐久；修复后实际上限会低于出厂值，模拟结果会偏乐观。已记录，未擅自改公式。
3. **跳弹**：仅入射角 > 0 且该层存在 `ricochetParams` 时显示；本次截图使用 0°，因此面罩层未出现跳弹行。
4. **XP 主题角标**：物品格 `×N` 角标改为半透明白底 + 深字 + `#aca899` 边，在浅色行底上对比度可读；但与深色小图标叠加时，局部对比度仍取决于图标本身。
5. **`tasks.css` 仍有未被渲染的 `.tl-*` 旧样式**（如 `.tl-thumb #161a1f`），对应 DOM 已不存在，不影响可见像素；本轮未清理以避免牵动历史断言。
6. **未重建 `dist/release`**：本轮只改源码，打包由另一次任务执行。

---

## 7. 变更文件

- `tasks.js`：移除商人任务页签与 pane、视图白名单收敛。
- `tasks.css`：`.db4` 深色令牌 → XP 变量；逐块 Luna 化；字体变量修正。
- `app.js`：`amSimHelmetMounts`、头盔挂件层、UI 挂件下拉、事件、耐久文案/注释。
- `combat_sim.js`：`KIND_RANK` 加 `face`；跳弹条件包含 `face`。
- `style.css`：头盔挂件标签宽度。
- `index.html`：任务模块注释去掉「商人任务」。
- `tests/test_r41_tasks_ui.py`：2 条过期断言同步。
