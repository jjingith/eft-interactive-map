"""`tools/serve.py`（M1 部分）的测试：静态托管、/api/health、错误处理。

M2 追加 SSE 与位置接口后会在此文件继续补用例（SSE 首帧、广播、目录缺失降级）。
测试全部走真实的 socket（端口 0 由系统分配），不联网、不依赖外部资源。
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import serve

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def base_url():
    httpd = serve.create_server(0, "127.0.0.1", str(ROOT))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield serve.url_for("127.0.0.1", httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def get(url: str):
    """返回 (status, content_type, body_bytes)，HTTP 错误也当正常结果返回。

    显式禁用代理：本机环境设了 HTTP_PROXY，urllib 会把 127.0.0.1 也送去代理导致 502。
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=20) as res:
            return res.status, res.headers.get("Content-Type", ""), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()


def get_json(url: str):
    status, ctype, body = get(url)
    assert "application/json" in ctype, ctype
    return status, json.loads(body.decode("utf-8"))


# --------------------------------------------------------------- 静态托管

def test_index_html_served(base_url):
    status, ctype, body = get(base_url + "index.html")
    assert status == 200
    assert "text/html" in ctype
    assert b"map-svg" in body


def test_root_path_serves_index(base_url):
    status, _, body = get(base_url)
    assert status == 200
    assert b"EFT" in body


def test_svg_gets_correct_content_type(base_url):
    """.svg 必须返回 image/svg+xml，否则浏览器可能拒绝按图片渲染（Windows 上标准库会猜错）。"""
    status, ctype, body = get(base_url + "assets/maps/Customs.svg")
    assert status == 200
    assert ctype.startswith("image/svg+xml")
    assert b"<svg" in body[:2000]


def test_maps_json_served(base_url):
    status, ctype, body = get(base_url + "data/maps.json")
    assert status == 200
    assert "application/json" in ctype
    assert json.loads(body.decode("utf-8"))["maps"]


def test_missing_file_is_404(base_url):
    status, _, _ = get(base_url + "no-such-file.txt")
    assert status == 404


# --------------------------------------------------------------- API

def test_health_reports_ready_and_map_count(base_url):
    status, payload = get_json(base_url + "api/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["app"] == serve.APP_ID
    assert payload["version"] == serve.VERSION
    assert payload["data"]["ready"] is True
    assert payload["data"]["maps"] >= 10


def test_unknown_api_returns_json_404(base_url):
    status, payload = get_json(base_url + "api/nope")
    assert status == 404
    assert payload["ok"] is False


def test_health_degrades_when_data_missing(tmp_path):
    """数据缺失时 /api/health 仍要能回答（launcher 靠它判断该提示什么），只是 ok=false。"""
    (tmp_path / "index.html").write_text("<!doctype html><title>t</title>", encoding="utf-8")
    httpd = serve.create_server(0, "127.0.0.1", str(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/health")
        assert status == 200
        assert payload["ok"] is False
        assert payload["data"]["maps"] == 0
        assert "maps.json" in payload["data"]["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


# --------------------------------------------------------------- 启动与报错

def test_missing_index_html_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        serve.create_server(0, "127.0.0.1", str(tmp_path))


def test_port_in_use_raises_clear_error():
    """端口占用必须抛 PortInUseError（且真的没占到端口），launcher 才能给出可操作提示。"""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        with pytest.raises(serve.PortInUseError) as info:
            serve.create_server(port, "127.0.0.1", str(ROOT))
        assert str(port) in str(info.value)
        assert "--port" in str(info.value)
    finally:
        blocker.close()


def test_url_for_maps_wildcard_host_to_loopback():
    assert serve.url_for("0.0.0.0", 8787) == "http://127.0.0.1:8787/"
    assert serve.url_for("127.0.0.1", 9000) == "http://127.0.0.1:9000/"


def test_main_reports_port_conflict():
    """CLI 路径：端口占用时返回退出码 2，而不是抛异常。"""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        assert serve.main(["--port", str(port), "--no-browser"]) == 2
    finally:
        blocker.close()
