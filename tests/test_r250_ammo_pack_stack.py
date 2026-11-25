# -*- coding: utf-8 -*-
"""R250：弹药名按「数量行有没有斜杠」区分弹药包 / 散装堆叠。

用户反馈（2026-11-12）：
  「这些子弹实际上游戏里是不能上架跳蚤的，能上架的是弹药包；弹药包有
    25/25 30/30 120/120 这类显示子弹数的，不是弹药包而是散装弹药的，
    下面只会显示不带 / 的堆叠数量。加一个判断：如果是识别到属于弹药类的名字，
    再看下面有没有 xx/xx —— 有就显示弹药包的价格，没有就显示单发弹药的商人
    收购价格乘下面显示的弹药堆叠数量。」

4K 真实截图实测几何：名字印在格子右上角（y=42）、数量印在同一格右下角
（y=138，右沿对齐，dy≈96px ≈ 0.76 格），格子宽 126px / 行框高 22px。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pytest  # noqa: E402

import config  # noqa: E402
import scan  # noqa: E402
import serve  # noqa: E402


def _line(text, x, y, w=30, h=22):
    """构造 OCR 原始行（points 四点，右下角 right = x+w）。"""
    return {"text": text, "score": 0.95,
            "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}


def _name_box(x=145, y=42, w=30, h=22):
    return {"x": x, "y": y, "w": w, "h": h}


@pytest.fixture(scope="module")
def catalog3():
    return serve._ocr_catalog(ROOT)


def _ids_for(short, catalog3):
    _names, idx, _items = catalog3
    return idx.get(short, [])


# ---------------------------------------------------------------- 形态分类

def test_ammo_kind_uses_ts(catalog3):
    _names, _idx, items = catalog3
    kinds = {v["n"]: serve._ocr_ammo_kind(v) for v in items.values()
             if any(t in (v.get("ts") or []) for t in ("ammo", "ammoBox"))}
    assert kinds["5.45x39毫米 BS"] == "loose"
    assert kinds["5.45x39mm BS弹药包（30发装）"] == "pack"
    # 少数弹药包 ts 同时含 ammo + ammoBox，必须先判 ammoBox
    assert kinds["5.45x39mm BP弹药包（120发装）"] == "pack"
    assert serve._ocr_ammo_kind({"ts": ["gun"]}) is None


def test_count_lines_recognize_pack_and_stack_but_not_noise():
    counts = serve._ocr_count_lines([
        _line("30/30", 100, 138), _line("120/120", 100, 138),
        _line("80", 100, 138), _line("8O", 100, 138),
        _line("33.2/58", 100, 138),     # 护甲耐久
        _line("BS", 100, 42),           # 物品名
        _line("子弹/弹匣/狗牌/钱", 100, 42),
        _line("100/100", 100, 138),
        _line("1,000", 100, 138),       # 价格标签 → 归一后 1000 > 999 丢弃
    ])
    pack = [c for c in counts if c["pack"]]
    stack = [c for c in counts if not c["pack"]]
    assert {c["qty"] for c in pack} == {30, 120, 100}
    assert 80 in {c["qty"] for c in stack}
    assert all(c["qty"] <= 999 for c in counts)
    assert len(counts) == 5, "耐久 / 物品名 / 栏位标题 / 价格标签不能当数量：%s" % counts


def test_count_association_uses_same_cell_right_edge():
    """数量行必须与名字右沿对齐、且在名字下方一个格子内。"""
    m = _name_box(x=145, y=42, w=30, h=22)      # right = 175
    own = _line("80", 141, 138, 33, 23)          # right = 174, dy = 96
    neighbor = _line("80", 267, 138, 33, 23)     # 邻格 right = 300
    above = _line("80", 141, -30, 33, 23)        # 上一行
    far = _line("80", 141, 400, 33, 23)          # 隔了两行
    counts = serve._ocr_count_lines([own, neighbor, above, far])
    got = serve._ocr_ammo_count(m, counts)
    assert got and got["qty"] == 80 and got["pack"] is False


# ---------------------------------------------------------------- 决策

def test_decision_loose_uses_plain_stack_count(catalog3):
    _names, _idx, items = catalog3
    ids = _ids_for("BS", catalog3)
    lines = [_line("BS", 145, 42), _line("80", 141, 138, 33, 23)]
    kind, qty, narrowed, found, _ambig = serve._ocr_ammo_decision(
        _name_box(), lines, ids, items)
    assert (kind, qty, found) == ("loose", 80, True)
    assert [items[i]["n"] for i in narrowed] == ["5.45x39毫米 BS"]


def test_decision_pack_uses_slash_count_and_matches_pack_size(catalog3):
    _names, _idx, items = catalog3
    ids = _ids_for("BS", catalog3)
    lines = [_line("BS", 145, 42), _line("30/30", 90, 138, 85, 23)]
    kind, qty, narrowed, found, _ambig = serve._ocr_ammo_decision(
        _name_box(), lines, ids, items)
    assert (kind, qty, found) == ("pack", 30, True)
    assert narrowed and all(serve._ocr_pack_size(items[i]["n"]) == 30 for i in narrowed)
    assert all(serve._ocr_ammo_kind(items[i]) == "pack" for i in narrowed)


def test_decision_pack_120_prefers_120_pack(catalog3):
    _names, _idx, items = catalog3
    ids = _ids_for("BS", catalog3)
    lines = [_line("BS", 145, 42), _line("120/120", 70, 138, 105, 23)]
    kind, qty, narrowed, _found, _ambig = serve._ocr_ammo_decision(
        _name_box(), lines, ids, items)
    assert kind == "pack" and qty == 120
    assert narrowed and all(serve._ocr_pack_size(items[i]["n"]) == 120 for i in narrowed)


def test_decision_non_ammo_is_untouched(catalog3):
    _names, _idx, items = catalog3
    ids = [i for i, v in items.items() if "ammo" not in (v.get("ts") or [])
           and "ammoBox" not in (v.get("ts") or [])][:3]
    kind, qty, narrowed, found, _ambig = serve._ocr_ammo_decision(
        _name_box(), [_line("30/30", 90, 138, 85)], ids, items)
    assert (kind, qty, narrowed, found, _ambig) == (None, 0, [], False, False)


def test_decision_no_count_line_falls_back_to_single_bullet(catalog3):
    """数量行没识别到 → 散装按 1 发保守计价，并标 qtyFound=False。"""
    _names, _idx, items = catalog3
    kind, qty, narrowed, found, _ambig = serve._ocr_ammo_decision(
        _name_box(), [_line("BS", 145, 42)], _ids_for("BS", catalog3), items)
    assert kind == "loose" and qty == 1 and found is False
    assert narrowed


def test_loose_decision_keeps_every_caliber(catalog3):
    """R309：散装 BP 的 5.45x39 / 7.62x39 / 9x39 全部保留，不再按包的口径分布猜。"""
    _names, _idx, items = catalog3
    ids = _ids_for("BP", catalog3)
    loose = [i for i in ids if serve._ocr_ammo_kind(items[i]) == "loose"]
    packs = [i for i in ids if serve._ocr_ammo_kind(items[i]) == "pack"]
    assert len(loose) == 3
    kind, _qty, picked, _found, ambig = serve._ocr_ammo_decision(
        _name_box(), [_line("BP", 145, 42), _line("80", 141, 138, 33)], loose + packs, items)
    assert kind == "loose"
    assert picked == loose
    assert ambig is True


# ---------------------------------------------------------------- 计价

def test_apply_ammo_stack_price_is_unit_times_qty(catalog3):
    _names, _idx, items = catalog3
    iid = _ids_for("BS", catalog3)[0]
    cand = {"id": iid, "price": {"lastLow": 999999, "avg24h": 999999,
                                 "w72": 1, "w30d": 1, "base": 999999}}
    assert serve._ocr_apply_ammo_stack(cand, items, 80, True) is True
    p = cand["price"]
    assert p["unitPrice"] == 351 and p["qty"] == 80
    assert p["trader"] == 351 * 80 and p["base"] == 351 * 80
    assert p["perSlot"] == 351 * 80
    assert p["priceSource"] == "trader" and p["ammoStack"] is True
    assert p["qtyFound"] is True and p["noFlea"] is True
    assert p["lastLow"] is None and p["w72"] is None and p["w30d"] is None
    assert cand["ammoKind"] == "loose" and cand["qty"] == 80


def test_scan_price_views_shows_stack_total_in_every_mode():
    """浮窗四种口径都显示整堆商人价（商人只有一口价）。"""
    m = {"gw": 1, "gh": 1, "price": {"priceSource": "trader", "trader": 28080,
                                     "unitPrice": 351, "qty": 80,
                                     "ammoStack": True, "base": 28080}}
    for key in scan.MODE_FIELDS:
        main, slot, _kg = scan.price_views(m, key)
        assert main == "28,080 ₽" and slot == "28,080 ₽"
    assert scan.is_trader_price(m)       # 红购物车照常显示


# ---------------------------------------------------------------- 契约

def test_contract_wires_decision_into_recognize_and_overlay_whitelist():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert "_ocr_ammo_decision(" in src and "_ocr_apply_ammo_stack(" in src
    assert "_ocr_count_lines(" in src and "_AMMO_PACK_RE" in src
    assert '"ammoKind", "qty", "price"' in src, "交接白名单要放行弹药标记"
    body = src[src.index("def _handle_ocr_recognize"):]
    assert "ammo_kind, ammo_qty, ammo_ids, ammo_found, ammo_ambig" in body
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    assert "m.ammoKind" in js and "散弹×" in js
