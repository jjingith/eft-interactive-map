"""R42 可选在线行情（tools/live_prices.py + serve 接口）—— 全离线测试。

不真联网：上游响应一律用固定样本 / 假 opener；代理不可达用本机关闭端口模拟。
"""
from __future__ import annotations

import datetime
import http.client
import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import config
import live_prices
import serve

ROOT = Path(__file__).resolve().parent.parent
FIXED_NOW = datetime.datetime(2026, 11, 4, 21, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))


# ---------------------------------------------------------------- 样本与桩件

def upstream_doc(n_items: int = 1200, updated: str | None = "2026-11-04T12:00:00.000Z") -> dict:
    """固定样本：1200 件，900 件有 lastLowPrice（满足 MIN_ITEMS / MIN_PRICED）。"""
    items = {}
    for i in range(n_items):
        item_id = "item%04d" % i
        rec = {
            "id": item_id,
            "name": item_id,
            "basePrice": 100 + i,
            "lastLowPrice": (1000 + i) if i % 4 != 3 else None,
            "avg24hPrice": 900 + i,
            "sellToTrader": [{"trader": "prapor", "priceRUB": 500 + i}],
        }
        if updated:
            rec["updated"] = updated
        items[item_id] = rec
    return {"data": {"items": items}, "translations": {}}


class FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}", headers: dict | None = None):
        self.status = status
        self.body = body
        self.headers = headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """按 route 返回响应或抛异常；记录每次请求头，便于断言条件请求。"""

    def __init__(self, route):
        self.route = route
        self.requests: list[urllib.request.Request] = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        return self.route(req)


def closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    monkeypatch.setenv(live_prices.CACHE_DIR_ENV, str(directory))
    return directory


def seed_cache(mode: str = "regular", checked_at: datetime.datetime | None = None,
               ttl_sec: int = 600) -> dict:
    now = checked_at or FIXED_NOW
    payload = live_prices.build_cache(upstream_doc(), mode, live_prices.MODES[mode]["source"],
                                      now=now, ttl_sec=ttl_sec)
    live_prices.write_atomic(live_prices.cache_path(mode), payload)
    return payload


# ---------------------------------------------------------------- 缓存构建与 TTL

def test_build_cache_keeps_price_fields_only(cache_env):
    payload = live_prices.build_cache(upstream_doc(), "regular",
                                      live_prices.MODES["regular"]["source"], now=FIXED_NOW)
    assert payload["mode"] == "regular"
    assert payload["priceMode"] == "pvp", "上游 regular 端点必须标成 PvP"
    assert payload["counts"]["itemsUpstream"] == 1200
    assert payload["counts"]["itemsWithPrice"] == 1200
    assert payload["counts"]["withLastLowPrice"] == 900
    row = payload["items"]["item0000"]
    assert set(row) <= {"l", "a", "u", "b", "tb", "tn"}
    assert row["l"] == 1000 and row["a"] == 900
    assert row["tb"] == 500 and row["tn"] == "prapor"
    assert row["u"] == "2026-11-04T12:00:00.000Z"
    # 越界 / 0 / 负数一律丢弃，不按 0 计入
    doc = upstream_doc()
    doc["data"]["items"]["item0001"]["lastLowPrice"] = 0
    built = live_prices.build_cache(doc, "regular", "https://x", now=FIXED_NOW)
    assert "l" not in built["items"]["item0001"]


def test_build_cache_rejects_truncated_payload(cache_env):
    doc = {"data": {"items": {"a": {"lastLowPrice": 1}}}}
    with pytest.raises(ValueError):
        live_prices.build_cache(doc, "regular", "https://x", now=FIXED_NOW)


def test_cache_status_ttl_and_updated_window(cache_env):
    seed_cache("regular", checked_at=FIXED_NOW)
    status = live_prices.cache_status("regular", ttl_sec=600, now=FIXED_NOW)
    assert status["exists"] and status["readable"]
    assert status["count"] == 1200
    assert status["ageSec"] == 0 and status["inTtl"] and not status["stale"]
    assert status["updatedOldest"] and status["updatedNewest"]
    assert status["updatedOldest"] == status["updatedNewest"]
    # 2 小时前的缓存：超 TTL → stale，但数据更新时间仍然读得出来
    old_now = FIXED_NOW - datetime.timedelta(hours=2)
    seed_cache("regular", checked_at=old_now, ttl_sec=600)
    stale = live_prices.cache_status("regular", ttl_sec=600, now=FIXED_NOW)
    assert stale["ageSec"] > 600 and stale["stale"] and not stale["inTtl"]
    assert stale["count"] == 1200


