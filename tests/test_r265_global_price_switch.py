# -*- coding: utf-8 -*-
"""R265：价格口径切换上移到二级工具条，全站统一。

用户要求（2026-11-12）：
  「将市场的最新价格 / 24h均价 / 7日均价三个切换按钮往上级移动，移到第二级
    （地图 任务 弹药 这一行），放在市场右侧，和市场之间留四个空字符的空间；
    然后配装 / 配枪 / 子弹这三个界面原本的价格切换按钮都去掉，都收第二级的
    这三个按钮支配。」
  追问确认：市场页额外保留「每格 / 每公斤」两个口径。

实现：
  · index.html 二级工具条新增 #vt-prices（市场右侧，4ch 间距）；
  · 删除 #lw-prices（配装）/ #gw-prices、#gw-browseprices（配枪）/ #am-price-mode（子弹）；
  · app.js 新增 renderVtPrices + setPriceMode 统一驱动 配装/配枪/市场/子弹；
  · market.js 只渲染 每格/每公斤，并暴露 window.GWMarket.setBasis 接收三档基准。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)

HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
APP = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
MARKET = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css"), encoding="utf-8").read()


def test_global_switcher_present_in_second_level_toolbar():
    assert 'id="vt-prices"' in HTML
    # 位于二级工具条内、市场按钮之后（紧跟「市场」组）
    assert HTML.index('id="view-switch"') < HTML.index('id="vt-prices"')
    assert HTML.index('id="view-btn-market"') < HTML.index('id="vt-prices"')


def test_four_page_switchers_removed():
    for gone in ('id="lw-prices"', 'id="gw-prices"', 'id="gw-browseprices"',
                 'id="am-price-mode"'):
        assert gone not in HTML, "旧的页面级价格切换未删除：%s" % gone


def test_toolbar_has_four_char_gap():
    assert "margin-left: 4ch" in CSS
    assert ".vt-prices" in CSS and ".vt-price" in CSS


def test_app_renders_and_drives_global_switch():
    assert "function renderVtPrices()" in APP
    assert "function applyPriceModeSideEffects()" in APP
    # 全局切换驱动市场 / 子弹
    assert "window.GWMarket.setBasis(" in APP
    assert "amFilterState().priceMode = state.priceMode" in APP
    # 二级工具条容器引用
    assert 'el.vtPrices = $("vt-prices")' in APP
    # 切换时刷新市场与子弹（side effects）
    i = APP.index("function setPriceMode(key) {")
    block = APP[i: APP.index("\n  }", i)]
    assert "applyPriceModeSideEffects()" in block


def test_market_keeps_only_slot_and_kg_and_exposes_setbasis():
    # buildModeButtons 跳过三档基准
    i = MARKET.index("function buildModeButtons()")
    block = MARKET[i: i + 700]
    assert 'm.key === "last" || m.key === "avg24h" || m.key === "avg7d"' in block
    assert "setBasis: setBasis" in MARKET
    assert "function setBasis(key)" in MARKET
