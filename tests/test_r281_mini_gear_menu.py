"""R281（0.2.7.4）：小地图偏移 ±300 + 游戏内齿轮设置菜单。

三层各测一层，都不需要真的开窗口：

1. `index.html` —— 偏移 X / Y 滑条范围都是 ±300（后端本来就是 ±800，不需要改）；
2. `app.js` —— 齿轮 / 菜单 / 三个页签与「DOM 迁移」接线（内容不复制，id 与事件沿用）；
3. `MiniHost.cs` —— 穿透联动：指针热区、WebMessage 开合、菜单期间禁用 Esc 恢复穿透。

主界面零变化是硬约束：齿轮与菜单只在 `body.tk-mini` 下由 JS 创建，
因此 `index.html` 里不应出现这两个 id；小地图样式全部挂在 `body.tk-mini` 作用域下
（后者已由 `test_r32_minimap.py::test_style_css_scopes_every_mini_rule_under_body_class` 扫描）。
"""

from __future__ import annotations

from pathlib import Path

import re

import pytest

import config

ROOT = Path(__file__).resolve().parent.parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- A · 偏移范围

def test_offset_sliders_allow_plus_minus_300():
    html = read("index.html")
    assert 'id="ov-offset-x" min="-300" max="300"' in html
    assert 'id="ov-offset-y" min="-300" max="300"' in html


def test_backend_offset_limit_still_wider_than_slider():
    """滑条 ±300 必须落在后端允许区间内，否则拖动会被服务端钳回去。"""
    assert config.OVERLAY_OFFSET_MIN <= -300
    assert config.OVERLAY_OFFSET_MAX >= 300
    # 前端只做 Math.round、不额外钳制；钳制交给 config.normalize
    app = read("app.js")
    assert "offset_x: Math.round(parseFloat(el.ovOffsetX && el.ovOffsetX.value)) || 0" in app


# --------------------------------------------------------------- B · 齿轮菜单（页面）

def test_app_js_creates_gear_and_menu_only_in_mini_mode():
    app = read("app.js")
    assert "function installMiniGearMenu" in app
    assert "installMiniGearMenu();" in app, "applyMiniMode 里必须真的调用"
    assert 'gear.id = "mini-gear"' in app
    assert 'root.id = "mini-menu"' in app
    # 三个页签
    for tab in ("mini", "layers", "tasks"):
        assert '{ id: "%s", label:' % tab in app
    assert "MINI_MENU_TABS" in app
    # 主界面不出现：index.html 里没有这两个 id（只在 mini 下由 JS 创建）
    html = read("index.html")
    assert 'id="mini-gear"' not in html
    assert 'id="mini-menu"' not in html


def test_app_js_migrates_existing_nodes_instead_of_copying():
    """三个子菜单必须迁入现有节点：id 不变 → 既有绑定与配置读写全部沿用。"""
    app = read("app.js")
    assert "function miniMenuMount" in app
    assert "entry.parent.insertBefore(entry.el, entry.next)" in app, "关闭菜单要原位还原"
    for ident in ("am-mini-panel", "floor-block", "layers-block", "wiki-panel", "task-layer-toggles"):
        assert '"%s"' % ident in app, ident
    # 不复制：不应为这些面板新建同名控件
    assert "cloneNode" not in app


def test_app_js_menu_open_close_hooks():
    app = read("app.js")
    assert "window.__tkMiniMenu = function" in app
    assert 'miniMenuPost("tk-mini-menu:1")' in app
    assert 'miniMenuPost("tk-mini-menu:0")' in app
    assert 'window.chrome.webview.postMessage' in app
    # 切图 / 全图模式强制收起
    assert 'window.addEventListener("gwmap:select", function () { miniMenuClose(); });' in app
    assert "if (on2) { miniMenuClose(); }" in app
    # 点菜单外收起（捕获阶段，赶在业务点击之前）
    assert "root.contains(ev.target) || gear.contains(ev.target)" in app


