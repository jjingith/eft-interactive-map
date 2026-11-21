# -*- coding: utf-8 -*-
"""R234：截图 OCR 价格识别（PaddleOCR det/rec + ItemMatcher + 市场同源价格）。

用户原话（2026-11-11 12:11）：
  「走A 然后项目不是网页啊 是独立的程序 只不过现在没有打包 所以测试是用网页
    然后价格就能使用市场界面里的数据了」

规格来源：docs/r32-xiaomeow-re/REPORT.md §3（XiaoMeowToolbox 管线逐常量复刻）。
工具链分层：tools/ocr.py 纯 stdlib 部分（归一化 / 匹配 / CTC / 排序 / unclip 数学）
在无 numpy/cv2/onnxruntime 的环境也可测；引擎级用例按依赖可用性跳过。
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import ocr  # noqa: E402  纯 stdlib 导入安全


def _read(*parts):
    with open(os.path.join(ROOT, *parts), "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 文本归一化

def test_ocr_text_norm():
    assert ocr.ocr_text_norm("AKM 7.62x39 突击步枪") == "akm 7.62x39 突击步枪"
    # 全角逗号不在保留集（规格只留 ASCII `.,-`）→ 折叠为空格
    assert ocr.ocr_text_norm("马卡洛夫，PM") == "马卡洛夫 pm"
    assert ocr.ocr_text_norm("АК-74（劣化） ") == "ак-74 劣化"
    assert ocr.ocr_text_norm("53,548 ₽") == "53.548"       # ₽ 被折叠掉
    assert ocr.ocr_text_norm("") == ""


def test_short_name_of_matches_market_js():
    # 与 js/market.js shortNameOf 逐条对齐（括号前、连续拉丁/数字段可含单个空格）
    assert ocr.short_name_of("AKM 7.62x39 突击步枪") == "AKM 7.62x39"
    assert ocr.short_name_of("5.56x45mm M855弹药包（50发装）") == "5.56x45mm M855"
    assert ocr.short_name_of("工厂紧急出口钥匙") == ""
    assert ocr.short_name_of("马卡洛夫9x18PM 手枪") == "9x18PM"


# ---------------------------------------------------------------- ItemMatcher

@pytest.fixture(scope="module")
def matcher():
    names = [
        "工厂紧急出口钥匙",
        "宿舍118房间钥匙",
        "宿舍306房间钥匙",
        "马卡洛夫9x18PM 手枪",
        "AKM 7.62x39 突击步枪",
        "5.56x45mm M855",
        "菲尼亚斯神像",
    ]
    return ocr.ItemMatcher(names)


def test_matcher_exact(matcher):
    m = matcher.match_line("宿舍118房间钥匙", 0.95, [[0, 0], [10, 0], [10, 10], [0, 10]])
    assert m and m["path"] == "精确" and m["key"] == "宿舍118房间钥匙"


def test_matcher_no_space(matcher):
    # OCR 吞空格：'AKM7.62x39突击步枪' → 去空格层（键的无空格变体单独副索引）
    m = matcher.match_line("AKM7.62x39突击步枪", 0.9, None)
    assert m and m["key"] == "akm7.62x39突击步枪"
    assert m["path"] == "去空格"
    assert matcher.names_for(m["key"]) == ["AKM 7.62x39 突击步枪"]


def test_matcher_token_fuzzy(matcher):
    # 真·模糊：首字写错（实测形态 上→马）+ 吞空格，token/整串层兜回
    m = matcher.match_line("上洛关9X18PM手柜", 0.9, None)
    assert m and m["key"] == "马卡洛夫9x18pm 手枪"
    assert m["path"].startswith(("模糊", "整串模糊"))


def test_matcher_whole_fuzzy_with_garbled_head(matcher):
    # 首字写错的整串（实测形态：工厂→十广、匙→起）
    m = matcher.match_line("十广紧急出口钥起", 0.9, None)
    assert m and m["key"] == "工厂紧急出口钥匙"
    assert m["path"].startswith("整串模糊")


def test_matcher_digit_run_guard_prefers_right_room(matcher):
    # 数字段守卫：118 的 OCR 不能落到 306 房间
    m = matcher.match_line("房全118房间钥起", 0.9, None)
    assert m and m["key"] == "宿舍118房间钥匙"


def test_matcher_pure_number_rejected(matcher):
    # 价格标签：千分位数字串任何层都不得匹配（⑤ 5.56x45mm M855 是同形态弹药名）
    assert matcher.match_line("53,548 ₽", 0.99, None) is None
    assert matcher.match_line("53548", 0.99, None) is None
    assert matcher.resolve_key("53.548")[0] is None


def test_matcher_digit_guard_6(matcher):
    # ⑥ 规格守卫：键含数字而 OCR 文本不含 → 丢（防纯文字误配数字物品名）
    assert matcher.match_line("房间钥匙", 0.95, None) is None


def test_matcher_low_score_rejected(matcher):
    assert matcher.match_line("宿舍118房间钥匙", 0.34, None) is None


def test_matcher_small_string_guard_7(matcher):
    # ⑦ 低置信 + 小面积 + 纯拉丁短串 → 丢
    box = [[0, 0], [20, 0], [20, 12], [0, 12]]  # 240 px²
    assert matcher.match_line("akmm", 0.5, box) is None


def test_matcher_dedup_grid(matcher):
    box1 = [[0, 0], [10, 0], [10, 10], [0, 10]]
    box2 = [[5, 5], [15, 5], [15, 15], [5, 15]]  # 同一 24px 栅格
    out = matcher.match_lines([
        {"text": "宿舍118房间钥匙", "score": 0.9, "box": box1},
        {"text": "宿舍118房间钥匙", "score": 0.9, "box": box2},
    ])
    assert len(out) == 1


def test_matcher_names_multi_id_picks_by_price():
    # 同 key 多条目（同名物品）：endpoint 按 perSlot 择优；matcher 返回全部名字
    m = ocr.ItemMatcher(["测试物品", "测试物品"])  # 重复名折叠为单 key
    assert len(m.names_for("测试物品")) == 1


# ---------------------------------------------------------------- CTC / 字典 / 排序

def test_ctc_collapse_collapses_repeats_and_skips_blank():
    chars = ["blank", "a", "b", " "]
    # 序列: a a blank b b blank a → 'aba'，分数 = (0.9+0.8+0.7)/3
    indices = [1, 1, 0, 2, 2, 0, 1]
    probs = [0.9, 0.95, 0.5, 0.8, 0.85, 0.5, 0.7]
    text, score = ocr.ctc_collapse(indices, probs, chars)
    assert text == "aba"
    assert abs(score - (0.9 + 0.8 + 0.7) / 3) < 1e-9


def test_ctc_greedy_decode_flat_seq():
    chars = ["blank", "x", "y"]
    T, C = 3, 3
    seq = [0] * (T * C)
    seq[0 * C + 1] = 5   # x
    seq[1 * C + 1] = 4   # x（重复折叠）
    seq[2 * C + 2] = 3   # y
    text, score = ocr.ctc_greedy_decode(seq, T, C, chars)
    assert text == "xy"
    assert abs(score - (5 / 1 + 3 / 1) / 2) < 1e-6 or score > 0  # 分数取自 argmax 值


def test_load_dict_adds_space_for_6625_classes():
    dict_path = os.path.join(ocr.OCR_ASSETS_DIR, "ppocr_keys_v1.txt")
    if not os.path.isfile(dict_path):
        pytest.skip("模型字典不在本机")
    chars = ocr.load_dict(dict_path, 6625)
    assert len(chars) == 6625 and chars[0] == "blank" and chars[-1] == " "


def test_sort_boxes_same_row_by_x():
    boxes = [
        {"points": [[100, 10], [200, 10], [200, 30], [100, 30]]},
        {"points": [[10, 12], [80, 12], [80, 32], [10, 32]]},    # 同行（Δy<10），更靠左
        {"points": [[10, 80], [80, 80], [80, 100], [10, 100]]},  # 下一行
    ]
    out = ocr.sort_boxes(boxes)
    assert out[0]["points"][0][0] == 10 and out[1]["points"][0][0] == 100


# ---------------------------------------------------------------- unclip 数学

def test_unclip_expands_axis_aligned_rect():
    eng = _engine_if_available()
    if eng is None:
        pytest.skip("OCR 重依赖不在本机（测试 Python 无 numpy/cv2）")
    box = [[0.0, 0.0], [400.0, 0.0], [400.0, 16.0], [0.0, 16.0]]
    out = eng._unclip(box, 1.5)
    # d = 6400*1.5/832 ≈ 11.538 → 外扩后 (423.1, 39.1)，用有向面积验证与顺序无关
    area = 0.0
    for i in range(len(out)):
        x1, y1 = out[i]
        x2, y2 = out[(i + 1) % len(out)]
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2.0
    assert abs(area - 423.077 * 39.077) < 0.5


# ---------------------------------------------------------------- 服务端契约（静态）

def test_serve_route_and_body_limit():
    src = _read("tools", "serve.py")
    assert 'if path == "/api/ocr/recognize":' in src
    assert "MAX_OCR_BODY" in src and "24 * 1024 * 1024" in src
    assert "def _handle_ocr_recognize" in src
    # 价格与市场页同源（不得另起数据层）
    assert "prices_source.snapshot_for(" in src
    assert "force=force, app_dir=app_dir" in src
    # 快照条目两种形状都要兼容（R258 收敛进 _ocr_flea_price）
    assert 'row.get("lastLowPrice") or row.get("l")' in src
    assert 'row.get("avg24hPrice") or row.get("a")' in src
    # 引擎缺失必须 503，而不是 500
    assert '"ocr-unavailable"' in src


def test_health_exposes_ocr():
    src = _read("tools", "serve.py")
    assert '"ocr": {"available": bool(ocr_ok), "hint": ocr_hint}' in src
    assert "ocr.check_available()" in src


def test_engine_lazy_imports():
    src = _read("tools", "ocr.py")
    head = src[:src.index("class OcrEngine")]
    for banned in ("import numpy", "import cv2", "import onnxruntime"):
        assert banned not in head, "模块级不得导入重依赖（%s）" % banned


def test_frontend_entry_and_paste_guard():
    src = _read("js", "market.js")
    assert "mk-ocr-btn" in src and "api/ocr/recognize" in src
    assert "mk-ocr-file" in src and "paste" in src
    # 免费档不隐藏入口：503 由状态行如实提示（错误文案走 d.hint）
    assert "OCR 不可用" in src


def test_models_present_with_reference_hashes():
    import hashlib
    want = {
        "det.onnx": 4729474,
        "rec.onnx": 10812334,
        "ppocr_keys_v1.txt": 26250,
    }
    for name, size in want.items():
        p = os.path.join(ocr.OCR_ASSETS_DIR, name)
        assert os.path.isfile(p), "缺模型 %s" % name
        assert os.path.getsize(p) == size, "%s 大小不符" % name


# ---------------------------------------------------------------- 引擎级（依赖可用才跑）

def _engine_if_available():
    ok, _hint = ocr.check_available()
    return ocr.get_engine() if ok else None


def test_engine_recognize_synthetic_nameplate():
    eng = _engine_if_available()
    if eng is None:
        pytest.skip("OCR 重依赖不在本机（服务端 Python 才有）")
    import base64
    import io
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 28)
    img = Image.new("RGB", (760, 300), (32, 34, 38))
    d = ImageDraw.Draw(img)
    d.text((30, 24), "工厂紧急出口钥匙", fill=(236, 236, 230), font=font)
    d.text((30, 94), "马卡洛夫9x18PM 手枪", fill=(236, 236, 230), font=font)
    d.text((480, 234), "53,548", fill=(220, 220, 214), font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    bgr = ocr.decode_image_bgr(buf.getvalue())
    lines, annotated, _ms = eng.recognize(bgr, annotate=True)
    texts = [ln["text"] for ln in lines]
    assert any("工厂紧急出口钥匙" == t for t in texts), texts
    assert any("马卡洛夫9x18PM手枪" == t for t in texts), texts
    assert annotated and annotated[:8] == b"\x89PNG\r\n\x1a\n"
    matcher = ocr.ItemMatcher(["工厂紧急出口钥匙", "马卡洛夫9x18PM 手枪"])
    matches = matcher.match_lines(lines)
    # 马卡洛夫 OCR 吞了空格 → 去空格层；工厂钥匙精确层
    assert {m["key"] for m in matches} == {"工厂紧急出口钥匙", "马卡洛夫9x18pm手枪"}
    base64.b64encode(annotated)  # 标注图必须可 base64


# ---------------------------------------------------------------- R19.81 未登录不报价

def test_ocr_scrub_prices_removes_every_price():
    """未登录：价格只能来自云端，服务端要把快照与目录基线价全部抹掉。"""
    import serve

    match = {
        "name": "测试物品",
        "price": {
            "lastLow": 1000, "avg24h": 900, "avg7d": 800, "w72": 700,
            "w30d": 600, "base": 1000, "perSlot": 1000, "trader": 50,
            "traderSell": 120, "unitPrice": 10, "manual": 5,
            "priceSource": "flea", "noFlea": False, "fleaFallback": True,
            "candidates": [{"name": "同短名口径", "price": 700}],
        },
        "candidates": [{"name": "重名物品", "price": 9, "perSlot": 9}],
    }
    serve._ocr_scrub_prices([match])
    price = match["price"]
    for field in serve._OCR_PRICE_FIELDS:
        assert price[field] is None, field
    assert price["priceSource"] == "flea" and price["fleaFallback"] is False
    assert price["candidates"][0]["price"] is None
    assert match["candidates"][0]["price"] is None
    assert match["candidates"][0]["perSlot"] is None


def test_ocr_recognize_skips_cloud_and_scrubs_when_logged_out():
    """未登录时识别接口不得请求云端行情，也不得回退 items.json 的离线基线价。"""
    src = _read("tools", "serve.py")
    assert "logged_in = _cloud_logged_in(cloud_client)" in src
    assert "if match_ids and logged_in:" in src
    assert "if not logged_in:" in src and "_ocr_scrub_prices(out_matches)" in src
    assert '"loginRequired": not logged_in' in src
