# -*- coding: utf-8 -*-
"""R20.4 枪械构建器仿制（对照 db4tarkov Gun Builder）的静态与数据层测试。

覆盖本轮新增：
  - 枪械浏览卡显示价格与重量（参考站列表形态）
  - 候选表新增「商人价 / 解锁」列，且缺失整列不渲染
  - 商人解锁等级解析正确（真实 items.json 抽样核对）
  - 「仅商人可买」只影响显示，不改兼容性与装配状态
  - 不兼容配件仍被禁止装配
  - 运行期不引入外部资源

不触碰业务数据，只读。
"""
import io
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.js"
HTML = ROOT / "index.html"
CSS = ROOT / "style.css"
ITEMS = ROOT / "data" / "items.json"


def _read(p):
    return io.open(p, encoding="utf-8").read()


def _fn(js, name):
    """抽取 function <name>( ... ) 的源码块（按大括号配平）。"""
    i = js.index("function %s(" % name)
    j = js.index("{", i)
    depth = 0
    for k in range(j, len(js)):
        if js[k] == "{":
            depth += 1
        elif js[k] == "}":
            depth -= 1
            if depth == 0:
                return js[i:k + 1]
    raise AssertionError("函数 %s 未闭合" % name)


# ---------------------------------------------------------------- 浏览卡：空枪重 + 射速 + 缩写名
def test_browse_card_shows_weight_rpm_and_short_name():
    js = _read(APP)
    card = _fn(js, "gwGunCard")
    assert "gwGunDefaultWeight(" in card and "gw-card-wt" in card, "右下角空枪重"
    assert "gunRpmValue(" in card and "gw-card-rpm" in card, "左下角射速"
    assert "gwFireModeIcon(" in card and "gw-card-fire" in card, "左下角发射模式图标"
    assert "irec.sn" in card and "gw-card-short" in card, "右下角枪械缩写名"
    assert "GW_GUN_ADDED" in card and "gw-card-ver" in card, "左上角版本角标"
    assert "gw-card-presets" in card, "右上角本机预设数量"


def test_browse_card_styles_exist():
    css = _read(CSS)
    for cls in (".gw-card-ver", ".gw-card-presets", ".gw-card-foot",
                ".gw-card-rpm", ".gw-card-fire", ".gw-card-short"):
        assert cls in css, "缺卡片样式 %s" % cls


# ---------------------------------------------------------------- 候选表：商人价 + 解锁
def test_candidate_table_has_trader_columns():
    js = _read(APP)
    cols = _fn(js, "gunColumns")
    assert "COL_BUY" in cols and '"商人价"' in cols
    assert "COL_LV" in cols and '"解锁"' in cols
    # 缺失整列不渲染（沿用 R19.28 约定）
    assert 'if (any(function (r) { return typeof r.buy === "number"' in cols
    assert 'if (any(function (r) { return typeof r.lv === "number"' in cols


def test_trader_columns_use_real_helpers():
    js = _read(APP)
    assert "buyPriceOf(rec)" in js
    assert "function traderMinLevel(rec)" in js
    assert "traderMinLevel(rec)" in _fn(js, "gunRows")


def test_existing_columns_order_kept():
    """新增列不得打乱既有列序（配件 → 子槽 → 后坐力 → 人机 → R+E/3 → 尺寸 → 重量 → 价格 → 状态）。"""
    js = _read(APP)
    cols = _fn(js, "gunColumns")
    assert "var cols = [COL_N];" in cols, "第一列仍是配件列"
    # else 分支（普通配件表）内的既有列顺序——只看从 COL_SUB 开始的那段，
    # 避免弹匣分支（magazine）里同名列的先后影响判定。
    tail = cols[cols.index("cols.push(COL_SUB)"):]
    seq = ["COL_RECOIL", "COL_ERGO", "COL_RE3", "COL_SIZE", "COL_W"]
    pos = []
    for c in seq:
        m = re.search(r"cols\.push\(%s\)" % c, tail)
        assert m, "既有列 %s 仍在列装配中" % c
        pos.append(m.start())
    assert pos == sorted(pos), "既有列顺序被打乱：%s" % seq
    # R19.92：候选表不再显示「价格档（最新）」与「状态」两列
    assert "cols.push(COL_BUY)" in cols and "cols.push(COL_LV)" in cols
    assert "COL_PRICE" not in cols and "COL_STATE" not in cols


