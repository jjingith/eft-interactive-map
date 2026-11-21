# -*- coding: utf-8 -*-
"""R261：散装弹药「数量没识别到」时别把单发价当整堆价。

用户反馈（2026-11-12）：三格 7N40，堆叠 80 / 68 / 80，识别价却是 405 / 27540 / 405。
405 是 7N40 的**单发商人收购价**（sl=405），78 那堆没对上数量 → 按 1 发兜底显示成 405，
很容易被误当成整堆价。

两处修复：
  ① 显示层：数量没识别到时主价标 `₽/发`，明确是单发价；
  ② 关联层：`_ocr_ammo_count` 改为「先比水平对齐 dx、再比纵向 dy」，避免同格附近
     的价格/耐久/邻格数字行被错认或抢走。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402
import serve  # noqa: E402


def _line(text, x, y, w=30, h=22):
    return {"text": text, "score": 0.95,
            "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}


def _name(x=145, y=42, w=30, h=22):
    return {"x": x, "y": y, "w": w, "h": h}


# ---------------------------------------------------------------- ① 显示

def test_price_views_marks_per_round_when_qty_unknown():
    m = {"gw": 1, "gh": 1, "price": {
        "priceSource": "trader", "trader": 405, "unitPrice": 405,
        "qty": 1, "ammoStack": True, "qtyFound": False, "base": 405}}
    for key in scan.MODE_FIELDS:
        assert scan.price_views(m, key)[0] == "405 ₽/发"


def test_price_views_shows_stack_total_when_qty_found():
    m = {"gw": 1, "gh": 1, "price": {
        "priceSource": "trader", "trader": 27540, "unitPrice": 405,
        "qty": 68, "ammoStack": True, "qtyFound": True, "base": 27540}}
    for key in scan.MODE_FIELDS:
        assert scan.price_views(m, key)[0] == "27,540 ₽"


def test_price_views_untouched_for_non_ammo():
    """普通物品（没有 ammoStack 标记）不受 /发 影响。"""
    m = {"gw": 1, "gh": 1, "price": {"priceSource": "trader", "trader": 12345}}
    assert scan.price_views(m, "last")[0] == "12,345 ₽"


# ---------------------------------------------------------------- ② 关联

def test_count_association_prefers_horizontal_alignment_over_closest_dy():
    """同格右沿对齐的数量行，优先于「更近但水平偏很远」的杂数字行。"""
    m = _name(x=145, y=42, w=30, h=22)          # right = 175, h = 22
    own = _line("80", 141, 138, 33, 23)          # right=174, dx=1, dy=96
    stray = _line("3", 200, 82, 24, 23)          # right=224, dx=49, dy=40（更近但偏右）
    counts = serve._ocr_count_lines([own, stray])
    got = serve._ocr_ammo_count(m, counts)
    assert got is not None and got["qty"] == 80, "应按右沿对齐选 80，而不是更近的杂数字"


def test_count_association_rejects_neighbor_cell():
    m = _name(x=145, y=42, w=30, h=22)
    neighbor = _line("80", 267, 138, 33, 23)     # right=300，邻格（dx=125 > 4h）
    counts = serve._ocr_count_lines([neighbor])
    assert serve._ocr_ammo_count(m, counts) is None


def test_count_association_same_cell_still_works():
    m = _name(x=145, y=42, w=30, h=22)
    own = _line("68", 141, 138, 33, 23)
    got = serve._ocr_ammo_count(m, serve._ocr_count_lines([own]))
    assert got and got["qty"] == 68 and got["pack"] is False


# ---------------------------------------------------------------- 契约

def test_contract_display_and_association():
    s = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert 'main = main + "/发"' in s
    v = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert "key = (dx, dy)" in v
