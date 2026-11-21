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

import config
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


def serve_dir(screenshots: str | None = None, poll_interval: float = 0.1, root=ROOT,
              game_dir: str | None = None, config_dir: str | None = None):
    """起一个带（或不带）截图目录 / 游戏目录的真实服务，返回 (base_url, httpd, thread)。"""
    kwargs = {}
    if game_dir is not None:
        kwargs["game_dir"] = game_dir
    if config_dir is not None:
        kwargs["config_dir"] = config_dir
    httpd = serve.create_server(0, "127.0.0.1", str(root), screenshots=screenshots,
                                poll_interval=poll_interval, **kwargs)
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


def post_json(url: str, payload, raw: bytes | None = None):
    """POST JSON，返回 (status, 解析后的 body)；HTTP 错误也当正常结果返回。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = raw if raw is not None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=20) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


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


def test_items_json_served(base_url):
    """物品资料库（配装 / 配枪视图用）也要能静态取到，且里面真有带槽位的装备。"""
    status, ctype, body = get(base_url + "data/items.json")
    assert status == 200
    assert "application/json" in ctype
    payload = json.loads(body.decode("utf-8"))
    assert payload["count"] == len(payload["items"])
    gear = [rec for rec in payload["items"].values() if rec.get("slot")]
    assert gear


def test_item_icon_gets_webp_content_type(base_url):
    """物品图标是 .webp：标准库要给出 image/webp，否则浏览器可能不按图片渲染。"""
    _, _, body = get(base_url + "data/items.json")
    items = json.loads(body.decode("utf-8"))["items"]
    item_id = next(i for i, rec in items.items() if rec.get("ic"))
    status, ctype, icon = get(base_url + "assets/icons-items/%s.webp" % item_id)
    assert status == 200
    assert ctype.startswith("image/webp")
    assert icon[:4] == b"RIFF" and icon[8:12] == b"WEBP"


def test_missing_file_is_404(base_url):
    status, _, _ = get(base_url + "no-such-file.txt")
    assert status == 404


def test_static_files_are_not_cached(base_url):
    """静态文件也必须禁缓存：否则换了新版本，浏览器仍拿旧 app.js（曾表现为「打包了新版却还是旧界面」）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in ("app.js", "style.css", "data/maps.json", "index.html"):
        with opener.open(base_url + path, timeout=20) as res:
            cache = res.headers.get("Cache-Control", "")
            assert "no-store" in cache, "%s 的 Cache-Control 是 %r" % (path, cache)
            assert res.headers.get("Pragma") == "no-cache"


