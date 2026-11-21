# -*- coding: utf-8 -*-
"""R19.6 回归：FORGE 压缩 + 中栏顺序 + 结构化装配画布（CSS Grid）。

验收重点（对应任务书）：
1. FORGE 区域被压缩（容器宽度上限、字号、间距都变小），且样式只作用于 .gw-forge；
2. 中栏 DOM 顺序为 LOAD VARIANT → 画布 → 属性条 → 整枪属性 → 隐藏属性 → 其余；
3. 装配画布由真实槽位树 + 父子关系算出网格位置，不再使用固定 left/top；
4. 枪械本体占 3 列、子弹格单独一行、空槽/真实槽位/已装件分离；
5. 交互契约（左键选槽 / 右键卸载 / 悬浮浮窗）与版本标记保持。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
HTML = os.path.join(ROOT, "index.html")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _body(css, selector, last=True):
    """取覆盖该选择器的最后一条（或第一条）规则体。"""
    i = css.rindex(selector) if last else css.index(selector)
    j = css.index("{", i)
    return css[j + 1:css.index("}", j)]


def test_forge_area_is_compacted():
    """FORGE 容器宽度 + 内部字号/间距都必须收紧（不是只改一两个数字）。"""
    css = _read(CSS)
    # 只在 R19.6 段内取规则：整张样式表里 .gw-buildpage 有多条历史规则，
    # 段内第一条是主规则，段内第二条是窄屏媒体查询（应取主规则）。
    r196 = css[css.index("   R19.6：FORGE 压缩 + 结构化装配画布"):]
    buildpage = _body(r196, ".gun-workbench .gw-buildpage {", last=False)
    assert "minmax(196px, 236px)" in buildpage, "FORGE 栏宽上限必须收窄到 236px"
    assert "column-gap: 8px" in buildpage

    forge = _body(css, ".gun-workbench .gw-forge {")
    assert "padding: 4px 8px 10px" in forge, "FORGE 内边距必须收紧（R19.95：顶部 4px 与三栏齐平）"
    assert "font-size: 10px" in forge and "line-height: 1.25" in forge

    head = _body(css, ".gun-workbench .gw-forge-head b {")
    assert "font-size: 11px" in head and "letter-spacing: .02em" in head, \
        "FORGE 标题字号/字距必须缩小"
    sub = _body(css, ".gun-workbench .gw-forge-sub {")
    assert "font-size: 9px" in sub and "margin: 1px 0 6px" in sub
    sec = _body(css, ".gun-workbench .gw-forge-sec {")
    assert "margin-bottom: 7px" in sec
    note = _body(css, ".gun-workbench .gw-forge-note {")
    assert "font-size: 9px" in note
    # 压缩必须精准作用于 FORGE 区域，不得出现全局 / 中栏/右栏选择器
    tail = css[css.index("   R19.6：FORGE 压缩 + 结构化装配画布"):]
    forge_part = tail[:tail.index("/* ---- 3) 装配画布")]
    for line in forge_part.splitlines():
        s = line.strip()
        if not s.endswith("{") or s.startswith("/*") or s.startswith("@"):
            continue
        assert ".gw-forge" in s or s == ".gun-workbench .gw-buildpage {", \
            "FORGE 压缩规则误伤其他区域：%s" % s


def test_center_column_order_is_loadvar_canvas_bars_stats_hidden():
    """整枪属性必须在属性条下方、隐藏属性上方（真实 DOM 顺序）。"""
    html = _read(HTML)
    idx = lambda sid: html.index('id="%s"' % sid)          # noqa: E731
    assert idx("gw-meta") < idx("gw-visual") < idx("gw-tree")
    assert idx("gw-tree") < idx("gw-bars")
    assert idx("gw-bars") < idx("gw-stats")
    assert idx("gw-stats") < idx("gw-hidden")
    # R19.11：信息条（当前槽位）已移到右栏顶部；中栏不再保留 gw-focus
    assert 'id="gw-focus"' not in html, "不得在中栏重复显示当前槽位"
    assert idx("gw-hidden") < idx("gw-bottom")
    assert idx("gw-slotinfo") < idx("gw-hidebad") < idx("gw-cand-search") < idx("gw-table"), \
        "右栏自上而下：当前槽位 → 隐藏不兼容 → 搜索 → 候选表"
    assert 'id="gw-ammo"' not in html, "R19.7：画布下方的独立弹药区必须删除"
    assert "gw-nodecanvas" not in html
    # 顺序由文档流决定，不允许用定位/负 margin 伪装
    css = _read(CSS)
    assert ".gun-workbench .gw-stats { order:" not in css
    assert ".gun-workbench .gw-center > * { position: absolute" not in css


def test_canvas_is_grid_driven_by_real_slot_tree():
    """R19.12：画布是**固定 6 行 × 9 列**网格，槽位只决定落在哪一格。

    与 R19.6 的差别：以前列数由真实槽位树算出（8~11 列随枪变化、行数也随之变化），
    现在行列数恒为 6×9；槽位树仍然决定"谁占哪一格"和父子锚定关系。
    """
    js = _read(APP)
    css = _read(CSS)

    engine = js[js.index("var GW_GRID_ROWS = 6"):js.index("function renderGunTree() {")]
    assert "GW_GRID_ROWS = 6" in engine and "GW_GRID_COLS = 9" in engine, "网格必须固定 6×9"
    assert "GW_ANCHOR" in engine and "span: 3" in engine, "枪械本体占 3 列且是固定锚点"
    assert "gwLaneOf(g, p)" in engine, "车道由真实槽位语义推导"
    assert "occupied" in engine, "同格冲突必须消除（不重叠、均可点击）"
    assert "reserved" in engine, "固定锚点格要预留，普通附件不得漂进去"
    assert "5bf3e03b" not in engine and '"M4A1"' not in engine, "不得为某把枪写死模板"

    grid = _body(css, ".gun-workbench .gw-canvas.gw-grid {")
    assert "display: grid" in grid
    assert "repeat(var(--gw-cols, 9), minmax(0, 1fr))" in grid
    # R19.14：空行不得塌缩——行轨道固定 6 条，且每条有非零最小高度
    assert "repeat(var(--gw-rows, 6), minmax(var(--gw-row-min" in grid, "行轨道必须固定为 6，且空行有最小高度"
    assert "minmax(0, auto))" not in grid, "minmax(0, auto) 会让空行塌缩成 0 高（R19.14 已禁止）"
    assert "max-width: 566px" in grid, "画布宽度上限（9 列 × 58px 量级）"
    assert "overflow: visible" in grid, "角标不得被裁切"
    part = _body(css, ".gun-workbench .gw-canvas.gw-grid .gw-part {")
    assert "aspect-ratio: 1 / 1" in part, "卡片尺寸由列宽决定，保持正方形"

    render = js[js.index("function renderGunTree() {"):js.index("function renderGunFocus(")]
    assert 'setProperty("--gw-cols"' in render and 'setProperty("--gw-rows"' in render
    assert 'setAttribute("data-parent"' in render and 'setAttribute("data-lane"' in render
    assert 'setAttribute("data-row"' in render and 'setAttribute("data-col"' in render
    assert "gw-cell-body" in render and "span " in render
    assert ".style.left" not in render and ".style.top" not in render


def test_slot_kinds_are_distinguished():
    """空白占位 / 可安装空槽 / 已装槽位 / 子弹格必须区分状态。"""
    js = _read(APP)
    vis = js[js.index("function gwSlotVisible("):js.index("function gwBuildLayout(")]
    assert "g.installed[path]" in vis, "已装件优先占格"
    # R19.18 升级：下挂榴弹槽（GP-25）不再被整体隐藏 —— 真实数据里有这个槽的枪械
    # 必须显示，并按布局规则落在导气区域下方；只有「游戏里真的没有」的枪械才不显示。
    assert 'base === "launcher"' not in vis, "下挂榴弹槽不得整体隐藏（R19.18：GP-25 要显示）"
    assert "gwSlotConflicted" in vis, "真实互斥（top cover 等）必须由安装状态驱动"
    assert "gwSameSlotKind" in vis, "只有真正重复的槽位才互相顶替"
    assert "gwSidBase" in vis and "sibs" in vis, "同基名空副本占格规则"
    card = js[js.index("function gwPartCard("):js.index("function gwDrawLinks(")]
    assert "gw-part-empty" in card and "gw-part-slotlab" in card, "空槽虚线 + 槽位短标签"
    assert "gwIsBadSlot(node) ? \"B.A.D\"" in card, "B.A.D 配件栏按数据判定"
    ammo = js[js.index("gw-part-ammo"):js.index("function renderGunFocus(")]
    assert 'setAttribute("data-gap", "mod_ammo")' in ammo, "子弹格如实标记为数据缺口"
    assert "g.ammoFocus = true" in ammo, "R19.7：子弹格点击必须切到右侧弹药候选"
    assert "gunAmmoState" in ammo, "子弹格复用统一的弹药选择状态"


def test_fixed_grid_anchor_coordinates():
    """任务书 3.2 节的固定坐标必须落成引擎常量，且主体链按真实槽位树映射。

    以前这条测的是"参考图里 M4A1 的行数能被复现"，属于随枪变化的经验值；
    现在规范固定成 6×9，所以断言改成核对锚点常量本身 + 两种主体结构的列映射。
    """
    js = _read(APP)
    eng = js[js.index("function gwSidBase("):js.index("function renderGunTree() {")]
    for frag in ('body:      { row: 3, col: 6, span: 3 }',
                 'stock:     { row: 3, col: 9 }',
                 'mag:       { row: 4, col: 7 }',
                 'grip:      { row: 4, col: 8 }',
                 'ammo:      { row: 5, col: 7 }',
                 'charge:    { row: 2, col: 9 }',
                 'stockChild:  { row: 4, col: 9 }',
                 'stockChild2: { row: 5, col: 9 }'):
        assert frag in eng, "固定锚点缺失：%s" % frag
    # 第三行主体：标准结构 c1..c5；无独立枪管槽时整体左移一格（c1 留空）
    assert 'if (hasBarrel) { return { muzzle: 1, gas_block: 2, barrel: 3, handguard: 4, receiver: 5 }; }' in eng
    assert 'return { muzzle: 2, gas_block: 3, barrel: 0, handguard: 4, receiver: 5 };' in eng
    # 枪托链只沿"基名仍是 stock"的子槽往下排（R19.15.1 起用 isStockBase 归一
    # mod_stock / mod_stock_000 / mod_stock_akms 三种上游写法），挂在枪托上的导轨不算枪托的一层
    assert 'isStockBase(baseOfPath(k))' in eng
    assert 'function isStockBase(b) { return b === "stock" || /^stock_[a-z0-9]+$/i.test(b); }' in eng


def test_interactions_and_business_logic_untouched():
    """本轮只改布局，业务链路必须原样保留。"""
    js = _read(APP)
    assert 'card.addEventListener("click"' in js
    assert "g.focus = path;" in js
    assert "persistGun();" in js
    assert 'card.addEventListener("contextmenu"' in js and "clearGunSlot(path)" in js
    assert "gwTipShow(card, tipHtml" in js
    # 右侧候选筛选仍然由选中槽位驱动
    assert "function renderGunTableView(" in js
    assert "function renderGunStatsV2(" in js and "function renderGunBars(" in js
    # 属性条 / 整枪属性 / 隐藏属性的渲染入口不变
    assert "renderGunStats();" in js and "renderGunBars();" in js and "renderGunTree();" in js


def test_version_marker_r19_6_synced():
    js = _read(APP)
    html = _read(HTML)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    build = m.group(1)
    for name in ("style.css", "theme-windows-xp.css", "app.js", "gun_builder.js", "combat_sim.js"):
        assert re.search(re.escape(name) + r"\?v=" + re.escape(build.lower()), html), "%s 版本串未同步到 r19.8" % name
