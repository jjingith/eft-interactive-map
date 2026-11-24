"""R32 小地图：`?mini=1` 页面模式 + `tools/overlay.py` 置顶宿主窗。

三层各测一层，都不需要真的开窗口：

1. `plan_window` —— 四角吸附的纯计算（对齐参考实现 `ApplyBounds`：边距 16、`right - size - 16`）；
2. `build_url` —— mini 模式地址拼接（参数顺序固定，便于人眼比对）；
3. 页面接线 —— `app.js` 真的挂了 class、`style.css` 真的隐藏了面板，且**只在 body.tk-mini 下生效**
   （这条最重要：小地图样式绝不能漏到主页面）。

真起窗口的那条路（Edge + SetWindowLong）不测：它会弹窗、抢焦点，测试不能干这种事。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import config
import overlay

ROOT = Path(__file__).resolve().parent.parent
WORK = (0, 0, 1920, 1040)


# --------------------------------------------------------------- 四角吸附

@pytest.mark.parametrize("corner,expect", [
    ("top-left", (16, 16)),
    ("top-right", (1920 - 260 - 16, 16)),
    ("bottom-left", (16, 1040 - 260 - 16)),
    ("bottom-right", (1920 - 260 - 16, 1040 - 260 - 16)),
])
def test_plan_window_snaps_to_corners_with_fixed_margin(corner, expect):
    x, y, w, h = overlay.plan_window(WORK, 260, corner)
    assert (x, y) == expect
    assert (w, h) == (260, 260)


def test_plan_window_applies_offset_on_top_of_margin():
    x, y, _, _ = overlay.plan_window(WORK, 260, "top-left", offset_x=10, offset_y=-4)
    assert (x, y) == (26, 12)


def test_plan_window_honours_non_zero_work_area_origin():
    """多显示器 / 任务栏在左侧时，工作区原点不是 (0,0)，偏移必须跟着走。"""
    x, y, _, _ = overlay.plan_window((-1920, 40, 0, 1080), 200, "bottom-right")
    assert (x, y) == (-200 - 16, 1080 - 200 - 16)


def test_plan_window_clamps_size_and_unknown_corner():
    assert overlay.plan_window(WORK, 1, "top-left")[2] == overlay.SIZE_MIN
    assert overlay.plan_window(WORK, 99999, "top-left")[2] == overlay.SIZE_MAX
    # 角落写错时宁可跑到右下角，也不要算出一个越界坐标
    assert overlay.plan_window(WORK, 260, "middle")[:2] == overlay.plan_window(WORK, 260, "bottom-right")[:2]


# --------------------------------------------------------------- URL 拼装
# R32.9：地址必须是 **http://本机服务**。file:// 下页面 fetch 不到 api/…，
# 表现是「地图能看、但永远不跟随玩家」——比直接报错更坑。

def test_build_url_carries_all_mini_params():
    url = overlay.build_url("http://127.0.0.1:8810/index.html", 300, 0.8, "square",
                            labels=1, follow=1, bg="#0d1117")
    assert "?mini=1&" in url
    assert "size=300" in url
    assert "opacity=0.8" in url
    assert "shape=square" in url
    assert "labels=1" in url
    assert "follow=1" in url
    assert "bg=%230d1117" in url
    assert url.startswith("http://127.0.0.1:8810/index.html")


def test_build_url_normalises_bad_values():
    url = overlay.build_url("http://127.0.0.1:8810/index.html", 99999, 5.0, "triangle")
    assert "size=%d" % overlay.SIZE_MAX in url
    assert "opacity=1" in url          # 小数点后的 0 被去掉，但值仍是 1
    assert "shape=circle" in url       # 不认识的形状回落圆形


def test_build_url_rejects_file_and_empty_base():
    """file:// 必须被拒：页面在那种协议下拿不到实时定位。"""
    with pytest.raises(ValueError):
        overlay.build_url("file:///C:/tmp/index.html")
    with pytest.raises(ValueError):
        overlay.build_url("")


def test_build_url_quotes_background_value():
    """背景色是拼进 URL 的，不能带出额外的参数。"""
    url = overlay.build_url("http://127.0.0.1:8810/index.html", bg="#000&size=9999")
    assert "size=9999" not in url
    assert "&size=260" in url


# --------------------------------------------------------------- 热键与尺寸

def test_parse_hotkey_reads_common_combos():
    assert overlay.parse_hotkey("Ctrl+Alt+M") == (0x0002 | 0x0001, ord("M"))
    assert overlay.parse_hotkey("f9") == (0, 0x78)
    assert overlay.parse_hotkey("Shift+F5") == (0x0004, 0x74)


