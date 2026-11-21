# -*- coding: utf-8 -*-
"""R243：统一字号 + 精确卢布金额。

用户反馈（2026-11-11 21:08）：
  「字体就是得固定大小 现在你搞得字体大小不同一 …… 单位不应该是万 而是卢布的
    单位 精确到个位数」

修复：①标签基准字号取**所有识别行框高的中位数**（全场景统一，不随单品抖动；
仍是该玩家屏幕上游戏文字的实际大小）；②金额 = 精确到个位的卢布 `431,400 ₽`；
③标签左沿 = 装备名行框左沿（左对齐）。

R249 迁移：用户实测后要求改成**右对齐**（价格右沿 = 装备名最右侧的字），且字号
固定为 0.80×行框高并按单格宽度全局收缩。本文件两条位置/字号断言随之迁移。
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


def test_label_base_font_is_median_and_clamped():
    assert scan.label_base_font([{"h": 20}, {"h": 40}]) == 40      # 两值取上中位
    assert scan.label_base_font([{"h": 20}, {"h": 30}, {"h": 50}]) == 30
    assert scan.label_base_font([]) == 16
    assert scan.label_base_font([{"h": 2}]) == 9                   # 钳下限
    assert scan.label_base_font([{"h": 999}]) == 300               # 钳上限


def test_render_uniform_font_size_regardless_of_item_height():
    """同一浮窗里两件物品行框高不同（20 vs 40），标签字号仍必须一致。"""
    sys.path.insert(0, TOOLS)
    a = {"x": 0, "y": 0, "w": 200, "h": 20, "gw": 1, "gh": 1,
         "price": {"lastLow": 431400}}
    b = {"x": 0, "y": 260, "w": 200, "h": 40, "gw": 1, "gh": 1,
         "price": {"lastLow": 9000}}
    img = scan.render_labels(900, 520, [a, b], "last", config.OCR_SCAN_TIERS_DEFAULT)

    def first_line_ink_span(y0, y1):
        rows = [y for y in range(y0, min(y1, img.height))
                if any(img.getpixel((x, y))[3] > 0 for x in range(0, 420, 2))]
        return (min(rows), max(rows)) if rows else None

    # R249：字号 0.80×行框高中位数（这里是 32px），第一行墨迹带 41..75 / 309..343。
    # 窗口只圈第一行，别把第二行「单格 …」一起量进去。
    span_a = first_line_ink_span(30, 78)
    span_b = first_line_ink_span(298, 346)
    assert span_a and span_b
    # 两处第一行墨迹高度应相同（±2px 抗锯齿余量）
    assert abs((span_a[1] - span_a[0]) - (span_b[1] - span_b[0])) <= 2, \
        "字号不统一：%s vs %s" % (span_a, span_b)


def test_label_text_is_full_ruble():
    assert scan.fmt_short(431400) == "431,400 ₽"
    assert scan.fmt_short(399999) == "399,999 ₽"
    m = {"price": {"lastLow": 399999}, "gw": 1, "gh": 2}
    main, slot, _kg = scan.price_views(m, "last")
    # 单格 = 整体/格数；fmt 精确到个位（199999.5 → 四舍六入到 200,000）
    assert main == "399,999 ₽" and slot == "200,000 ₽"
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    body = src[src.index("def fmt_short"):src.index("def price_views")]
    impl = body.split('"""')[-1]      # 去掉 docstring（说明文字里含「万/亿」）
    assert "万" not in impl and "亿" not in impl, "不允许万/亿简写"


def test_labels_right_aligned_to_name_bbox():
    """R249：价格**右端**对齐装备名最右侧的字（x + w = 320），不再左对齐。

    游戏里物品名印在格子右上角，左对齐会让价格向右冲进邻格；右对齐后向左展开
    正好落在本格内。描边向外扩几像素属正常。
    """
    sys.path.insert(0, TOOLS)
    m = {"x": 120, "y": 60, "w": 200, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 431400}}
    img = scan.render_labels(700, 300, [m], "last", config.OCR_SCAN_TIERS_DEFAULT)
    cols = [x for x in range(0, img.width)
            if any(img.getpixel((x, y))[3] > 0 for y in range(92, 170, 2))]
    assert cols and 302 <= cols[-1] <= 322, \
        "右沿应贴近 bbox 右沿（x+w=320），实际 %s" % cols[-2:]
    assert cols[0] < 300, "价格应从名字右沿向左展开，而不是从名字左沿向右冲"
