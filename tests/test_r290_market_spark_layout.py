# -*- coding: utf-8 -*-
"""R290：市场列表「历史 72h」缩略曲线 + 市场大盘板块重叠修复。

两条都是「看得见」的问题，静态契约负责锁住接线与布局规则，
真实取数由 /api/cloud/prices/series → 云端 /v1/prices/series 提供。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 历史曲线
def test_bff_route_forwards_cloud_series():
    src = read("tools/serve.py")
    assert 'if path == "/api/cloud/prices/series":' in src
    assert "cloud_client.prices_series" in src
    # 未登录 / 非会员必须原样回 401/403，让前端显示「会员功能」而不是假曲线
    assert "return self._cloud_call(cloud_client.prices_series" in src


def test_cloud_client_caps_ids_at_12():
    src = read("tools/cloud.py")
    assert "def prices_series(" in src
    assert 'CLOUD_BASE + "/prices/series' in src
    assert "ids[:12]" in src


def test_market_row_marks_hist_cell_and_draws_spark():
    js = read("js/market.js")
    assert 'td.className = "mk-col-hist";' in js
    assert 'td.setAttribute("data-id", row.id);' in js, "历史列必须带物品 id 才能批量补绘"
    assert "function loadHistSparks(" in js
    assert "function drawHistSpark(" in js
    assert 'className = "mk-spark"' in js
    assert "loadHistSparks();" in js, "表格渲染完必须触发异步补绘"


def test_no_fake_history_and_honest_fallbacks():
    js = read("js/market.js")
    # 老实现把整列硬编码成「积累中」；现在只允许作为失败/空态文案出现
    assert 'badge.textContent = "积累中"' not in js, "历史列不得再出现误导性的「积累中」占位"
    assert "历史 72h 曲线属于后续块" not in js
    assert '"读取中…"' in js, "异步补绘前应有明确的加载占位"
    for token in ('"1 点"', '"会员功能"', '"—"', "不插值、不画假线"):
        assert token in js, "缺诚实兜底文案：%s" % token
    # 切模式 / 重绘时让在途请求失效，避免把旧模式曲线画到新模式上
    assert "histToken++" in js and "token !== histToken" in js


def test_hist_spark_style_scoped():
    css = read("market.css")
    assert ".mk-col-hist .mk-spark" in css
    assert "width: 68px; height: 22px" in css


# ---------------------------------------------------------------- 大盘布局
def test_board_blocks_do_not_shrink():
    """重叠根因：flex 子项被压到 min-height:0，内部 canvas/表格仍占高 → 溢出遮挡。"""
    css = read("market.css")
    for selector in (".mb-terminal > .mb-head", ".mb-terminal > .mb-kpis",
                     ".mb-terminal > .mb-main", ".mb-terminal > .mb-lower",
                     ".mb-terminal > .mb-sector-card"):
        assert selector in css, "板块缺不收缩规则：%s" % selector
    assert "flex: 0 0 auto;" in css
    for label in (".mb-chart-card { min-height:", ".mb-watch-card { min-height:",
                  ".mb-rank-card { min-height:", ".mb-sector-card { min-height:"):
        assert label in css, "板块缺高度下限：%s" % label


def test_board_scroll_containers_have_caps():
    css = read("market.css")
    assert ".mb-table-wrap { max-height:" in css
    assert ".mb-sectors { max-height:" in css
