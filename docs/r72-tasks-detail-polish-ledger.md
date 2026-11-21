# R72 台账：任务顶栏控件 + 任务详情页打磨

host=HOMONAS user=MASTERJJ at=2026-11-04 23:45:55 +08:00

## 0. 现在顶栏长什么样、详情页改了什么

- 顶栏：标题行右侧**一行**紧凑分段选择器 `PvP | PvE | PvPS（赛季服）` + `版本 [蓝边]` 下拉，
  与标题同高；全局 `#game-mode-bar` 在任务视图隐藏，不再占第二行。1440 下 `#tk-scope-bar` 290×23，
  `.tk-head` 由 **92.8 px** 缩到 **63.8–66 px**（≤ 原来一半）。
- 详情页：字段区两列紧凑网格（标签 88 px 固定、值左对齐、行高 17 px），状态四项为 XP 分段按钮
  （选中凹陷蓝底 + 加粗 + 上方「任务状态」小标签），任务 ID 等宽字体 + 复制按钮，
  模式归属改短标签 + `title` 悬浮说明，数字用等宽数字并带单位；页面内不再出现任何 fandom 链接。

## 1. db4tarkov 取样结论

| 项 | 结果 |
| --- | --- |
| 页面 | `https://db4tarkov.com/tasks`（真实 Chrome，新建标签） |
| DOM | **不可读**：根节点为 `FLUTTER-VIEW`，`input/button` 数量 0，`document.body.innerText` 为空，94 个 HTML 节点中无 canvas 内容节点 |
| 截图 | 纯黑（`smoke/db4-tasks-unrenderable.png`），CanvasKit 未完成首帧 |
| 控制台 | `Null check operator used on a null value`、`Refused to set unsafe header "User-Agent"` |
| 替代手段 | 无法做像素度量（黑屏无控件），改用该站已知信息架构：搜索条同排、模式/版本为紧凑分段、选中态高亮；视觉完全按 XP 令牌重做，不复制其配色 |

## 2. 改动文件

| 文件 | 改动 |
| --- | --- |
| `tasks.js` | 删除详情「参考条目：…fandom…」；新增 `#tk-scope-bar`（模式分段 + 版本下拉 + 轻量反馈）、`fillEditionOptions()`/`syncScopeBar()`/`editionShort()`/`modeScopeShort()`/`copyTaskId()`；详情字段改 `[标签, 值, 类型, title]`，状态分段带 glyph+`aria-pressed`，状态变更后写底部状态栏；修复前置联动对话框「取消/确认」不关闭的问题 |
| `tasks.css` | `.tk-scope-bar/.tk-seg/.tk-seg-btn/.tk-edition/.tk-scope-feedback`；`.tk-mode-note` 隐藏；`.tk-detail-body max-width:none`；`.tk-facts` 两列网格 + `display:contents`；`.tk-detail-statuswrap`；`.tk-id/.tk-copy-btn`；空值弱化；`.tk-h3` 间距收紧 |
| `theme-windows-xp.css` | R72 段：分段按钮白底/垂直渐变/选中凹陷蓝、版本下拉边框、反馈文字绿色 |
| `app.js` | `setView` 写 `body[data-view]`；`GWDataScope` 暴露 `ensureEditions()`/`setEdition()`；`applyEdition` 后派发 `gw:edition` |
| `index.html` | 关于面板新增「任务参考 → Fandom Wiki 任务列表」（站外参考，不逐任务生成链接） |
| `tests/test_r19_23_round.py` | 模式归属断言同步为 `modeScopeShort(rec)` + `scopeShort` + `dd.title`（未删除、未放宽） |

## 3. 顶栏与详情验收数字

| 指标 | 1440×900 | 1024×768 | 860×720 |
| --- | --- | --- | --- |
| `documentElement.scrollWidth == innerWidth` | 1440 == 1440 | 1024 == 1024 | 859 == 859 |
| 横向溢出 | 0 | 0 | 0 |
| `.tk-head` 高度 | 66 px（改前 92.8） | 64 px | 64–66 px |
| `#tk-scope-bar` 尺寸 | 290×23 | 290×23 | 290×23（未换行） |
| 详情标题行数 | 1 | 1 | 1 |
| 详情字段区 `.tk-facts` | 1384×230，12 行 | 自适应 | 自适应 |