def test_missing_cache_status_is_stale(cache_env):
    status = live_prices.cache_status("pve", ttl_sec=600, now=FIXED_NOW)
    assert status["exists"] is False and status["stale"] is True
    assert status["error"] == "no-cache" and status["count"] == 0


def test_fetch_mode_skips_within_ttl_without_network(cache_env):
    # 用「当前时间」播种：TTL 是相对真实时钟判断的，固定 FIXED_NOW 会在 21:10 之后过期。
    seed_cache("regular", checked_at=datetime.datetime.now(FIXED_NOW.tzinfo))
    opener = FakeOpener(lambda req: (_ for _ in ()).throw(AssertionError("不应联网")))
    result = live_prices.fetch_mode("regular", proxy=None, force=False, opener=opener,
                                    directory=str(cache_env))
    assert result["ok"] and result["skipped"] and result["notModified"]
    assert opener.requests == []


# ---------------------------------------------------------------- 304 复用

def test_304_reuses_cache_and_refreshes_checked_at(cache_env):
    first = seed_cache("regular", checked_at=FIXED_NOW - datetime.timedelta(hours=1))
    digest_before = json.dumps(first["items"], sort_keys=True, ensure_ascii=False)

    def route(req):
        assert req.get_header("If-none-match") == '"etag-1"', "必须带 If-None-Match"
        raise urllib.error.HTTPError(req.full_url, 304, "Not Modified",
                                     {"ETag": '"etag-1"'}, None)

    opener = FakeOpener(route)
    payload = live_prices.build_cache(upstream_doc(), "regular", "https://x", now=FIXED_NOW)
    payload["http"] = {"status": 200, "notModified": False, "etag": '"etag-1"',
                       "lastModified": "Tue, 03 Nov 2026 17:10:34 GMT"}
    live_prices.write_atomic(live_prices.cache_path("regular"), payload)

    result = live_prices.fetch_mode("regular", proxy=None, force=True, opener=opener,
                                    directory=str(cache_env))
    assert result["ok"] and result["notModified"] and result["status"] == 304
    after = live_prices.load_cache("regular")
    assert json.dumps(after["items"], sort_keys=True, ensure_ascii=False) == digest_before
    assert after["checkedAt"] != payload["checkedAt"], "304 必须刷新 checkedAt"
    assert after["fetchedAt"] == payload["fetchedAt"], "304 不改价格抓取时间"
    attempt = live_prices.read_json(str(cache_env / "live-prices-regular.last-attempt.json"))
    assert attempt["ok"] is True and attempt["status"] == 304


def test_304_without_cache_is_validation_error(cache_env):
    def route(req):
        raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)

    result = live_prices.fetch_mode("pve", proxy=None, force=True,
                                    opener=FakeOpener(route), directory=str(cache_env))
    assert result["ok"] is False and result["exitCode"] == 2


# ---------------------------------------------------------------- 网络失败路径

def test_proxy_unreachable_keeps_old_cache(cache_env):
    old = seed_cache("regular", checked_at=FIXED_NOW - datetime.timedelta(hours=2))
    digest_before = json.dumps(old["items"], sort_keys=True, ensure_ascii=False)
    port = closed_port()
    result = live_prices.fetch_mode("regular", proxy="http://127.0.0.1:%d" % port,
                                    force=True, directory=str(cache_env))
    assert result["ok"] is False and result["exitCode"] == 1
    assert "不可达" in result["message"]
    after = live_prices.load_cache("regular")
    assert json.dumps(after["items"], sort_keys=True, ensure_ascii=False) == digest_before
    attempt = live_prices.read_json(str(cache_env / "live-prices-regular.last-attempt.json"))
    assert attempt["ok"] is False and attempt["stage"] == "proxy"


