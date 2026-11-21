"""配装工作台（第十六轮）的测试。

分两层：

1. **静态结构测试**（纯 Python）：守住工作台骨架、分类 tab 顺序、价格档降级、
   `setColumns` API 与 CSS 作用域等「文件里必须长成这样」的约束。
   前端没有构建步骤、也没有 JS 测试框架，这类约束只能靠读文件断言。

2. **动态切列测试**（node + 极简 DOM 垫片）：把 `app.js` 里的 `createTable`
   整段源码抠出来，在一个最小 DOM 实现上跑，真的验证
   「切列后表头/数据/列宽一起换、排序键回落第一列、搜索/过滤/选中态/滚动位置不丢」
   这些行为——只靠字符串断言证明不了。

不联网、不依赖外部资源；缺 node 时动态用例自动跳过。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
INDEX_HTML = ROOT / "index.html"
STYLE_CSS = ROOT / "style.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 静态结构
def test_app_js_armor_columns_split_six_concepts():
    """第七项：护甲六概念各自独立成列；错误的「部位有效护甲值」列及其算法必须彻底删除。"""
    js = _read(APP_JS)
    # 被删掉的错误列与它专属的算法（把防护等级与覆盖部位揉在一起）
    for gone in ("zoneClsCol", "zoneCls", "zoneArmorFacts", "zoneArmorText",
                 "collectByCl", "plateClassRange"):
        assert gone not in js, "错误的「部位有效护甲值」列残留：%s" % gone
    assert 'label: "部位有效护甲值"' not in js, "该列不得再作为列名出现"
    # 六个概念各有独立列（列 name 与中文列名）
    for key, label in (("matLabel", "装甲材质"), ("destr", "损毁系数"),
                       ("dur", "基础耐久"), ("effDur", "有效耐久"),
                       ("zoneText", "防护区域"), ("cl", "护甲等级")):
        assert 'key: "%s"' % key in js, "缺护甲列：%s" % key
        assert 'label: "%s"' % label in js, "缺护甲列名：%s" % label
    # 第九轮问题5：错误的「钝击穿透」列必须彻底移除（参考站护甲/头盔/眼镜表均无此列）
    assert 'key: "bt"' not in js, "钝击穿透列残留"
    assert 'label: "钝击穿透"' not in js, "钝击穿透列名残留"
    # 护甲列集必须正好是四列（材质 / 系数 / 有效耐久 / 防护区域），不再混入等级或部位等级
    assert "var armorCols = [matCol, destrCol, effDurCol, zoneCol];" in js
    # 有效耐久必须用未四舍五入的原始系数计算（除的是 materialDestructibility 的原始 d）
    assert "return dur / d;" in js and "effectiveDurability" in js


def test_app_js_plate_cell_na_blank_and_liner_block():
    """第十轮问题4：板位列只承载硬质插板——无硬板位整格空白；内衬走独立内衬列。

    第九轮的「无硬板位但有内衬时在板位格显示 V 块」方案已被第十轮任务书明确取消：
    内衬信息一律进独立的内衬列（linerSum + 九个 liner_* 列），板位列不再携带内衬字段。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    # na（无硬板位）→ 无条件整格空白：不显示插板框 / V 块 / 「未安装」/ 内衬信息
    assert 'if (st.state === "na") { cell.innerHTML = ""; return; }' in js
    # V 块方案必须彻底移除（JS 渲染与 CSS 样式都不许残留）
    assert "lw-plate-liner" not in js, "r9 内衬 V 块渲染残留"
    assert ".lw-plate-liner" not in css, "r9 内衬 V 块样式残留"
    # 板位状态只由硬板位槽（Front/Back/Left/Right_plate）决定，软甲内衬不再冒充板位
    assert "var hard = String(col.zone).toLowerCase();" in js
    # 内衬独立列模型存在：九个内衬 zone 定义 + linerBreakdown 分解函数
    assert "var LINER_COL_ZONES = [" in js and "function linerBreakdown(rec)" in js
    # 已安装插板（on）支持右键卸除：仅在 on 态拦截 contextmenu，复用 clearGearSlot
    assert 'if (st.state === "on" && st.slotId)' in js
    assert "clearGearSlot(st.slotId);" in js


def test_loadout_table_vlines_are_single_continuous_layer():
    """列分隔竖线只能由 .tbl-vlines 覆盖层整条绘制。

    R19.66：用户多次反馈「每个格子右侧有奇怪的竖线 / 竖线断开了」——
    根因是逐单元格 border-right 只覆盖各自内容高度，行高不一就会一段段断开，
    再叠一层覆盖线又会变成双线。这里锁住：单元格自身无右边框，覆盖层按
    表头+表体总高画一条整线，且不拦截鼠标。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    theme = _read(ROOT / "theme-windows-xp.css")
    # 配装表启用覆盖层，且线高 = 表头 + 表体（不是逐行高度）
    assert "vlines: true," in js
    assert "var h = head.offsetHeight + body.offsetHeight;" in js
    assert 'line.style.height = h + "px";' in js
    # 单元格自身不得再有右边框（会与覆盖层叠成双线 / 断线）
    assert "html .loadout-workbench .tbl-row .tbl-cell {" in theme
    assert "border-right: 0 !important;" in theme
    # R19.67：XP 皮肤给每个单元格右缘贴的 tbl-grid-v.png border-image 才是
    # 「一格一段」断线的真凶（border-image-width 独立于 border-width），必须关掉
    assert "border-image: none !important;" in theme
    # 覆盖层样式存在：绝对定位、不拦截鼠标、1px 竖线
    assert ".loadout-workbench .tbl-vlines" in css
    assert "pointer-events: none;" in css
    assert ".loadout-workbench .tbl-vlines > i" in css


def test_other_workbench_tables_share_continuous_vlines():
    """R19.68：配枪 / 弹药表与配装表同源——XP 皮肤给每个单元格右缘贴 tbl-grid-v.png，
    每格一段、行间留缝。三个工作台必须用同一套修复：关贴图 + 关逐格边框 + 覆盖层画整条线。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    theme = _read(ROOT / "theme-windows-xp.css")
    # 配装表、插板弹窗、配枪表、弹药表共 4 处启用覆盖层
    assert js.count("vlines: true,") >= 4
    # 配枪 / 弹药单元格同样关掉贴图与逐格右边框
    assert "html .gun-workbench .tbl-row .tbl-cell," in theme
    assert "html .am-workbench .tbl-row .tbl-cell {" in theme
    assert theme.count("border-image: none !important;") >= 2
    # 覆盖层结构样式在三个工作台都成立
    assert ".gun-workbench .tbl-vlines" in css
    assert ".am-workbench .tbl-vlines" in css


def test_app_js_loadout_echo_self_guard():
    """第九轮问题2附带修复：自己 POST prefs 的短暂窗口内忽略回声里的配装快照。

    服务端收到 /api/prefs 会向所有页面广播 config（含发起页自身）；此外 serve.py 的
    ConfigWatcher 轮询线程（1s 周期）会在配置文件 mtime 变化后再广播一次同样内容，
    比直发回声晚最多约 1.05s。配装快照走「值不同就覆盖」，过期回声会把刚换上的
    装备回滚成旧装备（快速连续换装必现；2.5s 窗口覆盖 2 个轮询周期 + 余量）。
    """
    js = _read(APP_JS)
    assert "var SELF_ECHO_GRACE = 2500;" in js
    assert "lastOwnPrefPostAt = Date.now();" in js
    assert "Date.now() - lastOwnPrefPostAt >= SELF_ECHO_GRACE" in js


def test_app_js_table_columns_have_alignment_spec():
    """第八项：createTable 用同一套列级对齐（表头 / 数据行 / 空状态共用 cellClass）。"""
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    assert "function alignOf(col)" in js and "function cellClass(col)" in js
    # 表头与数据行都用 cellClass(col)，不再各自拼 "tbl-cell" + (col.num ? " tbl-num" : "")
    assert 'cell.className = cellClass(col);' in js
    assert '(col.num ? " tbl-num" : "")' not in js, "旧的内联对齐拼接残留"
    # 空数据行也走同一列模板与对齐
    assert 'empty.className = "tbl-row tbl-empty";' in js
    # 三种对齐在 CSS 里各有定义
    assert ".tbl-num { text-align: right;" in css
    assert ".tbl-mid { text-align: center; }" in css
    assert ".tbl-row.tbl-empty .tbl-cell { color:" in css


def test_zone_icon_mapping_uses_local_packaged_assets():
    """第七项：防护区域图标映射只能指向项目内可打包目录，且必须与 iconize.py 的输出名一一对应。

    这条测的就是「图标映射审计」：词集合键的规范化、37 张映射是否都登记在案、
    文件名与 iconize 的复制清单是否对得上、有没有混进绝对路径或远程地址。
    R31.2：图标改为手绘重做后按数据自动拼合（tools/gen_zone_torso_handraw.py 写入分区图），
    数据里出现过的每种组合必有图；缺图必须与 r11 审计 JSON 的 pending_user_icons
    完全一致（当前为空），不得有未登记的缺图。
    """
    js = _read(APP_JS)
    css = _read(STYLE_CSS)
    iconize = _read(ROOT / "tools" / "iconize.py")

    # 部位词的固定顺序（规范化词集合键的基础）
    k0 = js.index("var ZONE_WORD_ORDER = [")
    order = re.findall(r'"([^"]+)"', js[k0:js.index("];", k0)])

    # app.js 的映射表：词集合键 → assets/icons/zones/*.png
    i = js.index("var ZONE_ICON_BY_WORDS = {")
    block = js[i:js.index("};", i)]
    pairs = re.findall(r'"([^"]+)":\s*"(assets/icons/zones/([^"/]+)\.png)"', block)
    # R295：头部换成手绘新版（25 条）+ 躯干 13 条 = 38；只允许增加，不允许悄悄减少
    assert len(pairs) >= 37, "防护区域图标映射不应少于 37 张，实际 %d" % len(pairs)
    mapping = {key: (path, name) for key, path, name in pairs}

    for key in mapping:
        words = key.split("|")
        assert words == [w for w in order if w in words], "词集合键未按固定词序规范化：%s" % key

    # 运行期只读本地相对路径：不得出现开发机绝对路径，也不得出现任何远程地址
    for bad in ("D:", "d:", "http:", "https:", "//", "\\\\"):
        assert bad not in block, "图标映射里出现了不允许的路径/地址：%s" % bad

    # 映射里的图：已入库的必须真的在可打包目录；还没入库的必须与 r11 审计 JSON 的
    # pending_user_icons 清单**完全一致**（缺图必须登记补图任务，不得静默缺图）。
    audit_path = ROOT / "docs" / "r11-armor-grouping" / "protection-zone-audit.json"
    missing = sorted(Path(path).name for key, (path, name) in mapping.items() if not (ROOT / path).is_file())
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    pending = sorted(p["file"] for p in audit.get("pending_user_icons", []))
    assert missing == pending, "缺图 %s 与审计 pending 清单 %s 不一致" % (missing, pending)

    # iconize.py 的复制清单与 app.js 的映射表一一对应（同一套词表、同一批文件名）
    zj = iconize.index("ZONE_JOBS = [")
    jobs = re.findall(r'\("([^"]+)"\s*,\s*"([^"]+)\.png"\s*,\s*"([^"]+)\.png"\s*,\s*\[([^\]]*)\]\)',
                      iconize[zj:iconize.index("\n]", zj)])
    # R295：头部改由 tools/gen_zone_head_handraw.py 直出 assets（不再走 iconize 复制），
    # 这里只校验躯干段的复制任务仍与映射表一一对应。
    job_names = {j[2] for j in jobs}
    torso_names = sorted(n for _, n in mapping.values() if not n.startswith("zone-head-"))
    for dst_name in torso_names:
        assert dst_name in job_names, "iconize.ZONE_JOBS 缺少躯干图标：%s" % dst_name
    for src_dir, src_name, dst_name, raw_words in jobs:
        words = re.findall(r'"([^"]+)"', raw_words)
        key = "|".join(w for w in order if w in words)
        mapped = mapping.get(key)
        if mapped and mapped[1].startswith("zone-head-"):
            continue          # R295：该词集合已改由手绘脚本直出，旧复制任务退役
        # R295：旧头部把 Neck* 并入「脖颈」，这些键已随新版拆成喉部/后颈而退役
        if "脖颈" in key.split("|") and ({"头顶", "后脑", "面部", "下颚", "眼部", "耳部"} & set(key.split("|"))):
            continue
        assert key in mapping, "iconize 的 %s 词集合 %s 在 app.js 映射表里找不到" % (dst_name, key)
        assert mapped[1] == dst_name, "%s 的文件名对不上" % dst_name
        assert "防护" in src_dir, "源目录名应说明防护部位：%s" % src_dir

    # 接线：行数据带图标与「图上没有的部位」，列真的用 renderZoneCell，审计面板给出映射统计
    # R298：当前装备行用 rowZones（本体 + 已装配件合并），其它候选行仍是 rec.z
    assert "zoneIcon: zoneIconFile(rowZones)" in js
    assert "zoneUnmapped: zoneWordsUnmapped(rowZones)" in js
    assert "render: renderZoneCell }" in js
    assert "zoneIconAudit()" in js and "防护区域图标映射" in js
    # 新样式一律限定在 .loadout-workbench 内（铁律：不得用全局选择器影响地图视图）
    assert ".loadout-workbench .tbl-zone-ico {" in css
    assert ".loadout-workbench .tbl-zone-more {" in css


def test_index_html_has_workbench_skeleton():
    """工作台骨架必须是 `.loadout-workbench` 网格，且顶栏 / 左栏 / 主表三块 id 齐全。"""
    html = _read(INDEX_HTML)
    assert 'class="loadout-workbench"' in html
    assert 'id="loadout-view"' in html
    for needle in (
        'id="lw-save"', 'id="lw-load"', 'id="lw-search"',
        'id="lw-quoted"', 'id="lw-hint"',
        'id="lw-stats"', 'class="lw-board"', 'id="lw-figure"', 'id="lw-cost"',
        'id="lw-audit"', 'id="lw-audit-body"',
        'id="gear-clear"', 'id="gear-table"',
    ):
        assert needle in html, "工作台骨架缺 %s" % needle
    # R19.84：顶部分类标签行 / PRESET 按钮 / 价格区间输入已按 PS 稿撤除
    # R19.85：灵敏度补偿整块删除；两个预设入口移到视图工具条 #cb-loadout
    for gone in ('id="lw-cats"', 'id="lw-preset"', 'id="lw-min"', 'id="lw-max"',
                 'id="sens-input"', 'id="sens-out"'):
        assert gone not in html, "已撤除的元素残留：%s" % gone
    # 第三轮第二项：左下方独立的「减益合计」大面板已按要求删除，改为左上紧凑统计栏
    assert 'id="lw-penalties"' not in html, "旧的左下减益合计面板残留"
    assert "减益合计" not in html, "旧面板标题文案残留"
    # 本轮：左侧改为「槽位卡片板」，不再有独立的「装备槽位树」列表容器
    assert 'id="lw-tree"' not in html, "旧的装备槽位树容器残留"
    assert "装备槽位树" not in html, "旧槽位树标题残留"


def test_index_html_dropped_old_three_column_layout():
    """旧三栏（左装备卡 + 中统计面板 + 右八列表格）的 DOM 已撤掉，不再两套并存。"""
    html = _read(INDEX_HTML)
    for dead in ("view-3col", "gear-slots", "gear-summary", "gear-penalties"):
        assert dead not in html, "旧三栏残留 %s" % dead


def test_index_html_keeps_other_views_untouched():
    """地图视图 / 配枪视图的存在性不得被配装改造波及。"""
    html = _read(INDEX_HTML)
    assert 'id="map-view"' in html
    assert 'id="gun-view"' in html
    assert 'id="view-btn-map"' in html
    assert 'id="view-btn-loadout"' in html


def test_app_js_unloadout_legacy_symbols_removed():
    """旧的配装渲染函数/变量已删除，避免与工作台实现并存导致行为不确定。"""
    js = _read(APP_JS)
    for dead in ("renderGearSlots", "gearSlotSubText", "renderGearSummary",
                 "gearCatalog", "slotLabelOf", "dlAppend"):
        assert dead not in js, "旧配装符号残留：%s" % dead


def test_app_js_exposes_setcolumns_api():
    """`createTable` 返回对象必须带 setColumns / setSearch / setFilter / refreshSelection。"""
    js = _read(APP_JS)
    for name in ("setColumns", "setSearch", "setFilter", "refreshSelection"):
        assert (name + ": function") in js, "createTable 返回对象缺 %s" % name
    # 切列时先重建表头与列宽变量、再重渲当前数据
    assert 'scroll.style.setProperty("--tbl-cols"' in js
    assert ".tbl-sort" in js


def test_app_js_toolbar_switch_defaults_on():
    """`toolbar` 选项缺省为 true —— 地图视图等既有调用方行为不变。"""
    js = _read(APP_JS)
    assert "var useBar = opts.toolbar !== false;" in js
    assert 'if (opts.onRender) { opts.onRender({ total: rows.length }); }' in js


def test_app_js_loadout_tabs_follow_reference_site():
    """一级分类照参考站实际可见的 7 个，顺序固定；护甲板**不**另开一级标签。"""
    js = _read(APP_JS)
    start = js.index("var LOADOUT_TABS = [")
    end = js.index("];", start)
    block = js[start:end]
    keys = re.findall(r'key: "(\w+)"', block)
    assert keys == ["armor", "helmet", "headset", "backpack", "rigs", "eyewear", "facecover"]
    labels = re.findall(r'label: "([^"]+)"', block)
    assert labels == ["护甲", "头盔", "耳机", "背包", "胸挂", "眼镜", "护面"]
    # 护甲板并入 ARMOR：不得出现独立的 plates 一级分类
    assert '"plates"' not in js
    assert '"armorplates"' not in js.lower()


def test_price_modes_match_market_tiers():
    """价格口径统一到市场页：最新 / 24h 均价 / 7 日均价；旧 PVP/SCAV/FLEA/BASE 已删除。"""
    js = _read(APP_JS)
    for key, label in (("last", "最新"), ("avg24h", "24h 均价"), ("avg7d", "7 日均价")):
        assert 'key: "%s", label: "%s"' % (key, label) in js, "%s 档缺失" % label
    # 旧口径必须真正删除（不是隐藏入口）
    for old in ('key: "pvp"', 'key: "scav"', 'key: "base"', 'key: "flea"'):
        assert old not in js, "旧价格档 %s 仍残留" % old
    # 免费 / 会员门控复用现有 .is-member-locked
    assert "priceModeLocked" in js and "is-member-locked" in js, "缺少免费/会员价格档门控"
    # 构建期快照必须标注「非实时」
    assert "非实时" in js


def test_css_workbench_rules_are_scoped():
    """`.lw-*` 规则必须挂在工作台作用域下，不泄漏成全局选择器。

    第六轮新增配枪工作台（`.gun-workbench`）与两个工作台共用的弹窗作用域（`.lw-scope`），
    它们同样是工作台作用域，不是全局选择器。
    """
    css = _read(STYLE_CSS)
    scopes = (".loadout-workbench", ".gun-workbench", ".lw-scope")
    offenders = []
    for raw in css.splitlines():
        line = raw.strip()
        if not line.startswith("."):
            continue
        selector = line.split("{", 1)[0]
        if ".lw-" in selector and not any(s in selector for s in scopes):
            offenders.append(line)
    assert not offenders, "未加作用域的 .lw- 选择器：%s" % offenders


def test_css_keeps_horizontal_scroll_for_wide_tables():
    """列多时靠横向滚动，而不是把列压扁（min-width: max-content）。"""
    css = _read(STYLE_CSS)
    scoped = css[css.index(".loadout-workbench {"):]
    assert "min-width: max-content" in scoped
    # 左栏宽度收敛成可调 CSS 变量（本轮按参考图实测比例定，不再写死 400px）
    assert "grid-template-columns: var(--lw-side-w) minmax(0, 1fr)" in scoped


