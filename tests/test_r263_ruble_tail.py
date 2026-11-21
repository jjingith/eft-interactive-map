# -*- coding: utf-8 -*-
"""R263：`405 ₽/发` 里的 ₽ 被渲染成方框「口」的修复。

根因：`_split_ruble` 只拆**末尾**的 ₽；R261 把主价改成 `405 ₽/发` 后，₽ 落在中间、
字符串不再以 ₽ 结尾 → 整个 `405 ₽/发` 用中文字体绘制，微软雅黑没有 U+20BD 字形 →
显示成「405口/发」。

修法：`_split_ruble` 拆出 (前缀, 是否含₽, ₽后尾巴)；₽ 单独用 Segoe UI Bold 画，
尾巴（如 `/发`）用回主字体。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402

SRC = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()


def _ammo_match(qty_found):
    return {"x": 100, "y": 60, "w": 120, "h": 22, "gw": 1, "gh": 1,
            "name": "7N40", "key": "7n40",
            "price": {"priceSource": "trader", "trader": 405, "unitPrice": 405,
                      "qty": 1, "ammoStack": True, "qtyFound": qty_found, "base": 405}}


def test_split_ruble_handles_mid_string_ruble():
    """源码层面：_split_ruble 用 find 拆 ₽ 与尾巴（而不是只认结尾）。"""
    body = SRC[SRC.index("def _split_ruble"):SRC.index("def _split_ruble") + 600]
    assert 'text.find("₽")' in body
    assert "return text[:i].rstrip(), True, text[i + 1:]" in body


def test_draw_line_treats_ruble_and_tail_separately():
    body = SRC[SRC.index("def _draw_price_line"):SRC.index("def _fixed_label_font")]
    assert "core, ruble, tail = _split_ruble(text)" in body
    assert '_font("segoeuib", fs)' in body          # ₽ 用卢布符号字体
    assert "tail" in body                            # 尾巴用回主字体


def test_price_views_per_round_text():
    assert scan.price_views(_ammo_match(False), "last")[0] == "405 ₽/发"
    assert scan.price_views(_ammo_match(True), "last")[0] == "405 ₽"


def test_render_does_not_crash_with_ruble_tail():
    img = scan.render_labels(360, 140, [_ammo_match(False)], "last", tiers=None,
                             extra_bottom=40, badges_out=[], tier_basis="overall")
    assert img.size == (360, 180)
    assert any(p[3] > 0 for p in img.getdata())
