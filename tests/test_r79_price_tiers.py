# -*- coding: utf-8 -*-
"""R79 三层行情：内置快照读取、构建期生成、采集器定时上传（R221 起每 30 分钟一轮）。

覆盖：
- `prices_source.load_bundled`：三模式互不串、完整字段归一化、7 日均价门槛、缺失/损坏；
- `build_bundled_prices.generate`：从采集器日锚点 + 最新快照生成内置快照、过期拒绝；
- `price_upload`：手动上传、重复幂等、409 幂等、断网 pending 后补传、节流与凭据。
"""

from __future__ import annotations

import contextlib
import datetime
import gzip
import http.server
import json
import socket
import threading
from pathlib import Path

import pytest

import build_bundled_prices
import price_upload
import prices_source

TZ = datetime.timezone(datetime.timedelta(hours=8))
FIXED_NOW = datetime.datetime(2026, 11, 9, 12, 0, 0, tzinfo=TZ)
BUNDLED = {
    "regular": "flea-prices.json",
    "pve": "flea-prices-pve.json",
    "pvps": "flea-prices-pvps.json",
}
MODES = ("regular", "pve", "pvps")


def _write_gz(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)


def _write_bundle(root: Path, name: str, doc: dict) -> Path:
    path = root / "data" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 上传载荷

def test_build_mode_payload_uploads_market_fields(tmp_path):
    day = "2026-11-09"
    _write_gz(
        tmp_path / "collect" / "snapshots" / "regular" / day / "115000.json.gz",
        {
            "snapshotAt": "2026-11-09T11:50:00+08:00",
            "items": {
                "x": {
                    "l": 100, "a": 110,
                    "mk": {"o": 12, "c": 3.5, "d": 3, "v": 1.2,
                           "s": "2026-11-09T03:50:00Z"},
                },
                "plain": {"l": 200},
            },
        },
    )
    payload, error = price_upload.build_mode_payload(str(tmp_path), "regular")
    assert error is None
    assert payload["prices"]["x"] == 100
    assert payload["market"]["x"]["o"] == 12
    assert payload["market"]["x"]["c"] == 3.5
    assert payload["market"]["x"]["d"] == 3
    assert payload["market"]["x"]["s"] == "2026-11-09T03:50:00Z"
    # 没有 mk 的物品只带价格，不会凭空长出涨跌 / 挂单字段
    assert payload["market"]["plain"] == {"l": 200}
    assert payload["contentHash"]


# ---------------------------------------------------------------- 内置快照读取

def test_load_bundled_normalizes_full_fields_and_avg7(tmp_path):
    doc = {
        "meta": {
            "generatedAt": "2026-11-09T11:50:00+08:00",
            "sourceUpdatedMax": "2026-11-09T03:50:00Z",
            "historyDays": 7,
        },
        "items": {
            "x": {
                "lastLowPrice": 39998,
                "avg24hPrice": 40000,
                "low24hPrice": 39000,
                "high24hPrice": 42000,
                "basePrice": 100,
                "updated": "2026-11-09T03:50:00Z",
                "minLevelForFlea": 15,
                "avg7daysPrice": 38000,
            }
        },
    }
    _write_bundle(tmp_path, BUNDLED["regular"], doc)
    payload = prices_source.load_bundled(str(tmp_path), "regular", now=FIXED_NOW)
    assert payload["ok"] is True and payload["available"] is True
    assert payload["items"]["x"] == {
        "l": 39998, "a": 40000, "lo": 39000, "hi": 42000,
        "b": 100, "u": "2026-11-09T03:50:00Z", "lv": 15,
    }
    assert payload["avg7d"]["days"] == 7
    assert payload["avg7d"]["values"] == {"x": 38000}
    assert payload["snapshotAt"] == "2026-11-09T11:50:00+08:00"
    assert payload["dataAt"] == "2026-11-09T03:50:00Z"
    assert payload["ageSec"] == 600
    assert payload["stale"] is False


def test_avg7_respects_history_days_gate(tmp_path):
    # 只有 2 天历史：即使带了 avg7daysPrice 也不能当真（不冒充 7 日均价）
    doc = {
        "meta": {"generatedAt": "2026-11-09T11:50:00+08:00", "historyDays": 2},
        "items": {"x": {"lastLowPrice": 100, "avg7daysPrice": 90}},
    }
    _write_bundle(tmp_path, BUNDLED["pve"], doc)
    payload = prices_source.load_bundled(str(tmp_path), "pve", now=FIXED_NOW)
    assert payload["avg7d"]["days"] == 2
    assert payload["avg7d"]["values"] == {}