def test_parse_hotkey_refuses_junk():
    for bad in ("", None, "off", "Ctrl+", "Ctrl+NotAKey"):
        assert overlay.parse_hotkey(bad) is None, bad


def test_plan_rect_handles_non_square_full_mode():
    x, y, w, h = overlay.plan_rect(WORK, 900, 640, "bottom-right")
    assert (w, h) == (900, 640)
    assert x == 1920 - 900 - 16
    assert y == 1040 - 640 - 16


# --------------------------------------------------------------- 页面接线

def test_app_js_has_mini_mode_entry():
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'classList.add("tk-mini")' in src
    assert "function applyMiniMode" in src
    assert "applyMiniMode();" in src, "boot() 里必须真的调用，否则参数形同虚设"


def test_app_js_mini_defaults_and_limits():
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "MINI_DEFAULT" in src and "MINI_LIMITS" in src
    assert '"circle"' in src
    # 默认值必须和 overlay.py 对齐，否则两边各说各话
    assert "size: 260" in src and "opacity: 0.9" in src


def test_app_js_supports_follow_and_full_switch():
    """R32.9：小地图要能跟随玩家，并且留一个宿主可调的「小窗/大图」开关。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function applyMiniView" in src
    assert "state.mini && state.mini.follow" in src
    assert "__tkMiniFull" in src
    assert "data-mini-full" in src


def test_follow_ignores_out_of_map_position():
    """截图坐标来自另一张图时不能把视角移过去，否则主图/小图整片黑。

    状态栏仍提示「可能不在当前地图」，centerOnPlayer / applyAutoZoom / applyPosition
    都必须在越界时保持当前视角。R85 起 applyMiniView 不再因「没有玩家」提前返回：
    跨图坐标不采用，锚点退到「最近一次已知位置」或当前地图几何中心，缩放仍然可见。
    """
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function centerOnPlayer" in src
    assert "if (!insideMap(state.map, state.player)) { return; }" in src
    assert "if (state.map && (!pos || !insideMap(state.map, pos))) { return; }" in src
    assert "if (state.player && !insideMap(state.map, state.player)) { applyView(); return; }" in src
    # R85：小地图锚点只采用「当前图内」的位置，跨图坐标不采用
    assert "function miniAnchor" in src
    assert "else if (state.lastPlayer && insideMap(map, state.lastPlayer))" in src
    assert "state.baseVb[0] + state.baseVb[2] / 2" in src


def test_app_js_background_color_is_sanitised():
    """背景色会进 CSS 变量，只放行「颜色」，不放行任何 CSS 片段。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function miniColor" in src
    assert "miniColor(q.bg)" in src



def test_mini_mode_is_opt_in_only():
    """不带 `?mini=1` 时必须原样返回 null——小地图不能有任何机会影响普通页面。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'if (!on) { return null; }' in src


def test_style_css_scopes_every_mini_rule_under_body_class():
    """所有小地图样式都必须挂在小地图作用域下：漏一条就会污染主页面。

    允许两种前缀：`body.tk-mini …` 与 `html.tk-mini-root`（后者只用于把 html 背景一起透明）。
    """
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    start = css.find("R32 小地图模式")
    anchor = css.rfind("/*", 0, start)
    assert anchor > 0, "找不到 R32 小地图样式段"
    # R273 起又在小地图段之后追加了普通样式；只扫到下一个顶层分节注释，
    # 否则后续版本追加的普通选择器会被误判成「漏挂 body.tk-mini 作用域」。
    end = css.find("/* ==========", start)
    if end < 0:
        end = len(css)
    block = re.sub(r"/\*.*?\*/", "", css[anchor:end], flags=re.S)   # 先剥注释，再解析选择器
    allowed = ("body.tk-mini", "html.tk-mini-root")
    for selector in re.findall(r"([^{}]+)\{", block):
        for one in selector.split(","):
            one = one.strip()
            if not one:
                continue
            assert one.startswith(allowed), "选择器没挂在小地图作用域下：%s" % one


def test_style_css_hides_the_chrome_panels():
    css = (ROOT / "style.css").read_text(encoding="utf-8")
    for ident in ("#menubar", "#sidebar", "#task-panel", "#sidebar-expand", "#hud", ".statusbar"):
        assert "body.tk-mini %s" % ident in css, "小窗里应隐藏 %s" % ident


def test_overlay_import_has_no_side_effects():
    """import 一下不能就起窗口 / 改别人的窗口样式（测试会 import 它）。"""
    assert overlay.IS_WINDOWS == (os.name == "nt" or overlay.IS_WINDOWS)
    assert overlay.MARGIN == 16                 # 与参考实现的 16 DIP 对齐
    assert set(overlay.CORNERS) == {"top-left", "top-right", "bottom-left", "bottom-right"}


def test_overlay_dry_run_does_not_touch_windows(capsys):
    """`--dry-run` 只打印计划；非 Windows 上直接返回「不支持」，都不碰 Win32。"""
    code = overlay.main(["--dry-run"])
    if not overlay.IS_WINDOWS:
        assert code == 3
        return
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "mini=1" in out


def test_overlay_rejects_file_base_before_touching_anything(capsys):
    """地址不是 http:// 时要**立刻**拒绝，而不是先起窗口再发现页面不工作。"""
    code = overlay.main(["--base", "file:///C:/tmp/index.html"])
    assert code == 2
    assert "http" in capsys.readouterr().err


