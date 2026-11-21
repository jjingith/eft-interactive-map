"""R278：价格曲线改成「本机快照 + 云端历史」双来源。

用户反馈：朋友新装的客户端打开物品详情只看到「当前没有可用样本，所以这里不画线」。
根因不是采集没跑，而是曲线只读**本机**采集快照——新机器要自己攒够样本才有线。
云端其实已经有采集机每 30 分钟上传的快照，这里锁住三件事：

1. 云端历史能并进本机结果，同时间戳以本机为准、不重复计数；
2. 云端失败 / 非会员 / 无数据时，本机已有数据一点都不能少；
3. BFF 只在会员态下才去问云端，且查询有短超时与 TTL 缓存。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _local_payload(points):
    return {
        "ok": True,
        "mode": "regular",
        "days": 7,
        "requested": ["item-a"],
        "windowStart": "2026-11-07T10:00:00+08:00",
        "snapshotsTotal": 1,
        "snapshotsUsed": len(points),
        "sources": {"fleaHistory": 0, "collector": 1},
        "series": {
            "item-a": {
                "points": points,
                "count": len(points),
                "firstAt": points[0][0] if points else None,
                "lastAt": points[-1][0] if points else None,
                "low": 100,
                "high": 100,
            }
        } if points else {},
        "missing": [] if points else ["item-a"],
        "error": None if points else "no-index",
    }


def test_cloud_points_fill_empty_local_series():
    import price_history

    payload = _local_payload([])
    cloud = {
        "status": "ok",
        "snapshots": 48,
        "window_end": "2026-11-14T03:51:01+00:00",
        "points": {"item-a": [["2026-11-14T01:00:00+00:00", 1200],
                              ["2026-11-14T01:30:00+00:00", 1300]]},
    }
    out = price_history.merge_cloud(payload, cloud)

    series = out["series"]["item-a"]
    assert [p[0] for p in series["points"]] == [
        "2026-11-14T01:00:00+00:00", "2026-11-14T01:30:00+00:00"]
    assert series["points"][0][1] == 1200
    assert series["points"][0][2] is None      # 云端只有最近低价，不编 24h 均价
    assert series["count"] == 2
    assert out["error"] is None                # 有数据了就不再报 no-index
    assert out["snapshotsUsed"] == 2
    assert out["sources"]["cloud"] == 2
    assert out["missing"] == []
    assert out["cloud"]["status"] == "ok"


def test_local_point_wins_on_same_timestamp():
    import price_history

    stamp = "2026-11-14T01:00:00+00:00"
    payload = _local_payload([[stamp, 999, 888]])
    cloud = {"status": "ok", "snapshots": 1,
             "points": {"item-a": [[stamp, 1200], ["2026-11-14T01:30:00+00:00", 1300]]}}
    out = price_history.merge_cloud(payload, cloud)

    points = out["series"]["item-a"]["points"]
    assert len(points) == 2, "同一时间戳不能算两份"
    assert points[0] == [stamp, 999, 888], "本机那份（含 24h 均价）必须优先"
    assert out["snapshotsUsed"] == 2


def test_local_and_cloud_timestamps_dedupe_across_timezones():
    """本机存本地时区、云端存 UTC：同一个瞬间不能算两个点。"""
    import price_history

    payload = _local_payload([["2026-11-14T11:51:01+08:00", 25000, 24000]])
    cloud = {"status": "ok", "snapshots": 2,
             "points": {"item-a": [["2026-11-14T03:51:01+00:00", 25000],
                                   ["2026-11-14T04:21:01+00:00", 26000]]}}
    out = price_history.merge_cloud(payload, cloud)

    points = out["series"]["item-a"]["points"]
    assert len(points) == 2, points
    assert points[0][1] == 25000 and points[0][2] == 24000, "同瞬间保留本机那份"
    assert points[1][1] == 26000


def test_cloud_failure_keeps_local_data_intact():
    import price_history

    local_points = [["2026-11-14T01:00:00+00:00", 100, 90]]
    payload = _local_payload(local_points)
    for status in ("offline", "member_required", "error", "no_data"):
        out = price_history.merge_cloud(_local_payload(local_points), None, status=status)
        assert out["series"]["item-a"]["points"] == local_points
        assert out["cloud"]["status"] == status
        assert out["sources"]["cloud"] == 0
        assert out["error"] is None


def test_merge_does_not_invent_points_for_other_items():
    import price_history

    payload = _local_payload([])
    payload["requested"] = ["item-a", "item-b"]
    payload["missing"] = ["item-a", "item-b"]
    cloud = {"status": "ok", "snapshots": 3,
             "points": {"item-a": [["2026-11-14T01:00:00+00:00", 1200]]}}
    out = price_history.merge_cloud(payload, cloud)

    assert "item-a" in out["series"]
    assert "item-b" not in out["series"]
    assert out["missing"] == ["item-b"]


def test_bff_only_asks_cloud_for_members_and_small_batches():
    source = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
    assert "def _cloud_series(" in source
    assert "config.is_member(app_dir)" in source
    assert "_CLOUD_SERIES_MAX_ITEMS" in source
    assert "price_history.merge_cloud(" in source
    # 云端挂了不能把本机曲线一起拖下水：异常必须收敛成 status，不往外抛
    assert "except cloud.CloudError" in source
    assert 'payload, status = None, "offline"' in source


def test_cloud_client_uses_short_timeout_for_series():
    source = (ROOT / "tools" / "cloud.py").read_text(encoding="utf-8")
    assert "def prices_series(" in source
    assert "timeout=4.0" in source
    # 短超时连接不能进 keep-alive 池
    assert "one_off" in source


def test_cloud_series_maps_errors_and_caches(monkeypatch):
    import cloud
    import serve

    calls = []

    class Stub:
        def __init__(self, exc=None, payload=None):
            self.exc = exc
            self.payload = payload

        def prices_series(self, mode, ids, days):
            calls.append((mode, tuple(ids), days))
            if self.exc:
                raise self.exc
            return self.payload

    serve._cloud_series_cache.clear()

    payload = {"status": "ok", "snapshots": 12, "points": {"item-a": [["t", 1]]}}
    stub = Stub(payload=payload)
    got, status = serve._cloud_series(stub, "regular", ["item-a"], 7)
    assert status == "ok" and got is payload
    # 5 分钟内同一个 key 不再打云端
    serve._cloud_series(stub, "regular", ["item-a"], 7)
    assert len(calls) == 1

    # 会员过期 → member_required；网络断 → offline；其它 → error
    for exc, expected in [
        (cloud.CloudError(403, "membership_required", "会员专属"), "member_required"),
        (cloud.CloudError(0, "network", "连不上"), "offline"),
        (cloud.CloudError(500, "boom", "炸了"), "error"),
    ]:
        serve._cloud_series_cache.clear()
        got, status = serve._cloud_series(Stub(exc=exc), "pve", ["item-b"], 1)
        assert got is None and status == expected

    # 云端抛非 CloudError 也不能冒到 BFF
    class Weird:
        def prices_series(self, mode, ids, days):
            raise ValueError("坏数据")

    serve._cloud_series_cache.clear()
    got, status = serve._cloud_series(Weird(), "regular", ["item-c"], 7)
    assert got is None and status == "error"

    # 没有客户端（例如测试环境 / 精简部署）→ disabled，不报错
    assert serve._cloud_series(None, "regular", ["item-a"], 7) == (None, "disabled")


def test_frontend_empty_state_explains_cloud_source():
    source = (ROOT / "js" / "market.js").read_text(encoding="utf-8")
    assert "云端历史是会员数据" in source
    assert "云端历史暂时连不上" in source
    assert "云历史" in source or "云端历史" in source
    # 旧的「只读本机」文案必须消失，否则用户还是会以为要自己攒样本
    assert "只读本机采集快照" not in source
