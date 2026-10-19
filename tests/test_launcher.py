"""`tools/launcher.py` 的测试：四步编排顺序、失败路径与退出清理。

界面（tkinter）不参与测试——编排与界面是分开的，`Startup` 的依赖全部可注入，
所以这里用桩件替换「起服务 / 自检 / 开浏览器」，不弹窗、不开浏览器。
最后一个用例用真实的 serve.create_server 跑一遍端到端，确认连接与清理都对。
"""

from __future__ import annotations

import json
import threading
import time
import types
import urllib.request
from pathlib import Path

import pytest

import config
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
    rec = {"servers": [], "opened": [], "create_args": [], "create_kwargs": []}

    def _create(p, h, r, screenshots=None, **kwargs):
        rec["create_args"].append((p, h, r))
        rec["create_kwargs"].append(dict(kwargs, screenshots=screenshots))
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


# --------------------------------------------------------------- 加壳版（独立应用窗口）

def test_parse_args_app_window_flag_defaults_off():
    assert launcher.parse_args([]).app_window is False
    assert launcher.parse_args(["--app-window"]).app_window is True


def test_app_mode_enabled_reads_flag_in_resource_dir(tmp_path, monkeypatch):
    """资源目录里出现 appmode.flag 才算加壳版；没有就是普通版。"""
    monkeypatch.setattr(launcher, "app_root", lambda: str(tmp_path))
    assert launcher.app_mode_enabled() is False
    (tmp_path / launcher.APP_MODE_FLAG).write_text("1", encoding="utf-8")
    assert launcher.app_mode_enabled() is True


def test_find_app_browser_returns_first_existing(tmp_path, monkeypatch):
    missing = tmp_path / "no-such-browser.exe"
    found = tmp_path / "msedge.exe"
    found.write_bytes(b"")
    monkeypatch.setattr(launcher, "_APP_WINDOW_BROWSERS", (str(missing), str(found)))
    assert launcher.find_app_browser() == str(found)


def test_find_app_browser_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "_APP_WINDOW_BROWSERS", (str(tmp_path / "nope.exe"),))
    assert launcher.find_app_browser() is None


def test_open_app_window_launches_app_mode_and_returns_true(monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, "find_app_browser", lambda: "C:/edge.exe")
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda argv, **kw: calls.append(argv))
    assert launcher.open_app_window("http://127.0.0.1:8787/") is True
    assert calls == [["C:/edge.exe", "--app=http://127.0.0.1:8787/"]]


def test_open_app_window_falls_back_to_default_browser(monkeypatch):
    monkeypatch.setattr(launcher, "find_app_browser", lambda: None)
    seen = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: seen.append(url) or True)
    assert launcher.open_app_window("http://x/") is True
    assert seen == ["http://x/"]


def test_open_app_window_falls_back_when_launch_fails(monkeypatch):
    """内核在、但起不来（被杀软拦等）→ 退回默认浏览器，不能打不开。"""
    monkeypatch.setattr(launcher, "find_app_browser", lambda: "C:/edge.exe")

    def boom(argv, **kw):
        raise OSError("blocked")

    monkeypatch.setattr(launcher.subprocess, "Popen", boom)
    seen = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: seen.append(url) or True)
    assert launcher.open_app_window("http://x/") is True
    assert seen == ["http://x/"]


# --------------------------------------------------------------- 目录与配置的纯函数