def test_load_bundled_accepts_short_keys(tmp_path):
    _write_bundle(tmp_path, BUNDLED["pvps"], {
        "items": {"x": {"l": 123, "a": 456, "u": "2026-11-09T03:50:00Z"}},
    })
    payload = prices_source.load_bundled(str(tmp_path), "pvps", now=FIXED_NOW)
    assert payload["items"]["x"] == {"l": 123, "a": 456, "u": "2026-11-09T03:50:00Z"}


def test_load_bundled_mode_files_do_not_leak(tmp_path):
    for mode, price in (("regular", 39998), ("pve", 29500), ("pvps", 30999)):
        _write_bundle(tmp_path, BUNDLED[mode], {"items": {"x": {"l": price}}})
    for mode, price in (("regular", 39998), ("pve", 29500), ("pvps", 30999)):
        payload = prices_source.load_bundled(str(tmp_path), mode, now=FIXED_NOW)
        assert payload["items"]["x"]["l"] == price
        assert payload["bundledPath"] == "data/" + BUNDLED[mode]


def test_load_bundled_missing_and_corrupt(tmp_path):
    missing = prices_source.load_bundled(str(tmp_path), "regular", now=FIXED_NOW)
    assert missing["ok"] is False and missing["error"] == "no-bundle"

    bad = tmp_path / "data" / BUNDLED["pve"]
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json", encoding="utf-8")
    corrupt = prices_source.load_bundled(str(tmp_path), "pve", now=FIXED_NOW)
    assert corrupt["ok"] is False and corrupt["error"] == "unreadable-bundle"

    _write_bundle(tmp_path, BUNDLED["pvps"], {"items": []})
    empty = prices_source.load_bundled(str(tmp_path), "pvps", now=FIXED_NOW)
    assert empty["ok"] is False and empty["error"] == "unreadable-bundle"


# ---------------------------------------------------------------- 构建期生成

def _collector_data(app_root: Path, mode: str, days: list[str], latest_price: int = 500) -> None:
    for idx, day in enumerate(days):
        _write_gz(app_root / "collect" / "daily" / mode / (day + ".json.gz"), {
            "schema": 1, "mode": mode, "day": day,
            "snapshotAt": day + "T23:59:00+08:00",
            "items": {
                "x": {"l": 100 + idx, "a": 200 + idx, "lo": 90 + idx,
                      "hi": 400 + idx, "b": 50, "lv": 10},
                "y": {"l": 1000 + idx * 100, "a": 1100 + idx * 100, "lo": 900,
                      "hi": 2000, "b": 700, "lv": 20},
            },
        })
    _write_gz(app_root / "collect" / "snapshots" / mode / "2026-11-09" / "115500.json.gz", {
        "schema": 1, "mode": mode,
        "snapshotAt": "2026-11-09T11:55:00+08:00",
        "sourceUpdatedMax": "2026-11-09T03:55:00Z",
        "counts": {"items": 2},
        "items": {
            "x": {"l": latest_price, "a": 600, "u": "2026-11-09T03:50:00Z"},
            "y": {"l": 1500, "a": 1600, "u": "2026-11-09T03:55:00Z"},
        },
    })


DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
        "2026-11-07", "2026-11-08", "2026-11-09"]


def test_generate_bundled_snapshot_merges_anchor_and_latest(tmp_path):
    app_root = tmp_path / "collector"
    for mode in ("regular", "pve"):
        _collector_data(app_root, mode, DAYS)
    out_dir = tmp_path / "out"
    report = build_bundled_prices.generate(
        app_root=str(app_root), out_dir=str(out_dir),
        modes=["regular", "pve"], now=FIXED_NOW,
    )
    assert report["ok"] is True, report["errors"]
    assert set(report["written"]) == {"regular", "pve"}

    doc = json.loads((out_dir / BUNDLED["regular"]).read_text(encoding="utf-8"))
    x = doc["items"]["x"]
    assert x["lastLowPrice"] == 500          # 最新快照覆盖日锚点的 l
    assert x["avg24hPrice"] == 600
    assert x["low24hPrice"] == 96             # lo/hi/b/lv 只来自日锚点
    assert x["minLevelForFlea"] == 10
    assert x["avg7daysPrice"] == 103          # (100+101+…+106)/7
    assert doc["meta"]["historyDays"] == 7
    assert doc["meta"]["avg7daysPriceReady"] is True
    assert doc["meta"]["generatedAt"] == "2026-11-09T11:55:00+08:00"
    assert doc["counts"]["itemsWithPrice"] == 2

    pve = json.loads((out_dir / BUNDLED["pve"]).read_text(encoding="utf-8"))
    assert pve["items"]["x"]["lastLowPrice"] == 500
    assert (out_dir / BUNDLED["pvps"]).exists() is False


