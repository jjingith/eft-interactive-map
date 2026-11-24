# -*- coding: utf-8 -*-
"""R303：读取行情时的可见加载动画。

启动/切换模式首次拉行情时，价格徽标从静态「正在读取行情…」改为
带旋转指示器的动画，并在 title 里说明"本地有缓存直接复用，不重复下载"。
已有缓存且模式相同则不进入 loading（瞬间返回，不闪动画）。

不变量：
1. priceSourceInfo 在 loading 时返回 loading:true 与明确文案；
2. renderPriceSourceBadge 依据 info.loading 加 is-loading class；
3. CSS 有 is-loading 的旋转/呼吸动画，且尊重 prefers-reduced-motion；
4. 缓存命中路径不设 phase=loading（不闪无意义动画）。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPJS = ROOT / "app.js"
STYLE = ROOT / "style.css"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_appjs_loading_flag_and_animation_class():
    js = read(APPJS)
    assert "loading: true" in js
    assert "is-loading" in js
    assert 'info.loading ? " is-loading" : ""' in js
    assert "正在从云端读取行情" in js
    assert "本地有缓存时直接复用，不会重复下载" in js


def test_cache_hit_does_not_set_loading():
    js = read(APPJS)
    # phase="loading" 只在 payload 缺失或模式不符时设置
    needle = 'if (!state.priceSnap.payload || state.priceSnap.payload.mode !== mode) {\n      state.priceSnap.phase = "loading";'
    assert needle in js


def test_css_animation_and_reduced_motion():
    css = read(STYLE)
    assert ".price-source-badge.is-pending.is-loading::before" in css
    assert "@keyframes mk-spin" in css
    assert "@keyframes mk-blink" in css
    assert "prefers-reduced-motion: reduce" in css
