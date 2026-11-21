# -*- coding: utf-8 -*-
"""R218：市场页历史价格曲线（真实采集快照，不插值、不补点）。

分两层验证：
1. `tools/price_history.py` 的序列口径：排序、模式过滤、时间窗、缺物品、缺口不补点；
2. 前端契约：市场页只认 `api/price-history`，没有样本就明说，不拿当前价冒充历史。
"""
from __future__ import annotations

import datetime
import json
import os

import pytest

import price_history

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = datetime.timezone(datetime.timedelta(hours=8))


@pytest.fixture(autouse=True)
def _isolate_collector(tmp_path, monkeypatch):
    """R222：本文件只测 `data/flea-price-history/` 这一路来源。

    采集器快照库（`%LOCALAPPDATA%\\EFTPrice`）是真机数据，必须显式关掉，
    否则这些用例会读到开发机上的 78 份真实快照。采集器那一路由
    `test_r222_collector_history.py` 用临时目录覆盖。
    """
    empty = tmp_path / "no-collector"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("EFT_PRICE_ROOT", str(empty))
    price_history.clear_cache()
    yield
    price_history.clear_cache()


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


def _write_snapshot(root: str, name: str, when: str, game_mode: str, items: dict) -> dict:
    directory = os.path.join(root, "data", "flea-price-history")
    os.makedirs(directory, exist_ok=True)
    day = when[:10]
    doc = {
        "schema": 1,
        "date": day,
        "snapshotAt": when,
        "gameMode": game_mode,
        "priceMode": "pvp",
        "items": items,
    }
    with open(os.path.join(directory, name), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return {
        "file": name,
        "date": day,
        "snapshotAt": when,
        "gameMode": game_mode,
        "priceMode": "pvp",
    }


def _write_index(root: str, entries: list) -> None:
    directory = os.path.join(root, "data", "flea-price-history")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "updatedAt": entries[-1]["snapshotAt"],
                   "keepDays": 90, "entries": entries}, f, ensure_ascii=False)


def _root(tmp_path) -> str:
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "data"), exist_ok=True)
    price_history.clear_cache()
    return root


def test_series_returns_real_points_in_time_order(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-09T060000.json", "2026-11-09T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1200, "a": 1400}}),
        _write_snapshot(root, "2026-11-08T060000.json", "2026-11-08T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1000, "a": 1300}}),
    ]
    _write_index(root, list(reversed(entries)))

    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    series = out["series"]["item-a"]
    assert [p[0] for p in series["points"]] == ["2026-11-08T06:00:00+08:00",
                                                "2026-11-09T06:00:00+08:00"]
    assert [p[1] for p in series["points"]] == [1000, 1200]
    assert series["low"] == 1000 and series["high"] == 1200
    assert out["coverageDays"] == 2


def test_series_does_not_interpolate_missing_snapshots(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-07T060000.json", "2026-11-07T06:00:00+08:00",
                        "regular", {"item-a": {"l": 900, "a": 950}}),
        _write_snapshot(root, "2026-11-09T060000.json", "2026-11-09T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1100, "a": 1150}}),
    ]
    _write_index(root, entries)

    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    points = out["series"]["item-a"]["points"]
    assert len(points) == 2, "中间缺的那天不能补一个假点"
    assert points[0][0] == "2026-11-07T06:00:00+08:00"
    assert points[1][0] == "2026-11-09T06:00:00+08:00"


def test_series_filters_by_game_mode(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-08T060000.json", "2026-11-08T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1000}}),
        _write_snapshot(root, "2026-11-09T060000.json", "2026-11-09T06:00:00+08:00",
                        "pve", {"item-a": {"l": 2000}}),
    ]
    _write_index(root, entries)

    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    assert out["snapshotsUsed"] == 1
    assert out["series"]["item-a"]["points"] == [["2026-11-08T06:00:00+08:00", 1000, None]]


