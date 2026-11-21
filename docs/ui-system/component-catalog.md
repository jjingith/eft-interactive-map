# 组件清单与使用说明（ui-components）

- 版本：`ui-spec 1.0` / 构建 `R19.24`
- 代码：`styles/design-tokens.css`（令牌）、`styles/ui-components.css`（样式）、`js/ui-components.js`（`window.GWUI`）
- 规范：`docs/ui-system/design-spec.md`
- 展示页：`/ui-showcase`（本地，可交互）

> 规则一句话：**业务模块只决定"放什么数据、放在哪"，不决定"长什么样"。**
> 需要新外观 → 改组件或加令牌，不在页面里写私有样式。

---

## 一、快速上手

```html
<link rel="stylesheet" href="styles/design-tokens.css">
<link rel="stylesheet" href="styles/ui-components.css">
<script src="js/ui-components.js"></script>
```

```js
// 按钮
var save = GWUI.btn({ label: "保存", variant: "primary", onClick: fn });

// 面板（带标题条与操作区）
var panel = GWUI.panel({
  title: "商人任务",
  sub: "PvP（常规）· 503 个",
  actions: [save],
  body: tableNode
});

// 表格（列宽用 colTemplate，单元格用 renderCell）
var table = GWUI.table({
  colTemplate: "minmax(140px,2fr) 84px 44px",
  columns: [{ key: "name", label: "任务" }, { key: "lvl", label: "等级", align: "right" }],
  rows: rows,
  renderCell: function (row, col, i) { return row[col.key]; }
});

// 弹窗（返回 { close }；Esc/遮罩可关、焦点自动归还）
var dlg = GWUI.dialog({
  title: "清空进度", danger: true,
  body: "清空后无法恢复。",
  buttons: [{ label: "取消" }, { label: "确认清空", danger: true, onClick: fn }]
});

// 提示（挂在元素上；挂了它就别再写 title，避免双提示）
GWUI.tooltip.attach(el, "完整名称：……", { delay: 260 });
```

---

## 二、组件一览

| 组件 | 类名 | API | 状态 | 备注 |
|---|---|---|---|---|
| 按钮 | `.ui-btn` + `--primary` `--danger` `--ghost` `--link` `--sm` `--lg` | `GWUI.btn({label, variant, size, icon, onClick, disabled, pressed, busy, title, ariaLabel, className})` | default / hover / active(下沉 1px) / focus-visible / `aria-pressed` / `disabled` / `aria-busy` | 切换型用 `pressed`；图标按钮必须给 `ariaLabel` |
| 输入框 | `.ui-input` + `--num` `--sm` | `GWUI.input({type, value, placeholder, num, size, min, max, invalid, disabled, onInput, onChange})` | default / focus / `aria-invalid` / `disabled` | 数字输入加 `num`（等宽右对齐） |
| 下拉 | `.ui-select` | `GWUI.select({options:[{value,label,disabled}], value, onChange})` | default / focus / disabled | **保留原生下拉**（离线、键盘、无裁切问题） |
| 复选/单选 | `.ui-check` `--radio` | `GWUI.check({label, checked, radio, name, id, disabled, onChange})` | 未选 / 选中 / focus / disabled | 方形勾用 CSS 画，不用字符 |
| 字段组合 | `.ui-field` `__label` `__hint` `__error` | `GWUI.field({label, hint, error, control, id})` | 正常 / `.is-error` | 标签在上、说明在下、错误替换说明 |
| 标签页 | `.ui-tabs` + `--segmented`；`.ui-tab` | `GWUI.tabs({items:[{key,label,disabled}], value, onChange, segmented})` | default / hover / `aria-selected` / focus / disabled | 方向键切换；roving tabindex |
| 面板 | `.ui-panel` + `--group` `--collapsible` `--plain` `--inset` `--floating` | `GWUI.panel({title, sub, actions, body, foot, group, collapsible, expanded})` | default / hover(标题条) / 折叠 | 嵌套最多 2 层 |
| 工具条 | `.ui-toolbar` + `--flat`；`__group` `__sep` `__grow` | `GWUI.toolbar({groups:[[node...], "sep", "grow", ...]})` | — | 高 30px；分组用 1px 竖线 |
| 表格 | `.ui-table` `__head` `__row` `__cell` `__empty` | `GWUI.table({columns, rows, colTemplate, rowClass, rowAttrs, renderCell, onRowClick, empty})` | 行：hover / `.is-selected` / `.is-disabled` / `.is-conflict`；空态 | 列宽只能通过 `colTemplate`（写到 `--ui-table-cols`） |
| 徽标 | `.ui-badge` + `--ok` `--warn` `--danger` `--info` `--primary` `--muted` | `GWUI.badge(text, kind, title)` | 静态 | 必须带文字，不能只靠颜色 |
| 标题栏 | `.ui-titlebar` `__icon` `__title` `__actions` `__btn` | 原生 DOM（无 API） | — | 不是"给 div 涂蓝"：渐变 + 内亮边 + 上两角圆角 |
| 状态栏 | `.ui-statusbar` `__grow` | 原生 DOM | — | 高 24px，米灰面 |
| 弹窗 | `.ui-dialog__scrim` / `__box` `__head` `__title` `__close` `__body` `__foot` | `GWUI.dialog({title, body, buttons, wide, danger, dismissible, onClose})` | 打开 / 关闭；危险态 | 全局单例；Esc 关闭；焦点陷阱 + 归还；锁滚动 |
| 菜单 | `.ui-menu` `__item` `__sep` `__label` | `GWUI.menu({anchor, items, align})` | hover/focus / `aria-checked` / disabled | 挂 body、视口翻转、↑↓/Enter/Esc |
| 提示 | `.ui-tooltip` `__title` `__en` | `GWUI.tooltip.attach(el, content, {delay, side})` / `.show` / `.hide` | 显示 / 隐藏 | 单节点复用；限宽 320px；hover 300ms、focus 立即 |
| 轻提示 | `.ui-toast` + `--ok` `--warn` `--danger`；`.ui-toast-stack` | `GWUI.toast(text, kind, ms)` | 3 秒自动消失 | 只用于"已保存"这类非阻断反馈 |
| 长文 | `.ui-prose` / `.ui-code` | 原生 DOM | — | 最大宽 760px，行高 1.7 |

