# R19.27 二次验收报告（只核验，未开发）

验收时间：2026-10-28 21:09–21:20（GMT+8）
验收性质：**独立复核**。本轮未修改任何业务代码、测试或数据文件；未提交/推送 Git；未触碰 `release/` 与校准数据。
所有数字、日志、截图均由本轮实际执行产生（浏览器验收产物 `docs/r19.27/browser-accept.json` 于 21:14 由本轮重跑覆盖）。

---

## 一、Git / 版本状态

| 项 | 验收前 | 验收后 |
|---|---|---|
| 分支 | `main` | `main`（不变） |
| HEAD | `bf438df` | `bf438df`（不变，零提交） |
| 工作区 | 326 项（21 M + 305 ??） | 326 项（同左，未增删） |
| `AM_BUILD` | `R19.27` | `R19.27` |
| HTML 资源串 | 15 处 `?v=r19.27` | 一致 |
| `serve.py` rev | `R19.27-` | 一致；运行中服务 `/api/build` = `R19.27-54245e47` |
| `release/` / 校准 | 未改动（`gun-layout-calibration.json` 及其 .bak/.prev 为前序未跟踪文件） | 同左 |

结论：磁盘代码确实对应 R19.27，三处版本标识一致。

---

## 二、三个存储键的真实实现（逐条核对代码 + 动态探针）

### 2.1 `eftmap.gameMode`（`js/game-mode.js`）

| 核查项 | 结论 | 证据 |
|---|---|---|
| 定义 | `var LS_KEY = "eftmap.gameMode"`（第 15 行） | 读码 |
| 合法值 | 严格 `regular` / `pve` / `pvps`（`KEYS` 来自 `MODES`，`valid()` 走 `KEYS.indexOf`） | 读码 + 线性扫描无第 4 个 key |
| 缺失/非法/读异常 | `readStored()` try/catch → `valid()` 返 null → 回退 `"regular"`；不抛错、不改写存储 | 读码 + 浏览器 G6（写 `"bogus"` 后刷新 → `regular`） |
| 切换一致性 | `set()`：`current = k` → `persist(k)` → `syncButtons()` → `notify()`；控件、`get()`、业务订阅者读同一个 `current` | 读码 + 动态探针 |
| 刷新恢复 | 浏览器 G5：切 PvPS → 刷新 → 仍 PvPS | 本轮实测 |
| **写入失败** | `persist()` 返 false；**内存与控件仍显示新模式（同源）**，业务读 `get()` 也是新模式 → **界面/业务不分裂**；但下次打开会回退存储值 | 动态探针：`set('pvps')` 写失败后 `get()=pvps`，存储仍空；恢复可写后正常落盘 |

**判定：通过。**写入失败只影响"持久性"（下次重开回退），不影响会话内界面/业务一致性。

### 2.2 `eftmap.tasks.progress.v1`（`tasks.js`）

| 核查项 | 结论 | 证据 |
|---|---|---|
| 定义 | `var LS_PROGRESS = "eftmap.tasks.progress.v1"`（第 21 行） | 读码 |
| 结构 | `{schema:1, modes:{regular:{},pve:{},pvps:{}}}`，每任务 `{status, objectives, updatedAt}` | 读码 + 浏览器 P1（`localStorage.getItem` 解剖） |
| 三模式隔离 | 写入面 `setStatusRaw`/`toggleObjective` 均只写 `state.progress.modes[state.mode]`；切换模式不触碰其它桶 | 读码 + 浏览器 P3（PvP completed ≠ PvE/PvPS none） |
| 批量原子性 | `applyStatusBatch`：快照 → 逐条 `setStatusRaw` → `saveProgress()`；**任一步失败回滚快照** + 提示 | **动态探针实证**：`setItem` 抛 QuotaExceeded → 返回 false、内存完全还原（`JSON.stringify` 前后逐字节相等）、提示「已回滚本次 2 项变更」 |
| 旧数据兼容 | 两模式旧结构（R19.22）自动补空 pvps 桶、保留已有条目；坏 JSON / schema 缺失 / null / 空串 → 当空进度，**不抛错、不覆盖存储原值** | 动态探针 6 例全通过 |
| 导入导出 | 导出含三模式段（`eftmap-task-progress:3`）；导入先全量校验后落盘 | 读码 + r1930 验收 T8b |

**发现（不影响本轮判定，属设计取舍，待批准后决定是否改）：**