def test_http_error_keeps_old_cache(cache_env):
    old = seed_cache("regular", checked_at=FIXED_NOW - datetime.timedelta(hours=2))
    before = Path(live_prices.cache_path("regular")).read_bytes()

    def route(req):
        raise RuntimeError("上游 HTTP 503")

    result = live_prices.fetch_mode("regular", proxy=None, force=True,
                                    opener=FakeOpener(route), directory=str(cache_env))
    assert result["ok"] is False and result["exitCode"] == 1
    assert Path(live_prices.cache_path("regular")).read_bytes() == before
    assert len(old["items"]) == 1200


def test_successful_fetch_writes_atomic_cache(cache_env):
    opener = FakeOpener(lambda req: FakeResponse(
        200, json.dumps(upstream_doc()).encode("utf-8"),
        {"ETag": '"v2"', "Last-Modified": "Tue, 04 Nov 2026 21:00:00 GMT"}))
    result = live_prices.fetch_mode("pve", proxy=None, force=True, opener=opener,
                                    directory=str(cache_env))
    assert result["ok"] and result["exitCode"] == 0 and not result["notModified"]
    cache = live_prices.load_cache("pve")
    assert cache["priceMode"] == "pve" and len(cache["items"]) == 1200
    assert cache["http"]["etag"] == '"v2"' and cache["http"]["sha256"]


def test_cli_status_is_offline(cache_env, capsys):
    assert live_prices.main(["--status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["modes"]) == {"regular", "pve", "pvps"}
    assert payload["modes"]["regular"]["exists"] is False


# ---------------------------------------------------------------- 配置

def test_config_defaults_live_prices_off(tmp_path):
    cfg = config.default_config()
    assert cfg["livePrices"] == {"enabled": False, "mode": "regular",
                                 "ttlSec": 600, "source": None}
    assert config.live_prices(str(tmp_path))["enabled"] is False


def test_config_normalizes_live_prices(tmp_path):
    cfg = config.save({"livePrices": {"enabled": True, "mode": "pvp",
                                      "ttlSec": 30, "source": "ftp://nope"}},
                      directory=str(tmp_path))
    assert cfg["livePrices"]["enabled"] is True
    assert cfg["livePrices"]["mode"] == "regular", "非法模式回落 regular"
    assert cfg["livePrices"]["ttlSec"] == 60, "TTL 下限 60"
    assert cfg["livePrices"]["source"] is None, "非 http(s) 地址丢弃"
    assert config.save({"livePrices": {"ttlSec": 99999}}, directory=str(tmp_path)
                       )["livePrices"]["ttlSec"] == 3600


# ---------------------------------------------------------------- 服务接口

def _write_config(directory: Path, live: dict) -> None:
    config.save({"livePrices": live}, directory=str(directory))


def _serve(config_dir: Path, **kwargs):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(config_dir),
                                poll_interval=0.2, **kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


def _stop(httpd, thread):
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


def _post(url: str, payload=None, token: str | None = None, headers: dict | None = None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = b"" if payload is None else json.dumps(payload).encode("utf-8")
    extra = {"Content-Type": "application/json"}
    if token:
        extra["X-EFTMap-Token"] = token
    if headers:
        extra.update(headers)
    req = urllib.request.Request(url, data=data, method="POST", headers=extra)
    try:
        with opener.open(req, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def api(tmp_path, cache_env):
    """默认关闭 livePrices 的真实服务。"""
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, config.LIVE_PRICES_DEFAULTS)
    httpd, thread = _serve(cfg_dir)
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        yield base, cfg_dir
    finally:
        _stop(httpd, thread)


def test_endpoint_disabled_returns_snapshot_marker(api, monkeypatch):
    base, _ = api

    def boom(*args, **kwargs):
        raise AssertionError("enabled=false 时接口绝不能联网")

    monkeypatch.setattr(live_prices, "fetch_url", boom)
    status, body = _get(base + "api/live-prices?mode=regular")
    assert status == 200
    assert body["ok"] is True and body["enabled"] is False
    assert body["available"] is False and body["source"] == "snapshot"
    assert body["snapshot"] == "data/flea-prices.json"
    assert body["prices"] == {} and body["count"] == 0 and body["stale"] is True
    assert body["priceMode"] == "pvp" and body["mode"] == "regular"


def test_endpoint_rejects_bad_mode(api):
    base, _ = api
    status, body = _get(base + "api/live-prices?mode=scav")
    assert status == 400 and body["error"] == "bad-mode"
    assert body["allowed"] == ["regular", "pve", "pvps"]


def test_status_endpoint_reports_off_and_both_caches(api):
    base, _ = api
    status, body = _get(base + "api/live-prices/status")
    assert status == 200 and body["ok"] is True
    assert body["enabled"] is False and body["mode"] == "regular"
    assert set(body["modes"]) == {"regular", "pve", "pvps"}
    assert body["modes"]["regular"]["exists"] is False
    assert body["modes"]["pve"]["stale"] is True


def test_refresh_requires_token(tmp_path, cache_env):
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True, "mode": "regular", "ttlSec": 600})
    httpd, thread = _serve(cfg_dir, shutdown_token="secret")
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, body = _post(base + "api/live-prices/refresh")
        assert status == 403 and "token" in body["error"]
        status, body = _post(base + "api/live-prices/refresh", token="wrong")
        assert status == 403
    finally:
        _stop(httpd, thread)


def test_refresh_disabled_returns_409_without_spawning(tmp_path, cache_env, monkeypatch):
    called = []
    monkeypatch.setattr(serve, "spawn_live_fetch",
                        lambda *a, **k: called.append(a) or (True, "spawned"))
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": False})
    httpd, thread = _serve(cfg_dir, shutdown_token="secret")
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, body = _post(base + "api/live-prices/refresh", payload={"mode": "pve"},
                             token="secret")
        assert status == 409 and body["error"] == "disabled"
        assert called == [], "开关关闭时不能启动抓取"
    finally:
        _stop(httpd, thread)


def test_refresh_starts_fetch_when_enabled(tmp_path, cache_env, monkeypatch):
    called = []
    monkeypatch.setattr(serve, "spawn_live_fetch",
                        lambda root, app_dir, mode, settings=None: (
                            called.append((mode, settings["ttlSec"])) or (True, "ok")))
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True, "mode": "regular", "ttlSec": 600})
    httpd, thread = _serve(cfg_dir, shutdown_token="secret")
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, body = _post(base + "api/live-prices/refresh", payload={"mode": "pve"},
                             token="secret")
        assert status == 202 and body["started"] and body["mode"] == "pve"
        assert called == [("pve", 600)]
    finally:
        _stop(httpd, thread)