# ------------------------------------------------- R32.9：设置面板（大小 / 位置 / 透明度）

def test_config_has_overlay_section():
    """设置面板与宿主共用 `overlay` 配置段：缺了它两边就各说各话。"""
    cfg = config.default_config()["overlay"]
    for key in ("enabled", "size", "opacity", "corner", "offset_x", "offset_y",
                "shape", "labels", "follow", "click_through"):
        assert key in cfg, key


def test_config_normalises_overlay_garbage():
    """脏值一律回落默认 / 钳到区间：绝不产出越界坐标或 NaN。"""
    got = config.normalize({"overlay": {
        "size": 99999, "opacity": 5, "corner": "middle", "shape": "triangle",
        "offset_x": -9999, "offset_y": "abc", "follow": "yes"}})["overlay"]
    assert got["size"] == config.OVERLAY_SIZE_MAX
    assert got["opacity"] == config.OVERLAY_OPACITY_MAX
    assert got["corner"] == "bottom-right"
    assert got["shape"] == "square"
    assert got["offset_x"] == config.OVERLAY_OFFSET_MIN
    assert got["offset_y"] == 0
    assert got["follow"] is True


def test_merge_ui_accepts_overlay_patch():
    """页面「设置」里改一项就发一段 overlay，合并时不能把其它项抹掉。"""
    merged = config.merge_ui({}, {"overlay": {"size": 320, "opacity": 0.5}})
    assert merged["overlay"]["size"] == 320
    assert merged["overlay"]["opacity"] == 0.5
    assert merged["overlay"]["corner"] == "bottom-right"     # 没发的键保持默认


def test_app_js_wires_overlay_settings_in_minimap_menu():
    """R306：小地图设置在一级菜单「小工具」内；设置面板不再有小地图 / 行情分区。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function applyOverlaySettings" in src
    assert "bindOverlaySettings();" in src

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    tools = html[html.index('id="am-tools-panel"'):html.index('id="app-legacy-sec"')]
    assert 'id="am-mini-panel"' in tools
    assert 'id="app-sec-mini"' not in tools
    panel = html[html.index('id="am-app-panel"'):html.index('id="app-legacy-sec"')]
    for gone in ("app-sec-mini", "app-sec-market", "settings-block"):
        assert 'id="%s"' % gone not in panel


def test_app_js_settings_persist_overlay_patch():
    """改设置要写回配置（否则刷新就没了），且起停走专门的接口。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'queuePrefs({ overlay: overlayPatch() })' in src
    assert '"api/overlay"' in src
    assert "function overlayPatch" in src


def test_index_html_has_overlay_controls():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for ident in ("ov-enabled", "ov-size", "ov-opacity",
                  "ov-corner", "ov-offset-x", "ov-offset-y", "ov-shape",
                  "ov-follow", "ov-labels", "ov-click"):
        assert 'id="%s"' % ident in html, ident
    assert 'id="menu-settings"' not in html
    assert 'id="settings-block"' not in html


def test_overlay_reads_settings_from_config():
    """命令行参数全部默认 None：不写就用设置面板里的值，写了才覆盖。"""
    src = (Path(overlay.__file__)).read_text(encoding="utf-8")
    assert "def settings_from" in src
    assert 'default=None, help="边长 px（覆盖设置面板）"' in src
    assert "config.load(" in src


def test_build_url_marks_host_managed_alpha():
    """宿主管透明度时要告诉页面「别再压地图」，否则两层叠加会过暗。"""
    url = overlay.build_url("http://127.0.0.1:8810/index.html", host_alpha=True)
    assert "ha=1" in url
    assert "ha=1" not in overlay.build_url("http://127.0.0.1:8810/index.html")


