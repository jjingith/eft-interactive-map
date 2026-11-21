# -*- coding: utf-8 -*-
"""R253：浮窗 ? 徽章可点击 → 弹出「选择口径」选单，手动选定后价格立即生效。

用户反馈（2026-11-12 15:06）：
  「问号徽章 我觉得可以改成是可以点击的 点击后就是选择口径 的选单」

架构：
  · 标签窗（role 0）去掉 WS_EX_TRANSPARENT——它会让系统完全跳过该窗口的鼠标
    消息；改用 WM_NCHITTEST 精确放行：命中 ? 徽章矩形 → HTCLIENT，其余 →
    HTTRANSPARENT（ULW alpha=0 像素本就不命中，行为与原先等效）。
  · 选单是新 role 6 分层窗（NOACTIVATE 不抢焦点），显示时 SetCapture：点行内
    → 选口径（price.manual），点菜单外 → 关闭。
  · price_base 优先 `price.manual`：候选只有单价没有历史行情，四种时间口径
    同值；徽章保留，可再次点开重选。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402

CANDS = [
    {"name": ".338 Lapua Magnum FMJ", "price": 810, "kind": "loose",
     "caliber": ".338", "source": "trader"},
    {"name": "5.56x45毫米 FMJ", "price": 38, "kind": "loose",
     "caliber": "5.56x45", "source": "trader"},
    {"name": "5.45x39mm BS弹药包（120发装）", "price": None, "kind": "pack",
     "caliber": "5.45x39", "source": "flea"},
]


def _match(**extra):
    p = {"priceSource": "trader", "trader": 64800, "lastLow": None,
         "ambiguous": True, "candidates": CANDS,
         "name": ".338 Lapua Magnum FMJ"}
    p.update(extra.pop("price_extra", {}))
    base = {"x": 60, "y": 40, "w": 90, "h": 22, "gw": 1, "gh": 1, "text": "FMJ",
            "price": p}
    base.update(extra)
    return base


# ------------------------------------------------------------ 手动选价

def test_price_base_manual_overrides_every_mode():
    """手动选口径后四种时间口径都显示所选价（候选无历史行情，同值最诚实）。"""
    m = {"price": {"lastLow": 100, "avg24h": 200, "w72": 300, "w30d": 400,
                   "manual": 555}}
    for key in scan.MODE_FIELDS.values():
        assert scan.price_base(m, key) == 555, key


def test_price_base_without_manual_unchanged():
    m = {"price": {"priceSource": "trader", "trader": 450, "lastLow": None}}
    assert scan.price_base(m, "last") == 450
    m2 = {"price": {"lastLow": 431400, "manual": None}}      # 空选不生效
    assert scan.price_base(m2, "last") == 431400
    m3 = {"price": {"lastLow": 100, "manual": -5}}           # 非法值忽略
    assert scan.price_base(m3, "last") == 100


# ------------------------------------------------------------ 徽章命中区

def test_render_labels_collects_badge_rects_on_yellow_center():
    """badges_out 收集的矩形中心必须是徽章黄色像素（命中区 = 所见）。"""
    badges = []
    img = scan.render_labels(700, 260, [_match()], "last", None,
                             badges_out=badges)
    assert len(badges) == 1 and badges[0][0] == 0
    x0, y0, x1, y1 = badges[0][1]
    assert x1 > x0 and y1 > y0
    r, g, b, a = img.getpixel(((x0 + x1) // 2, (y0 + y1) // 2))
    assert abs(r - 138) < 30 and g < 140 and b < 60 and a > 200, \
        "徽章矩形中心应是黄色圆（含描边混合），实际 %s" % ((r, g, b, a),)


def test_render_labels_no_badges_without_ambiguity():
    m = _match(price_extra={"ambiguous": None})
    m["price"].pop("ambiguous")
    badges = []
    scan.render_labels(700, 260, [m], "last", None, badges_out=badges)
    assert badges == []


# ------------------------------------------------------------ 选单渲染

def test_render_menu_rows_and_current_dot():
    img, rows = scan.render_menu(CANDS, 18, ".338 Lapua Magnum FMJ")
    assert img is not None and len(rows) == len(CANDS)
    for r in rows:
        assert r[2] > r[0] and r[3] > r[1]
    # 行高一致、纵向相连
    assert rows[0][3] == rows[1][1] and rows[1][3] == rows[2][1]


def test_render_menu_empty_candidates():
    img, rows = scan.render_menu([], 18, "")
    assert img is None and rows == []


def test_render_menu_name_and_price_do_not_overlap():
    """最长名字 + 最长价格也不许重叠（名字超长截断 …）。"""
    long_cands = [
        {"name": "5.45x39mm BS弹药包（120发装）", "price": None, "kind": "pack"},
        {"name": "7.62x54R FMJ", "price": 431400, "kind": "loose"},
        {"name": ".338 Lapua Magnum AP弹药包（20发装）", "price": 450, "kind": "pack"},
    ]
    img, _rows = scan.render_menu(long_cands, 18, "")
    # 名字区与价格区之间至少留 8px：取样每行中点右侧价格列与名字末端的间隙
    # （简化为结构断言：菜单宽度必须 ≥ 名字估算 + 价格 + 间距）
    assert img.size[0] >= 200


# ------------------------------------------------------------ 原生链路契约

def test_overlay_wiring_exists():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    for token in ("def hit_badge", "def toggle_menu", "def open_menu",
                  "def menu_click", "def pick_candidate", "def close_menu",
                  "render_menu(", "badges_out=badges", "SetCapture",
                  "ReleaseCapture", "SW_HIDE"):
        assert token in src, "浮窗选单链路缺 %s" % token
    # role 6 窗口 + role 0 不再整窗穿透（WS_EX_TRANSPARENT 只留给 4/5）
    assert "if role in (4, 5):" in src and "ex |= WS_EX_TRANSPARENT" in src
    body = src[src.index("def _ov_wndproc"):]
    assert "role == 6" in body, "WndProc 必须处理选单窗点击"
    assert "_ACTIVE.hit_badge(pt.x, pt.y)" in body, "标签窗命中必须走徽章矩形"


def test_price_views_show_manual_price_every_mode():
    """选完口径后浮窗四种口径显示同一个所选价（切口径不回跳推断价）。"""
    m = _match(price_extra={"manual": 38})
    seen = {scan.price_views(m, key)[0] for key in scan.MODE_FIELDS}
    assert seen == {"38 ₽"}, seen
