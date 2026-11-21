# -*- coding: utf-8 -*-
"""R259：两个设置回归修复。

用户反馈（2026-11-12）：
  「现在全屏识别的勾 勾不上 然后价格的颜色显示没生效」

A. 全屏识别勾不上：`merge_ui` 只拷了 hotkey / labelStyle，漏了 `fullScreen`，
   保存后回声把 fullScreen 又变回 false → 勾选被弹回。
B. 价格颜色没生效：`load_label_tiers` 在截图宿主进程里调 `config.is_member()`，
   独立进程永远 False → 恒返灰白单档。改为接收 OverlaySession 从 BFF 拉到的
   跨进程会员态；并让 `_normalize_ocr_scan` 保留 `tierBasis`（否则配色依据丢失）。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import config  # noqa: E402
import scan  # noqa: E402


# ---------------------------------------------------------------- A. 全屏识别

def test_merge_ui_keeps_fullscreen_true():
    cfg = config.default_config()
    merged = config.merge_ui(cfg, {"ocrScan": {"fullScreen": True}})
    assert merged["ocrScan"]["fullScreen"] is True


def test_merge_ui_keeps_fullscreen_false():
    cfg = config.default_config()
    cfg["ocrScan"]["fullScreen"] = True
    merged = config.merge_ui(cfg, {"ocrScan": {"fullScreen": False}})
    assert merged["ocrScan"]["fullScreen"] is False


def test_fullscreen_survives_normalize_roundtrip():
    cfg = config.default_config()
    cfg["ocrScan"]["fullScreen"] = True
    assert config.normalize(cfg)["ocrScan"]["fullScreen"] is True


# ---------------------------------------------------------------- B1. tierBasis

def test_normalize_default_tier_basis_overall():
    out = config._normalize_ocr_scan(None)
    assert out["labelStyle"]["tierBasis"] == "overall"


def test_normalize_keeps_tier_basis():
    out = config._normalize_ocr_scan({
        "labelStyle": {"tiers": [{"max": 1000, "color": "#ff0000"}],
                       "tierBasis": "perslot"}})
    assert out["labelStyle"]["tierBasis"] == "perslot"


def test_member_merge_keeps_tier_basis_when_only_tiers_sent():
    """改档位颜色时前端只发 tiers，不应把已选的 tierBasis 冲掉。"""
    config.set_member_state({"member": True})
    cfg = config.normalize(config.default_config())
    cfg["ocrScan"]["labelStyle"]["tierBasis"] = "perslot"
    tiers = cfg["ocrScan"]["labelStyle"]["tiers"]
    merged = config.merge_ui(cfg, {"ocrScan": {"labelStyle": {"tiers": tiers}}})
    assert merged["ocrScan"]["labelStyle"]["tierBasis"] == "perslot"
    assert config.normalize(merged)["ocrScan"]["labelStyle"]["tierBasis"] == "perslot"


# ---------------------------------------------------------------- B2. 档位颜色成员门控

def test_load_label_tiers_member_gets_colored_tiers():
    tiers = scan.load_label_tiers(None, member=True)
    assert len(tiers) > 1, "会员应拿到多档彩色档位（不是灰白单档）"


def test_load_label_tiers_non_member_gets_grey_single():
    tiers = scan.load_label_tiers(None, member=False)
    assert len(tiers) == 1
    assert tiers[0] is scan._OCR_MEMBER_GREY_TIERS[0] or tiers[0] == scan._OCR_MEMBER_GREY_TIERS[0]


def test_overlay_passes_member_into_load_label_tiers():
    """宿主渲染必须把跨进程会员态传进去（self.member），否则颜色恒灰白。"""
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert "load_label_tiers(self._config_dir, member=self.member)" in src
    assert "self.member = fetch_member_state(server, config_dir)" in src


def test_config_source_keeps_fullscreen_and_tier_basis():
    src = open(os.path.join(TOOLS, "config.py"), encoding="utf-8").read()
    assert 'base["fullScreen"] = ocr["fullScreen"]' in src
    assert 'out["labelStyle"]["tierBasis"] = ls["tierBasis"]' in src
