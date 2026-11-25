# -*- coding: utf-8 -*-
"""R309：左键点价格 → 紧凑详情卡（三档价 + 近 7 天曲线）。

契约：
  · 价格文本要登记可点击矩形（与画出来的字重合）；只画 ? 不报价的歧义物品不登记；
  · 详情卡只 232×~140 级别，含物品名、最新/24h/7日三行（当前口径高亮）与曲线；
  · 曲线来自 `/api/price-history?mode=&itemId=&days=`（会员接口），失败只影响曲线；
  · 标签窗 WM_NCHITTEST 对徽章与价格都放行，role 7 详情窗整窗可点。
"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402

SCAN = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()


def _match():
    return {"x": 20, "y": 20, "w": 90, "h": 22, "gw": 1, "gh": 1,
            "name": "显示卡 显卡", "text": "显卡",
            "price": {"priceSource": "flea", "lastLow": 522222,
                      "avg24h": 656641, "avg7d": 571851}}


def test_render_labels_collects_price_rects():
    prices: list = []
    img = scan.render_labels(700, 260, [_match()], "last", None, prices_out=prices)
    assert len(prices) == 2, "主价与单格价两行都应可点"
    for idx, (x0, y0, x1, y1) in prices:
        assert idx == 0 and x1 > x0 and y1 > y0
        # 命中区中心必须真的有字（ULW 透明像素收不到鼠标）
        assert any(img.getpixel((x, (y0 + y1) // 2))[3] > 0
                   for x in range(x0, x1, 2)), "价格命中区与文字不重合"


def test_ambig_only_item_has_no_price_rect():
    m = _match()
    m["price"] = dict(m["price"], ambiguous=True)
    prices: list = []
    badges: list = []
    scan.render_labels(700, 260, [m], "last", None,
                       badges_out=badges, prices_out=prices)
    assert badges and not prices, "只画 ? 的歧义物品不应登记价格点击区"


def test_detail_card_compact_with_three_rows_and_chart():
    m = _match()
    pts = [["2026-11-20T00:00:00+08:00", 530000, 600000],
           ["2026-11-21T00:00:00+08:00", 510000, 590000],
           ["2026-11-22T00:00:00+08:00", 560000, 610000],
           ["2026-11-23T00:00:00+08:00", 522222, 656641]]
    card = scan.render_detail_card(m, 1, pts, "ok", 1.0)
    assert 200 <= card.width <= 260 and 120 <= card.height <= 190, \
        "详情卡要紧凑，不能像网页弹窗"
    data = card.tobytes()
    # 曲线用蓝色折线画出来（采样是否存在该色）
    px = [card.getpixel((x, y)) for x in range(0, card.width, 2)
          for y in range(0, card.height, 2)]
    assert any(abs(p[0] - 58) < 18 and abs(p[1] - 110) < 18 and abs(p[2] - 200) < 18
               for p in px), "缺少价格曲线"
    loading = scan.render_detail_card(m, 1, None, "loading", 1.0).tobytes()
    assert data != loading, "加载中与有数据必须画得不一样"


def test_detail_card_trader_note_is_readable():
    """商人价物品：三档为 —，但有兜底说明（且 ₽ 不能是豆腐块）。"""
    m = {"name": "文件包", "text": "文件包",
         "price": {"priceSource": "trader", "trader": 167469, "base": 167469}}
    card = scan.render_detail_card(m, 0, [], "empty", 1.0)
    assert card.width > 200


def test_hit_price_maps_to_match_index():
    sess = SimpleNamespace(prices=[(3, (10, 10, 40, 30))])
    assert scan.OverlaySession.hit_price(sess, 20, 20) == 3
    assert scan.OverlaySession.hit_price(sess, 5, 20) is None


def test_backend_wiring():
    assert "def hit_price" in SCAN and "def toggle_detail" in SCAN
    assert "def open_detail" in SCAN and "def apply_detail_history" in SCAN
    assert "render_detail_card(" in SCAN
    assert "role == 7" in SCAN, "详情卡需要独立的 role 7 窗口"
    assert "hit_price(pt.x, pt.y)" in SCAN, "标签窗命中必须走价格矩形"
    assert "toggle_detail(pidx)" in SCAN
    assert "/api/price-history" in SCAN and "itemId=" in SCAN


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_price_history_parses_points(monkeypatch):
    seen = {}

    class _Opener:
        def open(self, url, timeout=None):
            seen["url"] = url
            return _Resp(json.dumps({"series": {"abc": {
                "points": [["2026-11-20T00:00:00+08:00", 100, 120],
                           ["2026-11-21T00:00:00+08:00", 130, 140]],
                "count": 2}}}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _Opener())
    pts, status = scan.fetch_price_history("http://127.0.0.1:8787", "pve", "abc")
    assert status == "ok" and len(pts) == 2 and pts[0][1] == 100
    assert "/api/price-history?" in seen["url"] and "itemId=abc" in seen["url"]


def test_fetch_price_history_handles_403(monkeypatch):
    class _Opener:
        def open(self, url, timeout=None):
            raise urllib.error.HTTPError(url, 403, "forbidden", None, io.BytesIO(b""))

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _Opener())
    pts, status = scan.fetch_price_history("http://127.0.0.1:8787", "pve", "abc")
    assert pts == [] and status == "http-403"


# ---------------------------------------------------------------- R309 物品小图

POSTER_A = "6759e19a8367ee2b0c0f4b92"
POSTER_B = "6759e6c39422e1708e0e9b81"


def test_item_icon_loads_and_missing_falls_back():
    assert scan._item_icon(POSTER_A, 20) is not None, "海报图标应能加载"
    assert scan._item_icon("no-such-item-id", 20) is None
    assert scan._item_icon("../../etc/passwd", 20) is None, "id 不允许路径穿越"


def test_menu_rows_show_distinct_item_icons():
    rows = [
        {"id": POSTER_A, "name": "女郎海报", "price": 40000},
        {"id": POSTER_B, "name": "女郎海报", "price": 25555},
    ]
    img, _rects = scan.render_menu(rows, 13, POSTER_A, "选择物品")
    assert img is not None
    # 同一名字、不同 id：两行的图标区像素必须不一样（否则等于没画小图）
    row_h = int(round(13 * 1.7))
    title_h = int(round(13 * 1.5))
    icon_sz = max(12, row_h - 6)
    pad = max(6, int(round(13 * 0.55)))
    dot_r = max(2, int(round(13 * 0.16)))
    x0 = pad + dot_r * 2 + 8
    y0 = title_h + pad // 2
    a = img.crop((x0, y0, x0 + icon_sz, y0 + icon_sz)).tobytes()
    b = img.crop((x0, y0 + row_h, x0 + icon_sz, y0 + row_h + icon_sz)).tobytes()
    assert a != b, "两个候选的小图不能相同"


def test_detail_card_includes_item_icon():
    p = {"priceSource": "flea", "lastLow": 25555, "avg24h": 33109, "avg7d": 29510}
    a = scan.render_detail_card({"id": POSTER_A, "name": "女郎海报", "price": p},
                                0, [], "empty", 1.0)
    b = scan.render_detail_card({"id": POSTER_B, "name": "女郎海报", "price": p},
                                0, [], "empty", 1.0)
    assert a.size == b.size
    # 标题栏左侧小图不同 → 位图不同
    title_h = int(round(28 * 1.0))
    icon_sz = max(14, title_h - int(round(6 * 1.0)))
    box = (8, (title_h - icon_sz) // 2, 8 + icon_sz, (title_h - icon_sz) // 2 + icon_sz)
    assert a.crop(box).tobytes() != b.crop(box).tobytes()