def test_css_left_width_is_a_scoped_variable():
    """左栏宽度是 `.loadout-workbench` 作用域内的 CSS 变量，且不污染地图/侧栏全局宽度。"""
    css = _read(STYLE_CSS)
    scoped = css[css.index(".loadout-workbench {"):]
    assert "--lw-side-w:" in scoped, "左栏宽度未收敛为 --lw-side-w 变量"
    assert "--lw-u:" in scoped, "参考图几何单位 --lw-u 缺失"
    # 变量只在配装工作台里定义，不得写进 :root 影响地图视图
    root = css[:css.index(".loadout-workbench {")]
    assert "--lw-side-w" not in root and "--lw-u" not in root


def test_index_html_has_nested_slot_tree_container():
    """子槽随父装备卡片所在行渲染（一个父装备一条 .lw-node-group），
    不再有「统一追加到底部」的容器，也没有独立的 #lw-tree 列表。"""
    html = _read(INDEX_HTML)
    js = _read(APP_JS)
    assert 'class="lw-board"' in html
    assert 'id="lw-tree"' not in html and "lw-tree" not in js, "旧的统一槽位树容器残留"
    # 卡片板在左栏里排在费用面板之前（Final Cost 在卡片板下方）
    assert html.index('class="lw-board"') < html.index('id="lw-cost"')
    for dead in ("lw-subslots", "lw-subgroup", "lw-subchips"):
        assert dead not in html, "旧的底部附件槽容器残留：%s" % dead


def test_app_js_board_renders_slot_cards_and_child_strips():
    """卡片板：按参考图几何的格子（LW_BOARD）渲染槽位卡片，紧跟它自己的子槽条。"""
    js = _read(APP_JS)
    assert "var LW_BOARD = [" in js
    assert "function slotCell(" in js
    # 空槽剪影 = 从用户参考图抠出的本地 PNG（不联网、不给图元加 CSS 动画 / transform）
    assert "var LW_SIL_FILE = {" in js
    assert "function silKey(" in js
    assert "function silImg(" in js
    # 上一轮那套自绘 SVG 剪影（LW_BANDS/LW_SIL/silSvg）已按用户要求删除，不得回潮
    assert "var LW_BANDS = [" not in js and "var LW_SIL = {" not in js and "function silSvg(" not in js
    # 卡片是槽位入口：点一下 = selectSlot，且带 data-slot / data-state
    assert "btn.dataset.slot = key" in js
    assert 'btn.className = "lw-cell"' in js
    assert "selectSlot(key)" in js
    # R299 修订：PSD 512×512 是绝对坐标画布，只给头盔保留 5 个环绕配件槽；
    # 其它装备的子槽条不再插进画布（否则会把 PSD 固定位置挤乱）。
    assert 'if (spec.cell === "helmet")' in js
    assert 'row.className = "lw-side-row";' in js
    assert 'renderGearTree(key, kids, tree, "side")' in js
    assert "var strip = renderGearTree(key, kids, tree);" not in js
    # 第五轮第六项：护甲板位不再当左侧子槽渲染，改到右表四个板位列 + 弹窗
    # 第七轮第 6 项：固定内衬同样不再当独立子卡片渲染（属性只在右侧装备信息里展示）
    assert 'if (kn && (kn.kind === "plate" || kn.kind === "liner")) { return; }' in js
    assert "function openPlatePicker(" in js and "function paintPlatePicker(" in js
    assert "el.lwFigure.appendChild(box);" in js
    # 枪械类槽位不再打「待接入」徽章（用户要求去掉）
    assert "lw-cell-pending" not in js and "lw-node-pending" not in js
    css = _read(STYLE_CSS)
    for cls in (".lw-board", ".lw-cellbox", ".lw-cell {", ".lw-sil {", ".lw-cellbox[data-cell="):
        assert ".loadout-workbench " + cls in css, "卡片板样式缺 %s" % cls
    assert ".lw-band " not in css, "旧的 .lw-band 行样式残留"
    assert '[data-state="pending"]' not in css, "已删的「待接入」徽章样式残留"


def test_app_js_renders_child_slots_inline_under_parent():
    """子槽必须紧跟父装备：renderGearTree 按父装备渲染一条子槽条，appendNodeRows 递归按 depth 缩进。"""
    js = _read(APP_JS)
    assert "function renderGearTree(" in js
    assert "function appendNodeRows(" in js
    # 递归渲染子节点（不是把所有子槽拼成一个平铺列表）
    assert "appendNodeRows(host, tree, id, depth + 1)" in js or \
           "appendNodeRows(" in js.split("function appendNodeRows(")[1]
    # 每个根槽位一个独立分组容器，子槽在其内部缩进
    assert "lw-node-group" in js and "lw-node-kids" in js
    assert "lw-node-group" in _read(STYLE_CSS) and "lw-node-kids" in _read(STYLE_CSS)


def test_app_js_liner_is_fixed_component():
    """固定内衬：childDefs 标 fixed/removable，candidatesOf 直接返回空，equipItem 不放行。"""
    js = _read(APP_JS)
    assert 'fixed: true, removable: false' in js
    assert 'kind: "liner"' in js
    # liner 不是可装槽位：候选为空、装备入口被挡、选中回退到父装备
    assert 'if (node.kind === "liner") { return out; }' in js
    # 第七轮第 6 项：固定内衬不再渲染成左侧独立子卡片（追加子槽时直接跳过）
    assert 'if (!node || node.kind === "liner") { return; }' in js
    assert 'tnode.kind === "liner" && tnode.parent' in js
    # 固定内衬的来源说明不得再写「数据缺失」
    assert "不可单独拆卸 / 更换（候选为空是设计如此，不是数据缺失）" in js


def test_app_js_create_table_is_resizable():
    """列宽拖动扩展现有 createTable（不重新实现第二个大表组件）。"""
    js = _read(APP_JS)
    assert "var MIN_COL_W = 56, MAX_COL_W = 520;" in js
    for name in ("clampW", "pxOf", "colCss", "appendGrip", "startResize"):
        assert ("function " + name + "(") in js, "列宽能力缺 %s" % name
    # 拖动挂在表头单元格右缘的拖柄上，尺寸变更写回 opts.onResize
    assert "if (opts.resizable) { appendGrip(cell, col); }" in js
    assert "if (opts.onResize) { opts.onResize(col, w); }" in js
    # 只有配装工作台打开 resizable，地图视图的既有调用方行为不变
    assert "resizable: true," in js
    assert ".tbl-grip" in _read(STYLE_CSS)


def test_app_js_col_width_persisted_per_category():
    """列宽按槽位类别持久化：localStorage 即时 + 配置文件 ui.colw 防抖落盘。"""
    js = _read(APP_JS)
    assert 'var LS_COLW = "eftmap.colw";' in js
    assert "colWidths: { byCat: {}, shared: {} }" in js
    for name in ("colwNorm", "loadColWidths", "colCatKey", "colWidthFor", "saveColWidth"):
        assert ("function " + name + "(") in js, "列宽持久化缺 %s" % name
    assert "colw: state.colWidths" in js          # 纳入 uiPatch()，随偏好整块落盘
    assert "loadColWidths();" in js               # restorePrefs 里恢复


def test_config_py_normalizes_colw():
    """后端要有与前端一致的列宽钳制与结构收敛（重启后从配置文件恢复）。"""
    cfg = _read(ROOT / "tools" / "config.py")
    assert "COL_W_MIN = 56" in cfg and "COL_W_MAX = 520" in cfg
    assert "def clamp_col_w(" in cfg and "def normalize_colw(" in cfg
    assert '"colw" in raw' in cfg
    assert '"colw"' in cfg


# ---------------------------------------------------------------- 2. 动态切列
DOM_HARNESS_JS = r"""
"use strict";
var fs = require("fs");
var appPath = process.argv[2];
var src = fs.readFileSync(appPath, "utf8");

/* 从 app.js 里抠出 function createTable(...) {...} 整段（按花括号配平，跳过字符串与注释） */
function extractFn(source, name) {
  var i = source.indexOf("function " + name + "(");
  if (i < 0) { throw new Error("找不到函数 " + name); }
  var start = source.indexOf("{", i);
  var depth = 0;
  for (var k = start; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) {
        if (source[k] === "\\") { k++; }
        k++;
      }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return source.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}

/* —— 极简 DOM 垫片：只实现 createTable 用到的那点东西 —— */
function Node(tag) {
  this.tag = tag;
  this._className = "";
  this._text = "";
  this.children = [];
  this.attrs = {};
  this.dataset = {};
  this.listeners = {};
  this.parentNode = null;
  this.value = "";
  this.type = "";
  this.placeholder = "";
  this.scrollTop = 0;
  this.clientHeight = 0;
  this.scrollHeight = 0;
  var props = {};
  this.style = {
    setProperty: function (k, v) { props[k] = v; },
    get: function (k) { return props[k]; }
  };
}
Object.defineProperty(Node.prototype, "className", {
  get: function () { return this._className; },
  set: function (v) { this._className = v == null ? "" : String(v); }
});
function defText(prop) {
  Object.defineProperty(Node.prototype, prop, {
    get: function () { return this._text; },
    set: function (v) { this._text = v == null ? "" : String(v); this.children = []; }
  });
}
defText("textContent");
defText("innerHTML");
Node.prototype.appendChild = function (child) {
  child.parentNode = this;
  this.children.push(child);
  return child;
};
Node.prototype.removeChild = function (child) {
  var i = this.children.indexOf(child);
  if (i >= 0) { this.children.splice(i, 1); }
  child.parentNode = null;
  return child;
};
Node.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Node.prototype.getAttribute = function (k) { return this.attrs[k]; };
Node.prototype.addEventListener = function (type, fn) {
  (this.listeners[type] = this.listeners[type] || []).push(fn);
};
Node.prototype.fire = function (type, ev) {
  var fns = this.listeners[type] || [];
  for (var i = 0; i < fns.length; i++) { fns[i].call(this, ev || {}); }
};
/* 列宽拖动用：宽度由 getBoundingClientRect().width 取（垫片里由测试自己塞 rectWidth） */
Node.prototype.getBoundingClientRect = function () {
  return { width: this.rectWidth || 0, height: 0, left: 0, top: 0 };
};
Node.prototype.querySelectorAll = function (sel) {
  var tokens = sel.split(".").filter(function (s) { return s.length > 0; });
  var out = [];
  var walk = function (n) {
    for (var i = 0; i < n.children.length; i++) {
      var c = n.children[i];
      var cls = (c._className || "").split(/\s+/);
      var ok = true;
      for (var j = 0; j < tokens.length; j++) { if (cls.indexOf(tokens[j]) < 0) { ok = false; break; } }
      if (ok) { out.push(c); }
      walk(c);
    }
  };
  walk(this);
  return out;
};
Node.prototype.querySelector = function (sel) {
  var list = this.querySelectorAll(sel);
  return list.length ? list[0] : null;
};
/* document 级监听：列宽拖动把 mousemove / mouseup 挂在 document 上（测试用它模拟拖拽） */
var docListeners = {};
var document = {
  createElement: function (tag) { return new Node(tag); },
  addEventListener: function (type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
  removeEventListener: function (type, fn) {
    var list = docListeners[type] || [];
    var i = list.indexOf(fn);
    if (i >= 0) { list.splice(i, 1); }
  }
};
function docFire(type, ev) {
  var list = (docListeners[type] || []).slice();
  for (var i = 0; i < list.length; i++) { list[i].call(document, ev || {}); }
}

var createTable = new Function("document", "TBL_PAGE",
  extractFn(src, "createTable") + "\nreturn createTable;")(document, 200);

/* —— 断言工具 —— */
var checks = 0;
var failures = [];
function check(name, cond) { checks++; if (!cond) { failures.push(name); } }

function scrollOf(root) { return root.querySelectorAll(".tbl-scroll")[0] || null; }
function headOf(root) { var s = scrollOf(root); return s ? s.children[0] : null; }
function bodyOf(root) { var s = scrollOf(root); return s ? s.children[1] : null; }
function headCells(root) { return headOf(root).querySelectorAll(".tbl-cell"); }
function headKeys(root) { return headCells(root).map(function (c) { return c.dataset.key; }); }
function headLabels(root) { return headCells(root).map(function (c) { return c._text; }); }
function rowCount(root) { return bodyOf(root).querySelectorAll(".tbl-row").length; }
function rowTexts(root, i) {
  var rows = bodyOf(root).querySelectorAll(".tbl-row");
  return rows[i] ? rows[i].children.map(function (c) { return c._text; }) : null;
}
function sortMark(root, i) {
  var m = headCells(root)[i].querySelector(".tbl-sort");
  return m ? m._text : null;
}
function colsVar(root) { return scrollOf(root).style.get("--tbl-cols"); }

/* T1 默认行为（向后兼容） */
var host1 = document.createElement("div");
var t1 = createTable(host1, {
  columns: [{ key: "a", label: "A", width: "1fr" }, { key: "b", label: "B", width: "1fr" }],
  rows: [{ __id: "r1", a: 1, b: 2 }, { __id: "r2", a: 3, b: 4 }]
});
var root1 = host1.children[0];
check("T1 根节点渲染", root1 && root1._className.indexOf("tbl") >= 0);
check("T1 默认带工具条", root1.querySelectorAll(".tbl-toolbar").length === 1);
check("T1 表头列序不变", headKeys(root1).join(",") === "a,b");
check("T1 数据两行", rowCount(root1) === 2);
check("T1 计数文案", root1.querySelectorAll(".tbl-count")[0]._text === "2 条");
check("T1 列宽变量", colsVar(root1) === "1fr 1fr");
check("T1 返回对象 API 齐全",
  typeof t1.setColumns === "function" && typeof t1.setSearch === "function" &&
  typeof t1.setFilter === "function" && typeof t1.refreshSelection === "function" &&
  typeof t1.render === "function" && typeof t1.setRows === "function");

/* T2 toolbar:false（配装工作台用）：不建工具条，且 setSearch 不炸（回归：曾空指针） */
var host2 = document.createElement("div");
var t2 = createTable(host2, {
  columns: [{ key: "n", label: "名称" }],
  rows: [{ __id: "x", n: "hello" }],
  toolbar: false
});
var root2 = host2.children[0];
check("T2 无工具条", root2.querySelectorAll(".tbl-toolbar").length === 0);
check("T2 setSearch 不抛异常", (function () {
  try { t2.setSearch("he"); t2.setSearch(""); return true; } catch (e) { return false; }
})());
check("T2 setFilter 不抛异常", (function () {
  try { t2.setFilter("z"); t2.setFilter(""); return true; } catch (e) { return false; }
})());

/* T3 setColumns：表头 / 数据 / 列宽一起换 */
var host3 = document.createElement("div");
var t3 = createTable(host3, {
  columns: [{ key: "a", label: "A", width: "1fr" }, { key: "b", label: "B", width: "1fr" }],
  rows: [
    { __id: "r1", a: 1, b: 2, n: "阿尔法", w: 5.5 },
    { __id: "r2", a: 3, b: 4, n: "贝塔", w: 7 }
  ],
  toolbar: false
});
var root3 = host3.children[0];
t3.setColumns([{ key: "n", label: "名称", width: "2fr" }, { key: "w", label: "重量", width: "1fr", num: true }]);
check("T3 表头换成新列", headLabels(root3).join("/") === "名称/重量");
check("T3 表头 key 同步", headKeys(root3).join(",") === "n,w");
check("T3 数据按新列渲染", (rowTexts(root3, 0) || []).join("|") === "阿尔法|5.5");
check("T3 列宽变量跟着换", colsVar(root3) === "2fr 1fr");

/* T4 排序列不在新列集 → 回落第一列（升序） */
var host4 = document.createElement("div");
var t4 = createTable(host4, {
  columns: [{ key: "a", label: "A" }, { key: "b", label: "B", num: true }],
  rows: [{ __id: "r1", a: "z", b: 1, n: "x" }],
  toolbar: false
});
var root4 = host4.children[0];
headCells(root4)[1].fire("click");
check("T4 点表头有排序标记", sortMark(root4, 1) === "▼");
t4.setColumns([{ key: "n", label: "名称" }, { key: "a", label: "A" }]);
check("T4 换列后回落第一列升序", sortMark(root4, 0) === "▲");
check("T4 旧排序列已无标记", sortMark(root4, 1) === "");

/* T5 搜索跨切列保留 */
var host5 = document.createElement("div");
var t5 = createTable(host5, {
  columns: [{ key: "n", label: "名称" }],
  rows: [{ __id: "r1", n: "alpha" }, { __id: "r2", n: "beta" }],
  toolbar: false, searchKeys: ["n"]
});
var root5 = host5.children[0];
t5.setSearch("alp");
check("T5 搜索生效", rowCount(root5) === 1);
t5.setColumns([{ key: "n", label: "名称" }, { key: "w", label: "重量", num: true }]);
check("T5 换列后搜索仍生效", rowCount(root5) === 1);
t5.setSearch("");
check("T5 清空搜索后恢复", rowCount(root5) === 2);

/* T6 过滤跨切列保留 */
var host6 = document.createElement("div");
var t6 = createTable(host6, {
  columns: [{ key: "n", label: "名称" }],
  rows: [{ __id: "r1", n: "a", g: "x" }, { __id: "r2", n: "b", g: "y" }],
  toolbar: false,
  filter: { value: function (row) { return row.g; } }
});
var root6 = host6.children[0];
t6.setFilter("y");
check("T6 过滤生效", rowCount(root6) === 1);
t6.setColumns([{ key: "n", label: "名称" }, { key: "g", label: "组" }]);
check("T6 换列后过滤仍生效", rowCount(root6) === 1);

/* T7 选中态跨切列保留 */
var host7 = document.createElement("div");
var t7 = createTable(host7, {
  columns: [{ key: "n", label: "名称" }],
  rows: [{ __id: "r1", n: "a" }, { __id: "r2", n: "b" }],
  toolbar: false,
  rowSelected: function (row) { return row.__id === "r1"; }
});
var root7 = host7.children[0];
check("T7 初始选中态", bodyOf(root7).querySelectorAll(".tbl-row")[0].getAttribute("aria-selected") === "true");
t7.setColumns([{ key: "n", label: "名称" }, { key: "w", label: "重量" }]);
check("T7 换列后选中态保留", bodyOf(root7).querySelectorAll(".tbl-row")[0].getAttribute("aria-selected") === "true");

/* T8 切列不重建滚动容器（横向滚动位置因此保留） */
var host8 = document.createElement("div");
var t8 = createTable(host8, {
  columns: [{ key: "a", label: "A" }, { key: "b", label: "B" }],
  rows: [{ __id: "r1", a: 1, b: 2, n: "x" }],
  toolbar: false
});
var root8 = host8.children[0];
var sc8 = scrollOf(root8);
sc8.scrollTop = 123;
t8.setColumns([{ key: "n", label: "名称" }]);
check("T8 滚动容器未被替换", scrollOf(root8) === sc8);
check("T8 scrollTop 保持", scrollOf(root8).scrollTop === 123);

/* T9 refreshSelection 只刷选中态、不重建行节点 */
var host9 = document.createElement("div");
var on9 = { on: false };
var t9 = createTable(host9, {
  columns: [{ key: "n", label: "名称" }],
  rows: [{ __id: "r1", n: "a" }],
  toolbar: false,
  rowSelected: function () { return on9.on; }
});
var root9 = host9.children[0];
var before9 = bodyOf(root9).querySelectorAll(".tbl-row")[0];
on9.on = true;
t9.refreshSelection();
var after9 = bodyOf(root9).querySelectorAll(".tbl-row")[0];
check("T9 复用同一行节点", before9 === after9);
check("T9 选中态已更新", after9.getAttribute("aria-selected") === "true");

/* T10 onRender 回调：首次渲染 / setRows / setColumns 都触发 */
var seen = [];
var host10 = document.createElement("div");
var t10 = createTable(host10, {
  columns: [{ key: "n", label: "N" }],
  rows: [{ n: "a" }],
  toolbar: false,
  onRender: function (info) { seen.push(info.total); }
});
check("T10 首次回调", seen.length === 1 && seen[0] === 1);
t10.setRows([{ n: "a" }, { n: "b" }]);
check("T10 setRows 后再回调", seen.length === 2 && seen[1] === 2);
t10.setColumns([{ key: "n", label: "N" }, { key: "w", label: "W" }]);
check("T10 setColumns 也回调", seen.length === 3 && seen[2] === 2);

/* T11 分页：首帧一页，滚到底追加 */
var many = [];
for (var i = 0; i < 250; i++) { many.push({ __id: "r" + i, n: "n" + i }); }
var host11 = document.createElement("div");
var t11 = createTable(host11, { columns: [{ key: "n", label: "N" }], rows: many, toolbar: false });
var root11 = host11.children[0];
check("T11 首帧只渲染一页", rowCount(root11) === 200);
var sc11 = scrollOf(root11);
sc11.scrollTop = 500; sc11.clientHeight = 100; sc11.scrollHeight = 600;
sc11.fire("scroll");
check("T11 滚到底追加剩余", rowCount(root11) === 250);

/* R1 拖动表头右缘改列宽：拖拽 → 宽度变量变 → onResize 回调 → mouseup 后停 */
var resizedR1 = [];
var hostR1 = document.createElement("div");
var tR1 = createTable(hostR1, {
  columns: [{ key: "a", label: "A", min: 60, max: 300 }, { key: "b", label: "B" }],
  rows: [{ __id: "r1", a: 1, b: 2 }],
  toolbar: false, resizable: true,
  onResize: function (col, px) { resizedR1.push(col.key + ":" + px); }
});
var rootR1 = hostR1.children[0];
var cellA = headCells(rootR1)[0];
check("R1 可拖动时表头带拖柄", cellA.querySelectorAll(".tbl-grip").length === 1);
check("R1 不可拖动时（T1）表头无拖柄", headCells(root1)[0].querySelectorAll(".tbl-grip").length === 0);
cellA.rectWidth = 100;
cellA.querySelector(".tbl-grip").fire("mousedown", { clientX: 500 });
docFire("mousemove", { clientX: 560 });
check("R1 拖 60px → 列宽变量从 100 变 160", colsVar(rootR1).indexOf("160px") === 0);
check("R1 onResize 回调带列 key 与实际像素", resizedR1.join(",") === "a:160");
check("R1 数据行仍是两列一格", (rowTexts(rootR1, 0) || []).join("|") === "1|2");
docFire("mouseup", {});
docFire("mousemove", { clientX: 900 });
check("R1 mouseup 之后不再继续改宽", colsVar(rootR1).indexOf("160px") === 0);
/* 上限：拖到远超 max 也只到 max（避免无限撑宽） */
cellA.querySelector(".tbl-grip").fire("mousedown", { clientX: 0 });
docFire("mousemove", { clientX: 5000 });
check("R1 超过 max 被钳到 300", colsVar(rootR1).indexOf("300px") === 0);
docFire("mouseup", {});

/* R2 widthFor：外部（持久化）宽度优先于列自带 width */
var hostR2 = document.createElement("div");
var tR2 = createTable(hostR2, {
  columns: [{ key: "a", label: "A" }, { key: "b", label: "B" }],
  rows: [{ __id: "r1", a: 1, b: 2 }],
  toolbar: false,
  widthFor: function (col) { return col.key === "a" ? 210 : null; }
});
check("R2 持久化宽度接管（a=210px，b 回落 1fr）", colsVar(hostR2.children[0]) === "210px 1fr");

/* R3 切列：本地拖动值被清掉，改由 widthFor 从持久化取（同名同义列复用） */
tR1.setColumns([{ key: "a", label: "A", min: 60, max: 300 }, { key: "b", label: "B" }]);
check("R3 切列后本地拖动值被清（不再沿用 300px）", colsVar(rootR1).indexOf("300px") < 0);

/* R4 切列后同名同义列的持久化宽度被复用（切列不丢用户设定的宽度） */
var persistW = { a: 180 };
var hostR4 = document.createElement("div");
var tR4 = createTable(hostR4, {
  columns: [{ key: "a", label: "A" }, { key: "b", label: "B" }],
  rows: [{ __id: "r1", a: 1, b: 2 }],
  toolbar: false,
  widthFor: function (col) { return persistW[col.key] || null; }
});
var rootR4 = hostR4.children[0];
check("R4 初始持久化宽度注入", colsVar(rootR4) === "180px 1fr");
persistW.b = 90;
tR4.setColumns([{ key: "b", label: "B" }, { key: "a", label: "A" }]);
check("R4 切列（换顺序 + 加宽另一列）后同名同义列各自复用宽度",
  colsVar(rootR4) === "90px 180px");
check("R4 切列后表头与宽度变量列序一致",
  headKeys(rootR4).join(",") === "b,a" && colsVar(rootR4).split(" ").length === 2);

/* R5 拖动改宽不影响搜索 / 排序 / 分页 / 选中态 */
var hostR5 = document.createElement("div");
var tR5 = createTable(hostR5, {
  columns: [{ key: "n", label: "名称", min: 60, max: 300 }],
  rows: [{ __id: "r1", n: "alpha" }, { __id: "r2", n: "beta" }],
  toolbar: false, resizable: true, searchKeys: ["n"],
  rowSelected: function (row) { return row.__id === "r2"; }
});
var rootR5 = hostR5.children[0];
tR5.setSearch("a");
check("R5 搜索先于拖动生效", rowCount(rootR5) === 2);   // alpha / beta 都含 a
var cellR5 = headCells(rootR5)[0];
cellR5.rectWidth = 120;
cellR5.querySelector(".tbl-grip").fire("mousedown", { clientX: 0 });
docFire("mousemove", { clientX: 40 });
docFire("mouseup", {});
check("R5 拖动后宽度已变", colsVar(rootR5).indexOf("160px") === 0);
check("R5 拖动后搜索结果仍正确", rowCount(rootR5) === 2);
check("R5 拖动后选中态仍正确",
  bodyOf(rootR5).querySelectorAll(".tbl-row")[1].getAttribute("aria-selected") === "true");
tR5.setSearch("beta");
check("R5 拖动后搜索仍可继续过滤", rowCount(rootR5) === 1);

/* T12 列级对齐规范（第八项）：文字左 / 数值右 / 图标可居中；表头、数据行、空状态三者一致 */
var host12 = document.createElement("div");
var t12 = createTable(host12, {
  columns: [
    { key: "n", label: "名称", align: "left" },
    { key: "w", label: "重量", num: true },
    { key: "ic", label: "图标", align: "center" }
  ],
  rows: [{ __id: "r1", n: "alpha", w: 5.5, ic: "" }],
  toolbar: false
});
var root12 = host12.children[0];
var hc12 = headCells(root12);
check("T12 文字列表头左对齐（无 tbl-num / tbl-mid）",
  hc12[0]._className.indexOf("tbl-num") < 0 && hc12[0]._className.indexOf("tbl-mid") < 0);
check("T12 数值列表头右对齐", hc12[1]._className.indexOf("tbl-num") >= 0);
check("T12 图标列表头居中", hc12[2]._className.indexOf("tbl-mid") >= 0);
var dc12 = bodyOf(root12).querySelectorAll(".tbl-row")[0].children;
check("T12 数据行逐列对齐与表头完全一致",
  dc12[0]._className.indexOf("tbl-num") < 0 && dc12[0]._className.indexOf("tbl-mid") < 0 &&
  dc12[1]._className.indexOf("tbl-num") >= 0 && dc12[2]._className.indexOf("tbl-mid") >= 0);
check("T12 数据行单元格带 data-key（与表头同键）",
  dc12[0].dataset.key === "n" && dc12[1].dataset.key === "w" && dc12[2].dataset.key === "ic");
/* 空状态：与表头同一列模板、同一对齐（第一列文字承载提示，数值列仍右对齐） */
t12.setRows([]);
var empty12 = bodyOf(root12).querySelectorAll(".tbl-row")[0];
check("T12 空状态是一行且列数与列集一致",
  !!empty12 && empty12._className.indexOf("tbl-empty") >= 0 && empty12.children.length === 3);
check("T12 空状态第一列承载提示且左对齐",
  empty12.children[0]._text === "没有匹配的条目" &&
  empty12.children[0]._className.indexOf("tbl-num") < 0 &&
  empty12.children[0]._className.indexOf("tbl-mid") < 0);
check("T12 空状态数值列仍右对齐", empty12.children[1]._className.indexOf("tbl-num") >= 0);
check("T12 空状态居中列仍居中", empty12.children[2]._className.indexOf("tbl-mid") >= 0);
/* 动态切列后，对齐随新列集自动生效 */
t12.setColumns([{ key: "w", label: "重量", num: true }, { key: "n", label: "名称" }]);
check("T12 切列后表头对齐随新列集",
  headCells(root12)[0]._className.indexOf("tbl-num") >= 0 &&
  headCells(root12)[1]._className.indexOf("tbl-num") < 0);

/* T13 第七轮 5.6：forceLeft = 连数值列也左对齐（配装表 / 插板窗专用，其它表行为不变） */
var host13 = document.createElement("div");
var t13 = createTable(host13, {
  columns: [{ key: "n", label: "名称", align: "left" }, { key: "w", label: "重量", num: true }],
  rows: [{ __id: "r1", n: "alpha", w: 5.5 }],
  toolbar: false, forceLeft: true
});
var root13 = host13.children[0];
check("T13 forceLeft：数值列表头不挂 tbl-num（左对齐）",
  headCells(root13)[1]._className.indexOf("tbl-num") < 0);
check("T13 forceLeft：数值数据行同样左对齐",
  bodyOf(root13).querySelectorAll(".tbl-row")[0].children[1]._className.indexOf("tbl-num") < 0);
t13.setRows([]);
check("T13 forceLeft：空状态数值列仍左对齐",
  bodyOf(root13).querySelectorAll(".tbl-row")[0].children[1]._className.indexOf("tbl-num") < 0);

if (failures.length) {
  console.error("FAIL (" + failures.length + "/" + checks + "):\n" + failures.join("\n"));
  process.exit(1);
}
console.log("OK " + checks + " checks passed");
"""