def test_series_respects_days_window(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-01T060000.json", "2026-11-01T06:00:00+08:00",
                        "regular", {"item-a": {"l": 500}}),
        _write_snapshot(root, "2026-11-09T060000.json", "2026-11-09T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1100}}),
    ]
    _write_index(root, entries)

    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    assert out["snapshotsUsed"] == 1
    assert out["series"]["item-a"]["count"] == 1
    assert out["series"]["item-a"]["points"][0][1] == 1100


def test_series_reports_items_without_price(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-08T060000.json", "2026-11-08T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1000}}),
        _write_snapshot(root, "2026-11-09T060000.json", "2026-11-09T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1000}, "item-b": {"u": "x"}}),
    ]
    _write_index(root, entries)

    out = price_history.series(root, "regular", ["item-a", "item-b", "item-c"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    assert "item-b" in out["missing"]
    assert "item-c" in out["missing"]
    assert "item-b" not in out["series"]
    assert "item-c" not in out["series"], "没有快照的物品不能凭当前价造一条线"


def test_series_is_empty_without_index(tmp_path):
    root = _root(tmp_path)
    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    assert out["ok"] is True
    assert out["snapshotsUsed"] == 0
    assert out["series"] == {}
    assert out["error"] == "no-index"


def test_series_caps_requested_items(tmp_path):
    root = _root(tmp_path)
    ids = ["i%d" % i for i in range(80)]
    out = price_history.series(root, "regular", ids, 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    assert len(out["requested"]) == price_history.MAX_ITEMS


def test_serve_exposes_price_history_route():
    serve = _read("tools/serve.py")
    assert '"/api/price-history"' in serve
    assert "def _handle_price_history" in serve
    assert "price_history.series(" in serve
    assert "import price_history" in serve


def test_market_js_reads_history_from_local_api_only():
    js = _read("js/market.js")
    assert '"api/price-history?mode="' in js
    assert "fetch(url, { cache: \"no-store\" })" in js
    # 旧占位文案必须消失：不能一边说「积累中」一边又有真曲线
    assert "数据积累中" not in js
    # 反伪造：断档处分段起笔不连线、单点不拉横贯线冒充趋势、缺口不补点
    assert "function histSegments(times, gapMs)" in js
    assert '(k ? "L" : "M")' in js
    assert "mk-hist-single-line" not in js
    # R225：图下一律不显示解释文案（用户明确要求去掉），口径说明也不再写死在这里
    assert "不是逐笔成交" not in js
    assert "没有样本的时间段不画线" not in js


def test_market_history_svg_is_pure_svg_without_new_dependency():
    js = _read("js/market.js")
    assert 'out.push(\'<svg class="mk-hist-svg ' in js
    assert "mk-hist-line" in js and "mk-hist-area" in js
    assert "plotly" not in js.lower()
    assert "chart.js" not in js.lower()
    assert "d3." not in js


def test_market_css_defines_history_chart():
    css = _read("market.css")
    for cls in (".mk-hist-wrap", ".mk-hist-svg", ".mk-hist-line", ".mk-hist-area",
                ".mk-hist-tip", ".mk-hist-range"):
        assert cls + " {" in css or cls + "," in css or cls + " " in css, cls
    # R225：单点的全宽参考线已删除（没有文字解释时会被读成「价格一直没变」）
    assert ".mk-hist-single-line" not in css
    assert ".mk-hist-svg.is-up { color: #b3261e; }" in css, "涨用红"
    assert ".mk-hist-svg.is-down { color: #1a7f37; }" in css, "跌用绿"


def test_history_payload_has_no_fabricated_fields(tmp_path):
    root = _root(tmp_path)
    entries = [
        _write_snapshot(root, "2026-11-08T060000.json", "2026-11-08T06:00:00+08:00",
                        "regular", {"item-a": {"l": 1000}}),
    ]
    _write_index(root, entries)
    out = price_history.series(root, "regular", ["item-a"], 7,
                               now=datetime.datetime(2026, 11, 9, 12, 0, tzinfo=TZ))
    point = out["series"]["item-a"]["points"][0]
    assert point[2] is None, "缺失的 24h 均价必须是 null，不能拿最近低价顶替"
    assert isinstance(point[0], str) and point[0].endswith("+08:00")
