# -*- coding: utf-8 -*-
"""R303：截图识别里「重名物资」的「?」标从不可交互改为可点选。

用户反馈：OCR 结果里重名物资确实有「?」标，但点了没反应（只有 hover tooltip）。
根因：两个「?」（price.ambiguous 弹药口径 / m.ambiguous 物品撞名）都只设了 title，
没有任何 click 监听。

修复：
1. 服务端候选补齐 id / detail（完整价格）/ 格数 / 短名，使切换后价格与每格价正确；
   弹药候选此前**没有 id**，无法定向切换。
2. 前端「?」加 role=button + tabIndex + click/keydown → 弹候选菜单；
   选中后替换 match 的 id/name/price/gw/gh，重绘整表并保留已选标记。
3. 菜单支持点击外部 / Esc 关闭，再点同一个「?」收起。

不变量：
- 候选必须带 id（可切换）与 detail（价格三档不丢）；
- 「?」可聚焦、可键盘触发；
- 切换后 userPickedId 记录，重绘仍显示「?」但标为已选（可改选）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / "tools" / "serve.py"
MARKET = ROOT / "js" / "market.js"
CSS = ROOT / "styles" / "market-dark.css"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_server_candidates_have_id_and_detail():
    src = read(SERVE)
    # _ocr_name_collision 的 cand
    assert '"detail": price}' in src or '"detail": price' in src
    # 两处候选都补了 id
    assert src.count('"id": iid, "name"') >= 2
    # 弹药候选补了 detail 与格数
    idx = src.index("def _ocr_ambig_candidates")
    seg = src[idx:idx + 1600]
    assert '"detail": price' in seg
    assert '"perSlot": price.get("perSlot")' in seg
    assert '"gw": rec.get("gw")' in seg


def test_market_js_ambig_is_clickable():
    js = read(MARKET)
    # 两处「?」都要可点
    assert js.count('mk-ocr-ambig') >= 2
    assert js.count("ocrOpenCandMenu(e, node, list, m)") >= 2
    assert js.count('setAttribute("role", "button")') >= 2
    assert js.count("tabIndex = 0") >= 2
    # 键盘可达
    assert js.count('e.key === "Enter"') >= 2


def test_market_js_menu_helpers():
    js = read(MARKET)
    assert "function ocrOpenCandMenu(" in js
    assert "function ocrCloseCandMenu(" in js
    assert "function ocrApplyCandidate(" in js
    # 关闭方式：点外部 / Esc
    assert "mousedown" in js and "ocrCandMenuOutside" in js
    assert 'ev.key === "Escape"' in js
    # 选择后重绘
    assert "ocrRenderResult(ocrState.lastResult)" in js
    # 已选标记
    assert "is-picked" in js
    assert "userPickedId" in js


def test_apply_candidate_maps_price_fields():
    js = read(MARKET)
    idx = js.index("function ocrApplyCandidate(")
    seg = js[idx:idx + 1600]
    assert "m.id = cand.id" in seg
    assert "m.price = cand.detail" in seg
    # 缺 detail 时按 kind 还原三档价格
    assert 'priced.traderSell = amount' in seg
    assert 'priced.trader = amount' in seg
    # 弹药形态跟随切换
    assert 'cand.kind === "loose"' in seg and 'm.ammoKind = cand.kind' in seg


def test_css_has_interactive_styles():
    css = read(CSS)
    assert ".mk-ocr-ambig" in css
    assert "cursor: pointer" in css
    assert ".mk-ocr-cand-menu" in css
    assert ".mk-ocr-cand-item" in css
    assert "z-index" in css
