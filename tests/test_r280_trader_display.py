# -*- coding: utf-8 -*-
"""R280：商人显示口径统一 + 识图浮窗禁售图标改造。

用户三条要求：
1. 市场界面「Sell to 商人收购价」要用任务界面里的商人头像（不是自绘 SVG 占位）；
2. 商人名字不要中文机翻，与任务界面一致，全部用英文原名；
3. 识图浮窗里跳蚤禁售（商人收购价）时，把红色购物车换成最高收购价商人的头像，
   后面再带价格。**只改这个红色购物车**：蓝购物车、跳蚤价、价格排版一律不动。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import config  # noqa: E402
import scan  # noqa: E402

MARKET_JS = (ROOT / "js" / "market.js").read_text(encoding="utf-8")
TASKS_TRADERS = json.loads(
    (ROOT / "data" / "tasks" / "traders.json").read_text(encoding="utf-8"))["traders"]
ITEMS_TRADERS = json.loads(
    (ROOT / "data" / "items.json").read_text(encoding="utf-8"))["traders"]

TIERS = config.OCR_SCAN_TIERS_DEFAULT
PRAPOR = "54cb50c76803fa8b248b4571"


def _trader_en_table() -> dict:
    m = re.search(r"var TRADER_EN = \{(.*?)\};", MARKET_JS, re.S)
    assert m, "market.js 里应有 TRADER_EN 表"
    return dict(re.findall(r'"([0-9a-f]{24})":\s*"([^"]+)"', m.group(1)))


# ---------------------------------------------------------------- 市场页：名字

def test_market_trader_names_match_tasks_view_exactly():
    """逐条等于 data/tasks/traders.json 的 nameEn（任务界面主显示名）。"""
    table = _trader_en_table()
    assert set(table) == set(ITEMS_TRADERS), "表要覆盖 items.json 里全部商人"
    for tid, en in table.items():
        assert TASKS_TRADERS[tid]["nameEn"] == en, "%s 与任务界面不一致" % tid


def test_market_trader_names_are_all_english():
    """不再出现中文机翻名；此前 'BTR司机'→'Btr Driver'、'Kerman'→'Mr Kerman'。"""
    table = _trader_en_table()
    assert table["656f0f98d80a697f855d34b1"] == "BTR Driver"
    assert table["688246518448b05efd61d461"] == "Mr. Kerman"
    assert table["68fe15990f29ba3fdbba9d55"] == "Radio Station"
    assert table["6617beeaa9cfa777ca915b7c"] == "Ref"
    for tid, en in table.items():
        assert not re.search(r"[\u4e00-\u9fff]", en), "%s 仍是中文：%s" % (tid, en)
    assert "if (TRADER_EN[id]) { return TRADER_EN[id]; }" in MARKET_JS


# ---------------------------------------------------------------- 市场页：头像

def test_market_uses_task_view_portrait():
    """头像路径 = 任务界面 db4Face 的 tr.portrait（portraits/<id>.webp）。"""
    assert 'var TRADER_PORTRAIT_DIR = "assets/icons-traders/portraits/"' in MARKET_JS
    assert "TRADER_PORTRAIT_DIR + id" in MARKET_JS
    for tid, rec in TASKS_TRADERS.items():
        assert rec["portrait"] == "assets/icons-traders/portraits/%s.webp" % tid
        assert (ROOT / rec["portrait"]).is_file(), "头像文件缺失：%s" % rec["portrait"]
    # 自绘 SVG 只作为加载失败时的兜底，不再是主图
    assert "img.onerror = function ()" in MARKET_JS
    assert "traderIconFallbackSrc(id)" in MARKET_JS
    assert 'var TRADER_ICON_DIR = "assets/icons-traders/"' in MARKET_JS


# ---------------------------------------------------------------- 浮窗：只换红购物车

def _buy_match():
    return {"x": 0, "y": 0, "w": 240, "h": 30, "gw": 1, "gh": 1,
            "price": {"priceSource": "trader", "trader": 12345, "traderId": PRAPOR,
                      "base": 12345, "perSlot": 12345, "noFlea": True,
                      "lastLow": None, "avg24h": None, "avg7d": None}}


def _sell_match():
    return {"x": 0, "y": 0, "w": 240, "h": 30, "gw": 1, "gh": 1,
            "price": {"priceSource": "traderSell", "traderSell": 9999,
                      "traderSellId": PRAPOR, "base": 9999, "perSlot": 9999,
                      "noFlea": True, "lastLow": None, "avg24h": None, "avg7d": None}}


def test_trader_portrait_id_only_for_buy_branch():
    assert scan.trader_portrait_id(_buy_match()) == PRAPOR
    assert scan.trader_portrait_id(_sell_match()) == ""
    assert scan.trader_portrait_id({"price": {"lastLow": 100}}) == ""
    assert scan.trader_portrait_id({}) == ""


def test_real_portrait_file_loads():
    img = scan._trader_portrait(PRAPOR, 24)
    assert img is not None and img.size == (24, 24)
    assert scan._trader_portrait("not-a-trader", 24) is None
    assert scan._trader_portrait("../evil", 24) is None


def test_red_cart_replaced_by_portrait(monkeypatch):
    """buy：画商人头像、不画红购物车；价格文字照常绘制。"""
    calls = {"cart": 0, "portrait": []}

    def fake_cart(*args, **kwargs):
        calls["cart"] += 1

    def fake_portrait(*args):
        calls["portrait"].append(args[-1])
        return True

    monkeypatch.setattr(scan, "_draw_cart", fake_cart)
    monkeypatch.setattr(scan, "_draw_trader_badge", fake_portrait)
    img = scan.render_labels(800, 400, [_buy_match()], "last", TIERS)

    assert calls["cart"] == 0, "红购物车分支不应再调用自绘购物车"
    assert calls["portrait"] == [PRAPOR], "应把最高收购价商人 id 传给头像绘制"
    assert img.getchannel("A").getextrema()[1] > 0, "价格文字仍要画出来"


def test_blue_cart_unchanged(monkeypatch):
    """sell：蓝购物车原样保留，头像逻辑一点不碰。"""
    calls = {"cart": 0, "portrait": []}

    def fake_cart(*args, **kwargs):
        calls["cart"] += 1

    def fake_portrait(*args):
        calls["portrait"].append(args[-1])
        return True

    monkeypatch.setattr(scan, "_draw_cart", fake_cart)
    monkeypatch.setattr(scan, "_draw_trader_badge", fake_portrait)
    scan.render_labels(800, 400, [_sell_match()], "last", TIERS)

    assert calls["cart"] >= 1
    assert calls["portrait"] == []


def test_flea_price_has_no_icon(monkeypatch):
    calls = {"cart": 0, "portrait": 0}
    monkeypatch.setattr(scan, "_draw_cart", lambda *a, **k: calls.__setitem__("cart", calls["cart"] + 1))
    monkeypatch.setattr(scan, "_draw_trader_badge",
                        lambda *a, **k: calls.__setitem__("portrait", calls["portrait"] + 1))
    m = {"x": 0, "y": 0, "w": 240, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 5000, "base": 5000, "perSlot": 5000}}
    scan.render_labels(800, 400, [m], "last", TIERS)
    assert calls == {"cart": 0, "portrait": 0}


def test_portrait_badge_actually_draws_pixels():
    """真实贴一张头像：区域内有非透明像素（不是空占位）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    assert scan._draw_trader_badge(img, dr, 5, 5, 24, PRAPOR) is True
    assert any(img.getpixel((x, y))[3] > 0
               for x in range(0, 40) for y in range(0, 40))


def test_market_tooltip_no_longer_promises_red_cart():
    assert "浮窗显示该商人头像" in MARKET_JS
    assert "浮窗会标蓝购物车" in MARKET_JS
    assert "浮窗会标红购物车" not in MARKET_JS
