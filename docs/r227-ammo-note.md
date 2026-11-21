# R227 弹药侧栏底部说明不再显示

日期：2026-11-10 16:45–17:00
入口：`app.js` 的 `renderAmmo()`（`#am-note`）、`style.css`

## 1. 用户要求

用户贴出弹药界面左侧（实际布局在右侧）筛选栏底部的那段文字：

```
共 200 件弹药 / 31 种口径。价格口径 lastPrice，来源 实时不可用，已回退快照（PvP）；
C1–C6 为对 1–6 级护甲的穿透概率（公开公式计算）。弹道曲线为本地 G1 阻力仿真，非线上行情。
```

原话：**「弹药界面的这个也不要显示 隐藏掉」**。

## 2. 这段话由哪四部分组成

| 片段 | 数据来源 | 说明 |
|---|---|---|
| `共 200 件弹药 / 31 种口径` | `data.rows.length` / `data.calibers.length` | 与工具栏 `#am-count`（`200 / 200 件`）重复 |
| `价格口径 lastPrice` | `amPriceLabel()` | 侧栏顶部三段按钮已经高亮当前档位 |
| `来源 实时不可用，已回退快照（PvP）` | `priceSourceInfo().short` | 工具栏 `#am-hint` 已在显示「价格来源：…」 |
| `C1–C6 为…穿透概率` / `弹道曲线为本地 G1 阻力仿真` | 固定文案 | 口径说明，页面上没有对应的“可能被误解”的展示需要它兜底 |

四段全部是“解释”，没有一段是当前状态才成立的提示——所以整段去掉，不是压缩。

## 3. 改法

| 位置 | 改动 |
|---|---|
| `app.js` `renderAmmo()` | 删掉整段 `innerHTML` 拼接；`srcInfo` 提前到 `amHint` 之前复用；`el.amHint.title = srcInfo.detail`（原来 detail 挂在 `#am-note` 的 `title` 上，说明删除后移到来源行，悬浮仍可看全部依据） |
| `app.js` | `amPriceLabel()` 只被这段说明调用，一并删除（无其他调用方） |
| `app.js` | `#am-note` 改为只在**两种边界**下写入并显示，其余情况 `textContent = ""` + `hidden = true` |
| `style.css` | 增 `.am-workbench .am-note[hidden] { display: none; }`，避免 `margin-top: 11px` 留空隙 |
| `tests/test_r44_mode_live.py` | `el.amNote.title = srcInfo.detail;` → `el.amHint.title = srcInfo.detail;`（随实现迁移，不是放宽） |
| `tests/test_r227_ammo_note_hidden.py`（新，5 条） | 文案不得复活 / `amPriceLabel` 已删 / 无提示时必须 hidden / detail 悬浮已迁移 / Node 桩实跑三种状态 |
| `tools/r227_accept.py`（新） | 真实浏览器 34 项验收 |

## 4. 保留下来的两种边界提示

删的是“解释”，不是“缺数据时的告示”。以下两种仍会在 `#am-note` 出现（也只有这两种）：

1. **来源选了 CRAFT**：`本地 ammo.json 的 src 实测只有 trader / barter / none，没有制作来源，结果为空（如实留空，不编造）。`
   —— 不写，用户会以为“筛选坏了”。
2. **价格口径选了 avg7d**：`上游 tarkov.dev 不提供 7 日均价，该列一律显示 —。`
   —— 不写，整列 `—` 会被当成数据缺失。

两者都是**结果会变空**的边界，且只在用户主动切到该筛选时出现；默认态下一行都不显示。

## 5. 验收

`tools/r227_accept.py`（真实浏览器）**34/34**：

| 状态 | 结果 |
|---|---|
| 默认（lastPrice / 全部来源） | `#am-note` `hidden=true`、`offsetParent=null`、高度 **0 px**、`textContent=""`；侧栏文本不含「种口径 / G1 阻力仿真 / C1–C6 / 弹道曲线 / 件弹药 /」 |
| 顶部工具栏 | `#am-count` = `200 / 200 件`；`#am-hint` = `本地数据 · 离线可用`，`title` 保留完整来源依据 |
| 切 avg7d | 提示出现（h=33 px），只有「价格口径选了 avg7d…」一句；切回 lastPrice 后重新隐藏（h=0） |
| 切 CRAFT | 提示出现，表格显示「没有匹配的弹药」；`RESET` 后恢复 200 行且提示再次隐藏 |
| 控制台 | 无 JS 异常 |

全量测试 **2023 passed / 1 skipped**（`build/_pytest_r227.xml`，退出码 0）。

## 6. 边界

- 只删前端文案，未改 `data/ammo.json`、未改任何价格口径逻辑（`amPriceOf` / `amPriceNA` 原样）。
- 未 commit / push，未打包（`dist/EFTMap.exe` 仍是 11-09 产物，看不到本次改动）。