def test_mini_menu_css_is_scoped_and_hides_gear_in_full_mode():
    css = read("style.css")
    assert "body.tk-mini #mini-gear" in css
    assert "body.tk-mini #mini-menu" in css
    assert 'body.tk-mini[data-mini-full="1"] #mini-gear { display: none; }' in css
    # 圆形窗口被 SetWindowRgn 裁成椭圆：齿轮必须内缩到圆内，否则点不到
    assert 'body.tk-mini[data-mini-shape="circle"] #mini-gear' in css
    assert "top: 17%;" in css
    # 迁入块要覆盖主界面的绝对定位 / 固定宽度，否则菜单会飞出窗口
    assert "body.tk-mini .tk-mini-menu-scope#am-mini-panel" in css
    assert "position: static;" in css
    # 窄窗保底宽度 + 滚动
    assert "min-width: 180px;" in css
    assert "overflow-y: auto;" in css


# --------------------------------------------------------------- B · 穿透联动（宿主）

def test_host_polls_cursor_and_manages_click_through():
    host = read("tools/host/src/MiniHost.cs")
    assert "GetCursorPos" in host
    assert "private void OnGearTick" in host
    assert "GEAR_HIT_DIP" in host
    # 菜单打开 → 关穿透；关闭 → 回到配置值（不写回配置）
    assert "private void OpenMenuState()" in host
    assert "private void CloseMenuState()" in host
    assert "_clickThrough = false;" in host
    assert "_cfg.ClickThrough" in host
    # 指针离开窗口自动收起（轮询 2 拍）
    assert "_menuOutsideTicks" in host


def test_host_uses_webmessage_contract():
    host = read("tools/host/src/MiniHost.cs")
    assert "WebMessageReceived" in host
    assert "IsWebMessageEnabled" in host
    assert 'msg == "tk-mini-menu:1"' in host
    assert 'msg == "tk-mini-menu:0"' in host
    assert "window.__tkMiniMenu" in host


def test_host_menu_does_not_fight_full_mode_or_config_tick():
    host = read("tools/host/src/MiniHost.cs")
    # 全图模式退出时由 ExitFull 恢复穿透；菜单期间不能被配置轮询抢回穿透
    assert "if (clickChanged && !_full && !_menuOpen && !_gearHover)" in host
    assert "SendMenuToPage(false);" in host
    # 全图模式进入前关闭菜单
    assert "R281：全图模式不显示齿轮" in host
    # 菜单期间窗口临时改回方形（圆形 SetWindowRgn 会裁掉菜单与齿轮）
    assert '(_menuOpen || _cfg.Shape != "circle") ? "square" : "circle"' in host
    assert "_menuOpen || _cfg.Shape" in host


def test_host_debug_state_exposes_menu_fields():
    host = read("tools/host/src/MiniHost.cs")
    assert 'd["menuOpen"] = _menuOpen;' in host
    assert 'd["gearHover"] = _gearHover;' in host


# --------------------------------------------------------------- 版本

def _version_of(rel: str) -> str:
    # 本项目版本号是三段或四段（0.2.7.6 / 0.2.8.1），所以段数不能写死。
    m = re.search(r'^VERSION = "([0-9]+(?:\.[0-9]+){2,3})"', read(rel), re.M)
    assert m, "%s 里找不到 VERSION 常量" % rel
    return m.group(1)


def test_version_consistent_between_serve_and_installer():
    """两个文件必须同一个版本号（构建脚本从 serve.py 读，安装器自报另一处）。

    这里刻意不写死具体版本：写死字面量每发一版都要改测试，已经连续漏改两次
    （0.2.7.8 / 0.2.8.1），失败信息还会伪装成「功能回归」。真正的不变量是二者一致。
    """
    serve_v = _version_of("tools/serve.py")
    inst_v = _version_of("tools/installer.py")
    assert serve_v == inst_v, "serve.py=%s 与 installer.py=%s 版本不一致" % (serve_v, inst_v)
    assert serve_v != "0.0.0", "版本号不能是占位的 0.0.0"
