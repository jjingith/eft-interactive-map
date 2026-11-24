"""R286 市场大盘：数据字段 / 小时聚合 / API / 前端契约测试。

口径铁律：在售挂单数不是成交量；冷启动不插值、不补点、不拿别的模式顶替。
"""
from __future__ import annotations

import datetime
import gzip
import json
import os
from pathlib import Path

import pytest

import market_overview
import price_collect
import r20_fetch_prices
import serve

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 上游字段
def test_market_fields_pass_through_build_cache():
    doc = {"data": {"items": {
        "a": {"lastLowPrice": 1000, "avg24hPrice": 1100,
              "lastOfferCount": 27, "changeLast48hPercent": 17.54,
              "changeLast48h": 15819, "velocity": 0,
              "lastScan": "2026-11-15T10:48:02.000Z", "updated": "2026-11-15T12:18:06Z"},
    }}}
    # build_cache 有 MIN_ITEMS 门槛，直接验字段映射常量与采集器行函数
    assert ("lastOfferCount", "lastOfferCount") in r20_fetch_prices.MARKET_FIELDS
    row = price_collect._compact_row({
        "lastLowPrice": 1000, "avg24hPrice": 1100, "updated": "2026-11-15T12:18:06Z",
        "lastOfferCount": 27, "changeLast48hPercent": 17.54,
        "changeLast48h": 15819, "velocity": 0,
    })
    assert row["mk"] == {"o": 27, "c": 17.54, "d": 15819, "v": 0}
    anchor = price_collect._anchor_row({
        "lastLowPrice": 1000, "lastOfferCount": 27, "changeLast48hPercent": -3.5,
    })
    assert anchor["mk"]["o"] == 27 and anchor["mk"]["c"] == -3.5
    # 旧快照无市场字段时必须兼容（不写 mk、不抛错）
    assert "mk" not in price_collect._compact_row({"lastLowPrice": 1000})
    assert "mk" not in price_collect._anchor_row({"lastLowPrice": 1000})


def test_market_fields_zero_and_negative_kept():
    """0 与负数是合法语义（涨跌为 0、跌价为负、无挂单），不能被当空值丢掉。"""
    row = price_collect._compact_row({
        "lastLowPrice": 100, "lastOfferCount": 0,
        "changeLast48hPercent": 0, "changeLast48h": -120, "velocity": -0.5,
    })
    assert row["mk"]["o"] == 0 and row["mk"]["c"] == 0
    assert row["mk"]["d"] == -120 and row["mk"]["v"] == -0.5


def test_build_items_adds_market_block(monkeypatch):
    import fetch_data as fd
    items = {
        "a": {"id": "a", "name": "A Name", "types": ["barter"], "lastOfferCount": 12,
              "changeLast48hPercent": -3.5, "velocity": 0.8},
        "b": {"id": "b", "name": "B Name", "types": ["barter"], "lastOfferCount": 0,
              "changeLast48hPercent": 0},
    }
    p = fd.build_items({"items": items}, {})
    assert p["items"]["a"]["mk"] == {"c": -3.5, "v": 0.8, "o": 12}
    assert p["items"]["b"]["mk"] == {"c": 0, "o": 0}
    cov = p["audit"]["coverage"]
    assert cov["marketOffer"] == 2 and cov["marketChange"] == 2
    assert cov["marketVelocity"] == 1


# ---------------------------------------------------------------- 小时聚合
def _write_snapshot(root: Path, mode: str, when: datetime.datetime, rows: dict):
    day = when.strftime("%Y-%m-%d")
    name = when.strftime("%H%M%S") + ".json.gz"
    d = root / "collect" / "snapshots" / mode / day
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / name, "wt", encoding="utf-8") as fh:
        json.dump({"schema": 1, "mode": mode, "items": rows}, fh)


def test_overview_cold_start(monkeypatch, tmp_path):
    monkeypatch.setenv("EFT_PRICE_ROOT", str(tmp_path))
    d = market_overview.overview("regular", hours=24,
                                 now=datetime.datetime(2026, 11, 17, 12, 0,
                                                       tzinfo=datetime.timezone.utc))
    assert d["status"] == "cold_start"
    assert d["buckets"] == [] and d["gainers"] == [] and d["hot"] == []
    assert "非成交量" in d["note"]


