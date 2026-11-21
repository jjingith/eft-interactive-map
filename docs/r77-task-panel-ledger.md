# R77 台账：地图页任务 / 剧情面板（单条开关 + 四档筛选 + 右键选单 + 详情深链）

host=HOMONAS user=MASTERJJ at=2026-11-05 16:18:36 +08:00

## 0. 结论先行

A–D 四条全部落地并在真实页面（Chrome DevTools，`http://127.0.0.1:8787/`，PvP / 塔科夫街区）实测取证：

- A：每行一个真开关（`input[type=checkbox][role=switch]`），按 `taskId + 模式` 存本地，
  刷新 / 切图 / 切模式后各自恢复；总闸关掉时点数归 0，但单条开关状态不清空，重开恢复。
- B：全部 / 未完成 / 已完成 / 可并行推进 四档互斥单选，列表与地图点同步过滤；
  筛选只改显隐，不改每条开关的存储值。
- C：任务行右键弹自定义菜单，「在地图上显示 / 不显示」与行开关同源，「任务详细」跳到任务系统；
  剧情行的「任务详细」明确禁用并写清原因。
- D：`#tasks:<taskId>` 深链跳到任务详情（复用 `renderDetail()`，落点滚到顶部）；
  浏览器后退回地图，地图状态（点数 / 开关 / 筛选 / 模式）不丢；ID 不存在时给可读提示。

本轮只改前端 4 个文件（`app.js` / `tasks.js` / `index.html` / `style.css`），
未加后端接口、未引第三方库、未动 XP 视觉体系；**未打包、未 commit**。

## 1. 改动文件

| 文件 | 改动 |
| --- | --- |
| `index.html` | 右侧任务面板：四档 radio（`name=task-point-filter`）+ 判定口径小字 `#task-filter-note`；旧「显示全部」按钮改为总闸 checkbox `#task-show-all` |
| `app.js` | 新增 R77 一套状态与函数：`loadTaskPointPrefs` / `setTaskPointSwitch` / `taskFilterPass` / `taskPrereqSatisfied` / `taskGroupVisible` / `applyTaskPointDisplay` / 右键菜单 / `#tasks:` 路由；`renderOverlay` 记录 `state.taskGroupNodes`，开关与筛选只改 `display`；`renderTaskPanel` / `taskRow` 重写 |
| `tasks.js` | `openTask()` 支持深链排队（数据未载入 → `pendingTaskOpen`）；`scrollDetailTop()`；`showMissingTask()` 与详情区可读空态 |
| `style.css` | `.task-filter*`、`.task-master-toggle`、`.task-row-head`、`.task-switch`、`.task-row.is-off`、`.task-context-menu` |

### 1.1 本轮修掉的一个真 bug

`taskRow()` 里先把开关的 checkbox 存在 `var box`，函数后段「楼层小按钮容器」又写了一次
`var box = document.createElement("div")`。`var` 提升导致 change 闭包里的 `box` 变成那个 div，
`box.checked === undefined`，于是每次点开关都被写成 `false`。已把后者改名 `floorBox`，
change 处理器改用 `ev.target.checked`。修复后实测恢复正常（见 2.1）。

## 2. A：单条开关（实测）

测试地图：塔科夫街区（PvP），任务/剧情图层开启，任务点节点总数 90（tasks 78 + stories 12）。

| 步骤 | 结果 |
| --- | --- |
| 基线（54 行全开） | 可见点 **90** |
| 关掉「城市的解药」（11 个点） | **90 → 79**，差 **11**；行 `is-off`；本地存 `"tasks:639135e0…": false` |
| 刷新页面（ignoreCache） | **79**，开关仍为关、行仍 `is-off`，存储仍 `false` |
| 总闸关（此时 79） | **79 → 0**；单条存储原样保留（仍只有那一条 `false`，其余条目未清空） |
| 总闸开 | **0 → 79**（上次关着的那条仍关着） |
| 再开回那条单开关 | **79 → 90**，行恢复 |
| 两条单开关关掉后：总闸关 + 刷新 | 仍是 **0** 点，`master="0"`；2 条 `is-off` 行原样（单条状态没被清） |
| 刷新后再开总闸 | **0 → 85**，两条 `is-off` 仍保留 |
| 真实鼠标点某行开关（a11y uid 点击，非脚本 `.click()`） | **86 → 85**；无任何行被误聚焦（`activeRows=0`） |

补充：切地图 `streets-of-tarkov → customs → streets-of-tarkov`，回来仍是 **85** 点、
两条 `is-off` 原样、存储值 `false` 不变 → 「切地图仍记得」。

## 3. B：四档筛选（实测）

为让「已完成 / 未完成」有区分，向 `eftmap.tasks.progress.v1`（tasks.js 写的同一个键）
注入 3 条 PvP 进度：`639135e0…=completed`（11 点）、`64f31769…=failed`（9 点）、
`674600a3…=active`（6 点）；随后刷新页面读取。

