"""R307：小工具提升为一级视图 + 市场列表改用全量物品 + 更新页回声宽限。

三块改动各自锁一遍：
1. 小工具不再是顶栏下拉菜单，而是与地图 / 配装同级的第 8 个视图；
2. 市场列表以 items.json 全量为基准渲染（BTC 等没上架跳蚤的也要能搜到），
   无报价行用空报价占位 + 「无报价」徽记，不让渲染层到处判空；
3. 点「更新」/「小工具」后，服务端旧配置回声不能把视图顶回去。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 小工具视图
def test_tools_is_a_top_level_view_not_a_menu():
    html = _read("index.html")
    app = _read("app.js")

    assert 'id="view-btn-tools"' in html and 'data-view="tools"' in html
    assert 'id="tools-view"' in html
    # 下拉菜单形态必须彻底消失，否则两套入口会打架
    assert 'id="am-tools"' not in html
    assert 'id="am-tools-panel"' not in html
    assert 'app-tools-panel' not in html

    assert '"tools"' in app
    assert 'el.toolsView = $("tools-view")' in app
    assert "tools: el.toolsView" in app
    assert "window.GWTools.mount()" in app


def test_tools_view_layout_has_list_and_panes():
    html = _read("index.html")
    start = html.index('id="tools-view"')
    block = html[start:html.index("</section>", start)]

    assert 'class="tl-item' in block
    assert block.count('class="tl-item') == 2
    assert 'data-tool="mini"' in block and 'data-tool="ocr"' in block
    assert 'id="tool-pane-mini"' in block and 'id="tool-pane-ocr"' in block
    assert 'id="am-mini-panel"' in block and 'id="am-ocr-panel"' in block
    # 为以后扩展留的说明
    assert "新增的小工具" in block
    # 小地图在前、价格识别在后（与用户熟悉的顺序一致）
    assert block.index("am-mini-panel") < block.index("am-ocr-panel")


def test_tools_view_is_deep_linkable():
    app = _read("app.js")
    assert 'location.hash === "#tools"' in app
    assert 'setView("tools", false)' in app


def test_tools_module_switches_panes_and_remembers_choice():
    js = _read("js/tools-view.js")
    assert "window.GWTools = {" in js
    assert "data-tool-pane" in js
    assert "eftmap.tools" in js, "刷新后应该回到上次用的工具"
    assert "ArrowDown" in js and "ArrowUp" in js


def test_tools_css_is_scoped_and_hides_market_controls():
    css = _read("styles/tools.css")
    assert "#tools-view" in css
    assert ".tl-item.is-active" in css
    assert "html body .tl-pane .app-menu-panel" in css, "嵌套下拉面板的定位/位图边框必须中和"
    changes = _read("styles/changes.css")
    assert 'body[data-view="tools"] #vt-prices' in changes
    assert 'body[data-view="tools"] #vt-market-meta' in changes


# ---------------------------------------------------------------- 市场全量物品
def test_market_rows_are_built_from_all_items():
    js = _read("js/market.js")
    assert "function emptyQuote()" in js
    assert "Object.keys(items).forEach" in js, "必须以全量物品为基准"
    assert "Object.keys(fItems).forEach" not in js, "不能再只遍历有行情的条目"
    assert 'rec.pt === "Preset"' in js, "枪械预设不是实体物品"
    assert "hasQuote: hasQuote" in js


def test_market_row_marks_missing_quote():
    js = _read("js/market.js")
    assert "mk-noquote" in js
    assert "无报价" in js
    assert "有报价 " in js, "统计文案要区分全量与有报价"
    css = _read("market.css")
    assert ".mk-noquote" in css


# ---------------------------------------------------------------- 视图回声宽限
def test_view_switch_ignores_stale_config_echo():
    app = _read("app.js")
    assert "var lastViewSwitchAt = 0;" in app
    assert "lastViewSwitchAt = Date.now();" in app
    assert "Date.now() - lastViewSwitchAt > SELF_ECHO_GRACE" in app, \
        "本地刚切视图后，服务端旧回声不能把视图顶回去"
    assert "/^#(tasks|stories|changes|tools)/" in app
