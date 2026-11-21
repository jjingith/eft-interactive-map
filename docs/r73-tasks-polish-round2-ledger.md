# R73 台账 · 任务详情页二轮打磨 + 顶栏手感 + 收尾交付

host=HOMONAS user=MASTERJJ at=2026-11-05 00:58 +08:00

> 本轮从 R72 验收后继续推进，目标时间点：2026-11-05 10:00（用户约定十点来测）。
> 全程未 git commit。

---

## 0. 十点该看哪几处（结论先行）

1. **任务详情页**：`#tasks` → 点任意任务 → 看「字段区」与右/下方的三张概览卡（前置 / 奖励 / 后续）。
   六轮打磨后：12 行字段行高统一 18px、`—/无` 统一 `#6b6b6b`（对比度约 5.6:1）、数值列等宽（实测 1111 与 9999 宽度同为 28.38px）、地图名只留中文（英文原名在 tooltip）。
2. **状态四态与键盘**：详情页状态组 Tab 只落 1 次（roving tabindex），方向键切换；860 档方向键切换触发「前置未完成」弹窗不出屏。
3. **「模式归属」**：由 `title` 改成**点击展开的行内说明**，触屏/无 hover 也能读；点空白处或 Esc 收起，只浮在该行下方，不撑高字段块（行高恒 18px）。
4. **顶栏模式切换**：PvP / PvE / PvPS 切换无白屏（`zeroRowFrames=0`），切换后列表回到顶部（`scrollTop 25074 → 0`）。
5. **交付物**：`release/` 三件套 + `dist/` 已按本轮源码重建，dist 内四个关键文件与源码 SHA256 完全一致（见 §5）。

---

## 1. 任务详情页：六轮发现与改动

### Round 1 —— 字段结构 + 概览卡（发现“右侧过大留白”）
- 发现：详情满宽后，字段区只占左半边，右下半屏空白；单张概览卡横排只占 1/3 宽，右侧 2/3 空着。
- 改动：
  - 字段改为 `.tk-facts` 两列网格（键列固定、值列自适应）。
  - 新增 `.tk-detail-top`：宽屏 `grid-template-columns: minmax(0,1fr) 236px`，左侧字段、右侧竖排三卡；≤1100px 自动变单列、三卡一行；≤620px 再竖排。
  - 概览卡只在**有数据**时渲染（前置 / 奖励 / 后续各一张），无数据不造假卡。
- 复检：864/1440 两档无横向溢出。

### Round 2 —— 字段排版细节（行高抖动 / 中英双写 / 空值灰度）
- 发现：`dt` 与 `dd` 行高 19/20 交替，眼睛能看出“行距不齐”；地图列出现 `Ground Zero 教程`、`实验室 (Dark)` 这类中英混写。
- 改动：
  - `dt/dd line-height: 18px`，`.tk-id` 11px/14px Consolas，`.tk-copy-btn` 10px/15px，最终 12 行全部 18px。
  - 新增 `MAP_LABELS`：`中心区（教程）`、`实验室（夜间）`；正文只显示中文，原始英文名进 `dd.title`。
  - 空值统一 `is-empty` → `#6b6b6b`（比正文黑明显淡，但不是灰到看不清）。
  - `.is-num` 加 `font-variant-numeric: tabular-nums`。
- 复检：`dtTop === ddTop`（12/12 行基线对齐）。

### Round 3 —— 「模式归属」从 title 改为点击展开
- 发现：说明只挂在 `title` 上，触屏 / 无 hover 环境读不到。
- 改动：`.tk-scope-toggle` 按钮 + `.tk-fact-note` 绝对定位说明（白底 `#ffffe1`、`#7f9db9` 边框、`max-width: min(360px, 100vw - 48px)`）；`aria-expanded` 同步，文案箭头 `▸/▾` 切换。
- 复检：展开前后该行行高 18px、字段块高度 258px 不变；说明右缘 434 < 859，不出屏。