def test_refresh_rejects_non_loopback(tmp_path, cache_env):
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True})
    Handler = serve.build_handler(str(ROOT), serve.PositionTracker(None),
                                  app_dir=str(cfg_dir), shutdown_token="secret")
    handler = object.__new__(Handler)
    handler.client_address = ("10.1.2.3", 55555)
    handler.headers = {}
    sent = []
    handler._send_json = lambda code, body: sent.append((code, body))
    handler._handle_live_prices_refresh()
    assert sent and sent[0][0] == 403 and "只允许本机" in sent[0][1]["error"]


def test_endpoint_reads_cache_when_enabled(tmp_path, cache_env):
    seed_cache("regular", checked_at=datetime.datetime.now().astimezone())
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True, "mode": "regular", "ttlSec": 600})
    httpd, thread = _serve(cfg_dir)
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, body = _get(base + "api/live-prices")
        assert status == 200 and body["ok"] is True and body["enabled"] is True
        assert body["available"] is True and body["count"] == 1200
        assert body["source"] == live_prices.MODES["regular"]["source"]
        assert body["priceMode"] == "pvp" and body["stale"] is False
        row = body["prices"]["item0000"]
        assert row == {"l": 1000, "a": 900, "u": "2026-11-04T12:00:00.000Z"}
        # 缓存里额外的 b/tb/tn 不暴露给接口，契约只到 l/a/u
        assert all(set(v) <= {"l", "a", "u"} for v in body["prices"].values())
    finally:
        _stop(httpd, thread)


