# R231 · 弹药页空结果时，去掉被拉伸放大的位图背景

## 用户原话（2026-11-10 20:41）

> 然后你看一下 我发现把所有子弹隐藏后 子弹页面背后的背景
> 好像是什么图强行放大后的样子 请改掉

## 排查结论：不是背景图，是表格滚动区的 `border-image … fill`

空态下把 `#ammo-view` 内所有元素的 `background-image` / 祖先链 / `<img>` / 伪元素
都查了一遍，**没有任何 background-image**。真正的来源是
`assets/xp-ui/xp-ui-app.css` 里三个工作台共用的一条规则：

```css
html body .loadout-workbench .tbl-scroll,
html body .gun-workbench .tbl-scroll,
html body .am-workbench .am-table .tbl-scroll {
  border: 2px solid transparent !important;
  border-image: url("table-frame.png") 2 fill / 2px stretch !important;
  background-color: #fff !important;
}
```

`table-frame.png` 只有 **64×64**（白底 + 一圈细内框线），`fill` 关键字让它的
中间切片一起被 `stretch` 到整块滚动区（实测 1282×715）。那圈细内框线被放大成
左右和底部一圈模糊灰带——就是「某张图强行放大后的样子」。

**为什么平时看不到**：表格有行时 200 行铺满滚动区，把这块 fill 完全盖住；
只有全部子弹被筛掉、只剩一行「没有匹配的弹药」时才露出来。

对比实验确认：单独关掉 `.tbl-scroll` 的 `border-image` → 灰带完全消失；
单独关掉 `#am-workbench` 的 `menu-panel-bg.png 12 fill / 1px stretch` → 截图**毫无变化**，
所以工作台外壳那层不是元凶，且它与枪匠 / 配装 / 任务共用，本轮不动。

## 修法

把弹药页从共用位图规则里摘出来，改用纯白底 + 1px 实线：

```css
/* 共用规则只留配装 / 枪匠 */
html body .loadout-workbench .tbl-scroll,
html body .gun-workbench .tbl-scroll { …table-frame.png… }

html body .am-workbench .am-table .tbl-scroll {
  border: 1px solid var(--xp-border-dark, #aca899) !important;
  background-color: #fff !important;
}
```

- 颜色与 `theme-windows-xp.css` 里既有的 `html .am-workbench .tbl-scroll`
  （白底 + `1px solid var(--xp-border-dark)`）完全一致，等于**回到主题本来的口径**。
- 必须带 `!important`：`style.css` 的 `.am-workbench .am-table .tbl-scroll { border: 0 }`
  特异性更高，不加会变成完全无边框。
- 配装 / 枪匠两个工作台保持原样（它们有数据时同样铺满，且未被用户提及）。

## 验收（`tools/r231_accept.py`，12/12 PASS）

| 检查 | 结果 |
| --- | --- |
| 静态：共用规则已摘掉弹药页；配装 / 枪匠仍在 | ✅ |
| 弹药页有数据（200 行） | `borderImageSource=none`、`borderTopWidth=1px`、白底 |
| **全部隐藏（搜索无结果，0 / 200 件 + 空态行）** | 仍 `none` / `1px` / 白底，**无放大灰带** |
| 枪匠 / 配装表格滚区 | 仍用 `table-frame.png`（未回归） |
| R228 / R230 | 32 个口径按钮仍 90px 等宽、清空搜索后全亮 |
| JS 异常 | 无 |

截图：`docs/r231/01-normal.png`（有数据）、`02-empty-fixed.png`（空结果，干净白底 + 细边）。

## 测试

`tests/test_r231_ammo_table_frame.py` 5 条静态契约：弹药页不再共用 fill 拉伸、
弹药段 CSS 声明里不得再出现位图 / `fill` / `stretch`（剥掉注释再查——注释为解释
原因会提到这些词，R226 踩过同样的坑）、`!important` 不能被去掉、与主题既有列表
口径一致、工作台外壳位图保持不动。

全量 `python -m pytest tests -q --junitxml=build/_pytest_r231.xml` →
**2036 passed / 0 failed / 0 errors / 1 skipped**（合计 2037，138.56 s，
比 R230 多 5 条，正好是本轮新增的 5 条用例）。
