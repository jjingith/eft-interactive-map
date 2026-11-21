# -*- coding: utf-8 -*-
"""R78/R79 市场按游戏模式取数（2026-11-17 起改为云端唯一数据源）。

规则：
  1. 未登录 → `loginRequired`，不请求云端，也不再读随包离线快照；
  2. 免费账号 → 云端快照，但服务端延迟 12 小时、每日 24 次、CD 59:59；
  3. 会员 → 云端最新快照、CD 30 秒、每日不限次；
  4. 云端不可达 → 本机最后一次成功结果，标 cached=true，绝不冒充实时。

全离线：云端客户端用假对象，不联网。
"""

from __future__ import annotations

import contextlib
import datetime
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import cloud
import config
import prices_source
import serve

ROOT = Path(__file__).resolve().parent.parent
TZ = datetime.timezone(datetime.timedelta(hours=8))
FIXED_NOW = datetime.datetime(2026, 11, 9, 12, 0, 0, tzinfo=TZ)
GENERATED_AT = "2026-11-09T00:00:00+00:00"

BUNDLED_FILES = {
    "regular": "flea-prices.json",
    "pve": "flea-prices-pve.json",
    "pvps": "flea-prices-pvps.json",
}
MODE_PRICES = {"regular": 39998, "pve": 29500, "pvps": 30999}


def _write_bundle(root: Path, mode: str, price: int) -> None:
    """写一份旧的随包快照：新逻辑必须完全不读它。"""
    doc = {
        "schema": 1,
        "gameMode": mode,
        "meta": {"generatedAt": "2026-11-09T11:50:00+08:00"},
        "items": {"x": {"lastLowPrice": price, "avg24hPrice": price + 50}},
    }
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / BUNDLED_FILES[mode]).write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )


def _cloud_doc(mode: str = "regular", price: int = 40000, tier: str = "free") -> dict:
    member = tier == "member"
    delay = 0 if member else 12 * 3600
    return {
        "status": "ok",
        "mode": mode,
        "tier": tier,
        "member": member,
        "generated_at": GENERATED_AT,
        "stored_at": GENERATED_AT,
        "delay_seconds": delay,
        "prices": {"x": price, "only-" + mode: price + 1},
        "market": {
            "x": {"l": price, "a": price + 50, "lo": price - 10, "hi": price + 400,
                  "o": 12, "c": 1.5, "d": 10, "s": "2026-11-09T03:50:00Z"},
            "only-" + mode: {"l": price + 1, "o": 2, "c": -0.5, "d": -2},
        },
        "quota": {
            "tier": tier,
            "daily_limit": None if member else 24,
            "used_today": 1,
            "remaining_today": None if member else 23,
            "cd_seconds": 30 if member else 59 * 60 + 59,
            "cooldown": False,
            "next_allowed_at": "2026-11-09T12:00:30+00:00",
            "reset_at": "2026-11-10T16:00:00+00:00",
            "delay_seconds": delay,
        },
    }


class FakeCloud:
    """假云端：实现 `prices_market`，记录调用次数；可模拟网络错误。"""

    def __init__(self, payload=None, error=None, token: str = "fake-access-token"):
        self.payload = payload or _cloud_doc()
        self.error = error
        self.calls: list[str] = []
        self.session = {"access_token": token}

    def prices_market(self, mode: str) -> dict:
        self.calls.append(mode)
        if self.error:
            raise self.error
        doc = dict(self.payload)
        doc["mode"] = mode
        return doc


# ---------------------------------------------------------------- 数据源

def test_free_uses_cloud_and_ignores_bundled(tmp_path):
    _write_bundle(tmp_path, "regular", 11111)
    client = FakeCloud(_cloud_doc("regular", 39998, "free"))
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=False,
        now=FIXED_NOW, app_dir=str(tmp_path / "app"),
    )
    assert payload["ok"] is True and payload["available"] is True
    assert payload["source"] == "cloud"
    assert payload["tier"] == "free"
    assert payload["live"] is False
    assert payload["nonLive"] is True
    assert payload["dataDelayed"] is True
    assert payload["delaySeconds"] == 12 * 3600
    assert payload["items"]["x"]["l"] == 39998          # 云端价，不是内置 11111
    assert payload["items"]["x"]["o"] == 12
    assert payload["quota"]["remaining_today"] == 23
    assert client.calls == ["regular"]


