"""`tools/launcher.py` 的测试：四步编排顺序、失败路径与退出清理。

界面（tkinter）不参与测试——编排与界面是分开的，`Startup` 的依赖全部可注入，
所以这里用桩件替换「起服务 / 自检 / 开浏览器」，不弹窗、不开浏览器。
最后一个用例用真实的 serve.create_server 跑一遍端到端，确认连接与清理都对。
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

import launcher
import serve

ROOT = Path(__file__).resolve().parent.parent


class FakeServer:
    """最小可用的服务替身：记录 shutdown/server_close 被调用过，避免 stop() 挂住。"""

    def __init__(self, port: int = serve.DEFAULT_PORT):
        self.server_address = ("127.0.0.1", port)
        self.calls: list[str] = []
        self._stop = threading.Event()

    def serve_forever(self):
        self.calls.append("serve_forever")
        self._stop.wait(timeout=5)

    def shutdown(self):
        self.calls.append("shutdown")
        self._stop.set()

    def server_close(self):
        self.calls.append("server_close")


def make_startup(root=ROOT, on_step=None, open_browser=None, health=None, create_server=None, port=serve.DEFAULT_PORT):
    """装好桩件的 Startup；返回 (startup, 记录容器)。"""
    rec = {"servers": [], "opened": [], "create_args": []}

    def _create(p, h, r, screenshots=None):
        rec["create_args"].append((p, h, r))
        rec["screenshots"] = screenshots
        srv = FakeServer(port)
        rec["servers"].append(srv)
        return srv

    def _open(url):
        rec["opened"].append(url)
        return True

    startup = launcher.Startup(
        root=str(root),
        port=port,
        create_server=create_server or _create,
        open_browser=open_browser or _open,
        health=health or (lambda url: {"ok": True, "version": launcher.VERSION}),
        on_step=on_step,
    )
    return startup, rec


# --------------------------------------------------------------- 成功路径

def test_steps_run_in_order():
    seen = []
    startup, rec = make_startup(on_step=lambda step, state, detail: seen.append((step, state)))
    startup.run()

    assert seen == [
        (launcher.STEP_CHECK, "running"), (launcher.STEP_CHECK, "done"),
        (launcher.STEP_SERVER, "running"), (launcher.STEP_SERVER, "done"),
        (launcher.STEP_SELFCHECK, "running"), (launcher.STEP_SELFCHECK, "done"),
        (launcher.STEP_BROWSER, "running"), (launcher.STEP_BROWSER, "done"),
    ]


def test_success_opens_single_url_and_keeps_server_alive():
    startup, rec = make_startup()
    startup.run()

    assert startup.url == "http://127.0.0.1:%d/" % serve.DEFAULT_PORT
    assert rec["opened"] == [startup.url]
    assert rec["create_args"][0][2] == str(ROOT)          # 把站点根目录交给了 serve
    assert "shutdown" not in rec["servers"][0].calls     # 启动成功就保持服务在跑
    startup.stop()
    assert rec["servers"][0].calls[-2:] == ["shutdown", "server_close"]


def test_step_detail_reports_map_count():
    details = {}
    startup, _ = make_startup(on_step=lambda step, state, detail: details.update({state and step: detail}))
    startup.run()
    assert "张地图" in details[launcher.STEP_CHECK]


# --------------------------------------------------------------- 失败路径

def test_missing_data_fails_before_touching_server(tmp_path):
    """数据没拉过：第一步就失败，且不去占端口、不开浏览器。"""
    seen = []
    startup, rec = make_startup(root=tmp_path, on_step=lambda s, st, d: seen.append((s, st, d)))
    with pytest.raises(launcher.StartupError) as info:
        startup.run()

    assert info.value.step == launcher.STEP_CHECK
    assert "fetch_data.py" in info.value.hint
    assert rec["servers"] == []
    assert rec["opened"] == []
    assert (launcher.STEP_CHECK, "failed") in [(s, st) for s, st, _ in seen]


def test_port_in_use_becomes_actionable_error():
    def _boom(port, host, root, screenshots=None):
        raise serve.PortInUseError("端口 %d 已被占用。" % port)

    startup, rec = make_startup(create_server=_boom)
    with pytest.raises(launcher.StartupError) as info:
        startup.run()

    assert info.value.step == launcher.STEP_SERVER
    assert "--port" in info.value.hint
    assert rec["opened"] == []


def test_self_check_failure_shuts_down_half_started_server():
    """自检不过必须把刚起的服务关掉，不留一个半活的端口。"""
    def _unhealthy(url):
        raise TimeoutError("自检超时")

    startup, rec = make_startup(health=_unhealthy)
    with pytest.raises(launcher.StartupError) as info:
        startup.run()

    assert info.value.step == launcher.STEP_SELFCHECK
    assert rec["servers"][0].calls[-2:] == ["shutdown", "server_close"]
    assert startup.server is None
    assert rec["opened"] == []


def test_browser_failure_is_not_fatal():
    """浏览器打不开不该把已就绪的服务关掉，页面仍可手动访问。"""
    def _boom(url):
        raise OSError("no browser")

    seen = []
    startup, rec = make_startup(open_browser=_boom, on_step=lambda s, st, d: seen.append((s, st, d)))
    startup.run()   # 不抛异常

    assert startup.server is not None
    detail = [d for s, st, d in seen if s == launcher.STEP_BROWSER and st == "done"][0]
    assert "手动访问" in detail and startup.url in detail
    startup.stop()


def test_stop_is_idempotent():
    startup, rec = make_startup()
    startup.run()
    startup.stop()
    startup.stop()   # 再调一次不应该报错，也不应该重复关闭
    assert rec["servers"][0].calls.count("server_close") == 1


def test_retry_after_failure_resets_and_reruns(tmp_path):
    """先失败（数据缺失）再重试成功：状态回到 pending 再逐条 done。"""
    seen = []
    startup, rec = make_startup(root=tmp_path, on_step=lambda s, st, d: seen.append((s, st)))
    with pytest.raises(launcher.StartupError):
        startup.run()

    startup.root = str(ROOT)
    startup.retry()

    assert seen[-1] == (launcher.STEP_BROWSER, "done")
    assert (launcher.STEP_CHECK, "pending") in seen[-12:]   # 重试会先把四步刷回 pending
    assert len(rec["opened"]) == 1


# --------------------------------------------------------------- 截图目录解析

def test_screenshots_passed_through_when_explicitly_given(tmp_path):
    """显式给了截图目录：必须原样交给 create_server（实时定位才会开）。"""
    startup, rec = make_startup(root=ROOT, port=0, create_server=serve.create_server)
    startup.screenshots = str(tmp_path)
    startup.step_check_data()
    startup.step_start_server()
    try:
        assert startup.screenshots_resolved == str(tmp_path)
        assert startup.server.tracker.enabled() is True
    finally:
        startup.stop()


def test_default_screenshot_dir_used_only_when_it_exists(tmp_path, monkeypatch):
    """没给参数时自动探测默认目录：目录存在才开监听，不存在就静默关闭（不报错）。"""
    monkeypatch.setattr(serve, "default_screenshots_dir", lambda: str(tmp_path))
    startup, rec = make_startup(root=ROOT, port=0, create_server=serve.create_server)
    startup.step_check_data()
    startup.step_start_server()
    try:
        assert startup.screenshots_resolved == str(tmp_path)
        assert startup.server.tracker.enabled() is True
    finally:
        startup.stop()

    missing = tmp_path / "nope"
    monkeypatch.setattr(serve, "default_screenshots_dir", lambda: str(missing))
    startup2, _ = make_startup(root=ROOT, port=0, create_server=serve.create_server)
    startup2.step_check_data()
    startup2.step_start_server()
    try:
        assert startup2.screenshots_resolved is None
        assert startup2.server.tracker.enabled() is False
    finally:
        startup2.stop()


def test_self_check_reports_position_state(tmp_path):
    """自检那一步要把「实时定位有没有开」讲清楚，用户才知道要不要设截图目录。"""
    seen = []
    startup, _ = make_startup(root=ROOT, port=0, create_server=serve.create_server,
                              health=launcher.check_health,
                              on_step=lambda step, state, detail: seen.append((step, state, detail)))
    startup.screenshots = str(tmp_path)
    startup.run()
    try:
        detail = [d for s, st, d in seen if s == launcher.STEP_SELFCHECK and st == "done"][0]
        assert "实时定位已开启" in detail
    finally:
        startup.stop()


# --------------------------------------------------------------- 真实服务端到端

def test_run_with_real_server_is_reachable_and_cleans_up():
    """走真实 serve + 真实自检：port=0 让系统分配端口，跑完能访问、退出能清理。"""
    startup, rec = make_startup(port=0, create_server=serve.create_server, health=launcher.check_health)
    startup.run()

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(startup.url + "api/health", timeout=10) as res:
        payload = json.loads(res.read().decode("utf-8"))
    assert payload["ok"] is True
    assert payload["app"] == serve.APP_ID

    thread = startup.thread
    startup.stop()
    assert not thread.is_alive()


def test_check_health_times_out_with_last_reason():
    with pytest.raises(TimeoutError):
        launcher.check_health("http://127.0.0.1:1/", timeout=0.6, interval=0.1)


def test_check_health_returns_payload_from_live_server():
    startup, _ = make_startup(port=0, create_server=serve.create_server)
    startup.step_check_data()
    startup.step_start_server()
    try:
        payload = launcher.check_health(startup.url, timeout=8)
        assert payload["ok"] is True
    finally:
        startup.stop()


def test_app_root_points_at_repo_when_not_frozen():
    assert launcher.app_root() == str(ROOT)


def test_parse_args_defaults_and_flags():
    args = launcher.parse_args([])
    assert (args.host, args.port, args.no_browser, args.screenshots) == (serve.DEFAULT_HOST, serve.DEFAULT_PORT, False, None)
    args = launcher.parse_args(["--port", "9100", "--no-browser", "--screenshots", "C:/shots"])
    assert (args.port, args.no_browser, args.screenshots) == (9100, True, "C:/shots")