def test_generate_requires_data(tmp_path):
    report = build_bundled_prices.generate(
        app_root=str(tmp_path / "empty"), out_dir=str(tmp_path / "none"),
        modes=["regular"], now=FIXED_NOW,
    )
    assert report["ok"] is False
    assert report["written"] == {}
    assert any("无采集数据" in item for item in report["errors"])


def test_generate_refuses_stale_unless_allowed(tmp_path):
    app_root = tmp_path / "collector"
    _collector_data(app_root, "regular", DAYS)
    later = datetime.datetime(2026, 11, 12, 12, 0, 0, tzinfo=TZ)
    out_dir = tmp_path / "stale"
    report = build_bundled_prices.generate(
        app_root=str(app_root), out_dir=str(out_dir), modes=["regular"],
        now=later, max_age_hours=12,
    )
    assert report["ok"] is False
    assert any("超过" in item for item in report["errors"])
    assert not (out_dir / BUNDLED["regular"]).exists()

    forced = build_bundled_prices.generate(
        app_root=str(app_root), out_dir=str(out_dir), modes=["regular"],
        now=later, max_age_hours=12, allow_stale=True,
    )
    assert forced["ok"] is True
    assert (out_dir / BUNDLED["regular"]).exists()


# ---------------------------------------------------------------- 采集器上传

