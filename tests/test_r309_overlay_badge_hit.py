# -*- coding: utf-8 -*-
"""R309：浮窗「?」徽章「点了没反应」的两个真实断点。

1. render_labels 按 (x, y) 重排后再枚举，badges_out 记的是**重排后的下标**；
   open_menu 却拿它去原始 matches 取物品——多件装备时点到的是别的物品，
   而那个物品多半没有候选，open_menu 直接 return，表现为「徽章毫无反应」。
2. 撞名但价差小的物品（is_ambig_price=False、仍报价）也会在价格左侧画 ?（soft），
   但命中区只登记了「完全不报价」的 amb 分支，soft 徽章整块鼠标穿透。

这里锁住：徽章下标映射回原始 matches；soft 徽章的命中区同样登记且落在黄色圆上。
"""

from __future__ import annotations

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402

CANDS = [
    {"id": "a", "name": "白卡", "price": 1000},
    {"id": "b", "name": "钥匙卡收纳盒", "price": 2000},
]


def _match(x: int, y: int, soft: bool = False) -> dict:
    price = {"priceSource": "flea", "lastLow": 1000, "candidates": CANDS}
    m = {"x": x, "y": y, "w": 90, "h": 22, "gw": 1, "gh": 1,
         "text": "钥匙卡", "name": "钥匙卡", "price": price}
    if soft:
        # 撞名但价差小：继续报价，只挂 ?（is_ambig_price=False / is_ambig_name=True）
        price.pop("ambiguous", None)
        m["ambiguous"] = True
        m["priceSpread"] = 1.1
    else:
        price["ambiguous"] = True
    return m


def test_badge_index_maps_back_to_original_matches():
    """输入顺序与渲染顺序不同时，badges 下标仍要指向原始 matches。"""
    right = _match(400, 40)     # 原始下标 0，渲染时排第二
    left = _match(60, 40)       # 原始下标 1，渲染时排第一
    matches = [right, left]
    badges: list = []

    scan.render_labels(700, 260, matches, "last", None, badges_out=badges)

    assert len(badges) == 2
    by_x = sorted(badges, key=lambda pair: pair[1][0])
    left_idx, right_idx = by_x[0][0], by_x[1][0]
    assert left_idx == 1 and matches[left_idx] is left
    assert right_idx == 0 and matches[right_idx] is right


def test_soft_ambiguity_badge_has_hit_rect():
    """报价里带 ? 的 soft 分支也要有命中区，且中心是黄色圆。"""
    m = _match(60, 40, soft=True)
    assert scan.is_ambig_price(m) is False
    assert scan.is_ambig_name(m) is True

    badges: list = []
    img = scan.render_labels(700, 260, [m], "last", None, badges_out=badges)

    assert len(badges) == 1 and badges[0][0] == 0
    x0, y0, x1, y1 = badges[0][1]
    assert x1 > x0 and y1 > y0
    r, g, b, a = img.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))
    assert a > 200 and r > 150 and b < 120, \
        "soft 徽章命中区中心应是黄色圆，实际 %s" % ((r, g, b, a),)
