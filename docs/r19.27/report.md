# R19.27 交付报告：递归任务依赖联动、全局游戏模式与任务进度持久化

构建号：`R19.27`（`AM_BUILD`、全部 `?v=r19.27`、`tools/serve.py` rev 已同步）
项目：`D:\personal\trae\02-塔科夫\e ft-interactive-map`（路径以实际为准：`D:\personal\trae\02-塔科夫\eft-interactive-map`）

---

## 1. 当前版本、Git 状态与测试基线

| 项 | 值 |
|---|---|
| 分支 / HEAD | `main` / `bf438df` |
| 接手时构建号 | `R19.26`（R19.27 未被占用） |
| 工作区 | 323 项未提交改动（前序轮次遗留），**全部保留**，未做任何 Git 操作 |
| 修改前全量 pytest | **1313 passed, 1 skipped**（`build-cache/r1927-baseline.log`，改动前实跑） |
| 修改后全量 pytest | **1332 passed, 1 skipped**（+19 = 本轮 `tests/test_r19_27_round.py`） |

R19.26 报告中的数字未被直接引用；三模式 / 任务树 / 配装验收均在本轮重新执行（见 §8）。
遗留文件 `tools/r1927_accept.py` 是 **R19.19** 的旧脚本（名字撞车），**未覆盖**，本轮验收脚本命名为 `tools/r1927_global_accept.py`。

---

## 2. 递归前置联动：原始缺陷与修复方案

### 2.1 原始缺陷（R19.26 实现）

`planPrereqFix` 只遍历目标任务的**一层** `prerequisites`：把直接前置调到目标档位就进计划，前置自己的前置不再检查。
链 `A → B → C` 在把 C 设为已完成时只改 B，A 仍是未开始 —— B 本身仍不满足自己的前置，整条链没有真正修复。

### 2.2 修复方案（`tasks.js` planPrereqFix 递归版）

**分析依赖 → 递归规划 → 展示全部改动（按深度分组）→ 用户确认 → 计划签名复核 → 一次 `applyStatusBatch` 原子落盘 → 刷新。**

- `walk(id, wantStatus, depth, via)` 沿前置向上递归：每选定一个前置的目标状态，就以该状态为新目标继续处理它自己的前置。
- 确认前**零写入**（沿用 R19.26 的计划/执行分离）；取消路径不碰任何状态。
- 弹窗按「直接前置（第 1 层）/ 间接前置（第 N 层）」分组，显示当前状态 → 目标状态、要求档位、依赖来源（`via`）。
- 执行前 `planSignature` 复核：弹窗期间状态若变化，放弃本次操作并提示重新计算（不覆盖新状态）。

### 2.3 防御

| 场景 | 处理 |
|---|---|
| 依赖环 | `path` 栈检测 → 进 `unfixable`（注明「循环依赖」），不静默删边、不继续展开 |
| 指向不存在的任务 | 进 `unfixable`（「任务不存在」），**不进改动清单** |
| 同一任务被多条链要求 | `planned` 表去重；档位冲突记 unfixable，不硬覆盖 |
| 展开规模 | `guard > 3000` 停止并提示（未做任何修改） |
| 规划异常 | 不产生部分修改（确认前本来就不写） |

---

## 3. 递归测试覆盖的依赖结构（场景 A–G）

`tests/test_r19_27_round.py` 用 Node 从 `tasks.js` 抽真函数跑合成数据（不复制实现）：

| 场景 | 覆盖 | 结果 |
|---|---|---|
| A 三层直线 A→B→C | 计划含 B@d0 + A@d1 | ✓ |
| B 五层长链 | 4 个前置全进计划（d0…d3），非只动一层 | ✓ |
| C 分支汇合（AND） | 多前置条目全部规划 | ✓ |
| D OR 分支 | 只选改动最少的一条（O1），O2 不碰；已满足则整组不动 | ✓ |
| E 不同目标状态 | 需「进行中」→ active；需「失败」→ failed（不一律 completed） | ✓ |
| F 异常依赖 | 环 / 缺失 ID 不挂死、不删边、不产生部分修改 | ✓ |
| G 取消确认 | 取消后当前任务与全部前置保持原状 | ✓ |

另有：后续重置不退化（B/C 双父 AND 下游递归重置）、非任务条件只提示不伪造、词面映射（见 §4）。

---

## 4. AND / OR 条件与非任务型条件

依据真实数据（`data/tasks/tasks.regular.json` 实测）：

- `prerequisites` 条目之间默认 **AND**（209 条 `logic=all`）；
- `logic=or` 的条目构成**或组**（13 条）：组内任一满足即可，规划时**只选改动代价最小的一条**（弹窗注明所选分支），其余分支保持不变；
- 单条目 `statuses` 多值（如 `['complete','failed']`）也是 OR：`pickStatus` 只取一档。