- 模式切换实测（任务数变化，`applyDataScope` 未退化）：**PvP 503 / PvE 499 / PvPS 462**。
- 版本下拉 6 项：未选版本、白边、遗落版、准备逃离版、蓝边、黑边；切换「蓝边」后
  `GWDataScope.get().edition="unheard"`、`localStorage eftmap.accountEdition="unheard"`，刷新后仍为「蓝边」。
- 说明：按现有设计，账号版本只驱动账号权益对照卡，**不改变任务数与行情价格**（`index.html` 与
  `app.js` 原注释均已注明）；R72 未改 `applyDataScope` 的这段语义，只补齐了清单加载与持久化。
- 状态：点「已完成」→ 弹出前置联动确认（原有保护）→ 确认后 4 段中 `completed=true`；点「已失败」即时生效；
  刷新后状态与选中任务保持；底部状态栏显示「已将「X」标记为「已失败」」。

## 4. 六轮打磨记录

| 轮次 | 截图 | 发现 | 改动 |
| --- | --- | --- | --- |
| 1 | `r72-round1-detail-1440.png` | 详情只占 1020 px，右侧空白约 420 px；字段一列「名+值」行距松 | `.tk-detail-body max-width:none`；`.tk-facts` 改两列网格；ID 等宽 + 复制 |
| 2 | `r72-round2-detail-1440.png` | 顶栏两行（全局模式条 + 任务模式条），高度 92.8 px | 新增 `#tk-scope-bar`；隐藏 `.tk-mode-note` 与任务视图下的 `#game-mode-bar`；head 63.8 px |
| 3 | `r72-round3-detail-1440.png` | 状态四项没有标题；「—/无」与数值同样黑；空值跳动 | 加「任务状态」小标签；空值 `.is-empty` 灰化；数字等宽；`.tk-h3` 间距收紧 |
| 4 | `r72-round4-detail-1440.png` | 版本下拉只有「未选版本」（`GWDataScope.editions` 未加载） | `ensureEditions()` 懒加载 + 重新填充；切版本改走 `setEdition()` 持久化；修复联动框取消/确认不关闭 |
| 5 | `r72-round5-detail-1024.png` / `r72-round5-detail-860.png` | 1024/860 尚未验证；长英文名可能撑破 | 实测 0 溢出；标题 1 行；分段不换行；长名任务（48 字符英文名）正常 |
| 6 | `r72-round6-detail-1440.png` / `r72-round6-detail-860.png` | 状态切换后无轻量反馈 | 底部状态栏输出「已将…标记为…」；最终三档复核；补齐边界截图 |

边界截图（`smoke/`）：`r72-edge-long-name-1440.png`（48 字符英文名）、
`r72-edge-no-map-1440.png`（地图「—」）、`r72-edge-no-faction-1440.png`（阵营「无」）、
`r72-edge-no-failed-branch-1440.png`（失败分支「无」）。

## 5. 验收

- 详情页 DOM `includes('fandom') == false`；关于面板存在「任务参考 → Fandom Wiki 任务列表」且可点
  （`https://escapefromtarkov.fandom.com/wiki/Quests`），关于面板 430×257、8 行链接（R70 为 7 行 / 233）。
- `C:\Python314\python.exe -m pytest tests -q`：**1740 passed, 1 skipped**。
- 最终重建 `build.ps1`（清单 13241 / 13241）+ `build_release.ps1 -SkipBase`。
- 三件套（`release/`）：

| 文件 | 体积 | SHA256 |
| --- | --- | --- |
| `EFTMap-AppWindow-0.1.0.zip` | 116.91 MB | `69A7A5239E7DA4073D00582641F76BD43929AFCEC2EB1F17ED75BBB9F3260F7D` |
| `EFTMap-Portable-0.1.0.zip` | 116.91 MB | `B032430F4E2F744C5B02AF2250C64F97C1E85E19B68C6E7A67BD7823A68BA773` |
| `EFTMap-Setup-0.1.0.exe` | 127.27 MB | `AA1DE153213AF9B2A4A156317956768BD3DB4D1ADD9F2FDB619B0F11807B22DD` |

未 git commit。