def test_endpoint_enabled_without_cache(tmp_path, cache_env):
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True})
    httpd, thread = _serve(cfg_dir)
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, body = _get(base + "api/live-prices?mode=pve")
        assert status == 200 and body["ok"] is False
        assert body["enabled"] is True and body["available"] is False
        assert body["error"] == "no-cache" and body["prices"] == {}
        assert body["priceMode"] == "pve"
    finally:
        _stop(httpd, thread)


# ---------------------------------------------------------------- 鉴权顺序与矩阵（R42 修后）

def _enabled_server(tmp_path, monkeypatch, enabled: bool = True, token: str | None = "secret"):
    called: list = []
    monkeypatch.setattr(serve, "spawn_live_fetch",
                        lambda root, app_dir, mode, settings=None: (
                            called.append(mode) or (True, "ok")))
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": enabled, "mode": "regular", "ttlSec": 600})
    httpd, thread = _serve(cfg_dir, shutdown_token=token)
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    return httpd, thread, base, called


def test_refresh_disabled_wins_over_missing_credentials(tmp_path, cache_env, monkeypatch):
    """开关关闭时先于凭据判定：无 token、无网页头也必须 409，且不启动抓取。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch, enabled=False)
    try:
        status, body = _post(base + "api/live-prices/refresh", payload={"mode": "pve"})
        assert status == 409 and body["error"] == "disabled" and body["enabled"] is False
        # 带错误 token 也仍然是 409（不能因为 token 错就变成 403）
        status, body = _post(base + "api/live-prices/refresh", token="wrong")
        assert status == 409
        assert called == [], "开关关闭时绝不能启动抓取"
    finally:
        _stop(httpd, thread)


def test_refresh_web_same_origin_allowed(tmp_path, cache_env, monkeypatch):
    """浏览器模式：回环 + X-EFTMap-Client: web + 同源 Origin → 202，via=web，无需 token。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch)
    origin = base.rstrip("/")
    try:
        status, body = _post(base + "api/live-prices/refresh", payload={"mode": "pve"},
                             headers={"X-EFTMap-Client": "web", "Origin": origin})
        assert status == 202 and body["started"] is True
        assert body["mode"] == "pve" and body["via"] == "web"
        assert called == ["pve"]
        # 只带 Referer（某些浏览器/隐私设置不送 Origin）也算同源
        status, body = _post(base + "api/live-prices/refresh",
                             headers={"X-EFTMap-Client": "web",
                                      "Referer": origin + "/index.html"})
        assert status == 202 and body["via"] == "web"
    finally:
        _stop(httpd, thread)


def test_refresh_web_requires_same_origin(tmp_path, cache_env, monkeypatch):
    """自定义头把跨站请求挡在预检之后；再来一层 Origin/Referer 同源校验。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch)
    try:
        # 跨站页面：Origin 是外站（即使伪造了自定义头也不行）
        status, body = _post(base + "api/live-prices/refresh",
                             headers={"X-EFTMap-Client": "web",
                                      "Origin": "http://evil.example"})
        assert status == 403 and "跨站" in body["error"]
        # 没有 Origin/Referer（非浏览器脚本）：同样拒绝
        status, body = _post(base + "api/live-prices/refresh",
                             headers={"X-EFTMap-Client": "web"})
        assert status == 403
        # 完全不带凭据：拒绝
        status, body = _post(base + "api/live-prices/refresh")
        assert status == 403 and "token" in body["error"]
        assert called == []
    finally:
        _stop(httpd, thread)


def test_refresh_desktop_token_unchanged(tmp_path, cache_env, monkeypatch):
    """桌面壳路径保持：正确 token → 202 via=token；错误 token → 403。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch)
    try:
        status, body = _post(base + "api/live-prices/refresh", token="secret")
        assert status == 202 and body["started"] is True and body["via"] == "token"
        status, body = _post(base + "api/live-prices/refresh", token="wrong")
        assert status == 403 and "token" in body["error"]
    finally:
        _stop(httpd, thread)


# ---------------------------------------------------------------- keep-alive（真实 socket）

def _conn(httpd) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)


def _same_connection_get(conn: http.client.HTTPConnection):
    conn.request("GET", "/api/live-prices?mode=regular")
    res = conn.getresponse()
    payload = json.loads(res.read().decode("utf-8"))
    return res, payload