**R19.27 修正的词面 bug**：数据 statuses 用 `complete / active / failed`，而进度状态是 `completed / active / failed`。旧 `satisfies`/`pickStatus` 只认 `"fail"`，导致「需前置失败」永远判不满足。现统一走 `WANT_TO_STATUS` 归一表，两个方向同一张表。

非任务型条件（商人等级 / 好感 / 阵营 / 技能…）：只进 `notes` 展示，**绝不伪造完成**；若无可调整的任务型前置，计划为 `null`，不弹无意义窗口。

---

## 5. 全局游戏模式：统一入口与持久化

| 项 | 实现 |
|---|---|
| 唯一状态 | `js/game-mode.js` → `window.GWGameMode.get()/set()/onChange()` |
| 控件位置 | 全局页头 `#game-mode-bar`（menubar 右上角，版本徽标左侧） |
| 持久化 | `localStorage["eftmap.gameMode"]`，只接受 `regular/pve/pvps`，非法/缺失回退 `regular` |
| 任务模块 | `state.mode` 只读全局；`setMode` → `GWGameMode.set` → 通知回调 `applyMode` 换数据 |
| 页面局部状态 | 搜索/筛选/缩放/选中仍存 `eftmap.tasks.ui.v1` 的 `perMode`（**不再存 mode**） |
| 页内按钮 | 任务页原有 `.tk-modebar` 已移除（不重复），只留「模式：…」文字提示 |

五页（地图/配装/配枪/弹药/任务）共用同一控件与同一状态；切换不清其他模式的进度；无模式差异的公共数据（枪械/弹药）不重建。

---

## 6. 各页面模式控件验收（真实浏览器）

| 检查 | 结果 |
|---|---|
| 五页右上角可见同一控件（inMenubar） | ✓ |
| 配装页切 PvPS → 任务页仍 PvPS | ✓ |
| 刷新后恢复 PvPS | ✓ |
| 非法存储值回退 PvP | ✓ |
| 任务模块数据随全局模式切换 | ✓（r1931 58/58 复跑） |

---

## 7. 任务进度持久化与存储键实现

### 7.1 三个 localStorage 键（具体实现）

| 键名 | 文件 | 写入点 | 结构 | 职责 |
|---|---|---|---|---|
| `eftmap.gameMode` | `js/game-mode.js` | `GWGameMode.set()` | 字符串：`"regular"` \| `"pve"` \| `"pvps"` | **全局游戏模式唯一持久化**。读取时 `valid(raw)` 校验，非法/缺失回退 `"regular"`；刷新与重开应用后恢复 |
| `eftmap.tasks.progress.v1` | `tasks.js` | `saveProgress()` | `{schema:1, modes:{regular:{},pve:{},pvps:{}}}`，每模式 `{taskId:{status,objectives,updatedAt}}` | **三模式任务进度**，三桶互不串用 |
| `eftmap.tasks.ui.v1` | `tasks.js` | `saveUi()` | `{perMode:{<mode>:{view,search,filters,selected,cam,ui}}}` | 每模式的浏览状态（**R19.27 起不再存 mode**——模式只认 `eftmap.gameMode`） |

代码定位：

```js
// js/game-mode.js:15
var LS_KEY = "eftmap.gameMode";
// 写：persist(key) → localStorage.setItem(LS_KEY, key)
// 读：readStored() → valid(localStorage.getItem(LS_KEY))，非法返回 null → 回退 "regular"

// tasks.js:21-22
var LS_PROGRESS = "eftmap.tasks.progress.v1";
var LS_UI = "eftmap.tasks.ui.v1";
// saveUi(): localStorage.setItem(LS_UI, JSON.stringify({ perMode: state.perMode }))
//          —— 不含 mode 字段，避免与全局模式键冲突/竞态
```

### 7.2 写入管道（原子 + 回滚）

全部进度写入口（`setStatus` / `requestStatusChange` / `applyStatusBatch` / `toggleObjective` / 导入）统一走：
`setStatusRaw(id, status)`（只改内存）→ `saveProgress()`（落盘）。

`applyStatusBatch(pairs)`：
1. 先打快照 `JSON.stringify(state.progress)`；
2. 逐条 `setStatusRaw`；
3. `saveProgress()` 失败 → **回滚快照** + 明确提示，绝不留半截状态；
4. 成功 → 一次落盘 + `broadcast()` + `renderAll()`。

### 7.3 模式与进度的关系

- 切换模式（`eftmap.gameMode`）**不清**任何模式的进度桶；
- 进度按 `modes[state.mode]` 读写，三模式隔离（浏览器实测 P3）；
- 页面局部状态（搜索/筛选/缩放）存 `eftmap.tasks.ui.v1` 的 `perMode[mode]`，与全局模式键分离。