class _StubHandler(http.server.BaseHTTPRequestHandler):
    server_version = "IngestStub/1"

    def log_message(self, fmt, *args):   # noqa: A003 - 覆盖标准库签名
        pass

    def do_POST(self):                   # noqa: N802 - 标准库方法名
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        doc = json.loads(gzip.decompress(body).decode("utf-8"))
        self.server.requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": doc,
        })
        status = self.server.response_status
        payload = json.dumps({"ok": status < 400, "status": status}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


class _IngestStub(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _StubHandler)
        self.requests: list[dict] = []
        self.response_status = 200


@contextlib.contextmanager
def _stub_server():
    srv = _IngestStub()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _cfg(port: int, **overrides) -> dict:
    cfg = {
        "schema": 1,
        "enabled": True,
        "url": "http://127.0.0.1:%d" % port,
        "token": "collector-secret",
        "proxy": "",
        "timeoutSec": 5,
        "maxAttempts": 1,
        "retrySleepSec": 0,
        "minIntervalSec": 3600,
    }
    cfg.update(overrides)
    return cfg


def _dead_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _collector_mode(app_root: Path, mode: str, stamp: str = "115500", price: int = 111) -> None:
    day = "2026-11-09"
    _write_gz(app_root / "collect" / "snapshots" / mode / day / (stamp + ".json.gz"), {
        "schema": 1, "mode": mode,
        "snapshotAt": "%sT%s:%s:%s+08:00" % (day, stamp[:2], stamp[2:4], stamp[4:]),
        "sourceUpdatedMax": "2026-11-09T03:50:00Z",
        "counts": {"items": 1},
        "items": {"x": {"l": price, "a": price + 10, "u": "2026-11-09T03:50:00Z"}},
    })
    _write_gz(app_root / "collect" / "daily" / mode / (day + ".json.gz"), {
        "schema": 1, "mode": mode, "day": day,
        "snapshotAt": day + "T23:59:00+08:00",
        "items": {"x": {"l": price, "a": price + 10, "lo": price - 10,
                        "hi": price + 40, "b": 10, "lv": 5}},
    })


def test_upload_skipped_when_disabled(tmp_path):
    result = price_upload.upload_all(str(tmp_path))
    assert result["skipped"] is True
    assert result["reason"] == "disabled"
    assert Path(result["configPath"]).name == "upload.json"

    price_upload.init_config(str(tmp_path))
    result = price_upload.upload_all(str(tmp_path))
    assert result["skipped"] is True and result["reason"] == "disabled"


def test_upload_skipped_when_token_missing(tmp_path):
    cfg = {"schema": 1, "enabled": True, "url": "https://example.com", "token": ""}
    result = price_upload.upload_all(str(tmp_path), cfg=cfg)
    assert result["skipped"] is True and result["reason"] == "not-configured"


def test_manual_upload_all_modes_and_idempotent(tmp_path):
    for mode in MODES:
        _collector_mode(tmp_path, mode)
    with _stub_server() as srv:
        cfg = _cfg(srv.server_address[1])
        first = price_upload.upload_all(str(tmp_path), cfg=cfg)
        assert first["ok"] is True
        assert set(first["modes"]) == set(MODES)
        assert all(item["status"] == "uploaded" for item in first["modes"].values())
        assert len(srv.requests) == 3

        for req in srv.requests:
            assert req["path"] == "/v1/prices/ingest"
            assert req["headers"]["X-Ingest-Token"] == "collector-secret"
            assert req["headers"]["Content-Encoding"] == "gzip"
            body = req["body"]
            assert body["mode"] in MODES
            assert body["generatedAt"]
            assert body["contentHash"]
            # 服务端契约：prices 是「物品 → 单个价格」，daily 是「日期 → 当日均价」
            assert body["prices"]["x"] == 111
            assert body["daily"]["2026-11-09"] == 111

        state = price_upload.load_state(str(tmp_path))
        for mode in MODES:
            assert state["modes"][mode]["pending"] is False
            assert state["modes"][mode]["lastSuccessAt"]

        # 每小时节流：不带 force 的重复调用直接跳过
        second = price_upload.upload_all(str(tmp_path), cfg=cfg)
        assert second["skipped"] is True and second["reason"] == "interval"
        assert len(srv.requests) == 3

        # force 绕过节流，但同一份内容仍不重复上传
        third = price_upload.upload_all(str(tmp_path), force=True, cfg=cfg)
        assert third["ok"] is True
        assert all(item["status"] == "identical" for item in third["modes"].values())
        assert len(srv.requests) == 3


def test_changed_snapshot_uploads_again(tmp_path):
    _collector_mode(tmp_path, "regular", price=111)
    with _stub_server() as srv:
        cfg = _cfg(srv.server_address[1])
        assert price_upload.upload_all(str(tmp_path), modes=["regular"], cfg=cfg)["ok"] is True
        _collector_mode(tmp_path, "regular", stamp="115900", price=321)
        result = price_upload.upload_all(str(tmp_path), modes=["regular"], force=True, cfg=cfg)
        assert result["modes"]["regular"]["status"] == "uploaded"
        assert len(srv.requests) == 2
        assert srv.requests[-1]["body"]["prices"]["x"] == 321
        assert srv.requests[-1]["body"]["generatedAt"] == "2026-11-09T11:59:00+08:00"


def test_upload_conflict_409_treated_as_success(tmp_path):
    _collector_mode(tmp_path, "regular")
    with _stub_server() as srv:
        srv.response_status = 409
        cfg = _cfg(srv.server_address[1])
        result = price_upload.upload_all(str(tmp_path), modes=["regular"], force=True, cfg=cfg)
        assert result["ok"] is True
        assert result["modes"]["regular"]["status"] == "uploaded"
        assert result["modes"]["regular"]["httpStatus"] == 409
        assert price_upload.load_state(str(tmp_path))["modes"]["regular"]["pending"] is False


def test_network_failure_keeps_pending_then_retries(tmp_path):
    _collector_mode(tmp_path, "regular")
    dead = _cfg(_dead_port())
    failed = price_upload.upload_all(str(tmp_path), modes=["regular"], force=True, cfg=dead)
    assert failed["ok"] is False
    assert failed["failed"] == ["regular"]
    assert failed["pending"] == ["regular"]
    state = price_upload.load_state(str(tmp_path))
    assert state["modes"]["regular"]["pending"] is True
    assert "网络错误" in (state["modes"]["regular"]["lastError"] or "")

    with _stub_server() as srv:
        # pending 绕过「每小时」节流：下一轮立即补传
        cfg = _cfg(srv.server_address[1])
        recovered = price_upload.upload_all(str(tmp_path), modes=["regular"], cfg=cfg)
        assert recovered["ok"] is True
        assert recovered["modes"]["regular"]["status"] == "uploaded"
        assert recovered["pending"] == []
        assert len(srv.requests) == 1


def test_upload_failure_never_breaks_collect(tmp_path, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(price_upload, "upload_all", _boom)
    result = price_upload.tick(str(tmp_path))
    assert result["ok"] is False
    assert "boom" in result["exception"]


def test_status_hides_token(tmp_path):
    cfg = _cfg(1, token="super-secret")
    price_upload._write_json(price_upload.config_path(str(tmp_path)), cfg)
    info = price_upload.status(str(tmp_path))
    assert info["configured"] is True
    assert info["enabled"] is True
    assert "super-secret" not in json.dumps(info, ensure_ascii=False)
    assert "token" not in info
