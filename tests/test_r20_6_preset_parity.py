# -*- coding: utf-8 -*-
"""R20.6：配装页（/preset）按钮功能复刻的自动化测试。

对照参考站 https://db4tarkov.com/preset 的候选表顶栏，本轮落地 5 个筛选 + 3 个分项排序：
  护甲等级（Class） / 商人等级 ≤ N（only TraderLvl） / 重量 ≤ kg（Max Kg）
  / 防弹等级 ≥（Min Built-in） / 惩罚 ≤%（Max Penalty）
  / 移动·转身·人机 三个分项排序（Mov / Turn / Ergo）

另记录明确的「不做」项与其原因（见 docs/r20.6/REPORT.md）：
  only FleaLvl（本地无跳蚤等级数据）、行尾 X 屏蔽（参考站语义未证实）。

本轮只改前端，不写业务数据；全部断言基于真实磁盘文件与静态代码契约。
"""
import hashlib
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "style.css")


def _read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


def _fn(js, name, nxt=None, span=4000):
    m = re.search(r"function %s\s*\(" % re.escape(name), js)
    assert m, "找不到函数 %s" % name
    start = m.start()
    if nxt:
        m2 = re.search(r"function %s\s*\(" % re.escape(nxt), js[start + 10:])
        assert m2, "找不到后续函数 %s" % nxt
        end = start + 10 + m2.start()
    else:
        end = min(len(js), start + span)
    return js[start:end]


# ---------------------------------------------------------------- 界面骨架
def test_filter_bar_exists_in_html():
    html = _read(HTML)
    for needle in ('id="lw-filters"', 'id="lw-cl"', 'id="lw-trader-level"', 'id="lw-flea-level"',
                   'id="lw-maxkg"', 'id="lw-mincl"', 'id="lw-maxpen"',
                   'id="lw-fl-state"'):
        assert needle in html, "缺少筛选条控件：%s" % needle
    # R20.7 起排序按钮从 3 个扩到 5 个（补上参考站表头同样可点的 Kg / Price），
    # 这里不再钉死总数，只要求「至少覆盖三项机动分项」且每个键唯一。
    for key in ("mov", "turn", "ergo"):
        assert 'data-lwsort="%s"' % key in html, "缺少排序按钮 %s" % key
    sort_keys = re.findall(r'data-lwsort="([a-z]+)"', html)
    assert len(sort_keys) >= 3, "至少要有 3 个分项排序按钮"
    assert len(set(sort_keys)) == len(sort_keys), "排序按钮的键不能重复"


def test_filter_bar_sits_above_table():
    html = _read(HTML)
    assert html.index('id="lw-filters"') < html.index('id="gear-table"'), \
        "筛选条必须在候选表上方（与参考站一致）"


def test_filter_bar_styles_scoped_to_loadout():
    css = _read(CSS)
    assert ".loadout-workbench .lw-filters" in css
    assert ".loadout-workbench .lw-sortbtn.is-on" in css
    # 不允许出现全局作用域的同类名（会污染地图/配枪视图）
    assert "\n.lw-filters {" not in css


# ---------------------------------------------------------------- 状态与事件
def test_state_fields_added():
    js = _read(APP)
    for f in ("lwCl", "lwTraderLevelOn", "lwFleaLevelOn", "lwMaxKg", "lwMinCl", "lwMaxPen", "lwSort"):
        assert re.search(r"^\s*%s:\s*" % f, js, re.M), "缺少状态字段 %s" % f


def test_events_wired():
    js = _read(APP)
    assert 'el.lwCl = $("lw-cl")' in js
    assert 'el.lwTraderLevel = $("lw-trader-level")' in js
    assert 'el.lwFleaLevel = $("lw-flea-level")' in js
    assert 'el.lwSortBtns = Array.prototype.slice.call(document.querySelectorAll(".lw-sortbtn"))' in js
    for key in ("lwMaxKg", "lwMinCl", "lwMaxPen"):
        assert 'bindLwFilter(el.%s, "%s", true)' % (
            {"lwMaxKg": "lwMaxKg", "lwMinCl": "lwMinCl", "lwMaxPen": "lwMaxPen"}[key], key) in js


# ---------------------------------------------------------------- 筛选真的生效
def test_five_filters_applied_in_gear_rows():
    js = _read(APP)
    fn = _fn(js, "gearRows", "equippedTradeTotals", span=9000)
    assert "state.lwCl" in fn and "rec.cl" in fn, "护甲等级筛选未接入"
    assert "state.lwMinCl" in fn and "baseArmorClassOf" in fn, "防弹等级下限未接入"
    assert "state.lwMaxKg" in fn and "rec.w" in fn, "重量上限未接入"
    assert "state.lwMaxPen" in fn and "penOf" in fn, "惩罚上限未接入"
    assert "state.lwTraderLevelOn" in fn and "traderAccessible" in fn, "商人等级筛选未接入"
    # 五个筛选都必须只是「跳过该行」，不能改动安装状态
    assert fn.count("continue;") >= 5
    assert "delete state.loadout" not in fn and "equipItem" not in fn


