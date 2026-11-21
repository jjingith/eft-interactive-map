# -*- coding: utf-8 -*-
"""R19.7 回归：属性信息、弹药交互、配件显示、战术装置位置与中栏收窄。

对应任务书八项：
1. 基础枪械 / 改装槽位 / 已装配件移到画布上方的信息条，不再混入整枪属性；
2. 整枪属性只显示名称与值，不输出「✓ 实测 / 缺失」等状态后缀；
3. 枪身图不再叠加「官方预设：…」，配件卡右上角 × 已删除（右键卸载保留）；
4. 战术装置排在前握把左侧，放不下时进入子弹行下方的独立底行；
5. 子弹格点击 → 右侧弹药候选 → 选中写回画布 + DPS 更新；
6. 删除隐藏属性下方的内部槽位路径 / 合法配件数量 / 弹药清单 / 公式说明；
7. 右栏候选名称不被裁切（图片固定、名称列占满剩余宽度）；
8. 中栏收窄到与画布宽度一致，释放宽度给右栏。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
HTML = os.path.join(ROOT, "index.html")
SERVE = os.path.join(ROOT, "tools", "serve.py")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _body(css, selector, last=True):
    i = css.rindex(selector) if last else css.index(selector)
    j = css.index("{", i)
    return css[j + 1:css.index("}", j)]


def _slice(js, start, end):
    return js[js.index(start):js.index(end)]


def test_meta_bar_holds_gun_name_slot_and_part_counts():
    js = _read(APP)
    html = _read(HTML)
    assert 'id="gw-meta"' in html, "画布上方必须有枪械信息条"
    meta = _slice(js, "function renderGunMeta()", "/** R19 属性面板入口")
    assert "基础枪械" in meta and "改装槽位" in meta and "已装配件" in meta
    assert "gunCurrentName()" in meta, "基础枪械名称必须来自当前枪械"
    assert "g.slots.order" in meta, "改装槽位数来自真实槽位树"
    assert "parts" in meta, "已装配件数量来自属性引擎统计"

    stats = _slice(js, "function renderGunStatsV2(", "function gunPresetStateText()")
    for label in ("基础枪械", "改装槽位", "已装配件", "当前预设"):
        assert 'gunStatRowEx(host, "%s"' % label not in stats, \
            "整枪属性不得再混入 %s" % label
        assert 'gunStatRow(host, "%s"' % label not in stats, \
            "整枪属性不得再混入 %s" % label
    assert "移到画布上方的信息条" in stats


def test_stats_have_no_status_badges():
    js = _read(APP)
    row = _slice(js, "function gunStatRowEx(", "function fmtStatValue(")
    for bad in ("实测", "缺失", "估算", "gw-stat-conf", "data-tone"):
        assert bad not in row, "属性行不得输出状态文字：%s" % bad
    assert "title = why" in row, "数据来源说明只保留在悬停提示里"


def test_gun_image_has_no_official_preset_overlay_but_overlay_shows_rpm_dps():
    js = _read(APP)
    tree = _slice(js, "function renderGunTree()", "function renderGunFocus(")
    # 先去掉行注释，避免「删除官方预设文字」这句说明本身触发断言
    code = re.sub(r"//[^\n]*", "", tree)
    assert "官方预设：" not in code, "枪身图上不得再叠加官方预设文字"
    assert "gw-hero-tag" not in code, "枪身图不得再渲染预设角标"
    assert "gw-gun-overlay" in code and "gunRpmText(" in code and "gunDpsText(" in code
    assert "gw-gun-rpm" in code and "gw-gun-dps" in code

    css = _read(CSS)
    rpm = _body(css, ".gun-workbench .gw-gun-rpm {")
    dps = _body(css, ".gun-workbench .gw-gun-dps {")
    assert "color: #55595e" in rpm, "射速必须是灰黑色小字"
    assert "color: #d02a1e" in dps, "DPS 必须是红色小字"
    assert "font-size: 8px" in rpm and "font-size: 8px" in dps


def test_dps_formula_uses_selected_ammo_and_rpm():
    js = _read(APP)
    dps = _slice(js, "function gunDpsValue(", "function gunDpsText(")
    assert "state.ammo.byId[selId]" in dps, "DPS 只读当前选中的弹药"
    assert "a.dmg * rpm / 60" in dps, "DPS ≈ 弹药伤害 × 射速 ÷ 60"
    assert "return null" in dps, "未选弹药 / 缺伤害时不得沿用旧值"
    text = _slice(js, "function gunDpsText(", "function gunAmmoRows(")
    assert 'return (dps === null) ? "DPS —"' in text
    rpm = _slice(js, "function gunRpmValue(", "function gunRpmText(")
    assert "state.gunStats" in rpm, "射速必须读当前枪械数据，不得写死"


def test_ammo_slot_drives_right_candidate_list():
    js = _read(APP)
    html = _read(HTML)
    assert 'id="gw-ammo"' not in html and "renderGunAmmo" not in js, \
        "画布下方的独立弹药区必须删除（不只是隐藏）"
    assert "弹道联动图尚未实现" not in js

    tree = _slice(js, "function renderGunTree()", "function renderGunFocus(")
    assert "g.ammoFocus = true" in tree, "点击子弹格切换右侧候选到弹药"
    assert "gunAmmoState()[g.gunId]" in tree, "弹药选择状态与画布共用"
    assert "setGearIcon(aic, ammoRec2.id)" in tree, "选中弹药必须在子弹格显示图标"
    assert "gw-ammo-short" in tree, "选中弹药必须在子弹格显示简洁名称"

    table = _slice(js, "function refreshGunTable()", "function gunEquip(")
    assert "gunAmmoColumns()" in table and "gunAmmoRows()" in table
    assert "ammoMode" in table, "右栏按当前选中的画布格子切换列集"
    equip = _slice(js, "function gunEquip(", "function clearGunSlot(")
    assert "gunAmmoState()[g.gunId] = id" in equip, "选弹药走同一安装入口"


def test_focus_bar_has_no_internal_slot_paths_or_dev_text():
    """R19.11：这条信息条从「隐藏属性下方」搬到「右侧候选栏顶部」，内容约束不变。"""
    js = _read(APP)
    focus = _slice(js, "function renderGunFocus()", "function syncGunHint(")
    assert "el.gwSlotInfo" in focus, "必须渲染到右栏顶部的 #gw-slotinfo"
    # R19.11：允许用 node.path 读当前装配（内部逻辑），但**可见文本**只能用 node.label
    assert '"当前槽位：" + node.label' in focus
    for seg in re.findall(r"textContent\s*=[^;]+;", focus):
        assert "node.path" not in seg, "不得把内部槽位路径写进可见文本"
    assert "严格按上游" not in focus, "不得输出 allow 数量与规则说明"
    assert "当前槽位：" in focus and "子弹" in focus
    # 隐藏属性块只允许属性行
    hid = _slice(js, "var hidHost = el.gwHidden || host;", "// R19.8：成本固定为属性面板第三行")
    assert "node.path" not in hid and "allow" not in hid


def test_part_cards_have_no_close_button_but_keep_right_click_uninstall():
    js = _read(APP)
    card = _slice(js, "function gwPartCard(", "function gwDrawLinks(")
    assert "gw-part-x" not in card, "配件卡右上角 × 必须删除"
    assert 'contextmenu' in card and "clearGunSlot(path)" in card, "右键卸载必须保留"
    css = _read(CSS)
    assert ".gun-workbench .gw-part-x" not in css, "× 的样式一并移除"


def test_tactical_and_foregrip_keep_parent_anchor_in_fixed_grid():
    """R19.12：固定 6×9 网格下，战术装置 / 前握把都锚在父件附近，不再有"独立底行"。

    与 R19.7/R19.10 的差别（规范变了，不是放宽）：
      · 以前画布行数随枪变化，战术装置放不下时会掉到"子弹行下方的独立底行"；
      · 现在格子固定 54 个，落位规则统一成"父件正下方 → 同行相邻 → 后续行"，
        前握把仍受更强的父子约束（钉在父件正下方同列，固定锚点格不许抢）。
    """
    js = _read(APP)
    engine = _slice(js, "var GW_GRID_ROWS = 6", "function gwPartCard(")
    assert "GW_GRID_ROWS" in engine and "GW_GRID_COLS" in engine, "网格边界必须显式存在"
    assert "foregrip" in engine, "前握把仍有专门的父子钉位逻辑"
    assert "wantRow = pc ? pc.row + 1 : GW_ANCHOR.body.row + 1" in engine, "前握把在父件正下方"
    assert "wantCol = pc ? pc.col : 5" in engine, "列与父件对齐"
    assert "if (wantRow > GW_GRID_ROWS) { wantRow = GW_GRID_ROWS; }" in engine, "不越出 6 行"
    assert "if (reserved[key] || (holder && holder.pinned)) {" in engine, \
        "固定锚点格不被抢（改为沿同列下探，保持列对齐）"
    assert "holder && !holder.pinned" in engine, "被挤走的只能是普通格"
    assert "tactical" in _slice(js, "function gwLaneOf(", "function gwBuildLayout("), \
        "战术装置的车道仍由真实槽位语义（gwLaneOf）判定"
    # 旧的"独立底行"逻辑必须彻底消失（否则会越出 6 行）
    assert "tactBottom" not in engine and "tacticalRow" not in engine and "extraRow" not in engine


def test_center_column_narrowed_to_canvas_width():
    css = _read(CSS)
    seg = css[css.index("   R19.6：FORGE 压缩 + 结构化装配画布"):]
    buildpage = _body(seg, ".gun-workbench .gw-buildpage {", last=False)
    assert "minmax(0, 600px)" in buildpage, "中栏必须收窄到画布宽度量级"
    assert "1.5fr" not in buildpage, "不得保留会撑出空白的弹性中栏"
    grid = _body(seg, ".gun-workbench .gw-canvas.gw-grid {")
    assert "max-width: 566px" in grid
    assert "margin: 0 auto" in grid


def test_candidate_names_are_not_clipped():
    css = _read(CSS)
    cell = _body(css, '.gun-workbench .tbl-row .tbl-cell[data-key="n"] {')
    assert "width: 0" in cell and "min-width: 100%" in cell
    assert "display: flex" in cell and "overflow: hidden" in cell
    name = _body(css, ".gun-workbench .tbl-row .gw-row-name {")
    assert "flex: 1 1 auto" in name and "min-width: 0" in name
    b = _body(css, ".gun-workbench .tbl-row .gw-row-name b,")
    assert "text-overflow: ellipsis" in b, "长名称必须有可见的省略号"


def test_version_marker_r19_7_synced():
    js = _read(APP)
    html = _read(HTML)
    serve = _read(SERVE)
    m = re.search(r'AM_BUILD = "([^"]+)"', js)
    assert m and m.group(1).startswith("R19."), m and m.group(1)   # 版本标记跟随 AM_BUILD 动态同步
    build = m.group(1)
    for name in ("style.css", "theme-windows-xp.css", "app.js", "gun_builder.js", "combat_sim.js"):
        assert re.search(re.escape(name) + r"\?v=" + re.escape(build.lower()), html), "%s 版本串未同步到 r19.8" % name
    assert ('"rev": "%s-"' % build) in serve, "serve.py rev 必须与 AM_BUILD(%s) 同步" % build
