# -*- coding: utf-8 -*-
"""R309：同名多 id 时「真实行情」必须优先于「基础价兜底」。

用户实测（文件包）：两个同名 1×2 容器，一个跳蚤有真价（约 118,000，且有历史曲线），
另一个跳蚤不卖、只剩 items.json 的 `p.b` 基础价（167,469，标 traderApprox）。
旧逻辑只比每格价（83,734 > 59,000），基础价盖过真实跳蚤价 → 浮窗数字不对、
详情卡也拿不到历史曲线。现在排序为：全名后缀 > 真实行情 > 每格价。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import serve  # noqa: E402


@pytest.fixture(scope="module")
def catalog():
    return serve._ocr_catalog(ROOT)


def test_base_price_fallback_is_marked_approx():
    rec = {"n": "文件包", "gw": 1, "gh": 2, "p": {"b": 167469},
           "ts": ["container", "noFlea"], "src": ["none"]}
    price = serve._ocr_resolve_price(rec, {}, {}, None)
    assert price["priceSource"] == "trader"
    assert price["trader"] == 167469
    assert price["traderApprox"] is True, "p.b 兜底必须标成估算"


def test_real_trader_offer_is_not_approx():
    rec = {"n": "某物品", "gw": 1, "gh": 1, "p": {"b": 100},
           "ts": ["noFlea"], "src": ["none"],
           "sl": [["traderA", 5000]]}
    price = serve._ocr_resolve_price(rec, {}, {}, None)
    assert price["trader"] == 5000 and not price.get("traderApprox")


def test_variant_rank_prefers_real_market_over_base_price():
    real = {"priceSource": "flea", "lastLow": 118000, "avg24h": 126132, "noFlea": False}
    base = {"priceSource": "trader", "trader": 167469, "base": 167469,
            "noFlea": True, "traderApprox": True}
    assert serve._ocr_variant_rank("文件包", "文件包", real, 59000) > \
        serve._ocr_variant_rank("文件包", "文件包", base, 83734)


def test_folder_picks_flea_variant_with_history(catalog):
    _names, idx, items = catalog
    ids = [i for i in idx.get("文件包") or [] if i in items]
    assert len(set(ids)) == 2, "应有两个同名「文件包」"
    snap = {"590c60fc86f77412b13fddcf": {"l": 118000, "a": 126132}}
    best, best_rank = None, None
    for iid in serve._ocr_prefer_base_variant(ids, items):
        rec = items[iid]
        price = serve._ocr_resolve_price(rec, snap.get(iid) or {}, {}, None)
        rank = serve._ocr_variant_rank(rec.get("n") or iid, "文件包", price,
                                       price.get("perSlot"))
        if best is None or rank > best_rank:
            best, best_rank = iid, rank
    assert best == "590c60fc86f77412b13fddcf", "必须选跳蚤有真价的那个文件包"
    assert serve._ocr_resolve_price(items[best], snap.get(best) or {}, {}, None)["lastLow"] == 118000