def test_penalty_sign_convention_documented():
    """pen.s/t/e 是负数分数；合计惩罚必须取绝对值，不能直接相加后当正数比较。"""
    js = _read(APP)
    fn = _fn(js, "gearRows", "equippedTradeTotals", span=9000)
    assert '-(penOf(rec, "s") + penOf(rec, "t") + penOf(rec, "e")) * 100' in fn


def test_trader_level_uses_shared_function():
    """配装与配枪的「商人等级」必须同一个函数口径，不能各写一份（R19.96 起统一读属性设置）。"""
    js = _read(APP)
    assert js.count("function traderAccessible(") == 1
    gun_filter = _fn(js, "gwFilteredGuns", "gwTraderMinLevel", span=4000)
    assert "traderAccessible(" in gun_filter
    gear_rows = _fn(js, "gearRows", "equippedTradeTotals", span=9000)
    assert "traderAccessible(" in gear_rows


# ---------------------------------------------------------------- 分项排序
def test_table_supports_virtual_sorters():
    js = _read(APP)
    m = re.search(r"function sorted\(rows\)\s*\{[\s\S]{0,2600}?\n    \}", js)
    assert m, "找不到 sorted() 实现"
    fn = m.group(0)
    assert "opts.sorters" in fn, "表格未支持虚拟排序键"
    assert "vSort" in fn
    assert "setSort: function (key, dir)" in js, "缺少 setSort 接口"
    assert "sortKey: function () { return view.sortKey; }" in js


def test_virtual_sort_key_survives_set_columns():
    js = _read(APP)
    m = re.search(r"setColumns: function \(next\) \{[\s\S]{0,600}?\n      \},", js)
    assert m, "找不到 setColumns 实现"
    assert "opts.sorters && opts.sorters[view.sortKey]" in m.group(0), \
        "换列集时虚拟排序键会被清掉，分项排序会失效"


def test_three_sorters_registered():
    js = _read(APP)
    i = js.find("sorters: {")
    assert i >= 0, "配装表没有注册 sorters"
    body = js[i:i + 400]
    for key, field in (("mov", "speed"), ("turn", "turn"), ("ergo", "ergo")):
        assert (key + ":") in body, "缺少分项排序 %s" % key
        assert ("r.%s" % field) in body, "排序 %s 应取 r.%s" % (key, field)


def test_sort_buttons_call_set_sort():
    js = _read(APP)
    assert "state.gearTable.setSort(state.lwSort)" in js
    assert 'state.lwSort = b.dataset.lwsort' in js


def test_sort_button_highlight_follows_table():
    js = _read(APP)
    fn = _fn(js, "renderGearFilters", "updateLwCount")
    assert "state.gearTable.sortKey()" in fn
    assert 'aria-pressed' in fn


# ---------------------------------------------------------------- 不越界
def test_no_business_data_write():
    js = _read(APP)
    for bad in ("writeFile", "writeFileSync", "saveJSON"):
        assert bad not in js


def test_business_data_hashes_unchanged():
    # 基线变更：2026-11-05 r79-eyewear-zones —— `data/items.json` 从
    # `599aef5e…4172d` 更新为 `33af6bd6…a3a9`。R79 依 `data/game-truth/armor_items.json`
    # 的 `props.armorColliders` 给 16 件空 `z` 的眼镜/面罩补防护区域（6B34 = `["Eyes"]`）；
    # 已核验差异仅为这 16 件新增 `z`（400 字节），回退后重新序列化可精确复现旧哈希。
    base = {
        # 2026-11-18 R300b：`sn` 从上游本地化键（"<id> ShortName"）替换为中文名表里的
        # 游戏内缩写（6B43 / PACA / ULACH / 帽…），文件因此变小。
        "data/items.json": "5e2c415eb1dcafa264b70b100e9a460a51dd8fbf79ac4579ef4324c28e97dfe0",
        "data/gunslots.json": "29b987b34a931b6ad5ec7587ff70bb36a112688e3303fb6467862fcaf21f8e3e",
        "data/gun-presets.json": "64e29bb5394bbd4a2d0845845f4ffc8748137fb8a8c216e77bd10e7cb452744b",
    }
    for rel, want in base.items():
        got = hashlib.sha256(io.open(os.path.join(ROOT, rel), "rb").read()).hexdigest()
        assert got == want, "%s 内容已变：%s" % (rel, got)


