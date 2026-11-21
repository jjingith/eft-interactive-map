"""第一阶段：主导航与地图页结构。

用户确认的线框图（docs/ui-system/wireframes/main-nav-map-v1.html）：
  · 工作区导航常驻顶栏；
  · 文件 / 工具 / 小地图 / 价格识别 / 关于 收进单一「应用菜单」；
  · 地图工具栏放地图、楼层、定位、复位、显示；
  · 左栏放图层搜索与常用快捷开关。

这里只断言结构与归属，不锁具体像素间距；视觉效果由浏览器验收。
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "index.html")
CSS = os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _between(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_single_app_menu_entry():
    html = _read(HTML)
    assert 'id="am-app"' in html
    for old in ("am-file", "am-view", "am-help", "am-mini", "am-ocr", "am-tools"):
        assert 'id="%s"' % old not in html, "旧一级菜单 %s 应已合并" % old
    assert html.index('id="app-menus"') < html.index('id="am-app"') < html.index("</nav>")


def test_workspace_nav_lives_in_top_bar():
    html = _read(HTML)
    bar_start = html.index('id="app-menubar"')
    view = html.index('id="view-switch"')
    status = html.index('id="app-menu-status"')
    bar_right = html.index('id="app-menubar-right"')
    menus = html.index('id="app-menus"')
    assert bar_start < menus < view < status < bar_right
    menubar_js = _read(os.path.join(ROOT, "js", "app-menubar.js"))
    assert "insertBefore(workspace, menus)" in menubar_js, "启动后工作区应排在应用菜单之前"
    # 市场大盘是「市场」工作区内的子页，不新增顶层视图 → 6 个工作区。
    assert html.count('id="view-btn-') == 6

    view_block = _between(html, 'id="view-switch"', 'id="app-menu-status"')
    for vt in ("vt-prices", "vt-market-meta", "vt-member-expire"):
        assert 'id="%s"' % vt not in view_block, "%s 应移出工作区导航" % vt

    global_block = _between(html, 'id="cb-global"', "</div>\n</div>")
    for vt in ("vt-prices", "vt-market-meta", "vt-member-expire"):
        assert 'id="%s"' % vt in global_block, "%s 应在上下文栏右侧" % vt


def test_legacy_menubar_is_hidden_anchor():
    html = _read(HTML)
    assert re.search(r'<div class="menubar" id="menubar" hidden', html), \
        "旧第二行只作为隐藏锚点存在"


def test_app_menu_has_five_sections():
    html = _read(HTML)
    panel = _between(html, 'id="am-app-panel"', 'id="app-menu-status"')
    nav = _between(panel, 'class="app-app-nav"', '</nav>')
    assert [nav.index('data-sec="%s"' % sec) for sec in ("file", "tools", "mini", "ocr", "about")] == sorted(
        nav.index('data-sec="%s"' % sec) for sec in ("file", "tools", "mini", "ocr", "about")
    )
    for sec in ("file", "tools", "mini", "ocr", "about"):
        assert 'id="app-sec-%s"' % sec in panel
        assert 'data-sec="%s"' % sec in panel
    assert 'id="app-sec-market"' not in panel
    assert "在线行情" not in panel


def test_moved_panels_live_inside_app_menu():
    html = _read(HTML)
    panel = _between(html, 'id="am-app-panel"', 'id="context-bar"')
    for ident in ("am-mini-panel", "am-ocr-panel", "raid-block", "about-block"):
        assert 'id="%s"' % ident in panel, "%s 应迁入应用菜单分区" % ident
    assert 'id="menu-settings"' not in html
    assert 'id="menu-about"' in html, "关于旧按钮保留为隐藏锚点"


def test_map_toolbar_has_map_floor_actions_and_display():
    html = _read(HTML)
    cb_map = _between(html, 'id="cb-map"', 'id="cb-tasks"')
    for ident in ("map-list", "floor-block", "cb-follow", "cb-reset", "cb-display", "display-pop"):
        assert 'id="%s"' % ident in cb_map, "地图工具栏缺少 %s" % ident


def test_sidebar_has_layer_search_and_quick_toggles():
    html = _read(HTML)
    layers = _between(html, 'id="layers-block"', 'id="wiki-panel"')
    assert 'id="layer-search"' in layers
    assert 'id="layer-quick"' in layers
    assert 'data-quick="extracts"' in layers
    assert 'id="layer-toggles"' in layers


def test_app_panel_is_settings_popover():
    css = _read(CSS)
    block = css[css.index("html body .app-app-panel {"):]
    block = block[:block.index("}")]
    assert "position: fixed" in block
    assert "right: 6px" in block
    assert "width: min(" in block and "height: min(" in block

    static_rule = css[css.index("html body .app-app-body .app-menu-panel,"):]
    static_rule = static_rule[:static_rule.index("}")]
    assert "position: static" in static_rule, "迁入设置弹层的旧下拉面板必须回到文档流"


def test_top_bar_narrow_uses_icons_without_losing_names():
    css = _read(CSS)
    selector = "html body .app-menubar .view-toolbar .vt-label {"
    block = css[css.index(selector):]
    block = block[:block.index("}")]
    assert "clip:" in block
    assert "display: none" not in block, "窄屏只做视觉隐藏，按钮文字仍作为无障碍名称"
    assert "@media (max-width: 1180px)" in css


def test_hud_sits_bottom_right():
    css = _read(CSS)
    block = css[css.index("html body #hud {"):]
    block = block[:block.index("}")]
    assert "top: auto" in block
    assert "bottom: 34px" in block
