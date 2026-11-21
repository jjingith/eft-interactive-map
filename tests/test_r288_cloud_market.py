# -*- coding: utf-8 -*-
"""云端行情缓存 / 大盘聚合：列表与大盘共用一次取数，失败回退本机缓存。"""

from __future__ import annotations

import datetime
import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import cloud  # noqa: E402
import cloud_market  # noqa: E402
import market_overview  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=8))
T1 = datetime.datetime(2026, 11, 17, 10, 0, 0, tzinfo=TZ)
T2 = datetime.datetime(2026, 11, 17, 11, 0, 0, tzinfo=TZ)


def _stamp(moment: datetime.datetime) -> str:
    return moment.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _doc(moment: datetime.datetime, prices: dict, tier: str = "free") -> dict:
    market = {
        item_id: {"l": price, "a": price, "o": 10, "c": change, "d": change}
        for item_id, (price, change) in prices.items()
    }
    member = tier == "member"
    return {
        "status": "ok",
        "mode": "regular",
        "tier": tier,
        "member": member,
        "generated_at": _stamp(moment),
        "stored_at": _stamp(moment),
        "delay_seconds": 0 if member else 12 * 3600,
        "prices": {item_id: price for item_id, (price, _) in prices.items()},
        "market": market,
        "quota": {
            "tier": tier,
            "daily_limit": None if member else 24,
            "used_today": 1,
            "remaining_today": None if member else 23,
            "cd_seconds": 30 if member else 3599,
            "cooldown": False,
        },
    }


class FakeClient:
    def __init__(self, docs):
        self.docs = list(docs)
        self.calls = 0
        self.error = None

    def prices_market(self, mode):
        self.calls += 1
        if self.error:
            raise self.error
        doc = self.docs[min(self.calls - 1, len(self.docs) - 1)]
        return dict(doc, mode=mode)


def test_from_snapshots_builds_kpis_ranks_and_buckets():
    first = {
        "generated_at": _stamp(T1),
        "prices": {"item-a": 100, "item-b": 200},
        "market": {
            "item-a": {"l": 100, "o": 10, "c": 1.0, "d": 1},
            "item-b": {"l": 200, "o": 10, "c": -1.0, "d": -2},
        },
    }
    second = {
        "generated_at": _stamp(T2),
        "prices": {"item-a": 110, "item-b": 190},
        "market": {
            "item-a": {"l": 110, "o": 12, "c": 5.0, "d": 5},
            "item-b": {"l": 190, "o": 8, "c": -2.5, "d": -5},
        },
    }
    payload = market_overview.from_snapshots("regular", [first, second], 24, now=T2)
    assert payload["ok"] is True and payload["status"] == "ok"
    assert payload["source"] == "cloud"
    assert payload["dataAt"] == _stamp(T2)
    assert payload["summary"]["items"] == 2
    assert payload["summary"]["up"] == 1
    assert payload["summary"]["down"] == 1
    assert payload["summary"]["avgChange"] == 1.25
    assert len(payload["buckets"]) == 2
    assert payload["gainers"][0]["id"] == "item-a"
    assert payload["gainers"][0]["change"] == 5.0
    assert payload["losers"][0]["id"] == "item-b"
    assert payload["losers"][0]["change"] == -2.5
    assert payload["sectors"]
    assert payload["coverage"]["withChange"] == 2


def test_from_snapshots_ranks_low_offer_items_and_uses_game_sectors():
    """R19.69：榜单不设在售数量门槛；板块按游戏 Handbook 的十个分类聚合。"""
    snapshot = {
        "generated_at": _stamp(T1),
        "prices": {"low-offer": 100},
        "market": {"low-offer": {"l": 100, "o": 1, "c": 5.0, "d": 5}},
    }
    payload = market_overview.from_snapshots("regular", [snapshot], 24, now=T1)
    assert [row["id"] for row in payload["gainers"]] == ["low-offer"]
    assert payload["minOffers"] == 0
    assert "≥" not in payload["note"]
    allowed = set(market_overview.SECTOR_ORDER)
    assert {sector["key"] for sector in payload["sectors"]} <= allowed