### Round 4 —— 860 联动弹窗 + 状态按钮四态
- 发现：状态按钮选中/hover 不够可辨；点击「进行中」若前置未完成会弹联动弹窗，需确认 860 档不超屏。
- 改动：选中蓝底 + 白字，`.is-on:hover` 保持蓝底（不再变浅黄），未选中 hover 才变浅黄，`:active` 内阴影；`:focus-visible` 内缩点线框。
- 复检：860 弹窗 `box [12,256,836,208]`，右缘 848 / 下缘 464 均在 859×720 内，`overflowX=0`；取消后状态仍为「未开始」。

### Round 5 —— 行内说明的收起行为 + 键盘触发前置弹窗（本轮新发现）
- **发现（真问题）**：行内说明用绝对定位浮层，点页面别处**不会收起**，会一直盖住下面「所属商人」「地图」两行。
- 改动（`tasks.js` / `tasks.css`）：
  - 新增 `closeScopeNotes()`；`document` 级 click 收口（点 `.tk-fact-scope` 内部不触发）。
  - 触发按钮自身支持 `Esc` 收起（`preventDefault + stopPropagation`），焦点留在按钮上。
  - 打开时先收其他已展开的说明；按钮加 `data-scope-label` 保证收起后文案能还原，并补 `aria-label`。
  - 说明阴影从 `1px 1px 0` 改为 `2px 2px 3px rgba(0,0,0,.18)`，浮层与下方文字层次可辨。
- 实测：
  - 点击说明 → `aria-expanded=true`、行高 18px、字段块 258px 不变。
  - 点标题空白 → 自动收起（`open:false, exp:false`）。
  - 键盘：焦点在按钮 → `Esc` → `open:false, exp:false, label "全模式 ▸"`，焦点仍是 `tk-scope-toggle`。
  - 键盘方向键：焦点在「未开始」→ `ArrowRight` → 触发前置联动弹窗，1440 `box [440,336,1000,564]`；切到 860 后 `[12,256,848,464]` 内屏、`overflowX=0`；`Esc` 取消后 `aria-checked` 仍为「未开始」、「进行中」回到 `tabIndex=-1`，焦点回到「未开始」。
- 顺带核实：状态按钮**没有 disabled 态**（四个状态永远可选，冲突由联动弹窗处理），所以本轮不新增 `:disabled` 样式，避免写死代码。

### Round 6 —— 换任务后详情滚动位置（本轮新发现）
- **发现（真问题）**：读到详情底部后换任务，`#tk-detail` 保留旧 `scrollTop`（实测 1194 → 864），新任务从半页开始，像“跳到了中间”。
- 改动：`renderDetail()` 末尾 `host.scrollTop = 0`（`innerHTML` 同步重建时浏览器不会自动归零，必须显式写）。
- 实测：`before 1194 → after 0 → 再开另一个任务仍为 0`。
- 回归：860 四边界任务详情高度均 571px、`overflowX=0`。

### 四种边界（每轮重拍，不复用旧文件）

| 边界 | 任务 | 结果 |
|---|---|---|
| 无失败分支 | 绿色通道 | 「失败分支 = 无」灰化 `rgb(107,107,107)`，行高 18 |
| 超长任务名 | 生存者之路 - Zhivchik（16 字） | 标题单行 25px，无换行/溢出 |
| 无地图 | 半满半空 | 「地图 = —」灰化，值列占满仍 `overflowX=0` |
| 无阵营要求 | 大客户 | 「阵营要求 = 无」灰化 + `is-empty` |

> Round 1–3 的边界图按 1440 拍，Round 4 混拍 1024/860，Round 5–6 按 860 拍。
> Round 6 四张与 Round 5 字节完全相同，是因为本轮唯一改动（换任务归零滚动）不改变静态画面，**文件是重新截的**，不是复制旧图。

---

## 2. 顶栏真实手感

### 2.1 模式切换：无白屏 + 回顶
采样方式：切换瞬间起 `requestAnimationFrame` 逐帧记录 `.db4-row` 数量与 `.tk-pane-list` opacity。

