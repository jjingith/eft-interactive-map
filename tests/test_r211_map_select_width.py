# -*- coding: utf-8 -*-
"""R211：地图下拉右缘与「图层」栏齐平；底图说明不再出现在界面上。

静态断言锁定三件事：宽度基准单一真源、下拉不再被 200px 限死、
底图说明的静态文案 / 运行时注入点 / 样式一并移除。
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XP_CSS = os.path.join("assets", "xp-ui", "xp-ui-app.css")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _rule(css: str, selector: str) -> str:
    """取某条规则的规则体（到第一个 } 为止），避免被别的规则误判。"""
    start = css.index(selector + " {")
    return css[start:css.index("}", start) + 1]


def test_sidebar_width_is_single_source_of_truth():
    css = _read("style.css")
    xp = _read(XP_CSS)
    assert "--eft-sidebar-w: 300px;" in css
    assert "width: var(--eft-sidebar-w);" in css
    assert "flex: 0 0 var(--eft-sidebar-w);" in css
    # 上下文栏有 2px 边框 + 6px 左内边距，分组宽度按同一变量减 8px 才能让右缘对齐
    assert "width: calc(var(--eft-sidebar-w, 300px) - 8px);" in xp


def test_map_select_is_not_clamped_to_200px():
    body = _rule(_read(XP_CSS), "html body .context-bar #map-list")
    assert "max-width: 200px" not in body
    assert "min-width: 150px" not in body
    assert "max-width: none;" in body
    assert "flex: 1 1 auto;" in body
    assert "min-width: 0;" in body


def test_narrow_screen_drops_the_fixed_alignment():
    xp = _read(XP_CSS)
    narrow = xp[xp.index("@media (max-width: 780px)"):]
    assert "section.block.cb-src-block { width: auto; }" in narrow
    # 自适应时仍要留够桌面档的 262px，否则最长地图名会贴边被裁
    assert "#map-list { min-width: 262px; }" in narrow


def test_base_map_note_is_gone():
    html = _read("index.html")
    js = _read("wiki-map.js")
    css = _read("style.css")
    xp = _read(XP_CSS)
    assert 'id="base-mode-note"' not in html
    assert "底图：矢量图" not in html
    assert "setNote(" not in js
    assert "el.note" not in js
    assert ".base-mode-note {" not in css
    # 迁上来的地图块不再为说明文字留 max-width / 省略号样式
    assert "section.block.cb-src-block > p" not in xp
