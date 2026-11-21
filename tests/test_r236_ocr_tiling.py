# -*- coding: utf-8 -*-
"""R236：整图分块识别（修「只能识别出几个物体」）。

用户原话（2026-11-11 14:37）：
  「你再看看 小喵工具箱是怎么做的 我现在试了几次都不对 只能识别出几个物体」

根因：整图 1080p 走单次 det（960 边长）会把游戏 14px 小字压到 ~7px，检测器失明。
XiaoMeow 的做法是 RecognizeChunked 分块（每块原生分辨率 + ≤1.6× 放大）。
补丁：块 640 / 步进 320（overlap 0.5）。窗口每 step 平移一次，文本宽 L 完整落入
某块 ⇔ L ≤ W − S = 320px，覆盖库存物品名的实际宽度；1080p 约 24 块 ≈ 6s。
另修匹配器两个真缺陷：
  ① token 候选窗口只对 len(tok) 开档，全名键带空格进不了候选 → OCR 吞空格时
     错配近似键（MP-133 错配 MP-153）。修：对 len(tok) 与 len(tok 去空格)
     各开一档，ratio 对键的两种形态取较高。
  ② 短 token（≤6 字符）在 0.60 阈值下太松（HUD 文字 'Esape' 擦线配上 'eagle'）。
     修：≤6 用 0.72，>6 用 0.60。
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import ocr  # noqa: E402

TRUTH_12 = [
    "柯尔特 M4A1 5.56x45 卡宾枪", "工厂紧急出口钥匙", "马卡洛夫9x18PM 手枪",
    "RGD-5手榴弹", "90-93 9x18PM 8发PM弹匣", "600 毫升瓶装水", "军用饼干",
    "ER“支点”刺刀", "MP-133 12 铅径泵动式霰弹枪", "Flyye MBSS 背包（通用迷彩）",
    "无菌绷带", "固定夹板",
]


# ---------------------------------------------------------------- 匹配器修复（纯 stdlib）

@pytest.fixture(scope="module")
def matcher():
    return ocr.ItemMatcher(TRUTH_12)


def test_token_fuzzy_finds_spaced_key_without_spaces(matcher):
    """OCR 吞空格 + 缺字（霰→无）：token 层必须经无空格变体命中 MP-133，
    不得错配 MP-153（修复前实测错配）。"""
    m = matcher.match_line("MP-13312铅径泵动式弹枪", 0.9, None)
    assert m is not None, "吞空格 + 缺字应命中"
    names = matcher.names_for(m["key"])
    assert any("MP-133" in n for n in names), (m["key"], names)


def test_token_fuzzy_no_mp153_confusion(matcher):
    """MP-153 与 MP-133 仅差两位数字——不得因候选窗口缺失而错配。"""
    m = matcher.match_line("MP-13312铅径泵动式弹枪", 0.9, None)
    if m is None:
        pytest.skip("该文本此轮未命中（保守丢弃也可接受）")
    assert not any("MP-153" in n for n in matcher.names_for(m["key"]))


def test_short_latin_token_needs_strict_ratio(matcher):
    """≤6 字符 token 用 0.72：'Esape' 不得擦线配上 'eagle'（修复前 0.60 擦线命中）。"""
    assert matcher.resolve_key("Esape from Tarkov 12:34:56")[0] is None


def test_tile_geometry_guarantees_text_width():
    """块几何：文本宽 L 完整落入某块 ⇔ L ≤ TILE_SIZE − step。"""
    assert ocr.TILE_SIZE - int(ocr.TILE_SIZE * (1 - ocr.TILE_OVERLAP)) >= 320


def test_tiled_trigger_threshold():
    assert ocr.TILED_TRIGGER > ocr.TILE_SIZE  # 分块块本身不二次分块


# ---------------------------------------------------------------- 引擎级（依赖可用才跑）

def _engine_if_available():
    ok, _hint = ocr.check_available()
    return ocr.get_engine() if ok else None


def test_tiled_full_hd_recovers_all_items():
    """1920×1080 库存风大图：分块后 12 个物品名全部命中（修复前只认出少数）。"""
    eng = _engine_if_available()
    if eng is None:
        pytest.skip("OCR 重依赖不在本机（服务端 Python 才有）")
    big = os.path.join(ROOT, "build", "_ocr_big_test.png")
    if not os.path.isfile(big):
        pytest.skip("大图测试样本未生成")
    import json
    img = ocr.decode_image_bgr(open(big, "rb").read())
    assert max(img.shape[:2]) > ocr.TILED_TRIGGER
    lines, _ann, ms = eng.recognize(img)
    assert ms < 30000, "整图分块应 <30s（实测 ~6s）"
    items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]
    m = ocr.ItemMatcher(v["n"] for v in items.values())
    matches = m.match_lines(lines)
    got = set()
    for x in matches:
        got.update(m.names_for(x["key"]))
    hit = [n for n in TRUTH_12 if n in got]
    assert len(hit) >= 11, "12 个物品名至少命中 11（实测 12/12）：漏 %s" % (set(TRUTH_12) - set(hit))


def test_dedup_lines_collapses_tile_overlaps():
    """同文本中心距 < 24px 或 IoU > 0.3 的跨块重复只留最高分。"""
    lo = {"text": "工厂紧急出口钥匙", "score": 0.9,
          "points": [[10, 10], [100, 10], [100, 30], [10, 30]]}
    hi = {"text": "工厂紧急出口钥匙", "score": 0.95,
          "points": [[12, 12], [102, 12], [102, 32], [12, 32]]}
    far = {"text": "工厂紧急出口钥匙", "score": 0.8,
           "points": [[600, 500], [700, 500], [700, 520], [600, 520]]}
    out = ocr.OcrEngine._dedup_lines([lo, hi, far])
    assert len(out) == 2
    assert max(x["score"] for x in out) == 0.95


def test_dedup_lines_iou_collapses_partial_vs_full_box():
    """重叠块里同一段文字被切出「部分框 vs 完整框」：中心距超 24 但 IoU 高，须收敛。"""
    partial = {"text": "Flyye MBSS背包", "score": 0.90,
               "points": [[60, 410], [230, 410], [230, 432], [60, 432]]}
    full = {"text": "Flyye MBSS 背包（通用迷彩）", "score": 0.95,
            "points": [[60, 410], [330, 410], [330, 432], [60, 432]]}
    # 不同物理位置的同一物品名：不得误杀
    other = {"text": "Flyye MBSS 背包（通用迷彩）", "score": 0.88,
             "points": [[900, 800], [1170, 800], [1170, 822], [900, 822]]}
    out = ocr.OcrEngine._dedup_lines([partial, full, other])
    assert len(out) == 2
    assert out[0]["score"] == 0.95  # 完整框（更高分）保留
