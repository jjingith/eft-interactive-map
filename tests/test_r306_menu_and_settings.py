# -*- coding: utf-8 -*-
"""R306：菜单重构（小工具 / 设置）+ 属性设置扁平化与 Save + 两处 CMD 闪窗 + 空板块置灰。

本轮用户需求（交付时逐条对应）：
1. 「应用菜单」改名「设置」，「文件」「工具」两个分区删掉；
2. 「小地图」「价格识别」拆到新一级菜单「小工具」；
3. 一级菜单顺序：… 更新 小工具 设置；
4. 截图 / 日志目录设置移到「设置」；
5. 点「浏览…」不再闪 cmd（serve.pick_folder_dialog 带 CREATE_NO_WINDOW）；
6. 安装时不再闪 cmd（旧版卸载器改用隐藏控制台继承）；
7. 市场大盘空板块置灰；属性设置去像素素材 + 左侧 Save 持久化；
   识图「?」徽记可点击（scan.py 坐标修复）。

这里锁结构与关键实现点；实际交互由 build/_r306_* 探针与浏览器截图验收。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "style.css").read_text(encoding="utf-8")
FLAT = (ROOT / "styles" / "modern-flat.css").read_text(encoding="utf-8")
MARKET_CSS = (ROOT / "market.css").read_text(encoding="utf-8")
BOARD_JS = (ROOT / "js" / "market-board.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "app.js").read_text(encoding="utf-8")
SERVE = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
INSTALLER = (ROOT / "tools" / "installer.py").read_text(encoding="utf-8")
SCAN = (ROOT / "tools" / "scan.py").read_text(encoding="utf-8")


def _block(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


# ---------------------------------------------------------------- 1. 菜单结构
def test_tools_is_a_top_level_view_before_settings():
    """R307：小工具从下拉菜单提为一级视图（与地图同级），设置仍是顶栏菜单。"""
    assert 'id="view-btn-tools"' in HTML and 'id="tools-view"' in HTML
    assert 'id="am-tools"' not in HTML and 'id="am-tools-panel"' not in HTML
    assert HTML.index('id="view-btn-changes"') < HTML.index('id="view-btn-tools"')
    menus = _block(HTML, 'id="app-menus"', "</nav>")
    assert 'id="am-app"' in menus and 'id="am-tools"' not in menus


def test_settings_has_only_dirs_and_about_tabs():
    panel = _block(HTML, 'id="am-app-panel"', 'id="app-legacy-sec"')
    nav = _block(panel, 'class="app-app-nav"', "</nav>")
    secs = re.findall(r'data-sec="([^"]+)"', nav)
    assert secs == ["dirs", "about"]
    for sec in secs:
        assert 'id="app-sec-%s"' % sec in panel
    # 「文件」「工具」不再作为分区出现
    assert "app-sec-file" not in panel and "app-sec-tools" not in panel
    assert ">文件</button>" not in nav and ">工具</button>" not in nav


def test_directory_settings_moved_into_settings():
    dirs = _block(HTML, 'id="app-sec-dirs"', 'id="app-sec-about"')
    for ident in ("mini-shots-dir", "mini-log-dir", "mini-paths-note"):
        assert 'id="%s"' % ident in dirs
    assert dirs.count("mini-dir-browse") == 2
    # 小工具视图里的小地图面板不再包含目录字段
    tools = _block(HTML, 'id="tools-view"', "</section>")
    mini = _block(tools, 'id="am-mini-panel"', 'id="am-ocr-panel"')
    assert 'id="mini-shots-dir"' not in mini and 'id="mini-log-dir"' not in mini


def test_legacy_raid_block_is_kept_alive():
    legacy = _block(HTML, 'id="app-legacy-sec"', 'id="context-bar"')
    for ident in ("raid-block", "raid-status", "quest-log", "shot-status", "clean-status"):
        assert 'id="%s"' % ident in legacy
    # 设置面板里不再直接放 raid-block（避免两个同名 id）
    panel = _block(HTML, 'id="am-app-panel"', 'id="app-legacy-sec"')
    assert 'id="raid-block"' not in panel


def test_about_section_id_is_unique():
    assert HTML.count('id="app-sec-about"') == 1, "重复 id 会让「关于」面板点击后显示空内容"


def test_tools_view_css_is_scoped_and_neutralizes_panel_chrome():
    """R307：小工具是视图，样式在新文件里；嵌套的下拉面板要中和定位与位图边框。"""
    tools_css = (ROOT / "styles" / "tools.css").read_text(encoding="utf-8")
    assert "#tools-view" in tools_css
    assert ".tl-item.is-active" in tools_css
    nested = _block(tools_css, "html body .tl-pane .app-menu-panel {", "}")
    assert "position: static" in nested
    assert "border-image: none" in nested
    dirs = _block(CSS, "html body .app-dir-panel {", "}")
    assert "width: auto" in dirs and "position" not in dirs


# ---------------------------------------------------------------- 2. CMD 闪窗
def test_pick_folder_dialog_uses_create_no_window():
    body = _block(SERVE, "def pick_folder_dialog(", "def best_logs_dir")
    assert 'creationflags' in body
    assert 'CREATE_NO_WINDOW' in body
    # 旧注释（「加了对话框会被隐藏」）是错的，已用探针实测替换
    assert "对话框照常弹出" in body or "探针验证" in body


def test_legacy_uninstaller_inherits_hidden_console():
    start = INSTALLER.index("def _run_legacy_uninstaller(")
    follow = INSTALLER.index("\ndef ", start + 10)
    body = INSTALLER[start:follow]
    assert "CREATE_NEW_CONSOLE" in body
    assert "STARTUPINFO" in body
    assert "STARTF_USESHOWWINDOW" in body and "SW_HIDE" in body
    # 代码里不能再用 CREATE_NO_WINDOW（会重新触发旧卸载器子进程的可见控制台）；
    # 文档字符串会解释为什么，所以只查赋值语句
    assert 'kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW' not in body


# ---------------------------------------------------------------- 3. 属性设置
def test_profile_has_prominent_left_save_button():
    foot = _block(HTML, 'class="gw-prof-foot gw-attrs-foot"', "</footer>")
    assert 'id="gw-attrs-saveleft"' in foot
    assert 'id="gw-attrs-savehint"' in foot
    assert ">保存设置</button>" in foot
    # Save 在左侧：DOM 顺序在取消 / Confirm 之前
    assert foot.index("gw-attrs-saveleft") < foot.index("gw-prof-cancel") < foot.index("gw-prof-save")


def test_profile_save_keeps_panel_open_and_persists():
    assert "function gwProfileSubmit(opts)" in APP_JS
    assert "opts.keepOpen" in APP_JS
    assert "已保存到本机，下次启动自动沿用" in APP_JS
    assert 'e.attrsSave.addEventListener("click"' in APP_JS
    # 持久化仍是 localStorage 的 GW_ATTR_KEY，启动按模式读回
    assert 'var GW_ATTR_KEY = "eftmap.attrs.v1"' in APP_JS
    assert "localStorage.setItem(GW_ATTR_KEY" in APP_JS
    assert "localStorage.getItem(GW_ATTR_KEY" in APP_JS


def test_profile_modal_uses_flat_not_bitmap():
    block = _block(FLAT, "html body .gw-prof-box {", "尊重减少动态")
    assert "border-image: none !important" in block
    assert "html body .gw-prof-head" in block
    assert "dialog-box.png" not in block and "titlebar.png" not in block
    # Save 键主色底白字
    save = _block(FLAT, "html body #gw-attrs-saveleft {", "}")
    assert "background:" in save and "!important" in save
    assert "color: #fff" in save


# ---------------------------------------------------------------- 4. 市场大盘空板块
def test_empty_sector_detection_and_grey_out():
    assert "emptySectors" in BOARD_JS
    assert "state.emptySectors[sector.key] = true" in BOARD_JS
    assert "is-empty" in BOARD_JS
    assert 'setAttribute("aria-disabled", "true")' in BOARD_JS
    assert "无行情数据" in BOARD_JS
    # 空板块分支不绑点击（否则点进去 0 项死胡同）
    seg = _block(BOARD_JS, "if (empty) {\n        cell.title", "} else {")
    assert "addEventListener(\"click\"" not in seg
    assert ".mb-sector.is-empty" in MARKET_CSS
    assert "grayscale" in MARKET_CSS


# ---------------------------------------------------------------- 5. 识图「?」可点击
def test_badge_click_uses_client_coords_not_screen():
    """WM_LBUTTONDOWN 的 lparam 已经是客户坐标；再 ScreenToClient 会整体平移命中区。"""
    block = _block(SCAN, "            if msg == WM_LBUTTONDOWN:\n                # R306", "if role == 6")
    assert "hit_badge(x, y)" in block
    # 注释里会解释旧写法，这里只锁「代码不再调用」ScreenToClient
    assert "_user32.ScreenToClient(hwnd" not in block
    assert "_ACTIVE.toggle_menu(idx)" in block


def test_badge_menu_selection_still_wired():
    assert "def hit_badge" in SCAN and "def toggle_menu" in SCAN
    assert "def menu_click" in SCAN and "def pick_candidate" in SCAN
    assert 'p["manual"] = c.get("price")' in SCAN