def test_api_responses_declare_cache_policy(base_url):
    """接口自己声明过缓存策略，不该再被叠一层（避免重复头）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base_url + "api/health", timeout=20) as res:
        values = res.headers.get_all("Cache-Control") or []
    assert values == ["no-store"], values


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
    assert serve.url_for("", 9000) == "http://127.0.0.1:9000/"


def test_lan_address_is_plausible_or_none():
    """局域网地址探测：要么给出一个非回环 IPv4，要么返回 None；绝不抛异常、不发包。"""
    ip = serve.lan_address()
    assert ip is None or (isinstance(ip, str) and ip.count(".") == 3 and not ip.startswith("127."))


def test_url_for_lan_uses_detected_ip():
    ip = serve.lan_address()
    url = serve.url_for_lan(8787)
    if ip is None:
        assert url is None
    else:
        assert url == "http://%s:8787/" % ip


def test_lan_hint_only_when_listening_on_all_interfaces(monkeypatch):
    monkeypatch.setattr(serve, "lan_address", lambda: "192.168.1.23")
    assert serve.lan_hint("127.0.0.1", 8787) is None
    hint = serve.lan_hint("0.0.0.0", 8787)
    assert hint and "http://192.168.1.23:8787/" in hint and "防火墙" in hint
    monkeypatch.setattr(serve, "lan_address", lambda: None)
    assert "未探测到" in serve.lan_hint("0.0.0.0", 8787)


def test_is_network_path_flags_unc_only():
    """UNC 路径（游戏在另一台电脑）要能识别出来，好提示「模拟按键跨机无效」。"""
    assert serve.is_network_path(r"\\JJPC\eft") is True
    assert serve.is_network_path("//JJPC/eft") is True
    assert serve.is_network_path(r"D:\EFT") is False
    assert serve.is_network_path("E:/Games/EFT") is False
    assert serve.is_network_path("") is False
    assert serve.is_network_path(None) is False


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


def _read_sse(response, count: int, timeout: float = 8.0, want: str | tuple | None = None):
    """从 SSE 流里读 count 条消息，返回负载列表。

    `want=None` 只收**无名帧**（实时位置）；给事件名（config/state/raid/quest）
    则只收该命名事件；给名字元组则收其中任意一种。
    读到 count 条或到 timeout 就返回；超时无帧返回 []（socket 到期会抛
    TimeoutError，不捕获会把「这段时间内没有新帧」误报成测试异常）。

    R32.10：事件现在按**时间戳**合流广播（两条日志流排序后合并），所以
    「先 raid 后 quest」这种到达顺序不能当前提——需要多类事件时给元组一起收。
    """
    frames = []
    deadline = time.monotonic() + timeout
    sock = _response_socket(response)
    name = None
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
        if text.startswith("event:"):
            name = text[6:].strip()
            continue
        if not text:            # 空行 = 一条消息结束，事件名归零
            name = None
            continue
        if text.startswith("data:"):
            payload = json.loads(text[5:].strip())
            if isinstance(want, (tuple, list, set)):
                matched = name in want
            else:
                matched = name == want
            if matched:
                frames.append(payload)
    return frames


def read_frames(response, count: int, timeout: float = 8.0):
    """只读无名帧（实时位置），命名事件一律跳过。"""
    return _read_sse(response, count, timeout, want=None)


def read_event(response, name: str, count: int = 1, timeout: float = 8.0):
    """只读某个 SSE 命名事件的负载。"""
    return _read_sse(response, count, timeout, want=name)


def open_stream(url: str, path: str = "events"):
    """打开 SSE 流（显式绕过代理，理由同 get()）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(url + path, timeout=15)


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
    # R108：这条测的是 SSE 推送链路本身，声明会员态以关闭非会员的 10 秒位置节流。
    # 注意：create_server 会构造 CloudClient，其初始化会按会话缓存重设会员态，
    # 所以要在起服务之后、订阅之前再声明一次。
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    url, httpd, thread = serve_dir(str(tmp_path), poll_interval=0.05, config_dir=str(cfg_dir))
    config.set_member_state({"member": True, "member_status": "permanent"})
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
    # R108：这里测的是「变化才推」的原始语义，声明会员态以关闭位置节流
    # （非会员的 10 秒节流见 test_member_gate）。
    tracker = serve.PositionTracker(str(tmp_path), member=lambda: True)
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


# --------------------------------------------------------------- /api/config

def test_config_endpoint_reports_defaults(tmp_path):
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        status, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/config")
        assert status == 200
        assert payload["config"]["auto_center"] is True
        assert payload["config"]["sound"]["enabled"] is False
        # R32：默认间隔改成 5 秒（1 秒一张 ≈ 2 GB/小时），断言盯常量而不是硬编码
        # R108：默认是非会员，所以落锁定值 10000ms
        assert payload["config"]["auto_screenshot"] == {
            "enabled": False, "interval_ms": config.SHOT_INTERVAL_LOCKED_MS, "key": None,
            "cleanup_on_raid_end": False}
        assert payload["config"]["account"] == {"member": False}
        assert payload["resolved"]["appDir"] == str(tmp_path)
        assert payload["resolved"]["soundsDir"] == str(tmp_path / "sounds")
    finally:
        stop(httpd, thread)


def test_config_endpoint_reflects_saved_file(tmp_path):
    import config

    config.save({"auto_zoom": True, "auto_center": False, "sound": {"enabled": True}}, str(tmp_path))
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/config")
        assert payload["config"]["auto_zoom"] is True
        assert payload["config"]["auto_center"] is False
        assert payload["config"]["sound"]["enabled"] is True
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- /api/prefs

