# -*- coding: utf-8 -*-
"""R18：Windows XP Luna 主题层测试（纯视觉层，不改布局/业务）。

断言目标：
1. 主题文件存在、在主样式之后加载、带版本参数；
2. 令牌与三个工作台的色板翻转齐全；
3. 不引入任何外部资源（无 @import / http(s) / url()）；
4. 不碰地图画布选择器（地图底图、标注、路线、定位保持原样）；
5. 所有选择器都带作用域前缀（html / :root / 三个工作台根），避免污染其它模块。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
THEME = os.path.join(ROOT, "theme-windows-xp.css")
STYLE = os.path.join(ROOT, "style.css")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _rules(css):
    """返回 [(selector, body)]；跳过注释与 at-rule 外层。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, buf, i, n = [], [], 0, len(css)
    while i < n:
        ch = css[i]
        if ch == "{":
            sel = "".join(buf).strip()
            buf = []
            depth, j = 1, i + 1
            while j < n and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            out.append((sel, css[i + 1:j - 1]))
            i = j
            continue
        if ch == "}":
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    return out


def _rule_map(css):
    d = {}
    for sel, body in _rules(css):
        d.setdefault(re.sub(r"\s+", " ", sel).strip(), []).append(body)
    return d


def test_theme_loaded_after_main_style():
    html = _read(INDEX)
    m_style = re.search(r'<link rel="stylesheet" href="style\.css\?v=([^"]+)">', html)
    m_theme = re.search(r'<link rel="stylesheet" href="theme-windows-xp\.css\?v=([^"]+)">', html)
    assert m_style, "缺 style.css 引用"
    assert m_theme, "缺 theme-windows-xp.css 引用"
    assert html.index("style.css") < html.index("theme-windows-xp.css"), "主题层必须在主样式之后加载"
    assert m_style.group(1) == m_theme.group(1), "主样式与主题层的版本参数必须同步"


def test_theme_tokens_present():
    css = _read(THEME)
    for tok in ("--xp-luna-1", "--xp-luna-2", "--xp-face", "--xp-border-dark",
                "--xp-btn-face-a", "--xp-btn-hover-c", "--xp-sel", "--xp-row-sel",
                "--xp-tip-bg", "--xp-ok", "--xp-warn", "--xp-bad"):
        assert tok in css, "缺主题令牌 %s" % tok


def test_theme_flips_three_workbenches():
    """配装 / 配枪 / 弹药三个工作台的深色令牌必须被翻成 Luna 浅色。"""
    css = _read(THEME)
    assert re.search(r"\.loadout-workbench\s*\{[^}]*--lw-bg:\s*#ece9d8", css, re.S), "配装底色未翻转"
    assert re.search(r"\.gun-workbench\s*\{[^}]*--lw-bg:\s*#ece9d8", css, re.S), "配枪底色未翻转"
    assert re.search(r"\.am-workbench,\s*#am-detail\s*\{[^}]*--am-bg:\s*#ece9d8", css, re.S), "弹药/弹窗底色未翻转"
    for tok in ("--lw-txt: #000000", "--lw-line: #d6d2c2", "--am-txt: #000000", "--am-line-2: #aca899"):
        assert tok in css, "缺色板项 %s" % tok


def test_theme_has_no_external_dependency():
    css = _read(THEME)
    assert "@import" not in css, "主题层不得 @import"
    assert "http://" not in css and "https://" not in css, "主题层不得引用外部 URL"
    assert "url(" not in css, "主题层不得引用外部/内嵌资源（运行期必须离线）"


def test_theme_does_not_touch_map_canvas():
    """地图画布 / 标注 / 路线 / 定位图元由脚本注入，主题层不得改它们的样式。"""
    css = _read(THEME)
    for bad in ("#map-svg", "#viewport", ".emk-", "#stage "):
        assert bad not in css, "主题层不应命中地图画布：%s" % bad


def test_all_selectors_are_scoped():
    """每条规则都必须带作用域（html / :root / 三个工作台根），避免全站误伤。"""
    css = _read(THEME)
    allowed = ("html ", "html.", ":root", ".loadout-workbench", ".gun-workbench",
               ".am-workbench", "#am-detail")
    bad = []
    for sel, _body in _rules(css):
        if not sel or sel.startswith("@"):
            continue
        for part in sel.split(","):
            p = part.strip()
            if not p:
                continue
            if not p.startswith(allowed):
                bad.append(p[:60])
    assert not bad, "存在未加作用域的规则：%s" % bad[:5]


def test_no_layout_takeover():
    """换肤不改布局：不出现 grid-template / flex 简写 / 宽高覆盖之外的排版重写。"""
    css = _read(THEME)
    for bad in ("grid-template", "flex-direction", "position: fixed;\n  left: 0"):
        assert bad not in css, "主题层不应改写布局：%s" % bad
    # 允许的定位只有既有浮层（弹窗/浮层复用原定位），不新增 fixed 容器
    assert css.count("position: fixed") == 0, "主题层不应新增 fixed 定位容器"


def test_theme_covers_key_components():
    """主要组件的选择器必须都在主题层出现（缺一项就意味着该模块没换肤）。"""
    css = _read(THEME)
    need = [
        ".lw-top", ".gw-top", ".am-top",              # 三个工具条
        ".lw-side", ".gw-side", ".am-side",            # 三个侧栏
        ".am-tab", ".lw-cat",                          # 标签页
        ".tbl-scroll", ".tbl-head", ".tbl-row",        # 表格
        ".lw-modal-box", ".am-modal-box", ".am-modal-head",  # 弹窗
        ".am-sim-runbar", ".am-sim-zsec", ".am-sim-prrow",   # 模拟器
        ".am-sim-log", ".am-sim-detailcell",                 # 逐发日志
        ".hud button", ".statusbar",                   # 地图周边
        "::-webkit-scrollbar",                          # 滚动条
    ]
    missing = [n for n in need if n not in css]
    assert not missing, "主题层缺组件：%s" % missing


def test_main_styles_untouched_for_layout_contracts():
    """style.css 里被测试依赖的布局契约仍在（换肤不得改动主样式）。"""
    css = _read(STYLE)
    assert ".am-sim-runbar" in css and "position: sticky" in css
    assert "max-height: calc(100vh - 168px)" in css
    assert ".loadout-workbench .lw-cell" in css
    assert ".am-workbench .am-sim-log" in css