def test_member_uses_latest_cloud_snapshot(tmp_path):
    client = FakeCloud(_cloud_doc("regular", 41000, "member"))
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=client, member=True,
        now=FIXED_NOW, app_dir=str(tmp_path / "app"),
    )
    assert payload["source"] == "cloud"
    assert payload["tier"] == "member"
    assert payload["live"] is True
    assert payload["nonLive"] is False
    assert payload["dataDelayed"] is False
    assert payload["items"]["x"]["l"] == 41000
    assert payload["quota"]["daily_limit"] is None
    assert client.calls == ["regular"]


def test_mode_aliases(tmp_path):
    client = FakeCloud(_cloud_doc("regular"))
    assert prices_source.snapshot_for(
        str(tmp_path), "pvp", cloud_client=client, app_dir=str(tmp_path / "app")
    )["mode"] == "regular"
    assert prices_source.snapshot_for(
        str(tmp_path), "pvp-season", cloud_client=client, app_dir=str(tmp_path / "app")
    )["mode"] == "pvps"
    with pytest.raises(ValueError):
        prices_source.snapshot_for(str(tmp_path), "solo", cloud_client=client)


def test_no_cloud_returns_structured_error_not_bundle(tmp_path):
    _write_bundle(tmp_path, "pve", 29500)
    payload = prices_source.snapshot_for(
        str(tmp_path), "pve", member=False, now=FIXED_NOW, app_dir=str(tmp_path / "app")
    )
    assert payload["ok"] is False
    assert payload["available"] is False
    assert payload["items"] == {}
    assert payload["source"] == "cloud"
    # 没有云端客户端时不能假装有数据，也不回退内置快照。
    assert payload["error"] != "no-bundle"


def test_cloud_failure_uses_last_success_cache(tmp_path):
    app_dir = str(tmp_path / "app")
    ok = FakeCloud(_cloud_doc("pve", 29500, "free"))
    first = prices_source.snapshot_for(
        str(tmp_path), "pve", cloud_client=ok, now=FIXED_NOW, app_dir=app_dir
    )
    assert first["available"] is True and first["cached"] is False

    broken = FakeCloud(error=cloud.CloudError(0, "network", "连不上云端"))
    second = prices_source.snapshot_for(
        str(tmp_path), "pve", cloud_client=broken, now=FIXED_NOW,
        force=True, app_dir=app_dir,
    )
    assert second["ok"] is True
    assert second["cached"] is True
    assert second["offline"] is True
    assert second["items"]["x"]["l"] == 29500
    assert second["quota"]["remaining_today"] == 23


def test_quota_exhausted_uses_cache(tmp_path):
    app_dir = str(tmp_path / "app")
    prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=FakeCloud(_cloud_doc("regular", 39998)),
        now=FIXED_NOW, app_dir=app_dir,
    )
    quota_error = cloud.CloudError(
        429, "quota_exhausted", "额度已用完", retry_after=3600,
        details={"quota": {"tier": "free", "used_today": 24, "remaining_today": 0,
                           "daily_limit": 24, "reset_at": "2026-11-10T16:00:00+00:00"}},
    )
    payload = prices_source.snapshot_for(
        str(tmp_path), "regular", cloud_client=FakeCloud(error=quota_error),
        now=FIXED_NOW, force=True, app_dir=app_dir,
    )
    assert payload["cached"] is True
    assert payload["quota"]["remaining_today"] == 0
    assert payload["items"]["x"]["l"] == 39998


# ---------------------------------------------------------------- 服务路由

