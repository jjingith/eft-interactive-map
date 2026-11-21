# R49 任务页视觉保真度打磨留痕

host=HOMONAS user=MASTERJJ at=2026-11-04 06:46:34

## 结论

- 取样对照 **15 项**（结构 6 项、尺寸 3 项、颜色 4 项、状态/容器 2 项）。
- 修为「一眼可见」差异 **9 项**：行/页底色与分隔线、任务字号、目标文案色、经验列形态、完成链接颜色与对齐、物品图标尺寸与数量角标、右栏密度与底色、商人列暖橙通栏、860 档横向溢出。
- 刻意不修 **6 项**，原因见下表与「刻意不修」章节。
- 回归：**1708 passed / 1 skipped / 0 failed**（与改前基线一致）。
- 只改了 `tasks.css`、`tasks.js`；未改 `app.js`、`index.html`、`style.css`、`tools/*.py`、`build/*.ps1`；未重建 dist / release；未 git 提交。

## 参考站取样与限制（实际执行记录）

| 项目 | 结果 |
| --- | --- |
| 网络 | 代理 `http://127.0.0.1:7896` 可用；`GET https://db4tarkov.com/tasks` 实取 HTTP 200，HTML 58,705 字符 |
| 浏览器 | Chrome DevTools 打开 `https://db4tarkov.com/tasks`，`document.title=Database for Tarkov`，`flt-glass-pane=true`、`body.innerText.length=0`、可访问 `<canvas>` 数量 0 |
| 渲染 | 1440×900 与 1024×768 两档新截图均为整屏空白；控制台固定报错 `Null check operator used on a null value at main.dart.js:242533`（Flutter CanvasKit 启动失败，非网络问题） |
| 替代证据 | 使用仓库内既有 **真实截图** `docs/r41-tasks-redesign/shots/ref-db4-1024.png`（实际 1600×1000）与 1:1 裁剪；本轮已复制到 `docs/r49-task-fidelity/ref/` |
| 度量方式 | 无 DOM 可读，全部用 PIL 对真实截图做像素取样（背景色取中位数、边界取列/行扫描） |
| 未能取证 | hover 态、选中态精确色值、空态文案位置；参考站本轮无法进入交互态，相关项按现有实现保留并标注 |

> 参考站是 Flutter CanvasKit，DOM 里没有可抄的结构与样式；上述取值来自真实像素，不是推测值，也没有复制其美术资源。

## 差异清单

单位：参考截图 1600×1000 像素；本项目截图 1440×900 / 1024×768 / 860×900，DPR=1。

| # | 区域 | 参考取样 | 改前 | 改后 | 处理 |
| --- | --- | --- | --- | --- | --- |
| 1 | 页面底色 / 任务行底 / 分隔线 | `#121212` / `#1a1a1a` / `#171717` | `#0e0e0e` / `#101010` / `#1e1e1e`（行比页面还暗，分隔线反而更亮） | `#121212` / `#1a1a1a` / `#171717` | 已修 |
| 2 | 任务名称 | 约 12px / 600 / `#ededed` | 12.5px / 600 | 12px / 600 | 已修 |
| 3 | 目标文案 | 中灰，取样 `#999` 左右 | `#cfcfcf`（偏亮，层级压过任务名） | `#a3a3a3` | 已修 |
| 4 | 经验列 | 单行深色小框，约 34×22，垂直居中，内容 `+N` | 两行：蓝色 `EXP` 标签 + 数值，贴顶 | 单行框 `#232323` / 边框 `#343434`，高 22、居中 | 已修 |
| 5 | 完成链接 | 蓝色 `#007aff`，约 56px，垂直居中 | 灰色 `#9a9a9a`、70px、贴顶 | `#3d9bff`、62px、垂直居中 | 已修 |
| 6 | 物品图标 | 约 35px 方图，数量压在右下角 | 26px，无数量角标 | 32px（≤980 档 28px）+ 右下 `×N` 角标 | 已修 |
| 7 | 右栏 | 底 `#121212`，按钮 `#1e1e1e`、高约 28，分组标题约 10.5px | 底 `#111`，按钮 `#1b1b1b`、高 30，标题 12px | 底 `#121212`，按钮 `#1e1e1e`、高 28，标题 10.5px | 已修 |
| 8 | 商人列（gutter） | 整列亮橙通栏，取样 `#d36501` | 纯黑 `#101010`，头像下方整段空黑 | 暖橙渐变 `#8c4403 → #40220a → #1d130a`，整列连续 | 近似修（美术不可照搬） |
| 9 | 行高 / 行距 | 约 62px（1600 参考） | 59px | 59px | 刻意不动 |
| 10 | 头像条 | 约 32×32，条高约 43，间距 2 | 32×32，条高 43，间距 2 | 不变 | 已对齐，无需改 |
| 11 | 搜索框 | 输入框高约 24，底约 `#1b1b1b` | 24，`#1b1b1b` | 不变 | 已对齐，无需改 |
| 12 | 商人列宽 | 参考约 90–103（1600）；前轮实测口径 56–58 | 58 | 58（≤980 档 54） | 沿用前轮口径 |
| 13 | 空态 | 参考站交互态无法取证 | 列表区顶部居中，块高 97 | 不变（本轮截图复核位置正常） | 保留 |
| 14 | hover | 无法取证 | `#191919` | `#202020`（与新行底 `#1a1a1a` 配套） | 保守调整 |
| 15 | 860 档容器 | 参考站无此应用外壳 | 整个任务面板被行内不可换行文案撑到 **968px**，右栏被挤出 860 视口 | `bodyW=860`、横向溢出元素 0 个，右栏 `x=690 w=170` 可见 | 已修 |

