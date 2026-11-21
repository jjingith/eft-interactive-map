# -*- coding: utf-8 -*-
"""R231/R232：所有表格滚动区都不再用小位图 `fill` 拉伸。

用户原话（2026-11-10 20:41 / 21:16）：
  「我发现把所有子弹隐藏后 子弹页面背后的背景好像是什么图强行放大后的样子 请改掉」
  「你检查一下 我发现好几个地方都会有而是表格滚动区的边框位图被放大」

R231 只修了弹药页；R232 排查发现同类问题遍布多处：
  - `table-frame.png`(64×64) `2 fill / 2px stretch` → 配装 / 枪匠 / 隐藏模板 .tbl-scroll
  - `groupbox.png`(280×154) `6 fill / 2px stretch` → 通用 `html body .tbl-scroll`
两条 fill 规则都从源头摘掉，所有 .tbl-scroll 回落到 style.css / theme 的
纯色底 + 1px 实线。工作台外壳的 menu-panel-bg.png 是另一类面板底板，不动。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _decl(*parts: str) -> str:
    """剥掉注释，只留 CSS 声明（注释为解释原因会提到被禁的关键词）。"""
    return re.sub(r"/\*.*?\*/", "", _read(*parts), flags=re.S)


def test_no_table_frame_bitmap_anywhere():
    """table-frame.png 不能再出现在任何 CSS 声明里（注释里可以提）。"""
    decl = _decl("assets", "xp-ui", "xp-ui-app.css")
    assert "table-frame.png" not in decl
    assert 'url("table-frame.png") 2 fill' not in decl


def test_generic_tbl_scroll_removed_from_groupbox_rule():
    """15.2 那组 groupbox.png fill 规则里不能再含 .tbl-scroll。"""
    css = _read("assets", "xp-ui", "xp-ui-app.css")
    i = css.index("html body #lw-cost,")
    seg = css[i:css.index("/* --- 15.3", i)]
    assert 'url("groupbox.png") 6 fill / 2px stretch' in seg  # 其它成员保持
    assert ".tbl-scroll" not in re.sub(r"/\*.*?\*/", "", seg, flags=re.S)


def test_no_tbl_scroll_rule_has_fill_bitmap():
    """任何以 .tbl-scroll 为目标的规则块都不能带 fill 位图。"""
    css = _decl("assets", "xp-ui", "xp-ui-app.css")
    for m in re.finditer(r"([^{}]*\.tbl-scroll[^{}]*)\{([^{}]*)\}", css):
        sel, body = m.group(1), m.group(2)
        # 滚动条轨道 / 滑块自己有九宫格位图，不是表格主体，跳过
        if "::" in sel:
            continue
        # 只管「.tbl-scroll 本身」；`.tbl-scroll .tbl-head` 这类子元素的
        # 1px 九宫格是刻意的 XP 表头皮肤（R96），且高度只有 20~32px，不在本轮范围
        targets = [s.strip() for s in sel.split(",") if s.strip()]
        if not any(s.endswith(".tbl-scroll") for s in targets):
            continue
        if "border-image" in body:
            assert "fill" not in body, "表格滚区仍有 fill 位图：%s" % sel.strip()[-120:]
            assert "stretch" not in body, "表格滚区仍有 stretch 位图：%s" % sel.strip()[-120:]


def test_ammo_still_forces_flat_border():
    """弹药页 style.css 写了 border:0，必须留这条 !important 压住。"""
    css = _read("assets", "xp-ui", "xp-ui-app.css")
    i = css.index("html body .am-workbench .am-table .tbl-scroll")
    seg = css[i:css.index("}", i)]
    assert "border: 1px solid var(--xp-border-dark" in seg
    assert "background-color: #fff !important" in seg
    assert seg.count("!important") >= 2
    assert "border-image" not in seg
    # 基础层仍在
    assert ".am-workbench .am-table .tbl-scroll" in _read("style.css")


def test_style_css_base_tbl_scroll_is_flat():
    """通用 .tbl-scroll 回落到 style.css 的纯色 + 1px 实线。"""
    css = _read("style.css")
    i = css.index("\n.tbl-scroll {")
    seg = css[i:css.index("}", i)]
    assert "background: var(--ui-color-surface-raised)" in seg
    assert "border: 1px solid var(--xp-input)" in seg
    assert "border-image" not in seg


def test_theme_workbench_views_are_flat():
    """配装 / 枪匠 / 弹药在 theme 里本来就是白底 + 1px（回落到它）。"""
    xp = _read("theme-windows-xp.css")
    for sel in ("html .loadout-workbench .tbl-scroll,", "html .am-workbench .tbl-scroll"):
        i = xp.index(sel)
        seg = xp[i:i + 220]
        assert "background: #ffffff" in seg
        assert "border: 1px solid var(--xp-border-dark)" in seg


def test_workbench_shell_bitmap_left_alone():
    """工作台外壳的 menu-panel-bg.png 是四个工作台共用的面板底板，
    实测关掉它空态截图无变化，不属于表格滚区，本轮不动。"""
    css = _read("assets", "xp-ui", "xp-ui-app.css")
    i = css.index("/* --- 15.3 工作台外壳")
    seg = css[i:i + 420]
    assert "html body #am-workbench" in seg
    assert 'url("menu-panel-bg.png") 12 fill / 1px stretch' in seg