def test_prefs_endpoint_saves_page_layer_toggles(tmp_path):
    """页面上勾掉的物资点要落进配置文件，重启后还在（这是「勾选的物资点也能保存」的落地处）。"""
    import config

    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        url = serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/prefs"
        status, payload = post_json(url, {"ui": {"layers": {"loose": False}, "floor_auto": False}})
        assert status == 200 and payload["ok"] is True

        cfg = config.load(str(tmp_path))
        assert cfg["ui"]["layers"] == {"loose": False}
        assert cfg["ui"]["floor_auto"] is False
    finally:
        stop(httpd, thread)


def test_prefs_endpoint_merges_layers_and_keeps_other_keys(tmp_path):
    """只发部分图层键时不能把已存的别的键冲掉，也不能动配置里其余的区块。"""
    import config

    config.save({"auto_zoom": True, "ui": {"layers": {"open": True, "locked": True}}}, str(tmp_path))
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        url = serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/prefs"
        _, payload = post_json(url, {"ui": {"layers": {"open": False}}})
        assert payload["ok"] is True

        cfg = config.load(str(tmp_path))
        assert cfg["ui"]["layers"] == {"open": False, "locked": True}
        assert cfg["auto_zoom"] is True
    finally:
        stop(httpd, thread)


def test_prefs_endpoint_can_change_auto_center(tmp_path):
    """HUD 上的「自动居中」按钮走同一条写回路径，与启动器里的同名勾选共用一份值。"""
    import config

    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        url = serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/prefs"
        _, payload = post_json(url, {"auto_center": False})
        assert payload["ok"] is True
        assert payload["config"]["auto_center"] is False
        assert config.load(str(tmp_path))["auto_center"] is False
    finally:
        stop(httpd, thread)


def test_prefs_endpoint_rejects_bad_body(tmp_path):
    """坏 JSON / 空体一律 400，且不把配置文件写坏。"""
    import config

    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        url = serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/prefs"
        status, payload = post_json(url, None, raw=b"{ not json")
        assert status == 400 and payload["ok"] is False
        assert config.load(str(tmp_path)) == config.default_config()
    finally:
        stop(httpd, thread)


def test_prefs_endpoint_unknown_path_is_json_404(tmp_path):
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        url = serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/nope"
        status, payload = post_json(url, {})
        assert status == 404 and payload["ok"] is False
    finally:
        stop(httpd, thread)


def test_prefs_endpoint_broadcasts_config_to_open_pages(tmp_path):
    """写回偏好后广播 config 事件，其它已经打开的页面能立刻跟上。"""
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        base = serve.url_for("127.0.0.1", httpd.server_address[1])
        with open_stream(base) as res:
            assert read_event(res, "config", 1)          # 连上时的首帧
            status, payload = post_json(base + "api/prefs", {"ui": {"layers": {"loose": False}}})
            assert status == 200 and payload["ok"] is True
            frames = read_event(res, "config", 1, timeout=10)
        assert frames and frames[0]["config"]["ui"]["layers"] == {"loose": False}
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- /api/logstate

def test_logstate_reports_disabled_without_game_dir(monkeypatch, tmp_path):
    # 隔离自动探测：显式关掉 default_game_dir，并用空白配置目录，验证「没有任何可识别日志目录时」应禁用
    monkeypatch.setattr(serve, "default_game_dir", lambda: None)
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        status, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/logstate")
        assert status == 200
        assert payload["available"] is False
        assert payload["raid"] is None
        assert payload["quests"] == []
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- /api/health · 自动截图

def test_health_exposes_shot_state(tmp_path):
    """health 要带上自动截图状态：launcher 自检与调试都靠它一眼看出开没开。"""
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/health")
        shot = payload["shot"]
        assert shot["enabled"] is False                  # 默认关闭
        # R108：默认非会员，健康检查里的间隔是锁定值 10000ms
        assert shot["intervalMs"] == config.SHOT_INTERVAL_LOCKED_MS
        assert shot["available"] is False                # 没开 = 不可能在拍
        assert shot["sent"] == 0
    finally:
        stop(httpd, thread)