@contextlib.contextmanager
def _serve(root: Path):
    (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    httpd = serve.create_server(0, "127.0.0.1", str(root), config_dir=str(root), poll_interval=0.2)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(url: str):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_route_requires_login(tmp_path):
    with _serve(tmp_path) as base:
        status, body = _get(base + "/api/price-snapshot?mode=regular")
        board_status, board = _get(base + "/api/market-overview?mode=regular")
    assert status == 200
    assert body["loginRequired"] is True
    assert body["available"] is False
    assert body["items"] == {}
    assert board_status == 200
    assert board["loginRequired"] is True


def test_route_free_user_uses_cloud(tmp_path, monkeypatch):
    client = FakeCloud(_cloud_doc("pve", 29500, "free"))
    monkeypatch.setattr(serve, "make_cloud_client", lambda app_dir: client)
    config.set_member_state({"member": False, "member_status": "none"})
    with _serve(tmp_path) as base:
        status, body = _get(base + "/api/price-snapshot?mode=pve")
        board_status, board = _get(base + "/api/market-overview?mode=pve")
        snapshot_again = _get(base + "/api/price-snapshot?mode=pve&force=1")
    assert status == 200
    assert body["source"] == "cloud"
    assert body["tier"] == "free"
    assert body["nonLive"] is True
    assert body["items"]["x"]["l"] == 29500
    assert board_status == 200
    assert board["ok"] is True and board["source"] == "cloud"
    assert board["tier"] == "free"
    assert board["summary"]["items"] == 2
    # 列表 / 大盘复用同一次取数；只有显式 force 才会再次打云端。
    assert client.calls == ["pve", "pve"]
    assert snapshot_again[1]["available"] is True


def test_route_member_uses_cloud_live(tmp_path, monkeypatch):
    client = FakeCloud(_cloud_doc("pve", 30000, "member"))
    monkeypatch.setattr(serve, "make_cloud_client", lambda app_dir: client)
    config.set_member_state({"member": True, "member_status": "active"})
    with _serve(tmp_path) as base:
        status, body = _get(base + "/api/price-snapshot?mode=pve")
    assert status == 200
    assert body["source"] == "cloud"
    assert body["tier"] == "member"
    assert body["live"] is True
    assert body["items"]["x"]["l"] == 30000


def test_route_offline_falls_back_to_cache(tmp_path, monkeypatch):
    app_root = tmp_path

    good = FakeCloud(_cloud_doc("regular", 39998, "free"))
    monkeypatch.setattr(serve, "make_cloud_client", lambda app_dir: good)
    config.set_member_state({"member": False, "member_status": "none"})
    with _serve(app_root) as base:
        first = _get(base + "/api/price-snapshot?mode=regular")
    assert first[1]["available"] is True

    broken = FakeCloud(error=cloud.CloudError(0, "network", "offline"))
    monkeypatch.setattr(serve, "make_cloud_client", lambda app_dir: broken)
    with _serve(app_root) as base:
        status, body = _get(base + "/api/price-snapshot?mode=regular&force=1")
    assert status == 200
    assert body["cached"] is True
    assert body["items"]["x"]["l"] == 39998


# ---------------------------------------------------------------- 前端静态约束

def test_market_frontend_uses_cloud_snapshot():
    js = (ROOT / "js" / "market.js").read_text(encoding="utf-8")
    assert "api.snapshot" in js
    assert "api.flea()" not in js
    assert 'loadJSON("data/flea-prices.json")' not in js
    for banned in ("本地采集器快照", "构建期单独抓取", "no-snapshot"):
        assert banned not in js
    assert "云端行情" in js
    assert "loginRequired" in js
    assert "今日剩余" in js
    assert "内置离线快照" not in js


def test_app_reads_price_snapshot_state():
    js = (ROOT / "app.js").read_text(encoding="utf-8")
    assert 'fetchPriceSnapshot({ reason: "mode" })' in js
    assert 'fetchPriceSnapshot({ reason: "init" })' in js
    assert "function priceQuoteOf" in js
    assert "state.priceSnap.payload" in js
    assert "snapshot: function () { return state.priceSnap.payload || null; }" in js
    assert "fetchCollectorPrices" not in js
    assert "state.collector" not in js