@pytest.mark.parametrize("name", ["renderGearFilters", "bindLwFilter"])
def test_new_functions_exist(name):
    # bindLwFilter 是事件接线区里的局部函数，只要求出现一次定义
    js = _read(APP)
    if name == "bindLwFilter":
        assert "function bindLwFilter(node, key, numeric)" in js
    else:
        assert "function %s(" % name in js


# ---------------------------------------------------------------- R20.6b 跳蚤上架等级
FLEA_LEVELS = os.path.join(ROOT, "data", "flea-levels.json")


def test_flea_levels_sidecar_structure():
    """sidecar 必须是真实上游数据的产物：字段名、来源、计数、逐件等级都要有。"""
    import json
    d = json.loads(_read(FLEA_LEVELS))
    assert d.get("schema") == 1
    assert d.get("field") == "minLevelForFlea", "字段名必须是上游真实字段"
    assert str(d.get("source", "")).startswith("https://json.tarkov.dev/"), d.get("source")
    assert d.get("fetchedAt"), "必须记录抓取时间"
    items = d.get("items") or {}
    assert isinstance(items, dict) and len(items) >= 5000, "物品数异常：%d" % len(items)
    # 每件都必须是合法等级（0 = 无限制）
    bad = [k for k, v in list(items.items())[:5000] if not isinstance(v, int) or v < 0]
    assert not bad, "存在非法等级：%s" % bad[:5]
    cnt = (d.get("counts") or {})
    assert cnt.get("total") == len(items)
    assert cnt.get("noRestriction") == sum(1 for v in items.values() if v == 0)
    # levels 汇总必须与逐件统计一致（防止汇总写错）
    from collections import Counter
    real = Counter(items.values())
    assert {int(k): v for k, v in d["levels"].items()} == dict(real), "levels 汇总与实际不符"


def test_flea_levels_not_inside_items_json():
    """跳蚤等级走独立 sidecar：items.json 只读，前端也没有任何写盘通道。"""
    js = _read(APP)
    assert 'loadJSON("data/flea-levels.json")' in js, "sidecar 必须走只读加载"
    assert 'loadJSON("data/items.json")' in js, "items.json 仍是只读取用"
    for bad in ("writeFile", "writeFileSync", "saveJSON"):
        assert bad not in js, "前端不应出现写盘能力：%s" % bad


def test_flea_level_reader_and_filter():
    js = _read(APP)
    assert "function fleaLevelOf(id)" in js
    fn = _fn(js, "fleaLevelOf", "renderQuoteStatus", span=900)
    assert "state.fleaLevels" in fn and "return (typeof v === \"number\"" in fn, \
        "缺失必须返回 null（不能当 0）"
    gear = _fn(js, "gearRows", "equippedTradeTotals", span=10000)
    assert "state.lwFleaLevelOn" in gear and "fleaLevelOf(" in gear
    assert "fl === null || fl > gwAttrMode().charLevel" in gear, \
        "R19.96：跳蚤等级对照属性设置里的角色等级；缺失物品必须按不可判定筛掉"


def test_flea_level_control_and_options():
    """R19.96：等级下拉改为勾选项，等级值统一读「属性设置」。"""
    html = _read(HTML)
    assert 'id="lw-flea-level"' in html and 'id="lw-trader-level"' in html
    js = _read(APP)
    assert 'el.lwFleaLevel = $("lw-flea-level")' in js
    assert 'el.lwTraderLevel = $("lw-trader-level")' in js
    fn = _fn(js, "renderGearFilters", "updateLwCount", span=3000)
    assert "if (!state.fleaLevels && state.lwFleaLevelOn) { state.lwFleaLevelOn = false; }" in fn, \
        "数据缺失时要安全退出并降级"
    assert "el.lwFleaLevel.checked !== !!state.lwFleaLevelOn" in fn, "勾选态要回填"


def test_flea_level_degrades_without_data():
    js = _read(APP)
    fn = _fn(js, "renderGearFilters", "updateLwCount", span=3000)
    assert "if (!state.fleaLevels && state.lwFleaLevelOn) { state.lwFleaLevelOn = false; }" in fn, \
        "数据缺失时要自动降级，避免筛出空表"
    assert "el.lwFleaLevel.disabled = !state.fleaLevels" in fn


def test_flea_levels_in_validator_whitelist():
    """新增 sidecar 必须纳入校验器白名单，否则会被当成「未归类 JSON」。"""
    v = _read(os.path.join(ROOT, "tools", "r20_validate_data.py"))
    assert '"flea-levels.json"' in v
    assert '"flea-prices.json"' in v