# ---------------------------------------------------------------- 3. 槽位驱动模型
def test_app_js_slot_driven_model_replaces_tab_state():
    """交互模型必须是「槽位驱动」：不得残留任何「当前分类 Tab」状态。"""
    js = _read(APP_JS)
    for dead in (
        r"state\.gearTab\b",      # 词边界：别把 state.gearTable 误判成残留
        r"setLwTab\b", r"currentTab\b", r"tabOf\b", r"onFocusSlot\b",
    ):
        assert not re.search(dead, js), "旧的 Tab 驱动状态残留：%s（点槽位不得反向去切顶部 Tab）" % dead
    for live in ("function selectSlot(", "function buildSlotTree(", "function renderGearTree(",
                 "function appendNodeRows(", "function commitLoadoutChange(",
                 "function candidatesOf(", "function conflictsOf("):
        assert live in js, "槽位驱动模型缺 %s" % live
    # 第一轮的「全部附件槽统一堆到左侧面板底部」已移除
    assert "renderGearSubSlots" not in js, "旧的底部附件槽容器函数残留"
    assert "lw-subslots" not in js and "lw-subslots" not in _read(INDEX_HTML)
    # 顶部 Tab 只是辅助入口：点它等于选中左侧同名槽位
    assert "selectSlot(tab.slot)" in js
    # 第一轮的护面近似规则（referencedIds / hasAnyType / isFaceCoverApprox）已删除
    for gone in ("function referencedIds(", "function hasAnyType(", "function isFaceCoverApprox("):
        assert gone not in js, "近似分类规则残留：%s（护甲板会因此混进 FACE COVER）" % gone
    # 冲突行是业务状态（rowClass 读 row.conflict / row.blocked），不是写死某几行的 CSS
    assert 'return row.conflict ? (row.blocked ? "tbl-conflict tbl-locked" : "tbl-conflict") : "";' in js
    assert "rowClass: function (row) {" in js
    assert "tbl-conflict" in _read(STYLE_CSS)
    assert "tbl-locked" in _read(STYLE_CSS)


