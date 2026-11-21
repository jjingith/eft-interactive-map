# -*- coding: utf-8 -*-
"""R291：大盘六榜（48h 涨/跌 + 24h 涨/跌 + 热卖 + 趋势）+ 涨跌幅异常治理。

上游 changeLast48hPercent 偶发极端脏值（某配件 +4496%、涨跌额 144 万），
榜单改用云端 /v1/prices/series 的真实采样点重算，并对异常值设上限。
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 后端
def test_bff_offers_route_registered():
    src = read("tools/serve.py")
    assert 'if path == "/api/market-offers":' in src
    assert "cloud_market.offers_history" in src


def test_offers_history_cold_start_is_null_not_zero(tmp_path):
    import cloud_market as cm
    os.environ["EFT_PRICE_ROOT"] = str(tmp_path)
    try:
        d = cm.offers_history(str(tmp_path), "regular", ["a", "b"], hours=24)
    finally:
        os.environ.pop("EFT_PRICE_ROOT", None)
    assert d["ok"] is True and d["status"] == "cold_start"
    assert d["items"]["a"] == {"current": None, "peak": None, "samples": 0, "points": []}
    assert "非成交量" in d["note"]


# ---------------------------------------------------------------- 前端
def test_six_boards_and_required_columns():
    js = read("js/market-board.js")
    for key in ("gainers48", "losers48", "gainers24", "losers24", "hot", "trend"):
        assert '"' + key + '"' in js, "缺榜单 %s" % key
    # 用户指定的列顺序
    assert "过去48h均价" in js and "过去24h均价" in js
    assert "当前价格" in js and "在售数量" in js
    assert "售卖数量" in js and "过去24h峰值数量" in js
    assert "过去七天价格" in js and "七天均价" in js and "七天价格榜" in js
    assert "当前售卖价格" in js
    # R19.71：四个涨跌榜都有价格曲线（固定在涨跌幅与在售数量之间），热卖榜有 24h 数量曲线
    assert "价格曲线" in js and "24h 数量曲线" in js
    assert "seriesWindow(row.points || [], winHours)" in js
    assert "points: o.points || []" in js
    assert 'sparkSvg(row.points || [], 132, 24)' in js


def test_rank_values_recomputed_from_real_series():
    js = read("js/market-board.js")
    assert "api/cloud/prices/series" in js
    assert "function enrichRanks(" in js
    assert "seriesWindow(" in js
    assert "api/market-offers" in js
    # 均价用窗口内真实采样点求平均，不用上游 avg24hPrice 冒充 48h 均价
    assert "reduce(function (x, y)" in js or "reduce(function (a, b)" in js


def test_absurd_upstream_percent_is_filtered():
    js = read("js/market-board.js")
    assert "MAX_PLAUSIBLE_PCT = 1000" in js
    assert "plausible(r, field)" in js
    assert "changeLast48hPercent" in js, "异常来源应被注释说明"


def test_trend_uses_seven_day_spark():
    js = read("js/market-board.js")
    assert "function sparkSvg(" in js
    assert "sparkSvg(row.points, 132, 24)" in js
    assert "&days=7" in js


def test_style_has_six_board_rules():
    css = read("market.css")
    for token in (".mb-table-hot", ".mb-table-trend", ".mb-table-spark",
                  ".mb-spark-cell", ".mb-rank-tabs { flex-wrap: wrap; }"):
        assert token in css, "缺样式 %s" % token


def test_rank_cards_order_is_trend_hot_24h_48h():
    """R19.74：六个榜单全部展开（不再用窄屏 Tab 折叠），顺序为 七天价格 → 热卖 → 24h → 48h。"""
    js = read("js/market-board.js")
    # 卡片顺序
    cards = [js.index('rankCard("trend")'), js.index('rankCard("hot")'),
             js.index('rankCard("gainers24")'), js.index('rankCard("losers24")'),
             js.index('rankCard("gainers48")'), js.index('rankCard("losers48")')]
    assert cards == sorted(cards), cards
    # 不再有窄屏折叠 Tab / 隐藏逻辑
    assert "data-rank-tab" not in js
    assert "is-hidden-narrow" not in js
    assert "switchRankTab" not in js
    # 每个榜单只显示 10 条
    assert ".slice(0, 10)" in js


def test_sector_chips_use_game_handbook_categories():
    """R19.69：板块分类按游戏内十个分类展示，不再按 tpl 父类型拆碎。"""
    js = read("js/market-board.js")
    for label in ("交换物品", "情报物品", "容器", "钥匙", "装备",
                  "武器", "配件", "弹药", "医疗", "饮食"):
        assert label in js, "缺游戏分类：%s" % label
    for stale in ("武器配件", "食品饮料", "投掷物", "头饰", "武器预设"):
        assert stale not in js, "旧的碎片分类仍在：%s" % stale
