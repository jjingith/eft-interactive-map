# -*- coding: utf-8 -*-
"""R309：浮窗选单选中候选后，价格仍跟随「最新 / 24小时 / 7日」口径。

用户实测：在识别价格的浮窗里点「?」选了「注射器收纳盒」后，再切价格口径，
价格不再变化（一直 275,000）。根因：旧 `pick_candidate` 把候选的单个数字写进
`price.manual`，`price_base` 永远优先返回 manual，切口径自然不动。

新行为：
  · 用候选的完整 `detail` 价格对象替换 `price`，记录 `pickedId`（正常报价、徽章保留）；
  · 候选清单保留，可再次点开改选；
  · 散装弹用 `unit × qty` 恢复「整堆价」；
  · 只有老后端缺 `detail` 时才退回固定 `manual`。
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402


def _sess(m: dict) -> SimpleNamespace:
    return SimpleNamespace(matches=[m], menu_for=0, menu_pinned=True,
                           close_menu=lambda: None, _redraw=lambda: None)


def _detail(last, a24, w7, slots=2):
    return {"lastLow": last, "avg24h": a24, "avg7d": w7,
            "base": last, "perSlot": last / slots, "priceSource": "flea",
            "noFlea": False}


def test_pick_candidate_keeps_mode_switchable():
    selected = _detail(275000, 270402, 260000)
    old = _detail(35555, 42267, 35679)
    old.update({
        "ambiguous": True,
        "candidates": [
            {"id": "one", "name": "一次性注射器", "price": 35555, "detail": _detail(35555, 42267, 35679, 1),
             "gw": 1, "gh": 1, "weight": 0.1},
            {"id": "case", "name": "注射器收纳盒", "price": 275000, "detail": selected,
             "gw": 1, "gh": 2, "weight": 0.5},
        ],
    })
    m = {"x": 0, "y": 0, "w": 20, "h": 20, "gw": 1, "gh": 1,
         "id": "one", "name": "注射器", "ambiguous": True, "price": old}

    scan.OverlaySession.pick_candidate(_sess(m), 0, 1)

    p = m["price"]
    assert p is not old
    assert "manual" not in p, "不能再冻结成 manual，否则切口径不会变"
    assert p["pickedId"] == "case"
    assert m["id"] == "case" and m["name"] == "注射器收纳盒"
    assert m["gh"] == 2 and m["weight"] == 0.5
    assert scan.is_ambig_price(m) is False, "已选定：正常显示价格"
    assert scan.is_ambig_name(m) is True, "徽章保留，可再点开改选"
    assert scan.ambig_candidates(m), "候选清单必须保留"
    assert scan.price_views(m, "last")[0] == "275,000 ₽"
    assert scan.price_views(m, "a24")[0] == "270,402 ₽"
    assert scan.price_views(m, "w7")[0] == "260,000 ₽"


def test_pick_loose_ammo_restores_stack_total():
    detail = {"lastLow": None, "avg24h": None, "avg7d": None, "base": 238,
              "perSlot": 238, "priceSource": "trader", "trader": 238,
              "traderId": "t", "noFlea": True}
    old = {"lastLow": None, "base": 238 * 80, "perSlot": 238 * 80,
           "priceSource": "trader", "trader": 238 * 80, "noFlea": True,
           "ammoStack": True, "qty": 80, "unitPrice": 238, "qtyFound": True,
           "ambiguous": True,
           "candidates": [{"id": "a", "name": "6.8x51毫米 SIG FMJ", "price": 238,
                           "kind": "loose", "unit": 238, "detail": detail,
                           "gw": 1, "gh": 1}]}
    m = {"x": 0, "y": 0, "w": 20, "h": 20, "gw": 1, "gh": 1,
         "id": "x", "name": "5.45x39毫米 FMJ", "ammoKind": "loose", "qty": 80,
         "price": old}

    scan.OverlaySession.pick_candidate(_sess(m), 0, 0)

    p = m["price"]
    assert p["ammoStack"] is True and "manual" not in p
    assert p["base"] == 238 * 80 and p["trader"] == 238 * 80
    assert p["unitPrice"] == 238 and p["qty"] == 80
    assert scan.price_views(m, "last")[0] == "19,040 ₽"
    assert m["id"] == "a" and m["name"] == "6.8x51毫米 SIG FMJ"
    assert scan.is_ambig_price(m) is False and scan.is_ambig_name(m) is True
    assert scan.ambig_candidates(m)


def test_pick_without_detail_falls_back_to_manual():
    """老后端候选没有 detail：保留旧的固定单价行为（只影响这类旧数据）。"""
    old = {"lastLow": 1000, "base": 1000, "perSlot": 1000, "priceSource": "flea",
           "candidates": [{"id": "a", "name": "A", "price": 900}]}
    m = {"x": 0, "y": 0, "w": 20, "h": 20, "gw": 1, "gh": 1, "name": "A", "price": old}

    scan.OverlaySession.pick_candidate(_sess(m), 0, 0)

    assert m["price"]["manual"] == 900
    assert "pickedId" not in m["price"]
    assert scan.is_ambig_price(m) is False
