# -*- coding: utf-8 -*-
"""R267：配枪价格跟随模式/口径 + 弹药单位中文 + 配装内衬/价格加深 + meta 右移。

用户反馈（2026-11-12）：
  ①「获取最新数据 / 数据截止」再往右移 4 个空位符；
  ② 配枪界面切均价、切 PvP/PvE/PvPS 模式，价格都不变；
  ③ 弹药界面的单位按钮现在是英文，改成「公制 / 英制」；
  ④ 配装界面内衬护甲值/防弹等级、获取方式价格颜色太淡、对比度太低，字色再深一点。
"""

import os

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)

HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css"), encoding="utf-8").read()
XP = open(os.path.join(ROOT, "theme-windows-xp.css"), encoding="utf-8").read()


def test_meta_moved_four_chars_right():
    assert ".vt-market-meta" in CSS
    assert "margin-left: 4ch" in CSS


def test_ammo_units_chinese():
    assert ">公制</button>" in HTML
    assert ">英制</button>" in HTML
    assert ">metric<" not in HTML and ">imperial<" not in HTML


def test_items_get_id_for_snapshot_lookup():
    assert "state.items[_iid].id = _iid" in APP


def test_item_price_prefers_mode_snapshot():
    i = APP.index("function itemPrice(")
    block = APP[i: i + 900]
    assert "priceQuoteOf(rec.id)" in block
    # 无快照时仍回退构建期 rec.p
    assert "priceFieldsFor(rec)" in block


def test_gun_stats_cost_uses_market_price():
    i = APP.index("function renderGunStatsV2(")
    block = APP[i: i + 2600]
    assert "gunCostPrice" in block and "priceOf: gunCostPrice" in block


def test_refresh_price_views_covers_gun_and_price_arrival():
    i = APP.index("function refreshPriceViews() {")
    block = APP[i: i + 1200]
    assert 'state.view === "gun"' in block and "renderGunStats()" in block
    # 行情回包统一刷新所有视图
    j = APP.index("var notify = function () {")
    assert "refreshPriceViews()" in APP[j: j + 700]


def test_xp_overrides_darken_liner_and_price():
    for cls in (".lw-liner-cl", ".lw-liner-dur", ".lw-src-price", ".lw-src-req"):
        assert cls in XP
    assert "html .loadout-workbench .lw-liner-cl" in XP
    assert "html .loadout-workbench .lw-src-price" in XP
