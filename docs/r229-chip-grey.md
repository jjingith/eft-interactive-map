# R229 · 口径按钮在「当前筛选下没有子弹」时置灰

> ⚠️ **本轮方向做反了，已被 R230 取代**，见 `docs/r230-chip-visible-state.md`。
> 用户随即澄清：要的是「凡是被口径过滤掉、当前没在显示的口径也一律变灰，只留选中的亮着」，
> 而且要「右侧的筛选按钮按下后就有变化」，不是搜索。R229 按不含口径过滤的池子统计，
> 导致点口径按钮时侧栏毫无变化。以下仅作历史记录，`tools/r229_accept.py` 同样已作废。

## 用户原话（2026-11-10 20:02）

> 还有一个问题 就是子弹页面 右侧的筛选 我希望点击后 如果是不显示的子弹
> 按钮就变灰 现在不知道哪些显示 哪些不显示

## 语义

**灰 = 这个口径在「当前其它筛选条件」下一发子弹都不剩，点了也不会有结果。**

- 不是禁用：不放宽条件时点它没有结果，但把搜索 / 区间 / 来源放宽就会亮回来，
  所以不加 `disabled` / `aria-disabled`，按钮始终可点；`title` 补上「当前筛选下 0 发子弹」。
- 「当前显示哪些」由 `aria-pressed`（选中高亮）表达；灰色表达的是另一件事——
  **这个口径有没有可显示的子弹**。两者不重复。
- 灰态跟随所有筛选：搜索词、穿透 / 伤害 / 初速区间、来源、only TraderLvl、商人等级。

## 最关键的一个取舍

统计**必须基于不含口径过滤的池子**（`amRowsBase()`），不能用 `amRows()`。
否则只要选中一个口径，其余 31 个口径都会因为「被口径过滤掉」而判成 0 发、全部变灰，
既和选中态重复，也让用户没法知道哪些口径其实还有子弹。

```
amRowsBase()   搜索 / 来源 / 商人等级 / 区间   ← 灰态按这个池子算
      │
      ├── amChipCounts(pool) → 每个口径各有多少发 → data-empty
      │
      └── amFilterByCal(pool) → 表格实际显示的行
```

`amRows()` 保留为 `amFilterByCal(amRowsBase())`，散点图那几处仍用它。

## 改动

`app.js`：

| 函数 | 作用 |
| --- | --- |
| `amChipOneHit(k, a)` | 从 `amChipHit` 抽出单口径匹配（含 `atyp` 的霰弹 / 独头弹拆分），供计数复用 |
| `amChipCounts(pool)` | 每个口径筹码在池子里的命中发数 |
| `amRowsBase()` | 原 `amRows()` 去掉口径过滤 |
| `amFilterByCal(pool)` | 在 base 上套口径多选 OR |
| `amChipEmptyState(chip, k, empty)` | 只写 `data-empty="0/1"` 与 title |
| `syncAmmoChipEmpty(pool)` | 只刷灰态、不重建 DOM |

- `renderAmmo()` 改为先算一次 `pool = amRowsBase()`，表格用 `amFilterByCal(pool)`，
  灰态用 `syncAmmoChipEmpty(pool)`，避免重复遍历。
- **搜索框是特例**：它的 `input` 事件只走 `createTable.setSearch()`，不重绘表格、
  也不重建 chips。所以那里单独补了 `var pool = amRowsBase(); syncAmmoChipEmpty(pool);`，
  并用 `amFilterByCal(pool).length` 更新工具栏计数（原来这里调了一次 `amRows()`）。
- `renderAmmoFilterUI()` 重建 chips 时直接按 `amChipCounts(amRowsBase())` 写好初始灰态，
  避免「先全亮一帧再变灰」。

`style.css`（深色底工作台）：`[data-empty="1"]` 用暗字 / 暗底 / 暗边；
选中但为空另给暗青底 `#53616b`，和正常选中的亮青 `--am-accent-2` 区分开。

`theme-windows-xp.css`（实际生效的 XP 主题）：XP 按钮是 `btn-normal.png` 九宫格，
`xp-ui-app.css` 用 `html body .am-workbench button:not(...)`（特异性 0,6,3）把
`background` 设成 `transparent !important`、`color` 也压过，改背景 / 文字色不生效。
所以用 **整体 `opacity`**：未选中且空 `.45`、选中但空 `.7`（保留按下态可辨）。
不用 `filter:grayscale`，那会把按下态一起洗掉。

## 验收（`tools/r229_accept.py`，14/14 PASS）

| 场景 | 结果 |
| --- | --- |
| 默认态 | 32 个按钮全有 `data-empty`，全 `0`；R228 的 90px 等宽不回归 |
| 搜索 `9x19` | 只有 `9x19` 不灰，其余 31 个灰；表格 9 / 200 件；灰按钮 computed `opacity=0.45`、正常 `1` |
| 点选一个已灰的 `5.45x39` | 其它 31 个灰态**集合不变**；该按钮 `aria-pressed=true` + `data-empty=1`；表格 `0 / 200 件` +「没有匹配的弹药」 |
| 清空搜索 / RESET | 灰态回到默认基线（0 个灰），无残留按下态 |
| `PEN ≥ 40` | 15 灰 / 17 亮，表格 43 / 200 件 |
| **逐个点选 32 个口径** | `data-empty=1` ⟺ 单独选中该口径后 0 行，**32 个全部吻合** |
| JS 异常 | 无 |

截图：`docs/r229/chips-default.png`、`chips-search-9x19.png`、`chips-pen40.png`。

## 测试

`tests/test_r229_chip_empty.py` 7 条：静态契约（灰态按 base 池算、搜索路径必须同步、
置灰不是禁用、两套主题都有灰态规则）＋ Node 抽函数实跑（`amChipCounts` 命中数、
选中口径后计数不变、`atyp` 霰弹 / 独头弹不串、`amChipEmptyState` 只改属性）。

全量 `python -m pytest tests -q --junitxml=build/_pytest_r229.xml` →
**2030 passed / 0 failed / 0 errors / 1 skipped**（合计 2031，140.97 s，
比 R228 的 2024 多 7 条，正好是新增的 7 条用例）。