| 档位 | 列表行数 | 地图可见点 | 说明 |
| --- | --- | --- | --- |
| 全部 | 54 | **90** | 基线 |
| 未完成 | 53 | **79** | 排除已完成那条（90−11） |
| 已完成 | 1 | **11** | 只剩那条已完成 |
| 可并行推进 | 42 | **50** | 90 − 完成 11 − 失败 9 = 70，再按「前置已满足」剔除 20 点 |

- 顶部小字实时显示：`可并行推进：同图 · 未完成 · 前置已满足`。
- 判定函数 `taskFilterPass()` 口径（代码注释同步）：
  1. 目标地图 == 当前地图（面板只列当前地图的分组，天然满足）；
  2. 状态不是 `completed`、也不是 `failed`；
  3. 前置在当前模式下全部完成（条目间 AND；`logic=or` 的条目构成或组，任一完成即可；无前置算满足）。
  数据缺 `prerequisites` 字段时第 3 条无法判定，小字会追加「已退化成 同图 + 未完成」。
- 切换四档后再读 `eftmap.taskPointSwitches.v1`：**未发生变化**（仍是之前的值），
  证明筛选只影响显示、不修改每条开关状态。

## 4. C：右键选单（实测）

| 检查项 | 结果 |
| --- | --- |
| 任务行右键 | 自定义菜单出现；两项文案 `在地图上不显示` / `任务详细` |
| 点「在地图上不显示」 | 菜单收起；点数 **90 → 86**（该任务 4 个点）；行开关同步为关；存储写 `false` |
| 再右键点「在地图上显示」 | 点数 **86 → 90**，行开关同步开，菜单文案随状态切换 |
| 点「任务详细」 | 跳到 `#tasks:6391359b9444fb141f4e6ee6`，详情显示「一信之缘」 |
| 剧情行右键 | 「任务详细」为 `disabled`，`title` 写明「剧情地点没有任务系统中的详情页」；开关项可用 |
| 收起行为 | 点别处 / 滚动 / 缩放 / `Esc` 均收起（capture 阶段监听） |

## 5. D：详情跳转（实测）

| 检查项 | 结果 |
| --- | --- |
| 跳转方式 | URL hash：`#tasks:<taskId>`（可复制、可分享，新增一条历史记录） |
| 落点 | `#tk-detail` 显示对应任务；`detailScrollTop = 0`（`scrollDetailTop()` 打开后滚到顶部） |
| 后退 | 浏览器后退回 `http://127.0.0.1:8787/`；点数仍 **90**、54 行、筛选 `all`、总闸开、开关状态不变 |
| 找不到任务 | `#tasks:no-such-task-xyz` → 详情区提示「未找到任务 no-such-task-xyz（当前模式 PvP（常规） 下不存在）。可能属于另一个模式：请用右上角切换模式后重试，或检查链接里的任务 ID。」不静默 |

## 6. 模式独立（实测）

| 模式 | 状态 |
| --- | --- |
| PvP | 85 点；关着 `tasks:6391359b…` 与 `stories:story-69052e…`（存储 `regular` 两条 `false`） |
| 切到 PvE | 90 点；无 `is-off` 行（`pve` 桶为空，默认全开）；`regular` 桶原样保留 |
| PvE 关掉「城市的解药」 | 90 → 79（差 11）；存储新增 `pve: {"tasks:639135e0…": false}` |
| 切回 PvP | 85 点；两条 `is-off` 原样；`pve` 那条仍为 `false`（互不影响） |

模式切换入口仍只有右上角一个（`.gm-btn`），面板内没有新增模式控件。

## 7. 约束对照

| 约束 | 落实情况 |
| --- | --- |
| 只存本地、不加后端接口 | 三个键：`eftmap.taskPointSwitches.v1`（按模式）、`eftmap.taskPointsMaster.v1`、`eftmap.taskPointFilter.v1` |
| 总闸语义 | 只参与「是否画」判定，绝不清空单条开关；重开恢复各自上次状态 |
| 重绘开销 | `renderOverlay()` 建点时把节点登记进 `state.taskGroupNodes`；开关 / 筛选 / 聚焦 / 总闸只改 `node.style.display`，不整层重建 |
| 不引第三方库 | 原生 DOM + SVG |
| XP 视觉体系 | 只新增控件样式，沿用 `--xp-*` 变量；开关与菜单无新配色体系 |
| 打包 / commit | 本轮不做 |

## 8. 已知边界（不属缺陷，说明口径）

- 点一行任务主体（`.task-main`）仍是旧的「只看这一组」聚焦语义；此时其他组的点会被隐藏，
  与该行开关无关。开关点击已 `stopPropagation`，不会误触聚焦（2.1 已实测）。
- 四档筛选是全局显示偏好（不按模式分别记忆）；不同模式下按同一档位重新判定，结果随数据变化。
- 剧情地点没有任务系统详情页，因此「任务详细」对其禁用而不是跳转。