def test_logstate_includes_shot_state(tmp_path):
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/logstate")
        assert payload["shot"]["enabled"] is False
        assert set(payload["shot"]) >= {"enabled", "intervalMs", "key", "sent", "available", "reason"}
    finally:
        stop(httpd, thread)


def test_sse_sends_shot_event_on_connect(tmp_path):
    """连上就先给一帧自动截图状态，页面首屏不必等第一次截图。"""
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    response = open_stream(serve.url_for("127.0.0.1", httpd.server_address[1]))
    try:
        shots = read_event(response, "shot")
        assert shots and shots[0]["enabled"] is False
    finally:
        response.close()
        stop(httpd, thread)


def test_server_close_stops_shotter_thread(tmp_path):
    """server_close 必须把自动截图线程一并停掉，否则进程退出后还在轮询配置。"""
    import config

    config.save({"auto_screenshot": {"enabled": False, "interval_ms": 1000, "key": "V"}}, str(tmp_path))
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    assert httpd.shotter._thread is not None
    stop(httpd, thread)
    assert httpd.shotter._thread is None


# --------------------------------------------------------------- /api/health · 自动删除截图

def test_health_exposes_clean_state(tmp_path):
    """health 要带上自动删除状态：默认关闭、没有已删计数。"""
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/health")
        clean = payload["clean"]
        assert clean["enabled"] is False                 # 默认关闭
        assert clean["available"] is False               # 没开 = 不可能在清理
        assert clean["deleted"] == 0
        assert clean["keepNewest"] == 1
    finally:
        stop(httpd, thread)


def test_logstate_includes_clean_state(tmp_path):
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/logstate")
        assert payload["clean"]["enabled"] is False
        assert set(payload["clean"]) >= {"enabled", "since", "keepNewest", "deleted",
                                         "lastDeletedAt", "available", "reason"}
    finally:
        stop(httpd, thread)


def test_sse_sends_clean_event_on_connect(tmp_path):
    """连上就先给一帧自动删除状态，页面首屏不必等第一次清理。"""
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    response = open_stream(serve.url_for("127.0.0.1", httpd.server_address[1]))
    try:
        cleans = read_event(response, "clean")
        assert cleans and cleans[0]["enabled"] is False
    finally:
        response.close()
        stop(httpd, thread)


def test_server_close_stops_pruner_thread(tmp_path):
    """server_close 必须把自动删除线程一并停掉，否则进程退出后还在扫截图目录。"""
    import config

    config.save({"auto_delete": {"enabled": False, "since": None}}, str(tmp_path))
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    assert httpd.pruner._thread is not None
    stop(httpd, thread)
    assert httpd.pruner._thread is None


# --------------------------------------------------------------- /sounds

def test_sounds_listing_and_serving(tmp_path):
    import config

    app = tmp_path / "app"
    app.mkdir()
    src = tmp_path / "bell.mp3"
    src.write_bytes(b"ID3fake")
    name = config.import_sound(str(src), str(app))

    _, httpd, thread = serve_dir(config_dir=str(app))
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        status, payload = get_json(base + "sounds")
        assert (status, payload["files"]) == (200, [name])

        status, ctype, body = get(base + "sounds/" + name)
        assert status == 200
        assert "audio/mpeg" in ctype
        assert body == b"ID3fake"
    finally:
        stop(httpd, thread)


