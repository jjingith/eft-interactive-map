# -*- coding: utf-8 -*-
"""R266：市场「获取最新数据 / 数据截止」上移到二级工具条最右；删除三页的价格来源/档位说明。

用户要求（2026-11-12）：
  「市场页的『获取最新数据』『数据截止 … · 近实时』也移动到二级栏，放在最右侧；
   配装的『40 条』『avg24hPrice：… 非实时』、配枪的『价格档 … 构建期快照，非实时行情』、
   子弹的『价格来源：实时不可用，已回退快照（PvP）』都去掉；这三页的价格依据应统一
   来源于市场界面的数据。」
"""

import os

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)

HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
MARKET = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css"), encoding="utf-8").read()


def test_market_meta_moved_into_toolbar():
    assert 'id="vt-market-meta"' in HTML
    assert HTML.index('id="vt-prices"') < HTML.index('id="vt-market-meta"')
    # 在工具条里有一席（R267 又把它右移了 4ch，见 test_r267）
    assert ".vt-market-meta" in CSS


def test_market_js_appends_cutoff_to_toolbar():
    assert 'document.getElementById("vt-market-meta")' in MARKET
    # 仍然保留原来的市场工具栏兜底
    assert 'root.querySelector(".mk-tb-main")' in MARKET


def test_loadout_count_and_notes_removed():
    assert 'id="lw-count"' not in HTML
    # 配装提示不再拼价格档说明
    i = APP.index("function syncLwFilters()")
    block = APP[i: APP.index("function ", i + 10)]
    assert "priceModeNote(" not in block
    # 配枪提示不再拼「构建期快照，非实时行情」
    assert "构建期快照，非实时行情" not in APP


def test_ammo_source_hint_removed():
    assert "价格来源：" not in APP
    assert "el.amHint.title = srcInfo.detail;" not in APP


def test_prices_still_share_market_source():
    # 三页仍读同一套价格来源 / 快照接口（未另起数据层）
    assert "function priceSourceInfo()" in APP
    assert "overlayQuoteFields" in APP
    assert "priceSourceInfo()" in APP