| 切换 | 帧数 | 0 行帧 | 最低 opacity | 行数 | 回顶 |
|---|---|---|---|---|---|
| PvP（从 PvPS，未缓存） | 155 | 0 | 0.59 | 503 | 25074 → 0 |
| PvE | — | 0 | 0.55 | 499 | 27264 → 0 |
| PvPS（已缓存） | — | 0 | 1.00 | 462 | 27011 → 0 |

- 过渡实现：`is-mode-loading` 只把 `.tk-pane-list/.tk-pane-tree` 降到 `opacity:.55` + `pointer-events:none`（0.12s 线性），不隐藏列表，所以任何一帧都有行。
- **为什么回顶**：模式切换等于换了一份任务集，旧滚动位置对应的行在新集合里没有意义；保留会导致“看起来停在 1/3 处但内容已不同”。因此 `setMode` 同时把 `paneList`、真正的滚动容器 `.db4-scroll`、`paneTree` 三段 `scrollTop` 归零——只重置外层容器是无效的（外层不滚）。

### 2.2 版本下拉键盘
元素：原生 `<select id="tk-edition">`（只监听 `change`，无自定义 keydown，不吞键）。

| 操作 | 结果 |
|---|---|
| `ArrowDown` | 白边 → 遗落版，`localStorage.eftmap.accountEdition = left-behind` |
| `Enter` | 值保持遗落版，无弹窗、视图/模式不变 |
| `Esc` | 不改变值、不触发页面级动作（`GWDataScope.get().edition` 与 select 同步） |
| 再 `ArrowDown` | 遗落版 → 准备逃离版，持久化同步 |

### 2.3 1024 / 860 与搜索条不重叠
| 档位 | 版本下拉 | 可见搜索框 | 重叠 | head 高度 |
|---|---|---|---|---|
| 1024 | `[923,42,1011,62]` | `#tk-list-search [12,104,955,128]` | false | 64 |
| 860 | `[758,67,846,87]` | `#tk-list-search [12,129,790,153]` | false | 64 |

两个档位版本下拉右缘都在视口内（860 右缘 846 < 859）；搜索条在 head 下方独立一行，纵向不交叠。

---

## 3. 验收数字（最终重建后，直接跑 dist 产物）

服务：`tools/serve.py --root dist\EFTMap\_internal`（8794），等价于运行期文件，不是源码目录。

| 档位 | 横向溢出 | 可横向滚动 | 请求数 | 外部请求 | 非 200/304 | console error | PvP / PvE / PvPS |
|---|---|---|---|---|---|---|---|
| 1440×900 | 0 | 0 | 242 | 0 | 0 | 0 | 503 / 499 / 462 |
| 1024×768 | 0 | 0 | 242 | 0 | 0 | 0 | 503 / 499 / 462 |
| 859×720 | 0 | 0 | 242 | 0 | 0 | 0 | 503 / 499 / 462 |

- 溢出判定同时看 `documentElement.scrollWidth - clientWidth` 与 `scrollingElement.scrollLeft` 上限；1024 下 `body.scrollWidth` 偶发 1025 是 0.667 缩放取整（body 宽 1024.5），`html` 与滚动上限均为 0，不是真溢出。
- 源码站（8789）同口径复测：218 请求、外部 0、非 200/304 0、console error 0、三档 0 溢出。

---

## 4. 构建与哈希

- `build/build.ps1`：清单预检 **13241 / 13241**（缺失 0、未登记 0），产物体积 **155.1 MB**，底图 SVG 13 张。
- `build/build_release.ps1 -SkipBase`：三件套（壳文件已并入 `dist\EFTMap`）。

