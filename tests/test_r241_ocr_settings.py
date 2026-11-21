# -*- coding: utf-8 -*-
"""R241：价格识别设置面板 + 档位样式标签。

用户需求（2026-11-11 18:33）：
  「价格显示在我大概框蓝框的位置（装备名上）；只显示价格和单格价格，不要 kg；
   字体大小和游戏内装备上的字体一样大（各玩家分辨率不同 → 用 OCR 实测的
   文字像素高 × 档位倍率，比解包静态值更准）；菜单栏小地图按钮右侧加价格识别
   按钮：免费用户只能设置截图键，会员可按价格档位自定义字号/字体/颜色/内外描边/区间」
"""

import os
import sys

import pytest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import config  # noqa: E402
import scan  # noqa: E402


@pytest.fixture()
def no_member():
    config.set_member_state({"member": False})
    yield
    config.set_member_state({"member": False})


# ---------------------------------------------------------------- config.ocrScan

def test_ocr_scan_defaults():
    cfg = config.default_config()
    ocr = cfg["ocrScan"]
    assert ocr["hotkey"] == "ctrl+alt+p"
    tiers = ocr["labelStyle"]["tiers"]
    assert len(tiers) == 4
    assert tiers[-1]["max"] is None                      # 末档无上限
    assert [t["max"] for t in tiers[:3]] == [50000, 300000, 1000000]
    assert all(t["outer"] and not t["inner"] for t in tiers)
    assert tiers[3]["color"] == "#f2c14e"


def test_ocr_scan_normalize_coerces_dirty_input():
    raw = {"hotkey": "F8", "labelStyle": {"tiers": [
        {"max": "200000", "color": "not-a-color", "sizeScale": "1.5", "font": "SIMHEI"},
        {"max": 100000, "color": "#FF0000", "sizeScale": 9.0},
        {"max": None, "color": "#00ff00"},
    ]}}
    ocr = config._normalize_ocr_scan(raw)
    assert ocr["hotkey"] == "f8"
    tiers = ocr["labelStyle"]["tiers"]
    assert len(tiers) == 3
    # 排序：有上限按值升序，无上限殿后；脏色回退**该行索引**的默认档色；越界倍率钳位
    assert [t["max"] for t in tiers] == [100000, 200000, None]
    assert tiers[0]["color"] == "#ff0000" and tiers[0]["sizeScale"] == 3.0
    assert tiers[0]["font"] == "msyhbd"                  # 未指定字体 → 默认
    assert tiers[1]["color"] == "#b9c0c9" and tiers[1]["font"] == "simhei"
    assert tiers[2]["color"] == "#00ff00"


def test_merge_ui_member_gating(no_member, tmp_path):
    """免费用户：热键可改，labelStyle 手搓请求被剥离（UI 锁之外的服务端兜底）。"""
    cfg = config.load(str(tmp_path))
    styled = {"tiers": [{"max": 1, "color": "#123456", "sizeScale": 2.0, "font": "simhei",
                         "outer": False, "outerColor": "#111111",
                         "inner": True, "innerColor": "#222222"}]}
    merged = config.merge_ui(cfg, {"ocrScan": {"hotkey": "f8", "labelStyle": styled}})
    assert merged["ocrScan"]["hotkey"] == "f8"
    assert merged["ocrScan"]["labelStyle"]["tiers"] == config.OCR_SCAN_TIERS_DEFAULT, \
        "非会员传入的 labelStyle 必须被丢弃"


def test_merge_ui_member_can_set_label_style(tmp_path):
    config.set_member_state({"member": True, "member_status": "active"})
    try:
        cfg = config.load(str(tmp_path))
        styled = {"tiers": [{"max": 700000, "color": "#123456", "sizeScale": 1.4, "font": "simsun",
                             "outer": False, "outerColor": "#111111",
                             "inner": True, "innerColor": "#222222"},
                            {"max": None, "color": "#ffcc00", "sizeScale": 1.0, "font": "msyhbd",
                             "outer": True, "outerColor": "#000000",
                             "inner": False, "innerColor": "#000000"}]}
        merged = config.merge_ui(cfg, {"ocrScan": {"labelStyle": styled}})
        tiers = merged["ocrScan"]["labelStyle"]["tiers"]
        assert tiers[0]["color"] == "#123456" and tiers[0]["sizeScale"] == 1.4
        assert tiers[0]["inner"] is True and tiers[0]["outer"] is False
    finally:
        config.set_member_state({"member": False})


# ---------------------------------------------------------------- 标签渲染

def test_tier_for_selection():
    tiers = config.OCR_SCAN_TIERS_DEFAULT
    assert scan._tier_for(tiers, 9000)["color"] == "#b9c0c9"
    assert scan._tier_for(tiers, 120000)["color"] == "#f2f2ee"
    assert scan._tier_for(tiers, 400000)["color"] == "#7fd48a"
    assert scan._tier_for(tiers, 5000000)["color"] == "#f2c14e"
    assert scan._tier_for(tiers, None) == tiers[0]       # 价格未知落第一档
    assert scan._tier_for(tiers, 500001)["color"] == "#7fd48a"
    assert scan._tier_for(tiers, 1000001)["color"] == "#f2c14e"