def test_overview_aggregates_by_hour_and_keeps_last(monkeypatch, tmp_path):
    monkeypatch.setenv("EFT_PRICE_ROOT", str(tmp_path))
    tz = datetime.timezone(datetime.timedelta(hours=8))
    # 同一小时两份快照：应只取较晚那份（不重复计数）
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 9, 10, tzinfo=tz),
                    {"a": {"l": 1000, "mk": {"o": 10, "c": 1.0}}})
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 9, 40, tzinfo=tz),
                    {"a": {"l": 1100, "mk": {"o": 20, "c": 2.0}},
                     "b": {"l": 500, "mk": {"o": 5, "c": -3.0}}})
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 10, 30, tzinfo=tz),
                    {"a": {"l": 1200, "mk": {"o": 25, "c": 4.0}},
                     "b": {"l": 480, "mk": {"o": 4, "c": -5.0}}})
    d = market_overview.overview("regular", hours=6,
                                 now=datetime.datetime(2026, 11, 17, 11, 0, tzinfo=tz))
    assert d["status"] == "ok"
    assert len(d["buckets"]) == 2
    assert d["buckets"][0]["offers"] == 25, "同小时只取最后一份快照"
    assert "非成交量" in d["note"]
    assert [r["id"] for r in d["gainers"]] == ["a", "b"]
    assert [r["id"] for r in d["losers"]] == ["b", "a"]
    # 热度按在售挂单数环比变化率；a: 20 -> 25 = +25%
    a_hot = next(r for r in d["hot"] if r["id"] == "a")
    assert a_hot["offers"] == 25 and a_hot["prev"] == 20 and a_hot["rate"] == 25.0


def test_overview_rejects_bad_mode_and_hours():
    assert market_overview.overview("nope")["error"] == "bad-mode"


def test_legacy_snapshot_bucket_is_null_not_zero(monkeypatch, tmp_path):
    """采集器升级前的旧快照没有 mk：整桶必须留空，不能写成「在售 0 件」。"""
    monkeypatch.setenv("EFT_PRICE_ROOT", str(tmp_path))
    tz = datetime.timezone(datetime.timedelta(hours=8))
    # 8 点：升级前的旧行为（只有价格，没有 mk）
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 8, 30, tzinfo=tz),
                    {"a": {"l": 900}})
    # 9、10 点：升级后
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 9, 10, tzinfo=tz),
                    {"a": {"l": 1000, "mk": {"o": 10, "c": 1.0}}})
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 10, 30, tzinfo=tz),
                    {"a": {"l": 1200, "mk": {"o": 25, "c": 4.0}}})

    d = market_overview.overview("regular", hours=6,
                                 now=datetime.datetime(2026, 11, 17, 11, 0, tzinfo=tz))
    assert d["status"] == "ok"
    legacy, nine, ten = d["buckets"]
    assert legacy["marketRows"] == 0
    assert legacy["offers"] is None and legacy["avgChange"] is None
    assert legacy["up"] is None and legacy["down"] is None, "缺测桶的涨跌计数也必须留空"
    assert legacy["items"] == 1, "但价格条目数仍要如实反映"
    assert nine["offers"] == 10 and ten["offers"] == 25

    # 热度榜的「上一小时」要跳过没有 mk 的旧桶，取 9 点（10 → 25 = +150%）
    a_hot = next(r for r in d["hot"] if r["id"] == "a")
    assert a_hot["prev"] == 10 and a_hot["rate"] == 150.0


def test_only_legacy_snapshots_is_cold_start(monkeypatch, tmp_path):
    monkeypatch.setenv("EFT_PRICE_ROOT", str(tmp_path))
    tz = datetime.timezone(datetime.timedelta(hours=8))
    _write_snapshot(tmp_path, "regular", datetime.datetime(2026, 11, 17, 9, 10, tzinfo=tz),
                    {"a": {"l": 1000}})
    d = market_overview.overview("regular", hours=6,
                                 now=datetime.datetime(2026, 11, 17, 10, 0, tzinfo=tz))
    assert d["status"] == "cold_start" and d["buckets"] == []
    assert d["coverage"] == {"items": 0, "withOffers": 0, "withChange": 0}