| 产物 | 字节 | SHA256 |
|---|---|---|
| `EFTMap-Portable-0.1.0.zip` | 122,596,361 | `4d5d82b6b2f25ee2c880d8ddf588f50664349519de0a1a3f1d1c0927df527fa5` |
| `EFTMap-AppWindow-0.1.0.zip` | 122,596,500 | `56034343c07929b08f084b9b1f19eecf7c751ea53a0be93db7764c9e1953d521` |
| `EFTMap-Setup-0.1.0.exe` | 133,456,341 | `ec78e6b50ac120b4f05caf005fae588b98e6b45b03e982589a968fd93b415314` |

dist 内运行期文件与源码逐字节一致：

| 文件 | SHA256（源码 = `dist\EFTMap\_internal\<同名文件>`） |
|---|---|
| `tasks.js` | `4fb34ddf1d56af6b1997feb48d4755780b24777aa300c2d7ed1a7b7374b4e341` |
| `tasks.css` | `6268f7c7366918e1f8b3ccccef69ad39b013e8f9299112c353bf51f64293d833` |
| `app.js` | `d8152d22dbed5c28211e67ebbf0bf00f50cc83cf66da9f6ef3911c7178d86e62` |
| `index.html` | `ef57cbf467f69f5d901ce42ed4bab13e133beb754d5092fb00cffb0eef1cd456` |

---

## 5. 测试

- `python -m pytest tests -q` → **1740 passed, 1 skipped（99.20s）**。
- 本轮同步修改了 `tests/test_r19_25_round.py::test_C_no_chinese_trader_names_in_task_ui`：详情副标题去掉重复商人名后 `traderEn(` 调用点 10 → 9，下限断言同步改为 `>= 9`（断言意图不变：禁止把 data 里的中文 `nameZh` 直接显示）。
- `test_r19_23_round.py` 已含「模式归属」新结构断言（`modeScopeShort` / `tk-fact-scope` / `tk-scope-toggle` / `tk-fact-note`，且不再断言 `dd.title`）。

---

## 6. 未解决 / 如实保留的限制

1. **db4tarkov 无法取样**：线上页需要登录/反爬，本轮没有稳定截图可比对；“照 db4 信息架构”只做到结构与密度层面（状态分段、字段两列、概览卡），**未做像素级对齐**。
2. **原生下拉的 Esc 取消无法在页面内观测**：`<select>` 是浏览器原生控件，弹层在 OS 层，Puppeteer 读不到开合状态；只能确认 Esc 不改变值、不触发页面动作。方向键/回车路径已实测。
3. **状态按钮无 disabled 态**：四个状态恒可选（前置冲突走联动弹窗），因此没有“disabled 与选中态如何区分”的实物；本轮未为了凑样式写死 `:disabled` 规则。
4. **商人名只有英文一套**：上游 `traderZh` 字段与英文名同值，且既有测试明确禁止任务 UI 出现中文商人名；本轮只删掉副标题里的重复商人，正文不再出现两遍。
5. **Round 6 四张边界图与 Round 5 字节相同**：本轮唯一改动是滚动归零，静态画面零变化；文件是新截的，但内容一致。
6. **性能数字是本地口径**：PvP 首次切换 558ms、PvE 1247ms、PvPS 缓存 474ms（8789/8794 本机），不含杀软扫描与冷盘开销。

---

## 7. 截图清单（`docs/r73-tasks-polish/smoke/`）

- Round 1–3：`r73-round{1,2,3}-detail-1440.png` + 各自 `edge-{nofail,longname,nomap,nofaction}-1440.png`
- Round 4：`r73-round4-detail-{1440,1024,860}.png` + `r73-round4-edge-*-1440.png`
- Round 5：`r73-round5-detail-860.png`、`r73-round5-scope-open-860.png`、`r73-round5-scope-note-860.png`、`r73-round5-dialog-860.png`、`r73-round5-dialog-keyboard-860.png`、`r73-round5-b{1..4}-*-860.png`
- Round 6：`r73-round6-detail-{1440,1024,860}.png`、`r73-round6-topbar-860.png`、`r73-round6-b{1..4}-*-860.png`
- 顶栏：`r73-topbar-1024.png`、`r73-topbar-860.png`
- dist 产物实测：`r73-dist-detail-860.png`