SLOT_MODEL_JS = r"""
"use strict";
var fs = require("fs");
var src = fs.readFileSync(process.argv[2], "utf8");

/* 按花括号配平抠出 function name(...) {...} 整段（跳过字符串与注释） */
function extractFn(source, name) {
  var i = source.indexOf("function " + name + "(");
  if (i < 0) { throw new Error("找不到函数 " + name); }
  var start = source.indexOf("{", i);
  var depth = 0;
  for (var k = start; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return source.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}

/* 抠出 var name = ...; 这条语句（用括号/方括号/花括号配平找结尾分号） */
function extractVar(source, name) {
  var i = source.indexOf("var " + name + " =");
  if (i < 0) { throw new Error("找不到 var " + name); }
  var depth = 0;
  for (var k = source.indexOf("=", i) + 1; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "[" || c === "{" || c === "(") { depth++; }
    else if (c === "]" || c === "}" || c === ")") { depth--; }
    else if (c === ";" && depth === 0) { return source.slice(i, k + 1); }
  }
  throw new Error("找不到 " + name + " 的结尾分号");
}

/* 夹具：只用真实的字段形状（cat = 构建期一级类别；slots[].allow；aps[].plates / aps[].fx；conflict） */
var ITEMS = {
  "helmetA": { n: "头盔A", cat: "helmet", ts: ["helmet", "wearable"], pt: "Helmet", w: 3, p: { a: 1000 },
    conflict: ["hp1"], src: ["flea", "trader"],
    slots: [{ id: "nvg", sid: "mod_nvg", label: "支架", allow: ["nvg1"] },
            { id: "mount", sid: "mod_mount", label: "基座", allow: ["mount1"] }] },
  "helmetB": { n: "头盔B", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2, p: { a: 900 },
    mat: "Ceramic", cl: 3, dur: 30,
    aps: [{ zone: "Helmet_top", fx: 1, mat: "Ceramic", cl: 3, dur: 30, z: ["ParietalHead"] }] },
  "helmetPlain": { n: "素头盔", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 1, p: { a: 800 },
    src: ["none"] },
  "helmetC": { n: "头盔C", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2.5, p: { a: 950 },
    slots: [{ id: "mount", sid: "mod_mount", label: "基座", allow: ["mount1"] }] },
  "helmetD": { n: "头盔D", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2.6, p: { a: 960 },
    slots: [{ id: "mount", sid: "mod_mount", label: "基座", allow: ["mount2"] }] },
  "helmetF": { n: "头盔F", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2.7, p: { a: 970 },
    slots: [{ id: "eq", sid: "mod_equipment", label: "装备", allow: ["maskRef"] }] },
  "helmetG": { n: "头盔G", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2.8, p: { a: 980 },
    slots: [{ id: "eq", sid: "mod_equipment", label: "装备", cats: ["mod_equipment"] }] },
  "nvg1": { n: "夜视仪1", ts: ["mods"], pt: "NightVision", w: 0.5, p: { a: 200 } },
  "mount1": { n: "安装座1", ts: ["mods"], pt: "WeaponMod", w: 0.1, p: { a: 50 } },
  "mount2": { n: "安装座2", ts: ["mods"], pt: "WeaponMod", w: 0.2, p: { a: 60 } },
  "maskRef": { n: "被引用面罩", ts: ["wearable"], pt: "ArmorAttachment", w: 1, p: { a: 260 } },
  "faceMask": { n: "独立面罩", cat: "face", ts: ["wearable"], pt: "ArmorAttachment", w: 1.1, p: { a: 250 } },
  "hp1": { n: "耳机1", cat: "headphones", ts: ["headphones"], pt: "Headphone", w: 0.3, conflict: ["helmetA"], p: { a: 100 } },
  "hp2": { n: "耳机2", cat: "headphones", ts: ["headphones"], pt: "Headphone", w: 0.3, p: { a: 120 } },
  "glasses1": { n: "眼镜1", cat: "glasses", ts: ["glasses"], pt: "Glasses", w: 0.1, p: { a: 40 },
    pen: { t: -1, s: -2 } },
  "armorA": { n: "护甲A", cat: "armor", slot: "armor", ts: ["armor"], pt: "Armor", w: 8, cl: 4, dur: 60, mat: "UHMWPE",
    z: ["RibcageUp", "RibcageLow", "SpineTop"], p: { a: 5000 },
    aps: [{ zone: "Front_plate", plates: ["plateS", "plateM"], z: ["RibcageUp"] },
          { zone: "Back_plate", plates: ["plateM"], z: ["RibcageLow", "SpineTop"] }] },
  "armorPlain": { n: "素护甲", cat: "armor", slot: "armor", ts: ["armor"], pt: "Armor", w: 7, cl: 3, dur: 50, mat: "Aramid", p: { a: 4000 },
    aps: [{ zone: "Soft_armor_front", fx: 1, mat: "Aramid", cl: 2, dur: 40, z: ["RibcageUp"] }] },
  /* 「分类错配」反向样本：构建期按 types 优先级把它归成 cat=rig，但它真实 slot=armor
     → 只属于防弹衣槽、不得出现在胸挂槽候选里（证明判定肯认 slot、不认 cat） */
  "armorMisCat": { n: "错类护甲", cat: "rig", slot: "armor", ts: ["armor"], pt: "Armor", w: 8, cl: 4, dur: 60,
    p: { a: 5100 },
    /* 第十轮 T30：src 缺省但逐笔 trade 有确认兑换（模拟 6B43 型「src 与 barters 矛盾」数据）——
       行的 srcKind 必须以确认渠道为准（ok），不得误标「不可获得」。 */
    trade: [{ k: "barter", t: "nope", l: 3, r: [["plateS", 2]], o: 1 }] },
  "plateS": { n: "小插板", cat: "plate", ts: ["armorPlate"], pt: "ArmorPlate", cl: 3, dur: 40, mat: "Ceramic",
    z: ["RibcageUp", "RibcageLow"], w: 1, p: { a: 300 } },
  "plateM": { n: "中插板", cat: "plate", ts: ["armorPlate"], pt: "ArmorPlate", cl: 5, dur: 50, mat: "Ceramic",
    z: ["RibcageUp"], w: 2, p: { a: 600 }, pen: { s: -1 }, src: ["barter"] },
  "plateX": { n: "异形板", cat: "plate", ts: ["armorPlate"], pt: "ArmorPlate", cl: 6, dur: 55, mat: "ArmoredSteel",
    z: ["RibcageUp"], w: 3, p: { a: 900 } },
  "rigA": { n: "胸挂A", cat: "rig", slot: "rig", ts: ["rig"], pt: "ChestRig", w: 2, p: { a: 700 }, conflict: ["bagA"] },
  /* 装甲防弹弹挂：pt=ChestRig 且 aps[] 带真实防护（fx 内衬），是「防弹衣↔装甲弹挂」互斥的真实判据。
     ★ 关键：上游对这类物品的真实 slot 是 "rig"，但构建期按 types(armor+rig) 把它归成了 cat="armor"。
     这正是本轮要修的「分类错配」真实样本：只看 cat 会让它混进防弹衣槽。 */
  "rigArmored": { n: "装甲弹挂", cat: "armor", slot: "rig", ts: ["armor", "rig"], pt: "ChestRig", w: 4, p: { a: 900 },
    aps: [{ zone: "Soft_armor_front", fx: 1, mat: "Aramid", cl: 3, dur: 45, z: ["RibcageUp", "RibcageLow"] }] },
  /* 普通无装甲弹挂：同一 rig 槽位、同样 pt=ChestRig，但**一条 aps 都没有** → 不得被误判互斥 */
  "rigPlain": { n: "普通弹挂", cat: "rig", slot: "rig", ts: ["rig"], pt: "ChestRig", w: 1.5, p: { a: 500 } },
  "bagA": { n: "背包A", cat: "backpack", ts: ["backpack"], pt: "Backpack", gw: 4, gh: 4, w: 3, p: { a: 1500 } },
  /* 近战武器：上游 propertiesType=ItemPropertiesMelee（本地 pt="Melee"），types 里既无 melee 也无 knife */
  "meleeA": { n: "近战A", ts: ["knife"], pt: "Melee", w: 1, p: { a: 200 }, pen: { e: -2 }, src: ["flea"] },
  "meleeB": { n: "近战B", ts: ["knife"], pt: "Melee", w: 1.2, p: { a: 260 }, pen: { t: -1 } },
  /* 枪械与配件：枪械槽的候选来自已保存的枪械预设，不是这些物品本身 */
  "gunA": { n: "M4A1", cat: "gun", cats: ["5447b5f14bdc2d61278b4567"], w: 3.5, p: { a: 50000 } },
  "pistolA": { n: "PM 手枪", cat: "gun", cats: ["5447b5cf4bdc2d65278b4567"], w: 0.7, p: { a: 9000 } },
  /* 臂带 / 狗牌：狗牌分类同时包含香烟等杂物，候选必须按物品名过滤 */
  "armbandA": { n: "臂带A", cats: ["5b3f15d486f77432d0509248"], w: 0.1, p: { a: 10 } },
  "dogtagA": { n: "BEAR 狗牌", cats: ["590c745b86f7743cc433c5f2"], w: 0.01, p: { b: 900 } },
  "dogtagCig": { n: "香烟", cats: ["590c745b86f7743cc433c5f2"], w: 0.02, p: { a: 100 } },
  "dogtagBag": { n: "狗牌包", pt: "Container", cats: ["590c745b86f7743cc433c5f2"], w: 0.1, p: { a: 100 } },
  "barrelA": { n: "枪管A", cat: "mod", w: 0.4, p: { a: 5000 } }
};

/* 构建期 audit（材质表 / 分类判定依据）：前端只做查表，不猜 */
var AUDIT = {
  rules: { helmet: "types:helmet", headphones: "types:headphones",
           glasses: "types:glasses + category:vis-observ-device",
           face: "category:face-cover", armor: "types:armor",
           rig: "types:rig", backpack: "types:backpack" },
  materials: { Aramid: { d: 0.25 }, Ceramic: { d: 0.55 },
               UHMWPE: { d: 0.45 }, ArmoredSteel: { d: 0.65 } }
};

var bundle = [
  extractVar(src, "ROOT_SLOTS"),
  "var ROOT_BY_KEY = {};ROOT_SLOTS.forEach(function (s) { ROOT_BY_KEY[s.key] = s; });",
  "var GEAR_SLOTS = ROOT_SLOTS.map(function (s) { return s.key; });",
  extractVar(src, "PT_LABELS"),
  extractVar(src, "CHILD_SLOT_LABELS"),
  extractVar(src, "PLATE_LABELS"),
  extractVar(src, "PLATE_LABEL_LC"),
  extractFn(src, "plateLabel"),
  extractVar(src, "MATERIAL_LABELS"),
  extractVar(src, "ZONE_LABELS"),
  extractVar(src, "ZONE_WORD_ORDER"),
  /* R295：头部/躯干颈部词分叉依赖 HEAD_ZONE_CORE + isHeadZoneSet */
  extractVar(src, "HEAD_ZONE_CORE"),
  extractVar(src, "ZONE_WORDS"),
  extractVar(src, "ZONE_ICON_BY_WORDS"),
  extractVar(src, "ZONE_BASE_ICON"),
  extractFn(src, "isHeadZoneSet"),
  extractFn(src, "zoneWord"),
  /* R67：防护区域列的排序值 = 覆盖的不同部位个数（gearRows 里 zoneCount 用到） */
  extractFn(src, "zonePartCount"),
  extractFn(src, "zoneIconKey"),
  extractFn(src, "zoneIconFile"),
  extractFn(src, "zoneWordsUnmapped"),
  extractFn(src, "zoneIconAudit"),
  extractFn(src, "renderZoneIconCell"),
  extractFn(src, "renderZoneCell"),
  "var document = { createElement: function (tag) { return { tagName: String(tag).toUpperCase(), className: \"\"," +
  " title: \"\", src: \"\", alt: \"\", textContent: \"\", children: []," +
  " appendChild: function (c) { this.children.push(c); return c; } }; } };",
  extractVar(src, "PRICE_MODES"),
  extractVar(src, "MODE_SHORT"),
  extractFn(src, "modeShort"),
  extractVar(src, "SRC_LABELS"),
  extractFn(src, "accessText"),
  extractFn(src, "accessKind"),
  extractVar(src, "LS_COLW"),
  extractFn(src, "rootDef"),
  extractFn(src, "itemRec"),
  extractFn(src, "itemPrice"),
  extractFn(src, "fleaPriceInfo"),
  extractFn(src, "modeFleaPrice"),
  extractFn(src, "flea24hPrice"),
  /* R300：配装估值回退链（跳蚤 → 商人直购 → 兑换/制作材料递归估价） */
  extractFn(src, "recipeMaterialCost"),
  extractFn(src, "itemValueInfo"),
  extractFn(src, "itemValue"),
  /* R300d：头盔配件语义位置与子配件外侧偏移（2px 间距） */
  extractVar(src, "HELMET_SLOT_XY"),
  extractFn(src, "helmetSlotPos"),
  extractFn(src, "helmetChildOffset"),
  extractFn(src, "avg7dPriceOf"),
  extractFn(src, "flea7dPrice"),
  extractFn(src, "itemQuoted"),
  extractFn(src, "numOr0"),
  extractFn(src, "penOf"),
  extractFn(src, "priceModeOf"),
  extractFn(src, "materialLabel"),
  extractFn(src, "materialBadge"),
  extractFn(src, "zoneLabel"),
  extractFn(src, "zoneText"),
  extractFn(src, "materialDestructibility"),
  extractFn(src, "effectiveDurability"),
  extractFn(src, "childDefs"),
  /* R19.26：插板按「护甲身份」存取的助手（gearRows / prune / 统计都依赖） */
  extractFn(src, "plateStorageKey"),
  extractFn(src, "isPlateStorageKey"),
  extractFn(src, "plateStorageParts"),
  extractFn(src, "plateStorageActive"),
  extractFn(src, "plateGet"),
  extractFn(src, "plateSet"),
  extractFn(src, "nodeStorageKey"),
  extractFn(src, "nodeLoadoutId"),
  extractFn(src, "nodeSetLoadout"),
  extractFn(src, "plateRecordValid"),
  extractFn(src, "addChildNodes"),
  extractFn(src, "buildSlotTree"),
  extractFn(src, "pruneOrphanSlots"),
  extractFn(src, "currentNode"),
  extractFn(src, "focusRootKey"),
  extractFn(src, "inList"),
  extractVar(src, "SLOT_DRIVEN_ROOTS"),
  extractVar(src, "ARMBAND_CAT"),
  extractFn(src, "isDogtagItem"),
  extractFn(src, "inRootSlot"),
  extractFn(src, "candidatesOf"),
  extractFn(src, "isArmoredRig"),
  extractFn(src, "isBodyArmor"),
  extractFn(src, "isChestRig"),
  extractFn(src, "conflictKinds"),
  extractFn(src, "installCheck"),
  extractFn(src, "conflictsOf"),
  /* 第六轮：枪械预设引用（nameOf / candidateSource / gearTotals 都依赖这组纯查表函数） */
  extractVar(src, "GUN_REF_PREFIX"),
  extractVar(src, "GUN_CAT_HANDGUN"),
  extractFn(src, "gunIsHandgun"),
  extractFn(src, "isGunRef"),
  extractFn(src, "gunRefToken"),
  extractFn(src, "gunRefId"),
  extractFn(src, "weaponPresets"),
  extractFn(src, "weaponPresetById"),
  extractFn(src, "builtinGunPresets"),
  extractFn(src, "builtinGunPresetById"),
  extractFn(src, "gunslotsData"),
  extractFn(src, "gunRecord"),
  extractFn(src, "gunRefInfo"),
  extractFn(src, "weaponPresetTotals"),
  extractFn(src, "sellPriceOf"),
  extractFn(src, "buyPriceOf"),
  extractFn(src, "gunRefRows"),
  extractFn(src, "equipGunRef"),
  extractFn(src, "nameOf"),
  extractFn(src, "nodeLabel"),
  extractFn(src, "candidateSource"),
  extractFn(src, "gearRows"),
  extractFn(src, "equippedList"),
  extractFn(src, "gearTotals"),
  extractFn(src, "slotLocalPen"),
  extractFn(src, "clampColW"),
  extractFn(src, "colwNorm"),
  extractFn(src, "loadColWidths"),
  extractFn(src, "colCatKey"),
  extractFn(src, "colWidthFor"),
  extractFn(src, "saveColWidth"),
  extractVar(src, "LW_COL_BASE"),
  extractVar(src, "LW_COL_DEFAULTS"),
  extractFn(src, "applyColDefaults"),
  extractFn(src, "selectSlot"),
  extractFn(src, "equipItem"),
  extractFn(src, "clearGearSlot"),
  extractFn(src, "unequipByContextMenu"),
  extractFn(src, "commitLoadoutChange"),
  /* 第五轮：逐笔获取方式 + 护甲板位（两个新业务函数集，纯查表，不碰 DOM） */
  extractFn(src, "fmtNum"),
  extractFn(src, "fmtMoney"),
  extractVar(src, "TRADER_ICON_DIR"),
  extractVar(src, "TRADER_PORTRAIT_DIR"),
  extractVar(src, "ROMAN_LEVEL"),
  extractVar(src, "TRADE_KIND_LABEL"),
  extractFn(src, "romanLevel"),
  extractFn(src, "traderRec"),
  extractVar(src, "TRADER_SLUG_UPPER"),
  extractFn(src, "traderEnglishFromSlug"),
  extractFn(src, "traderName"),
  extractFn(src, "traderIconUrl"),
  extractFn(src, "traderIconFallbackUrl"),
  extractFn(src, "setImgFallback"),
  extractFn(src, "taskName"),
  extractFn(src, "fleaIconUrl"),
  /* R296：兑换数量取整（GP 币上游折算值是浮点） */
  extractFn(src, "reqQty"),
  extractFn(src, "tradeView"),
  extractFn(src, "tradeViews"),
  extractVar(src, "PLATE_COL_ZONES"),
  extractFn(src, "armorSocket"),
  /* 第十轮：内衬独立列模型（r9 的 armorLiner 已删除，内衬不再进板位格） */
  extractVar(src, "LINER_COL_ZONES"),
  extractFn(src, "linerBreakdown"),
  extractVar(src, "LW_HARD_PLATE_ZONES"),
  extractFn(src, "maxArmorClassOf"),
  extractFn(src, "baseArmorClassOf"),
  extractFn(src, "renderNameCellPlain"),
  extractFn(src, "plateSlotState"),
  extractFn(src, "plateSlotStates"),
  /* 第五轮第五节：按类别生成列集（列定义里引用到的渲染函数也要带上） */
  extractFn(src, "renderNameCell"),
  extractFn(src, "renderPenCell"),
  extractFn(src, "renderPlateCell"),
  extractFn(src, "renderSrcCell"),
  extractFn(src, "gearColumns")
].join("\n");

var state = { items: {}, loadout: {}, focus: "helmet", slotTree: null, audit: null,
              traders: {}, tasks: {}, gunslots: {}, presets: {},
              colWidths: { byCat: {}, shared: {} },
              pending: [], lwMin: null, lwMax: null, lwQuoted: false, priceMode: "avg24h",
              dataScope: { mode: "regular" }, sens: null };
var store = {};
var localStorage = {
  setItem: function (k, v) { store[k] = String(v); },
  getItem: function (k) { return (k in store) ? store[k] : null; },
  removeItem: function (k) { delete store[k]; }
};
function noop() {}
var api = new Function(
  "state", "localStorage", "persistLoadout", "renderLwTabs", "renderGearSide",
  "refreshGearTable", "syncLwFilters", "syncSensInput", "queuePrefs", "uiPatch",
  "paintPlatePicker", "hideLwTip",
  bundle + "\nreturn {buildSlotTree:buildSlotTree,candidatesOf:candidatesOf,gearRows:gearRows," +
  "gearTotals:gearTotals,slotLocalPen:slotLocalPen,selectSlot:selectSlot,equipItem:equipItem," +
  "clearGearSlot:clearGearSlot,unequipByContextMenu:unequipByContextMenu," +
  "equipGunRef:equipGunRef,nameOf:nameOf,gunRefToken:gunRefToken," +
  "commitLoadoutChange:commitLoadoutChange,currentNode:currentNode,focusRootKey:focusRootKey," +
  "nodeLabel:nodeLabel,candidateSource:candidateSource,installCheck:installCheck," +
  "accessText:accessText,accessKind:accessKind," +
  "conflictsOf:conflictsOf,childDefs:childDefs,materialLabel:materialLabel,zoneText:zoneText," +
  "zoneIconKey:zoneIconKey,zoneIconFile:zoneIconFile,zoneWordsUnmapped:zoneWordsUnmapped," +
  "zoneIconAudit:zoneIconAudit,renderZoneCell:renderZoneCell," +
  "effectiveDurability:effectiveDurability," +
  "materialDestructibility:materialDestructibility," +
  "colwNorm:colwNorm,loadColWidths:loadColWidths,colCatKey:colCatKey,colWidthFor:colWidthFor," +
  "saveColWidth:saveColWidth,ROOT_SLOTS:ROOT_SLOTS,GEAR_SLOTS:GEAR_SLOTS," +
  "LW_COL_BASE:LW_COL_BASE,LW_COL_DEFAULTS:LW_COL_DEFAULTS,applyColDefaults:applyColDefaults," +
  "tradeViews:tradeViews,tradeView:tradeView,plateSlotStates:plateSlotStates," +
  "plateSlotState:plateSlotState,romanLevel:romanLevel,PLATE_COL_ZONES:PLATE_COL_ZONES," +
  "LINER_COL_ZONES:LINER_COL_ZONES,linerBreakdown:linerBreakdown," +
  "maxArmorClassOf:maxArmorClassOf,renderNameCellPlain:renderNameCellPlain," +
  "HELMET_SLOT_XY:HELMET_SLOT_XY,helmetSlotPos:helmetSlotPos," +
  "helmetChildOffset:helmetChildOffset," +
  "gearColumns:gearColumns};"
)(state, localStorage, noop, noop, noop, noop, noop, noop, noop, function () { return {}; }, noop, noop);

var checks = 0;
var failures = [];
function check(name, cond) { checks++; if (!cond) { failures.push(name); } }
function sorted(a) { return a.slice().sort(); }
function rowIds() { return sorted(api.gearRows().map(function (r) { return r.__id; })); }
function node(id) { return state.slotTree.nodes[id]; }
function kids(id) { return sorted((node(id) && node(id).children) || []); }
function rowOf(id) {
  var rows = api.gearRows();
  for (var i = 0; i < rows.length; i++) { if (rows[i].__id === id) { return rows[i]; } }
  return null;
}
function reset() {
  state.items = ITEMS;
  state.audit = AUDIT;
  state.loadout = {};
  state.focus = "helmet";
  state.colWidths = { byCat: {}, shared: {} };
  state.pending = [];
  state.lwMin = null; state.lwMax = null; state.lwQuoted = false;
  state.gunslots = { gunA: { n: "M4A1" } };
  state.presets = {};
  state.slotTree = api.buildSlotTree();
}

/* T1 候选按槽位的真实类型过滤（护甲板不算护甲；附件不在根槽位候选里） */
reset();
check("T1 空配装只建根槽位（9 个装备槽 + 4 个武器槽）",
  state.slotTree.order.length === 13 && node("helmet").kind === "root");
check("T1 头盔候选只含构建期 cat=helmet 的",
  sorted(api.candidatesOf(node("helmet"))).join(",") ===
  "helmetA,helmetB,helmetC,helmetD,helmetF,helmetG,helmetPlain");
check("T1 臂带候选按分类 id 取", sorted(api.candidatesOf(node("armband"))).join(",") === "armbandA");
check("T1 狗牌候选按物品名取（排除香烟 / 狗牌包）",
  sorted(api.candidatesOf(node("dogtag"))).join(",") === "dogtagA");
check("T1 护甲候选排除护甲板、含装甲胸挂（R22.2 归防弹衣槽）",
  sorted(api.candidatesOf(node("armor"))).join(",") === "armorA,armorMisCat,armorPlain,rigArmored");
check("T1 背包候选", sorted(api.candidatesOf(node("backpack"))).join(",") === "bagA");
check("T1 护面只含构建期 face 分类（不再用「未被引用」近似）",
  sorted(api.candidatesOf(node("face"))).join(",") === "faceMask");
check("T1 护甲板不得出现在护面候选里",
  sorted(api.candidatesOf(node("face"))).indexOf("plateX") < 0);
check("T1 眼镜只含构建期 glasses 分类",
  sorted(api.candidatesOf(node("glasses"))).join(",") === "glasses1");
check("T1 头盔专用附件（被 slots 引用）不得出现在眼镜候选里",
  sorted(api.candidatesOf(node("glasses"))).indexOf("maskRef") < 0);
check("T1 七类互斥：每件物品只属于一个根槽位",
  (function () {
    var seen = {};
    for (var i = 0; i < api.ROOT_SLOTS.length; i++) {
      var ids = api.candidatesOf(node(api.ROOT_SLOTS[i].key));
      for (var j = 0; j < ids.length; j++) {
        if (seen[ids[j]]) { return false; }
        seen[ids[j]] = true;
      }
    }
    return true;
  })());

/* T2 点左侧槽位 → 右侧候选立即换（防「伪联动」：不得沿用上一类别） */
reset();
state.focus = "helmet";
check("T2 focus=头盔时右侧是头盔候选", rowIds().length === 7 && rowIds()[0] === "helmetA");
api.selectSlot("backpack");
check("T2 selectSlot 只改 focus", state.focus === "backpack" && api.focusRootKey() === "backpack");
check("T2 右侧立即换成背包候选（不是上一类别）", rowIds().join(",") === "bagA");
api.selectSlot("helmet");
check("T2 切回头盔候选", rowIds().length === 7);

/* T3 冲突：真实规则（任一方向命中即冲突）→ 候选标红 + 明确原因，且**点它装不上** */
reset();
var rowIn = function (rows, id) {
  for (var i = 0; i < rows.length; i++) { if (rows[i].__id === id) { return rows[i]; } }
  return null;
};
api.selectSlot("headphones");
api.equipItem("hp1");                 // 先装耳机（此时无冲突）
api.selectSlot("helmet");
var rowsHelmet = api.gearRows();
var rowA = rowIn(rowsHelmet, "helmetA");
var rowPlain = rowIn(rowsHelmet, "helmetPlain");
check("T3 头盔A 与耳机1 冲突 → 红行 + blocked", rowA && rowA.conflict === true && rowA.blocked === true);
check("T3 冲突原因可读（含对方物品名与规则）",
  rowA && rowA.conflictText.indexOf("耳机1") >= 0 && rowA.conflictText.indexOf("互斥") >= 0);
check("T3 不冲突的候选保持正常", rowPlain && rowPlain.conflict === false);
/* 点冲突候选：不改配装、不自动卸下对方、统计不变 */
var snapBefore = JSON.stringify(state.loadout);
var totBefore = api.gearTotals();
api.equipItem("helmetA");
check("T3 点冲突候选：配装完全不改（未装上）", JSON.stringify(state.loadout) === snapBefore);
check("T3 点冲突候选：不会自动卸下造成冲突的耳机1", state.loadout.headphones === "hp1");
check("T3 点冲突候选：件数 / 重量 / 价格统计不变",
  api.gearTotals().count === totBefore.count &&
  api.gearTotals().weight === totBefore.weight &&
  api.gearTotals().price === totBefore.price);
check("T3 点击时给出明确原因但不执行装配",
  state.pending.join("").indexOf("无法安装") >= 0 &&
  state.pending.join("").indexOf("耳机1") >= 0 &&
  state.pending.join("").indexOf("未改动配装") >= 0);

/* T4 单向 conflict 字段也判冲突（实测上游多为双向，但判定用「任一方向」） */
reset();
api.selectSlot("rig");
api.equipItem("rigA");
api.selectSlot("backpack");
check("T4 背包A 与胸挂A 冲突（单向字段也命中）", api.gearRows()[0].conflict === true);
api.clearGearSlot("rig");
api.selectSlot("backpack");
check("T4 移除胸挂后背包候选恢复", api.gearRows()[0].conflict === false);

/* T5 移除造成冲突的装备 → 冲突立即消失 */
reset();
api.selectSlot("headphones");
api.equipItem("hp1");
api.selectSlot("helmet");
api.clearGearSlot("headphones");
var r2 = api.gearRows();
var a2 = rowIn(r2, "helmetA");
check("T5 卸下耳机后头盔候选不再冲突", a2 && a2.conflict === false);

/* T6 装上带插槽的装备 → 左侧按真实定义生成子槽；点子槽右侧只显示该槽可装附件 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetA");
check("T6 头盔A 生成两个附件子槽", kids("helmet").join(",") === "helmet/mount,helmet/nvg");
check("T6 子槽 kind=attach", node("helmet/nvg").kind === "attach");
check("T6 子槽面包屑", api.nodeLabel(node("helmet/nvg")) === "头盔 › 夜视仪座");
api.selectSlot("helmet/nvg");
check("T6 点夜视仪座 → 右侧只有 nvg1", rowIds().join(",") === "nvg1");
api.selectSlot("helmet/mount");
check("T6 点安装座 → 右侧只有 mount1", rowIds().join(",") === "mount1");
check("T6 候选来源写清父装备与字段", api.candidateSource(node("helmet/mount")).indexOf("slots[].allowedItems") >= 0);

/* T7 不支持该插槽的头盔不凭空生成同名子槽 */
api.selectSlot("helmet");
api.equipItem("helmetPlain");
check("T7 素头盔没有子槽", kids("helmet").length === 0);
check("T7 换父装备后旧子槽键已清掉", !Object.prototype.hasOwnProperty.call(state.loadout, "helmet/nvg"));

/* T8 换父装备：子槽按新定义变化；仍存在但不再允许的附件会被自动卸下并提示 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetC");
api.selectSlot("helmet/mount");
api.equipItem("mount1");
check("T8 头盔C 上装好 mount1", state.loadout["helmet/mount"] === "mount1");
api.selectSlot("helmet");
api.equipItem("helmetD");
check("T8 头盔D 的子槽仍是 mount（结构未变）", kids("helmet").join(",") === "helmet/mount");
check("T8 不再被允许的 mount1 被自动卸下（不悄悄保留）", !state.loadout["helmet/mount"]);
check("T8 自动卸下有可见提示",
  state.pending.join("").indexOf("自动卸下") >= 0 && state.pending.join("").indexOf("安装座1") >= 0);

/* T9 卸下父装备 → 子槽与附件一起消失 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetA");
api.selectSlot("helmet/nvg");
api.equipItem("nvg1");
api.clearGearSlot("helmet");
check("T9 卸下头盔后子槽消失", kids("helmet").length === 0);
check("T9 子槽里的夜视仪键一并清掉", !state.loadout["helmet/nvg"]);

/* T10 只有 allowedCategories 的槽 → 标数据缺口、候选留空（不虚构规则） */
reset();
api.selectSlot("helmet");
api.equipItem("helmetG");
check("T10 缺口槽仍会生成（结构真实存在）", kids("helmet").join(",") === "helmet/eq");
check("T10 缺口槽标为 gap", node("helmet/eq").def.gap === true);
check("T10 缺口槽候选为空", api.candidatesOf(node("helmet/eq")).length === 0);
check("T10 缺口在来源说明里讲清楚",
  api.candidateSource(node("helmet/eq")).indexOf("数据缺口") >= 0);
check("T10 清单里写明走的是 armorSlots 而不是 slots", node("helmet/eq").def.source === "slots[].allowedItems");

/* T11 护甲板：用真实兼容关系（allowedPlates），不是按名字分类 */
reset();
api.selectSlot("armor");
api.equipItem("armorA");
check("T11 护甲A 生成两个板位", kids("armor").join(",") === "armor/Back_plate,armor/Front_plate");
check("T11 板位 kind=plate", node("armor/Front_plate").kind === "plate");
check("T11 板位面包屑", api.nodeLabel(node("armor/Front_plate")) === "护甲 › 前插板");
api.selectSlot("armor/Front_plate");
check("T11 前插板候选 = allowedPlates 前插板槽的列表",
  rowIds().join(",") === "plateM,plateS");
api.selectSlot("armor/Back_plate");
check("T11 后插板候选只有 plateM", rowIds().join(",") === "plateM");
check("T11 不在允许列表里的护甲板不出现",
  rowIds().indexOf("plateX") < 0 && sorted(api.candidatesOf(node("armor"))).indexOf("plateX") < 0);
check("T11 板位来源写明 armorSlots[].allowedPlates",
  api.candidateSource(node("armor/Back_plate")).indexOf("armorSlots[].allowedPlates") >= 0);

/* T12 统计遍历槽位树（含子槽）：重量/件数跟着换装备更新 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetC");
api.selectSlot("helmet/mount");
api.equipItem("mount1");
var t = api.gearTotals();
check("T12 件数含子槽附件", t.count === 2);
check("T12 重量为父子之和", Math.abs(t.weight - 2.6) < 1e-9);
api.selectSlot("helmet");
api.clearGearSlot("helmet");
check("T12 卸下后件数归零", api.gearTotals().count === 0);

/* U1 固定内衬：固定组件（非可装子槽）、无候选、不可装卸、也不标「数据缺失」 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetB");
check("U1 头盔B 只有内衬子槽（在父装备正下方）", kids("helmet").join(",") === "helmet/Helmet_top");
var linerNode = node("helmet/Helmet_top");
check("U1 内衬节点挂在父装备下", linerNode.parent === "helmet");
check("U1 内衬 kind=liner", linerNode.kind === "liner");
check("U1 内衬标记为固定（fixed=true / removable=false）",
  linerNode.def.fixed === true && linerNode.def.removable === false);
check("U1 内衬没有可选项（不可自由选装）", api.candidatesOf(linerNode).length === 0);
check("U1 内衬来源写明不可拆卸、且明确不是数据缺口",
  api.candidateSource(linerNode).indexOf("不可单独拆卸") >= 0 &&
  api.candidateSource(linerNode).indexOf("不是数据缺失") >= 0 &&
  api.candidateSource(linerNode).indexOf("数据缺口") < 0);
check("U1 内衬带真实防护数据（材质/等级/耐久/防护区）",
  linerNode.def.mat === "Ceramic" && linerNode.def.cl === 3 &&
  linerNode.def.dur === 30 && linerNode.def.z.join(",") === "ParietalHead");
check("U1 内衬标签写明「固定」", api.nodeLabel(linerNode).indexOf("固定") >= 0);
/* 不提供安装入口：把 focus 直接指向内衬，equipItem 是空操作 */
state.focus = "helmet/Helmet_top";
var beforeLoadout = JSON.stringify(state.loadout);
api.equipItem("plateX");
check("U1 固定内衬上 equipItem 是空操作（不提供装卸入口）",
  JSON.stringify(state.loadout) === beforeLoadout);
/* 点子槽焦点自动回退到父装备（不留独立操作入口） */
api.selectSlot("helmet/Helmet_top");
check("U1 选中内衬会回退到父装备槽位", state.focus === "helmet");
/* 换父装备 → 固定内衬随父装备结构同步更新 */
api.equipItem("helmetPlain");
check("U1 换成无内衬头盔后内衬槽消失", kids("helmet").length === 0);
api.equipItem("helmetB");
check("U1 换回头盔B 内衬按新结构重建", kids("helmet").join(",") === "helmet/Helmet_top");

/* U2 不同头盔的附件槽结构按各自真实定义生成、彼此不同 */
reset();
function structKey(rootId) {
  return kids(rootId).map(function (k) {
    var n = node(k);
    return k + ":" + (n.kind === "liner" ? ("liner-fixed=" + n.def.fixed)
      : (n.def.gap ? "gap" : (n.def.allow || []).join("+")));
  }).join("|");
}
api.selectSlot("helmet");
api.equipItem("helmetA");
var sA = structKey("helmet");
check("U2 头盔A = 夜视仪座 + 安装座", kids("helmet").join(",") === "helmet/mount,helmet/nvg");
api.equipItem("helmetD");
var sD = structKey("helmet");
check("U2 头盔D 只有安装座，且允许的是 mount2",
  kids("helmet").join(",") === "helmet/mount" &&
  api.candidatesOf(node("helmet/mount")).join(",") === "mount2");
api.equipItem("helmetF");
var sF = structKey("helmet");
check("U2 头盔F 是装备座（可装 maskRef）",
  kids("helmet").join(",") === "helmet/eq" &&
  api.candidatesOf(node("helmet/eq")).join(",") === "maskRef");
api.equipItem("helmetG");
var sG = structKey("helmet");
check("U2 头盔G 是缺口装备座（只有 allowedCategories）",
  kids("helmet").join(",") === "helmet/eq" && node("helmet/eq").def.gap === true);
api.equipItem("helmetB");
var sB = structKey("helmet");
check("U2 头盔B 只有固定内衬、没有可装附件槽", kids("helmet").join(",") === "helmet/Helmet_top");
check("U2 五种头盔的附件槽结构确实彼此不同",
  sA !== sD && sD !== sF && sF !== sG && sG !== sB && sB !== sA);

/* U3 不同护甲：可换插板槽 vs 固定内衬，安装关系真实 */
reset();
api.selectSlot("armor");
api.equipItem("armorA");
check("U3 护甲A 两个可换插板槽", kids("armor").join(",") === "armor/Back_plate,armor/Front_plate");
check("U3 插板槽 kind=plate（与内衬区分）",
  node("armor/Front_plate").kind === "plate" && node("armor/Back_plate").kind === "plate");
check("U3 前插板允许列表来自上游 armorSlots[].allowedPlates",
  node("armor/Front_plate").def.allow.join(",") === "plateS,plateM");
api.equipItem("armorPlain");
check("U3 素护甲没有可换插板槽，只有固定内衬",
  kids("armor").join(",") === "armor/Soft_armor_front" &&
  node("armor/Soft_armor_front").kind === "liner");
check("U3 固定内衬标记固定、无候选",
  node("armor/Soft_armor_front").def.fixed === true &&
  api.candidatesOf(node("armor/Soft_armor_front")).length === 0);
api.equipItem("armorA");
api.selectSlot("armor/Front_plate");
api.equipItem("plateM");
check("U3 前插板装上 plateM（R19.26 按护甲身份存）",
  state.loadout["armor/Front_plate@armorA"] === "plateM");
api.selectSlot("armor");
api.equipItem("armorPlain");
check("U3 换父护甲后旧插板槽（树上节点）与其它附件一起消失",
  kids("armor").join(",") === "armor/Soft_armor_front");
check("U3 R19.26：换护甲不删旧护甲的插板配置（切回来要能恢复）",
  state.loadout["armor/Front_plate@armorA"] === "plateM");
check("U3 R19.26：新护甲不受旧插板影响（读不到、不显示已安装）",
  !Object.prototype.hasOwnProperty.call(state.loadout, "armor/Front_plate") &&
  api.plateSlotStates("armorPlain", "armor", state.items.armorPlain)[0].state !== "on" &&
  api.plateSlotStates("armorA", "armor", state.items.armorA)[0].state !== "on");

/* U4 护甲列：装甲材质 / 材料毁损系数 / 基础耐久 / 有效耐久 / 防护区域 / 护甲等级 六种概念互不混淆 */
reset();
api.selectSlot("armor");
var ar = rowOf("armorA");
check("U4 装甲材质显示真实材质并给中文映射",
  ar.mat === "UHMWPE" && ar.matLabel === "聚乙烯");
check("U4 材料毁损系数取自上游材质表", ar.destr === 0.45);
check("U4 基础耐久 = 游戏内显示耐久", ar.dur === 60);
check("U4 有效耐久 = 基础耐久 ÷ 毁损系数（系数不四舍五入）",
  ar.effDur !== null && Math.abs(ar.effDur - 60 / 0.45) < 1e-9);
check("U4 有效耐久与基础耐久是两个不同值", ar.effDur !== ar.dur);
check("U4 防护区域来自物品自身 zones（中文映射）", ar.zoneText === "上胸、下胸、上背");
check("U4 已删除错误的「部位有效护甲值」行字段", !("zoneCls" in ar));
check("U4 插板行：材质/毁损/有效耐久/防护区域各自独立",
  (function () {
    api.equipItem("armorA");                   // 插板槽只在父护甲装上后才存在
    api.selectSlot("armor/Front_plate");
    var pl = rowOf("plateM");
    return pl && pl.matLabel === "陶瓷" && pl.destr === 0.55 &&
      Math.abs(pl.effDur - 50 / 0.55) < 1e-9 &&
      pl.zoneText === "上胸" && !("zoneCls" in pl);
  })());
/* 六种护甲概念必须各自独立成列：由下面的 pytest 静态断言核对列集与列名 */
api.selectSlot("armor");
check("U4 材质未知时不伪造（素护甲材质映射仍可读）",
  rowOf("armorPlain").matLabel === "芳纶" && rowOf("armorPlain").destr === 0.25);

/* U5 列宽持久化：保存 → localStorage → 「重启」重新载入 → 宽度恢复 */
reset();
state.colWidths = { byCat: {}, shared: {} };
api.saveColWidth(node("helmet"), { key: "n" }, 240);
api.saveColWidth(node("helmet"), { key: "w" }, 80);
check("U5 保存后写入本类别桶", state.colWidths.byCat.helmet.n === 240);
check("U5 保存后写入同名同义共享桶", state.colWidths.shared.n === 240);
check("U5 列宽已落到 localStorage", (store["eftmap.colw"] || "").indexOf('"n":240') >= 0);
/* 模拟重启：清空内存态后从 localStorage 恢复 */
state.colWidths = { byCat: {}, shared: {} };
api.loadColWidths();
check("U5 重启后按类别恢复列宽", api.colWidthFor(node("helmet"), { key: "n" }) === 240);
check("U5 重启后另一类别复用同名同义列宽（shared 桶）",
  api.colWidthFor(node("armor"), { key: "n" }) === 240);
check("U5 未设置过的列返回 null（交给列自带宽度）",
  api.colWidthFor(node("helmet"), { key: "conflict" }) === null);
api.saveColWidth(node("helmet"), { key: "ptLabel" }, 10000);
check("U5 超大宽度被钳到 520", api.colWidthFor(node("helmet"), { key: "ptLabel" }) === 520);
api.saveColWidth(node("helmet"), { key: "cl" }, 3);
check("U5 过小宽度被钳到 56", api.colWidthFor(node("helmet"), { key: "cl" }) === 56);
var clean = api.colwNorm({ byCat: { helmet: { n: "abc", w: undefined, cl: 300 } }, shared: 5 });
check("U5 非数值列宽被丢弃、合法值保留",
  clean.byCat.helmet.n === undefined && clean.byCat.helmet.w === undefined &&
  clean.byCat.helmet.cl === 300);
check("U5 结构非法的桶被丢弃", Object.keys(clean.shared).length === 0);

/* U6 子槽一律挂在各自父装备节点下（不存在「集中到面板底部」的平铺附件列表） */
reset();
api.selectSlot("helmet");
api.equipItem("helmetA");
api.selectSlot("armor");
api.equipItem("armorA");
check("U6 头盔与护甲的子槽分别挂在各自根节点下",
  node("helmet/nvg").parent === "helmet" && node("helmet/mount").parent === "helmet" &&
  node("armor/Front_plate").parent === "armor" && node("armor/Back_plate").parent === "armor");
check("U6 子槽不共享同一个父节点（不是统一追加到底部）",
  node("helmet/nvg").parent !== node("armor/Front_plate").parent);

/* T13 统一安装前校验：不兼容候选一律点不下，原装备 / 统计一律不变（所有装备入口同一检查） */
reset();
api.equipItem("helmetA");                  // focus = helmet
api.selectSlot("rig");
api.equipItem("rigA");                    // 胸挂A 与背包A 上游互斥
api.selectSlot("backpack");
var bpRow = api.gearRows()[0];
check("T13 冲突背包候选 blocked（红行 + 原因含对方名）",
  bpRow.conflict === true && bpRow.blocked === true && bpRow.conflictText.indexOf("胸挂A") >= 0);
var snap13 = JSON.stringify(state.loadout);
var tot13 = api.gearTotals();
api.equipItem("bagA");
check("T13 点冲突候选：配装完全不改", JSON.stringify(state.loadout) === snap13);
check("T13 点冲突候选：件数 / 重量 / 价格统计不变",
  api.gearTotals().count === tot13.count &&
  api.gearTotals().weight === tot13.weight &&
  api.gearTotals().price === tot13.price);
check("T13 冲突被拒时不会自动卸下已装备的胸挂A", state.loadout.rig === "rigA");
check("T13 点击给出明确原因（对方物品名 + 规则 + 未改动配装）",
  state.pending.join("").indexOf("胸挂A") >= 0 &&
  state.pending.join("").indexOf("未改动配装") >= 0);
check("T13 installCheck 是统一入口（gearRows / equipItem 都走它）",
  api.installCheck("bagA", "backpack").allowed === false &&
  api.installCheck("bagA", "backpack").hits.length === 1);

/* T14 装甲弹挂 ↔ 胸挂双向互斥（R22.2：选了防弹胸挂就不能选胸挂）；防弹衣与普通胸挂可共存 */
reset();
api.selectSlot("armor");
api.equipItem("rigArmored");               // (a) 先穿装甲弹挂（归防弹衣槽）
api.selectSlot("rig");
var rigRows = api.gearRows();
var rPlainRig = rowIn(rigRows, "rigPlain");
var rA = rowIn(rigRows, "rigA");
check("T14 先穿装甲弹挂后：胸挂红 + 禁装 + 原因",
  rPlainRig && rPlainRig.conflict === true && rPlainRig.blocked === true &&
  rPlainRig.conflictText.indexOf("互斥") >= 0);
check("T14 普通胸挂也被禁（同为 rig 类别也判冲突）",
  rA && rA.conflict === true);
api.equipItem("rigPlain");
check("T14 胸挂装不上，装甲弹挂仍在",
  !state.loadout.rig && state.loadout.armor === "rigArmored");
reset();
api.selectSlot("rig");
api.equipItem("rigPlain");                 // (b) 先穿胸挂
api.selectSlot("armor");
var aArm = rowIn(api.gearRows(), "rigArmored");
check("T14 先穿胸挂后：装甲弹挂红 + 禁装 + 原因",
  aArm && aArm.conflict === true && aArm.blocked === true &&
  aArm.conflictText.indexOf("互斥") >= 0);
api.equipItem("rigArmored");
check("T14 装甲弹挂也装不上，胸挂仍在",
  !state.loadout.armor && state.loadout.rig === "rigPlain");
api.selectSlot("rig");
api.clearGearSlot("rig");                  // (c) 卸下胸挂 → 装甲弹挂恢复可选
api.selectSlot("armor");
check("T14 卸下胸挂后装甲弹挂恢复可选",
  rowIn(api.gearRows(), "rigArmored").conflict === false);
reset();
api.selectSlot("armor");
api.equipItem("armorA");                   // (d) 防弹衣与普通胸挂可共存
api.selectSlot("rig");
check("T14 普通胸挂与防弹衣不冲突",
  rowIn(api.gearRows(), "rigPlain").conflict === false);
api.equipItem("rigPlain");
check("T14 普通胸挂可以真的装上", state.loadout.rig === "rigPlain");

/* T15 四个武器槽：枪械槽从已保存的枪械预设中选（gunref 稳定引用），近战走真实 Melee 候选 */
reset();
check("T15 四个武器槽都是根槽位",
  ["primary1", "primary2", "holster", "melee"].every(function (k) {
    return node(k) && node(k).kind === "root";
  }));
check("T15 枪械槽标记为 gunref（候选来自已保存枪械预设，不拿普通物品冒充）",
  node("primary1").def.gunref === true && node("primary2").def.gunref === true &&
  node("holster").def.gunref === true && !node("melee").def.gunref);
check("T15 未保存任何枪械预设时枪械槽候选为空，来源说明指向 weapon-presets.json",
  api.candidatesOf(node("primary1")).length === 0 &&
  api.candidateSource(node("primary1")).indexOf("weapon-presets.json") >= 0);
api.selectSlot("primary1");
check("T15 未保存预设时枪械槽右侧没有任何行", api.gearRows().length === 0);
check("T15 近战槽不是 pending", !node("melee").def.pending);
check("T15 近战候选来自真实 pt=Melee 的物品（不混入普通物品）",
  sorted(api.candidatesOf(node("melee"))).join(",") === "meleeA,meleeB");
api.selectSlot("melee");
api.equipItem("meleeA");
check("T15 近战武器可实际装上", state.loadout.melee === "meleeA");
api.clearGearSlot("melee");
check("T15 近战武器可卸下", !state.loadout.melee);

/* T15b 有枪械预设后：候选行来自预设，槽位存稳定引用 @wp:<id>，重命名不影响引用 */
reset();
state.presets = { weapon: { presets: [
  { id: "wp_a", name: "我的 M4A1", gunId: "gunA", items: {} },
  { id: "wp_b", name: "我的短管", gunId: "gunA", items: { mod_barrel: "barrelA" } },
  { id: "wp_p", name: "我的 PM", gunId: "pistolA", items: {} }
] } };
api.selectSlot("primary1");
check("T15b 候选行来自已保存枪械预设", api.gearRows().length === 2);
check("T15b 枪械预设行带预设 id、名称与真实重量",
  !!rowOf("wp_a") && rowOf("wp_a").n === "我的 M4A1" &&
  Math.abs(rowOf("wp_a").w - 3.5) < 1e-9);
check("T15b 带配件的预设重量含配件（3.5 + 0.4）",
  Math.abs(rowOf("wp_b").w - 3.9) < 1e-9);
check("T15b 主武器槽不混入手枪预设", !rowOf("wp_p"));
api.equipGunRef("wp_a");
check("T15b 主武器 1 存稳定引用而不是物品 id", state.loadout.primary1 === "@wp:wp_a");
check("T15b 引用解析出预设名", api.nameOf(state.loadout.primary1) === "我的 M4A1");
check("T15b 主武器槽拒绝手枪预设（保留原枪，不静默替换）", (function () {
  api.equipGunRef("wp_p");
  return state.loadout.primary1 === "@wp:wp_a" &&
    state.pending.join(" ").indexOf("主武器槽只能装主武器") >= 0;
})());
api.selectSlot("holster");
check("T15b 手枪槽只列手枪预设", api.gearRows().length === 1 && !!rowOf("wp_p"));
check("T15b 手枪槽拒绝步枪预设（业务层，不只靠按钮禁用）", (function () {
  api.equipGunRef("wp_b");
  return !state.loadout.holster && state.pending.join(" ").indexOf("手枪") >= 0;
})());
api.equipGunRef("wp_p");
check("T15b 手枪槽可装手枪枪械预设", state.loadout.holster === "@wp:wp_p");
api.selectSlot("primary1");
api.equipGunRef("wp_a");
check("T15b 再点同一套 = 卸下", !state.loadout.primary1);

/* T15c 预设被删掉后引用显式标记缺失，绝不静默换成别的枪 */
state.loadout.primary1 = "@wp:wp_gone";
check("T15c 缺失引用显示「缺失」，不静默替换",
  api.nameOf(state.loadout.primary1).indexOf("缺失") >= 0);
check("T15c 缺失引用在槽位来源说明里明确标出「不存在」",
  api.candidateSource(node("primary1")).indexOf("不存在") >= 0);

/* T16 减益 / 重量 / 件数统计遍历**所有已装可装备物品**，安装 / 卸下 / 换装备后实时更新 */
reset();
api.selectSlot("glasses");
api.equipItem("glasses1");                 // 眼镜：此前被漏统计的那批
var tA = api.gearTotals();
check("T16 眼镜装上 → 转身 / 移动减益立即计入",
  tA.turn === -1 && tA.speed === -2);
check("T16 眼镜计入件数与重量", tA.count === 1 && Math.abs(tA.weight - 0.1) < 1e-9);
api.selectSlot("backpack");
api.equipItem("bagA");
api.selectSlot("melee");
api.equipItem("meleeA");                   // 近战自带人机工学减益
var t16 = api.gearTotals();
check("T16 件数含眼镜 / 背包 / 近战（不再只看头盔+防弹衣）", t16.count === 3);
check("T16 重量为实际已装物品之和", Math.abs(t16.weight - (0.1 + 3 + 1)) < 1e-9);
check("T16 人机工学减益来自近战（全量遍历）", Math.abs(t16.ergo - (-2)) < 1e-9);
api.selectSlot("armor");
api.equipItem("armorA");
api.selectSlot("armor/Front_plate");
api.equipItem("plateM");                   // 护甲板也是「实际安装的物品」
api.selectSlot("armor");
var t16b = api.gearTotals();
check("T16 护甲板计入件数 / 重量 / 移动减益",
  t16b.count === 5 && Math.abs(t16b.weight - (0.1 + 3 + 1 + 8 + 2)) < 1e-9 &&
  t16b.speed === -3);
api.selectSlot("armor/Front_plate");
api.clearGearSlot("armor/Front_plate");    // 卸下插板 → 减益与重量同步回退
var t16c = api.gearTotals();
check("T16 卸下插板后减益 / 重量 / 件数同步回退",
  t16c.count === 4 && t16c.speed === -2 && Math.abs(t16c.weight - (0.1 + 3 + 1 + 8)) < 1e-9);
check("T16 固定内衬不重复计入（素护甲只有 1 件）",
  (function () {
    reset();
    api.selectSlot("armor");
    api.equipItem("armorPlain");           // 仅有固定内衬，内衬不在 loadout 里
    return api.gearTotals().count === 1;
  })());
check("T16 固定内衬的减益不叠加到父装备（素护甲只按自身计入）",
  (function () {
    reset();
    api.selectSlot("armor");
    api.equipItem("armorA");
    var a = api.gearTotals();
    api.selectSlot("armor/Front_plate");
    api.equipItem("plateM");               // 装板后只多一件，不因内衬结构重复计
    api.selectSlot("armor");
    return api.gearTotals().count === a.count + 1;
  })());

/* T17 获取方式（第六项）：多来源共存 / 未知与确认不可获得明确区分 / 只用构建期 src（不联网） */
reset();
api.selectSlot("helmet");
check("T17 多来源全部展示（跳蚤 + 商人购买，不强行只留一个）",
  api.accessText(["flea", "trader"]) === "跳蚤市场购买 / 商人购买");
check("T17 三种来源可共存",
  api.accessText(["flea", "trader", "barter"]) === "跳蚤市场购买 / 商人购买 / 商人兑换");
check("T17 确认不可获得有独立文案", api.accessText(["none"]) === "以上方式不可获得");
check("T17 数据缺失 / 无法判断 → 数据未确认（不误判成不可获得）",
  api.accessText(["unknown"]) === "数据未确认" && api.accessText(null) === "数据未确认" &&
  api.accessText([]) === "数据未确认");
check("T17 状态类别区分 none / unknown / ok",
  api.accessKind(["none"]) === "none" && api.accessKind(["unknown"]) === "unknown" &&
  api.accessKind(["flea"]) === "ok" && api.accessKind(undefined) === "unknown");
check("T17 行数据带 srcText / srcKind（多来源）",
  rowOf("helmetA").srcText === "跳蚤市场购买 / 商人购买" && rowOf("helmetA").srcKind === "ok");
check("T17 确认不可获得的候选标 none", rowOf("helmetPlain").srcKind === "none");
check("T17 没有 src 字段的物品按「数据未确认」处理（不误判为不可获得）", (function () {
  api.selectSlot("headphones");
  return rowOf("hp2").srcText === "数据未确认" && rowOf("hp2").srcKind === "unknown";
})());

/* T18 防护区域本地图标（第七项；R31.1 组件化）：词集合规范化 → 完全一致才命中；对不上就文字降级 */
function cell18() { return { children: [], appendChild: function (c) { this.children.push(c); return c; } }; }
check("T18 词集合键按固定词序规范化（R31.2：下胸并入腹部、上背并入上胸，正反面统一）",
  api.zoneIconKey(["LeftSideChestDown", "RibcageLow", "RibcageUp"]) === "上胸|腹部|侧面");
check("T18 组合部位命中组合图（上胸+腹部，按数据自动生成入库）",
  api.zoneIconFile(["RibcageUp", "RibcageLow"]) === "assets/icons/zones/zone-chest-abdomen.png");
check("T18 组合部位命中组合图（上胸+腹部+裆部，按数据自动生成入库）",
  api.zoneIconFile(["RibcageUp", "RibcageLow", "Pelvis"]) === "assets/icons/zones/zone-chest-abdomen-groin.png");
check("T18 没有对应组合图 → null（不做模糊匹配、不拿别的图顶替；数据里不存在 肩部|耳部 组合）",
  api.zoneIconFile(["LeftUpperArm", "Ears"]) === null);
check("T18 正反面统一：上背/后插板映射到上胸，不再视为图上缺失",
  api.zoneWordsUnmapped(["RibcageUp", "SpineTop", "Plate_6B13_back"]).join(",") === "");
check("T18 仍如实标出无法投影的 zone（防御性：用不存在的 zone 校验）",
  api.zoneWordsUnmapped(["__nonexistent_zone__"]).join(",") === "__nonexistent_zone__");
check("T18 完全没有 zone 的物品既不命中也不误报", api.zoneIconFile([]) === null &&
  api.zoneWordsUnmapped([]).length === 0);
api.selectSlot("armor");
check("T18 护甲行带本地图标路径（上胸+腹部 并入同一胸区图）",
  rowOf("armorA").zoneIcon === "assets/icons/zones/zone-chest-abdomen.png");
check("T18 正反面统一后护甲A不再标『图上缺失』（上背已并入上胸图）",
  rowOf("armorA").zoneUnmapped.join(",") === "");
check("T18 无防护区域的护甲行显示『未穿护甲』底图（R31.4，不再是一个『—』）",
  rowOf("armorPlain").zoneIcon === "assets/icons/zones/zone-base.png");
check("T18 悬停文案仍是完整中文部位名", rowOf("armorA").zoneText === "上胸、下胸、上背");
api.equipItem("armorA");
api.selectSlot("armor/Front_plate");
check("T18 插板行同样走本地图标", rowOf("plateS").zoneIcon === "assets/icons/zones/zone-chest-abdomen.png");
var zcell18 = cell18();
api.renderZoneCell(zcell18, rowOf("plateS"));
check("T18 命中图标时渲染本地 img（class=tbl-zone-ico + 中文悬停）",
  zcell18.children.length === 1 && zcell18.children[0].tagName === "IMG" &&
  zcell18.children[0].className === "tbl-zone-ico" &&
  zcell18.children[0].src === "assets/icons/zones/zone-chest-abdomen.png" &&
  zcell18.children[0].title.indexOf("上胸") >= 0);
/* 正反面统一后：含上背的护甲直接命中对应部位图（胸区合并图），图上不再单列『＋上背』；
   上背仍保留在中文悬停文案里，正反面信息不丢 */
api.selectSlot("armor");
var zcell18a = cell18();
api.renderZoneCell(zcell18a, rowOf("armorA"));
check("T18 正反面统一：含上背的护甲命中共用图（不再补『＋上背』小字）",
  zcell18a.children.length === 1 && zcell18a.children[0].tagName === "IMG" &&
  zcell18a.children[0].className === "tbl-zone-ico" &&
  zcell18a.children[0].src === "assets/icons/zones/zone-chest-abdomen.png" &&
  zcell18a.children[0].title.indexOf("上背") >= 0);
/* 命中图标但物品还防到图上没画的部位 → 图标后补标小字（防御性路径：合成数据校验渲染） */
var zcell18a2 = cell18();
api.renderZoneCell(zcell18a2, { zoneIcon: "assets/icons/zones/zone-chest.png", zoneText: "上胸、上背", zoneUnmapped: ["SpineTop"] });
check("T18 命中图标且含图上未画部位时补标小字（合成数据）",
  zcell18a2.children.length === 2 && zcell18a2.children[0].tagName === "IMG" &&
  zcell18a2.children[1].tagName === "SPAN" &&
  zcell18a2.children[1].className === "tbl-zone-more" &&
  zcell18a2.children[1].textContent.indexOf("上背") >= 0);
var zcell18b = cell18();
api.renderZoneCell(zcell18b, { zoneIcon: null, zoneText: "面部、下颚", zoneUnmapped: [] });
check("T18 缺图标时文字降级（span 显示中文部位名，不加任何图标）",
  zcell18b.children.length === 1 && zcell18b.children[0].tagName === "SPAN" &&
  zcell18b.children[0].textContent === "面部、下颚");
check("T18 文字降级的长清单也悬停给完整中文部位名（避免被列宽截断后看不全）",
  zcell18b.children[0].title === "面部、下颚");
var zcell18c = cell18();
api.renderZoneCell(zcell18c, { zoneIcon: null, zoneText: "上胸、上背", zoneUnmapped: ["SpineTop"] });
check("T18 文字降级时悬停说明原因", zcell18c.children[0].title.indexOf("文字降级") >= 0 &&
  zcell18c.children[0].title.indexOf("上背") >= 0);
var zmap18 = api.zoneIconAudit();
check("T18 映射审计：本地图 ≥37 张映射按新词表命中可复核，旧词『胸部/颈部/腹股沟』已退役",
  zmap18.icons >= 37 && zmap18.withIcon >= 1 && zmap18.fallback >= 0 && zmap18.noZone >= 0 &&
  !Object.keys(zmap18.used).some(function (k) { return /胸部|颈部|腹股沟/.test(k); }));

/* T19 装甲胸挂归防弹衣槽（R22.2 参考站 Armor Armored Rig 口径）；与胸挂互斥 */
reset();
api.selectSlot("armor");
var t19Armor = sorted(api.candidatesOf(node("armor"))).join(",");
check("T19 防弹衣槽候选含装甲胸挂（参考站 Armor Armored Rig 口径）",
  t19Armor.indexOf("rigArmored") >= 0);
check("T19 防弹衣槽候选不含普通胸挂 rigA / rigPlain",
  api.candidatesOf(node("armor")).indexOf("rigA") < 0 &&
  api.candidatesOf(node("armor")).indexOf("rigPlain") < 0);
check("T19 错类护甲 cat=rig 但 slot=armor → 只进防弹衣槽",
  api.candidatesOf(node("armor")).indexOf("armorMisCat") >= 0);
check("T19 防弹衣槽候选来源写明装甲胸挂归防弹衣槽",
  api.candidateSource(node("armor")).indexOf('slot === "armor"') >= 0);

api.selectSlot("rig");
var t19Rig = sorted(api.candidatesOf(node("rig"))).join(",");
check("T19 胸挂槽候选不含装甲胸挂（已归防弹衣槽）",
  t19Rig.indexOf("rigArmored") < 0);
check("T19 胸挂槽候选不含只属于防弹衣槽的 armorA / armorMisCat",
  api.candidatesOf(node("rig")).indexOf("armorA") < 0 &&
  api.candidatesOf(node("rig")).indexOf("armorMisCat") < 0);
check("T19 胸挂槽候选来源写明排除装甲胸挂",
  api.candidateSource(node("rig")).indexOf('slot === "rig"') >= 0);

/* 装甲胸挂 ↔ 胸挂互斥：胸挂候选红 + 禁装；防弹衣不受影响 */
reset();
api.selectSlot("armor");
api.equipItem("rigArmored");
api.selectSlot("rig");
var t19RowsRig = api.gearRows();
var t19RowPlain = rowIn(t19RowsRig, "rigPlain");
var t19RowA = rowIn(t19RowsRig, "rigA");
check("T19 已穿装甲弹挂时：胸挂候选红 + 禁装 + 原因可读",
  t19RowPlain && t19RowPlain.conflict === true && t19RowPlain.blocked === true &&
  t19RowPlain.conflictText.indexOf("互斥") >= 0);
check("T19 已穿装甲弹挂时：所有胸挂都被禁",
  t19RowA && t19RowA.conflict === true);
api.equipItem("rigPlain");
check("T19 红态胸挂点它装不上，装甲弹挂仍在",
  !state.loadout.rig && state.loadout.armor === "rigArmored");

/* 卸下装甲弹挂 → 胸挂候选红态解除（候选按当前已装备重算，不复用旧结果） */
api.selectSlot("armor");
api.clearGearSlot("armor");
api.selectSlot("rig");
check("T19 卸下装甲弹挂后：胸挂红态解除、可装",
  rowIn(api.gearRows(), "rigPlain").conflict === false);
api.equipItem("rigPlain");
check("T19 卸甲后胸挂可以真的装上", state.loadout.rig === "rigPlain");

/* 替换父装备 → 子槽按新槽位定义重算，不复用前一个父装备的结果 */
reset();
api.selectSlot("helmet");
api.equipItem("helmetA");                     // 头盔A 带 nvg + mount 两个子槽
var t19KidsA = kids("helmet").join(",");
api.equipItem("helmetC");                     // 头盔C 只有 mount 一个子槽 → nvg 必须随换装消失
var t19KidsC = kids("helmet").join(",");
check("T19 替换父装备后子槽按新槽位重算（旧 nvg 子槽不再残留）",
  t19KidsA.indexOf("nvg") >= 0 && t19KidsC.indexOf("nvg") < 0);

/* T20 第五轮：逐笔获取方式（跳蚤 / 商人购买 / 商人兑换）各自成条，不合并、不猜测 */
reset();
state.traders = { prapor: { n: "Prapor", nn: "prapor" },
                  ragman: { n: "Ragman", nn: "ragman" } };
state.tasks = { task1: "测试任务" };
state.items.tradeMulti = { n: "多来源物品", cat: "backpack", ts: ["backpack"], pt: "Backpack",
  w: 2, p: { a: 1000 }, src: ["flea", "trader"],
  trade: [{ k: "flea" },
          { k: "buy", t: "prapor", l: 4, c: "RUB", p: 1000, u: "task1" },
          { k: "barter", t: "ragman", l: 2, r: [["plateM", 2]], o: 1 }] };
var tv = api.tradeViews(state.items.tradeMulti);
check("T20 三种来源各自成条（3 条，不合并）",
  tv.length === 3 && tv[0].k === "flea" && tv[1].k === "buy" && tv[2].k === "barter");
check("T20 购买条：游戏素材商人头像（portraits/{id}.webp）+ 罗马数字 IV",
  tv[1].icon === "assets/icons-traders/portraits/prapor.webp" && tv[1].level === "IV");
/* R23.2：按用户决定（学术研究/非商用）改用游戏素材头像；自绘 .svg 退为加载失败兜底 */
check("T20 商人头像走游戏素材 .webp，且带自绘 .svg 兜底地址",
  tv[1].icon.indexOf("/portraits/") >= 0 && tv[1].icon.indexOf(".webp") >= 0 &&
  tv[1].iconFallback === "assets/icons-traders/prapor.svg" &&
  tv[2].icon.indexOf("/portraits/") >= 0 &&
  tv[2].iconFallback === "assets/icons-traders/ragman.svg");
check("T20 购买浮窗含商人/等级/交易类型/价格/任务",
  tv[1].tip.indexOf("Prapor LL4") >= 0 && tv[1].tip.indexOf("解锁购买") >= 0 &&
  tv[1].tip.indexOf("测试任务") >= 0);
check("T20 兑换条：罗马数字 II + 配方物品与数量",
  tv[2].level === "II" && tv[2].tip.indexOf("Ragman LL2") >= 0 &&
  tv[2].tip.indexOf("解锁兑换配方") >= 0 && tv[2].tip.indexOf("2 × 中插板") >= 0);
check("T20 跳蚤条用本地跳蚤图标，不联网",
  tv[0].icon === "assets/icons-traders/flea.svg");
check("T20 罗马数字映射 LL1–LL6 → I–VI（参考图插板等级到 VI）",
  api.romanLevel(1) === "I" && api.romanLevel(2) === "II" &&
  api.romanLevel(3) === "III" && api.romanLevel(4) === "IV" &&
  api.romanLevel(5) === "V" && api.romanLevel(6) === "VI");
/* 数据缺失 / 确认不可获得必须是两种不同状态，不得混为一谈 */
var tvNone = api.tradeViews({ n: "确认不可获得", src: ["none"] });
var tvUnknown = api.tradeViews({ n: "来源未知" });
check("T20 确认不可获得 → none 状态（不是 unknown）",
  tvNone.length === 1 && tvNone[0].k === "none" && tvNone[0].tone === "none");
check("T20 数据缺失 → unknown 状态（不误判为不可获得）",
  tvUnknown.length === 1 && tvUnknown[0].k === "unknown" && tvUnknown[0].tone === "unknown");
check("T20 商人 id 缺失时头像回退本地 unknown.svg（不联网）",
  api.tradeViews({ n: "x", trade: [{ k: "buy", t: "nope", l: 1 }] })[0].icon ===
  "assets/icons-traders/unknown.svg");

/* T21 第五轮：护甲四个板位（前/后/左/右）按真实 aps 槽位出状态 */
reset();
var plateStates = api.plateSlotStates("armorA", "armor", state.items.armorA);
check("T21 四个板位键固定为 front/back/left/right",
  plateStates.map(function (s) { return s.key; }).join(",") === "front,back,left,right");
check("T21 前/后板位存在且未安装，左/右不可用",
  plateStates[0].state === "empty" && plateStates[1].state === "empty" &&
  plateStates[2].state === "na" && plateStates[3].state === "na");
check("T21 板位槽 id 带位置含义（根槽位/zone）",
  plateStates[0].slotId === "armor/Front_plate");
state.loadout.armor = "armorA";
state.loadout["armor/Front_plate@armorA"] = "plateS";   // R19.26：键带护甲身份
var plateOn = api.plateSlotStates("armorA", "armor", state.items.armorA);
check("T21 装上插板后前板位变 on 并给出插板 id",
  plateOn[0].state === "on" && plateOn[0].plate === "plateS");
check("T21 无硬板位的护甲：前板位 na（整格空白），板位状态**不再**携带内衬字段（第十轮）",
  (function () {
    var st = api.plateSlotState("armorPlain", "armor", state.items.armorPlain, api.PLATE_COL_ZONES[0]);
    return st.state === "na" && st.liner === undefined && st.linerText === undefined;
  })());
check("T21 无硬板位也无内衬的列整格不可用（na）",
  api.plateSlotState("armorPlain", "armor", state.items.armorPlain, api.PLATE_COL_ZONES[2]).state === "na" &&
  api.plateSlotState("armorPlain", "armor", state.items.armorPlain, api.PLATE_COL_ZONES[2]).socket === null);

/* T22 第五轮第五节：右侧列集按类别分别生成（不再共用同一模板），但统一骨架一致：
   名称 → 冲突 → 类别专属列 → 重量 → 价格 → 获取方式（永远最右一列）。 */
reset();
function colKeys(slot) {
  return api.gearColumns(node(slot), "flea").map(function (c) { return c.key; });
}
var kArmor = colKeys("armor"), kRig = colKeys("rig"), kBag = colKeys("backpack"),
    kHp = colKeys("headphones"), kGlasses = colKeys("glasses"), kFace = colKeys("face"),
    kHelmet = colKeys("helmet"), kMelee = colKeys("melee"),
    kArmband = colKeys("armband"), kDogtag = colKeys("dogtag");
/* R22.0 逐类属性列对齐参考站 db4（「按 db4 来」）：armor=插板+Material+Eff+内衬+Zone+Cap/SE/Slots；
   rig=参考站 Chest Rig 口径（Cap/SE/Slots，不再套护甲插板/内衬版式）；其余按各自参考站列集。
   R219：获取方式回到**末列合并格**（跳蚤/商人/兑换/制作的图标 + 价格 + 商人等级），
   R74 拆出来的「跳蚤 24h / 7d 均价」两列已撤掉；冲突走整行标红（无独立冲突列）。 */
var T20_COLS = "n,pen,plate_front,plate_back,plate_left,plate_right,matLabel,effDur," +
  "liner_front,liner_back,liner_left,liner_right,liner_collar,liner_shoulder_l," +
  "liner_shoulder_r,liner_groin,liner_groin_back,zoneIco,cap,se,slots,w,srcGroup";
check("T22 护甲列集 = 参考站 Armor/Armored Rig 口径（插板+Material+Eff+内衬+Zone+Cap/SE/Slots）+ 末列获取方式（格内带价格）",
  kArmor.join(",") === T20_COLS);
check("T22 胸挂列集 = 参考站 Chest Rig 口径（Cap/SE/Slots，不再套护甲版式）+ 末列获取方式",
  kRig.join(",") === "n,pen,cap,se,slots,w,srcGroup");
check("T20 护甲列里恰好 4 个板位列 + 9 个内衬列 + 1 个防护图标列 + Cap/SE/Slots（无冲突列）",
  kArmor.filter(function (k) { return k.indexOf("plate_") === 0; }).length === 4 &&
  kArmor.filter(function (k) { return k.indexOf("liner_") === 0; }).length === 9 &&
  kArmor.indexOf("zoneIco") >= 0 && kArmor.indexOf("cap") >= 0 &&
  kArmor.indexOf("se") >= 0 && kArmor.indexOf("slots") >= 0 &&
  kArmor.indexOf("srcGroup") === kArmor.length - 1 && kArmor.indexOf("conflict") < 0 &&
  kArmor.indexOf("zoneText") < 0);
check("T22 背包列集：名称/减益/排除物品/容量/空间效率/槽位/重量/获取方式（R300 去掉仅允许列）",
  kBag.join(",") === "n,pen,glExcl,cap,se,slots,w,srcGroup");
check("T22 耳机列集：距离/环境音量/干音量/失真（四参数，参考站无减益列）+ 末列获取方式",
  kHp.join(",") === "n,hpd,hpa,hpdv,hpr,w,srcGroup");
check("T22 眼镜列集：名称/减益/防护区域/重量/获取方式（R79 补眼部防护列，价格在末列格内）",
  kGlasses.join(",") === "n,pen,zoneIco,w,srcGroup");
check("T22 护面列集：名称/减益/防护区域/重量/互斥物品/获取方式（R79 补眼部防护列，价格在末列格内）",
  kFace.join(",") === "n,pen,zoneIco,w,conflictCount,srcGroup");
check("T22 头盔列集：名称/减益/跳弹角/Material/Eff/防护区域/听力衰减/重量/获取方式（无板位，价格在末列格内）",
  kHelmet.indexOf("plate_front") < 0 && kHelmet.join(",") ===
    "n,pen,rcz,matLabel,effDur,zoneText,df,w,srcGroup");
check("T22 近战列集：类型/减益/重量/末列获取方式（价格在格内）",
  kMelee.join(",") === "n,ptLabel,pen,w,srcGroup");
check("T22 臂带列集 = 名称/重量/获取方式",
  kArmband.join(",") === "n,w,srcGroup");
check("T22 狗牌列集 = 名称/重量/获取方式",
  kDogtag.join(",") === "n,w,srcGroup");
check("R219：每个类别的最后一列都是获取方式（价格并回格内，表尾不再有独立价格列）",
  [kArmor, kRig, kBag, kHp, kGlasses, kFace, kHelmet, kMelee, kArmband, kDogtag].every(function (k) {
    return k[k.length - 1] === "srcGroup" &&
      k.indexOf("p24") < 0 && k.indexOf("p7d") < 0;
  }));
check("T22 类别之间确实不同（不是同一套模板换标题）",
  kBag.join(",") !== kHp.join(",") && kHp.join(",") !== kFace.join(",") &&
  kFace.join(",") !== kHelmet.join(",") && kHelmet.join(",") !== kArmor.join(",") &&
  kArmor.join(",") !== kRig.join(","));
/* 插板候选窗（kind=plate）：列集与护甲同源（Material/Eff/防护区域），去掉板位/槽位，
   获取方式列放末尾（格内带价格，与主表同口径）。 */
reset();
api.selectSlot("armor");
api.equipItem("armorA");          // 板位节点随父护甲建立
var plateNode = node("armor/Front_plate");
check("T22 插板候选窗 exists（护甲根槽位下有板位节点）", !!plateNode && plateNode.kind === "plate");
if (plateNode) {
  check("T22 插板候选窗列集：与护甲同源但去板位/槽位，获取方式列在末尾",
    api.gearColumns(plateNode, "flea").map(function (c) { return c.key; }).join(",") ===
      "n,cl,dur,w,matLabel,destr,effDur,zoneText,srcGroup");
}
/* 无选中节点（旧调用方）→ 「名称/类型/重量/获取方式」兜底（价格在末列格内） */
check("T22 无节点兜底列集 = 名称/类型/重量/末列获取方式",
  api.gearColumns(null, "flea").map(function (c) { return c.key; }).join(",") ===
    "n,ptLabel,w,srcGroup");

/* T30 第十轮：内衬独立列模型（linerBreakdown）+ 行级 liners + 最高防弹等级角标 +
   逐笔来源视图（tradeView/tradeViews 仍携带价格/配方摘要，供悬停与其它调用方使用）。 */
reset();
/* (a) linerBreakdown：九个 zone 归位、材质汇总、总耐久与有效耐久（逐块 dur ÷ d 再相加） */
var lbA = api.linerBreakdown(state.items.armorPlain);   // Aramid 前内衬 cl2 dur40
check("T30 内衬分解：前内衬归位（等级/材质/耐久）",
  lbA.zones.front && lbA.zones.front.cl === 2 && lbA.zones.front.dur === 40);
check("T30 内衬分解：有效耐久 = dur ÷ 材质毁损系数（40 ÷ 0.25 = 160）",
  Math.round(lbA.zones.front.eff) === 160);
check("T30 内衬分解：总耐久 40 / 有效耐久总和 160 / 材质名芳纶",
  lbA.total === 40 && Math.round(lbA.eff) === 160 &&
  lbA.matLabels.join("/") === api.materialLabel("Aramid"));
check("T30 内衬分解：未覆盖的内衬列都是 undefined（不造「—」以外的假值）",
  !lbA.zones.back && !lbA.zones.groin && !lbA.zones.groin_back);
check("T30 内衬分解：九列映射之外 fx 区进 unmatched（不塞进相近列）",
  (function () {
    var lb = api.linerBreakdown({ aps: [
      { zone: "Soft_armor_pelvis", fx: 1, mat: "Aramid", cl: 2, dur: 10 },
      { zone: "soft_armor_front", fx: 1, mat: "Aramid", cl: 3, dur: 45 }] });
    return lb.unmatched.join(",") === "Soft_armor_pelvis" &&
      lb.zones.front && lb.zones.front.dur === 45 && lb.total === 45;
  })());
check("T30 内衬分解：zone 匹配大小写无关（上游 Soft_armor_right / soft_armor_front 并存）",
  (function () {
    var lb = api.linerBreakdown({ aps: [
      { zone: "Soft_armor_right", fx: 1, mat: "Ceramic", cl: 4, dur: 30 },
      { zone: "SOFT_ARMOR_LEFT", fx: 1, mat: "Ceramic", cl: 4, dur: 28 }] });
    return lb.zones.right && lb.zones.right.dur === 30 &&
      lb.zones.left && lb.zones.left.dur === 28 && lb.total === 58;
  })());
check("T30 内衬分解：只有映射不到的内衬时 total 不造假 0（null）",
  (function () {
    var lb = api.linerBreakdown({ aps: [
      { zone: "Soft_armor_pelvis", fx: 1, mat: "Aramid", cl: 2, dur: 10 }] });
    return lb.total === null && lb.eff === null && lb.unmatched.length === 1;
  })());
/* (b) armor/rig 候选行携带 liners；普通类别（背包等）不携带 */
api.selectSlot("armor");
var armorRow = rowOf("armorPlain");
check("T30 护甲候选行携带内衬分解（行级 liners.total）",
  armorRow && armorRow.liners && armorRow.liners.total === 40);
api.selectSlot("backpack");
check("T30 背包候选行不携带内衬分解（20 列只属 armor/rig）",
  rowOf("bagA") && rowOf("bagA").liners === null);
/* (c) maxArmorClassOf：本体 vs. 已装硬插板取最高；候选/未装不算；空槽 0 */
api.selectSlot("armor");
api.equipItem("armorA");                    // 本体 cl=4
check("T30 最高防弹等级：无插板时 = 本体等级 4", api.maxArmorClassOf("armor") === 4);
state.loadout["armor/Front_plate@armorA"] = "plateM";   // 前板 cl=5（R19.26 稳定身份键）
check("T30 最高防弹等级：插板高于本体时取插板 5", api.maxArmorClassOf("armor") === 5);
state.loadout["armor/Front_plate@armorA"] = "plateS";   // 前板 cl=3
check("T30 最高防弹等级：插板低于本体时仍取本体 4", api.maxArmorClassOf("armor") === 4);
delete state.loadout["armor/Front_plate@armorA"];
api.clearGearSlot("armor");
check("T30 最高防弹等级：空槽返回 0（不显示假数字）", api.maxArmorClassOf("armor") === 0);
/* (d) 逐笔来源视图：tradeView 仍携带价格/币种/配方摘要（格内不再展示，价格列与悬停各自取用） */
check("T30 tradeView 市场价随当前价格档（24h 均价档取 a）",
  api.tradeView({ k: "flea" }, { p: { a: 12345 } }).price === 12345);
check("T30 tradeView 商人直购带价格与币种",
  (function () {
    var v = api.tradeView({ k: "buy", t: "nope", l: 2, p: 3000, c: "RUB" }, null);
    return v.price === 3000 && v.cur === "RUB" && v.level === "II";
  })());
check("T30 tradeView 兑换配方摘要 = 数量×物品名（不用卢布价冒充）",
  api.tradeView({ k: "barter", t: "nope", l: 1, r: [["plateS", 2], ["plateM", 1]], o: 1 }, null)
    .reqText === "2×小插板 + 1×中插板");
check("T30 row.srcKind：src 与逐笔 trade 矛盾时以确认渠道为准（6B43 型数据）",
  (function () {
    /* armorMisCat 在 fixture 里带 src 缺省（无 src 字段 → accessKind 走 unknown/none 路径）
       但补了一条确认兑换配方（trade 数组）→ 行的 srcKind 必须是 ok，渠道与配方都要在。 */
    var r = rowOf("armorMisCat");
    return !!r && r.srcKind === "ok" && r.trades.length === 1 &&
      r.trades[0].k === "barter" && r.trades[0].reqText === "2×小插板";
  })());
check("T30 row.srcKind：既无逐笔渠道又标记 none 的行才落到 none",
  (function () {
    var tv = api.tradeViews({ src: ["none"], trade: [] });
    return tv.length === 1 && tv[0].k === "none";
  })());

/* T23 第七轮：四部位局部减益 = 本部位本体 + 已装可拆卸组件；固定内衬不在 loadout，不重复计；
   局部统计与全身统计各自独立，互不替代。 */
reset();
state.items.localHelm = { n: "局部头盔", cat: "helmet", ts: ["helmet"], pt: "Helmet", w: 2, p: { a: 100 },
  pen: { s: -0.01, t: -0.03, e: -0.02 },
  slots: [{ id: "nvg", sid: "mod_nvg", label: "支架", allow: ["localNvg"] }],
  aps: [{ zone: "Helmet_top", fx: 1, mat: "Ceramic", cl: 3, dur: 30, z: ["ParietalHead"] }] };
state.items.localNvg = { n: "局部夜视仪", ts: ["mods"], pt: "NightVision", w: 0.5, p: { a: 200 },
  pen: { s: -0.02, t: -0.01, e: -0.03 } };
api.selectSlot("helmet");
api.equipItem("localHelm");
api.selectSlot("helmet/nvg");
api.equipItem("localNvg");
var lp1 = api.slotLocalPen("helmet");
check("T23 头盔局部减益计入本体 + 已装附件（两件）", lp1.count === 2);
check("T23 头盔局部减益数值 = 本体 + 附件的逐项之和",
  Math.abs(lp1.speed + 0.03) < 1e-9 && Math.abs(lp1.turn + 0.04) < 1e-9 &&
  Math.abs(lp1.ergo + 0.05) < 1e-9);
check("T23 固定内衬没有混进局部统计（内衬不是 loadout 条目）",
  (function () {
    for (var k in state.loadout) { if (k.indexOf("Helmet_top") >= 0) { return false; } }
    return lp1.count === 2;
  })());
var gy1 = api.gearTotals();
check("T23 该头盔局部合计与全身合计同源同值",
  Math.abs(gy1.speed - lp1.speed) < 1e-9 && Math.abs(gy1.turn - lp1.turn) < 1e-9 &&
  Math.abs(gy1.ergo - lp1.ergo) < 1e-9);
api.selectSlot("glasses");
api.equipItem("glasses1");
var lp2 = api.slotLocalPen("helmet"), gy2 = api.gearTotals();
check("T23 装上眼镜后头盔局部减益不变（部位之间不串算）",
  Math.abs(lp2.speed - lp1.speed) < 1e-9 && Math.abs(lp2.turn - lp1.turn) < 1e-9);
check("T23 同时全身合计已含眼镜（局部 ≠ 全身）",
  Math.abs(gy2.speed - (lp2.speed + api.slotLocalPen("glasses").speed)) < 1e-9 &&
  gy2.speed !== lp2.speed);
check("T23 未装装备的部位局部合计为空（count=0，界面不显示减益条）",
  api.slotLocalPen("rig").count === 0);

/* T23b 第九轮问题2：背包局部减益（LW_DEBUFF_KEYS 新增 backpack，复用 armor/rig 同一套机制） */
reset();
state.items.bagPen = { n: "减益背包", cat: "backpack", ts: ["backpack"], pt: "Backpack",
  gw: 4, gh: 4, w: 2.5, p: { a: 1200 }, pen: { s: -0.02, t: -0.01, e: -0.03 } };
api.selectSlot("backpack");
api.equipItem("bagPen");
var lpBag = api.slotLocalPen("backpack");
check("T23b 背包局部减益计入本体（移动/转身/人机与物品 pen 一致）",
  lpBag.count === 1 && Math.abs(lpBag.speed + 0.02) < 1e-9 &&
  Math.abs(lpBag.turn + 0.01) < 1e-9 && Math.abs(lpBag.ergo + 0.03) < 1e-9);
check("T23b 背包减益同时进入全身合计（同源不重复计）",
  (function () {
    var g = api.gearTotals();
    return g.count === 1 && Math.abs(g.speed + 0.02) < 1e-9;
  })());
api.clearGearSlot("backpack");
check("T23b 卸下背包后局部减益清空", api.slotLocalPen("backpack").count === 0);
api.selectSlot("backpack");
api.equipItem("bagPen");
check("T23b 重装背包后局部减益恢复",
  (function () {
    var lp = api.slotLocalPen("backpack");
    return lp.count === 1 && Math.abs(lp.ergo + 0.03) < 1e-9;
  })());

/* T24 第七轮 5.3：逐类别默认列宽（名称列 minmax 吃掉余量，其余固定 px），
   默认值不覆盖用户拖动后的持久化宽度。 */
reset();
var colOf = function (nodeObj, key) {
  var cs = api.gearColumns(nodeObj, "flea");
  for (var i = 0; i < cs.length; i++) { if (cs[i].key === key) { return cs[i]; } }
  return null;
};
check("T24 护甲名称列默认宽度来自 armor 类别（固定 230px，表头与数据行列边界一致）",
  colOf(node("armor"), "n").width === "230px");
check("T24 头盔名称列与护甲不同（逐类别独立）",
  colOf(node("helmet"), "n").width === "210px");
check("T24 护甲列使用紧凑固定宽度（插板/内衬/防护/Cap/SE/Slots/重量/末列获取方式均有列宽）",
  !!colOf(node("armor"), "plate_front") && !!colOf(node("armor"), "plate_front").width &&
  !!colOf(node("armor"), "liner_front") && !!colOf(node("armor"), "liner_front").width &&
  !!colOf(node("armor"), "zoneIco") && !!colOf(node("armor"), "zoneIco").width &&
  !!colOf(node("armor"), "cap") && !!colOf(node("armor"), "cap").width &&
  !!colOf(node("armor"), "se") && !!colOf(node("armor"), "se").width &&
  !!colOf(node("armor"), "slots") && !!colOf(node("armor"), "slots").width &&
  !!colOf(node("armor"), "srcGroup") && !!colOf(node("armor"), "srcGroup").width);
check("T24 背包 / 耳机默认列宽各自独立",
  colOf(node("backpack"), "cap").width === "52px" &&
  colOf(node("headphones"), "hpd").width === "62px");
check("T24 每个类别都有默认列宽表（护甲/头盔/胸挂/背包/耳机/眼镜/护面/插板/枪械/近战）",
  ["armor", "helmet", "rig", "backpack", "headphones", "glasses", "face", "plate", "gun", "melee"]
    .every(function (k) { return !!api.LW_COL_DEFAULTS[k]; }));
check("T24 未知列保留列自带宽度（不被默认表清空）",
  (function () {
    var cols = api.applyColDefaults("armor", [{ key: "unknownCol", width: "123px" }]);
    return cols[0].width === "123px";
  })());
/* 默认值只影响「没拖过」的列：用户拖动后的宽度仍由 colWidthFor 优先返回 */
state.colWidths = { byCat: {}, shared: {} };
api.saveColWidth(node("armor"), { key: "n" }, 300);
check("T24 用户自定义列宽优先于类别默认值",
  api.colWidthFor(node("armor"), { key: "n" }) === 300 &&
  colOf(node("armor"), "n").width === "230px");

/* T25 第八轮：左栏已装卡片右键卸除。
   右键只做两件事：拦截默认菜单 + 复用 clearGearSlot；空槽不拦截、不改变任何状态。 */
function ctx(slotKey) {
  var ev = { prevented: false, preventDefault: function () { this.prevented = true; } };
  var handled = api.unequipByContextMenu(ev, slotKey);
  return { handled: handled, prevented: ev.prevented };
}
/* (1) 普通已装物品 */
reset();
api.selectSlot("rig"); api.equipItem("rigA");
var t25w0 = api.gearTotals().weight, t25c0 = api.gearTotals().count;
var t25r1 = ctx("rig");
check("T25.1 右键已装普通物品：卸除成功、并拦截浏览器默认菜单",
  t25r1.handled === true && t25r1.prevented === true && !state.loadout.rig);
check("T25.1 卸除后全身重量与件数立即回落",
  api.gearTotals().weight < t25w0 && api.gearTotals().count === t25c0 - 1);
/* (2) 空槽 */
var t25f0 = state.focus, t25k0 = Object.keys(state.loadout).join(",");
var t25r2 = ctx("backpack");
check("T25.2 右键空槽：不改状态、也不拦截默认菜单",
  t25r2.handled === false && t25r2.prevented === false &&
  Object.keys(state.loadout).join(",") === t25k0 && state.focus === t25f0);
/* (3) 左键语义不变：选中仍是 selectSlot，右键不抢焦点 */
api.selectSlot("headphones");
api.selectSlot("helmet"); api.equipItem("helmetA");
api.selectSlot("headphones");
var t25f1 = state.focus;
ctx("helmet");
check("T25.3 右键卸除不改变当前选中槽位（左键 selectSlot 语义独立）",
  t25f1 === "headphones" && state.focus === "headphones");
/* (4) 头盔附件 */
reset();
api.selectSlot("helmet"); api.equipItem("helmetA");
api.selectSlot("helmet/nvg"); api.equipItem("nvg1");
var t25r4 = ctx("helmet/nvg");
check("T25.4 右键卸除头盔附件：附件清掉、父装备保留、子槽仍在",
  t25r4.handled && !state.loadout["helmet/nvg"] && state.loadout.helmet === "helmetA" &&
  !!node("helmet/nvg"));
/* (5) 带子槽的父装备 */
api.selectSlot("helmet/nvg"); api.equipItem("nvg1");
var t25r5 = ctx("helmet");
check("T25.5 右键卸除带附件的父装备：父子一起清掉，无孤立引用",
  t25r5.handled && !state.loadout.helmet &&
  Object.keys(state.loadout).every(function (k) { return k.indexOf("helmet/") !== 0; }) &&
  !node("helmet/nvg"));
/* (6) 已装插板的防弹衣 */
reset();
api.selectSlot("armor"); api.equipItem("armorA");
api.selectSlot("armor/Front_plate"); api.equipItem("plateS");
var t25w6 = api.gearTotals().weight;
check("T25.6 前置条件：护甲与前置插板都已装上",
  state.loadout.armor === "armorA" && state.loadout["armor/Front_plate@armorA"] === "plateS");
var t25r6 = ctx("armor");
var t25plates = api.plateSlotStates("armorA", "armor", state.items.armorA);
check("T25.6 右键卸除已装板护甲：重量回落、局部减益归零、插板不再计入",
  t25r6.handled && !state.loadout.armor &&
  Object.keys(state.loadout).every(function (k) {
    return k.indexOf("armor/") !== 0 || k.indexOf("@armorA") > 0;   // 历史插板配置允许保留
  }) &&
  api.gearTotals().weight < t25w6 && api.slotLocalPen("armor").count === 0);
check("T25.6 R19.26：卸甲不清该护甲的插板历史（切回来能恢复，但当前不计入）",
  state.loadout["armor/Front_plate@armorA"] === "plateS" &&
  api.plateSlotStates("armorA", "armor", state.items.armorA).every(function (s) { return s.state !== "on"; }));
check("T25.6 卸除后四个板位不再有「已安装」状态",
  t25plates.every(function (s) { return s.state !== "on"; }));
/* (7) 候选冲突状态实时重算：头盔A 与耳机1 互斥，卸掉头盔后耳机1 恢复可选 */
reset();
api.selectSlot("helmet"); api.equipItem("helmetA");
api.selectSlot("headphones");
var t25hpBefore = api.gearRows().filter(function (r) { return r.__id === "hp1"; })[0];
check("T25.7 前置条件：装上头盔A 后耳机1 在候选里是冲突态",
  !!t25hpBefore && !!t25hpBefore.conflict);
var t25r7 = ctx("helmet");
var t25hpAfter = api.gearRows().filter(function (r) { return r.__id === "hp1"; })[0];
check("T25.7 右键卸除后右侧候选的冲突状态立即重算（耳机1 不再冲突）",
  t25r7.handled && !!t25hpAfter && !t25hpAfter.conflict);
check("T25.7 卸除后全身减益 / 件数同步归零",
  api.gearTotals().count === 0 && api.slotLocalPen("helmet").count === 0);
/* (8) 子槽附件卸除后不得留下重复装备或孤立引用 */
reset();
api.selectSlot("helmet"); api.equipItem("helmetA");
api.selectSlot("helmet/mount"); api.equipItem("mount1");
ctx("helmet/mount");
var t25left = [];
for (var t25k in state.loadout) {
  if (state.loadout[t25k]) { t25left.push(t25k); }
}
check("T25.8 附件卸除后 loadout 里只剩父装备一条有效记录（无重复、无孤立）",
  t25left.join(",") === "helmet" && t25left.length === 1);

/* R300d：头盔配件语义位置 + 子配件贴父件外侧（间距 2px） */
reset();
api.selectSlot("helmet"); api.equipItem("helmetA");   // 只有装上带子槽的头盔才会生成 helmet/nvg、helmet/mount
check("R300d 头盔槽语义：mod_nvg → 夜视仪位，mod_mount → 导轨位",
  api.helmetSlotPos(node("helmet/nvg").def) === "nvg" &&
  api.helmetSlotPos(node("helmet/mount").def) === "rail");
(function () {
  var n = api.helmetChildOffset("nvg", 1);
  var r = api.helmetChildOffset("rail", 1);
  var t = api.helmetChildOffset("top", 1);
  var f = api.helmetChildOffset("face", 1);
  var b = api.helmetChildOffset("rear", 1);
  var gapLeft = api.HELMET_SLOT_XY.nvg[0] - (n[0] + 32);    // 左父件：父左 0 - 子右(-2) = 2
  var gapRight = r[0] - (api.HELMET_SLOT_XY.rail[0] + 32);  // 右父件：子左 147 - 父右 145 = 2
  check("R300d 子配件贴在父配件外侧：左父→左、右/顶父→右，间距 2px",
    n[0] === -34 && f[0] === -34 && r[0] === 147 && b[0] === 147 && t[0] === 91 &&
    n[1] === 36 && r[1] === 36 && f[1] === 77 && b[1] === 77 && t[1] === 0 &&
    gapLeft === 2 && gapRight === 2);
})();

if (failures.length) {
  console.error("FAIL (" + failures.length + "/" + checks + "):\n" + failures.join("\n"));
  process.exit(1);
}
console.log("OK " + checks + " checks passed");
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑前端动态槽位模型测试")
def test_slot_driven_model_dynamic(tmp_path):
    """把槽位驱动的纯逻辑抠到 node 上真跑：选槽 / 候选过滤 / 冲突 / 动态子槽 / 换父装备清理。"""
    harness = tmp_path / "slot_model.js"
    harness.write_text(SLOT_MODEL_JS, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(harness), str(APP_JS)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, "动态槽位模型测试失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    assert "checks passed" in proc.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node 才能跑前端动态切列测试")
def test_create_table_dynamic_column_switch(tmp_path):
    """把 createTable 抠到极简 DOM 垫片上真跑一遍：切列相关行为全部生效。"""
    harness = tmp_path / "harness.js"
    harness.write_text(DOM_HARNESS_JS, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(harness), str(APP_JS)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, "动态切列测试失败：\n%s\n%s" % (proc.stdout, proc.stderr)
    assert "checks passed" in proc.stdout

def _scoped_block(css, selector):
    """取某条作用域选择器的规则体（用于断言具体属性，而不是全文件里碰运气匹配）。"""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css, re.S)
    return m.group(1) if m else ""


def test_r7_visual_replication_rules():
    """第七轮视觉复刻（以原站截图为依据）：字号 / 行高 / 全列左对齐 / 滚动条根因 /
    选中行强调边 / 局部减益 / 已装名称悬停浮窗。"""
    js = _read(APP_JS)
    css = _read(STYLE_CSS)

    # 5.2 表格字号与行高收敛为工作台专属变量（不改地图与其它模块的字号）
    # 第七轮校准：参考图逐像素测量为表头 32px / 数据行 40px / 正文 12px / 表头 11px
    assert "--lw-table-font-size: 11px;" in css
    assert "--lw-table-head-font-size: 10px;" in css
    # R300b：用户要求贴近 db4 的紧凑行高（护甲 46px、其余类别 26px，由 app.js 按类别覆盖）。
    assert "--lw-table-row-height: 46px;" in css
    assert "--lw-table-head-height: 28px;" in css
    for var in ("--lw-table-font-size", "--lw-table-row-height", "--lw-table-head-height"):
        assert ("var(%s)" % var) in css, "表格块没有真正使用变量 %s" % var

    # 5.4 横向滚动条根因：滚动容器显式 min-width:0，否则 flex 子项会被内容撑宽 → 没有真实溢出
    scroll = _scoped_block(css, ".loadout-workbench .tbl-scroll")
    assert "min-width: 0" in scroll, "滚动容器缺 min-width:0（滑块会再次消失）"
    assert "overflow: auto" in scroll
    assert "::-webkit-scrollbar" in css and "scrollbar-width: thin" in css
    assert "::-webkit-scrollbar-thumb" in css

    # R26.0：用户要求「除名称列外一律居中」，名称列仍左对齐（图标 + 长名字左起更好读）
    assert "text-align: center" in _scoped_block(css, ".loadout-workbench .tbl-cell")
    assert "text-align: center" in _scoped_block(css, ".loadout-workbench .tbl-head .tbl-cell")
    assert ".loadout-workbench .tbl-num,\n.loadout-workbench .tbl-mid { text-align: center;" in css
    assert '.loadout-workbench .tbl-row .tbl-cell[data-key="n"],' in css
    # createTable 的 forceLeft：配装表与插板窗都显式传入（不靠默认 CSS 偶然决定）
    assert js.count("forceLeft: true") >= 2
    assert "if (opts.forceLeft) { return \"left\"; }" in js

    # 5.5 选中行：只保留左侧 2px 细蓝边，不加大面积高亮底色；冲突 + 选中时蓝边优先
    sel = _scoped_block(css, '.loadout-workbench .tbl-row[aria-selected="true"]')
    assert "inset 2px 0 0 var(--lw-accent)" in sel
    assert "background: transparent" in sel and "#10242a" not in sel
    both = _scoped_block(css, '.loadout-workbench .tbl-row.tbl-conflict[aria-selected="true"]')
    assert "inset 2px 0 0 var(--lw-accent)" in both, "冲突 + 选中时必须保留蓝色选中边"

    # 5.3 逐类别默认列宽：每个类别独立一套，插板弹窗单独一类，用户拖动值仍然优先
    assert "var LW_COL_DEFAULTS = {" in js
    assert "function applyColDefaults(cat, cols)" in js
    for cat in ("armor", "helmet", "rig", "backpack", "headphones", "glasses",
                "face", "plate", "gun", "melee"):
        assert re.search(r"\n    %s: \{" % cat, js), "缺少类别默认列宽：%s" % cat
    assert "var cat = !node ? \"default\" : (node.kind === \"plate\" ? \"plate\" : rootKey);" in js
    assert "return applyColDefaults(cat, cols);" in js

    # 4.2 已装装备不再常驻名称，改为悬停浮窗
    assert "function bindCellTip(" in js and "bindCellTip(btn," in js
    assert "nm.textContent = nameOf(id);" not in js, "已装卡片的常驻名称残留"
    assert "btn.setAttribute(\"aria-label\"" in js, "悬停浮窗之外还缺可访问名称"

    # 4.3 R299 修订：局部减益只写三项数值，不再渲染「移动 / 转身 / 人机」标签；
    # PSD 里胸挂没有属性带，rig 从键表移除。
    assert "var LW_DEBUFF_KEYS = { helmet: 1, armor: 1, glasses: 1, backpack: 1 };" in js
    assert "function slotLocalPen(" in js and "function debuffEl(" in js
    assert "lw-debuff-lab" not in js
    assert ".loadout-workbench .lw-cell-debuff" in css
    assert ".loadout-workbench .lw-debuff-num" in css


def _fn_body(js, name):
    """按 `function name(...) { ... }` 起点截到最后（只用于断言函数内部实现）。"""
    i = js.find("function %s(" % name)
    assert i >= 0, "找不到函数 %s" % name
    return js[i:i + 1400]


def test_left_cards_right_click_unequip():
    """第八轮：左栏已装卡片右键卸除。

    · 只在「已装」的卡片上 preventDefault（空槽不拦截浏览器菜单、不改状态）；
    · 卸除复用 clearGearSlot → commitLoadoutChange，不另写一套状态更新；
    · 固定内衬 / 装饰剪影 / 其他区域没有 contextmenu 绑定；
    · 左键 click 仍走 selectSlot，行为不变。
    """
    js = _read(APP_JS)

    assert "function unequipByContextMenu(ev, slotKey)" in js
    body = _fn_body(js, "unequipByContextMenu")
    assert "if (!slotKey || !state.loadout[slotKey]) { return false; }" in body
    assert body.index("ev.preventDefault") < body.index("clearGearSlot(slotKey)"), \
        "必须先拦截默认菜单，再卸除"
    assert "clearGearSlot(slotKey);" in body and "return true;" in body

    # 右键监听（第十轮第 4 项起）：bindCellUnequip 一处 + 插板格「已安装插板」卸除一处；
    # R19.4 起配枪工作台的装配卡也有一处（不同的工作台、不同的卸载函数 clearGunSlot，
    # 语义等价扩展而非削弱）；R19.7 起画布子弹格多一处「清空已选弹药」（仍是仅在该格上
    # preventDefault，非全局拦截）。
    # R77 起任务栏再增两处，经实测均非重复绑定（同一元素只绑一次，右键一次只弹 1 个菜单）：
    #   ① #task-list 容器上代理一处：任务行右键 → 自定义任务菜单；initTaskPanel 启动时
    #      只执行一次，行节点每次重绘都重建、不会在旧节点上叠绑。
    #   ② document 级一处「点别处收起菜单」：不 preventDefault、不拦截浏览器菜单，
    #      只收起已打开的自定义菜单（还覆盖 Shift+F10 等不经过 mousedown 的路径）。
    assert js.count('.addEventListener("contextmenu"') == 6
    assert js.count('document.addEventListener("contextmenu"') == 1, \
        "document 级只能有 R77 的「收起任务菜单」一处"
    assert 'window.addEventListener("contextmenu"' not in js
    # document 级那处不得拦截默认菜单，只允许收起自绘菜单
    i = js.index('document.addEventListener("contextmenu"')
    seg = js[i:js.index(", true);", i)]
    assert "preventDefault" not in seg, "document 级 contextmenu 不得拦截浏览器右键菜单"
    assert "hideTaskContextMenu()" in seg
    # #task-list 上的那处是代理式任务菜单入口
    j = js.index('el.taskList.addEventListener("contextmenu"')
    assert "showTaskContextMenu(" in js[j:j + 700]
    assert "function bindCellUnequip(node, slotKey)" in js
    # 第二处只在「有硬板位且已安装」的格上拦截：空槽 / na / 本体右键不受影响，
    # 且同样复用 clearGearSlot（不另建卸除系统）。_fn_body 截 1400 字符不够长，
    # 这里用「renderPlateCell 起点 → renderSrcCell 起点」整段切片。
    i0 = js.find("function renderPlateCell(")
    i1 = js.find("function renderSrcCell(")
    assert 0 < i0 < i1
    pbody = js[i0:i1]
    assert 'if (st.state === "on" && st.slotId)' in pbody
    assert 'clearGearSlot(st.slotId);' in pbody
    assert 'ev.preventDefault' in pbody

    # 根卡与子槽（附件）都绑定；固定内衬行不绑定
    assert "bindCellUnequip(btn, key);" in js
    assert "bindCellUnequip(btn, node.id);" in js
    assert "bindCellUnequip" not in _fn_body(js, "linerRow")

    # 左键原有行为保持：仍是 selectSlot
    assert 'btn.addEventListener("click", function () { selectSlot(key); });' in js
    assert 'btn.addEventListener("click", function () { selectSlot(node.id); });' in js

    # 唯一卸除入口仍是 clearGearSlot（随后统一走 commitLoadoutChange）
    clear = _fn_body(js, "clearGearSlot")
    assert "state.loadout[nodeId] = null;" in clear
    assert "commitLoadoutChange(" in clear
    assert "function commitLoadoutChange(msg)" in js
    assert "pruneOrphanSlots(state.slotTree);" in _fn_body(js, "commitLoadoutChange")
