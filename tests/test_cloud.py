"""云账号 BFF 的单元测试：不联网，全部用假 _request 替身。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import cloud
import config
import serve

ROOT = Path(__file__).resolve().parent.parent


def make_client(tmp_path) -> cloud.CloudClient:
    return cloud.CloudClient(str(tmp_path), str(ROOT / "assets" / "cloud-ca.pem"))


def stub_request(client: cloud.CloudClient, handler) -> list:
    calls = []

    def fake(method, path, *, payload=None, token=None, retryable=False):
        calls.append({"method": method, "path": path, "payload": payload, "token": token})
        return handler(method, path, payload, token)

    client._request = fake  # type: ignore[method-assign]
    return calls


def test_login_persists_session_and_status(tmp_path):
    client = make_client(tmp_path)
    seen = stub_request(
        client,
        lambda method, path, payload, token: (
            200,
            {
                "status": "ok",
                "session": {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 900,
                    "refresh_expires_in": 86400,
                },
                "last_login": {"at": "2026-01-01T00:00:00+00:00", "ip": "1.2.3.4"},
            },
        )
        if path.endswith("/auth/login")
        else pytest.fail("unexpected " + path),
    )

    result = client.login("a@example.com", "hunter2")
    assert result["email"] == "a@example.com"
    assert result["last_login"]["ip"] == "1.2.3.4"

    session_file = tmp_path / cloud.SESSION_NAME
    assert json.loads(session_file.read_text(encoding="utf-8"))["access_token"] == "access-1"

    # 设备 ID 首次生成后落盘，并随请求一起上行
    device = json.loads((tmp_path / cloud.DEVICE_NAME).read_text(encoding="utf-8"))
    assert device["device_id"]
    assert seen[0]["payload"]["device_id"] == device["device_id"]
    assert set(seen[0]["payload"]["fingerprint"]) == {"machine", "volume", "mac"}

    status = client.status()
    assert status["logged_in"] is True
    assert status["email"] == "a@example.com"


def test_login_returns_verification_required_for_new_device(tmp_path):
    client = make_client(tmp_path)
    stub_request(
        client,
        lambda method, path, payload, token: (
            202,
            {
                "status": "verification_required",
                "reason": "new_device",
                "challenge": "challenge-1",
                "expires_in": 600,
                "message": "新设备需要邮箱验证",
            },
        )
        if path.endswith("/auth/login")
        else pytest.fail("unexpected " + path),
    )

    result = client.login("a@example.com", "hunter2")
    assert result["status"] == "verification_required"
    assert result["reason"] == "new_device"
    assert result["challenge"] == "challenge-1"
    assert client.status()["logged_in"] is False


def test_access_token_refreshes_only_before_expiry(tmp_path):
    client = make_client(tmp_path)
    client._session = {
        "email": "a@example.com",
        "access_token": "old",
        "refresh_token": "refresh-1",
        "access_expires_at": 0,  # 已过期
        "refresh_expires_at": 0,
    }
    calls = stub_request(
        client,
        lambda method, path, payload, token: (
            (200, {"access_token": "new", "refresh_token": "refresh-2",
                   "expires_in": 900, "refresh_expires_in": 86400})
            if path.endswith("/auth/refresh")
            else (200, {"email": "a@example.com", "email_verified": True,
                        "created_at": "2026-01-01T00:00:00+00:00"})
        ),
    )

    assert client.me()["email"] == "a@example.com"
    assert [call["path"] for call in calls] == ["/v1/auth/refresh", "/v1/auth/me"]
    assert calls[1]["token"] == "new"
    # 刷新后新的 access 到点才刷，不会周期性刷新
    assert client.status()["access_expires_in"] > 800


def test_me_caches_server_member_state(tmp_path):
    """R108：会员态只认服务端 /auth/me 的返回；本地配置不再参与。"""
    client = make_client(tmp_path)
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12}
    member = {
        "member": True, "member_status": "permanent", "member_plan": "permanent",
        "member_since": "2026-01-01T00:00:00+00:00", "member_expires_at": None,
    }
    stub_request(client, lambda method, path, payload, token: (200, {
        "email": "a@example.com", "email_verified": True, "has_password": True,
        "created_at": "2026-01-01T00:00:00+00:00", **member,
    }))

    assert config.is_member() is False
    client.me()
    assert config.is_member() is True
    # 快照写进会话缓存，离线重启也能展示
    assert client._load(cloud.SESSION_NAME)["member"] == member


def test_logout_clears_cached_member_state(tmp_path):
    client = make_client(tmp_path)
    client._session = {
        "email": "a@example.com", "access_token": "access-1",
        "refresh_token": "refresh-1", "access_expires_at": 10**12,
        "member": {"member": True, "member_status": "permanent", "member_plan": "permanent",
                   "member_since": "2026-01-01T00:00:00+00:00", "member_expires_at": None},
    }
    client._save(cloud.SESSION_NAME, client._session)
    config.set_member_state(client._session["member"])
    stub_request(client, lambda method, path, payload, token: (200, {"ok": True}))

    client.logout()
    assert config.is_member() is False


def test_sync_uploads_only_changed_keys(tmp_path):
    client = make_client(tmp_path)
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12}
    config.set_member_state({"member": True, "member_status": "permanent"})
    seen: list[dict] = []

    def handler(method, path, payload, token):
        seen.append({"method": method, "path": path, "payload": payload})
        if path.endswith("/sync/push"):
            return 200, {"rev": 1, "applied": 1, "conflicts": {}, "remote": {}}
        raise AssertionError("unexpected " + path)

    stub_request(client, handler)
    result = client.sync({"progress.pvp": '{"done":[1]}'})
    assert result["uploaded"] == 1
    push = seen[0]["payload"]
    assert push["base_rev"] == 0
    assert set(push["changes"]) == {"progress.pvp"}
    assert len(push["changes"]["progress.pvp"]["hash"]) == 16

    # 同一内容第二次同步：没有变化 → 只发一个 state 请求（304）
    seen.clear()

    def handler2(method, path, payload, token):
        seen.append({"method": method, "path": path, "payload": payload})
        if path.startswith("/v1/sync/state"):
            return 304, None
        raise AssertionError("unexpected " + path)

    stub_request(client, handler2)
    result = client.sync({"progress.pvp": '{"done":[1]}'})
    assert result["uploaded"] == 0
    assert [item["method"] for item in seen] == ["GET"]


def test_sync_pulls_remote_changed_keys(tmp_path):
    client = make_client(tmp_path)
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12}
    config.set_member_state({"member": True, "member_status": "permanent"})
    # 本地内容已经同步过（哈希一致），所以这次不会上传
    client._sync = {
        "account": "a@example.com",
        "rev": 1,
        "hashes": {"progress.pvp": cloud._hash_value('{"done":[1]}')},
    }

    def handler(method, path, payload, token):
        if path.startswith("/v1/sync/state"):
            return 200, {"rev": 2, "keys": {"progress.pve": "bbbbbbbbbbbbbbbb"}}
        if path.endswith("/sync/fetch"):
            assert payload["keys"] == ["progress.pve"]
            return 200, {"keys": {"progress.pve": {
                "hash": "bbbbbbbbbbbbbbbb", "value": '{"done":[2]}'}}}
        raise AssertionError("unexpected " + path)

    stub_request(client, handler)
    result = client.sync({"progress.pvp": '{"done":[1]}'})
    assert result["remote"] == {"progress.pve": '{"done":[2]}'}
    assert result["download"] == 1


def test_sync_is_gated_for_non_members(tmp_path):
    """非会员：BFF 直接 403，不发起任何 /v1/sync/* 请求。"""
    client = make_client(tmp_path)
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12}
    calls = stub_request(client, lambda *args: pytest.fail("非会员不应发起同步请求"))

    with pytest.raises(cloud.CloudError) as caught:
        client.sync({"progress.pvp": '{"done":[1]}'})
    assert caught.value.status == 403
    assert caught.value.code == "membership_required"
    assert calls == []


def test_sync_403_clears_member_cache(tmp_path):
    """服务端 403 membership_required：视同非会员，保留登录态但清掉会员缓存。"""
    client = make_client(tmp_path)
    member = {"member": True, "member_status": "permanent", "member_plan": "permanent",
              "member_since": "2026-01-01T00:00:00+00:00", "member_expires_at": None}
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12,
                       "member": member}
    client._save(cloud.SESSION_NAME, client._session)
    config.set_member_state(member)

    def handler(method, path, payload, token):
        raise cloud.CloudError(403, "membership_required", "云同步是会员功能",
                               member_status="expired")

    stub_request(client, handler)
    with pytest.raises(cloud.CloudError) as caught:
        client.sync({"progress.pvp": '{"done":[1]}'})
    assert caught.value.code == "membership_required"
    assert config.is_member() is False
    assert config.member_state()["member_status"] == "expired"
    cached = client._load(cloud.SESSION_NAME)
    assert cached["access_token"] == "access-1"   # 仍保持登录，仅同步被锁
    assert cached["member"]["member"] is False
    assert cached["member"]["member_status"] == "expired"


def test_status_reports_member_snapshot(tmp_path):
    """面板打开时靠 /api/cloud/status 拿会员快照，立即按会员态渲染同步区。"""
    client = make_client(tmp_path)
    client._session = {"email": "a@example.com", "access_token": "access-1",
                       "refresh_token": "refresh-1", "access_expires_at": 10**12}
    config.set_member_state({"member": True, "member_status": "permanent"})

    status = client.status()
    assert status["member"]["member"] is True
    assert status["member"]["member_status"] == "permanent"

    config.set_member_state({"member": False, "member_status": "expired"})
    status = client.status()
    assert status["member"]["member"] is False
    assert status["member"]["member_status"] == "expired"


def test_request_consumes_three_tuple(tmp_path):
    client = make_client(tmp_path)
    client._request_once = lambda *args, **kwargs: (200, {"ok": True}, {})  # type: ignore[method-assign]
    status, data = client._request("GET", "/v1/ping", retryable=True)
    assert status == 200
    assert data == {"ok": True}


def test_rate_limit_error_carries_retry_after(tmp_path):
    client = make_client(tmp_path)
    client._request_once = lambda method, path, payload, token: (  # type: ignore[method-assign]
        429,
        {
            "error": {
                "code": "too_many_attempts",
                "message": "请求过于频繁，请在 42 秒后重试",
                "retry_after": 42,
            }
        },
        {},
    )

    with pytest.raises(cloud.CloudError) as caught:
        client._request("POST", "/v1/auth/register", payload={})
    assert caught.value.status == 429
    assert caught.value.retry_after == 42


def test_register_verify_requires_session_from_server(tmp_path):
    client = make_client(tmp_path)
    seen = stub_request(
        client,
        lambda method, path, payload, token: (
            200, {"verified": True, "email": "a@example.com", "purpose": "register"}
        )
        if path.endswith("/auth/verify-email")
        else pytest.fail("unexpected " + path),
    )

    # 验证通过却没会话：说明服务端不是新版本，绝不悄悄退化成「无需登录」
    with pytest.raises(cloud.CloudError) as caught:
        client.verify_register("a@example.com", "123456")
    assert caught.value.code == "invalid_response"
    assert seen[0]["payload"]["device_id"]
    assert client.status()["logged_in"] is False


def test_password_reset_and_change_clear_local_session(tmp_path):
    client = make_client(tmp_path)

    def handler(method, path, payload, token):
        if path.endswith("/password/reset"):
            return 200, {"status": "reset"}
        if path.endswith("/password/change"):
            return 200, {"status": "changed"}
        raise AssertionError("unexpected " + path)

    stub_request(client, handler)
    client._session = {
        "email": "a@example.com",
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "access_expires_at": 10**12,
    }

    client.reset_password("a@example.com", "123456", "new-pass")
    assert client.status()["logged_in"] is False

    client._session = {
        "email": "a@example.com",
        "access_token": "access-2",
        "refresh_token": "refresh-2",
        "access_expires_at": 10**12,
    }
    client.change_password("654321", "new-pass")
    assert client.status()["logged_in"] is False


def test_devices_list_and_remove_current_clears_session(tmp_path):
    client = make_client(tmp_path)
    client._session = {
        "email": "a@example.com",
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "access_expires_at": 10**12,
    }
    seen: list[dict] = []

    def handler(method, path, payload, token):
        seen.append({"method": method, "path": path, "payload": payload})
        if path.endswith("/auth/devices"):
            return 200, {
                "devices": [{"device_id": "dev-1", "current": True}],
                "max_devices": 3,
                "max_active": 2,
            }
        if path.endswith("/auth/devices/remove"):
            return 200, {"removed": True, "device_id": "dev-1", "current": True}
        raise AssertionError("unexpected " + path)

    stub_request(client, handler)
    assert client.devices()["max_devices"] == 3
    result = client.revoke_device("dev-1")
    assert result["current"] is True
    assert client.status()["logged_in"] is False


def test_cloud_body_limit_covers_three_256kb_keys(tmp_path):
    # BFF 接收 3 个键的完整进度；上限至少要容纳 3 × 256 KB，且仍保留自己的上界
    assert serve.MAX_CLOUD_BODY >= 3 * 256 * 1024
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # 256 KB 的键值应能被读入（未登录应报 401，而不是 413）
        body = json.dumps({"values": {"progress.regular": "z" * (256 * 1024)}}).encode("utf-8")
        request = urllib.request.Request(
            base + "/api/cloud/sync",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            opener.open(request, timeout=10)
        assert caught.value.code == 401

        # 超过 BFF 上限仍拒绝
        huge = json.dumps({"values": {"progress.regular": "z" * (1024 * 1024)}}).encode("utf-8")
        request = urllib.request.Request(
            base + "/api/cloud/sync",
            data=huge,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as rejected:
            opener.open(request, timeout=10)
        assert rejected.value.code == 413
        payload = json.loads(rejected.value.read().decode("utf-8"))
        assert payload["code"] == "payload_too_large"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_bff_sync_route_locks_non_member(tmp_path):
    """已登录但不是会员：BFF 直接 403 membership_required，不再打云端。"""
    session = {"email": "a@example.com", "access_token": "access-1",
               "refresh_token": "refresh-1", "access_expires_at": 10**12}
    (tmp_path / cloud.SESSION_NAME).write_text(json.dumps(session), encoding="utf-8")

    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        status_url = base + "/api/cloud/status"
        with opener.open(status_url, timeout=10) as res:
            body = json.loads(res.read().decode("utf-8"))
        assert body["logged_in"] is True
        assert body["member"]["member"] is False

        request = urllib.request.Request(
            base + "/api/cloud/sync",
            data=json.dumps({"values": {"progress.pvp": "{}"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            opener.open(request, timeout=10)
        assert caught.value.code == 403
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["code"] == "membership_required"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_cloud_routes_are_wired(tmp_path):
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT), config_dir=str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base + "/api/cloud/status", timeout=10) as res:
            body = json.loads(res.read().decode("utf-8"))
        assert body["ok"] is True
        assert body["logged_in"] is False

        request = urllib.request.Request(
            base + "/api/cloud/sync",
            data=json.dumps({"values": {"progress.pvp": "{}"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            opener.open(request, timeout=10)
        assert caught.value.code == 401
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["code"] == "unauthorized"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