---

## 三、状态契约（所有组件共同遵守）

| 状态 | 属性 | 视觉 |
|---|---|---|
| Hover | — | 琥珀底 + 琥珀边 |
| Active | `:active` | 底色加深 + 下沉 1px + 立体翻转 |
| Focus | `:focus-visible` | 1px 蓝环（`--ui-shadow-focus`），不改变布局 |
| Selected | `aria-selected="true"` | 蓝底白字（表格行）／蓝左边条（列表项） |
| Current（分段/标签） | `aria-selected="true"` | 琥珀底 + 内凹（像按下的按钮） |
| Pressed（开关按钮） | `aria-pressed="true"` | 同 Current |
| Disabled | `disabled` + `aria-disabled="true"` | 灰面灰字、去立体、`not-allowed`、不可聚焦 |
| Error | `aria-invalid="true"` + `.is-error` 容器 | 红边 + 红字说明 |
| Loading | `aria-busy="true"` | 左侧转圈 + 文案"处理中…" + 禁止重复点击 |
| Conflict | `.is-conflict` + `disabled` | 红虚线 + 左红条 + ⚠ 文字；逻辑上不可选 |

---

## 四、使用约定

1. **额外类名只能加钩子，不能改视觉**：`GWUI.table({className:"tk-table"})` 是为了兼容既有测试选择器；
   想在钩子类里写颜色/字号是禁止的（评审与测试会拦）。
2. **不要自造按钮/输入/表格样式**。确实缺角色时，先加令牌（`--ui-color-*`）+ 组件修饰类，再更新本文件。
3. **浮层一律挂 body**。业务容器常常有 `overflow: hidden`，自绘浮层会被裁切。
4. **`title` 与自定义提示二选一**。项目里 `title` 还承担"英文原名悬停"（`data-en-text`）职责，
   用了 `GWUI.tooltip.attach` 的元素要先 `removeAttribute("title")`。
5. **销毁**：`tooltip.attach()` 返回 `destroy()`；页面切换/重渲染时应调用，避免旧节点残留监听。
6. **不要重复插入**：`dialog()` 全局单例（开第二个会自动关第一个）；`menu()` 同理。
7. **键盘可达**：所有交互控件要么是原生 `button/input/select`，要么带 `tabindex` 与 `role`。

---

## 五、已知偏差（本轮的取舍，写清楚以便后续收敛）

| 偏差 | 现状 | 影响 | 计划 |
|---|---|---|---|
| 颜色来源 | `--ui-color-*` 桥接 `--xp-*`，调色板仍以 `theme-windows-xp.css` 为准 | 改主色要改 `--xp-*`；但不会出现两套近似色 | 后续把 theme 第 12/13/14 节的硬编码色逐步换成 `--ui-*`，最后删掉自动映射层 |
| 旧弹窗 | `.am-modal`（弹药）、`.gw-prof-modal`（枪械配置）、`.cal-modal`（校准器）仍存在 | 三套标题栏/遮罩/关闭按钮；z-index 取值不一（90 / 9000 / 9990） | 按"弹药 → 配枪 → 校准器"顺序迁到 `ui-dialog` |
| 旧提示 | `.gw-tip`、`.am-graph-tip` 仍存在 | 与 `ui-tooltip` 是两套定位实现 | 同上，随模块迁移 |
| 地图画布 | 深色底、9–10px 标注、脚本注入 SVG 样式 | 属规范 §2.5 例外 | 保持 |
| 任务模块其它页（树/详情/进度） | 仍用 `.tk-btn` 等旧类 | 视觉与商人页略有差异（同一套颜色，但按钮是旧实现） | 试点验收通过后按同一套路迁移 |
| 内联样式 | 仍有 61 处 `style.width` 等 | 多为数据驱动的宽度/位置（合理例外） | 只收敛"样式决策"类内联写法 |

---

## 六、测试与验收怎么跑

```bash
python tools/ui_audit.py                 # 现状审计（数字进 docs/ui-system/audit-data.json）
python -m pytest tests/test_ui_system_round.py -q   # 令牌/组件/展示页/试点/回归
python tools/serve.py --port 8790        # 另起一个本地服务（不动 8787）
python tools/ui_accept.py --port 9791 --base http://127.0.0.1:8790
```

`ui_accept.py` 会做：令牌解析一致性、组件渲染、按钮/输入/标签/表格状态、弹窗 Esc 与焦点归还、
菜单与提示不被裁切、1280/1680 无横向溢出、试点页表格与弹窗、**全部请求必须同源**（离线检查），
并把截图写到 `docs/ui-system/shots/`。
