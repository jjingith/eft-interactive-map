# -*- coding: utf-8 -*-
"""R258：三档价格优先级（用户需求）。

用户反馈（2026-11-12）：
  「rgd-5 这个手雷是跳蚤市场可以售卖的 但是现在识别后显示的是商人收购价格
    另外我觉得逻辑得改一下 如果跳蚤有售卖 则显示跳蚤价格 如果不能售卖 但是商人会卖
    则显示商人售卖价格  如果商人和跳蚤都不卖 则显示商人收购价格」

优先级：跳蚤价 > 商人售卖价 > 商人收购价。
对应 serve.py `_ocr_resolve_price` / scan.py `price_base` 及购物车颜色。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import serve  # noqa: E402
import scan  # noqa: E402

RGD_5 = "5448be9a4bdc2dfd2f8b456a"


# ---------------------------------------------------------------- 数据解析层

def _rec(**kw):
    base = {"n": "测试物品", "gw": 1, "gh": 1, "src": [], "ts": [], "trade": []}
    base.update(kw)
    return base


def test_flea_sellable_prefers_flea_price():
    """跳蚤可售卖 → 必须显示跳蚤价（RGD-5 bug 回归）。"""
    rec = _rec(src=["flea", "trader"], ts=["grenade"],
               sl=[[0, 2892]], trade=[{"k": "flea"}])
    row = {"lastLowPrice": 22000, "avg24hPrice": 21577}
    p = serve._ocr_resolve_price(rec, row, {}, 20000)
    assert p["priceSource"] == "flea"
    assert p["base"] == 22000
    assert p["lastLow"] == 22000 and p["avg24h"] == 21577
    assert "traderSell" not in p   # 跳蚤价分支不应带商人价字段
    assert "trader" not in p


def test_flea_sellable_missing_snapshot_uses_catalog_baseline():
    """跳蚤可售卖但实时快照缺失 → 回退目录 p.l/p.a，而不是掉到商人收购价。"""
    rec = _rec(src=["flea"], ts=[], p={"l": 25000, "a": 29187, "b": 7230})
    p = serve._ocr_resolve_price(rec, {}, {}, None)
    assert p["priceSource"] == "flea"
    assert p["base"] == 25000
    assert p["fleaFallback"] is True


def test_no_flea_but_trader_sells_shows_trader_sell():
    """跳蚤不卖但商人会卖 → 商人售卖价（玩家从商人处购买）。"""
    rec = _rec(src=["trader"], trade=[{"k": "buy", "t": "T", "l": 2, "c": "RUB", "p": 14750}])
    p = serve._ocr_resolve_price(rec, {}, {}, None)
    assert p["priceSource"] == "traderSell"
    assert p["base"] == 14750
    assert p["traderSell"] == 14750
    assert "trader" not in p          # 不应出现收购价字段


def test_neither_sells_shows_trader_buy():
    """商人和跳蚤都不卖 → 商人收购价（玩家卖给商人）。"""
    rec = _rec(src=["trader"], trade=[], sl=[[0, 2892], [1, 2819]])
    p = serve._ocr_resolve_price(rec, {}, {}, None)
    assert p["priceSource"] == "trader"
    assert p["base"] == 2892          # sl 里最高收购价
    assert p["trader"] == 2892


def test_trader_sell_offer_picks_cheapest():
    """多个商人都在卖 → 取最低买入价（最便宜的渠道）。"""
    rec = _rec(trade=[
        {"k": "buy", "c": "RUB", "p": 15000},
        {"k": "buy", "c": "RUB", "p": 12000},
        {"k": "barter"}, {"k": "buy", "c": "USD", "p": 99},
    ])
    val, tid, lvl = serve._trader_sell_offer(rec)
    assert val == 12000


def test_real_rgd5_record_is_flea():
    """真实 items.json 的 RGD-5：跳蚤可卖，解析必须是 flea。"""
    import json
    items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]
    rec = items.get(RGD_5)
    assert rec, "RGD-5 记录缺失"
    p = serve._ocr_resolve_price(rec, {"lastLowPrice": 22000}, {}, None)
    assert p["priceSource"] == "flea"
    assert p["base"] == 22000


# ---------------------------------------------------------------- 展示层

def test_price_base_honors_each_source():
    flea = {"price": {"priceSource": "flea", "lastLow": 22000, "avg24h": 21000, "avg7d": 20000}}
    sell = {"price": {"priceSource": "traderSell", "traderSell": 14750}}
    buy = {"price": {"priceSource": "trader", "trader": 2892}}
    assert scan.price_base(flea, "last") == 22000
    assert scan.price_base(flea, "w7") == 20000
    assert scan.price_base(sell, "last") == 14750
    assert scan.price_base(sell, "w7") == 14750   # 商人价不分口径
    assert scan.price_base(buy, "last") == 2892


def test_is_trader_price_covers_both_tiers():
    flea = {"price": {"priceSource": "flea"}}
    sell = {"price": {"priceSource": "traderSell", "traderSell": 1}}
    buy = {"price": {"priceSource": "trader", "trader": 1}}
    assert not scan.is_trader_price(flea)
    assert scan.is_trader_price(sell)
    assert scan.is_trader_price(buy)


def test_trader_price_kind_maps_to_cart_colour():
    assert scan.trader_price_kind({"price": {"priceSource": "trader"}}) == "buy"
    assert scan.trader_price_kind({"price": {"priceSource": "traderSell"}}) == "sell"
    assert scan.trader_price_kind({"price": {"priceSource": "flea"}}) == ""
    assert scan.trader_price_kind({"price": {}}) == ""


def test_manual_price_still_wins():
    """R253 手动选口径仍最高优先。"""
    m = {"price": {"priceSource": "traderSell", "traderSell": 14750, "manual": 999}}
    assert scan.price_base(m, "last") == 999


def test_serve_source_has_three_tier_contract():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert "_ocr_resolve_price" in src
    assert '"priceSource": "flea"' in src
    assert '"priceSource": "traderSell"' in src
    assert '"priceSource": "trader"' in src