def test_keepalive_after_409_reads_request_body(tmp_path, cache_env, monkeypatch):
    """回归：POST 带 body 被 409 提前返回后，同一条 keep-alive 连接上的 GET 不能是 501。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch, enabled=False)
    conn = _conn(httpd)
    try:
        body = json.dumps({"mode": "pve"}).encode("utf-8")
        conn.request("POST", "/api/live-prices/refresh", body=body,
                     headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        assert res.status == 409
        payload = json.loads(res.read().decode("utf-8"))
        assert payload["error"] == "disabled"
        assert res.getheader("Connection") is None, "能读完 body 就不该关连接"
        res2, payload2 = _same_connection_get(conn)
        assert res2.status == 200, "同连接下一次 GET 不应 501/500"
        assert payload2["enabled"] is False and payload2["source"] == "snapshot"
    finally:
        conn.close()
        _stop(httpd, thread)


def test_keepalive_after_403_reads_request_body(tmp_path, cache_env, monkeypatch):
    """403 提前返回同样要先读尽 body；否则残留字节会被当成下一条请求行。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch)
    conn = _conn(httpd)
    try:
        body = json.dumps({"mode": "regular"}).encode("utf-8")
        conn.request("POST", "/api/live-prices/refresh", body=body,
                     headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        assert res.status == 403
        res.read()
        res2, payload2 = _same_connection_get(conn)
        assert res2.status == 200 and payload2["enabled"] is True
        assert payload2["ok"] is False and payload2["error"] == "no-cache"
    finally:
        conn.close()
        _stop(httpd, thread)


def test_keepalive_oversize_body_closes_connection(tmp_path, cache_env, monkeypatch):
    """413 无法安全丢弃未知大小的 body：显式 Connection: close。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch)
    conn = _conn(httpd)
    try:
        body = b"x" * (serve.MAX_PREFS_BODY + 1024)
        conn.request("POST", "/api/live-prices/refresh", body=body,
                     headers={"Content-Type": "application/json"})
        res = conn.getresponse()
        assert res.status == 413
        assert (res.getheader("Connection") or "").lower() == "close"
        res.read()
    finally:
        conn.close()
        _stop(httpd, thread)


def test_post_without_content_length_does_not_hang(tmp_path, cache_env, monkeypatch):
    """Content-Length 缺失按 0 处理，不阻塞；连接仍可复用。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch, enabled=False)
    conn = _conn(httpd)
    try:
        conn.putrequest("POST", "/api/live-prices/refresh")
        conn.putheader("Content-Type", "application/json")
        conn.endheaders()          # 故意不发 Content-Length
        res = conn.getresponse()
        assert res.status == 409
        res.read()
        res2, payload2 = _same_connection_get(conn)
        assert res2.status == 200
    finally:
        conn.close()
        _stop(httpd, thread)


def test_invalid_content_length_closes_connection(tmp_path, cache_env, monkeypatch):
    """非数字 Content-Length → 400；无法判断 body 长度，显式关连接。"""
    httpd, thread, base, called = _enabled_server(tmp_path, monkeypatch, enabled=False)
    conn = _conn(httpd)
    try:
        conn.putrequest("POST", "/api/live-prices/refresh")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "abc")
        conn.endheaders()
        res = conn.getresponse()
        assert res.status == 400
        assert (res.getheader("Connection") or "").lower() == "close"
        res.read()
    finally:
        conn.close()
        _stop(httpd, thread)


def test_options_preflight_grants_no_cors(tmp_path, cache_env):
    """跨域预检：只回 Allow，不给 Access-Control-Allow-* → 浏览器拦下跨站 POST。"""
    cfg_dir = tmp_path / "cfg"
    _write_config(cfg_dir, {"enabled": True})
    httpd, thread = _serve(cfg_dir)
    conn = _conn(httpd)
    try:
        conn.request("OPTIONS", "/api/live-prices/refresh", headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-eftmap-client, content-type",
        })
        res = conn.getresponse()
        res.read()
        assert res.status == 204
        assert res.getheader("Access-Control-Allow-Origin") is None
        assert res.getheader("Access-Control-Allow-Headers") is None
        assert "POST" in (res.getheader("Allow") or "")
    finally:
        conn.close()
        _stop(httpd, thread)