## 改了哪些选择器

`tasks.css`

- 变量：`.db4 { --db4-bg }` → `#121212`
- 容器/头部：`.tk-shell.db4 .tk-head`、`.tk-shell.db4 .tk-statusbar`、`.db4-bar`
- 行与分组：`.db4-group`、`.db4-row`、`.db4-row:hover`、`.db4-row.is-completed`、`.db4-row.is-failed`
- 商人列：`.db4-gutter`
- 文本：`.db4-name`、`.db4-obj-desc`
- 物品：`.db4-items`、`.db4-item-cell`（新）、`.db4-item`、`.db4-item-n`（新）、`.db4-item-more`
- 经验/完成：`.db4-exp`、`.db4-exp-chip`（隐藏）、`.db4-exp-val`、`.db4-complete`
- 右栏：`.db4-rail`、`.db4-rail-grp`、`.db4-rail-title`、`.db4-rail-btn`
- `@media (max-width: 980px)`：`.tk-titlebar`（允许换行）、`.tk-modebar`、`.view-pane` / `#task-view` / `.tk-body` / `.tk-pane`（`min-width:0`）、`.db4-rail`、`.db4-gutter`、`.db4-items`、`.db4-item-cell`、`.db4-item-more`、`.db4-exp`、`.db4-complete`、`.db4-gutter .db4-face-img`

`tasks.js`

- 物品渲染包一层 `span.db4-item-cell`，图片保留 `.db4-item`，`count > 1` 时追加 `span.db4-item-n`（右下 `×N`）。
- 仍为 ES5（`var` / `function`），未改业务逻辑与数据口径。

## 响应式自检（改后实测）

| 档位 | body 宽 / 视口 | 横向溢出元素 | 右栏 | 账号抽屉（5 卡） |
| --- | --- | --- | --- | --- |
| 1440×900 | 1440 / 1440 | 0 | `x=1244 w=196` | `x=172 y=32 w=500 h=648`，底 680 < 900 |
| 1024×768 | 1024 / 1024 | 0 | 196 | `x=249 y=31 w=460 h=553`，底 583 < 768 |
| 860×900 | 860 / 860 | 0 | `x=690 w=170` | `x=8 y=69 w=844 h=822`，底 891 < 900（保持 `position:fixed; left:8px; right:8px; top:68px`） |

860 档标题栏由两行降为一行（高 23px），模式选择器在 `x=4 y=32 w=317`，未遮挡筛选栏。空态在 860 档块宽 690，未盖住右栏。

## 截图路径

参考（真实截图，已复制，来源为 r41 归档）：

- `docs/r49-task-fidelity/ref/ref-db4-1600x1000.png`
- `docs/r49-task-fidelity/ref/crop-ref-top.png`（头像条与搜索框 1:1）
- `docs/r49-task-fidelity/ref/crop-ref-rows.png`（任务行 1:1）
- `docs/r49-task-fidelity/ref/crop-ref-rail.png`（右栏 1:1）
- `docs/r49-task-fidelity/ref/crop-ref-gutter.png`（商人列 1:1）

本项目改前 / 改后：

| 场景 | 改前 | 改后 |
| --- | --- | --- |
| 1440 列表 | `shots/before-1440-list.png` | `shots/after-1440-list.png` |
| 1440 选中商人 | `shots/before-1440-trader.png` | `shots/after-1440-trader.png` |
| 1024 列表 | `shots/before-1024-list.png` | `shots/after-1024-list.png` |
| 1024 选中商人 | `shots/before-1024-trader.png` | `shots/after-1024-trader.png` |
| 860 列表 | `shots/before-860-list.png` | `shots/after-860-list.png` |
| 860 选中商人 | — | `shots/after-860-trader.png` |
| 账号抽屉 | — | `shots/after-1440-account.png` / `after-1024-account.png` / `after-860-account.png` |
| 空态 | — | `shots/after-1440-empty.png` / `after-1024-empty.png` / `after-860-empty.png` |

改前基线另有一张误命名的 `before-860-account.png`（实际未打开抽屉），已删除，避免误读。

## 刻意不修（附原因）

1. **搜索条与头像条合并成同一行**：参考站把 16 个头像、搜索框、LV/收藏/账号统计压在一行。本项目没有对应的账号统计簇，合并后中段会出现大块空白，且会破坏已固化的「搜索条 + 头像条」四区契约；保留两行。
2. **商人列亮橙徽章与任务类型小图标**：`#d36501` 通栏由 db4 的商人徽章美术构成，属于受版权保护的上游美术，不能照搬；只用暖橙渐变还原「整列有底色」的观感。
3. **行内等级 chip（`LL1`）位置**：参考站把它放在任务名前；本项目等级来自任务数据映射且与中英双语名并排，移动会改变 i18n 取词与信息层级，收益低于风险。
4. **右栏 Display 三按钮（Show first Objective / Show all Objectives / Show thumbnail）**：db4 特有的显示模式组合，本项目用单开关等价覆盖，不新增交互。
5. **顶部站点导航与账号统计（MARKET/SEASON/QUEST、Lv 65、收藏、统计）**：属于 db4 站点外壳，不属于交互地图任务页。
6. **hover / 选中态精确色值**：参考站本轮 CanvasKit 启动崩溃，无法进入交互态取证；不凭压缩图猜色，保留可用且与新行底协调的 `#202020` 与白底选中。

## 回归

```text
python -m pytest tests -q
1708 passed, 1 skipped
```

与改前基线 `1708 passed / 1 skipped / 0 failed` 持平，无新增失败。