def test_hot_board_sorted_by_current_offer_count():
    """R19.73：热卖榜按当前在售挂单数降序，而不是按 24h 变化率。"""
    snap = {
        "generated_at": _stamp(T1),
        "prices": {"few": 100, "many": 200, "mid": 300},
        "market": {
            "few": {"l": 100, "o": 9, "c": 1.0, "d": 1},
            "many": {"l": 200, "o": 31, "c": 0.2, "d": 1},
            "mid": {"l": 300, "o": 20, "c": 3.0, "d": 1},
        },
    }
    payload = market_overview.from_snapshots("regular", [snap], 24, now=T1)
    assert [row["id"] for row in payload["hot"]] == ["many", "mid", "few"]


def test_sector_mapping_follows_game_categories():
    assert market_overview._sector_key({"pt": "WeaponMod"}) == "Mod"
    assert market_overview._sector_key({"pt": "Helmet"}) == "Gear"
    assert market_overview._sector_key({"pt": "FoodDrink"}) == "Food"
    assert market_overview._sector_key({"pt": "InfoContent"}) == "Info"
    assert market_overview._sector_key({"pt": "Key"}) == "Key"
    assert market_overview._sector_key({"ts": ["barter"]}) == "Barter"
    assert market_overview._sector_key({"pt": "Ammo"}) == "Ammo"


def test_sector_filter_applies_to_hot_board_too():
    """点分类后热卖榜也必须只留该分类，否则「榜单物资类型对不上」。"""
    snapshot = {
        "generated_at": _stamp(T1),
        "prices": {"item-a": 100, "item-b": 200},
        "market": {
            "item-a": {"l": 100, "o": 10, "c": 1.0, "d": 1},
            "item-b": {"l": 200, "o": 8, "c": -1.0, "d": -2},
        },
    }
    payload = market_overview.from_snapshots("regular", [snapshot], 24,
                                             sector="Key", now=T1)
    assert payload["hot"] == []
    assert payload["gainers"] == [] and payload["losers"] == []


