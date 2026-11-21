# -*- coding: utf-8 -*-
"""R244：价格标签三行版式——第 1 行留空（装备名自己那一行），第 2 行整体价，
第 3 行单格价。

用户反馈（2026-11-11 21:24）：
  「现在价格会和装备名称重叠 应该是再第一行是空格 第二行是单个物品的价格
    第三行是耽搁(单格)价格」
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import config  # noqa: E402
import scan  # noqa: E402

TIERS = config.OCR_SCAN_TIERS_DEFAULT


def _ink_rows(img, y0, y1, x_hi=420, step=2):
    rows = []
    for y in range(y0, min(y1, img.height), step):
        if any(img.getpixel((x, y))[3] > 0 for x in range(0, min(x_hi, img.width), step)):
            rows.append(y)
    return rows


def test_no_ink_over_name_row():
    """装备名所在行（第 1 行）必须完全透明——价格不再压名字。"""
    m = {"x": 0, "y": 0, "w": 220, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 400000}}
    img = scan.render_labels(800, 400, [m], "last", TIERS)
    assert _ink_rows(img, 0, 30) == [], "装备名行不应有任何价格墨迹"


def test_two_price_lines_start_below_name():
    """第 2 行 = 整体价、第 3 行 = 单格价，都从名字下沿起笔且两行分开。"""
    m = {"x": 0, "y": 0, "w": 220, "h": 30, "gw": 2, "gh": 2,
         "price": {"lastLow": 400000}}
    img = scan.render_labels(800, 400, [m], "last", TIERS)
    rows = _ink_rows(img, 0, 220, step=1)
    assert rows, "应有价格墨迹"
    assert rows[0] >= 30, "价格起点必须在名字下沿（h=30）之后，实际 %d" % rows[0]
    # 墨迹应分成两段（整体价 / 单格价），中间有可见空隙
    bands = []
    prev = None
    for y in rows:
        if prev is None or y != prev + 1:
            bands.append([y, y])
        else:
            bands[-1][1] = y
        prev = y
    assert len(bands) == 2, "应恰好两段价格墨迹（整体价 + 单格价），实际 %s" % bands
    assert bands[1][0] - bands[0][1] >= 4, "两行之间应有空隙，实际 %s" % bands


def test_extra_bottom_lets_bottom_rows_draw_below_name():
    """框选区贴近屏幕下沿：extra_bottom 让最后一行的价格仍画在名字下方。"""
    h = 30
    m = {"x": 0, "y": 300, "w": 220, "h": h, "gw": 1, "gh": 1,
         "price": {"lastLow": 400000}}
    # 无额外空间：画布高 340，价格放下不 → 兜底改画在名字上方
    img_plain = scan.render_labels(800, 340, [m], "last", TIERS)
    assert _ink_rows(img_plain, 300, 330) == [], "空间不足时不应压名字（应改画在上方）"
    # 有额外空间：画布变高，价格落在名字下方
    img_extra = scan.render_labels(800, 340, [m], "last", TIERS, extra_bottom=160)
    assert img_extra.height == 500
    below = _ink_rows(img_extra, 330, 500)
    assert below and min(below) >= 330, "有额外空间时价格应在名字下方"


def test_render_canvas_height_grows_with_extra_bottom():
    m = {"x": 0, "y": 0, "w": 200, "h": 20, "gw": 1, "gh": 1,
         "price": {"lastLow": 9000}}
    base = scan.render_labels(600, 200, [m], "last", TIERS)
    grown = scan.render_labels(600, 200, [m], "last", TIERS, extra_bottom=120)
    assert base.size == (600, 200)
    assert grown.size == (600, 320)


def test_dense_rows_fall_back_inline_never_cover_next_name():
    """两件贴得很近（dy=70 < 三行块高）时退化为名字右侧单行——下一件名字必须干净。"""
    a = {"x": 0, "y": 0, "w": 160, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 400000}}
    b = {"x": 0, "y": 70, "w": 160, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 9000}}
    img = scan.render_labels(800, 400, [a, b], "last", TIERS)
    # b 的名字行（70..100）不能有任何价格墨迹
    assert _ink_rows(img, 70, 100, step=1) == [], "价格压到了下一件装备名"
    # a 的价格应画在名字右侧同一行
    right = [x for x in range(170, 700)
             if any(img.getpixel((x, y))[3] > 0 for y in range(0, 40))]
    assert right, "行距不足时应退化为名字右侧单行"
