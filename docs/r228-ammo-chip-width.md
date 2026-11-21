# R228 · 弹药侧栏口径按钮统一宽度

## 用户原话（2026-11-10 16:55）

> 然后子弹界面右侧的筛选按钮 我希望所有子弹的按钮都一样宽

## 改前实测

侧栏固定 300px，口径分组 `.am-chips` 是 `display:flex; flex-wrap:wrap`，每个
`.am-chip` 的宽度 = 文字自然宽度 + padding，于是同一屏里 32 个按钮从 **36.1px 到
95.9px** 参差，每行塞 4–5 个不等：

```
7.62x25 56.0 | 9x18 41.5 | 9x19 41.5 | 9x21 41.5 | .50 AE 49.5
.357 39.4 | .45 ACP 56.0 | 20x1mm 59.9
...
20g 36.1 | 40mm 俄制榴弹 95.9
```

## 根因

`.am-chip` 没有宽度约束，flex 容器按内容分配，口径名长短直接决定按钮宽窄。

## 改法

`style.css`：

```css
.am-workbench .am-chips {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 3px;
}
.am-workbench .am-chip {
  /* 原 height / padding / font / 配色不变 */
  min-width: 0;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

- `minmax(0, 1fr)`：列宽只由容器决定，不受内容撑开（`minmax(0,…)` 是必需的，
  `1fr` 单独用时最小值仍是 `auto`，长内容会把列撑宽）。
- 侧栏 300px − padding 20 − 分组边框 2 = 276px，3 列 → **每列 90px**。
- 省略号是兜底：真装不下的口径名收成 `…`，完整名在 `title` 里（原本就有）。

窄屏（≤1100px，侧栏从右栏变成整行）追加一条：

```css
@media (max-width: 1100px) {
  .am-workbench .am-chips { grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); }
}
```

否则 3 列会被拉成 300px 宽的大条；`auto-fill` 让列数随可用宽度增长，同一行内仍等宽。

## 一个容易踩的点：真正决定按钮尺寸的不是 style.css

工作台的按钮尺寸最终由 `assets/xp-ui/xp-ui-app.css` 里这条高特异性规则决定：

```css
html body .am-workbench button:not(.am-tab):not(.am-seg-btn):not(...) {
  height: 28px; padding: 0 8px; font: 11px/1 ...;
  border: 5px solid transparent; border-image: url("btn-normal.png") 5 fill / 5px stretch;
}
```

它在 `index.html` 里最后加载，特异性 (0,6,3) 远高于 `.am-workbench .am-chip` (0,2,0)。
所以 R228 只改布局（`.am-chips` 的 grid、`.am-chip` 的溢出行为），**不动**
height / padding / font——那几条改了也不会生效，硬要改就得同步改 xp-ui 那一层。

## 验收（`tools/r228_accept.py`，18/18 PASS）

1600×1000 视口：

| 项目 | 结果 |
| --- | --- |
| `.am-chips` display | `grid` |
| 列轨 | `90px 90px 90px` |
| 32 个按钮宽度簇 | `[90]`（唯一值） |
| 各分组内部宽度簇 | pistol / rifle / pdw / shot / gl 全部 `[90]` |
| 每行按钮数 | ≤ 3，共 12 行（改前 9 行） |
| 侧栏横向滚动 | 0 |
| 选中一个（aria-pressed=true）后 | 仍有勾选态，宽度仍 `[90]` |
| 无 JS 异常 | ✅ |

1000×800 窄视口：`grid`，9 列每列 105.7px，宽度簇 `[105.7]`，侧栏无横向滚动。

## 已知边界

- **`40mm 俄制榴弹` 会显示省略号**：XP 主题下 90px 列宽扣掉 5px 边框 ×2 与 8px
  内边距 ×2 后内容区只有 64px，这条口径名 11px 字号下要约 73px。它同时也是全部 32
  个口径里唯一超标的一个（次长 `12 号独头弹` 约 58px，正常显示）。
  完整名仍在 `title`，表格里也照常显示全称。
  若要它不省略，只有三条路：改成 2 列（每列 136px，行数 12 → 16）、侧栏加宽到约
  325px（会让主表少 25px）、或给它单独一个短名（属于改文案，需用户点头）。
- 按钮**高度**不受影响：XP 主题统一 28px，深色底样式 18px，两种都是原值。

## 测试基线

全量 `python -m pytest tests -q --junitxml=build/_pytest_r228.xml` →
**2023 passed / 0 failed / 1 skipped**（合计 2024 条，与 R227 持平：本轮是纯 CSS
布局改动，未新增用例；`tests/test_r12_ammo.py` 只断言 `#am-groups` 存在，不涉及
子元素布局）。