def test_sounds_rejects_traversal_and_missing(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    _, httpd, thread = serve_dir(config_dir=str(app))
    base = serve.url_for("127.0.0.1", httpd.server_address[1])
    try:
        for path in ("sounds/ghost.mp3", "sounds/..%2F..%2Feftmap.config.json", "sounds/../../secret.mp3"):
            status, ctype, body = get(base + path)
            assert status == 404, path
            assert "application/json" in ctype
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- SSE 命名事件

def test_sse_sends_config_and_state_on_connect(tmp_path, monkeypatch):
    # 隔离自动探测，验证「未配置日志目录」时 state 快照的 available 为 False
    monkeypatch.setattr(serve, "default_game_dir", lambda: None)
    _, httpd, thread = serve_dir(config_dir=str(tmp_path))
    response = open_stream(serve.url_for("127.0.0.1", httpd.server_address[1]))
    try:
        configs = read_event(response, "config")
        states = read_event(response, "state")
        assert configs and configs[0]["config"]["auto_center"] is True
        assert states and states[0]["available"] is False
    finally:
        response.close()
        stop(httpd, thread)


def test_active_map_broadcasts_to_sse_clients(tmp_path, monkeypatch):
    # R-fix：主窗口切图上报 /api/active-map 后，应广播 `map` 事件给所有 SSE 客户端（小地图据此跟随）
    monkeypatch.setattr(serve, "default_game_dir", lambda: None)
    url, httpd, thread = serve_dir(config_dir=str(tmp_path))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        res = opener.open(url + "events", timeout=15)
        read_event(res, "config")  # 先消耗连上时的初始帧
        req = urllib.request.Request(
            url + "api/active-map",
            data=json.dumps({"map": "woods"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(req, timeout=5):
            pass
        maps = read_event(res, "map")
        assert maps and maps[0].get("map") == "woods"
        # 再次切换也应继续广播
        req2 = urllib.request.Request(
            url + "api/active-map",
            data=json.dumps({"map": "lighthouse"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(req2, timeout=5):
            pass
        maps2 = read_event(res, "map")
        assert maps2 and maps2[0].get("map") == "lighthouse"
    finally:
        res.close()
        stop(httpd, thread)


def test_sse_broadcasts_raid_and_quest_events(tmp_path):
    import eftlog

    game = tmp_path / "EFT"
    logs = game / "Logs"
    session = logs / "log_2026.10.17_19-42-17_1.2.5.0.48146"
    session.mkdir(parents=True)
    base_name = "2026.10.17_19-42-17_1.2.5.0.48146"
    (session / ("%s application_000.log" % base_name)).write_text("", encoding="utf-8")
    push = session / ("%s push-notifications_000.log" % base_name)
    push.write_text("", encoding="utf-8")

    _, httpd, thread = serve_dir(game_dir=str(game), config_dir=str(tmp_path), poll_interval=0.05)
    response = open_stream(serve.url_for("127.0.0.1", httpd.server_address[1]))
    try:
        read_event(response, "state")            # 先把首帧消费掉
        with open(session / ("%s application_000.log" % base_name), "a", encoding="utf-8") as fh:
            fh.write("2026-10-17 19:52:43.123 | scene preset path:maps/Bigmap_preset.bundle\n")
            fh.write("2026-10-17 19:52:44.123 | PlayerSpawnEvent:22.21(22.21)\n")
        with open(push, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "new_message", "message": {
                "templateId": "q1 description", "hasRewards": False,
                "dt": 1760787163}}) + "\n")       # 2026-10-17 前后的真实 unix 秒

        # R32.10：事件按时间戳合流广播，raid 与 quest 的先后不再是约定，
        # 两类一起收回来再分开断言（顺序不再是前提，内容仍然是）。
        got = _read_sse(response, 3, timeout=4.0, want=("raid", "quest"))
        raids = [e for e in got if e.get("type") == "raid"]
        quests = [e for e in got if e.get("type") == "quest"]
        assert [e["phase"] for e in raids] == ["map", "start"]
        assert raids[0]["mapId"] == "bigmap"
        assert quests and quests[0]["action"] == "started"
        assert eftlog.SESSION_RE.match(session.name)
    finally:
        response.close()
        stop(httpd, thread)


# --------------------------------------------------------------- 配置解析

def test_resolve_settings_prefers_cli_then_config_then_defaults(tmp_path, monkeypatch):
    import config

    game = tmp_path / "EFT"
    (game / "Logs").mkdir(parents=True)
    shots = tmp_path / "shots"
    shots.mkdir()
    config.save({"game_dir": str(game), "screenshots_dir": str(shots)}, str(tmp_path))

    class Args:
        screenshots = None
        game_dir = None
        config_dir = str(tmp_path)
        no_position = False
        no_logs = False

    settings = serve.resolve_settings(Args())
    assert (settings["game_dir"], settings["screenshots"]) == (str(game), str(shots))
    assert settings["app_dir"] == str(tmp_path)

    other = tmp_path / "other"
    other.mkdir()
    Args.game_dir = str(other)
    Args.screenshots = str(other)
    settings = serve.resolve_settings(Args())
    assert (settings["game_dir"], settings["screenshots"]) == (str(other), str(other))


def test_resolve_settings_ignores_nonexistent_and_off_switches(tmp_path):
    import config

    config.save({"game_dir": str(tmp_path / "ghost"), "screenshots_dir": str(tmp_path / "ghost2")},
                str(tmp_path))

    class Args:
        screenshots = None
        game_dir = None
        config_dir = str(tmp_path)
        no_position = True
        no_logs = True

    settings = serve.resolve_settings(Args())
    assert settings["game_dir"] is None
    assert settings["screenshots"] is None     # --no-position 关掉后即使自动定位也不启用


def test_default_game_dir_honours_env_var(tmp_path, monkeypatch):
    game = tmp_path / "MyEFT"
    (game / "Logs").mkdir(parents=True)
    monkeypatch.setenv("EFT_GAME_DIR", str(game))
    assert serve.default_game_dir() == str(game)

    monkeypatch.setenv("EFT_GAME_DIR", str(tmp_path / "nope"))
    assert serve.default_game_dir() != str(tmp_path / "nope")   # 无效值不该被采信


def test_default_game_dir_never_raises(monkeypatch):
    """探测不到就返回 None，探测到就返回**真实存在的目录**，两种都不许抛异常。

    这里刻意不再断言「一定是 None」：那等于假设跑测试的机器上没装游戏。
    本机装好 EFT 之后（D:\\Games\\EFT 这类默认位置）该断言就会误报，
    而函数行为其实完全正确。
    """
    monkeypatch.delenv("EFT_GAME_DIR", raising=False)
    monkeypatch.setattr(serve, "GAME_DIR_NAMES", ("绝不存在_EFT_目录",))
    result = serve.default_game_dir()
    assert result is None or os.path.isdir(result)


def test_parse_net_use_extracts_and_dedupes_hosts():
    """连接表输出里既有带盘符的映射，也有「记住的」无盘符共享，两种都要抽到且去重。"""
    text = (
        "\nStatus       Local     Remote                    Network\n"
        "-------------------------------------------------------------------------------\n"
        "OK                     \\\\JJPC\\Screenshots        Microsoft Windows Network\n"
        "OK           Z:         \\\\JJPC\\eft                Microsoft Windows Network\n"
        "OK                     \\\\NAS\\backup               Microsoft Windows Network\n"
    )
    assert serve.parse_net_use(text) == ["\\\\JJPC", "\\\\NAS"]
    assert serve.parse_net_use("") == []
    assert serve.parse_net_use(None) == []


def test_network_roots_survives_missing_net_command(monkeypatch):
    def boom(*_args, **_kwargs):
        raise FileNotFoundError("没有 net 命令")

    monkeypatch.setattr(serve.subprocess, "run", boom)
    assert serve._network_roots() == []


def test_default_game_dir_also_probes_network_shares(monkeypatch):
    """游戏装在别的机器共享盘上时（本地盘符扫不到），要能在网络主机上找到。"""
    monkeypatch.delenv("EFT_GAME_DIR", raising=False)
    monkeypatch.setattr(serve, "_network_roots", lambda: ["\\\\JJPC"])
    seen: list[str] = []
    target = os.path.join("\\\\JJPC", "EFT")

    def fake_looks(path):
        seen.append(path)
        return path == target

    monkeypatch.setattr(serve, "_looks_like_game_dir", fake_looks)
    assert serve.default_game_dir() == target
    assert target in seen


def test_health_exposes_log_monitoring(tmp_path):
    game = tmp_path / "EFT"
    (game / "Logs").mkdir(parents=True)
    _, httpd, thread = serve_dir(game_dir=str(game), config_dir=str(tmp_path))
    try:
        _, payload = get_json(serve.url_for("127.0.0.1", httpd.server_address[1]) + "api/health")
        assert payload["logs"] is True
        assert payload["gameDir"] == str(game)
        assert payload["logDir"] == str(game / "Logs")
        assert payload["logSession"] is None      # 还没有会话
    finally:
        stop(httpd, thread)


# --------------------------------------------------------------- R107 自动探测
def test_detect_logs_dir_prefers_session_with_application_log(tmp_path, monkeypatch):
    """多会话时选「最新且真的含 application 日志」的那个，空壳会话不能算命中。"""
    monkeypatch.setattr(serve, "_documents_dirs", lambda: [])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-missing"))
    logs = tmp_path / "Logs"
    old = logs / "log_2026.10.01_10-00-00_1.0.0.0.40000"
    new = logs / "log_2026.10.02_10-00-00_1.0.0.0.40001"
    old.mkdir(parents=True)
    new.mkdir()
    (old / "2026.10.01_10-00-00_1.0.0.0.40000 application_000.log").write_text("", encoding="utf-8")

    found, note = serve.detect_logs_dir(str(tmp_path))
    assert found == str(logs)
    assert "2026.10.01" in (note or "")


def test_detect_screenshots_dir_picks_most_recent(tmp_path, monkeypatch):
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    fake_shot(a, 1, 1, when=1_000_000)
    fake_shot(b, 1, 1, when=2_000_000)
    monkeypatch.setattr(serve, "screenshot_dir_candidates", lambda game_dir=None: [str(a), str(b)])
    found, _note = serve.detect_screenshots_dir()
    assert found == str(b)


def test_path_resolver_manual_paths_win_over_auto(tmp_path, monkeypatch):
    app = tmp_path / "cfg"
    manual_shots = tmp_path / "manual-shots"
    manual_logs = tmp_path / "manual-logs"
    manual_shots.mkdir()
    manual_logs.mkdir()
    config.save({"screenshots_dir": str(manual_shots), "log_dir": str(manual_logs)}, str(app))
    monkeypatch.setattr(serve, "detect_screenshots_dir", lambda game_dir=None: (str(tmp_path / "auto"), "auto"))
    monkeypatch.setattr(serve, "detect_logs_dir", lambda game_dir=None: (str(tmp_path / "auto"), "auto"))

    resolver = serve.PathResolver(str(app))
    assert resolver.screenshots_dir() == str(manual_shots)
    assert resolver.logs_dir() == str(manual_logs)
    snap = resolver.snapshot()
    assert snap["screenshotsManual"] is True
    assert snap["logManual"] is True


def test_shot_manifest_add_and_discard(tmp_path):
    manifest = serve.ShotManifest(str(tmp_path))
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    manifest.add(str(first))
    manifest.add(str(second))
    assert manifest.list() == [str(first), str(second)]
    manifest.discard([str(first)])
    assert manifest.list() == [str(second)]


def test_raid_end_cleaner_only_deletes_manifest_files(tmp_path):
    """保守清理：只删清单内（本工具按键后新出现）的图，手动截图原样保留。"""
    shots = tmp_path / "shots"
    shots.mkdir()
    auto = shots / "auto.png"
    manual = shots / "manual.png"
    auto.write_bytes(b"auto")
    manual.write_bytes(b"manual")
    app = tmp_path / "cfg"
    config.save({"screenshots_dir": str(shots),
                 "auto_screenshot": {"cleanup_on_raid_end": True}}, str(app))
    manifest = serve.ShotManifest(str(app))
    manifest.add(str(auto))

    cleaner = serve.RaidEndCleaner(str(app), manifest, directory=str(shots))
    result = cleaner.cleanup()
    assert result["deleted"] == 1
    assert auto.exists() is False
    assert manual.exists() is True
    assert manifest.list() == []


