# -*- coding: utf-8 -*-
"""R249：浮窗按钮 XP 化 / 价格右对齐固定字号 / 禁售跳蚤改商人价。

用户反馈（2026-11-12）：
  「右上角的价格切换钮和关闭键 应该是两个分开的按钮 采用项目现有的xp风格ui
    然后位置要微调 按钮的最下面的边 应该在截图选框的最上边的上面 有一个像素间隔
    现在按钮会挡住价格
    然后字体我发现有些大了 如果是单格的物资 如果价值高了 价格的字会超出物资的宽度
    另外 现在是价格和物资右上角名称的最左侧的字 向左对齐
    改成最右侧的字向右对齐 然后字体改成固定的大小 大小你自己测
    然后 有些东西是不能上跳蚤的 现在识别出来是没有价格的
    这种情况就按照贩卖给商人的价格显示 然后标注一个红色的购物车小图标」

实测标定：`ui图标/ocr测试专用游戏内截图.png`（3840×2160 真实游戏仓库）里
OCR 行框高 19~27px（中位 22）、相邻单格物品名 x 间距 126px → 格宽 ≈ 5.7×行框高；
所以固定字号取 0.80×行框高，并按这个格宽做一次全局收缩。
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

TIERS = config.OCR_SCAN_TIERS_DEFAULT
WIN_ONLY = pytest.mark.skipif(not scan.IS_WINDOWS, reason="原生浮窗仅 Windows")


def _ink_cols(img, y0, y1, x0=0, x1=None):
    x1 = img.width if x1 is None else x1
    return [x for x in range(x0, min(x1, img.width))
            if any(img.getpixel((x, y))[3] > 0 for y in range(y0, min(y1, img.height)))]


def _ink_rows(img, x0, x1, y0=0, y1=None):
    y1 = img.height if y1 is None else y1
    return [y for y in range(y0, min(y1, img.height))
            if any(img.getpixel((x, y))[3] > 0 for x in range(x0, x1))]


def _match(x, y, w, h, price, gw=1, gh=1):
    return {"x": x, "y": y, "w": w, "h": h, "gw": gw, "gh": gh,
            "price": {"lastLow": price, "avg24h": price, "avg7d": price,
                      "w72": price, "w30d": price, "base": price}}


# ---------------------------------------------------------------- 纯几何

def test_control_position_one_pixel_above_selection_top():
    """按钮底边 == 框选区顶边 - 1px（原来在选区内部 ry+2，会挡住价格）。"""
    cx, cy = scan.control_position(200, 300, 800, 500, 82, 24, 1920, 1080)
    assert cy + 24 == 300 - 1
    assert cx + 82 <= 200 + 800
    assert cx >= 0
    # 选区贴屏幕上沿时退到选区下沿外 1px，绝不压到选区里
    _, cy2 = scan.control_position(200, 5, 800, 500, 82, 24, 1920, 1080)
    assert cy2 == 5 + 500 + 1


def test_control_position_never_leaves_screen():
    for ry, rh in ((0, 1070), (3, 1070), (1000, 80)):
        _, cy = scan.control_position(0, ry, 900, rh, 90, 28, 1920, 1080)
        assert 0 <= cy <= 1080 - 28


# ---------------------------------------------------------------- XP 双按钮

@WIN_ONLY
def test_control_is_three_separate_xp_buttons():
    # R256：控制条三键 [切换模式][价格切换][关闭]，彼此透明间隔，不是胶囊
    img, rgm, rb, rc = scan.render_control("PvP", "最新价格", 1.0)
    assert rgm[2] < rb[0] < rc[0], "三个按钮之间必须留有间隔"
    assert rb[0] - rgm[2] >= 3 and rc[0] - rb[2] >= 3
    # 间隔列必须全透明（点击也穿透）
    for x in range(rgm[2], rb[0]):
        assert all(img.getpixel((x, y))[3] == 0 for y in range(img.height))
    for x in range(rb[2], rc[0]):
        assert all(img.getpixel((x, y))[3] == 0 for y in range(img.height))
    # 按钮面是项目 XP Luna 皮肤（浅色），不是旧的深色胶囊
    light = 0
    for x, y in ((3, 3), (rgm[2] - 4, 3), (rgm[2] + 4, img.height - 4),
                 (rb[0] + 4, 4), (rc[0] + 4, img.height - 5), (rc[2] - 4, img.height - 5)):
        p = img.getpixel((x, y))
        if p[3] > 180 and p[0] > 175 and p[1] > 170 and p[2] > 150:
            light += 1
    assert light >= 4, "应使用 assets/xp-ui/btn-*.png 的浅色 XP 按钮皮肤"


@WIN_ONLY
def test_control_hover_pressed_states_change_skin():
    normal = scan.render_control("PvP", "最新价格", 1.0)[0].tobytes()
    hover = scan.render_control("PvP", "最新价格", 1.0, hover="gamemode")[0].tobytes()
    pressed = scan.render_control("PvP", "最新价格", 1.0, pressed="close")[0].tobytes()
    assert normal != hover and normal != pressed and hover != pressed


@WIN_ONLY
def test_control_rects_do_not_overlap_and_cover_whole_button():
    img, rgm, rb, rc = scan.render_control("PvE", "7日均价", 1.0)
    assert rgm == (0, 0, rgm[2], img.height)
    assert rc[2] == img.width and rc[1] == 0 and rc[3] == img.height


def test_xp_skin_assets_exist_and_are_the_project_ones():
    for name in ("btn-normal.png", "btn-hover.png", "btn-pressed.png"):
        path = os.path.join(ROOT, "assets", "xp-ui", name)
        assert os.path.isfile(path), path
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "btn-normal.png" in src and "_nine_slice" in src


# ---------------------------------------------------------------- 右对齐 / 固定字号

@WIN_ONLY
def test_prices_right_align_to_name_right_edge():
    """价格最右侧的字对齐装备名最右侧的字（x+w），不再从名字左沿向右冲。"""
    a = _match(100, 0, 86, 22, 400000)
    b = _match(400, 200, 86, 22, 9000)
    img = scan.render_labels(900, 420, [a, b], "last", TIERS)
    ca = _ink_cols(img, 25, 100, 0, 300)
    cb = _ink_cols(img, 225, 300, 300, 650)
    assert ca and cb
    assert 100 + 86 - 8 <= ca[-1] <= 100 + 86 + 4, "第一件价格右沿 %s" % ca[-1]
    assert 400 + 86 - 8 <= cb[-1] <= 400 + 86 + 4, "第二件价格右沿 %s" % cb[-1]
    assert ca[0] < 100 + 86, "价格应向左展开进本格，不是向右冲进邻格"


@WIN_ONLY
def test_fixed_font_is_identical_across_items_and_price_modes():
    """字号全场固定：不同物品、切换四种口径都不许变字号。"""
    a = _match(100, 0, 86, 22, 4000000)
    b = _match(400, 200, 86, 22, 9000)
    heights = []
    for key in scan.MODE_FIELDS:
        img = scan.render_labels(900, 420, [a, b], key, TIERS)
        for x0, x1, y0, y1 in ((0, 300, 0, 160), (300, 650, 190, 380)):
            rows = _ink_rows(img, x0, x1, y0, y1)
            assert rows
            # 第一行墨迹连续带的高度 = 字号的可观测代理
            band = [y for y in rows if y < rows[0] + 60]
            heights.append(band[-1] - band[0])
    assert max(heights) - min(heights) <= 2, "字号随物品/口径变化了：%s" % heights


@WIN_ONLY
def test_high_value_single_slot_price_stays_inside_cell():
    """4K 实测格宽 126px / 行框高 22px：高价单格物品的价格不能溢出格子。"""
    # 真实仓库里相邻单格物品名 x 间距 126px（BS / BT / M856A1 …）；错开 y 便于
    # 逐件量墨迹（同一行会串到一起），格宽标定仍由 x 间距给出。
    xs = (145, 271, 400, 526)
    ys = (169, 300, 431, 562)
    matches = [_match(x, y, 86, 22, 4000000) for x, y in zip(xs, ys)]
    unit = scan.label_cell_unit(matches, scan.label_base_font(matches))
    assert 120 <= unit <= 128, "格宽标定应贴近实测 126px，实际 %s" % unit
    img = scan.render_labels(840, 700, matches, "last", TIERS)
    for x, y in zip(xs, ys):
        right = x + 86
        cols = _ink_cols(img, y + 25, y + 120,
                         max(0, int(right - unit - 30)), min(img.width, right + 30))
        assert cols, "物品 %d 应有价格" % x
        assert cols[-1] <= right + 4, "价格冲出物品右沿：%s > %s" % (cols[-1], right)
        assert cols[0] >= right - unit - 4, \
            "价格向左超出单格宽度：%s < %s" % (cols[0], right - unit)


def test_cell_unit_calibration_is_resolution_independent():
    """1080p（11px 字 / 63px 格）与 4K（22px 字 / 126px 格）同比例。"""
    unit4k = scan.label_cell_unit([_match(x, 0, 60, 22, 1000) for x in (0, 126, 252)], 22)
    unit1080 = scan.label_cell_unit([_match(x, 0, 30, 11, 1000) for x in (0, 63, 126)], 11)
    assert unit4k / 22 == pytest.approx(unit1080 / 11, abs=0.05)


# ---------------------------------------------------------------- 商人价 + 图标（R280 起为商人头像）

def test_trader_price_used_for_every_mode():
    """商人只有一口价：四种口径都显示同一个收购价，不拿跳蚤历史凑数。"""
    m = {"gw": 1, "gh": 1, "price": {"priceSource": "trader", "trader": 10239,
                                     "lastLow": None, "avg24h": None,
                                     "w72": None, "w30d": None}}
    assert scan.is_trader_price(m)
    for key in scan.MODE_FIELDS:
        main, slot, _kg = scan.price_views(m, key)
        assert main == "10,239 ₽" and slot == "10,239 ₽"
    m2 = _match(0, 0, 80, 22, 10239)
    assert not scan.is_trader_price(m2)
    assert scan.price_views(m2, "last")[0] == "10,239 ₽"


@WIN_ONLY
def test_trader_label_shows_portrait_instead_of_red_cart():
    """R280：禁售跳蚤（商人收购价）改显示最高收购价商人的头像，红购物车撤掉。

    蓝色购物车（traderSell）与跳蚤价不受影响，见 tests/test_r280_trader_display.py。
    """
    m = {"x": 300, "y": 60, "w": 80, "h": 22, "gw": 1, "gh": 1,
         "price": {"priceSource": "trader", "trader": 12345, "lastLow": None,
                   "traderId": "54cb50c76803fa8b248b4571"}}
    img = scan.render_labels(700, 300, [m], "last", TIERS)

    def cart_reds(im):
        """只数自绘红购物车的填充色 (226,54,48)，不把头像里的暖色误判成图标。"""
        n = 0
        for y in range(60, 160):
            for x in range(180, 400):
                r, g, b, a = im.getpixel((x, y))
                if a > 180 and abs(r - 226) < 12 and abs(g - 54) < 12 and abs(b - 48) < 12:
                    n += 1
        return n

    def colored(im):
        """真人头像是彩色照片；单色自绘图标/灰白价格文字不会有这么多彩色像素。"""
        n = 0
        for y in range(60, 160):
            for x in range(180, 400):
                r, g, b, a = im.getpixel((x, y))
                if a > 180 and max(r, g, b) - min(r, g, b) > 18:
                    n += 1
        return n

    assert cart_reds(img) == 0, "红色购物车已被商人头像替换"
    assert colored(img) > 20, "应画出任务界面同款商人头像"
    flea = scan.render_labels(700, 300, [_match(300, 60, 80, 22, 12345)], "last", TIERS)
    assert cart_reds(flea) == 0, "正常跳蚤价不该出现红色图标"


def test_bff_trader_price_comes_from_market_sell_to_source():
    """商人价取 items.json 的 sl（市场页「Sell to 卖给谁」同源），不臆造。"""
    import json

    import serve

    doc = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))
    picked = None
    for iid, rec in (doc.get("items") or {}).items():
        if ("noFlea" in (rec.get("ts") or []) and rec.get("sl")
                and isinstance(rec["sl"][0][1], (int, float)) and rec["sl"][0][1] > 0):
            picked = (iid, rec)
            break
    assert picked, "数据里应存在 noFlea 且有商人收购价的物品"
    _iid, rec = picked
    price, trader_id, approx = serve._trader_sell_price(rec)
    assert price == max(int(r[1]) for r in rec["sl"] if isinstance(r[1], (int, float)))
    assert trader_id == rec["sl"][0][0] and approx is False
    assert serve._ocr_no_flea(rec) is True
    # 没有 sl 时退回基础价并标记 approx
    assert serve._trader_sell_price({"p": {"b": 22755}}) == (22755, None, True)
    assert serve._trader_sell_price({}) == (None, None, False)


def test_recognize_contract_emits_trader_flag_and_overlay_keeps_it():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    assert '"priceSource": "trader"' in src
    assert "_trader_sell_price(rec)" in src and "_ocr_no_flea(rec)" in src
    assert '"noFlea",' in src and '"ammoKind", "qty", "price"' in src, \
        "交接白名单必须放行 noFlea / ammoKind / qty"
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    # R258：价格来源三档（跳蚤 / 商人售卖 / 商人收购）——都读 priceSource 判定
    assert 'm.price.priceSource' in js
    assert 'kind === "trader"' in js and 'kind === "traderSell"' in js