def test_item_sectors_match_game_handbook_counts():
    """R19.70：板块归属来自 tarkov.dev handbookCategories，数量对齐参考站分类页。"""
    import json

    path = os.path.join(ROOT, "data", "item-sectors.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    counts = {}
    for sectors in doc["items"].values():
        for key in sectors:
            counts[key] = counts.get(key, 0) + 1
    assert counts == {
        "Barter": 402, "Info": 128, "Container": 38, "Key": 245,
        "Gear": 841, "Weapon": 616, "Mod": 2312, "Ammo": 429,
        "Medical": 43, "Food": 45,
    }
    totals = market_overview._sector_map()[1]
    assert totals == counts


def test_trend_board_scans_all_items_and_trims_outlier_prices():
    """R19.77：七天价格榜扫描全市场（不依赖涨跌/热卖候选），并剔除天价孤挂。"""
    stamps = []
    for i in range(7):
        moment = T1 + datetime.timedelta(hours=i)
        prices = {"a": 100, "b": 500, "c": 50}
        if i == 6:
            prices["c"] = 10_000_000   # 最后一笔天价孤挂
        stamps.append({"generated_at": _stamp(moment), "prices": prices, "market": {}})
    payload = market_overview.from_snapshots("regular", stamps, 24, now=T1 + datetime.timedelta(hours=6))
    # 这些物品没有涨跌 / 挂单字段，不会进涨跌榜与热卖榜
    assert payload["gainers"] == [] and payload["losers"] == [] and payload["hot"] == []
    # 但七天价格榜必须覆盖它们：b(500) > a(100) > c(剔除天价后 50)
    assert [row["id"] for row in payload["trend"]] == ["b", "a", "c"]
    c = [row for row in payload["trend"] if row["id"] == "c"][0]
    assert c["avg7"] < 1000, c


def test_rank_lists_cover_all_items_and_follow_sector():
    """R19.78：24h/48h 涨跌榜从全市场物品里选，板块筛选时从该板块全量物品里选。"""
    import json

    with open(os.path.join(ROOT, "data", "item-sectors.json"), encoding="utf-8") as fh:
        sectors = json.load(fh)["items"]
    mod_id = next(key for key, value in sectors.items() if "Mod" in value)
    ammo_id = next(key for key, value in sectors.items() if "Ammo" in value)
    stamps = []
    for i in range(25):
        prices = {mod_id: 100 + i * 4, ammo_id: 100 + i * 8}
        for n in range(20):
            prices["filler-%d" % n] = 1000
        stamps.append({"generated_at": _stamp(T1 + datetime.timedelta(hours=i)),
                       "prices": prices, "market": {}})
    now = T1 + datetime.timedelta(hours=24)

    payload = market_overview.from_snapshots("regular", stamps, 24, now=now)
    # 涨幅第一必须是全市场里 24h 涨幅最大的弹药（不是旧候选池的子集）
    assert payload["gainers24"][0]["id"] == ammo_id
    assert payload["gainers24"][0]["change24"] > 40

    filtered = market_overview.from_snapshots("regular", stamps, 24, now=now, sector="Mod")
    assert filtered["gainers24"], filtered
    assert all(row["sector"] == "Mod" for row in filtered["gainers24"])
    assert all(row["sector"] == "Mod" for row in filtered["losers24"])


def test_ranks_and_trend_use_cloud_price_cache(tmp_path):
    """R19.79：大盘均价/趋势优先用云端价格缓存（会员全量 30 分钟序列），不用本机零散快照。"""
    import json

    os.makedirs(os.path.join(str(tmp_path), "cloud-cache"), exist_ok=True)
    base = int(T1.timestamp() * 1000)
    series = {"a": [[base + i * 3600 * 1000, 1000 + i * 50] for i in range(25)]}
    with open(os.path.join(str(tmp_path), "cloud-cache", "pve.json"), "w", encoding="utf-8") as fh:
        json.dump({"series": series, "snapshots": 25}, fh)
    moment = T1 + datetime.timedelta(hours=24)
    snapshot = {
        "generated_at": _stamp(moment),
        "prices": {"a": 2200},
        "market": {"a": {"l": 2200, "o": 5, "c": 1.0}},
    }
    payload = market_overview.from_snapshots("pve", [snapshot], 24, now=moment,
                                             app_dir=str(tmp_path))
    row = [item for item in payload["gainers24"] if item["id"] == "a"][0]
    assert row["avg24"] != 2200, "24h 均价应来自云端序列，而不是快照里的单点价格"
    trend = [item for item in payload["trend"] if item["id"] == "a"][0]
    assert 1000 < trend["avg7"] < 2200


def test_fetch_reuses_local_result_and_force_calls_cloud(tmp_path):
    app_dir = str(tmp_path / "app")
    client = FakeClient([
        _doc(T1, {"item-a": (100, 1.0), "item-b": (200, -1.0)}),
        _doc(T2, {"item-a": (110, 5.0), "item-b": (190, -2.5)}),
    ])
    first = cloud_market.fetch(app_dir, "regular", client, now=T1)
    assert first["available"] is True and first["cached"] is False
    assert first["items"]["item-a"]["l"] == 100
    assert first["quota"]["remaining_today"] == 23

    # 列表 / 大盘在 120 秒内复用同一次结果，不重复扣次。
    again = cloud_market.fetch(app_dir, "regular", client,
                               now=T1 + datetime.timedelta(seconds=30))
    assert again["items"]["item-a"]["l"] == 100
    assert client.calls == 1

    forced = cloud_market.fetch(app_dir, "regular", client, force=True,
                                now=T1 + datetime.timedelta(seconds=40))
    assert forced["items"]["item-a"]["l"] == 110
    assert client.calls == 2

    overview = cloud_market.overview(app_dir, "regular", 24,
                                     now=T2 + datetime.timedelta(minutes=1))
    assert overview["ok"] is True
    assert overview["summary"]["items"] == 2
    assert overview["tier"] == "free"
    assert overview["dataDelayed"] is True
    assert overview["quota"]["remaining_today"] == 23
    assert overview["cached"] is False

    history = cloud_market.history(app_dir, "regular", ["item-a"], 1, now=T2)
    assert history["series"]["item-a"]["count"] == 2
    assert [price for _, price in history["series"]["item-a"]["points"]] == [100, 110]


def test_fetch_failure_falls_back_to_cache_and_marks_it(tmp_path):
    app_dir = str(tmp_path / "app")
    client = FakeClient([_doc(T1, {"item-a": (100, 1.0)})])
    cloud_market.fetch(app_dir, "regular", client, now=T1)

    client.error = cloud.CloudError(0, "network", "连不上云端")
    cached = cloud_market.fetch(app_dir, "regular", client, force=True,
                                now=T1 + datetime.timedelta(minutes=5))
    assert cached["ok"] is True
    assert cached["cached"] is True
    assert cached["offline"] is True
    assert cached["items"]["item-a"]["l"] == 100

    overview = cloud_market.overview(app_dir, "regular", 24,
                                     now=T1 + datetime.timedelta(minutes=6))
    assert overview["cached"] is True
    assert overview["cacheReason"] == "network"
    assert cloud_market.status(app_dir)["modes"]["regular"]["lastError"] == "network"


def test_history_does_not_fetch_cloud(tmp_path):
    app_dir = str(tmp_path / "app")
    client = FakeClient([_doc(T1, {"item-a": (100, 1.0)})])
    cloud_market.fetch(app_dir, "regular", client, now=T1)
    payload = cloud_market.history(app_dir, "regular", ["item-a"], 7, now=T1)
    assert payload["status"] == "ok"
    assert client.calls == 1


def test_free_cutoff_hides_fresh_local_cache(tmp_path):
    app_dir = str(tmp_path / "app")
    old = T2 - datetime.timedelta(hours=13)
    client = FakeClient([
        _doc(old, {"item-a": (90, 1.0)}, tier="member"),
        _doc(T2, {"item-a": (110, 5.0)}, tier="member"),
    ])
    cloud_market.fetch(app_dir, "regular", client, force=True, now=old)
    cloud_market.fetch(app_dir, "regular", client, force=True, now=T2)
    assert cloud_market.load_latest(app_dir, "regular")["generated_at"] == _stamp(T2)

    # 免费账号可见上限 = T2 - 12h：必须退到 13 小时前那份，不能拿到 T2 的新数据。
    payload = cloud_market.fetch(
        app_dir, "regular", None, now=T2,
        max_generated_at=T2 - datetime.timedelta(hours=12),
    )
    assert payload["snapshotAt"] == _stamp(old)
    assert payload["tier"] == "free"
    assert payload["dataDelayed"] is True
    assert payload["items"]["item-a"]["l"] == 90

    overview = cloud_market.overview(
        app_dir, "regular", 24, now=T2,
        max_generated_at=T2 - datetime.timedelta(hours=12),
    )
    assert overview["summary"]["items"] == 1
    assert overview["tier"] == "free"
    assert overview["dataDelayed"] is True


# ---------------------------------------------------------------- R19.82 列表 7 日均价

def _write_series(app_dir: str, mode: str, series: dict) -> None:
    import json

    os.makedirs(os.path.join(app_dir, "cloud-cache"), exist_ok=True)
    with open(os.path.join(app_dir, "cloud-cache", "%s.json" % mode), "w",
              encoding="utf-8") as fh:
        json.dump({"series": series, "snapshots": 1}, fh)


def _hourly(days: int, price: float, start: datetime.datetime) -> list:
    return [[int((start + datetime.timedelta(hours=i)).timestamp() * 1000), price]
            for i in range(days * 24)]


def test_seven_day_averages_from_cloud_cache(tmp_path):
    """列表「7 日均价」用云端缓存逐物品计算，并剔除天价孤挂。"""
    base = T1
    series = {
        "a": _hourly(8, 1000, base),
        # 一个 10,000,000 的天价孤挂不能把均价拉到天上
        "b": _hourly(8, 1000, base) + [[int((base + datetime.timedelta(days=8)).timestamp() * 1000),
                                        10_000_000]],
    }
    app_dir = str(tmp_path)
    _write_series(app_dir, "pve", series)
    values = market_overview.seven_day_averages(app_dir, "pve")
    assert values["a"] == 1000
    assert values["b"] == 1000


def test_seven_day_averages_requires_full_week(tmp_path):
    """缓存跨度不足 7 天 → 返回空表（界面显示积累中，不拿短窗口冒充）。"""
    app_dir = str(tmp_path)
    _write_series(app_dir, "pve", {"a": _hourly(3, 1000, T1)})
    assert market_overview.seven_day_averages(app_dir, "pve") == {}


def test_snapshot_for_attaches_avg7d_from_cloud_cache(tmp_path, monkeypatch):
    """市场列表的行情 payload 必须带上逐物品 7 日均价（原来整列「积累中」）。"""
    import prices_source

    app_dir = str(tmp_path / "app")
    _write_series(app_dir, "pve", {"item-a": _hourly(8, 1000, T1)})

    def fake_fetch(app_dir_arg, mode, client, **kwargs):
        return {"ok": True, "available": True, "mode": mode, "source": "cloud",
                "items": {"item-a": {"l": 1200}}}

    monkeypatch.setattr(prices_source.cloud_market, "fetch", fake_fetch)
    payload = prices_source.snapshot_for(ROOT, "pve", cloud_client=object(),
                                         member=True, app_dir=app_dir)
    assert payload["avg7d"]["days"] == 7
    assert payload["avg7d"]["values"]["item-a"] == 1000