def test_resolve_dirs_prefers_explicit_then_config_then_auto(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    auto = tmp_path / "auto"
    auto.mkdir()
    monkeypatch.setattr(serve, "default_game_dir", lambda: str(auto))
    monkeypatch.setattr(serve, "default_screenshots_dir", lambda: str(auto))

    cfg = {"game_dir": str(remembered), "screenshots_dir": str(remembered)}
    assert launcher.resolve_dirs(cfg, str(explicit)) == (str(explicit), str(remembered))
    assert launcher.resolve_dirs(cfg) == (str(remembered), str(remembered))
    assert launcher.resolve_dirs({}) == (str(auto), str(auto))


def test_resolve_dirs_drops_nonexistent_paths(tmp_path):
    """配置里记着的目录被删了：不能把一个用不了的路径显示在界面上。"""
    cfg = {"game_dir": str(tmp_path / "gone"), "screenshots_dir": str(tmp_path / "gone2")}
    assert launcher.resolve_dirs(cfg) == ("", "")


def test_build_config_shape_and_bool_coercion(tmp_path):
    cfg = launcher.build_config(
        game_dir=str(tmp_path), screenshots_dir="", auto_zoom=True,
        auto_center=False, auto_start=True, sound_enabled=True,
        sound_on={"raid_start": False}, sound_files={"matching": "bell.mp3"},
    )
    assert cfg["game_dir"] == str(tmp_path)
    assert cfg["screenshots_dir"] is None              # 空串不写进配置
    assert cfg["auto_zoom"] is True and cfg["auto_center"] is False and cfg["auto_start"] is True
    assert cfg["sound"]["enabled"] is True
    assert cfg["sound"]["raid_start"] == {"on": False, "file": None}
    assert cfg["sound"]["matching"] == {"on": True, "file": "bell.mp3"}
    assert cfg["sound"]["location_loading"] == {"on": True, "file": None}


def test_build_config_round_trips_through_config_module(tmp_path):
    """build_config 的产物必须能被 config.normalize 原样收下（两个模块的契约）。"""
    cfg = launcher.build_config(game_dir="E:\\EFT", auto_zoom=True, sound_enabled=True,
                                sound_files={"raid_start": "bell.wav"})
    (tmp_path / config.CONFIG_NAME).write_text(json.dumps(cfg), encoding="utf-8")
    assert config.normalize(cfg) == config.load(str(tmp_path))


# --------------------------------------------------------------- 自动截图配置

def test_build_config_auto_screenshot_defaults_to_off():
    cfg = launcher.build_config()
    assert cfg["auto_screenshot"] == {"enabled": False, "interval_ms": config.SHOT_INTERVAL_DEFAULT,
                                      "key": None}


def test_build_config_auto_screenshot_passes_values():
    cfg = launcher.build_config(auto_screenshot=True, shot_interval_ms=2500, shot_key="  V  ")
    assert cfg["auto_screenshot"] == {"enabled": True, "interval_ms": 2500, "key": "V"}


def test_build_config_auto_screenshot_blank_key_is_none():
    cfg = launcher.build_config(shot_key="   ")
    assert cfg["auto_screenshot"]["key"] is None


@pytest.mark.parametrize("raw,expect", [
    (50, config.SHOT_INTERVAL_MIN),
    (10_000_000, config.SHOT_INTERVAL_MAX),
    ("abc", config.SHOT_INTERVAL_DEFAULT),
])
def test_build_config_clamps_interval(raw, expect):
    """界面上的间隔输入必须被钳死，否则用户手滑输入 50 会让截图目录瞬间爆炸。"""
    cfg = launcher.build_config(auto_screenshot=True, shot_interval_ms=raw)
    assert cfg["auto_screenshot"]["interval_ms"] == expect


def test_build_config_auto_screenshot_round_trips(tmp_path):
    cfg = launcher.build_config(auto_screenshot=True, shot_interval_ms=1500, shot_key="V")
    (tmp_path / config.CONFIG_NAME).write_text(json.dumps(cfg), encoding="utf-8")
    loaded = config.load(str(tmp_path))
    assert loaded["auto_screenshot"] == cfg["auto_screenshot"]


# --------------------------------------------------------------- 自动删除截图配置

def test_build_config_auto_delete_defaults_to_off():
    cfg = launcher.build_config()
    assert cfg["auto_delete"] == {"enabled": False, "since": None}


def test_build_config_auto_delete_passes_since():
    cfg = launcher.build_config(auto_delete=True, delete_since=1700000000.0)
    assert cfg["auto_delete"] == {"enabled": True, "since": 1700000000.0}


def test_build_config_auto_delete_off_clears_since():
    """开关关着时 `since` 必须归 None，否则下次开启会沿用旧时间闸、把新截图也扫进清理范围。"""
    cfg = launcher.build_config(auto_delete=False, delete_since=1700000000.0)
    assert cfg["auto_delete"] == {"enabled": False, "since": None}


def test_build_config_auto_delete_round_trips(tmp_path):
    cfg = launcher.build_config(auto_delete=True, delete_since=1700000000.0)
    (tmp_path / config.CONFIG_NAME).write_text(json.dumps(cfg), encoding="utf-8")
    loaded = config.load(str(tmp_path))
    assert loaded["auto_delete"] == cfg["auto_delete"]


# --------------------------------------------------------------- 游戏目录透传

def test_game_dir_and_config_dir_are_passed_to_server(tmp_path):
    """界面里填的游戏目录要真的交给 serve，日志监控/自动切图才会开。"""
    game = tmp_path / "EFT"
    (game / "Logs").mkdir(parents=True)
    startup, rec = make_startup(root=ROOT, port=0)
    startup.game_dir = str(game)
    startup.config_dir = str(tmp_path)
    startup.step_check_data()
    startup.step_start_server()
    try:
        assert rec["create_kwargs"][0]["game_dir"] == str(game)
        assert rec["create_kwargs"][0]["config_dir"] == str(tmp_path)
        assert startup.game_dir_resolved == str(game)
    finally:
        startup.stop()


def test_no_game_dir_means_no_log_monitoring(tmp_path):
    """没填游戏目录就不启用日志监控（清空目录 = 关掉自动切图，不该被自动定位顶回来）。"""
    startup, rec = make_startup(root=ROOT, port=0)
    startup.game_dir = None
    startup.step_check_data()
    startup.step_start_server()
    try:
        assert "game_dir" not in rec["create_kwargs"][0]
        assert startup.game_dir_resolved is None
    finally:
        startup.stop()


def test_self_check_reports_log_monitoring(tmp_path):
    seen = []
    startup, _ = make_startup(root=ROOT, port=0, create_server=serve.create_server,
                              health=launcher.check_health,
                              on_step=lambda step, state, detail: seen.append((step, state, detail)))
    startup.screenshots = str(tmp_path / "no-shots")     # 指一个不存在的目录，避免依赖本机环境
    startup.step_check_data()
    startup.step_start_server()
    try:
        startup.step_self_check()
        detail = [d for s, st, d in seen if s == launcher.STEP_SELFCHECK and st == "done"][0]
        assert "日志监控未开启" in detail
    finally:
        startup.stop()


def test_self_check_reports_log_monitoring_enabled(tmp_path):
    game = tmp_path / "EFT"
    (game / "Logs").mkdir(parents=True)
    seen = []
    startup, _ = make_startup(root=ROOT, port=0, create_server=serve.create_server,
                              health=launcher.check_health,
                              on_step=lambda step, state, detail: seen.append((step, state, detail)))
    startup.game_dir = str(game)
    startup.screenshots = str(tmp_path / "no-shots")
    startup.step_check_data()
    startup.step_start_server()
    try:
        startup.step_self_check()
        detail = [d for s, st, d in seen if s == launcher.STEP_SELFCHECK and st == "done"][0]
        assert "日志监控已开启（自动切图 / 任务事件）" in detail
    finally:
        startup.stop()


# --------------------------------------------------------------- 落盘时的界面偏好

def _stub_window(tmp_path, **overrides):
    """不弹窗地拿到一个「够用」的启动器窗口替身：只补 `_save` 会碰到的属性。"""
    fields = dict(
        app_dir=str(tmp_path),
        current_config=lambda: launcher.build_config(auto_zoom=True),
        message=types.SimpleNamespace(configure=lambda **kw: None),
    )
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


def test_save_keeps_page_ui_prefs(tmp_path):
    """启动器落盘必须带上磁盘上的 ui 块。

    `build_config()` 的产物里没有 ui 键，`config.normalize()` 会把它归成 `{}`；
    不补回来的话，表单每失焦一次就把 WebUI 刚保存的图层勾选抹掉一次。
    """
    config.save({"ui": {"layers": {"extract_scav": False}, "floor_auto": False}}, str(tmp_path))
    assert launcher.LaunchWindow._save(_stub_window(tmp_path)) is True

    loaded = config.load(str(tmp_path))
    assert loaded["ui"] == {"layers": {"extract_scav": False}, "floor_auto": False}
    assert loaded["auto_zoom"] is True          # 启动器自己那几项照常写进去


def test_save_survives_missing_ui_block(tmp_path):
    """磁盘上还没有 ui 块（用户从没在页面上点过）时，落盘不能报错。"""
    assert launcher.LaunchWindow._save(_stub_window(tmp_path)) is True
    assert config.load(str(tmp_path))["ui"] == {}


def test_save_reports_failure_without_raising(tmp_path, monkeypatch):
    """落盘失败（磁盘满 / 没权限）只能提示，不能把启动流程炸掉。"""
    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(config, "save", _boom)
    assert launcher.LaunchWindow._save(_stub_window(tmp_path)) is False
