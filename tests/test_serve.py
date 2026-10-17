"""`tools/serve.py` 的测试：静态托管、/api/health、/api/position、SSE、错误处理。

测试全部走真实的 socket（端口 0 由系统分配），不联网、不依赖外部资源。
实时定位用 tmp_path 造「假截图目录」（只写文件名，不含任何图片内容）。
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
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


def serve_dir(screenshots: str | None = None, poll_interval: float = 0.1, root=ROOT):
    """起一个带（或不带）截图目录的真实服务，返回 (base_url, httpd, thread)。"""
    httpd = serve.create_server(0, "127.0.0.1", str(root), screenshots=screenshots, poll_interval=poll_interval)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return serve.url_for("127.0.0.1", httpd.server_address[1]), httpd, thread


def stop(httpd, thread):
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def fake_shot(directory, x, z, yaw_quat=(0.0, 0.0, 0.0, 1.0), when=None, name=None):
    """写一个**真实格式**的截图文件名（只写文件名，不写图片内容）。"""
    name = name or ("2026-09-19[10-44]_%s, 1.00, %s_%s (0).png"
                    % (x, z, ", ".join(str(v) for v in yaw_quat)))
    path = Path(directory) / name
    path.write_bytes(b"fake")
    if when is not None:
        os.utime(path, (when, when))
    return path


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


# --------------------------------------------------------------- /api/position

def test_position_disabled_when_no_screenshots_dir():
    url, httpd, thread = serve_dir(None)
    try:
        _, payload = get_json(url + "api/position")
        assert payload["available"] is False
        assert payload["position"] is None
        assert "--screenshots" in payload["reason"]
    finally:
        stop(httpd, thread)


def test_position_reports_latest_parsed_screenshot(tmp_path):
    fake_shot(tmp_path, "123.45", "-678.90")
    url, httpd, thread = serve_dir(str(tmp_path))
    try:
        _, payload = get_json(url + "api/position")
        assert payload["available"] is True
        pos = payload["position"]
        assert (pos["x"], pos["z"]) == (123.45, -678.90)
        assert pos["yaw"] == pytest.approx(0.0)
        assert pos["name"].endswith(".png")
        assert pos["mtime"] > 0
    finally:
        stop(httpd, thread)


def test_position_degrades_when_directory_missing(tmp_path):
    """目录不存在只能降级，不能 500、不能停服。"""
    url, httpd, thread = serve_dir(str(tmp_path / "nope"))
    try:
        status, payload = get_json(url + "api/position")
        assert status == 200
        assert payload["available"] is False
        assert "不存在" in payload["reason"]
        # 其它功能照常
        assert get_json(url + "api/health")[1]["ok"] is True
    finally:
        stop(httpd, thread)


def test_position_picks_newest_by_mtime(tmp_path):
    now = time.time()
    fake_shot(tmp_path, "1.00", "1.00", when=now - 100)
    fake_shot(tmp_path, "2.00", "2.00", when=now)
    url, httpd, thread = serve_dir(str(tmp_path))
    try:
        _, payload = get_json(url + "api/position")
        assert payload["position"]["x"] == 2.00
    finally:
        stop(httpd, thread)


def test_health_exposes_position_state(tmp_path):
    fake_shot(tmp_path, "5.00", "5.00")
    url, httpd, thread = serve_dir(str(tmp_path))
    try:
        _, payload = get_json(url + "api/health")
        assert payload["position"] is True
        assert payload["positionAvailable"] is True
        assert payload["screenshots"] == str(tmp_path)
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- SSE

def _response_socket(response):
    """取 SSE 响应底层的 socket，用来把读超时压到本次探针的时长内。"""
    try:
        return response.fp.raw._sock          # urllib 返回的 http.client.HTTPResponse
    except AttributeError:
        return None


def read_frames(response, count: int, timeout: float = 8.0):
    """从 SSE 流里读 count 条 `data: {...}` 帧（跳过 `:` 心跳注释）。

    读到 count 条或到 timeout 就返回；超时无帧返回 []（socket 到期会抛 TimeoutError，
    不捕获会把「这段时间内没有新帧」误报成测试异常）。
    """
    frames = []
    deadline = time.monotonic() + timeout
    sock = _response_socket(response)
    while len(frames) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if sock is not None:
            sock.settimeout(remaining)
        try:
            line = response.readline()
        except (TimeoutError, OSError):
            break
        if not line:
            break
        text = line.decode("utf-8").strip()
        if text.startswith("data:"):
            frames.append(json.loads(text[5:].strip()))
    return frames


def test_sse_sends_current_state_immediately(tmp_path):
    """连上就先给一帧：首屏不必等下一次变更。"""
    fake_shot(tmp_path, "42.00", "43.00")
    url, httpd, thread = serve_dir(str(tmp_path))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        assert res.headers.get("Content-Type", "").startswith("text/event-stream")
        frames = read_frames(res, 1)
        assert frames and frames[0]["position"]["x"] == 42.00
        res.close()
    finally:
        stop(httpd, thread)


def test_sse_broadcasts_new_screenshot(tmp_path):
    """新截图出现后必须被推给已订阅的页面（这是实时定位的核心链路）。"""
    fake_shot(tmp_path, "10.00", "10.00")
    url, httpd, thread = serve_dir(str(tmp_path), poll_interval=0.05)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        assert read_frames(res, 1)[0]["position"]["x"] == 10.00

        time.sleep(0.3)
        fake_shot(tmp_path, "20.00", "20.00")       # 新的一张，mtime 更晚
        frames = read_frames(res, 1)
        assert [f["position"]["x"] for f in frames] == [20.00]
        res.close()
    finally:
        stop(httpd, thread)


def test_sse_does_not_repeat_unchanged_position(tmp_path):
    """位置没变就不该反复推：心跳之外不应有多余帧。"""
    fake_shot(tmp_path, "7.00", "7.00")
    url, httpd, thread = serve_dir(str(tmp_path), poll_interval=0.05)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        assert read_frames(res, 1)[0]["position"]["x"] == 7.00
        assert read_frames(res, 1, timeout=0.8) == []      # 0.8 秒内不该有第二帧
        res.close()
    finally:
        stop(httpd, thread)


def test_sse_reports_unavailable_without_screenshots():
    url, httpd, thread = serve_dir(None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        frames = read_frames(res, 1)
        assert frames[0]["available"] is False
        res.close()
    finally:
        stop(httpd, thread)


def test_sse_client_disconnect_unsubscribes(tmp_path, monkeypatch):
    """页面关闭后订阅者必须被摘掉，否则监听线程会一直往死连接里写。

    服务端只在**写帧/写心跳失败**时才发现断连，故把心跳压到 0.3s（等价于真实场景里
    等一个心跳周期），保证 4 秒内必定触发一次写盘失败。
    """
    monkeypatch.setattr(serve, "SSE_HEARTBEAT", 0.3)
    fake_shot(tmp_path, "1.00", "1.00")
    url, httpd, thread = serve_dir(str(tmp_path), poll_interval=0.05)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        read_frames(res, 1)
        assert httpd.tracker.broadcaster.subscriber_count() == 1
        res.close()
        fake_shot(tmp_path, "2.00", "2.00")        # 再推一帧，加速服务端发现断连
        for _ in range(40):
            if httpd.tracker.broadcaster.subscriber_count() == 0:
                break
            time.sleep(0.1)
        assert httpd.tracker.broadcaster.subscriber_count() == 0
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- tracker 单元

def test_tracker_poll_once_detects_change_only(tmp_path):
    fake_shot(tmp_path, "1.00", "1.00")
    tracker = serve.PositionTracker(str(tmp_path))
    assert tracker.poll_once() is True       # 首次拿到位置
    assert tracker.poll_once() is False      # 没变就不再推
    time.sleep(0.02)
    fake_shot(tmp_path, "2.00", "2.00")
    assert tracker.poll_once() is True
    assert tracker.snapshot()["position"]["x"] == 2.00


def test_tracker_start_is_noop_without_directory():
    tracker = serve.PositionTracker(None)
    tracker.start()
    assert tracker._thread is None
    tracker.stop()          # 可重复调用


def test_broadcaster_drops_frames_when_subscriber_is_full():
    b = serve.Broadcaster()
    q = b.subscribe()
    b.publish({"n": 1})
    assert q.get_nowait() == {"n": 1}
    for i in range(200):                    # 塞满队列后不应抛异常
        b.publish({"n": i})
    b.unsubscribe(q)
    assert b.subscriber_count() == 0


def test_default_screenshots_dir_shape():
    assert serve.default_screenshots_dir().endswith(os.path.join("Escape from Tarkov", "Screenshots"))


def test_resolve_screenshots_prefers_explicit_dir(tmp_path):
    class Args:
        no_position = False
        screenshots = str(tmp_path)

    assert serve.resolve_screenshots(Args()) == str(tmp_path)


def test_resolve_screenshots_respects_no_position():
    class Args:
        no_position = True
        screenshots = "C:/whatever"

    assert serve.resolve_screenshots(Args()) is None

