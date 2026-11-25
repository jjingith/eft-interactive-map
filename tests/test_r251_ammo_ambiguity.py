# -*- coding: utf-8 -*-
"""R251：同短名不同口径（.338 AP vs .300 AP、FMJ 11 个口径…）的区分与歧义标注。

用户反馈（2026-11-12）：
  「有些子弹口径不一样但是显示的缩写名称是一样的，如 .338 .300 就都有
    AP 还有 fmj 之类的，这该怎么区别」

事实约束：游戏内物品名印的就是短名（AP / FMJ / BP …），口径完全不可见；
OCR 能拿到的只有「短名文本 + 右下角数量」。可用的确定性证据：
  ① 弹药包：xx/xx 的容量数 ↔ 名字里的「N发装」（20/20 → .338 AP 包唯一）；
  ② 散装：口径无法从截图上区分 → **全部口径列进候选选单**，让玩家自己选
     （R309 用户口径：不再按同短名弹药包的口径分布去猜，宁可全列出来）。
无法唯一确定（.338/.300/.45 包都是 50 发装；散装 AP 包口径 1:1:1）就如实
标 ambiguous=True + candidates 价目表，前端画黄色「?」徽章让玩家核对。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pytest  # noqa: E402

import serve  # noqa: E402


def _line(text, x, y, w=30, h=22):
    return {"text": text, "score": 0.95,
            "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}


def _name_box(x=145, y=42, w=30, h=22):
    return {"x": x, "y": y, "w": w, "h": h}


@pytest.fixture(scope="module")
def catalog3():
    return serve._ocr_catalog(ROOT)


def _split(catalog3, short):
    _names, idx, items = catalog3
    ids = idx.get(short, [])
    loose = [i for i in ids if serve._ocr_ammo_kind(items[i]) == "loose"]
    packs = [i for i in ids if serve._ocr_ammo_kind(items[i]) == "pack"]
    return items, loose, packs


# ---------------------------------------------------------------- 口径识别

def test_caliber_matches_metric_and_imperial():
    """口径正则：公制 5.45x39（不吃 mm）、英制 .338/.300/.45、霰弹 12/70 取不到。"""
    f = serve._ocr_caliber
    assert f("5.45x39mm BS弹药包（30发装）") == "5.45x39"
    assert f(".338 Lapua Magnum AP") == ".338"
    assert f(".300 Blackout AP") == ".300"
    assert f(".45 ACP AP弹药包（50发装）") == ".45"
    assert f("7.62x54R FMJ") == "7.62x54"
    assert f(".50 AE FMJ") == ".50"
    assert f("6.8x51mm SIG FMJ") == "6.8x51"
    assert f("12/70 Poleva-3 独头弹") == ""   # 霰弹口径 → 走歧义路径
    assert f("") == "" and f(None) == ""


def test_ambiguous_requires_two_calibers(catalog3):
    _names, _idx, items = catalog3
    bs_pack = [i for i, v in items.items()
               if v["n"].startswith("5.45x39mm BS弹药包")]
    assert serve._ocr_ambiguous(bs_pack, items) is False, \
        "同口径的重复包装（BS 120 发装两条）不算歧义"


# ------------------------------------------------------- 能确定的场景

def test_ap_pack_20_is_unique(catalog3):
    """20/20 → .338 AP 弹药包（20发装）唯一，无歧义。"""
    items, _loose, packs = _split(catalog3, "AP")
    narrowed = serve._ocr_prefer_pack(packs, items, 20)
    assert [items[i]["n"] for i in narrowed] == ["​.338 Lapua Magnum AP弹药包（20发装）".replace("​", "")]
    assert serve._ocr_ambiguous(narrowed, items) is False


def test_ap_pack_50_collides_and_is_flagged(catalog3):
    """50/50 → .300 与 .45 ACP 两个 50 发装包，容量匹配无法区分 → 歧义。"""
    items, _loose, packs = _split(catalog3, "AP")
    lines = [_line("AP", 145, 42), _line("50/50", 100, 138, 60, 23)]
    kind, qty, narrowed, found, ambig = serve._ocr_ammo_decision(
        _name_box(), lines, list(_split(catalog3, "AP")[1]) + packs, items)
    assert kind == "pack" and qty == 50 and found is True
    assert ambig is True
    assert len(narrowed) == 2
    assert {serve._ocr_caliber(items[i]["n"]) for i in narrowed} == {".300", ".45"}


def test_ap_loose_is_inherently_ambiguous(catalog3):
    """.338 AP 与 .300 Blackout AP 散装：口径无法区分 → 两个都进候选、标歧义。"""
    items, loose, packs = _split(catalog3, "AP")
    lines = [_line("AP", 145, 42), _line("80", 141, 138, 33, 23)]
    kind, qty, narrowed, _found, ambig = serve._ocr_ammo_decision(
        _name_box(), lines, loose + packs, items)
    assert kind == "loose" and qty == 80 and ambig is True
    assert {serve._ocr_caliber(items[i]["n"]) for i in narrowed} == {".338", ".300"}


def test_fmj_loose_11_calibers_stays_ambiguous(catalog3):
    """FMJ 散装 11 个口径全部保留：不猜口径，交给选单。"""
    items, loose, packs = _split(catalog3, "FMJ")
    assert len(loose) == 11
    lines = [_line("FMJ", 145, 42), _line("80", 141, 138, 33, 23)]
    kind, qty, narrowed, _found, ambig = serve._ocr_ammo_decision(
        _name_box(), lines, loose + packs, items)
    assert kind == "loose" and qty == 80
    assert narrowed == loose and ambig is True


# ------------------------------------------------------- 不再按包装分布猜口径

@pytest.mark.parametrize("short", ["BP", "PS", "US", "PP"])
def test_pack_distribution_never_hides_calibers(catalog3, short):
    """R309：包再多也只说明包装规格，不代表玩家手里散装弹的口径 → 全列。"""
    items, loose, packs = _split(catalog3, short)
    assert len(loose) >= 2
    lines = [_line(short, 145, 42), _line("80", 141, 138, 33, 23)]
    kind, _qty, narrowed, _found, ambig = serve._ocr_ammo_decision(
        _name_box(), lines, loose + packs, items)
    assert kind == "loose"
    assert narrowed == loose, "不得按包装分布收窄口径"
    assert ambig is True
    assert serve._ocr_ambiguous(narrowed, items) is True


# ------------------------------------------------------- 候选价目表

def test_ambig_candidates_lists_caliber_prices(catalog3):
    """candidates：每个口径给名字 / 口径 / 形态 / 来源 / 价格，散装按单发商人价。"""
    _names, _idx, items = catalog3
    snap = {"5fc382a9d724d907e2077dab": {}, "5fd20ff893a8961fc660a954": {}}
    cands = serve._ocr_ambig_candidates(
        ["5fc382a9d724d907e2077dab", "5fd20ff893a8961fc660a954"], items, snap)
    by_cal = {c["caliber"]: c for c in cands}
    assert set(by_cal) == {".338", ".300"}
    for c in cands:
        assert c["kind"] == "loose" and c["source"] == "trader"
        assert isinstance(c["price"], int) and c["price"] > 0
    assert by_cal[".338"]["price"] > by_cal[".300"]["price"], \
        ".338 AP 商人价应显著高于 .300 AP（实测 2061 vs 391）"
    assert by_cal[".338"]["name"] == ".338 Lapua Magnum AP"


def test_ambig_candidates_keep_every_caliber(catalog3):
    """R309：候选表不得截断——FMJ 11 个口径，旧实现 [:6] 把 6.8x51 等直接丢掉。"""
    items, loose, _packs = _split(catalog3, "FMJ")
    assert len(loose) == 11
    cands = serve._ocr_ambig_candidates(loose, items, {})
    cals = [c["caliber"] for c in cands]
    assert len(cands) == len(loose), "候选数量必须等于候选口径数量"
    assert set(cals) == {serve._ocr_caliber(items[i]["n"]) for i in loose}
    assert "6.8x51" in cals


# ------------------------------------------------------- 前端与装配契约

def test_contract_ambiguous_wired_end_to_end():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    body = src[src.index("def _handle_ocr_recognize"):]
    assert "price.ambiguous" in body or '"ambiguous"' in body, \
        "装配处必须把 ambiguous 写进 price"
    assert "_ocr_ambig_candidates(" in body, "装配处必须给前端候选价目表"
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    assert "mk-ocr-ambig" in js and "price.ambiguous" in js, \
        "市场页要画黄色 ? 徽章并把候选写进 tooltip"
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()
    assert ".mk-ocr-ambig" in css, "徽章样式缺失"


def test_overlay_draws_ambig_badge(catalog3):
    """R252/R256：歧义物品浮窗只画 ? 徽章（价格、购物车一律不画）；无歧义的不画。"""
    import scan
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "_draw_ambig_badge" in src and "is_ambig_price" in src, \
        "浮窗必须有歧义徽章绘制与判定"
    # 歧义：只画黄色 ? 徽章，价格与购物车都不画（R256：无法准确识别就不显示价格）
    m = {"x": 60, "y": 40, "w": 90, "h": 22, "gw": 1, "gh": 1,
         "price": {"priceSource": "trader", "trader": 64800, "lastLow": None,
                   "ambiguous": True, "candidates": [{"name": "x", "price": 1}]}}
    img = scan.render_labels(700, 260, [m], "last", None)
    yellows = [(x, y) for y in range(50, 170) for x in range(0, 700)
               if (lambda p: abs(p[0] - 243) < 12 and abs(p[1] - 212) < 12
                   and abs(p[2] - 118) < 14 and p[3] > 200)(img.getpixel((x, y)))]
    assert yellows, "歧义物品必须画黄色 ? 徽章"
    reds = [x for y in range(50, 170) for x in range(0, 700)
            if (lambda p: p[0] > 190 and p[1] < 90 and p[2] < 90
                and p[3] > 200)(img.getpixel((x, y)))]
    assert not reds, "R256：歧义物品不画价格，故也不画红色购物车"
    # 无歧义商人价：不画徽章（价格/购物车仍正常画，属其它测试职责）
    m2 = {"x": 60, "y": 40, "w": 90, "h": 22, "gw": 1, "gh": 1,
          "price": {"priceSource": "trader", "trader": 2830, "lastLow": None}}
    img2 = scan.render_labels(700, 260, [m2], "last", None)
    yellows2 = [(x, y) for y in range(50, 170) for x in range(0, 700)
                if (lambda p: abs(p[0] - 243) < 12 and abs(p[1] - 212) < 12
                    and abs(p[2] - 118) < 14 and p[3] > 200)(img2.getpixel((x, y)))]
    assert not yellows2, "无歧义的物品不应画黄色徽章"
