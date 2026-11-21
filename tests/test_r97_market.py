# -*- coding: utf-8 -*-
"""R97 市场模块：抓取器扩展（updated / minLevelForFlea / meta / 历史归档 / 7 日均价）
与前端静态边界。"""

import datetime
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import r20_fetch_prices as f  # noqa: E402


def _items(n, price=1000, lv=30, updated="2026-11-08T04:00:00Z"):
    out = {}
    for i in range(n):
        out["id%03d" % i] = {
            "lastLowPrice": price + i,
            "avg24hPrice": price + 100 + i,
            "low24hPrice": price - 10 + i,
            "high24hPrice": price + 200 + i,
            "basePrice": price - 100 + i,
            "updated": updated,
            "minLevelForFlea": lv,
        }
    return out


def _payload(items=None, day="2026-11-08", at="2026-11-08T14:00:00+08:00"):
    return {
        "schema": 1,
        "source": "https://example.invalid/regular/items",
        "gameMode": "regular",
        "priceMode": "pvp",
        "lastSuccessAt": at,
        "localDate": day,
        "meta": {
            "generatedAt": "2026-11-08T06:00:00Z",
            "sourceUpdatedMax": "2026-11-08T04:00:00Z",
            "generatedAtLocal": at,
        },
        "counts": {"itemsWithPrice": len(items or {})},
        "items": items or {},
    }


def test_build_cache_carries_updated_and_min_level(monkeypatch):
    monkeypatch.setattr(f, "MIN_ITEMS", 1)
    monkeypatch.setattr(f, "MIN_PRICED", 1)
    now = datetime.datetime(
        2026, 11, 8, 14, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
    )
    payload = f.build_cache({"data": {"items": _items(2)}}, "https://x", "regular", now=now)
    row = payload["items"]["id000"]
    assert row["updated"] == "2026-11-08T04:00:00Z"
    assert row["minLevelForFlea"] == 30
    assert row["fetchedAt"] == "2026-11-08T14:00:00+08:00"
    assert payload["meta"]["generatedAt"] == "2026-11-08T06:00:00Z"
    assert payload["meta"]["sourceUpdatedMax"] == "2026-11-08T04:00:00Z"
    assert payload["counts"]["withUpdated"] == 2
    assert payload["counts"]["withMinLevel"] == 2


def test_build_cache_source_updated_max_is_max_not_last(monkeypatch):
    monkeypatch.setattr(f, "MIN_ITEMS", 1)
    monkeypatch.setattr(f, "MIN_PRICED", 1)
    items = _items(2, updated="2026-11-08T01:00:00Z")
    items["id001"]["updated"] = "2026-11-08T05:30:00Z"
    payload = f.build_cache({"data": {"items": items}}, "https://x", "regular")
    assert payload["meta"]["sourceUpdatedMax"] == "2026-11-08T05:30:00Z"


def test_build_cache_drops_invalid_level_and_updated(monkeypatch):
    monkeypatch.setattr(f, "MIN_ITEMS", 1)
    monkeypatch.setattr(f, "MIN_PRICED", 1)
    items = _items(1)
    items["id000"]["minLevelForFlea"] = "30"
    items["id000"]["updated"] = "not-a-time"
    payload = f.build_cache({"data": {"items": items}}, "https://x", "regular")
    row = payload["items"]["id000"]
    assert "minLevelForFlea" not in row
    assert "updated" not in row
    assert payload["meta"]["sourceUpdatedMax"] is None


def test_history_archive_compact_and_index(tmp_path):
    items = _items(2)
    out = str(tmp_path / "flea-prices.json")
    path = f.write_history(_payload(items), out, keep_days=90)
    assert os.path.basename(path) == "2026-11-08T140000.json"
    with open(path, encoding="utf-8") as fh:
        archive = json.load(fh)
    assert archive["items"]["id000"]["l"] == 1000
    assert archive["items"]["id000"]["a"] == 1100
    assert archive["items"]["id000"]["u"] == "2026-11-08T04:00:00Z"
    index = json.load(
        open(
            os.path.join(tmp_path, "flea-price-history", "index.json"),
            encoding="utf-8",
        )
    )
    assert len(index["entries"]) == 1
    assert index["entries"][0]["file"] == os.path.basename(path)


