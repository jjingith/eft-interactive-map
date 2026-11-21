# -*- coding: utf-8 -*-
"""R302：市场大盘整体暗色主题。

用户诉求：市场大盘一部分 UI 是亮色调，希望整个市场大盘都是暗色调（顶部全局顶栏除外，
用户明确要求保持亮色）。

做法：market.css 配色全走 --ui-* 令牌（design-tokens 是 XP 浅色桥接值），
所以新增 styles/market-dark.css，在 #market-view 作用域内重定义令牌为暗色，
不改 market.css 一行、不影响其它视图。另补少数裸色（斑马纹 rgba 等）。

不变量：
1. index.html 在 market.css 之后加载 market-dark.css；
2. 暗色令牌定义在 #market-view 作用域（不污染全局、不碰顶栏）；
3. 覆盖 market.css 实际用到的主要令牌；
4. 保留全局顶栏亮色（作用域不含 .app-menubar / .view-toolbar）。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
DARK = ROOT / "styles" / "market-dark.css"
MARKET = ROOT / "market.css"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_dark_layer_loaded_after_market_css():
    html = read(INDEX)
    i_market = html.index("market.css")
    i_dark = html.index("market-dark.css")
    assert i_dark > i_market, "market-dark.css 必须在 market.css 之后加载"


def test_tokens_scoped_to_market_view_only():
    css = read(DARK)
    assert "#market-view {" in css, "暗色令牌必须限定在 #market-view 作用域"
    # 不能有 :root / html 全局定义（否则会污染其它视图与顶栏）
    assert ":root" not in css
    assert "html body" not in css.split("#market-view {")[0]
    # 明确不碰顶栏（顶栏类不在本文件里）
    for bar in [".app-menubar", ".view-toolbar"]:
        # 允许在注释里说明，但不能作为选择器出现
        assert bar + " {" not in css and bar + "{" not in css, \
            "顶栏应保持亮色，不得在此改：%s" % bar


def test_covers_market_tokens():
    css = read(DARK)
    market = read(MARKET)
    # market.css 用到的令牌，暗色层应覆盖（面/文字/边框/状态/渐变）
    for tok in [
        "--ui-color-surface:", "--ui-color-surface-alt:",
        "--ui-color-surface-raised:", "--ui-color-surface-inset:",
        "--ui-color-text:", "--ui-color-text-muted:",
        "--ui-color-border:", "--ui-color-border-soft:",
        "--ui-color-selected-bg:", "--ui-color-warning-bg:",
        "--ui-grad-face-a:", "--ui-grad-head-a:",
    ]:
        assert tok in css, "暗色层缺少令牌：%s" % tok
    # 斑马纹裸色覆盖
    assert "nth-child(even)" in css and "rgba(255, 255, 255, .03)" in css


def test_dark_color_actually_dark():
    css = read(DARK)
    # 主面/交替面必须是深色（RGB 各通道 < 80）
    import re
    for tok, val in re.findall(r"(--ui-color-surface(?:-alt)?):\s*(#[0-9a-fA-F]{6})", css):
        r, g, b = int(val[1:3], 16), int(val[3:5], 16), int(val[5:7], 16)
        assert max(r, g, b) < 80, "%s 应为深色，实际 %s" % (tok, val)