def test_settings_from_prefers_config_over_defaults(tmp_path):
    config.save({"overlay": {"size": 400, "corner": "top-left"}}, str(tmp_path))
    got = overlay.settings_from(str(tmp_path), {})
    assert got["size"] == 400
    assert got["corner"] == "top-left"
    # 命令行显式给的值仍然要能覆盖
    assert overlay.settings_from(str(tmp_path), {"size": 180})["size"] == 180


# ------------------------------------------------- R32.9：设置面板（大小 / 位置 / 透明度）

def test_config_has_overlay_section():
    """设置面板与宿主共用 `overlay` 配置段：缺了它两边就各说各话。"""
    cfg = config.default_config()["overlay"]
    for key in ("enabled", "size", "opacity", "corner", "offset_x", "offset_y",
                "shape", "labels", "follow", "click_through"):
        assert key in cfg, key


def test_config_normalises_overlay_garbage():
    """脏值一律回落默认 / 钳到区间：绝不产出越界坐标或 NaN。"""
    got = config.normalize({"overlay": {
        "size": 99999, "opacity": 5, "corner": "middle", "shape": "triangle",
        "offset_x": -9999, "offset_y": "abc", "follow": "yes"}})["overlay"]
    assert got["size"] == config.OVERLAY_SIZE_MAX
    assert got["opacity"] == config.OVERLAY_OPACITY_MAX
    assert got["corner"] == "bottom-right"
    assert got["shape"] == "square"
    assert got["offset_x"] == config.OVERLAY_OFFSET_MIN
    assert got["offset_y"] == 0
    assert got["follow"] is True


def test_merge_ui_accepts_overlay_patch():
    """页面「设置」里改一项就发一段 overlay，合并时不能把其它项抹掉。"""
    merged = config.merge_ui({}, {"overlay": {"size": 320, "opacity": 0.5}})
    assert merged["overlay"]["size"] == 320
    assert merged["overlay"]["opacity"] == 0.5
    assert merged["overlay"]["corner"] == "bottom-right"     # 没发的键保持默认


def test_app_js_wires_overlay_settings_in_minimap_menu():
    """R306：小地图设置在一级菜单「小工具」内；设置面板不再有小地图 / 行情分区。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert "function applyOverlaySettings" in src
    assert "bindOverlaySettings();" in src

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    tools = html[html.index('id="am-tools-panel"'):html.index('id="app-legacy-sec"')]
    assert 'id="am-mini-panel"' in tools
    assert 'id="app-sec-mini"' not in tools
    panel = html[html.index('id="am-app-panel"'):html.index('id="app-legacy-sec"')]
    for gone in ("app-sec-mini", "app-sec-market", "settings-block"):
        assert 'id="%s"' % gone not in panel


def test_app_js_settings_persist_overlay_patch():
    """改设置要写回配置（否则刷新就没了），且起停走专门的接口。"""
    src = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'queuePrefs({ overlay: overlayPatch() })' in src
    assert '"api/overlay"' in src
    assert "function overlayPatch" in src


def test_index_html_has_overlay_controls():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    for ident in ("ov-enabled", "ov-size", "ov-opacity",
                  "ov-corner", "ov-offset-x", "ov-offset-y", "ov-shape",
                  "ov-follow", "ov-labels", "ov-click"):
        assert 'id="%s"' % ident in html, ident
    assert 'id="menu-settings"' not in html
    assert 'id="settings-block"' not in html


def test_overlay_reads_settings_from_config():
    """命令行参数全部默认 None：不写就用设置面板里的值，写了才覆盖。"""
    src = (Path(overlay.__file__)).read_text(encoding="utf-8")
    assert "def settings_from" in src
    assert 'default=None, help="边长 px（覆盖设置面板）"' in src
    assert "config.load(" in src


def test_build_url_marks_host_managed_alpha():
    """宿主管透明度时要告诉页面「别再压地图」，否则两层叠加会过暗。"""
    url = overlay.build_url("http://127.0.0.1:8810/index.html", host_alpha=True)
    assert "ha=1" in url
    assert "ha=1" not in overlay.build_url("http://127.0.0.1:8810/index.html")


def test_settings_from_prefers_config_over_defaults(tmp_path):
    config.save({"overlay": {"size": 400, "corner": "top-left"}}, str(tmp_path))
    got = overlay.settings_from(str(tmp_path), {})
    assert got["size"] == 400
    assert got["corner"] == "top-left"
    # 命令行显式给的值仍然要能覆盖
    assert overlay.settings_from(str(tmp_path), {"size": 180})["size"] == 180
