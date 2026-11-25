# -*- coding: utf-8 -*-
"""R309：浮窗控制条「总价值」（PvE 按钮左边）。

用户口径：识别价格的浮窗里，PvE 按钮边上直接显示这一堆装备的总价值，一眼看完。

契约：
  · 总额与浮窗价格严格同源（price_base / 当前价格口径，散装弹是整堆价）；
  · 只画 ? 不报价的歧义物品不计入，总额前缀 ≈（已知下限）；
  · 全部无价 → 「总价值 —」；
  · 只读栏在「切换模式」按钮左侧，与按钮之间保留透明间隔（不参与 hit_button）。
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


def _match(price: dict) -> dict:
    return {"x": 0, "y": 0, "w": 10, "h": 10, "price": price}


def _text(matches, mode_idx=0) -> str:
    sess = SimpleNamespace(matches=matches, mode_idx=mode_idx)
    return scan.OverlaySession.total_value_text(sess)


def test_total_value_sums_prices_of_current_mode():
    matches = [
        _match({"priceSource": "flea", "lastLow": 1000, "avg24h": 1200}),
        _match({"priceSource": "flea", "lastLow": 2500, "avg24h": 3000}),
    ]
    assert _text(matches, 0) == "总价值 3,500 ₽"
    assert _text(matches, 1) == "总价值 4,200 ₽", "切口径后总额必须跟着变"


def test_total_value_counts_loose_ammo_stack_total():
    """散装弹的 trader 字段已是「单发 × 堆叠数量」，总额直接用它。"""
    matches = [_match({"priceSource": "trader", "trader": 19040, "perSlot": 19040})]
    assert _text(matches) == "总价值 19,040 ₽"


def test_total_value_skips_ambiguous_and_marks_approx():
    matches = [
        _match({"priceSource": "flea", "lastLow": 1000}),
        _match({"priceSource": "flea", "lastLow": 9999, "ambiguous": True}),
    ]
    assert _text(matches) == "总价值 ≈ 1,000 ₽"


def test_total_value_all_ambiguous_is_dash():
    matches = [_match({"priceSource": "flea", "lastLow": 9999, "ambiguous": True})]
    assert _text(matches) == "总价值 —"


def test_total_value_counts_manual_pick_and_unpriced_partial():
    picked = _match({"priceSource": "flea", "ambiguity": True, "ambiguous": True,
                     "manual": 238})
    unpriced = _match({"priceSource": "flea"})
    assert _text([picked]) == "总价值 238 ₽", "手动选口径后按所选价计入"
    assert _text([picked, unpriced]) == "总价值 ≈ 238 ₽", "无价物品存在时标 ≈"


def test_control_total_chip_sits_left_of_gamemode():
    """总价值栏在最左侧，与「切换模式」按钮之间保留透明间隔。"""
    img, rgm, rb, rc = scan.render_control(
        "PvE", "最新价格", 1.0, total_label="总价值 12,345 ₽")
    assert rgm[0] > 0 and rgm[2] < rb[0] < rc[0]
    chip_w = rgm[0] - 4              # scale=1 → gap=4
    # 金额栏本身是可见的（凹面填充 alpha≈246）
    assert any(img.getpixel((x, y))[3] > 200
               for x in range(0, chip_w) for y in (2, img.height // 2))
    # 与按钮之间的间隔列全透明（点击穿透）
    for x in range(chip_w, rgm[0]):
        assert all(img.getpixel((x, y))[3] == 0 for y in range(img.height))


def test_control_without_total_keeps_old_layout():
    _img, rgm, _rb, rc = scan.render_control("PvE", "最新价格", 1.0)
    assert rgm[0] == 0, "不传 total_label 时布局与旧版一致"
    assert rc[2] == _img.width
