#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R-fix · 显示名撞名（同名不同物）的「?」徽记契约。

用户实测：实验室白卡（TerraGroup实验室访问钥匙卡）、蓝色记号钥匙卡、钥匙卡收纳盒
在游戏里显示的名字都是「钥匙卡」，OCR 只看得到这三个字。旧逻辑按「每格价最高」直接
挑一个 → 白卡被显示成收纳盒的价（用户原话「显示的是 811111 明显不够」）。

契约：
  1. `serve._ocr_name_collision` 把候选**按全名折叠**后返回；长度 ≥2 = 真歧义；
  2. 装配处把歧义写成 match 级 `ambiguous` + `candidates`（不污染 price.ambiguous，
     那是弹药口径歧义的专用通道）；
  3. `scan.is_ambig_price` 认 match 级歧义 → 浮窗只画 ? 徽章、不画价格；
  4. `scan.ambig_candidates` 两种来源都能读到候选表；
  5. 市场页表格给 match 级歧义画同款「?」徽章。
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan      # noqa: E402
import serve     # noqa: E402


# 三个 id 是真实数据里短名都叫「钥匙卡」的三件**不同**物品
KEY_A = "5c94bbff86f7747ee735c08f"   # TerraGroup实验室访问钥匙卡
KEY_B = "5efde6b4f5448336730dbd61"   # 蓝色记号钥匙卡
KEY_C = "619cbf9e0a7c3a1a2731940a"   # 钥匙卡收纳盒


def _catalog():
    return {
        KEY_A: {"n": "TerraGroup实验室访问钥匙卡", "gw": 1, "gh": 1, "w": 0.01,
                "p": {"b": 100000}, "src": ["flea"], "trade": [{"k": "flea"}]},
        KEY_B: {"n": "蓝色记号钥匙卡", "gw": 1, "gh": 1, "w": 0.01,
                "p": {"b": 50000}, "src": ["flea"], "trade": [{"k": "flea"}]},
        KEY_C: {"n": "钥匙卡收纳盒", "gw": 1, "gh": 1, "w": 0.095,
                "p": {"b": 458453}, "src": ["flea"], "trade": [{"k": "flea"}]},
    }


def test_collision_lists_every_distinct_item():
    """同一显示名 → 三件不同物品，全部进候选（不能只留一个）。"""
    cat = _catalog()
    snap = {"avg7d": {"values": {}}}
    rows = serve._ocr_name_collision([KEY_A, KEY_B, KEY_C], cat, {}, {}, snap)
    names = sorted(r["name"] for r in rows)
    assert names == ["TerraGroup实验室访问钥匙卡", "蓝色记号钥匙卡", "钥匙卡收纳盒"]
    assert all(r["id"] for r in rows)


def test_same_item_duplicated_by_two_ids_is_not_a_collision():
    """同一件物品重复录入（全名完全相同）不能算歧义——否则满屏都是「?」。"""
    cat = _catalog()
    cat["dup_of_a"] = dict(cat[KEY_A])          # 同名的第二条 id
    snap = {"avg7d": {"values": {}}}
    rows = serve._ocr_name_collision([KEY_A, "dup_of_a"], cat, {}, {}, snap)
    assert len(rows) == 1, "同名多 id 应折叠成一条"


def test_single_candidate_is_not_ambiguous():
    cat = _catalog()
    rows = serve._ocr_name_collision([KEY_B], cat, {}, {}, {"avg7d": {"values": {}}})
    assert len(rows) == 1


def test_overlay_treats_match_level_ambiguity_as_ambiguous():
    """浮窗：match 级 ambiguous 也要只画徽章、不画价格。"""
    m = {"name": "钥匙卡", "gw": 1, "gh": 1, "ambiguous": True,
         "candidates": [{"name": "蓝色记号钥匙卡", "price": 298989},
                        {"name": "钥匙卡收纳盒", "price": 458453}],
         "price": {"lastLow": 458453}}
    assert scan.is_ambig_price(m) is True
    assert len(scan.ambig_candidates(m)) == 2


def test_manual_pick_clears_ambiguity_for_display():
    """玩家在 ? 菜单里选定某件后，按所选价正常显示（不再只剩一个问号）。"""
    m = {"name": "钥匙卡", "ambiguous": True,
         "candidates": [{"name": "蓝色记号钥匙卡", "price": 298989}],
         "price": {"lastLow": 458453, "manual": 298989}}
    assert scan.is_ambig_price(m) is False


def test_small_price_spread_keeps_price_but_keeps_badge():
    """候选价差很小的同名组（同款不同色）不该被剥掉价格——只挂徽章。"""
    m = {"name": "GEN M3", "ambiguous": True, "priceSpread": 1.05,
         "candidates": [{"name": "a", "price": 100}, {"name": "b", "price": 105}],
         "price": {"lastLow": 100}}
    assert scan.is_ambig_name(m) is True
    assert scan.is_ambig_price(m) is False, "价差 1.05× 仍应正常报价"


def test_large_price_spread_suppresses_price():
    m = {"name": "钥匙卡", "ambiguous": True, "priceSpread": 4.2,
         "candidates": [{"name": "a", "price": 100}, {"name": "b", "price": 420}],
         "price": {"lastLow": 420}}
    assert scan.is_ambig_price(m) is True


def test_missing_spread_falls_back_to_suppressing():
    """拿不到价差时保守处理：宁可不报价，也不报一个可能错 3 个数量级的数。"""
    m = {"name": "地图", "ambiguous": True, "price": {"lastLow": 1}}
    assert scan.is_ambig_price(m) is True


def test_ammo_ambiguity_still_wins_via_price_channel():
    """弹药口径歧义走 price.ambiguous，不能被 match 级通道挤掉。"""
    m = {"name": "AP", "price": {"ambiguous": True, "candidates": [{"name": "x", "price": 1}]}}
    assert scan.is_ambig_price(m) is True
    assert scan.ambig_candidates(m) == [{"name": "x", "price": 1}]


def test_market_page_renders_badge_for_match_level_ambiguity():
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    assert "m.ambiguous" in js, "市场页必须处理 match 级歧义"
    assert "mk-ocr-ambig" in js, "复用弹药同款 ? 徽章"
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()
    assert ".mk-ocr-ambig" in css and ".mk-ocr-price-ambig" in css


def test_scan_render_labels_accepts_match_level_ambiguity():
    """端到端：带 match 级歧义的 match 画出来的墨量应少于正常价（只画徽章）。"""
    base = {"x": 0, "y": 0, "w": 200, "h": 30, "gw": 1, "gh": 1,
            "price": {"lastLow": 458453}}
    normal = dict(base)
    amb = dict(base, name="钥匙卡", ambiguous=True,
               candidates=[{"name": "蓝色记号钥匙卡", "price": 298989}])
    tiers = [{"max": None, "color": "#f2f2ee", "font": "msyh", "sizeScale": 1.0}]
    img_n = scan.render_labels(900, 400, [normal], "last", tiers)
    img_a = scan.render_labels(900, 400, [amb], "last", tiers, badges_out=[])
    ink = lambda im: sum(1 for p in im.getdata() if p[3] > 0)
    assert ink(img_a) < ink(img_n)
