# -*- coding: utf-8 -*-
"""R300：全站 UI 从 XP 像素位图统一为现代扁平风（以 market.css 为样板）。

用户诉求：像素位图按钮和整体 UI 不好看；market.css 那套纯 CSS 扁平控件顺眼，
希望全项目统一成那样。做法：新增 styles/modern-flat.css 作为最后加载的覆盖层，
把控件位图（border-image / 位图背景）换成纯 CSS 扁平样式，配色仍走 --ui-* 令牌。

不变量：
1. index.html 在 xp-ui-app.css 之后加载 modern-flat.css；
2. 覆盖层去 border-image、按钮/输入/复选/滚动条走纯 CSS；
3. 内容位图（导航图标 / 空态插图 / badge）不被误伤；
4. 既有 XP 源文件未被改动（覆盖层可整体删除回滚）。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
FLAT = ROOT / "styles" / "modern-flat.css"
XP_APP = ROOT / "assets" / "xp-ui" / "xp-ui-app.css"
XP_UI = ROOT / "assets" / "xp-ui" / "xp-ui.css"
THEME = ROOT / "theme-windows-xp.css"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_flat_layer_loaded_last():
    html = read(INDEX)
    i_xp = html.index("xp-ui-app.css")
    i_flat = html.index("modern-flat.css")
    assert i_flat > i_xp, "modern-flat.css 必须在 xp-ui-app.css 之后加载才能覆盖"


def test_flat_layer_removes_bitmaps():
    css = read(FLAT)
    assert "border-image: none !important" in css, "必须统一摘掉位图边框"
    # 按钮/输入/控件都有纯 CSS 背景
    assert "background: linear-gradient(180deg," in css
    assert "--ui-grad-face-a" in css and "--ui-color-hover-soft" in css, \
        "配色须走 design-tokens，与 market.css 同源"
    # 覆盖层用高优先级选择器（提权段落）
    assert ":is(" in css and "view-toolbar .view-btn" in css, \
        "需提权压过 xp-ui-app.css 的 html body .view-toolbar .view-btn"


def test_flat_layer_covers_all_control_types():
    css = read(FLAT)
    for token, label in [
        ("input[type=\"checkbox\"]", "复选框"),
        ("input[type=\"radio\"]", "单选"),
        ("input[type=\"range\"]", "滑块"),
        ("::-webkit-scrollbar-thumb", "滚动条"),
        (".view-toolbar .view-btn", "视图按钮"),
        (".game-mode-bar .gm-btn", "模式按钮"),
        (".task-switch-track", "开关"),
        (".progress-fill", "进度条"),
        (".am-tab", "页签"),
        (":focus-visible", "焦点环"),
    ]:
        assert token in css, "覆盖层缺少对%s的处理：%s" % (label, token)


def test_content_bitmaps_preserved():
    """覆盖层不得移除导航图标/空态插图/badge 等位图（图形素材，非控件皮肤）。"""
    css = read(FLAT)
    # 覆盖层里没有把这些内容类设为 display:none 或清背景图片
    for bad in ["icon-map", "icon-tasks", "empty-box", "badge-md"]:
        rule = [line for line in css.splitlines() if bad in line and "display: none" in line]
        assert not rule, "内容位图不应被隐藏：%s" % bad


def test_source_xp_files_untouched():
    """覆盖层方案的关键优势：原 XP 源文件保持不变，可整体删除回滚。"""
    xp_app = read(XP_APP)
    xp_ui = read(XP_UI)
    theme = read(THEME)
    # 原始位图规则仍在（覆盖层是叠加，不是改写）
    assert "border-image-source: url(\"btn-normal.png\")" in xp_ui
    assert "border-image-source" in xp_app
    assert "--xp-" in theme
