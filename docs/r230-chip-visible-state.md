# R230 · 口径按钮「亮 = 当前显示」，按下右侧筛选按钮立即变化

## 用户澄清（2026-11-10 20:22 / 20:23）

> 凡是被口径过滤掉、当前没在显示的口径也一律变灰，只留选中的亮着 要的就是这个啊

> 而且你现在做的是搜索 我要的是右侧的筛选按钮 按下后就有变化

R229 理解反了：按**不含口径过滤**的池子（`amRowsBase()`）统计「这个口径还有没有子弹」，
于是点口径按钮时其它按钮纹丝不动，只有搜索 / 区间才让它们变灰——正好不是用户要的。

## 现在的语义

**亮 = 这个口径的子弹当前确实显示在表格里；灰 = 当前不显示。**

| 状态 | 结果 |
| --- | --- |
| 没选任何口径 | 所有有子弹的口径都亮；被其它筛选（搜索 / 区间 / 来源 / 商人等级）筛成 0 发的口径灰 |
| 选中 1 个口径 | **只有它亮，其余 31 个立刻变灰** |
| 选中多个 | 只有那几个亮，其余灰 |
| 被选中但其它条件把它筛成 0 发 | 仍然灰（它确实没显示），`aria-pressed` 仍显示选中态 |
| RESET / 取消全部选择 | 回到「所有有子弹的口径都亮」 |

灰不是禁用：点一下就把它加入选中集合、亮回来。所以仍然只改 `data-empty` 与 `title`，
不加 `disabled` / `aria-disabled`。两种灰在悬浮提示里分开说明：

- 「当前未选中，表格不显示该口径（点击可加入）」——还有子弹，只是没选；
- 「当前筛选下 0 发子弹」——其它条件把它筛空了。

## 实现

核心一句话：**灰态按最终显示行算，不按 base 池算。**

```
pool  = amRowsBase()              搜索 / 来源 / 商人等级 / 区间
rows  = amFilterByCal(pool)       ← 表格实际显示的行
        │
        ├── amChipCounts(rows)   → 每个口径「显示了几发」→ 0 发就置灰
        └── amChipCounts(pool)   → 只用来在 title 里解释灰的原因
```

`app.js` 三处调用点都传了 `rows`：

- `renderAmmo()`：`syncAmmoChipEmpty(pool, rows)` —— **点口径按钮走的就是这条**
  （事件委托里改完 `aria-pressed` 调 `renderAmmo()`），所以按下立刻有变化；
- `renderAmmoFilterUI()`：重建 chips 时按 `amFilterByCal(pool)` 写好初始亮/灰，
  避免先全亮一帧再变灰；
- 搜索框 `input`：只走 `createTable.setSearch()` 不重绘表格，单独同步一次。

`amChipCounts()` 是纯计数函数（传哪池数哪池），`amRows()` 仍等于
`amFilterByCal(amRowsBase())`，散点图那几处不变。CSS 沿用 R229 的灰态
（`style.css` 暗字暗底 + 选中但空的暗青底；`theme-windows-xp.css` 用整体
`opacity` .45 / .7，因为 XP 按钮是位图九宫格、改背景色会被高特异性规则压过）。

## 验收（`tools/r230_accept.py`，19/19 PASS）

全部用真实点击触发，不拿搜索当触发源：

| 场景 | 结果 |
| --- | --- |
| 默认 | 32 个全亮，表格 200 / 200 件；R228 的 90px 等宽不回归 |
| **按下 `9x19`** | **只剩 `9x19` 亮，31 个立刻变灰**；按下态生效；灰按钮 computed `opacity=0.45` vs 亮 `1`；灰按钮 title 说「当前未选中」；表格 9 / 200 件 |
| 再按 `5.45x39` | 两个亮、30 个灰；表格 9 → 22 件 |
| 再按一次 `9x19` 取消 | 只剩 `5.45x39` 亮；表格 22 → 13 件 |
| SHOW 手枪组 | 只亮该组 8 个口径，其余灰 |
| 搜索 9x19 后按 `5.45x39`（0 发） | 它**仍然灰**、title 说「0 发子弹」、表格 0 行 |
| RESET | 32 个全亮、无残留按下态 |
| `PEN≥40`（无选中） | 17 亮 / 15 灰（0 发的灰），表格 43 件 |
| **逐个点选 32 个口径** | 每次只亮「当前选中且有子弹」的那一个，32 个全吻合 |
| JS 异常 | 无 |

截图：`docs/r230/01-default.png` … `06-pen40.png`。

## 测试

`tests/test_r229_chip_empty.py` 断言按新语义**改向、不放宽**（8 条）：
「灰态按 base 池算」改为「按最终显示行算，且 `amChipCounts(pool)` 仍保留用于解释原因」，
新增「点口径按钮的路径必须重算亮/灰」；Node harness 的 `countsWhileSelected`
改为验证「按最终显示行计数时未选中口径归零」，并加验两种灰的 title。

`tools/r229_accept.py` 与 `docs/r229-chip-grey.md` 已加「已作废」标注，保留作历史。

全量 `python -m pytest tests -q --junitxml=build/_pytest_r230.xml` →
**2031 passed / 0 failed / 0 errors / 1 skipped**（合计 2032，138.95 s，
比 R229 多 1 条，正是新增的「点口径按钮必须重算亮/灰」用例）。
日志末段的 `ConnectionAbortedError` / `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 是
SSE 测试线程收尾与临时目录批量删除守卫的既有噪音，JUnit 无 failure / error 节点。