- **F1（记录，未修）**：单条写入 `setStatus()` / `toggleObjective()` 在 `saveProgress()` 失败时**不回滚内存**——动态探针实测：内存 `A=failed`，存储仍是 `A=completed`。会话内界面与内存一致（都显示 failed），但**刷新后会静默回退为旧值**，且用户无提示（`setStatus` 忽略 `saveProgress` 返回值）。批量路径 `applyStatusBatch` 有完整回滚，单条路径没有。影响面：仅"存储不可写（隐私模式/配额满）+ 单条改状态"场景；常规路径无影响。

### 2.3 `eftmap.tasks.ui.v1`（`tasks.js`）

| 核查项 | 结论 | 证据 |
|---|---|---|
| 定义 | `var LS_UI = "eftmap.tasks.ui.v1"`（第 22 行） | 读码 |
| 只写 perMode | `saveUi()` → `localStorage.setItem(LS_UI, JSON.stringify({ perMode: state.perMode }))`，**无顶层 `mode` 字段** | 读码 |
| 模式来源 | `loadUi()` 中 `state.mode = globalMode()`（读 GWGameMode）；`doc.mode` 仅在 `!window.GWGameMode` 降级路径读取（写入端已不产出该字段） | 读码 |
| perMode 隔离 | `snapshotMode()` 按 `state.mode` 写入独立桶；`restoreMode()` 只套目标桶；三模式的 view/search/filters/selected/cam/ui 互不覆盖 | 读码 |
| 其它模式存储 | 全库扫描：`app.js` 的 `eftmap.gwmode` 是**配枪页视图模式**（caliber/class/table/build），与游戏模式无关，值域无交集；无第三套游戏模式存储 | grep + 读码 |
| 竞态 | 模式由 `GWGameMode.onChange` 单向驱动 `applyMode`；`saveUi` 不写 mode → 无双写覆盖 | 读码 |

**判定：通过。**

---

## 三、测试执行记录（本轮实跑）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `C:/Python314/python.exe -m pytest -q` | **1332 passed, 1 skipped**（98.85s） | 0 |
| `pytest tests/test_r19_27_round.py -q` | **19 passed** | 0 |
| `python tools/r1927_global_accept.py --base http://127.0.0.1:8791 --port 9931` | **17/17** | 0 |
| `python tools/r1931_accept.py --port 9932`（三模式） | **58/58** | 0 |
| `python tools/r1932_accept.py --port 9933`（任务树） | **34/34** | 0 |
| `python tools/r1926_gear_accept.py --port 9934`（配装） | **27/27** | 0 |
| `python tools/r1930_accept.py --port 9935`（任务系统） | **30/30** | 0 |

- 浏览器环境：真实 Chrome（CDP，`tools/r181_accept.py launch/find_chrome`），1680×1050，缓存禁用，临时 profile（每项独立端口/独立 profile）。
- 离线检查：本轮验收 P4 实测 **732 个请求，外部 0**（全同源）。
- 未修改任何旧测试；本轮未新增/删除测试文件（test_r19_27_round.py 为 R19.27 开发轮产物，本轮原样执行）。

---

## 四、与原 R19.27 报告的一致性核对

| 原报告声称 | 复核结果 |
|---|---|
| 全量 1332 passed, 1 skipped | **一致**（本轮重跑同数字） |
| 浏览器 17/17 | **一致**（本轮重跑 21:14 产物） |
| 回归 58/58、34/34、27/27、30/30 | **一致**（本轮全部重跑） |
| 三键结构与职责 | **一致** |
| `applyStatusBatch` 回滚 | **一致且实证有效**（原报告只做代码声明，本轮用抛错探针验证） |
| 单条写入的失败行为 | **原报告未明确说明**——见发现 F1 |

---

## 五、未能验证项（如实标注）

1. **真实浏览器配额满场景**：用可控异常（`setItem` 抛 `QuotaExceeded`）模拟验证了代码路径，未做真实压满存储测试。
2. **GWGameMode 缺失降级路径**：`loadUi` 的 `doc.mode` 分支仅代码可读性确认，未在剥离 game-mode.js 的页面上实测。
3. **多标签页并发写入**：未验证两个标签页同时切换模式/写进度的竞态（`localStorage` 无锁）。
4. F1 的真实用户影响面（隐私模式用户占比）无法在本环境量化。

---

## 六、结论

**通过**（附 1 条记录性发现 F1，不构成阻塞）：

- 三个存储键定义、读写、隔离、兼容与回滚均与 R19.27 报告一致；`applyStatusBatch` 回滚经异常注入实证有效。
- 全量 1332 passed / 专项 19 passed / 浏览器 17+58+34+27+30 全部通过，无回归。
- 三模式进度隔离、模式持久化、离线约束均实测通过。
- F1（单条写入保存失败无回滚、无提示）已记录证据与影响，**按要求未修复**，等待批准后再决定是否处理。

验收完成，停止。未开发 R19.28，未提交，未推送。