def test_render_labels_two_lines_no_kg_anchored_at_bbox():
    """R244 版式：第 1 行留空（装备名那一行），第 2 行整体价、第 3 行单格价，无 kg。"""
    sys.path.insert(0, TOOLS)
    m = {"text": "工厂紧急出口钥匙", "x": 0, "y": 0, "w": 180, "h": 30,
         "gw": 1, "gh": 1, "weight": 0.01,
         "price": {"lastLow": 400000, "avg24h": 400000}}
    img = scan.render_labels(800, 400, [m], "last", config.OCR_SCAN_TIERS_DEFAULT)

    def row_ink(y, x_hi=300):
        return any(img.getpixel((x, y))[3] > 0 for x in range(0, x_hi, 2))

    # 第 1 行（装备名自身那一行）必须完全空着——价格不再压名字
    assert not any(row_ink(y) for y in range(0, 28, 2)), "装备名所在行不应有价格墨迹"
    # 第 2 行（整体价）从 h+gap=33 起笔；第 3 行（单格价）紧跟其下
    assert row_ink(40) and row_ink(55), "整体价应在装备名下方（第 2 行）"
    assert row_ink(70) and row_ink(85), "单格价应在第 3 行"
    # 档位色（绿 #7fd48a）应出现在整体价字芯里
    greens = 0
    for y in range(36, 62):
        for x in range(0, 200):   # R249：价格右对齐后整体左移，取样窗口覆盖整行
            p = img.getpixel((x, y))
            if p[3] > 200 and p[1] > 150 and p[1] > p[0] + 30:
                greens += 1
    assert greens > 5, "主价应按档位色渲染（绿档）"
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    body = src[src.index("def render_labels"):src.index("def render_control")]
    assert "kg" not in body, "标签里不应再有公斤价"


def test_render_labels_font_size_follows_game_text():
    """字号跟随 OCR 实测文字像素高（R249：bh=30 → 整体价 0.80×30=24px，
    再按单格宽度全局收缩；仍保留「名字下方两行」的版式契约）。"""
    sys.path.insert(0, TOOLS)
    m = {"x": 0, "y": 0, "w": 200, "h": 30, "gw": 1, "gh": 1,
         "price": {"lastLow": 400000}}
    img = scan.render_labels(900, 400, [m], "last", config.OCR_SCAN_TIERS_DEFAULT)

    def row_has_ink(y):
        return any(img.getpixel((x, min(y, img.height - 1)))[3] > 0 for x in range(0, 260, 3))

    assert row_has_ink(40) and row_has_ink(55), "整体价应在名字下方（h+gap 起笔，约 30px 高）"
    assert row_has_ink(70) and row_has_ink(85), "单格价在第三行（约 33+30 处起笔）"


# ---------------------------------------------------------------- 契约

def test_scan_host_settings_contract():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "def load_label_tiers" in src and "_tier_for" in src
    assert "OverlaySession(region, matches, config_dir, server=server)" in src
    assert "热键已切换为" in src and "UnregisterHotKey" in src   # 热键热更新
    assert 'from config import OCR_SCAN_TIERS_DEFAULT' in src


def test_page_settings_contract():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'id="app-sec-ocr"' in html and ">价格识别</button>" in html
    assert 'id="ocr-hotkey"' in html and 'id="ocr-tiers"' in html
    assert html.index("am-mini-panel") < html.index("am-ocr-panel"), "价格识别在小地图设置之后"
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    for marker in ("function applyOcrSettings", "function collectOcrTiers",
                   "function bindOcrSettings",
                   "queuePrefs({ ocrScan: { labelStyle: { tiers: collectOcrTiers() } } })",
                   "isMember()"):
        assert marker in js, "app.js 缺 %s" % marker
    # R254：热键改为游戏式按键记录（按钮 + keydown 捕获 + 强制修饰键）
    for marker in ("hkOnKey", 'queuePrefs({ ocrScan: { hotkey: text } })',
                   'hkError("须含 Ctrl/Alt/Shift（避免占用游戏键）")',
                   'e.key === "Escape"'):
        assert marker in js, "app.js 缺 R254 热键记录 %s" % marker


def test_config_contract():
    src = open(os.path.join(TOOLS, "config.py"), encoding="utf-8").read()
    assert "OCR_SCAN_DEFAULTS" in src and "_normalize_ocr_scan" in src
    assert "cfg[\"ocrScan\"] = _normalize_ocr_scan(raw.get(\"ocrScan\"))" in src
    assert 'merged["ocrScan"] = base' in src and "labelStyle" in src
