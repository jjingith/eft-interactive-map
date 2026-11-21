# -*- coding: utf-8 -*-
"""R257：价格档位面板字体微调 + 档位配色依据开关（整体价格 / 单格价格）。

- 前端：价格识别设置栏字体缩小、档位行改为竖排避免遮挡；新增「配色依据」单选，
  写回 ocrScan.labelStyle.tierBasis。
- 后端：render_labels 的档位选色使用 tier_price(m, mode, basis)，
  basis=perslot 时按 base/(gw*gh) 比价（显示数字仍用整体价）。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scan  # noqa: E402

TIERS = [
    {"max": 150000, "color": "#b9c0c9", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
    {"max": 400000, "color": "#7fd48a", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
    {"max": None, "color": "#f2c14e", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
]


def _match(price, gw=2, gh=1):
    return {
        "x": 100, "y": 100, "w": 80, "h": 22,
        "gw": gw, "gh": gh, "weight": 1.0,
        "price": {"lastLow": price, "avg24h": price, "avg7d": price},
    }


def test_tier_price_overall_returns_base():
    m = _match(200000)
    assert scan.tier_price(m, "last", "overall") == 200000


def test_tier_price_perslot_divides_by_slots():
    m = _match(200000, gw=2, gh=1)  # 2 格
    assert scan.tier_price(m, "last", "perslot") == 100000.0


def test_tier_price_perslot_falls_back_when_no_grid():
    m = _match(200000)
    del m["gw"]; del m["gh"]
    assert scan.tier_price(m, "last", "perslot") == 200000


def test_basis_changes_selected_tier_color():
    # 整体价 200k 落入中档；单格价 100k 落入低档——开关应改变选中的颜色。
    m = _match(200000, gw=2, gh=1)
    overall = scan._tier_for(TIERS, scan.tier_price(m, "last", "overall"))
    perslot = scan._tier_for(TIERS, scan.tier_price(m, "last", "perslot"))
    assert overall["color"] == "#7fd48a"
    assert perslot["color"] == "#b9c0c9"
    assert overall["color"] != perslot["color"]


def _with_fake_config(cfg_dict):
    class FakeCfg:
        def load(self, *a, **k):
            return cfg_dict
    saved = sys.modules.get("config")
    sys.modules["config"] = FakeCfg()
    try:
        yield
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_load_tier_basis_default_when_config_missing():
    class NoCfg:
        def load(self, *a, **k):
            raise RuntimeError("no config")
    saved = sys.modules.get("config")
    sys.modules["config"] = NoCfg()
    try:
        assert scan.load_tier_basis() == "overall"
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_load_tier_basis_reads_value():
    saved = sys.modules.get("config")
    sys.modules["config"] = type("C", (), {
        "load": lambda self, *a, **k: {"ocrScan": {"labelStyle": {"tierBasis": "perslot"}}}
    })()
    try:
        assert scan.load_tier_basis() == "perslot"
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_render_labels_accepts_tier_basis_kwarg():
    img1 = scan.render_labels(800, 400, [_match(200000, 2, 1)], "last", TIERS)
    img2 = scan.render_labels(800, 400, [_match(200000, 2, 1)], "last", TIERS,
                              tier_basis="perslot")
    assert img1 is not None and img2 is not None


def test_frontend_has_basis_toggle():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'name="ocr-tier-basis"' in html
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    assert "tierBasis: v" in js
