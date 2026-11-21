# -*- coding: utf-8 -*-
"""R19.8 回归：保存预设、弹药后坐力/ACC、成本第三行、部件价格、分页筛选、FORGE 约束。

对应任务书六项：
1. LOAD VARIANT 在「恢复默认」右侧新增「保存预设」，保存后可刷新重新载入；
2. 弹药候选增加「后坐力 / ACC」，字段来自 ammo.json 的 recoilModifier / accuracyModifier；
3. 整枪成本与改装件成本固定在整枪属性第三行并排显示，金额与 ₽ 都不省略；
4. 逐部件价格明细：左图标 + 名称 + 右侧商人价 / 跳蚤价（复用配装界面的取价函数）；
5. 口径 / 种类分页的主武器、手枪、Auto、Burst、Single 用真实分类与射击模式字段筛选；
6. FORGE 必需瞄具改为近 / 中 / 远三档（按真实倍率分档）+ 手电 / 激光功能约束。

数据侧断言直接读 data/*.json，避免只检查 CSS 或按钮文字。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
CSS = os.path.join(ROOT, "style.css")
HTML = os.path.join(ROOT, "index.html")
BUILDER = os.path.join(ROOT, "gun_builder.js")
FORGE = os.path.join(ROOT, "data", "forge-constraints.json")
AMMO = os.path.join(ROOT, "data", "ammo.json")
ITEMS = os.path.join(ROOT, "data", "items.json")
GUNSLOTS = os.path.join(ROOT, "data", "gunslots.json")
GUNSTATS = os.path.join(ROOT, "data", "gun-stats.json")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _body(css, selector, last=True):
    i = css.rindex(selector) if last else css.index(selector)
    j = css.index("{", i)
    return css[j + 1:css.index("}", j)]


def _slice(js, start, end):
    i = js.index(start)
    return js[i:js.index(end, i + len(start))]


def _fn(js, name):
    """抓取一个 2 空格缩进的顶层函数体（到下一个同缩进函数为止）。"""
    start = js.index("function " + name + "(")
    m = re.search(r"\n  function [A-Za-z0-9_$]+\(", js[start + 1:])
    end = start + 1 + m.start() if m else len(js)
    return js[start:end]


# ---------------------------------------------------------------- 1. 预设入口

def test_preset_links_replaced_load_variant_row():
    """R19.91：LOAD VARIANT 行整行删除，预设入口移到二级工具条（R19.97 去掉重复的「加载预设」）。"""
    html = _read(HTML)
    for gone in ('class="gw-loadvar"', 'id="gw-default"', 'id="gw-save"',
                 'id="gw-clearall"', 'id="gw-undo"', 'id="gw-preset-state"',
                 'id="gw-load-link"'):
        assert gone not in html, "旧控件必须删除：%s" % gone
    wrap = html[html.index('id="gw-preset-links"'):]
    wrap = wrap[:wrap.index('</span>')]
    order = ['id="gw-save-link"', 'id="gw-read-link"', 'id="gw-clear-link"', 'id="gw-hint"']
    pos = [wrap.index(x) for x in order]
    assert pos == sorted(pos), "顺序必须是 保存配枪 → 读取预设 → 清空预设 →（提示）"

    js = _read(APP)
    assert 'el.gwSaveLink = $("gw-save-link")' in js
    assert 'el.gwReadLink = $("gw-read-link")' in js
    assert 'el.gwClearLink = $("gw-clear-link")' in js
    assert 'el.gwLoadLink' not in js, "「加载预设」与「读取预设」重复，已删除"
    handler = _slice(js, "if (el.gwSaveLink) {", "if (el.gwReadLink) {")
    assert "window.prompt(" in handler, "点击后必须允许用户输入预设名称"
    assert "gbSaveCurrent(name)" in handler, "输入的名称必须交给保存逻辑"
    assert name_guard(handler), "名称为空时必须拒绝保存（不发请求、不写脏数据）"
    # 清空预设 = 恢复官方默认装配
    clear = _slice(js, "if (el.gwClearLink) {", "document.addEventListener(\"click\"")
    assert "applyDefaultBuild(false)" in clear
    # 读取预设 = 把隐藏的 #gw-ref 选项渲染成菜单
    menu = _slice(js, "function openGunPresetMenu(", "if (el.gwSaveLink) {")
    assert "el.gwRef.options" in menu
    assert '"内置参考预设"' in menu and "applyBuiltinGunPreset" not in menu, \
        "菜单只负责选值，载入仍由 #gw-ref 的 change 处理器统一执行"


def name_guard(handler):
    """名称为空时不得调用保存：检查 `if (!name) { ... return; }` 这类守卫存在。"""
    return bool(re.search(r'if \(!name\)[^\n]*\n[^\n]*return', handler)) or \
           bool(re.search(r'if \(!name\) \{.*?return;.*?\}', handler, re.S))


# ---------------------------------------------------------------- 2. 保存 / 载入

def test_save_preset_writes_local_store_and_marks_user_preset():
    js = _read(APP)
    save = _fn(js, "gbSaveCurrent")
    assert "window.GB.serialize" in save, "保存内容来自引擎序列化（含枪械 id 与槽位装配）"
    assert 'obj.id = "b"' in save, "预设要有稳定 id"
    assert "gbStoreLoad()" in save and "gbStoreWrite(" in save, "写入本地预设存储"
    assert "g.userPresetId = obj.id" in save, "保存后把当前装配标记为该本机预设"
    assert "persistGun()" in save, "保存后持久化当前枪械状态"
    assert "gunToast(" in save, "保存成功要有可见反馈"

    key = re.search(r'var GB_STORE_KEY = "([^"]+)"', js)
    assert key and key.group(1) == "eftmap.gunbuilds.v1", "本机预设存储键保持不变"
    assert "localStorage.setItem(GB_STORE_KEY" in _fn(js, "gbStoreWrite")


def test_user_presets_are_grouped_in_dropdown_and_load_with_user_preset_id():
    js = _read(APP)
    ref = _fn(js, "renderGunRefOptions")
    assert "我的预设（本机）" in ref, "用户预设与内置预设必须分组显示"
    assert '"u:" + b.id' in ref, "用户预设选项值必须带 u: 前缀"
    assert "g.userPresetId && userIds.indexOf(g.userPresetId) >= 0" in ref, \
        "刷新后下拉要回显到当前本机预设"

    bind = _slice(js, "if (el.gwRef) {", "// R19.1：视图模式页签")
    assert 'v.indexOf("u:") === 0' in bind, "change 事件要区分 u: 用户预设"
    assert "gbLoadBuild(obj, { userPresetId: obj.id })" in bind, "载入时带上来源 id"

    load = _fn(js, "gbLoadBuild")
    assert "g.userPresetId = opts.userPresetId" in load, "载入后要记住来源（刷新可回显）"
    assert "persistGun()" in load and "renderGun(" in load
    assert "window.GB.sanitize" in load, "载入前必须过真实槽位兼容校验"


def test_default_restore_does_not_remove_user_presets():
    js = _read(APP)
    dft = _fn(js, "applyDefaultBuild")
    assert 'g.userPresetId = ""' in dft, "恢复默认只是取消选中，不等于删除"
    assert "gbStoreWrite" not in dft and "localStorage.removeItem" not in dft, \
        "恢复默认不得删除本机预设"


def test_preset_state_text_is_short_with_full_name_in_title():
    js = _read(APP)
    info = _fn(js, "gunPresetStateInfo")
    for txt in ("内置 · 已装载", "本机 · 未改动", "本机 · 改 ", "未保存（改装中）"):
        assert txt in info, "预设状态短文缺失：%s" % txt
    assert "title: \"预设：" in info, "完整预设名放进悬停 title（行内不靠省略号）"
    assert "diffAgainstDefault" in info, "改动数按当前装配与该预设比较"
    css = _read(CSS)
    st = _body(css, ".gun-workbench .gw-preset-state {")
    assert "max-width: 150px" in st and "text-overflow: ellipsis" in st


# ---------------------------------------------------------------- 3. 弹药后坐力 / ACC

def test_ammo_candidate_columns_show_recoil_and_accuracy():
    js = _read(APP)
    cols = _fn(js, "gunAmmoColumns")
    assert 'label: "后坐力"' in cols and 'label: "ACC"' in cols
    assert cols.count('width: "62px"') >= 2, "两列都要有足够宽度，避免 +10.0% 被裁切"
    assert "gunAmmoModPct" in cols
    assert "recoilModifier" in cols and "accuracyModifier" in cols, \
        "必须说明字段来源，确认是弹药修正而非枪械后坐力"
    assert "不是枪械本身的后坐力" in cols
    assert "散布增加" in cols, "ACC 的含义要在 tooltip 里写清（正值 = 精度下降）"
    for bad in ("rpm", "recoilV", "gunRecoil"):
        assert bad not in cols, "弹药列不得混入枪械自身后坐力字段：%s" % bad

    rows = _fn(js, "gunAmmoRows")
    assert "a.rec" in rows and "a.acc" in rows, "行数据直接取弹药库字段"
    assert "isFinite" in rows, "非数值一律按缺失处理"
    pct = _fn(js, "gunAmmoModPct")
    assert 'return "—"' in pct and 'return "0%"' in pct and "amSignPct" in pct


def test_ammo_modifier_data_is_real_and_differs_per_round():
    ammo = _json(AMMO)["ammo"]
    assert len(ammo) >= 100
    for a in ammo:
        for k in ("rec", "acc"):
            assert k not in a or isinstance(a[k], (int, float)), \
                "%s 的 %s 必须是数值或缺失" % (a.get("n"), k)
    with_rec = [a for a in ammo if isinstance(a.get("rec"), (int, float))]
    assert len(with_rec) == len(ammo), "本地弹药库每条都应有 recoilModifier"
    nonzero = [a for a in with_rec if a["rec"] != 0]
    assert len(nonzero) >= 3, "至少三种弹药有非零后坐力修正，可用于实际核对"
    combos = {(a.get("rec"), a.get("acc")) for a in ammo}
    assert len(combos) >= 50, "不同弹药的后坐力/ACC 组合必须来自各自真实数据"

    # 至少三种属性不同的弹药，用于页面实测核对（名称 / 后坐力 / ACC）
    picks = [a for a in ammo if a.get("rec") not in (0, None)][:3]
    assert len(picks) == 3
    assert len({(a["rec"], a["acc"]) for a in picks}) == 3, "抽样弹药必须属性不同"
    for a in picks:
        assert -10 <= a["rec"] <= 10 and -10 <= a["acc"] <= 10, "修正量是小数比例，不是百分比数值"


def test_ammo_price_prefers_trader_buy_then_base_reference():
    js = _read(APP)
    fn = _fn(js, "ammoPriceOf")
    assert "b.rub" in fn and "a.base" in fn
    assert 'kind: "buy"' in fn and 'kind: "base"' in fn
    assert "> 0" in fn, "非正数不得当作有效报价"
    ammo = _json(AMMO)["ammo"]
    miss = 0
    for a in ammo:
        b = a.get("buy")
        ok = (isinstance(b, dict) and isinstance(b.get("rub"), (int, float)) and b["rub"] > 0) or \
             (isinstance(b, (int, float)) and b > 0) or \
             (isinstance(a.get("base"), (int, float)) and a["base"] > 0)
        if not ok:
            miss += 1
    assert miss == 0, "弹药价格列应能对全部弹药给出报价或明确缺价，实际缺 %d 条" % miss
    assert all(a.get("flea") in (None, 0, []) for a in ammo), \
        "本地弹药库没有跳蚤报价，价格列不得伪装成跳蚤价"


# ---------------------------------------------------------------- 4. 成本第三行

def test_cost_row_is_third_row_of_stats_grid():
    js = _read(APP)
    stats = _fn(js, "renderGunStatsV2")
    order = _slice(js, "var GW_STAT_ORDER", "];")
    labels = re.findall(r'"([a-zA-Z]+)"', order)
    assert len(labels) == 9, "前 9 项在 5 列网格里占满两行，成本才能固定第三行"
    assert "gw-costrow" in stats
    assert 'costCell("整枪成本（含原厂件）"' in stats
    assert 'costCell("其中改装件"' in stats
    assert "includeStock: true" in stats and "includeStock: false" in stats
    assert stats.index("gw-costrow") > stats.index('"隐藏属性"'), \
        "成本块必须在属性项之后追加（第三行），不得移到第一 / 第二行"
    assert "g.installed || {}" in stats, "成本必须按当前装配计算，不写死"
    assert "missingPrice" in stats, "缺价件必须提示，不得按 0 计"

    css = _read(CSS)
    assert "grid-template-columns: repeat(5, 1fr);" in css, \
        "属性面板必须 5 列（9 项占两行，成本才能稳定第三行）"
    # 更窄的窗口（<=900px）才退化为 2 列，不影响 1920 / 1384 两档验收
    i2 = css.find("repeat(2, 1fr)", css.find(".gun-workbench .gw-stats {"))
    if i2 >= 0:
        assert "@media (max-width: 900px)" in css[max(0, i2 - 220):i2]
    row = _body(css, ".gun-workbench .gw-stats .gw-costrow {")
    assert "grid-column: 1 / -1" in row, "成本行横跨整行"
    assert "display: flex" in row, "两项必须并排"
    num = _body(css, ".gun-workbench .gw-stats .gw-cost .gw-stat-num {")
    assert "font-size: 8.5px" in num, "金额字体缩小但仍可读"
    assert "white-space: nowrap" in num, "金额与 ₽ 不得换行省略"
    lab = _body(css, ".gun-workbench .gw-stats .gw-cost .gw-stat-lab {")
    assert "overflow: visible" in lab and "text-overflow: clip" in lab, "标签不得省略号截断"


# ---------------------------------------------------------------- 5. 逐部件价格

def test_parts_timeline_uses_icon_left_and_trader_flea_prices_right():
    js = _read(APP)
    bottom = _fn(js, "renderGunBottom")
    for h in ("部件", "人机", "后坐", "默认", "商人价"):
        assert '"%s"' % h in bottom, "时间线表头缺列：%s" % h
    assert 'pmLabel + " 价"' in bottom, "市场价列表头必须跟随当前价格口径"
    assert 'className = "tbl-icon gw-tl-icon"' in bottom, "每行左侧要有部件自己的图标"
    assert bottom.index("cellName.appendChild(img)") < bottom.index("cellName.appendChild(nmTxt)"), \
        "图标必须在名称左侧"
    assert "buyPriceOf(rec)" in bottom, "商人价复用配装界面同一取价函数"
    assert 'itemPrice(rec)' in bottom, "市场价复用配装界面同一取价函数（跟随当前口径）"
    assert 'tb2.textContent = buy > 0 ? fmtMoney(buy) : "—"' in bottom
    assert 'tf.textContent = flea > 0 ? fmtMoney(flea) : "—"' in bottom
    assert "不按 0" in bottom, "缺价只显示 —，不填猜测值"

    css = _read(CSS)
    assert "width: 74px" in _body(css, ".gun-workbench .gw-timeline td.gw-tl-price {")
    icon = _body(css, ".gun-workbench .gw-timeline .gw-tl-icon {")
    assert "width" in icon and "height" in icon


def test_part_price_logic_matches_loadout_shared_helpers():
    js = _read(APP)
    buy = _fn(js, "buyPriceOf")
    assert 't.k !== "buy"' in buy, "商人买入价只取 buy 报价（不混出售价）"
    assert "p <= 0" in buy and "p < best" in buy, "取有效的最低买入报价"
    price = _fn(js, "itemPrice")
    assert "priceModeOf(" in price, "跳蚤价复用配装界面的价格档位函数"
    assert "fields" in price and "return v" in price
    assert "return 0" in price, "没有可用值时返回 0，由界面显示 —（不顶替别的档位）"
    assert 'key: "last"' in js and 'key: "avg24h"' in js and 'key: "avg7d"' in js, \
        "价格档位必须与市场页同口径（最新 / 24h / 7d）"


# ---------------------------------------------------------------- 6. 分页筛选

CLASSES = {
    "5447b5f14bdc2d61278b4567": "突击步枪",
    "5447b5cf4bdc2d65278b4567": "手枪",
    "5447b5e04bdc2d62278b4567": "冲锋枪",
    "5447b6094bdc2dc3278b4567": "霰弹枪",
    "5447b6194bdc2d67278b4567": "精确射手步枪",
    "5447b6254bdc2dc3278b4568": "栓动狙击步枪",
    "5447b5fc4bdc2d87278b4567": "卡宾枪",
    "5447bed64bdc2d97278b4568": "机枪",
    "617f1ef5e8b54b0998387733": "左轮",
    "5447bedf4bdc2d87278b4568": "榴弹发射器",
}
HANDGUN = ("手枪", "左轮")


def _filter_expected(kind="", fire=""):
    guns = _json(GUNSLOTS)["guns"]
    items = _json(ITEMS)["items"]
    stats = _json(GUNSTATS)["guns"]
    out = []
    for gid in guns:
        rec = items.get(gid) or {}
        cat = (rec.get("cats") or [""])[0]
        cls = CLASSES.get(cat, "其它")
        if kind:
            is_hand = cls in HANDGUN
            if (kind == "primary" and is_hand) or (kind == "handgun" and not is_hand):
                continue
        if fire:
            fm = [str(x).lower() for x in (stats.get(gid) or {}).get("fm") or []]
            ok = any(
                (fire == "fullauto" and m in ("fullauto", "auto")) or
                (fire == "single" and m == "single") or
                (fire == "burst" and m == "burst")
                for m in fm
            )
            if not ok:
                continue
        out.append(gid)
    return set(out)


def test_filter_chips_use_real_class_and_fire_mode_fields():
    js = _read(APP)
    filt = _fn(js, "gwFilteredGuns")
    assert "GW_HANDGUN_CLASSES[gunClassOf(id)]" in filt, "武器类别按上游分类 cats[0] 判定"
    assert "gun-stats" in filt or "state.gunStats" in filt
    assert ".fm" in filt and "gwFireMatch" in filt, "射击模式按 gun-stats.json 的 fm 字段"
    assert "gunName" not in filt, "不得用枪械名称关键字代替真实字段"
    assert not re.search(r"\.n\b", filt), "不得拿名称字段当分类依据"

    match = _fn(js, "gwFireMatch")
    assert 'm === "fullauto" || m === "auto"' in match
    assert 'm === "single"' in match and 'm === "burst"' in match

    click = _slice(js, "function gwChipClick(host, group) {", "gwChipClick(el.gwKindchips")
    assert "gwGroupActive(group) === k" in click, "再点已选条件 = 清除本组"
    assert "st[x] = (x === k)" in click, "同组单选，另一组不受影响"
    assert "renderGun();" in click, "点击必须真正重绘列表"

    sync = _fn(js, "gwSyncFilterUI")
    assert 'setAttribute("aria-pressed"' in sync
    assert "el.gwFilterState" in sync
    assert '"筛选："' in sync and '"全部枪械 · "' in sync, "状态文字要能直接读出当前条件"
    assert "gwFilteredGuns().length" in sync, "状态里的数量来自真实筛选结果"

    html = _read(HTML)
    for attr in ('data-gwkind="primary"', 'data-gwkind="handgun"',
                 'data-gwfire="fullauto"', 'data-gwfire="single"', 'data-gwfire="burst"'):
        assert attr in html, "按钮缺少真实筛选字段：%s" % attr
        assert 'aria-pressed="false"' in html

    css = _read(CSS)
    on = _body(css, '.gun-workbench .gw-chip[aria-pressed="true"] {')
    assert "background" in on and "border-color" in on, "选中与未选中必须有明显区分"
    state = _body(css, '.gun-workbench .gw-filterstate[data-on="1"] {')
    assert "font-weight: 700" in state


def test_filter_expected_counts_match_local_data():
    guns = _json(GUNSLOTS)["guns"]
    total = set(guns)
    primary = _filter_expected("primary")
    handgun = _filter_expected("handgun")
    assert primary | handgun == total and not (primary & handgun), "两组互补覆盖全部枪械"
    assert len(total) == 163 and len(primary) == 132 and len(handgun) == 31

    auto = _filter_expected("", "fullauto")
    single = _filter_expected("", "single")
    burst = _filter_expected("", "burst")
    assert len(auto) == 89 and len(single) == 156 and len(burst) == 7
    assert auto <= total and single <= total and burst <= total
    assert auto & single, "同一把枪可以既有 Auto 也有 Single（fm 多模式）"
    assert len(_filter_expected("primary", "fullauto")) == 86
    assert len(_filter_expected("primary", "single")) == 125
    assert len(_filter_expected("handgun", "single")) == 31

    stats = _json(GUNSTATS)["guns"]
    no_fm = [gid for gid in guns if not (stats.get(gid) or {}).get("fm")]
    assert not no_fm, "本地射击模式数据必须完整，否则按钮无法真实筛选"


# ---------------------------------------------------------------- 7. FORGE 瞄具

def test_forge_optic_tiers_replace_single_toggle():
    js = _read(APP)
    forge = _fn(js, "renderGunForge")
    assert 'var TIER_LABEL = { near: "近", mid: "中", far: "远" }' in forge
    assert '["near", "mid", "far"]' in forge, "三档必须是真实按钮"
    assert "forgeTierOptics(f.opticTier)" in forge, "点击档位后列出该档位兼容瞄具"
    assert "forgeMagText(o)" in forge, "列表要显示倍率信息"
    assert 'aria-pressed' in forge
    # R19.10：选中具体型号后必须收起候选列表（不再是把候选全部铺开、只换个底色）
    assert "f.opticId = o.id;" in forge, "点瞄具名写入真实 item id"
    assert "f.opticOpen = false;" in forge, "选定后必须收起候选列表（只留这一款）"
    assert "f.opticOpen = true;" in forge, "再点档位 / 已选型号要能重新展开候选"
    assert '已选：' in forge and 'TIER_LABEL[f.opticTier]' in forge, "显示档位与已选瞄具名"
    assert "forgeMagText(selOptic)" in forge, "收起态只显示已选型号时也要带倍率"
    assert 'f.opticTier = ""; f.opticId = "";' in forge, "必须能清除必需瞄具"
    assert "没有兼容瞄具" in forge, "无兼容瞄具时要明确提示"


def test_forge_selected_optic_and_features_feed_optimizer():
    js = _read(APP)
    cons = _slice(js, "function forgeConstraints() {", "function forgeBuildNote(")
    assert "cons.scopeId = f.opticId" in cons, "选中瞄具接入引擎的 scopeId 约束"
    # R19.9：手电/激光由功能开关升级为具体型号 → deviceIds；旧 features 仅作布尔兼容
    assert "cons.deviceIds = devIds" in cons, "选定型号必须进入引擎约束"
    assert '["light", "laser"].forEach(function (k) {' in cons
    assert "if (feats.length) { cons.features = feats; }" in cons, "布尔兼容路径保留"

    forge = _fn(js, "renderGunForge")
    assert "constraints: forgeConstraints()" in forge, "生成方案必须带同一份约束"
    assert "window.GB.verifyBuild(ctx, g.gunId, res.installed, cons" in forge, \
        "应用前必须做整树终检（结构 + 互斥 + 约束 + 声称件是否还在）"
    note = _slice(js, "function forgeBuildNote(b) {", "var head = document.createElement")
    assert "未满足" in note, "结果行要显示约束是否被实际设备满足"
    assert "(devs[hit] || {}).n" in note, "要显示满足约束的真实设备名"
    assert "要求 " in note, "未满足时必须写出所要求的具体型号"

    assert '[["light", "手电"], ["laser", "激光"]]' in forge, "手电 / 激光是两个独立选择区"
    # R19.10：手电 / 激光统一成「手电 | 激光 | 清除」三个按钮，选定后同样收起列表
    assert "f.devices[key] = id;" in forge, "点型号=写入真实 item id（不是布尔切换）"
    assert 'f.devOpen = "";' in forge, "选定型号后收起候选列表"
    assert 'f.devOpen = (f.devOpen === key) ? "" : key' in forge, "再点同一按钮可重新展开 / 收起"
    assert 'f.devices.light = ""' in forge and 'f.devices.laser = ""' in forge, \
        "「清除」必须同时取消两个设备的型号约束"
    assert "款兼容" in forge, "列表按当前枪械真实兼容性过滤（显示可安装型号数）"
    assert "没有兼容的" in forge, "无兼容型号时必须明说，而不是展示全部设备"
    assert "gw-forge-bad" in forge and "violations[0].why" in forge, "无解要标红并说明原因"


def test_engine_supports_scope_id_and_feature_constraints():
    gb = _read(BUILDER)
    cc = _fn(gb, "checkConstraints")
    assert "cons.scopeId" in cc, "终检必须校验具体瞄具"
    assert 'kind: "scopeId"' in cc
    assert "cons.features" in cc and "violations.push" in cc, "终检必须校验功能约束"
    assert "cons.deviceIds" in cc and 'kind: "deviceId"' in cc, "终检必须逐件校验选定型号"
    ri = _fn(gb, "resolveInstall")
    assert "carries" in ri and "slots" in ri, "允许通过一级转接座（真实槽位链）安装"
    opt = _fn(gb, "optimize")
    assert "cons.scopeId" in opt and "cons.features" in opt, "优化器搜索阶段遵守约束"
    assert "(cons.deviceIds || []).forEach" in opt, "选定型号计入必装预装"


def test_forge_constraint_audit_data_is_complete_and_consistent():
    f = _json(FORGE)
    assert f.get("schema") == "eftmap.forge-constraints/1"
    optics = f.get("optics") or []
    devices = f.get("devices") or []
    assert len(optics) == 78 and len(devices) == 26

    items = _json(ITEMS)["items"]
    bad = []
    tiers = {"near": 0, "mid": 0, "far": 0}
    for o in optics:
        assert o.get("id") and o.get("n") and o.get("src"), "瞄具审计项字段不全"
        mn, mx, t = o["min"], o["max"], o["tier"]
        assert mn <= mx, "倍率区间非法：%s" % o.get("n")
        tiers[t] += 1
        # 任务书分类：固定 1× → 近；最高 ≤4× → 中；最高 >4× → 远
        ok = ((t == "near" and mn == mx == 1) or
              (t == "mid" and mx <= 4 and not (mn == mx == 1)) or
              (t == "far" and mx > 4))
        if not ok:
            bad.append((o.get("n"), mn, mx, t))
        rec = items.get(o["id"])
        assert rec, "瞄具 id 不在本地 items.json：%s" % o.get("id")
        assert rec.get("n") == o.get("n"), "瞄具名称与本地物品库不一致：%s" % o.get("id")
    assert not bad, "倍率分档与任务书规则不一致：%s" % bad[:5]
    assert tiers == {"near": 34, "mid": 27, "far": 17}

    for d in devices:
        assert d.get("id") and d.get("n") and d.get("src")
        assert isinstance(d.get("light"), bool) and isinstance(d.get("laser"), bool)
        assert d["id"] in items, "设备 id 不在本地 items.json：%s" % d.get("id")
    assert sum(1 for d in devices if d["light"]) == 13
    assert sum(1 for d in devices if d["laser"]) == 18
    assert sum(1 for d in devices if d["light"] and d["laser"]) == 5, \
        "需要存在双功能设备，用于手电 + 激光同时约束的单一设备方案"


# ---------------------------------------------------------------- 8. R19.7 保留项

def test_r19_7_layout_contract_kept():
    html = _read(HTML)
    order = ['id="gw-meta"', 'id="gw-visual"', 'id="gw-tree"',
             'id="gw-bars"', 'id="gw-stats"', 'id="gw-hidden"']
    pos = [html.index(x) for x in order]
    assert pos == sorted(pos), "中栏顺序被破坏：信息条 → 枪身图 → 画布 → 属性条 → 属性 → 隐藏"
    assert 'id="gw-meta"' in html[:html.index('id="gw-tree"')], "枪械信息条在画布之前"
    js = _read(APP)
    tree = _fn(js, "renderGunTree")
    code = re.sub(r"//[^\n]*", "", tree)
    assert "官方预设：" not in code
    assert "gw-gun-rpm" in code and "gw-gun-dps" in code
    bottom = _fn(js, "renderGunBottom")
    assert "内部槽位" not in bottom and "合法配件" not in bottom, "不得恢复开发者调试文本"