def test_history_prune_keeps_window_and_matching_files(tmp_path):
    out = str(tmp_path / "flea-prices.json")
    extra = tmp_path / "flea-price-history" / "README.txt"
    os.makedirs(extra.parent, exist_ok=True)
    extra.write_text("keep me", encoding="utf-8")

    days = [
        ("2026-11-05", "2026-11-05T10:00:00+08:00"),
        ("2026-11-06", "2026-11-06T10:00:00+08:00"),
        ("2026-11-08", "2026-11-08T10:00:00+08:00"),
    ]
    # 固定「现在」为最后一个快照当天，否则跨过午夜后 cutoff 前移，测试会随系统时间飘。
    now = datetime.datetime(2026, 11, 8, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    for day, at in days:
        f.write_history(_payload(_items(1), day=day, at=at), out, keep_days=3, now=now)

    files = sorted(
        n
        for n in os.listdir(tmp_path / "flea-price-history")
        if f.HISTORY_FILE_RE.match(n)
    )
    assert files == ["2026-11-06T100000.json", "2026-11-08T100000.json"]
    assert extra.exists(), "非本工具命名的文件不能被清理"


def test_avg7_requires_seven_snapshot_days_and_no_interpolation():
    six_days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
    snaps6 = [(d, {"items": {"a": {"l": 100}, "b": {"l": 200}}}) for d in six_days]
    today = {"items": {"a": {"lastLowPrice": 100}, "b": {"lastLowPrice": 200}}}
    assert f.compute_avg7(today, snaps6, "2026-11-07") == {}, "合计 6 个快照日不得计算"

    six_days = [
        "2026-11-01",
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
    ]
    snaps = [(d, {"items": {"a": {"l": 100}, "b": {"l": 200}}}) for d in six_days]
    avg = f.compute_avg7(today, snaps, "2026-11-07")
    assert avg["a"] == 100
    assert avg["b"] == 200

    broken = list(snaps)
    broken[2] = ("2026-11-03", {"items": {"a": {"l": 102}}})
    avg = f.compute_avg7(today, broken, "2026-11-07")
    assert "b" not in avg
    assert "a" in avg


def test_frontend_market_view_and_offline_contract():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()

    assert 'id="view-btn-market"' in html, "市场入口应在工作区导航里"
    assert 'data-view="market"' in html
    assert 'id="market-view"' in html
    build = re.search(r'AM_BUILD = "([^"]+)"', app).group(1).lower()
    assert ("market.css?v=" + build) in html
    assert ("js/market.js?v=" + build) in html

    assert '"market"' in app and "GWMarketData" in app and "market: el.marketView" in app

    assert "GWMarketData" in js
    assert "数据截止" in js
    assert "没有匹配的物品" in js
    assert "积累中" in js
    # R218：历史曲线要读本机采集快照，因此允许本机相对接口请求；
    # 仍然不允许外网地址、不允许 XHR 直连。
    # R234：市场视图新增「截图识别」面板，第二个本机相对接口 api/ocr/recognize
    # （用户拍板的 A 路线）。
    # R279：云端价格缓存条新增 api/price-cache/status 与 api/price-cache/sync
    # 两个本机接口（登录后整包下载、点「获取最新数据」拉增量）。
    # R290：历史 72h 缩略图新增第 5 个 fetch（局部 url 变量 → api/cloud/prices/series）。
    # 护栏保持原意：每个 fetch 的实参要么是 api/ 相对字符串、要么是 url 变量，
    # 白名单写死，杜绝顺手加外网请求。
    assert 'var url = "api/price-history?mode="' in js
    assert 'fetch(url, { cache: "no-store" })' in js
    fetch_args = re.findall(r"fetch\(\s*([^,()]+?)\s*[,)]", js)
    allowed = {'"api/ocr/recognize"', '"api/price-cache/status"', '"api/price-cache/sync"', "url"}
    assert set(fetch_args) <= allowed, "市场页出现未登记的本机接口：%s" % fetch_args
    assert len(fetch_args) == 5, "市场页本机接口请求数量变了：%s" % fetch_args
    assert "api/cloud/prices/series" in js, "历史 72h 缩略图接口接线丢失"
    for arg in fetch_args:
        if arg.startswith('"'):
            assert arg.startswith('"api/'), "非本机相对接口：%s" % arg
        else:
            assert arg == "url", "fetch 实参必须是 url 变量或 api/ 字符串：%s" % arg
    assert "XMLHttpRequest" not in js
    assert "http://" not in js and "https://" not in js

    assert "@media (max-width: 1200px)" in css
    assert "@media (max-width: 870px)" in css
    assert "@media (max-width: 640px)" in css
    assert ".mk-cutoff.is-stale" in css


def test_market_row_actions_and_detail_skeleton():
    """第二块护栏：行内来源/商人图标、选中复制、详情弹窗的 Tabs 与诚实占位。"""
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()

    for key in (
        "Obtain",
        "Uses",
        "Banned",
        "Sell to",
        # R223：Collected 计数（FIR / non-FIR）整块删除，不再要求出现；
        # 「不得复活」的护栏放在下面的第三块与本轮用例里。
        # R218：占位文案「数据积累中」换成了真实状态；诚实边界不变
        "还没有历史快照",
        "不插值、不补点",
        "minLevelForFlea",
        "sellToTrader",
    ):
        assert key in js

    assert "assets/icons-traders/" in js
    assert "navigator.clipboard" in js
    assert "复制所选" in js
    assert "noFlea" in js
    assert ".mk-modal-shade" in css
    assert "flex-direction: column" in css


def test_market_uses_quest_refs_local_counts_and_collapsed_sellto():
    """第三块护栏：Uses 反查任务目标、本机计数标注、Sell to 折叠、过期/装载态。"""
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()

    assert "loadTasks" in app
    assert "api.loadTasks" in js
    assert "data/tasks/tasks." in app

    assert "任务目标" in js and "已检查 " in js
    assert "没有找到引用" in js
    assert "没有针对性引用" in js and "通用目标" in js
    assert "暂不覆盖" in js and "藏身处制作" in js
    # R223：Collected 计数（FIR / non-FIR）整块删除——它只写不读，页面没有
    # 任何地方消费这个数字。原有的「本机计数标注」断言随之反转为「不得复活」。
    assert "仅保存在本机、不跨设备" not in js
    assert "mk-count-hint" not in js and ".mk-count-hint" not in css
    assert "mk-collected" not in js and ".mk-collected" not in css
    assert "data-mk-sellto-toggle" in js
    assert "展开全部 " in js and "收起，只看最高" in js
    assert "is-loading" in js and ".mk-empty.is-loading" in css
    assert "mk-stale" in js and ".mk-stale" in css


def test_market_view_registered_in_server_whitelist():
    """服务端共享配置的 view 白名单必须和前端一致。

    漏掉 market 时前端一点就切过去、随后被配置回填重置回 map，浏览器里看起来像
    「点了没反应」；这一条就是那次回归的护栏。
    """
    import config as server_config

    assert "market" in server_config.VIEWS


def test_market_frontend_uses_derived_short_name_and_level_defaults():
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    assert "shortNameOf" in js
    assert "rec.sn" not in js
    assert "lv: LV_MAX" in js
    assert 'td.className = "mk-col-price"' in js


def test_real_cache_has_market_meta_when_present():
    path = os.path.join(ROOT, "data", "flea-prices.json")
    data = json.load(open(path, encoding="utf-8"))
    meta = data.get("meta")
    if not meta:
        pytest.skip("当前缓存还是旧结构，等待下一次构建期抓取补齐 meta")
    assert meta.get("generatedAt")
    assert meta.get("sourceUpdatedMax")
    row = next(iter(data["items"].values()))
    assert "updated" in row
    assert "minLevelForFlea" in row


def test_market_table_has_no_ops_column():
    """R19.83：去掉最右侧「操作」列；点整行仍能开详情，底部仍可复制所选。"""
    js = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "market.css"), encoding="utf-8").read()
    assert "mk-col-ops" not in js and "mk-col-ops" not in css
    assert "mk-mini" not in js and "mk-mini" not in css
    assert 'openModal(tr2.getAttribute("data-id"))' in js
    assert "mk-copy-sel" in js