# ---------------------------------------------------------------- 商人等级解析（真实数据）
def test_trader_min_level_matches_real_data():
    items = json.load(io.open(ITEMS, encoding="utf-8"))["items"]

    def expect(rec):
        lv = None
        for t in (rec.get("trade") or []):
            if t.get("k") != "buy":
                continue
            l = t.get("l")
            if isinstance(l, (int, float)) and l > 0:
                lv = l if lv is None else min(lv, l)
        return lv

    checked = 0
    with_buy = 0
    without = 0
    for rec in items.values():
        got = expect(rec)
        if got is None:
            without += 1
            continue
        with_buy += 1
        buys = [t for t in (rec.get("trade") or []) if t.get("k") == "buy"]
        assert min(t["l"] for t in buys) == got
        checked += 1
        if checked > 400:
            break
    assert with_buy > 100, "真实数据里应存在大量可从商人购买的物品"
    assert without > 0, "真实数据里应存在只能跳蚤获得的物品"


def test_gun_base_price_and_weight_available_for_browse_cards():
    """浏览卡要用到的枪械本体价格/重量必须在本地数据里存在（不是编造）。"""
    guns = json.load(io.open(ROOT / "data" / "gunslots.json", encoding="utf-8"))["guns"]
    items = json.load(io.open(ITEMS, encoding="utf-8"))["items"]
    n = 0
    for gid in list(guns)[:200]:
        rec = items.get(gid)
        assert rec is not None, "枪械 %s 在 items.json 里没有对应条目" % gid
        assert isinstance(rec.get("p"), dict), gid
        assert isinstance(rec.get("w"), (int, float)), gid
        n += 1
    assert n >= 100


# ---------------------------------------------------------------- 仅商人可买：只影响显示
def test_only_trader_filter_is_display_only():
    js = _read(APP)
    body = _fn(js, "refreshGunTable")
    assert "gwOnlyTrader()" in body, "候选表需要支持「仅商人可买」过滤"
    assert 'rows = rows.filter(function (r) { return typeof r.buy === "number" && r.buy > 0; });' in body
    # 不得改兼容性结论或装配状态
    assert "r.conflict =" not in body
    assert "installed[" not in body
    assert "function gwOnlyTrader() { return !!state.gwOnlyTrader; }" in js


def test_only_trader_switch_wired():
    html = _read(HTML)
    assert 'id="gw-onlytrader"' in html, "候选栏需要「仅商人可买」开关"
    js = _read(APP)
    assert 'el.gwOnlyTrader = $("gw-onlytrader")' in js
    assert "state.gwOnlyTrader = !!el.gwOnlyTrader.checked;" in js


# ---------------------------------------------------------------- 不兼容仍禁止装配
def test_incompatible_parts_cannot_be_installed():
    js = _read(APP)
    fn = _fn(js, "gunEquip")
    assert "if (!chk.allowed)" in fn, "不兼容配件必须被拒绝"
    seg = fn[fn.index("if (!chk.allowed)"):fn.index("if (!chk.allowed)") + 400]
    assert "return;" in seg, "拒绝后必须直接返回，不改动装配"
    assert "无法安装" in fn, "拒绝时要给出可读原因"


def test_replacing_parent_cleans_children():
    js = _read(APP)
    fn = _fn(js, "gunEquip")
    assert "node.path + \"/\"" in fn, "换父配件时必须清理其子槽上的旧配件"
    assert "dropped" in fn