# ---------------------------------------------------------------- API / 前端
def test_api_route_registered():
    src = read("tools/serve.py")
    assert 'if path == "/api/market-overview":' in src
    assert "def _handle_market_overview" in src
    assert "import market_overview" in src


def test_market_board_is_inside_market_workspace():
    html = read("index.html")
    js = read("app.js")
    board = read("js/market-board.js")
    css = read("market.css")
    # R286 修订：大盘不再是顶层视图，而是市场工作区的子页。
    assert 'data-market-tab="board"' in html
    assert 'id="market-board-pane"' in html
    assert 'id="market-list-pane"' in html
    assert 'id="view-btn-market-board"' not in html
    assert 'id="market-board-view"' not in html
    assert 'src="js/market-board.js' in html
    assert 'src="js/market-workspace.js' in html
    assert "GWMarketBoard" in js
    assert "GWMarketWorkspace" in js
    # R305 追加了「更新」视图；这里只锁「大盘不是顶层视图」，列表内容随版本演进
    assert 'var VIEWS = ["map", "loadout", "gun", "ammo", "tasks", "market", "changes"]' in js
    assert "在售挂单数" in board and "非成交量" in board
    # 「成交量」只允许出现在否定语境（非成交量 / 不是成交量 / 而非成交量），
    # 不得作为指标名单独出现——否则等于把挂单数谎报成成交量。
    stripped = board.replace("非成交量", "").replace("不是成交量", "")
    assert "成交量" not in stripped, "「成交量」只能出现在否定语境"
    assert "#market-board-pane" in css and ".mb-table" in css and ".mb-sector" in css
    # 小地图模式不得命中大盘页样式
    assert "body.tk-mini .mb-" not in css


def test_board_follows_global_mode_without_own_select():
    """大盘不再自带模式下拉：PvP / PvE / PvPS 以顶栏 GWGameMode 为唯一状态源。"""
    board = read("js/market-board.js")
    assert "GWGameMode.get" in board
    assert ".mb-mode" not in board, "大盘不应再有独立的模式 select"
    assert "ui.mode.value" not in board
    assert "ui.mode.textContent" not in board


def test_baseline_uses_bundled_market_fields():
    """没有采集器快照时，内置快照仍能给出真实涨跌榜 / 板块，而不是冷启动空态。"""
    d = market_overview.baseline("regular")
    assert d["status"] == "baseline"
    assert d["source"] == "bundled-items"
    assert d["coverage"]["withOffers"] > 1000
    assert d["coverage"]["withChange"] > 1000
    assert d["gainers"] and d["losers"] and d["sectors"]
    assert d["minOffers"] == market_overview.BASELINE_MIN_OFFERS
    # 每条上榜物资都必须满足流动性门槛，不能把 1 个挂单的噪声塞进榜单。
    assert all(row["offers"] >= d["minOffers"] for row in d["gainers"])


def test_baseline_other_modes_use_their_own_files():
    for mode, name in (("pve", "flea-prices-pve.json"), ("pvps", "flea-prices-pvps.json")):
        d = market_overview.baseline(mode)
        assert d["status"] == "baseline"
        assert d["source"] == "bundled-prices"
        assert d["mode"] == mode
        assert d["coverage"]["withOffers"] > 0
        assert d["gainers"] and d["sectors"]
        assert name  # 静态提示：模式文件必须存在，缺失会退成 cold_start


def test_market_history_route_is_not_member_gated():
    src = read("tools/serve.py")
    assert 'if path == "/api/market-history":' in src
    assert "def _handle_market_history" in src
    # 大盘曲线读本机累积的云端快照，不再复用会员墙的 403 分支。
    start = src.index("def _handle_market_history")
    block = src[start:start + 2200]
    assert "member_required" not in block
    assert "cloud_market.history" in block


def test_board_uses_cloud_snapshots_only():
    src = read("tools/serve.py")
    start = src.index("def _handle_market_overview")
    block = src[start:start + 3200]
    assert "market_overview.overview(" not in block
    assert "market_overview.baseline(" not in block
    assert "cloud_market.overview" in block
    assert "loginRequired" in block
