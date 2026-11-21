# -*- coding: utf-8 -*-
"""R19.5 回归：空间装配画布（对照 db4tarkov /gun 中央区）。

核心断言：
1. 装配区不再是纵向递归卡片树，而是分区空间画布（顶带/中带/底带/rail 带 + SVG 连接线）；
2. 分区规则是通用 sid 语义规则（不硬编码逐枪坐标）；
3. 参考站式视觉元素：空槽占位标签、卡片属性角标、枪械居中卡（当前/基准重量）；
4. R19.4 全部交互契约保留（左键选槽 / 右键卸载 / hover+焦点浮窗 / 64px 方卡）；
5. 版本标记 R19.5。
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


def test_spatial_canvas_replaces_vertical_tree():
    """装配区重构：结构化网格画布 + 父子连接线，旧纵向树 / 旧带式分栏渲染函数移除。"""
    js = _read(APP)
    assert "function renderGunTreeList(" not in js, "旧纵向树渲染必须移除"
    assert "function gwBuildLayout(" in js, "由真实槽位树算出网格行列的布局引擎"
    assert "function gwLaneOf(" in js, "车道（行）语义规则"
    # R19.15：连接线已按需求整体移除；函数实现保留，但画布不再生成 svg 容器
    assert "function gwDrawLinks(" in js, "连线实现保留作历史参考"
    assert "el.gwTree.appendChild(svg)" not in js, "画布不得再挂载 SVG 连线容器"
    assert "--gw-cols" in js and "gridRow" in js and "gridColumn" in js, "CSS Grid 定位"
    assert 'setAttribute("data-parent"' in js, "父件关系可追踪"
    # R19.6：旧带式分栏（顶带/中带/底带/rail 带）与旧分区函数必须彻底移除
    assert "gwZoneOf" not in js and "gwZoneRank" not in js
    assert "gw-band" not in js and "gw-raildiv" not in js
    assert "gwFlatten" not in js and "gwClusterRow" not in js
    # R19.15：连线绘制调用必须移除（不 requestAnimationFrame 画线、不绑 resize 重绘）
    assert "requestAnimationFrame(function () { gwDrawLinks(svg, el.gwTree); })" not in js
    assert "gwBindLinksRedraw();" not in js
    assert "getBoundingClientRect" in js[js.index("function gwDrawLinks("):
                                          js.index("function renderGunTree() {")]
    # 零件不再依赖固定绝对坐标（R19.12：装配布局仍必须由网格坐标驱动；
    # 外观图层 renderGunSkin 是叠加在整枪图上的示意合成，允许用百分比锚点定位）
    engine = js[js.index("function gwBuildLayout("):js.index("function renderGunSkin(")]
    assert ".style.left" not in engine and ".style.top" not in engine
    assert ".style.left" not in js[js.index("function renderGunTree() {"):js.index("function renderGunFocus(")]
    assert "img.style.left" in js[js.index("function renderGunSkin("):js.index("function nodeLabelOf(")]


def test_zoning_is_generic_semantic_rules():
    """车道必须由 sid 语义 + 父子关系决定，不得按具体枪械硬编码。"""
    js = _read(APP)
    body = js[js.index("function gwLaneOf("):js.index("var GW_ROOT_COL_OFF")]
    # 规则基于 sid 模式（mod_ 前缀剥离后按前缀匹配）与父件关系
    for pat in ("sight_rear|sight_front|charge", "scope", "mount", "base === pbase",
                "magazine|pistol_grip"):
        assert pat in body, "车道规则缺 %s" % pat
    assert "gwLaneOf(g, node.parent)" in body, "车道需按父件递归推导"
    # 不允许出现任何具体枪械 id / 枪名驱动的布局分支
    engine = js[js.index("function gwSidBase("):js.index("function gwPartCard(")]
    # R19.28：该切片内新增「标准 AK 照门物品 id → 中文名」数据字典 GW_AK_REAR_SIGHT_IDS，
    # 它按 allow 里的**物品 id** 做结构判定，不是枪名分支；仅该字典的说明性名称含枪名。
    table = re.search(r"var GW_AK_REAR_SIGHT_IDS = \{[\s\S]*?\};", engine)
    assert table, "AK 照门系结构判定缺少物品 id 字典"
    # 剥离注释与该物品名数据字典后再扫描（注释举例、物品中文名不属于布局分支）
    code = engine.replace(table.group(0), "")
    code = re.sub(r"/\*[\s\S]*?\*/", "", code)
    code = re.sub(r"//[^\n]*", "", code)
    assert "5bf3e03b" not in code and "AK-74" not in code and "M4A1" not in code
    # 更严格：枪名 / 枪 id 不得作为比较目标出现在任何分支条件里
    for tok in ("5bf3e03b", "AK-74", "M4A1"):
        assert not re.search(r"(===|!==|==|!=)\s*[\"']" + re.escape(tok), engine), \
            "不允许按具体枪械 id / 枪名做布局分支：%s" % tok


def test_reference_visual_elements():
    """参考站视觉元素：空槽短标签、属性角标、当前/基准重量。"""
    js = _read(APP)
    assert "gw-part-slotlab" in js, "空槽占位短标签（MUZZLE/SCOPE…）"
    assert "gw-part-b2" in js, "卡片上方人机/后坐变化角标"
    assert "gw-gun-meta" in js and "kg" in js, "枪卡当前/基准重量"
    css = _read(CSS)
    # 连线样式可以保留（历史类名），但不得再有连线元素被创建
    assert ".gun-workbench .gw-canvas-links" in css
    # R19.6：卡片尺寸由网格列宽决定（正方形），旧的写死 64/52px 只作为非网格上下文的后备
    m = re.search(r"\.gun-workbench \.gw-canvas\.gw-grid \.gw-part \{[^}]*aspect-ratio: 1 / 1", css)
    assert m, "网格画布内的装配卡必须按列宽保持正方形（R19.6）"


def test_interaction_contracts_kept():
    """R19.4 交互契约在画布卡片上原样保留。"""
    js = _read(APP)
    assert 'card.addEventListener("contextmenu"' in js
    assert "if (installedId) { clearGunSlot(path); }" in js
    assert "gwTipShow(card, tipHtml" in js
    assert 'card.addEventListener("focus"' in js


def test_center_column_structure_matches_reference():
    """中栏顺序（R19.6 用户指定的结构顺序）。

    LOAD VARIANT → 装配画布 → 属性条 → 整枪属性 → 隐藏属性 → 其余。
    整枪属性必须位于属性条下方、隐藏属性上方；顺序由真实 DOM 排列实现，
    不得靠绝对定位 / 负 margin 视觉挪位。
    """
    html = _read(HTML)
    order = [html.index('id="gw-meta"'),
             html.index('id="gw-visual"'),
             html.index('id="gw-tree"'),
             html.index('id="gw-bars"'), html.index('id="gw-stats"'),
             html.index('id="gw-hidden"'),
             html.index('id="gw-bottom"')]
    assert order == sorted(order), "中栏顺序必须为 信息条→画布→属性条→整枪属性→隐藏属性→其余"
    # R19.11：当前槽位信息搬到右侧候选栏顶部，中栏不再有 gw-focus（两处重复显示是 bug）
    assert 'id="gw-focus"' not in html, "隐藏属性下方的「当前槽位」必须删除"
    assert 'id="gw-slotinfo"' in html
    assert 'id="gw-ammo"' not in html, "R19.7：独立弹药区已删除，弹药由画布子弹格驱动"
    assert "gw-nodecanvas" not in html, "旧节点链画布已由结构化画布取代"
    assert "装配（点卡片换配件）" not in html, "参考站无该常驻标题"
    assert 'aria-label="枪械空间装配画布"' in html
    css = _read(CSS)
    cen = css[css.index("/* ============================================================\n   R19.6："):
              css.index(".gun-workbench .gw-canvas.gw-grid {")]
    assert "position: absolute" not in cen and "margin-top: -" not in cen, \
        "中栏顺序不得靠绝对定位 / 负 margin 实现"


def test_build_marker_r19_6():
    js = _read(APP)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    html = _read(HTML)
    assert ("app.js?v=" + m.group(1).lower() + '"') in html   # 资源版本跟随 AM_BUILD 动态同步