# ---------------------------------------------------------------- 价格口径 LAST（参考站 lastPrice）
def test_last_price_mode_uses_local_lastlow_field():
    js = _read(APP)
    assert '"last"' in js and '"最新"' in js, "价格档位需要「最新」（对应参考站 lastPrice）"
    assert 'fields: ["l"]' in js, "最新档必须取上游 lastLowPrice（p.l），不能拿别的字段冒充"
    # 2026-11：与市场页统一为 最新 / 24h 均价 / 7 日均价
    assert '"avg24h"' in js and '"avg7d"' in js, "必须与市场页同口径提供 24h / 7d"
    items = json.load(io.open(ITEMS, encoding="utf-8"))["items"]
    n = 0
    for rec in items.values():
        p = rec.get("p")
        if isinstance(p, dict) and isinstance(p.get("l"), (int, float)) and p["l"] > 0:
            n += 1
    assert n > 1000, "真实数据里应有大量 lastLowPrice 可用"


def test_gun_view_has_price_mode_pills():
    html = _read(HTML)
    # R265：价格口径上移到二级工具条 #vt-prices，枪械页不再单独一份
    assert 'id="gw-prices"' not in html, "枪械页不应再有自己的价格口径容器（已上移）"
    assert 'id="vt-prices"' in html, "需要全局价格口径容器 #vt-prices"
    js = _read(APP)
    assert "function renderGunPrices()" in js
    assert 'el.gwPrices = $("gw-prices")' in js


# ---------------------------------------------------------------- 商人等级门槛（R19.93 改为全局属性设置）
def test_trader_level_filter_moved_to_global_attrs():
    html = _read(HTML)
    assert 'id="gw-trader-lv"' not in html, "右栏的商人等级下拉已移除"
    assert 'id="am-attrs"' in html, "顶栏必须有属性设置入口"
    assert 'data-attrtab="traders"' in html and 'id="gw-attr-traders"' in html
    js = _read(APP)
    assert "function gwTraderLvLimit()" not in js
    assert "function gwTraderLevelOf(" in js
    body = _fn(js, "buyPriceOf")
    assert "gwTraderLevelOf(t.t)" in body, "商人报价必须按全局商人好感过滤"
    assert "gwAttrMode" in _fn(js, "gwTraderLevelOf")


def test_trader_level_values_are_real():
    """等级取值必须来自真实 trade[].l（1..4 区间），不是写死的假值。"""
    items = json.load(io.open(ITEMS, encoding="utf-8"))["items"]
    levels = set()
    for rec in items.values():
        for t in (rec.get("trade") or []):
            if t.get("k") == "buy" and isinstance(t.get("l"), (int, float)):
                levels.add(int(t["l"]))
    assert levels, "真实数据里应有商人解锁等级"
    assert max(levels) <= 6, "等级值异常：%s" % levels


# ---------------------------------------------------------------- 差额列（参考站属性增减角标）
def test_delta_columns_present():
    js = _read(APP)
    cols = _fn(js, "gunColumns")
    for c in ("COL_DERGO", "COL_DREC", "COL_DW", "COL_DPRICE"):
        assert c in cols, "缺少差额列 %s" % c
    for label in ("Δ人机", "Δ后坐", "Δ重量", "Δ价"):
        assert label in cols, "缺少差额列表头 %s" % label
    rows = _fn(js, "gunRows")
    assert "dErgo" in rows and "dRecoil" in rows and "dW" in rows and "dPrice" in rows
    # 差额必须有基准（当前槽位已装件），且缺数据时为 null 而不是 0
    assert "baseErgo" in rows and "baseRecoil" in rows and "baseW" in rows


def test_delta_columns_hidden_when_no_baseline():
    js = _read(APP)
    cols = _fn(js, "gunColumns")
    assert 'if (any(function (r) { return typeof r.dErgo === "number"; }))' in cols, \
        "没有基准（未装件/缺属性）时整列不渲染，沿用「缺失属性整列隐藏」约定"


# ---------------------------------------------------------------- 无外部资源
def test_no_external_runtime_resources():
    html = _read(HTML)
    for bad in ("cdn.", "unpkg", "jsdelivr", "googleapis", "fonts.g"):
        assert bad not in html, "不得引入外部资源: %s" % bad
    js = _read(APP)
    assert "fetch(\"http" not in js and "fetch('http" not in js


@pytest.mark.parametrize("f", ["app.js", "index.html", "style.css"])
def test_files_exist(f):
    assert (ROOT / f).is_file()
