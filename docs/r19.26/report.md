# R19.26 交付报告：配装状态持久化 / 装备栏紧凑化 / 任务进度联动

构建标记：`R19.26`（`AM_BUILD`、`index.html ?v=r19.26`、`tools/serve.py` rev 同步）
文档目录：`docs/r19.26/`（不覆盖其它版本目录）

---

## 1. 当前状态与测试基线

| 项 | 值 |
|---|---|
| Git | 分支 `main`，HEAD `bf438df`；**未提交、未推送** |
| 工作区 | 319 项前序未提交改动全部保留；`release/`、`data/gun-layout-calibration.json` 未触碰 |
| 接手时版本 | `R19.25.1`（任务书建议 R19.26，已确认该构建号未被占用 → 本轮使用 R19.26） |
| 修改前基线 | `build-cache/r1926-baseline.log`（全量 pytest，改动前跑） |
| 遗留文件 | `tools/r1926_accept.py` 等是 **R19.18 时期的同名旧文件**（内容属于槽位审计），本轮未覆盖、未删除；本轮验收脚本命名为 `tools/r1926_gear_accept.py` |

## 2. 防弹插板丢失的根本原因

插板值存在 `state.loadout["armor/Front_plate"]` 这类**不带护甲身份**的键上（`rootKey/zone`）：

1. **换护甲越权套用**：换成同样有 `Front_plate` 的护甲 B，`plateSlotState` 读同一个键 → A 的插板被显示/计入 B（兼容性被绕过）。
2. **换护甲配置丢失**：换成没有该板位的护甲 → `pruneOrphanSlots` 判定「树上已无此节点」直接 `delete` → 切回 A 时配置没了。
3. 页面切换 / 重渲染本身不丢数据（都在 `state.loadout`），丢的是**键的归属**——所以不能靠"缓存 HTML 片段"或临时变量修。

## 3. 配装状态保存与恢复方案

**稳定身份 = 板位节点 id + 所属护甲物品 id**：键形如 `armor/Front_plate@<护甲ID>`。

- 仍在既有 `state.loadout` / `localStorage["eftmap.loadout"]` 里，**不新建键、不建平行状态系统**。
- `plateGet/plateSet/nodeLoadoutId/nodeSetLoadout` 是唯一读写入口；候选表、焦点面板、费用清单、
  重量/减益/护甲等级统计全部改走它们。
- `pruneOrphanSlots`：带 `@` 的插板记录只在「护甲 / 板位 / 插板不再合法」时清理；
  旧格式 `root/zone` 自动迁移到当前护甲名下（不静默丢用户数据）。
- 切到护甲 B 时只读 B 自己的记录；A 的记录保留但**不参与** B 的显示、重量、价格、护甲等级与导出。
- 不兼容插板不会被套用：读取时按护甲身份隔离，合法性再由 `candidatesOf` / `plateRecordValid` 双重把关。
- 多方案：根槽位（配装方案）与插板键同处一个 `state.loadout`，方案切换沿用原逻辑，不串用。
- 会话内与刷新后都持久（验收 P3/P4/P5）。

## 4. 左侧装备栏改造前后（1680×1050 实测，`tools/r1926_side_measure.py`）

| 指标 | 改造前 | 改造后 |
|---|---|---|
| `.lw-side` 内容高 scrollHeight | **1021px**（超出可视 980，需滚动） | **980px**（= 可视高，不再滚动） |
| 卡片板 `.lw-board` 高 | 639px | 584px |
| 相邻装备行间距 | 5 / 26 / 26 / 26 | **3 / 12 / 12 / 12** |
| 顶部统计条 | min-height 54u / 上内边距 17u | 44u / 10u |
| 文本裁切 | 0 | 0 |

做法只动**行与行之间的垫高行 / 行距 / 统计条内边距**（26u→12u、13u→6u、5u→3u、row-gap 11u→7u），
**没有缩小任何字号**，卡片本体尺寸、图标、点击区、悬停提示全部保留（截图 `shots/02-side-compact.png`）。

## 5. 任务状态联动的前置条件计算

- 复用现有依赖数据：`prerequisites`（条目间 AND）+ 条目内 `statuses`（OR，满足其一）。
- **情况 A**（设为 进行中/已完成）：`planPrereqFix` 逐条比对前置当前状态与 `statuses`；
  未满足的进 `changes`（用 `pickStatus` 选与用户目标一致、否则改动最小的一档——OR 不全量完成）；
  非任务型条件（商人等级/阵营/技能…）进 `notes` **只提示不伪造**；等级条件走现有校验不伪造。
- 确认后 `applyStatusBatch` 一次性写入（内存改完再一次 `saveProgress`），随后统一刷新树/详情/进度。
- 执行前 `planSignature` 复核：状态若刚被其它操作改动 → 计划作废、提示重做，**不覆盖**。

## 6. 后续任务重置范围与 AND / OR

- **情况 B**（设为 未开始）：`planFollowUpReset` 只沿 `followUps`（真实解锁方向，**失败分支不是解锁边**）
  BFS 传播；每个候选按「假想状态 = 目标任务已未开始 + 已决定的重置」重算其 `prerequisites`。