- **写入口统一**：`setStatus` / `requestStatusChange` / `applyStatusBatch` / `toggleObjective` / 导入 全部落到 `setStatusRaw` + `saveProgress()`（同一管道，无旁路 `localStorage.setItem`）。
- **原子批量**：`applyStatusBatch` 先打快照，任一步抛错或 `saveProgress()` 失败 → **回滚到快照**并明确提示，绝不留半截状态。
- **存储**：`eftmap.tasks.progress.v1`，`modes.{regular,pve,pvps}` 三桶隔离；切换模式/刷新/重开互不串用（浏览器实测 P1–P3）。
- 导入导出格式不变（`eftmap-task-progress` + 三模式段），批量变更不影响兼容性。

---

## 8. 修改前后测试结果

| 项 | 修改前 | 修改后 |
|---|---|---|
| 全量 pytest | 1313 passed, 1 skipped | **1332 passed, 1 skipped** |
| 本轮专项 `test_r19_27_round.py` | — | **19/19** |
| 浏览器验收 `r1927_global_accept.py` | — | **17/17** |
| 回归 `r1931`（三模式） | 58/58 | **58/58** |
| 回归 `r1932`（任务树 R19.25） | 34/34 | **34/34** |
| 回归 `r1926_gear_accept`（配装） | 27/27 | **27/27** |
| 回归 `r1930`（任务系统 R19.22） | 30/30 | **30/30** |
| 离线 | — | 本轮验收 P4：全部请求同源，0 外链 |

### 旧测试升级（未删除、未弱化）

| 测试 | 原断言 | 升级后 |
|---|---|---|
| `test_r19_26` D 组版本 | 写死 R19.26 | 跟随 `AM_BUILD` + 覆盖 `js/game-mode.js` |
| `test_r19_26` C 组 OR | 搜旧 pickStatus 字面 | 改查词面归一 `wantStatus` + `logic=or` 或组 |
| `test_r19_26` 批量落盘 | 500 字节内 1 次 save | 扩到含回滚分支，仍只落一次 + 要求快照回滚 |
| `test_r19_23` A 组按钮位置 | 「贴在任务模块右上角」 | 「固定在全局页头右上角」（要求 inMenubar） |
| `r1931` A3 度量 | 量任务壳内边距 | 量 menubar 内位置（gapRight 上界按版本徽标放宽） |

---

## 9. 浏览器截图与未验证事项

截图（`docs/r19.27/shots/`）：`01-map-mode.png`（地图页全局控件）、`02-loadout-mode.png`（配装页）、`03-detail-before.png`、`04-recursive-dialog.png`（递归计划分层展示）、`05-reset-dialog.png`（后续重置确认）、`06-mode-isolation.png`（三模式隔离）、`07-final.png`。

**未验证（如实标注）**：
- <1280px 窄屏与高 DPI（125%/150%）下的模式栏换行；
- `GWGameMode` 缺失时的降级路径（代码有 `applyMode` 兜底，但未在无模块环境实测）；
- `localStorage` 真正配额满时的回滚路径（用保存失败分支覆盖，未做真实压满）；
- 枪械/弹药页无模式差异数据（按要求不制造差异），仅验证控件可见与状态一致。

---

## 10. 修改文件清单

| 文件 | 职责 |
|---|---|
| `js/game-mode.js` | **新增**：全局游戏模式状态 + 右上角控件 + 持久化 |
| `index.html` | 页头挂 `#game-mode-bar`、引入 game-mode.js、版本串 r19.27 |
| `tasks.js` | planPrereqFix 递归 + OR 组选路 + 词面归一；setMode/applyMode 接全局；saveProgress 返回值 + applyStatusBatch 回滚；骨架去页内模式按钮 |
| `style.css` | `.game-mode-bar` 控件样式（XP Luna） |
| `tasks.css` | `.tk-mode-hint` / `.tk-plan-group` 样式 |
| `app.js` / `tools/serve.py` | `AM_BUILD=R19.27`、rev 同步 |
| `tests/test_r19_27_round.py` | **新增** 19 条专项测试 |
| `tools/r1927_global_accept.py` | **新增** 17 项真实浏览器验收 |
| `tools/r1931_accept.py` | A3/A6 度量升级到全局页头 |
| `tests/test_r19_23_round.py` / `test_r19_26_round.py` | 旧断言升级（见 §8） |

未改动：`data/tasks/*`（数据管线）、三模式进度结构、配装/枪械/弹药业务逻辑、`release/`、`gun-layout-calibration.json`。
Git：分支 `main`，HEAD 仍为 `bf438df`，**零提交零推送**；工作区 326 项未提交改动全部保留（含前序 323 项 + 本轮新增/修改）。


---

## 11. 其它发现

- R19.26 的 `satisfies`/`pickStatus` 词面 bug（`failed` vs `fail`）是历史遗留，本轮顺带修正并补测试（属本轮 AND/OR 正确性范围）。
- `tools/r1927_accept.py`、`tools/r1926_accept.py` 均为早期轮次遗留的同名文件，本轮一律未覆盖。
