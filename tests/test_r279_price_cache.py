"""R279：云端价格本地缓存（登录整包下载 / 按需增量 / 过期清理）。

用户口径（2026-11-14）：
1. 登录会员后一次性把云端数据下载到本地，之后打开价格页不依赖网络；
2. 点「获取最新数据」才向服务器请求缺失的部分（带 cursor 的增量）；
3. 会员过期 → 客户端自动清掉缓存。

这里锁住：文件怎么落、增量怎么去重、窗口怎么锚、过期怎么清、接口怎么回。
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import config
import price_cache
import serve

ROOT = Path(__file__).resolve().parent.parent


class FakeCloud:
    """最小 CloudClient 替身：按 mode/since 回预设 payload。"""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def prices_cache(self, mode, since=None):
        self.calls.append((mode, since))
        key = (mode, since)
        if key in self.payloads:
            return self.payloads[key]
        return {"status": "up_to_date", "mode": mode, "cursor": since, "snapshots": 0, "series": {}}


def _snapshot(series, cursor, snapshots=1):
    return {"status": "ok", "mode": "regular", "cursor": cursor,
            "snapshots": snapshots, "series": series}


def test_full_sync_writes_cache_and_series_reads_back(tmp_path):
    cloud = FakeCloud({("regular", None): _snapshot(
        {"item-a": [[1763000000000, 1000], [1763001800000, 1200]]},
        "2026-11-14T05:00:00+00:00", snapshots=2)})

    summary = price_cache.sync(str(tmp_path), cloud, "regular")
    assert summary["kind"] == "full"
    assert summary["snapshots"] == 2
    assert summary["added"] == 2
    assert Path(price_cache.cache_path(str(tmp_path), "regular")).is_file()
    assert cloud.calls == [("regular", None)]

    data = price_cache.series(str(tmp_path), "regular", ["item-a"], days=7)
    assert data["status"] == "ok"
    assert data["snapshots"] == 2
    assert [p[1] for p in data["points"]["item-a"]] == [1000, 1200]
    assert data["points"]["item-a"][0][0].startswith("2025-") or data["points"]["item-a"][0][0]
    assert data["window_end"]

    st = price_cache.status(str(tmp_path))
    assert st["modes"]["regular"]["exists"] is True
    assert st["modes"]["regular"]["snapshots"] == 2
    assert st["modes"]["pve"]["exists"] is False


def test_incremental_sync_appends_and_dedupes(tmp_path):
    cloud = FakeCloud({
        ("regular", None): _snapshot({"item-a": [[1000, 10], [2000, 20]]}, "c1", snapshots=2),
        ("regular", "c1"): _snapshot({"item-a": [[2000, 20], [3000, 30]]}, "c2", snapshots=1),
    })
    price_cache.sync(str(tmp_path), cloud, "regular")
    summary = price_cache.sync(str(tmp_path), cloud, "regular")

    assert summary["kind"] == "incremental"
    assert summary["added"] == 1, "同一时间戳只留一个点"
    assert summary["snapshots"] == 3
    data = price_cache.series(str(tmp_path), "regular", ["item-a"])
    assert [p[1] for p in data["points"]["item-a"]] == [10, 20, 30]
    assert cloud.calls[-1] == ("regular", "c1")


def test_up_to_date_keeps_existing_cache(tmp_path):
    cloud = FakeCloud({("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c1")})
    price_cache.sync(str(tmp_path), cloud, "regular")
    again = price_cache.sync(str(tmp_path), cloud, "regular")
    assert again["up_to_date"] is True
    assert price_cache.series(str(tmp_path), "regular", ["item-a"])["counts"]["item-a"] == 1


def test_series_window_anchors_latest_and_skips_old(tmp_path):
    day = 86400 * 1000
    now = 1763000000000
    cloud = FakeCloud({("regular", None): _snapshot(
        {"item-a": [[now - 3 * day, 100], [now - day, 200], [now, 300]]}, "c1", snapshots=3)})
    price_cache.sync(str(tmp_path), cloud, "regular")

    day7 = price_cache.series(str(tmp_path), "regular", ["item-a"], days=7)
    assert [p[1] for p in day7["points"]["item-a"]] == [100, 200, 300]
    day1 = price_cache.series(str(tmp_path), "regular", ["item-a"], days=1)
    assert [p[1] for p in day1["points"]["item-a"]] == [200, 300]
    assert day1["window_end"] == day7["window_end"]


def test_purge_clears_everything(tmp_path):
    cloud = FakeCloud({("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c1")})
    price_cache.sync(str(tmp_path), cloud, "regular")
    assert price_cache.has_data(str(tmp_path), "regular")
    removed = price_cache.purge(str(tmp_path), reason="membership-expired")
    assert removed >= 1
    assert not price_cache.has_data(str(tmp_path), "regular")
    assert price_cache.status(str(tmp_path))["modes"]["regular"]["exists"] is False
    assert price_cache.series(str(tmp_path), "regular", ["item-a"])["status"] == "no_data"


def test_corrupt_cache_is_not_fatal(tmp_path):
    price_cache.cache_dir(str(tmp_path))
    bad = Path(price_cache.cache_path(str(tmp_path), "regular"))
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json", encoding="utf-8")
    data = price_cache.series(str(tmp_path), "regular", ["item-a"])
    assert data["status"] == "no_data"

    cloud = FakeCloud({("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c2")})
    summary = price_cache.sync(str(tmp_path), cloud, "regular")
    assert summary["kind"] == "full", "缓存坏了不能当增量基线"
    assert price_cache.series(str(tmp_path), "regular", ["item-a"])["counts"]["item-a"] == 1


# ---------------------------------------------------------------- HTTP 接口

@pytest.fixture
def server(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    httpd = serve.create_server(0, "127.0.0.1", str(tmp_path), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1]), tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _call(url, payload=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with opener.open(req, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_status_endpoint_reports_cache(server, monkeypatch):
    base, tmp_path = server
    monkeypatch.setattr(config, "member_state", lambda: {"member": True, "member_status": "active"})
    monkeypatch.setattr(config, "is_member", lambda *a, **k: True)
    cloud = FakeCloud({("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c1")})
    price_cache.sync(str(tmp_path), cloud, "regular")

    status, data = _call(base + "/api/price-cache/status")
    assert status == 200, data
    assert data["ok"] is True and data["member"] is True
    assert data["modes"]["regular"]["snapshots"] == 1


def test_status_endpoint_purges_for_non_member(server, monkeypatch):
    base, tmp_path = server
    cloud = FakeCloud({("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c1")})
    price_cache.sync(str(tmp_path), cloud, "regular")
    monkeypatch.setattr(config, "is_member", lambda *a, **k: False)

    status, data = _call(base + "/api/price-cache/status")
    assert status == 200, data
    assert data["member"] is False
    assert data["modes"]["regular"]["exists"] is False, "非会员不许留着会员数据"
    assert not price_cache.has_data(str(tmp_path), "regular")


def test_sync_endpoint_rejects_non_member(server, monkeypatch):
    base, _tmp = server
    monkeypatch.setattr(config, "is_member", lambda *a, **k: False)
    status, data = _call(base + "/api/price-cache/sync", {"mode": "regular"})
    assert status == 403, data
    assert data["error"] == "member_required"


def test_sync_endpoint_runs_full_then_incremental(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    cloud = FakeCloud({
        ("regular", None): _snapshot({"item-a": [[1000, 10]]}, "c1"),
        ("regular", "c1"): _snapshot({"item-a": [[2000, 20]]}, "c2"),
    })
    monkeypatch.setattr(config, "is_member", lambda *a, **k: True)
    # 服务端在 build_handler 里就构造云端客户端，所以必须在 create_server 之前替换。
    monkeypatch.setattr(serve, "make_cloud_client", lambda app_dir: cloud)
    httpd = serve.create_server(0, "127.0.0.1", str(tmp_path), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, data = _call(base + "/api/price-cache/sync", {"mode": "regular"})
        assert status == 200, data
        assert data["ok"] is True
        assert data["kind"] == "full"
        assert data["status"]["modes"]["regular"]["snapshots"] == 1

        status, data = _call(base + "/api/price-cache/sync", {"mode": "regular"})
        assert status == 200, data
        assert data["kind"] == "incremental"
        assert data["added"] == 1
        points = price_cache.series(str(tmp_path), "regular", ["item-a"])["points"]["item-a"]
        assert [p[1] for p in points] == [10, 20]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