- OR 保护：若另一档/其它前置仍满足 → 该后续**不进**重置计划。
- 直接/间接分层展示（`depth`），弹窗按钮：`确认并重置后续任务` / `仅重置当前任务` / `取消`。
- 只清进度状态；任务定义、依赖边、目标、奖励、模式信息、其它模式进度一律不动。

## 7. 新增 / 修改文件

| 文件 | 说明 |
|---|---|
| `app.js` | 插板稳定身份（`plateStorageKey` 等 8 个助手）、prune 迁移、统计过滤、`window.GWLoadout` 受控接口、版本 R19.26 |
| `tasks.js` | `setStatusRaw/applyStatusBatch`、`planPrereqFix/planFollowUpReset/planSignature/planBody/openLinkageDialog/executePlan/requestStatusChange`；入口改走联动 |
| `tasks.css` | 联动弹窗计划列表样式（`.tk-plan-*`） |
| `style.css` | 左侧装备栏纵向紧凑化（4 处） |
| `index.html` / `tools/serve.py` | `?v=r19.26` / rev 同步 |
| `tools/r1926_side_measure.py` | 装备栏实测（before/after） |
| `tools/r1926_gear_accept.py` | 本轮真实浏览器验收 27 项 |
| `tests/test_r19_26_round.py` | 专项测试 |
| `docs/r19.26/*` | 本报告 + 实测 JSON + 截图 |

## 8. 测试前后真实数据

| 项 | 结果 |
|---|---|
| 修改前全量 pytest | 见 `build-cache/r1926-baseline.log` |
| 修改后全量 pytest | **见文末「最终数字」**（执行后回填） |
| 本轮专项 `tests/test_r19_26_round.py` | **19 条全部通过** |
| 真实浏览器验收 `tools/r1926_gear_accept.py` | **27/27**（P1–P7 插板、L1–L3 布局、T0–T12 联动、G1–G2 离线/无异常） |
| 回归 `r1932` / `r1931` / `r1930` | 见文末（任务树 / 三模式 / R19.22） |

## 9. 截图（`docs/r19.26/shots/`，真实浏览器）

- `side-before.png` / `side-after.png`：左侧装备栏改造前后
- `01-loadout-plates.png`：配装工作台（插板状态）
- `02-side-compact.png`：紧凑化后的装备栏
- `03-link-dialog-prereq.png`：「前置任务尚未完成」确认弹窗
- `04-link-applied.png`：确认调整后的状态
- `05-link-dialog-reset.png`：「重置后续任务？」弹窗

## 10. 未解决 / 未验证（如实）

- 未验证：<1280px 窄屏与 125%/150% 高 DPI 下的装备栏行距表现；插板弹窗在窄屏的布局。
- 弹窗降级路径：若 `window.GWUI` 缺失会退回原生 `confirm()`（代码里有注释记录；本次验收走的是 GWUI.dialog）。
- 「进行中/已完成 + 前置未满足 + 只存在非任务型缺口」时**不弹窗**（无关联任务可调，避免无意义弹窗），
  与任务书 §7.1 的字面表述略有取舍，已在 §5 说明。
- 旧 `tools/r1926_*.py` 遗留文件未清理（与本任务无关）。

---

## 最终数字（本轮实跑）

| 项 | 结果 |
|---|---|
| 修改前全量 pytest | **1294 passed, 1 skipped**（`build-cache/r1926-baseline.log`，改动前） |
| 修改后全量 pytest | **1313 passed, 1 skipped**（+19 = 本轮专项 `test_r19_26_round.py` 全部新增） |
| 本轮专项 `tests/test_r19_26_round.py` | 19/19 |
| 动态槽位模型 `tests/test_loadout_workbench.py` | 259 条场景全过（含升级后的 U3/T21/T25.6/T30） |
| 真实浏览器验收 `tools/r1926_gear_accept.py` | **27/27** |
| 回归 `r1931_accept.py`（三模式） | **58/58** |
| 回归 `r1930_accept.py`（R19.22） | **30/30** |
| 回归 `r1932_accept.py`（任务树 R19.25） | **34/34** |
| 离线 | 验收 G1：全部请求同源，0 外链 |
| i18n | 未新增英文 UI 文案；商人英文名例外规则未受影响 |

### 旧测试的升级（未删除、未弱化）

| 测试 | 原断言 | 升级后 |
|---|---|---|
| `test_loadout_workbench` U3 | 换护甲后插板键被删（编码了缺陷行为） | 树上节点消失 + **历史配置保留** + 新护甲不被套用（3 条更强断言） |
| 同上 T21 / T30 / T25.6 | 直接读写 `armor/Front_plate` | 改为稳定身份键 `armor/Front_plate@armorA`，并补「卸甲不清历史」断言 |
| `test_r19_23` D 组进度隔离 | 只覆盖 `setStatus` 写入面 | 扩到 `setStatusRaw + toggleObjective`（新写入面），仍禁止写死模式名 |
| `test_r19_25` E 组版本 | 写死 R19.25.1 | 跟随 `AM_BUILD` 正则 + 资源串一致 |
