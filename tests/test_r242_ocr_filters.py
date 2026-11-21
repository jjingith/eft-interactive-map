# -*- coding: utf-8 -*-
"""R242：识别净化——栏位标题黑名单 / 臂带狗牌物品排除 / 同位置去重 / 「单格」文案。

用户反馈（2026-11-11 20:40）：
  「识别到除了装备以外的字 比如装备栏位上方的字『耳机』『头部装备』这种，
    还有臂带和狗牌 也不要识别」「格又是什么 是单格」

小喵没有这些问题的原因：它只扫鼠标光标周围一小块（CursorCenteredRegion），
栏位标题根本进不了画面；我们扫整个框选区 → 必须整词拦截 + 物品排除 + 同位去重。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import ocr  # noqa: E402
import serve  # noqa: E402


# ---------------------------------------------------------------- 栏位标题黑名单

def test_section_headers_blocked_in_matcher():
    """栏位标题整行（含去空格形态）在任何匹配层之前拦截。"""
    names = ["VKBO军用背包", "木质装备箱", "GSSh-6 耳机"]
    m = ocr.ItemMatcher(names)
    for header in ("耳机", "头部装备", "面部装备", "眼部装备", "背包",
                   "身体护甲", "战术胸挂", "口袋", "特殊装备", "刀鞘",
                   "耳 机", "背 包"):
        key, path = m.resolve_key(header)
        assert key is None, "栏位标题被误配：%s → %s" % (header, path)
    # 含标题词的真物品全名不受影响
    key, path = m.resolve_key("VKBO军用背包")
    assert key is not None and path == "精确"
    key, path = m.resolve_key("GSSh-6 耳机")
    assert key is not None


def test_section_headers_fuzzy_layer_blocked():
    """token 层也要拦（标题碎片不参与模糊，防止 '战术胸挂' 一半擦线配上别物）。"""
    assert "耳机" in ocr.SECTION_HEADERS and "头部装备" in ocr.SECTION_HEADERS
    assert "背包" in ocr.SECTION_HEADERS and "战术胸挂" in ocr.SECTION_HEADERS


# ---------------------------------------------------------------- 物品排除（臂带/狗牌）

def test_item_name_excluded():
    assert ocr.item_name_excluded("臂带（白）")
    assert ocr.item_name_excluded("ALGY 臂章")
    assert ocr.item_name_excluded("狗牌包")
    assert ocr.item_name_excluded("Bronze 狗牌容器")
    assert ocr.item_name_excluded("T H.I.E.F. Dogtag")
    assert not ocr.item_name_excluded("VKBO军用背包")
    assert not ocr.item_name_excluded("")
    assert not ocr.item_name_excluded(None)


# ---------------------------------------------------------------- 同位置去重

def _m(text, x, y, h=20, score=0.9, tier="精确", name=None, mid="id1"):
    return {"text": text, "x": x, "y": y, "w": 100, "h": h,
            "ocrScore": score, "tier": tier, "id": mid, "name": name or text}


def test_dedup_same_id_nearby_fragments():
    """『肾上』+『腺素』（同 id、中心距 ~43px）→ 只留一个。"""
    a = _m("肾上", 2837, 924, score=0.8)
    b = _m("腺素", 2880, 923, score=0.85, mid="id1")
    out = serve.dedup_ocr_matches([a, b])
    assert len(out) == 1 and out[0]["ocrScore"] == 0.85


def test_dedup_same_position_tier_priority():
    """EXFIL（精确 0.98）与 EXPIE（整串模糊 0.67）同位置 → 留精确。"""
    good = _m("EXFIL", 618, 310, score=0.98, tier="精确", name="EXFIL 盔罩", mid="good")
    bad = _m("EXPIE", 618, 320, score=0.67, tier="整串模糊(0.67)", name="鹿弹", mid="bad")
    out = serve.dedup_ocr_matches([bad, good])
    assert len(out) == 1 and out[0]["text"] == "EXFIL"


def test_dedup_far_same_id_both_kept():
    """两块夹板（同 id、相距 >300px）各自保留。"""
    a = _m("夹板", 2491, 925, mid="splint")
    b = _m("夹板", 1657, 1000, mid="splint")
    out = serve.dedup_ocr_matches([a, b])
    assert len(out) == 2


def test_dedup_keeps_higher_score_for_same_id_close():
    """同 id 近距：分数低者被替换。"""
    lo = _m("肾上", 2837, 924, score=0.6)
    hi = _m("肾上", 2838, 925, score=0.9)
    out = serve.dedup_ocr_matches([lo, hi])
    assert len(out) == 1 and out[0]["ocrScore"] == 0.9


# ---------------------------------------------------------------- 契约

def test_serve_filters_contract():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert "ocr.item_name_excluded(best[\"name\"])" in src
    assert "out_matches = dedup_ocr_matches(out_matches)" in src
    assert "_ocr_close" in src and "_OCR_TIER_RANK" in src


def test_label_line2_is_dange():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert 'line2 = "单格 " + slot_txt' in src
    assert '"格 " + slot_txt' not in src
