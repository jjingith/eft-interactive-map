# -*- coding: utf-8 -*-
"""R19.11 合并修复：100 发容量硬约束 / 属性条实心-斜纹 / 枪匠大师与个人属性 /
右侧候选栏（当前槽位 · 红斜纹 · 隐藏不兼容 · 统一兼容性）/ 逐发模拟弹匣同源。

分工：
· 静态：文件里"必须长成这样"的契约（键名、判据顺序、CSS 覆盖层优先级、DOM 顺序）；
· 动态（node + 真实数据）：容量硬约束、弹匣清单同源、M4 枪托链路的结构性结论。
不联网；缺 node 时动态用例跳过。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.js"
HTML = ROOT / "index.html"
CSS = ROOT / "style.css"
THEME = ROOT / "theme-windows-xp.css"
GB = ROOT / "gun_builder.js"
ENG = ROOT / "tools" / "r1911_engine.js"

M4A1 = "5447a9cd4bdc2dbd208b4567"
AK74 = "5bf3e03b0db834001d2c4a9c"
SPEAR = "65290f395ae2ae97b80fdf2d"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn(js: str, name: str) -> str:
    i = js.find("function %s(" % name)
    assert i >= 0, "找不到函数 %s" % name
    depth, j = 0, js.index("{", i)
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i:j + 1]
        j += 1
    return js[i:]


def _body(css: str, selector: str) -> str:
    i = css.rindex(selector)
    j = css.index("{", i)
    return css[j + 1:css.index("}", j)]


# ---------------------------------------------------------------- 1. 容量硬约束
def test_engine_enforces_mag_capacity_before_greedy():
    gb = _read(GB)
    fn = _fn(gb, "enforceMagCapacity")
    assert "/magazine/i" in fn, "按真实槽位基名找弹匣槽，不按物品名猜"
    assert "inst[path] !== row.id" in fn, "候选必须通过 sanitize 才算可装"
    assert "caps.indexOf(cap) < 0" in fn, "容量不在允许集合就跳过"
    assert "cap === null" in fn, "容量未知不得当作合规"
    # 在 optimize 里：预装 + 锁死 + 无解标记
    opt = _fn(gb, "optimize")
    assert "enforceMagCapacity(ctx, gunId, cur, cons)" in opt
    assert "lockedPaths[magFix.locked[mfi]] = 1;" in opt, "合规弹匣槽必须锁死，贪心不得换回小弹匣"
    assert "capsOk = false;" in opt and "capsWhy = magFix.why;" in opt
    assert "capsOk: magOkNow, capsWhy: magWhyNow" in opt, "每个方案都要带容量结论"
    assert 'kind: "caps"' in opt


def test_ui_drops_infeasible_builds_instead_of_coloring_them():
    forge = _fn(_read(APP), "renderGunForge")
    assert "var list = rawList.filter(function (b) { return b.constraintOk !== false; });" in forge, \
        "不满足约束的方案不得混进有效方案列表"
    assert "gw-forge-nosolution" in forge, "无可行方案要明确提示"
    assert "不会用 30 发之类的弹匣凑数" in forge


@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_caps_hard_constraint_real_data():
    def run(gun, caps):
        proc = subprocess.run(["node", str(ENG), "caps", gun, caps],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr[:800]
        return json.loads(proc.stdout)

    m4 = run(M4A1, "100")
    assert len(m4["builds"]) >= 4
    assert all(b["ok"] and b["capsOk"] for b in m4["builds"]), "M4A1 有 100 发弹匣，方案必须全部合规"
    for b in m4["builds"]:
        assert b["mags"], "方案里必须有弹匣"
        assert all(m["cap"] == 100 for m in b["mags"]), "装上的必须真的是 100 发"

    ak = run(AK74, "100")
    assert all(not b["capsOk"] for b in ak["builds"]), "AK-74 没有 100 发弹匣，必须判无解"
    why = ak["builds"][0]["violations"][0]
    assert why["kind"] == "caps"
    assert "没有满足 100 发容量约束" in why["why"]
    assert "10 / 20 / 30 / 45 / 60 / 95" in why["why"], "无解时要列出该枪真实可选容量"

    # 回归：其他容量不被新逻辑破坏
    m4_30 = run(M4A1, "30")
    assert all(b["capsOk"] and b["mags"] and b["mags"][0]["cap"] == 30 for b in m4_30["builds"])
    ak_multi = run(AK74, "30,45")
    assert all(b["capsOk"] for b in ak_multi["builds"])
    assert all(b["mags"][0]["cap"] in (30, 45) for b in ak_multi["builds"])


# ---------------------------------------------------------------- 2. 属性条
def test_bars_solid_is_shared_range_and_stripe_is_delta():
    js = _read(APP)
    bar = _fn(js, "gwBar")
    assert "var lowVal = Math.min(b, v), highVal = Math.max(b, v);" in bar
    assert 'seg(0, lowVal, "solid-" + good);' in bar, "共有区间 [0,min] 实心"
    assert 'seg(lowVal, highVal, "stripe-" + good);' in bar, "差异区间 [min,max] 斜纹"
    assert "lowerBetter" in bar, "优劣方向仍由颜色表达"
    # 基线标记固定在 f(B)
    assert "mark.style.left = pct(b);" in bar
    assert "不随改装移动" in bar
    # 三值
    for lab in ('"基线 "', '"改装 "', '"技能 "'):
        assert lab in bar
    assert "gw-bar-skillval" in bar and "gw-bar-modval" in bar


def test_bars_three_values_come_from_three_paths():
    js = _read(APP)
    tiers = _fn(js, "gunStatTiers")
    assert "gunComputeOf(g.gunId, d ? d.installed : {}, noSkill)" in tiers, "基线=默认装配且无技能"
    assert "gunComputeOf(g.gunId, g.installed || {}, noSkill)" in tiers, "改装=当前装配且无技能"
    assert "gunComputeSkilledOf(g.gunId, g.installed || {})" in tiers, "技能=当前装配+个人属性"
    assert "strengthLevel: 0, equipErgoModifier: 0" in tiers, "基线与改装不得混入个人属性"
    skilled = _fn(js, "gunComputeSkilledOf")
    assert "gwApplySkillStats" in skilled and "gwWeaponSkillLevel(gunId)" in skilled


def test_skill_formula_scope_is_documented_and_limited():
    js = _read(APP)
    assert "recoilPerLevel: 0.003" in js and "ergoPerLevel: 0.002" in js
    assert "recoilCap: 0.15" in js and "ergoCap: 0.10" in js
    apply_ = _fn(js, "gwApplySkillStats")
    assert 'mul("recoilV"' in apply_ and 'mul("recoilH"' in apply_ and 'mul("ergonomics"' in apply_
    # 只动这三项：不得碰散布角 / 初速 / 重量 / 成本
    for bad in ('mul("accuracy"', 'mul("velocity"', 'mul("weight"', 'mul("cost"'):
        assert bad not in apply_, "技能不得改 %s" % bad
    assert "力量/耐力不影响武器人机与后坐" in js or "力量、耐力" in js, "技能范围要在代码里写明"


# ---------------------------------------------------------------- 3. 改名 + 个人属性
def test_forge_renamed_to_gunsmith_master():
    js = _read(APP)
    assert 't.textContent = "枪匠大师";' in js
    assert "FORGE BETA" not in js.replace("（原 FORGE BETA）", ""), "可见标题不得再出现 FORGE BETA"
    assert "枪匠大师（原 FORGE BETA）" in js, "hover 里可以注明原名"


def test_profile_persist_validate_and_scope():
    js = _read(APP)
    # R19.93：个人属性升级为「属性设置」，技能按游戏模式写入 eftmap.attrs.v1
    assert 'GW_ATTR_KEY = "eftmap.attrs.v1"' in js
    assert 'GW_PROFILE_KEY = "eftmap.profile.v1"' in js, "旧键仍用于首次迁移"
    assert "eftmap.gwsim.v1" in js, "更早的模拟参数也要迁移"
    prof = _fn(js, "gwProfile")
    assert "gwAttrMode()" in prof, "技能必须按当前模式读取"
    save = _fn(js, "gwProfileSave")
    assert "gwAttrsLoad()" in save and "gwAttrsSave(all)" in save
    for msg in ("超出合法等级范围", "必须是整数等级", "装备人机修正超出范围"):
        assert msg in save, "缺校验提示：%s" % msg
    # 类别技能：与「口径/种类」分页同一套类别，不另造
    assert "var GW_SKILL_CLASS_OF = {" in js
    for zh in ("突击步枪", "卡宾枪", "冲锋枪", "精确射手步枪", "栓动狙击步枪", "机枪", "霰弹枪", "手枪", "左轮"):
        assert '"%s":' % zh in js, "缺类别映射：%s" % zh
    lv = _fn(js, "gwWeaponSkillLevel")
    assert "p.skillByClass[key]" in lv and "p.weaponSkillDefault" in lv, "类别覆盖优先、否则默认"
    # 弹窗字段与保存/取消（三页签里的技能分页沿用原有 id）
    html = _read(HTML)
    for fid in ("gw-prof-strength", "gw-prof-endurance", "gw-prof-skill-default",
                "gw-prof-equip", "gw-prof-mastery", "gw-prof-save", "gw-prof-cancel"):
        assert 'id="%s"' % fid in html, "弹窗缺字段 %s" % fid
    assert 'id="btn-profile"' in html, "顶栏缺少属性设置的原锚点"


def test_profile_modal_is_in_top_nav_row():
    """第一阶段：工作区导航上移顶栏，个人属性入口仍在顶栏区域（隐藏锚点内）。"""
    html = _read(HTML)
    assert 'id="btn-profile"' in html, "顶栏缺少个人属性入口"
    assert html.index('id="view-btn-map"') < html.index('id="btn-profile"')
    assert 'id="gw-profile"' in html and 'role="dialog"' in html


# ---------------------------------------------------------------- 4. 右侧候选栏
def test_slot_info_moved_to_candidate_panel_top():
    """R19.96：当前槽位 / 筛选 / 搜索上提到视图工具条，右栏直接以候选表开始。"""
    html = _read(HTML)
    assert 'id="gw-focus"' not in html, "隐藏属性下方的旧信息条必须删除"
    cands = html[html.index('<aside class="gw-cands"'):html.index("</aside>", html.index('<aside class="gw-cands"'))]
    assert 'id="gw-slotinfo"' not in cands, "R19.96：这一行已上提到视图工具条"
    assert 'id="gw-table"' in cands, "右栏应从候选表开始"
    modes = html[html.index('class="gw-modes"'):html.index('<div class="gw-filterrow"')]
    assert modes.index('id="gw-slotinfo"') < modes.index('id="gw-hidebad"') < \
        modes.index('id="gw-cand-search"'), \
        "工具条内顺序：当前槽位 → 隐藏不兼容 → 搜索"
    js = _read(APP)
    focus = _fn(js, "renderGunFocus")
    assert "el.gwSlotInfo" in focus
    assert '"当前槽位：" + node.label' in focus
    assert '"当前槽位：子弹"' in focus, "弹药模式要有自己的上下文"
    assert 'el.gwSlotInfo.dataset.kind = "ammo"' in focus


def test_hide_incompat_filters_without_touching_data():
    js = _read(APP)
    tbl = _fn(js, "refreshGunTable")
    assert "if (!ammoMode && gwHideIncompat()) {" in tbl
    assert "rows = rows.filter(function (r) { return !r.conflict; });" in tbl
    assert "state.gunHiddenBad = hiddenBad;" in tbl
    # 只影响显示：不改 conflict / 不清搜索 / 不重置列宽
    assert "r.conflict =" not in tbl and "state.gunCandQuery =" not in tbl
    assert "setColumns" in tbl and "gunColumns(" in tbl, "切列逻辑保持（列宽不受影响）"
    # 空状态提示
    build = _fn(js, "buildGunTable")
    assert "取消「隐藏不兼容配件」可以看到它们与原因" in build
    assert "没有匹配「" in build and "已隐藏" in build, "搜索无命中与全部不兼容要分开提示"
    html = _read(HTML)
    assert 'id="gw-hidebad"' in html and "隐藏不兼容配件" in html


def test_incompatible_rows_have_full_width_red_stripes():
    css = _read(CSS)
    row = _body(css, ".gun-workbench .tbl-row.tbl-conflict::after")
    assert "repeating-linear-gradient(45deg" in row
    assert "inset: 0" in row, "斜纹覆盖整条，不是角落小图标"
    assert "pointer-events: none" in row, "覆盖层不能拦截鼠标"
    assert "z-index: 2" in row
    for state in (":hover::after", '[aria-selected="true"]::after', ":focus::after"):
        assert ".gun-workbench .tbl-row.tbl-conflict" + state in css, "缺 %s 的斜纹保持" % state
    assert ".gun-workbench .tbl-row.tbl-conflict .gw-row-why" in css, "行内要有可读原因"


def test_single_compatibility_source_used_by_list_install_and_filters():
    js = _read(APP)
    compat = _fn(js, "gunCompatOf")
    # 判据顺序：allow → 互斥 → 试装 → 连带拆除
    assert "if (!inList(node.allow, id))" in compat
    assert "inList(rec.conflict || [], otherId)" in compat
    assert "window.GB.sanitize(ctx, g.gunId, trial)" in compat, "必须用真实安装链试装"
    assert "会连带卸下" in compat, "不允许静默拆除无关组件"
    assert 'kind: "self"' in compat and 'kind: "evict"' in compat
    # 列表与安装共用
    rows = _fn(js, "gunRows")
    assert "gunCompat(id, node)" in rows
    equip = _fn(js, "gunEquip")
    assert "gunInstallCheck(id, node)" in equip
    check = _fn(js, "gunInstallCheck")
    assert "gunCompat(id, node)" in check, "安装入口必须复用同一判据"


# ---------------------------------------------------------------- 5. M4 枪托链路
@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_m4_stock_buffer_tube_structure():
    proc = subprocess.run(["node", str(ENG), "stock", M4A1],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    assert d["stockPaths"][0] == "mod_stock"
    assert len(d["stockPaths"]) >= 2, "装上缓冲管后必须出现子枪托槽"
    # 根槽 17 项 = 缓冲管（带 stock 子槽）+ 一体式枪托（无子槽）
    assert d["rootAllow"] == len(d["carriers"]) + len(d["integrated"])
    assert len(d["carriers"]) >= 5 and len(d["integrated"]) >= 5
    # 需要缓冲管的枪托不能直接出现在枪身根槽
    assert d["leakToRoot"] == 0, "需要缓冲管的枪托被错误地允许直接挂枪身"
    # R19.12：M4A1 默认装配的握把是「Hera 一体化枪托」，它在上游 conflictingItems 里
    # 声明了与 UBR 等独立枪托互斥。所以：
    #   ① 保留握把直接换 UBR → 必须被拒（这才是真实兼容结论，以前会被静默装上）
    #   ② 先腾空握把再换 UBR → 合法，且子槽消失、只剩这一件
    after = d["afterIntegrated"]
    assert after["keptStock"] is False, "一体化握把与独立枪托互斥，不能同时存在"
    assert any("互斥" in (x["why"] or "") for x in after["dropped"]), \
        "拒绝原因必须写明上游互斥"
    free = after["freeSlot"]
    assert free["keptStock"] is True, "腾空握把后 UBR 应当能合法装上"
    assert free["stockPathsAfter"] == ["mod_stock"], "一体式枪托没有子枪托槽"
    assert len(free["stockItems"]) == 1, "不得同时残留缓冲管/普通枪托"


# ---------------------------------------------------------------- 6. 模拟器弹匣
@pytest.mark.skipif(shutil.which("node") is None, reason="需要 node")
def test_sim_mag_list_matches_gun_slot_tree():
    guns = [SPEAR, M4A1, "5a7ae0c351dfba0017554310"]
    proc = subprocess.run(["node", str(ENG), "mags", ",".join(guns)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[:800]
    d = json.loads(proc.stdout)
    for gid, rec in d.items():
        assert rec["count"] > 0, "%s 没有弹匣候选" % rec["name"]
        assert rec["sameSet"], "%s 的兼容表与 mod_magazine allow 不一致" % rec["name"]
    spear = d[SPEAR]
    assert spear["count"] == 6, "SPEAR 应有 6 个 AR-10 弹匣"
    names = " ".join(spear["tree"])
    assert spear["count"] == len(set(spear["tree"]))


def test_sim_uses_shared_mag_source_and_loading_state():
    js = _read(APP)
    ids = _fn(js, "gunMagIds")
    assert "window.GB.buildTree(ctx, gunId, inst)" in ids, "优先用改枪界面同一棵槽位树"
    assert "/magazine/i" in ids
    assert "simGunCompat(gunId)" in ids, "引擎未就绪才回退兼容表"
    allowed = _fn(js, "simAllowedMags")
    assert "gunMagIds(amSimState().gunId)" in allowed
    picker = _fn(js, "renderSimMagPicker")
    assert "物品数据加载中" in picker, "数据没到齐不得显示成 missing"
    gun = _fn(js, "renderSimGun")
    assert "if (s.gunId !== gunBefore) { amSimOnGunChanged(); }" in gun, \
        "口径筛选隐式换枪必须走完整换枪联动"
    sim = _fn(js, "renderAmmoSim")
    assert "ensureItems().then(function () {" in sim, "items 晚到要补渲染弹匣"
